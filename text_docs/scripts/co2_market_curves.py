"""
Supply-demand curves for the two CO2 markets of a solved PyPSA-Eur network.

    python text_docs/scripts/co2_market_curves.py <network.nc> <out_dir> <label>

Every deployed link with a port on the market bus gets a break-even price,
computed with the LCOP rule on everything EXCEPT the market's own port:

    profit_excl = sum over other ports of  (-p_i(t)) * price_i(t) * w(t)   (inputs < 0, outputs > 0)
                  - capital_cost * p_nom_opt   (extendable links only; brownfield capex is sunk)
                  - marginal_cost * p0 * w
                  - capex of extendable "own terminal" stores (see below)
    q           = tonnes delivered INTO the market bus over the year (negative = withdrawn)
    p*          = -profit_excl / q          (in the market bus's own price units)

Links delivering into the bus are the supply side (sorted by ascending p*),
links withdrawing from it the demand side (sorted by descending p*). By LP
duality, every link whose capacity is free to expand breaks even exactly at
its own flow-weighted market price, so the curves cross at the market price;
links held at a bound (potentials, sunk capacity) show up as rents.

Market A, atmosphere (bus carrier "co2", one bus, price = CO2Limit dual):
    the atmosphere port is left out; captured CO2 is priced at the hourly
    nodal "co2 stored" price. Shown in permit-price terms (pi = -price >= 0):
    emitters (demand) with their willingness to pay per tonne emitted,
    removers (supply) with their cost per tonne removed. A net-negative
    CO2Limit is a fixed block of required net removal on the demand side, a
    positive one a free block of supply at 0.
Market B, captured CO2 (bus carrier "co2 stored", 50 nodal buses):
    the "co2 stored" port is left out; the atmosphere port is priced at the
    CO2 price. Capture (BECCS, DAC, industry and process CC) is supply,
    sequestration and utilisation (Sabatier, methanolisation, FT...) demand.
    CO2 pipelines (market bus on both ends) are transfers and are left out;
    "co2 stored" stores only shift CO2 in time and are reported, not plotted.

"Own terminal" buses (the per-node CDR store buses and "co2 sequestered")
belong to the technology: their price is not counted, the capex of their
extendable stores is. So a potential-limited CDR or the capped geological
storage shows its rent instead of absorbing it into a bus price.

Outputs in <out_dir>: co2_market_{A_atmosphere,B_captured}_<label>.png and
.csv (one row per technology and node), plus a printed validation summary.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
import yaml

from scripts._helpers import rename_techs

with open(REPO / "config" / "plotting.default.yaml") as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]


def official_colour(carrier):
    """PyPSA-Eur tech colour: the carrier's own entry, else that of its plot_summary group
    (rename_techs, as in the costs plot), else grey. Same technology, same colour, in every figure."""
    return TECH_COLORS.get(carrier) or TECH_COLORS.get(rename_techs(carrier)) or "#9e9e9e"

# Two colour families so the sides of a market never share a colour:
# cool for supply (removers / capture, bars), warm for demand (emitters / storage and use, step line).
COOL = ["#1f5f99", "#2ca02c", "#17becf", "#6a51a3", "#1b9e77", "#66a61e", "#4575b4", "#74add1",
        "#006d2c", "#41ab5d", "#08519c", "#6baed6", "#807dba", "#a1d99b", "#35978f", "#9ecae1"]
WARM = ["#d62728", "#ff7f0e", "#8c564b", "#e377c2", "#b8860b", "#e6550d", "#a50f15", "#fb6a4a",
        "#fdae6b", "#843c39", "#d6616b", "#f16913", "#cb181d", "#b15928", "#e7969c", "#fd8d3c"]
OTHER_COOL, OTHER_WARM = "#b7c9d9", "#e3c2b5"
N_SHOWN = 14

OWN_TERMINAL = {"co2 afforestation", "co2 perennials", "co2 biochar", "co2 rock weathering", "co2 sequestered"}
MIN_TONNES = 1e3  # a technology-node pair counts as deployed above 1 kt/yr
BIOGENIC_CYCLE = {"electrobiofuels", "biogas to gas", "biogas to gas CC", "biomass to liquid", "biomass-to-methanol"}


def break_even_table(n, market_carrier):
    w = n.snapshot_weightings.generators
    mp = n.buses_t.marginal_price
    market = set(n.buses.index[n.buses.carrier == market_carrier])
    L = n.links
    ports = [i for i in range(5) if f"bus{i}" in L.columns]
    on_market = pd.Series(False, index=L.index)
    n_market_ports = pd.Series(0, index=L.index)
    for i in ports:
        hit = L[f"bus{i}"].isin(market)
        on_market |= hit
        n_market_ports += hit.astype(int)
    cand = L.index[on_market & (n_market_ports == 1)]  # pipelines touch the market twice

    ext_store_capex = {}
    st = n.stores[n.stores.bus.isin(n.buses.index[n.buses.carrier.isin(OWN_TERMINAL)])]
    for name, s in st.iterrows():
        if s.get("e_nom_extendable", False):
            ext_store_capex[s["bus"]] = ext_store_capex.get(s["bus"], 0.0) + s["capital_cost"] * s["e_nom_opt"]

    def link_node(link):
        """Node of a link: the location of its first port at a real node. bus0 alone is not enough:
        CDR links draw from the single 'co2 atmosphere' bus and oil products from 'EU oil', but
        their store or demand bus sits at a node."""
        for i in ports:
            loc = n.buses.location.get(link[f"bus{i}"], "") if isinstance(link[f"bus{i}"], str) else ""
            if loc and loc != "EU":
                return loc
        return n.buses.location.get(link["bus0"], "") or link["bus0"]

    rows = []
    for lk in cand:
        link = L.loc[lk]
        p0 = n.links_t.p0[lk] if lk in n.links_t.p0.columns else None
        if p0 is None or not np.any(p0.values):
            continue
        q = value = lam_q = 0.0
        own_capex = 0.0
        for i in ports:
            bus = link[f"bus{i}"]
            if not isinstance(bus, str) or not bus or bus not in n.buses.index:
                continue
            P = n.links_t[f"p{i}"]
            if lk not in P.columns:
                continue
            flow_in = -P[lk] * w  # into bus i, weighted
            car = n.buses.at[bus, "carrier"]
            if bus in market:
                q += flow_in.sum()
                lam_q += (flow_in * mp[bus]).sum()
            elif car in OWN_TERMINAL:
                own_capex += ext_store_capex.pop(bus, 0.0)
            elif bus in mp.columns:
                value += (flow_in * mp[bus]).sum()
        capex = link["capital_cost"] * link["p_nom_opt"] if link["p_nom_extendable"] else 0.0
        mc = n.links_t.marginal_cost[lk] if lk in n.links_t.marginal_cost.columns else link["marginal_cost"]
        om = (mc * p0 * w).sum()
        rows.append(dict(
            link=lk, carrier=link["carrier"], node=link_node(link),
            # brownfield industry-heat links re-added as "-derated" (add_brownfield.py) are extendable
            # only downwards: capex 0 and p_nom_max = existing capacity, so they are sunk capacity too
            extendable=bool(link["p_nom_extendable"])
            and not (link["capital_cost"] == 0 and link["p_nom_opt"] >= link["p_nom_max"] - 1e-3),
            q=q, lam_q=lam_q,
            profit_excl=value - capex - own_capex - om,
        ))
    d = pd.DataFrame(rows)
    if d.empty:  # nothing flows through this market (e.g. no capture in early horizons)
        return pd.DataFrame(columns=["carrier", "node", "q", "lam_q", "profit_excl", "has_sunk", "p_star", "lam_bar"])
    g = d.groupby(["carrier", "node"]).agg(q=("q", "sum"), lam_q=("lam_q", "sum"),
                                           profit_excl=("profit_excl", "sum"),
                                           has_sunk=("extendable", lambda s: (~s).any()))
    g = g[g.q.abs() >= MIN_TONNES].copy()
    g["p_star"] = -g.profit_excl / g.q          # break-even price at the market bus
    g["lam_bar"] = g.lam_q / g.q                 # own flow-weighted market price
    return g.reset_index()


def step_bars(ax, df, x0, ylab_col, color_map, alpha, hatch=None, edge="white", base=0.0):
    """Supply bars from `base` up (or down) to each break-even price."""
    x = x0
    for _, r in df.iterrows():
        w = abs(r.q) / 1e6
        ax.bar(x, r[ylab_col] - base, bottom=base, width=w, align="edge", color=color_map.get(r.carrier, "#9e9e9e"),
               alpha=alpha, edgecolor=edge, linewidth=0.2, hatch=hatch)
        x += w
    return x


def step_line(ax, df, x0, ylab_col, color_map, ylim):
    """Demand curve as a thick step line, each segment coloured by technology."""
    x = x0
    prev = None
    for _, r in df.iterrows():
        w = abs(r.q) / 1e6
        y = float(np.clip(r[ylab_col], *ylim))
        if prev is not None:
            ax.plot([x, x], [prev, y], color="black", lw=1.5, zorder=4)
        ax.plot([x, x + w], [y, y], color=color_map.get(r.carrier, "#9e9e9e"), lw=6, zorder=5,
                solid_capstyle="butt")
        x += w
        prev = y
    return x


def plot_market(df, *, title, ylabel, price_lines, out_path, fixed_demand=0.0, fixed_supply=0.0,
                note="", sign=1.0, supply_label="Supply (bars)", demand_label="Demand (step line)"):
    d = df.copy()
    d["y"] = sign * d["p_star"]
    supply = d[d.q > 0].sort_values("y")
    demand = d[d.q < 0].sort_values("y", ascending=False)
    if sign < 0:  # atmosphere: removers withdraw (q < 0) but supply permits; emitters inject (q > 0) and demand them
        supply, demand = d[d.q < 0].sort_values("y"), d[d.q > 0].sort_values("y", ascending=False)

    def side_colours(side, palette, other):
        # official PyPSA-Eur colours for every technology (palette/other kept for the call signature)
        vol = side.groupby("carrier").q.apply(lambda s: s.abs().sum()).sort_values(ascending=False)
        shown = list(vol.index)
        cmap = {c: official_colour(c) for c in shown}
        return vol, shown, cmap

    vol_s, shown_s, cmap_s = side_colours(supply, COOL, OTHER_COOL)
    vol_d, shown_d, cmap_d = side_colours(demand, WARM, OTHER_WARM)

    eq = price_lines[0][1]
    finite = d["y"].replace([np.inf, -np.inf], np.nan).dropna()
    lo, hi = np.nanpercentile(finite, [3, 97]) if len(finite) else (eq - 100, eq + 100)
    span = max(abs(eq), 50.0)
    ylim = (min(lo, eq - 1.2 * span, 0), max(hi, eq + 1.2 * span, 0))

    fig, (ax, axl) = plt.subplots(1, 2, figsize=(17, 7.5), gridspec_kw={"width_ratios": [4.2, 1]})
    x = 0.0
    if fixed_supply > 0:
        ax.bar(0, 0.02 * (ylim[1] - ylim[0]), width=fixed_supply / 1e6, align="edge", color="#cfcfcf", edgecolor="#555")
        ax.text(fixed_supply / 2e6, 0.03 * (ylim[1] - ylim[0]), "CO2Limit\n(free)", ha="center", fontsize=8)
        x = fixed_supply / 1e6
    # negative-price market (e.g. captured CO2 as a waste): grow bars from the axis bottom, not from 0
    x_s = step_bars(ax, supply, x, "y", cmap_s, alpha=0.9, base=0.0 if eq >= 0 else ylim[0])
    x = 0.0
    if fixed_demand > 0:
        # inelastic block: the required net removal of a net-negative CO2Limit (unbounded willingness to pay)
        ax.plot([0, fixed_demand / 1e6], [ylim[1], ylim[1]], color="black", lw=6, zorder=5, solid_capstyle="butt")
        ax.annotate("required net removal\n(net-negative CO2Limit, inelastic)", xy=(fixed_demand / 2e6, ylim[1]),
                    xytext=(fixed_demand / 2e6, ylim[1] - 0.12 * (ylim[1] - ylim[0])), ha="center", fontsize=8,
                    arrowprops=dict(arrowstyle="->", lw=0.8), bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
        x = fixed_demand / 1e6
    x_d = step_line(ax, demand, x, "y", cmap_d, ylim)

    for label, val, ls in price_lines:
        ax.axhline(val, color="black", ls=ls, lw=1.3, zorder=6)
        ax.text(max(x_s, x_d) * 0.995, val, f" {label}: {val:.0f} €/t", ha="right", va="bottom", fontsize=9,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.2), zorder=7)
    n_clip = int(((d["y"] > ylim[1]) | (d["y"] < ylim[0])).sum())
    ax.set_ylim(*ylim)
    ax.set_xlim(0, max(x_s, x_d) * 1.02)
    ax.set_xlabel("Cumulative CO2 [MtCO2 per year]")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    foot = [f"Bars: supply ({abs(supply.q).sum() / 1e6:.1f} Mt, ascending).  "
            f"Step line: demand ({abs(demand.q).sum() / 1e6 + fixed_demand / 1e6:.1f} Mt, descending), segment colour = technology.  "
            f"Width = annual tonnes of one technology at one node."]
    if n_clip:
        foot.append(f"{n_clip} bars extend beyond the y-range (clipped).")
    if note:
        foot.append(note)
    fig.text(0.01, -0.02, "\n".join(foot), fontsize=8, color="dimgrey", ha="left", va="top")

    axl.axis("off")
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    def legend_block(vol, shown, cmap, other, as_line):
        items = []
        for c in shown:
            lab = f"{c} ({vol[c] / 1e6:.0f} Mt)"
            items.append(Patch(facecolor=cmap[c], label=lab))
        return items

    leg_s = axl.legend(handles=legend_block(vol_s, shown_s, cmap_s, OTHER_COOL, False), loc="upper left",
                       frameon=False, fontsize=7, title=supply_label, title_fontproperties={"weight": "bold", "size": 9},
                       alignment="left")
    axl.add_artist(leg_s)
    axl.legend(handles=legend_block(vol_d, shown_d, cmap_d, OTHER_WARM, True), loc="lower left",
               frameon=False, fontsize=7, title=demand_label, title_fontproperties={"weight": "bold", "size": 9},
               alignment="left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def validation(df, market_price_label, sign=1.0):
    d = df.copy()
    d["gap"] = sign * (d.p_star - d.lam_bar)
    tot = d.q.abs().sum()
    within = d.loc[d.gap.abs() <= 1.0, "q"].abs().sum()
    print(f"  {market_price_label}: {len(d)} technology-node pairs, {tot / 1e6:.1f} Mt; "
          f"break-even within 1 €/t of own market price for {within / tot:.0%} of the volume")
    big = d.assign(abs_gap=d.gap.abs()).sort_values("abs_gap", ascending=False)
    big = big[big.abs_gap > 1.0]
    if len(big):
        top = big.groupby("carrier").agg(Mt=("q", lambda s: s.abs().sum() / 1e6), max_gap=("abs_gap", "max"),
                                         sunk=("has_sunk", "any")).sort_values("Mt", ascending=False).head(12)
        print("  largest deviations (rents: bounds or sunk capex), by carrier:")
        print(top.round(1).to_string())


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    path, out_dir, label = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    out_dir.mkdir(parents=True, exist_ok=True)
    n = pypsa.Network(str(path))
    gc = n.global_constraints
    co2_price = -float(gc.at["CO2Limit", "mu"])
    cap = float(gc.at["CO2Limit", "constant"])

    # --- A: atmosphere
    A = break_even_table(n, "co2")
    A.to_csv(out_dir / f"co2_market_A_atmosphere_{label}.csv", index=False)
    emit, remove = A.loc[A.q > 0, "q"].sum(), -A.loc[A.q < 0, "q"].sum()
    print(f"\n[A] atmosphere: CO2 price {co2_price:.1f} €/t, CO2Limit {cap / 1e6:.1f} Mt; "
          f"emitted {emit / 1e6:.1f} Mt, removed {remove / 1e6:.1f} Mt, net {(emit - remove) / 1e6:.1f} Mt")
    if A.empty:
        print("  [A] no deployed technology on the atmosphere bus: figure skipped")
    else:
      validation(A, "atmosphere", sign=-1.0)
      plot_market(
        A, sign=-1.0,
        title=f"Atmosphere: emitters (demand) vs removers (supply) — {label}",
        ylabel="Break-even CO2 price [€/tCO2]\n(emitters: willingness to pay per t emitted; removers: cost per t removed)",
        price_lines=[("CO2 price (CO2Limit dual)", co2_price, "--")],
        fixed_demand=max(-cap, 0.0), fixed_supply=max(cap, 0.0),
        supply_label="REMOVERS — supply (bars)", demand_label="EMITTERS — demand (step line)",
        note="Captured CO2 is priced at the hourly nodal 'co2 stored' price; fuels at their bus prices, which include any "
             "fossil-limit shadow price. Electrobiofuels / biogas upgrading count as removals because biogenic carbon is "
             "credited at conversion; it is emitted again when the fuel is burned (demand side).",
        out_path=out_dir / f"co2_market_A_atmosphere_{label}.png",
    )

    # --- B: captured CO2
    B = break_even_table(n, "co2 stored")
    B.to_csv(out_dir / f"co2_market_B_captured_{label}.csv", index=False)
    w = n.snapshot_weightings.generators
    stored = n.buses.index[n.buses.carrier == "co2 stored"]
    sup = B.loc[B.q > 0]
    lam_eq = sup.lam_q.sum() / sup.q.sum() if len(sup) else np.nan
    cs = n.stores[n.stores.bus.isin(stored)]
    shift = (n.stores_t.e[cs.index].iloc[-1] - cs.e_initial).sum() / 1e6 if len(cs) else 0.0
    print(f"\n[B] captured CO2: supply {sup.q.sum() / 1e6:.1f} Mt, demand {-B.loc[B.q < 0, 'q'].sum() / 1e6:.1f} Mt, "
          f"'co2 stored' store net change {shift:.2f} Mt; flow-weighted 'co2 stored' price {lam_eq:.1f} €/t")
    if B.empty:
        print("  [B] no captured CO2 in this horizon: figure skipped")
        return
    validation(B, "co2 stored")
    if not np.isfinite(lam_eq):
        lam_eq = 0.0
    plot_market(
        B,
        title=f"Captured CO2 ('co2 stored'): capture (supply) vs storage and use (demand) — {label}",
        supply_label="CAPTURE — supply (bars)", demand_label="STORAGE & USE — demand (step line)",
        ylabel="Break-even 'co2 stored' price [€/tCO2]\n(supply: price needed per t delivered; demand: price payable per t taken)",
        price_lines=[("flow-weighted 'co2 stored' price", lam_eq, "--"), ("CO2 price (atmosphere)", -co2_price, ":")],
        note="Atmosphere port priced at the CO2 price (a credit for BECCS/DAC, a charge for residual emissions of "
             "capture plants). Negative prices: captured CO2 is a waste that needs disposal, typically when "
             "geological storage is capped.",
        out_path=out_dir / f"co2_market_B_captured_{label}.png",
    )

    # --- fossil-limit check: does the gas bus price carry the security-limit shadow price?
    if "energy_limit_security_gas" in gc.index:
        mu = -float(gc.at["energy_limit_security_gas", "mu"])
        gas_bus = [b for b in n.buses.index[n.buses.carrier == "gas"] if b in n.buses_t.marginal_price.columns]
        gens = n.generators[n.generators.carrier == "gas"]
        if gas_bus and len(gens):
            gp = (n.buses_t.marginal_price[gas_bus].mul(w, axis=0).sum() / w.sum()).mean()
            mc = gens.marginal_cost.mean()
            inten = n.carriers.at["gas", "security_co2_eq_gas"] if "security_co2_eq_gas" in n.carriers else 0.198
            print(f"\n[check] gas bus price {gp:.1f} €/MWh vs generator marginal cost {mc:.1f} + fossil-limit "
                  f"shadow {mu:.1f} €/t x {inten:.3f} t/MWh = {mc + mu * inten:.1f} €/MWh")


if __name__ == "__main__":
    main()
