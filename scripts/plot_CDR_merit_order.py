"""
CDR merit-order / marginal abatement cost curve.

Standalone diagnostic — run from the pypsa-eur root:

    python scripts/plot_CDR_merit_order.py CDRs_2050

One bar per (CDR technology, node) combination, sorted along the x-axis from
cheapest to most expensive Levelized Cost of CDR (LCCDR, gross — excludes the
CO2 credit). Bar width = that node's technical potential (e_nom / e_nom_max).
A horizontal line marks the system's CO2 shadow price (CO2Limit dual).

Solid bars reuse compute_cdr_per_node() from plot_CDR_map.py verbatim — the
exact same per-node LCCDR (observed, time-resolved dispatch and local
marginal prices, so e.g. rock weathering's electricity-price timing
arbitrage is captured correctly) that feeds the CDR_costs_map panels.

Nodes with no observed CO2 flow (lccdr_gross is NaN there -- undeployed, no
real dispatch to read a cost off) get a hatched bar instead of being
dropped: capex and VOM are read from the same static per-node parameters as
usual, but energy inputs/co-products are priced at each node's own
snapshot-weighted *mean* local price rather than a real dispatch profile,
since there's no actual solved timing to draw from. This is a hypothetical
"if built and run uniformly all year" estimate, not an optimized one -- it
misses any price-timing arbitrage a real dispatch could capture (relevant
for technologies with a wide-open, unrestricted dispatch window, e.g.
biochar and rock weathering), so it should be read as an upper-bound-ish
estimate, not an exact figure. Flagged in the legend/caption accordingly.

A 5th series, "Geological CO2 storage", adds the generic underground
sequestration potential (carrier "co2 sequestered") -- NOT a removal
technology like the other four (it has no link to the atmosphere at all;
it's fed by whatever capture technologies -- DAC, BECCS, industrial CC --
happen to be active elsewhere in the model). Its LCCDR is the end-to-end
bus-price gap (system CO2 price - price at that node's "co2 sequestered"
bus), bundling whatever capture technology + CO2 pipeline transport is
marginally cheapest to get a tonne there -- see sequestration_lccdr() for
why this is used instead of the store's own capacity-bound dual
(mu_ext_e_nom_upper), which turns out to be near-zero and uninformative
almost everywhere. Because this answers "cost of capture + transport +
final injection" rather than "cost of removing a tonne from the atmosphere
via a dedicated technology", it isn't a direct substitute for the other
four and its potential shouldn't be read as competing 1:1 with theirs on
this shared x-axis -- shown here for cost comparison only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
import yaml

from _check_utils import parse_check_args, load_check_params
from plot_CDR_map import CDR_TECHS, compute_cdr_per_node


def hypothetical_lccdr(n, carrier, sw, mp, locations):
    """
    Analytic "if fully built and run uniformly all year" LCCDR for a given
    subset of undeployed nodes, using each node's own snapshot-weighted mean
    local price for every non-CDR, non-atmosphere bus the link touches --
    i.e. no price-timing arbitrage, just "capex + VOM + inputs/co-products
    at their average price".

    `locations` are location names (compute_cdr_per_node()'s index, e.g.
    "AL2 0") -- resolved back to the underlying Store via each store's own
    bus's "location" attribute. Returns a Series indexed by location name
    (EUR/tCO2), aligned with the "potential" column already computed by
    compute_cdr_per_node.
    """
    stores = n.stores[n.stores.carrier == carrier]
    links = n.links[n.links.carrier == carrier]
    if stores.empty or links.empty or not len(locations):
        return pd.Series(dtype=float)

    store_bus_to_link = {}
    for lk_name, lk in links.iterrows():
        for i in range(5):
            bus_col = f"bus{i}"
            if bus_col not in links.columns:
                continue
            bus = lk.get(bus_col)
            if not isinstance(bus, str) or not bus or bus not in n.buses.index:
                continue
            if n.buses.at[bus, "carrier"] == carrier:
                store_bus_to_link[bus] = lk_name

    location_to_store = {}
    for store_name, store in stores.iterrows():
        loc = n.buses.at[store["bus"], "location"] if store["bus"] in n.buses.index else None
        if loc:
            location_to_store[loc] = store_name

    mean_price = mp.mul(sw, axis=0).sum() / sw.sum() if mp is not None else None

    out = {}
    for location in locations:
        store_name = location_to_store.get(location)
        if store_name is None:
            continue
        store = stores.loc[store_name]
        store_bus = store["bus"]
        potential = (
            float(store["e_nom_max"])
            if bool(store.get("e_nom_extendable", False))
            else float(store["e_nom"])
        )
        if not np.isfinite(potential) or potential <= 0:
            continue

        link_name = store_bus_to_link.get(store_bus)
        if link_name is None or link_name not in links.index:
            continue
        link = links.loc[link_name]

        i_store = None
        for i in range(1, 5):
            bus_col = f"bus{i}"
            if bus_col in links.columns and link.get(bus_col) == store_bus:
                i_store = i
                break
        if i_store is None:
            continue
        eff_col = "efficiency" if i_store == 1 else f"efficiency{i_store}"
        eff_store = link.get(eff_col, 0.0)
        if eff_store == 0.0:
            continue

        if link_name in n.links_t.p_max_pu.columns:
            pmax_t = n.links_t.p_max_pu[link_name]
        else:
            pmax_t = pd.Series(float(link.get("p_max_pu", 1.0)), index=sw.index)

        hours_factor = (eff_store * pmax_t * sw).sum()
        if hours_factor <= 0:
            continue
        p_nom_full = potential / hours_factor
        p0_full_mean = p_nom_full * (pmax_t * sw).sum() / sw.sum()  # snapshot-weighted mean p0

        capex = link.get("capital_cost", 0.0) * p_nom_full + store.get("capital_cost", 0.0) * potential
        vom = link.get("marginal_cost", 0.0) * p0_full_mean * sw.sum()

        bus_other = 0.0
        for i in range(5):
            bus_col = f"bus{i}"
            if bus_col not in links.columns:
                continue
            bus_name = link.get(bus_col)
            if not isinstance(bus_name, str) or not bus_name or bus_name not in n.buses.index:
                continue
            bus_carrier = n.buses.at[bus_name, "carrier"]
            if bus_carrier in (carrier, "co2"):
                continue
            if mean_price is None or bus_name not in mean_price.index:
                continue
            price_mean = mean_price[bus_name]
            if i == 0:
                p_i_full_mean = p0_full_mean
            else:
                eff_col_i = "efficiency" if i == 1 else f"efficiency{i}"
                if eff_col_i not in links.columns:
                    continue
                eff_i = link.get(eff_col_i, 0.0)
                if eff_i == 0.0:
                    continue
                p_i_full_mean = -eff_i * p0_full_mean
            bus_other += price_mean * p_i_full_mean * sw.sum()

        out[location] = (capex + vom + bus_other) / potential

    return pd.Series(out, dtype=float)


def sequestration_lccdr(n, co2_price, sw):
    """
    Per-node LCCDR for the generic geological CO2 sequestration store
    (carrier "co2 sequestered"), restricted to nodes with real local
    geological potential (e_nom_max > 0 -- see module docstring for why
    nodes without local geology aren't a "destination" in their own right).

    Uses the end-to-end bus-price gap, not the store's capacity-bound dual
    (mu_ext_e_nom_upper): mu_ext only reflects whether the local geological
    *ceiling* is binding, which is mostly slack here (supply-limited by
    upstream capture, not cost), making it near-zero and uninformative
    almost everywhere. The bus-price gap instead captures the full,
    technology-agnostic cost of getting a marginal tCO2 from the atmosphere,
    through whatever capture technology + CO2 pipeline network is marginally
    cheapest, into this specific node's permanent storage:

        LCCDR = mean_price("<node> co2 sequestered") + co2_price

    This is robust to the near-zero-flow noise that plagues ratio-based
    LCCDR (observed capex / observed flow): it's a direct bus price, not a
    ratio, so it stays well-behaved even for barely-used nodes.

    Bar width uses e_nom_opt (actually-used storage), not e_nom_max (the
    technical ceiling): unlike the other four CDR techs, sequestration
    utilisation is often genuinely partial rather than bang-bang (its
    "supply" is capped by whatever CO2 the various capture technologies
    elsewhere in the model produce, not solely by its own economics), so
    e_nom_max would overstate how much of this node's ceiling is actually
    relevant right now.

    Returns a DataFrame indexed by node with columns ["potential", "lccdr"].
    """
    stores = n.stores[n.stores.carrier == "co2 sequestered"]
    if stores.empty:
        return pd.DataFrame(columns=["potential", "lccdr"])

    mp = n.buses_t.marginal_price if "marginal_price" in n.buses_t else None
    mean_price = mp.mul(sw, axis=0).sum() / sw.sum() if mp is not None else None

    records = []
    for store_name, store in stores.iterrows():
        e_nom_max = float(store["e_nom_max"])
        if not np.isfinite(e_nom_max) or e_nom_max <= 0:
            continue
        used = float(store.get("e_nom_opt", 0.0))
        if used <= 0:
            continue
        bus = store["bus"]
        if mean_price is None or bus not in mean_price.index:
            continue
        node = n.buses.at[bus, "location"] if bus in n.buses.index else store_name
        records.append(dict(node=node, potential=used, lccdr=mean_price[bus] + co2_price))

    if not records:
        return pd.DataFrame(columns=["potential", "lccdr"])
    return pd.DataFrame(records).set_index("node")


def main():
    args = parse_check_args()
    p = load_check_params(args)
    RESULTS, WC = p["RESULTS"], p["WC"]

    with open("config/plotting.default.yaml") as f:
        tech_colors = yaml.safe_load(f)["plotting"]["tech_colors"]

    opt_path = RESULTS / "networks" / f"{WC}.nc"
    print(f"Loading {opt_path}")
    n = pypsa.Network(str(opt_path))

    sw = n.snapshot_weightings["stores"]
    mp = n.buses_t.marginal_price if "marginal_price" in n.buses_t else None

    co2_price = None
    if "CO2Limit" in n.global_constraints.index:
        mu = n.global_constraints.at["CO2Limit", "mu"]
        if pd.notna(mu):
            co2_price = -mu  # mu is negative (cost-reduction sign); price is positive EUR/tCO2
            print(f"CO2 shadow price: {co2_price:.2f} EUR/tCO2\n")

    ALL_SERIES = list(CDR_TECHS) + [("Geological CO2 storage", "co2 sequestered")]

    frames = []
    any_hypothetical = False
    for label, carrier in CDR_TECHS:
        df = compute_cdr_per_node(n, carrier)
        if df.empty:
            print(f"  {label}: no components found, skipping")
            continue

        df = df.rename(columns={"e_nom_max": "potential", "lccdr_gross": "lccdr"})
        undeployed_idx = df.index[df["lccdr"].isna()]
        df["hypothetical"] = False

        if len(undeployed_idx):
            hyp = hypothetical_lccdr(n, carrier, sw, mp, undeployed_idx)
            df.loc[hyp.index, "lccdr"] = hyp.values
            df.loc[hyp.index, "hypothetical"] = True
            n_est = len(hyp)
            n_dropped = len(undeployed_idx) - n_est
            print(f"  {label}: {n_est} undeployed node(s) given a hypothetical mean-price estimate"
                  + (f", {n_dropped} dropped (no valid link/potential)" if n_dropped else ""))
            if n_est:
                any_hypothetical = True

        df = df.dropna(subset=["lccdr"])
        if df.empty:
            print(f"  {label}: no usable nodes, skipping")
            continue

        df["tech"] = label
        df["carrier"] = carrier
        n_deployed = int((~df["hypothetical"]).sum())
        print(f"  {label}: {n_deployed} deployed + {int(df['hypothetical'].sum())} hypothetical nodes, "
              f"potential {df['potential'].sum() / 1e6:.2f} MtCO2, "
              f"LCCDR {df['lccdr'].min():.0f}-{df['lccdr'].max():.0f} EUR/tCO2")
        frames.append(df)

    if co2_price is not None:
        seq_label, seq_carrier = "Geological CO2 storage", "co2 sequestered"
        seq_df = sequestration_lccdr(n, co2_price, sw)
        if not seq_df.empty:
            seq_df["tech"] = seq_label
            seq_df["carrier"] = seq_carrier
            seq_df["hypothetical"] = False
            print(f"  {seq_label}: {len(seq_df)} nodes with potential, "
                  f"potential {seq_df['potential'].sum() / 1e6:.2f} MtCO2, "
                  f"LCCDR {seq_df['lccdr'].min():.0f}-{seq_df['lccdr'].max():.0f} EUR/tCO2")
            frames.append(seq_df)
        else:
            print(f"  {seq_label}: no usable nodes, skipping")

    if not frames:
        sys.exit("No usable CDR nodes found in this network.")

    supply = pd.concat(frames).sort_values("lccdr").reset_index(drop=True)
    supply["left_edge"] = supply["potential"].cumsum() - supply["potential"]

    fig, ax = plt.subplots(figsize=(13, 6))
    techs_present = []
    for label, carrier in ALL_SERIES:
        mask = supply["tech"] == label
        if not mask.any():
            continue
        techs_present.append((label, carrier))
        for hypothetical, hatch in [(False, None), (True, "///")]:
            sub = supply[mask & (supply["hypothetical"] == hypothetical)]
            if sub.empty:
                continue
            ax.bar(
                sub["left_edge"] / 1e6,
                sub["lccdr"],
                width=sub["potential"] / 1e6,
                align="edge",
                color=tech_colors.get(carrier, "grey"),
                edgecolor="white",
                linewidth=0.2,
                hatch=hatch,
            )

    if co2_price is not None:
        ax.axhline(co2_price, color="black", linestyle="--", linewidth=1.2, zorder=5)
        ax.text(
            supply["potential"].sum() / 1e6 * 0.99, co2_price, f" CO2 price: {co2_price:.0f} EUR/tCO2",
            ha="right", va="bottom", fontsize=9,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.5),
        )

    ax.set_xlabel("Cumulative CO2 removal potential [MtCO2]")
    ax.set_ylabel("Levelized Cost of CDR [EUR/tCO2]  (excl. CO2 credit)")
    ax.set_title(f"CDR merit order — {WC}")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.spines[["top", "right"]].set_visible(False)

    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=tech_colors.get(carrier, "grey"), edgecolor="white", label=label)
        for label, carrier in techs_present
    ]
    if any_hypothetical:
        handles.append(Patch(facecolor="white", edgecolor="black", hatch="///",
                              label="Undeployed — hypothetical, mean local price"))
    ax.legend(handles=handles, frameon=False, loc="upper left")

    notes = []
    if any_hypothetical:
        notes.append(
            "Hatched bars: node had no observed dispatch, so cost is estimated assuming uniform "
            "dispatch all year at the node's own mean local price (no price-timing optimization) — "
            "likely an overestimate for technologies with a flexible, unrestricted dispatch window "
            "(e.g. biochar, rock weathering)."
        )
    if (supply["tech"] == "Geological CO2 storage").any():
        notes.append(
            "Levelized cost for Geological CO2 storage includes the end-to-end bus-price gap (system CO2 price − Co2 stored price at that node's "
            "\"co2 sequestered\" bus), bundling whatever capture technology + CO2 pipeline transport"
            "shown for cost comparison only, its potential doesn't compete 1:1 with other CDRs"
        )
    if notes:
        fig.text(
            0.01, -0.02, "\n".join(notes),
            fontsize=7.5, color="dimgrey", ha="left", va="top",
        )

    out_dir = RESULTS / "graphics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"CDR_merit_order_{WC}.pdf"
    fig.savefig(out_path, bbox_inches="tight")
    print(f"\nSaved: {out_path.resolve()}")


if __name__ == "__main__":
    main()
