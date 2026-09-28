"""
System-level impact metrics of the weekend batch: what the fossil limits
(aggregate or per carrier) and the LULUCF correction change.

Run from the pypsa-eur root.

  1. extract (needs the solved networks; one call per run, e.g. as a job array):

        python text_docs/scripts/batch_impact_metrics.py extract <results_root> <out_dir> <run>

     writes <out_dir>/impact_<run>.csv, one row per horizon and metric:
       cost        total system cost and cost by technology group (capex + opex, bn EUR/yr)
       shadow      shadow prices of all global constraints (EUR/tCO2 for CO2Limit, fossil_fuel_limit,
                   energy_limit_security_* and co2_sequestration_limit)
       price       demand-weighted average price of AC, H2, gas and co2 stored buses (EUR/MWh, EUR/t)
       co2         atmospheric emissions and removals by technology, CO2 captured, sequestered (Mt/yr)
       grid        H2 / CO2 / gas pipelines and AC / DC transmission: capacity x length and flow
       capacity    DAC (tCO2/h at co2 stored), electrolysis, methanation, Fischer-Tropsch, methanolisation:
                   output capacity (MW) and annual output (TWh; Mt for DAC)

  2. plot (needs the extract files of weekend_run1..9):

        python text_docs/scripts/batch_impact_metrics.py plot <extract_dir> <out_dir>

     writes to <out_dir>:
       impact_overview.png        one panel per metric, all 9 runs over time
       impact_lever_effects.png   effect of each lever (limit type, target, LULUCF),
                                  mean over its 4 matched run pairs, range shaded
     and to <extract_dir>: impact_table.csv (the plotted metrics per run and year)
     and impact_lever_effects.csv.

Average prices are weighted by the energy withdrawn from each bus in each
snapshot (loads, link inputs, store charging); transport links (pipelines, DC
links) are left out of the weights because their withdrawal is only transit.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

TRANSPORT = ["pipeline", "DC", "import", "export"]


# ---------------------------------------------------------------- extract helpers
def link_ports(n):
    return [i for i in range(5) if f"bus{i}" in n.links.columns and f"p{i}" in n.links_t]


def withdrawals(n, buses):
    """Energy withdrawn from each of `buses` per snapshot (MW), excluding transport links."""
    W = pd.DataFrame(0.0, index=n.snapshots, columns=buses)
    L = n.loads[n.loads.bus.isin(buses)]
    if len(L):
        p = n.loads_t.p.reindex(columns=L.index).fillna(0.0).clip(lower=0)
        W = W.add(p.T.groupby(L.bus).sum().T, fill_value=0.0)
    links = n.links[~n.links.carrier.str.contains("|".join(TRANSPORT), case=False)]
    for i in link_ports(n):
        sel = links[links[f"bus{i}"].isin(buses)]
        if sel.empty:
            continue
        p = n.links_t[f"p{i}"].reindex(columns=sel.index).fillna(0.0).clip(lower=0)
        W = W.add(p.T.groupby(sel[f"bus{i}"]).sum().T, fill_value=0.0)
    S = n.stores[n.stores.bus.isin(buses)]
    if len(S):
        p = (-n.stores_t.p.reindex(columns=S.index).fillna(0.0)).clip(lower=0)
        W = W.add(p.T.groupby(S.bus).sum().T, fill_value=0.0)
    return W[buses]


def weighted_price(n, bus_carrier):
    buses = [b for b in n.buses.index[n.buses.carrier == bus_carrier] if b in n.buses_t.marginal_price.columns]
    if not buses:
        return np.nan, np.nan, 0.0
    w = n.snapshot_weightings.generators
    mp = n.buses_t.marginal_price[buses]
    W = withdrawals(n, buses).mul(w, axis=0)
    total = W.values.sum()
    demand_weighted = (mp * W).values.sum() / total if total > 0 else np.nan
    time_mean = float(mp.mul(w, axis=0).sum().div(w.sum()).mean())
    return demand_weighted, time_mean, total


def pipe_metrics(n, pattern, component="links"):
    df = getattr(n, component)
    if component == "links":
        df = df[df.carrier.str.contains(pattern, case=False, regex=True)]
        cap = df.p_nom_opt
        flow = n.links_t.p0.reindex(columns=df.index).fillna(0.0).abs()
    else:
        cap = df.s_nom_opt
        flow = n.lines_t.p0.reindex(columns=df.index).fillna(0.0).abs()
    w = n.snapshot_weightings.generators
    length = df.length.fillna(0.0)
    return {
        "capacity": cap.sum(),                      # MW (or t/h for CO2)
        "capacity_length": (cap * length).sum(),    # MW km
        "flow_length": (flow.mul(w, axis=0).sum() * length).sum(),  # MWh km
        "flow": flow.mul(w, axis=0).sum().sum(),    # MWh
    }


def link_output(n, pattern, port=1):
    """Capacity at the output port (p_nom_opt x efficiency of that port) and annual output there."""
    sel = n.links.index[n.links.carrier.str.contains(pattern, case=False, regex=True)]
    w = n.snapshot_weightings.generators
    eff = n.links.loc[sel, "efficiency" if port == 1 else f"efficiency{port}"]
    cap = (n.links.loc[sel, "p_nom_opt"] * eff).sum()
    p = n.links_t[f"p{port}"].reindex(columns=sel).fillna(0.0)
    return cap, -(p.mul(w, axis=0).sum().sum())


def extract(results_root, out_dir, run):
    import pypsa

    from batch_cdr_analysis import sequestration_annual
    from batch_comparison_figures import cost_group
    from co2_market_curves import break_even_table
    from scripts._helpers import rename_techs

    rows = []

    def add(year, kind, name, value):
        rows.append(dict(run=run, year=year, kind=kind, name=name, value=float(value)))

    for path in sorted((results_root / run / "networks").glob("*.nc")):
        m = re.search(r"_(\d{4})\.nc$", path.name)
        if not m:
            continue
        year = int(m.group(1))
        print(f"{run} {year}", flush=True)
        n = pypsa.Network(str(path))
        w = n.snapshot_weightings.generators

        # costs
        cost = (n.statistics.capex().groupby("carrier").sum()
                .add(n.statistics.opex().groupby("carrier").sum(), fill_value=0.0)) / 1e9
        add(year, "cost", "total", cost.sum())
        for grp, v in cost.groupby(cost.index.map(lambda c: cost_group(rename_techs(c)))).sum().items():
            add(year, "cost", grp, v)
        add(year, "cost", "objective", n.objective / 1e9)

        # shadow prices of global constraints
        gc = n.global_constraints
        for name in gc.index:
            add(year, "shadow", name, -gc.at[name, "mu"])

        # demand-weighted average prices
        for carrier in ["AC", "H2", "gas", "co2 stored", "solid biomass", "oil", "methanol"]:
            dw, tm, tot = weighted_price(n, carrier)
            add(year, "price", carrier, dw)
            add(year, "price_time_mean", carrier, tm)
            add(year, "demand", carrier, tot / 1e6)  # TWh (Mt for co2 stored)

        # CO2: atmosphere by technology (+ emit, - remove), captured CO2 by technology
        t = break_even_table(n, "co2")
        for carrier, q in t.groupby("carrier").q.sum().items():
            add(year, "co2 atmosphere", carrier, q / 1e6)
        t = break_even_table(n, "co2 stored")
        for carrier, q in t.groupby("carrier").q.sum().items():
            add(year, "co2 stored", carrier, q / 1e6)
        co2_price = -float(gc.at["CO2Limit", "mu"]) if "CO2Limit" in gc.index else 0.0
        seq = sequestration_annual(n, co2_price, w)
        add(year, "co2", "sequestered", seq["potential"].sum() / 1e6 if len(seq) else 0.0)

        # grids
        for name, pattern in [("H2 pipeline", r"H2 pipeline"), ("CO2 pipeline", r"CO2 pipeline"),
                              ("gas pipeline", r"gas pipeline"), ("DC", r"^DC$")]:
            for k, v in pipe_metrics(n, pattern).items():
                add(year, f"grid {k}", name, v)
        for k, v in pipe_metrics(n, None, component="lines").items():
            add(year, f"grid {k}", "AC", v)

        # conversion capacities (p_nom_opt at bus0) and output at bus1
        for name, pattern, port in [("DAC", r"DAC$", 3), ("H2 Electrolysis", r"H2 Electrolysis", 1),
                                    ("Sabatier", r"Sabatier|methanation", 1), ("Fischer-Tropsch", r"Fischer-Tropsch", 1),
                                    ("methanolisation", r"methanolisation", 1), ("SMR", r"^SMR", 1),
                                    ("SMR CC", r"^SMR CC", 1)]:
            cap, out = link_output(n, pattern, port)
            add(year, "capacity", name, cap)
            add(year, "output", name, out / 1e6)

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / f"impact_{run}.csv", index=False)
    print(f"wrote {out_dir / f'impact_{run}.csv'}")


# ---------------------------------------------------------------- plot
RUNS = [f"weekend_run{i}" for i in range(1, 10)]
# scenario design: limit type, self-sufficiency target, LULUCF correction
DESIGN = {
    1: ("none", None, "off"),
    2: ("aggregate", 100, "BAU"), 3: ("aggregate", 60, "BAU"),
    4: ("per-carrier", 100, "BAU"), 5: ("per-carrier", 60, "BAU"),
    6: ("aggregate", 100, "optimistic-weak"), 7: ("aggregate", 60, "optimistic-weak"),
    8: ("per-carrier", 100, "optimistic-weak"), 9: ("per-carrier", 60, "optimistic-weak"),
}
LIMIT_COLOUR = {"none": "#6b6b6b", "aggregate": "#2a78d6", "per-carrier": "#eb6834"}
# matched pairs (from -> to) that change exactly one lever
LEVERS = {
    "aggregate → per-carrier limit": [(2, 4), (3, 5), (6, 8), (7, 9)],
    "100 % → 60 % self-sufficiency": [(2, 3), (4, 5), (6, 7), (8, 9)],
    "BAU → optimistic-weak LULUCF": [(2, 6), (3, 7), (4, 8), (5, 9)],
}
LEVER_COLOUR = dict(zip(LEVERS, ["#eb6834", "#1baf7a", "#2a78d6"]))

LAND_CDR = ["afforestation", "perennial", "weathering", "biochar"]


def metrics(ext):
    """Wide table: (run, year) x metric, in the units of the figures."""
    def pick(kind, name=None, match=None):
        d = ext[ext.kind == kind]
        if name is not None:
            d = d[d.name == name]
        if match is not None:
            d = d[d.name.str.contains(match, case=False, regex=True)]
        return d.groupby(["run", "year"]).value.sum()

    atm = ext[ext.kind == "co2 atmosphere"]
    land = atm[atm.name.str.contains("|".join(LAND_CDR), case=False)]
    shadow = ext[ext.kind == "shadow"]
    fossil = shadow[shadow.name.str.contains("fossil|energy_limit_security", case=False)]
    m = pd.DataFrame({
        "total system cost [bn€/yr]": pick("cost", "total"),
        "CO2 price [€/t]": pick("shadow", "CO2Limit"),
        "captured-CO2 price [€/t]": pick("price", "co2 stored"),
        "highest fossil-limit shadow price [€/tCO2]": fossil.groupby(["run", "year"]).value.max(),
        "land-based CDR [Mt/yr]": -land.groupby(["run", "year"]).value.sum(),
        "DAC capture [Mt/yr]": pick("co2 stored", "DAC"),
        "geological storage [Mt/yr]": pick("co2", "sequestered"),
        "gross CO2 emitted, all emitters [Mt/yr]": atm[(atm.value > 0)].groupby(["run", "year"]).value.sum(),
        "H2 pipelines [TW·km]": pick("grid capacity_length", "H2 pipeline") / 1e6,
        "CO2 pipelines [Mt/yr·1000 km]": pick("grid capacity_length", "CO2 pipeline") * 8760 / 1e9,
        "AC + DC transmission [TW·km]": (pick("grid capacity_length", "AC").add(pick("grid capacity_length", "DC"), fill_value=0)) / 1e6,
        "electrolysis [GW H2]": pick("capacity", "H2 Electrolysis") / 1e3,
        "electricity price [€/MWh]": pick("price", "AC"),
        "H2 price [€/MWh]": pick("price", "H2"),
        "natural gas price [€/MWh]": pick("price", "gas"),
        "solid biomass price [€/MWh]": pick("price", "solid biomass"),
    })
    # quantities absent in a horizon (no CDR, no DAC, no pipelines yet) are zero, not missing
    quantities = [c for c in m.columns if "price" not in c]
    m[quantities] = m[quantities].fillna(0.0)
    m["highest fossil-limit shadow price [€/tCO2]"] = m["highest fossil-limit shadow price [€/tCO2]"].fillna(0.0)
    # run1 has no fossil limit: leave its shadow price out of the plots
    m.loc[m.index.get_level_values("run") == "weekend_run1", "highest fossil-limit shadow price [€/tCO2]"] = np.nan
    return m


def run_no(run):
    return int(run.replace("weekend_run", ""))


def fig_overview(m, out):
    cols = list(m.columns)
    fig, axes = plt.subplots(4, 4, figsize=(18, 15), layout="constrained")
    for ax, col in zip(axes.flat, cols):
        for run in RUNS:
            if run not in m.index.levels[0]:
                continue
            limit, target, lulucf = DESIGN[run_no(run)]
            y = m.loc[run, col]
            face = LIMIT_COLOUR[limit] if lulucf != "optimistic-weak" else "white"
            ax.plot(y.index, y.values, color=LIMIT_COLOUR[limit], ls="--" if target == 60 else "-",
                    lw=2.2 if limit != "none" else 2.8, marker="o", ms=5, mfc=face, mec=LIMIT_COLOUR[limit],
                    zorder=3 if limit == "none" else 2)
        ax.set_title(col, loc="left", fontsize=11)
        ax.grid(alpha=0.3)
        ax.axhline(0, color="#999", lw=0.8)
        ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    for ax in axes.flat[len(cols):]:
        ax.set_visible(False)
    handles = [Line2D([], [], color=c, lw=2.5, label=f"{k} limit" if k != "none" else "run1 (no limit, no LULUCF corr., no CDR)")
               for k, c in LIMIT_COLOUR.items()]
    handles += [Line2D([], [], color="k", lw=2, ls="-", label="100 % self-sufficiency by 2050"),
                Line2D([], [], color="k", lw=2, ls="--", label="60 % self-sufficiency by 2050"),
                Line2D([], [], color="k", marker="o", ls="", mfc="k", label="BAU LULUCF (run2–5)"),
                Line2D([], [], color="k", marker="o", ls="", mfc="white", label="optimistic-weak LULUCF (run6–9)")]
    fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=11)
    fig.suptitle("Weekend batch: system-level impact of the fossil limits, the self-sufficiency target and LULUCF",
                 fontsize=14, x=0.01, ha="left")
    fig.savefig(out, dpi=160)
    plt.close(fig)


def lever_effects(m):
    rows = []
    for lever, pairs in LEVERS.items():
        for a, b in pairs:
            ra, rb = f"weekend_run{a}", f"weekend_run{b}"
            if ra not in m.index.levels[0] or rb not in m.index.levels[0]:
                continue
            d = m.loc[rb] - m.loc[ra]
            d["lever"], d["pair"] = lever, f"run{a}→run{b}"
            rows.append(d.reset_index())
    return pd.concat(rows, ignore_index=True)


def fig_levers(eff, cols, out):
    fig, axes = plt.subplots(4, 4, figsize=(18, 15), layout="constrained")
    for ax, col in zip(axes.flat, cols):
        for lever in LEVERS:
            d = eff[eff.lever == lever].groupby("year")[col]
            mean, lo, hi = d.mean(), d.min(), d.max()
            ax.fill_between(mean.index, lo.values, hi.values, color=LEVER_COLOUR[lever], alpha=0.15, lw=0)
            ax.plot(mean.index, mean.values, color=LEVER_COLOUR[lever], lw=2.4, marker="o", ms=4)
        ax.axhline(0, color="#555", lw=0.9)
        ax.set_title("Δ " + col, loc="left", fontsize=11)
        ax.grid(alpha=0.3)
        ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    for ax in axes.flat[len(cols):]:
        ax.set_visible(False)
    handles = [Line2D([], [], color=c, lw=2.5, label=k) for k, c in LEVER_COLOUR.items()]
    handles.append(Patch(color="#999", alpha=0.3, label="range over the 4 matched run pairs"))
    fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False, fontsize=11)
    fig.suptitle("Effect of each lever: change when only that lever changes (mean of 4 matched run pairs)",
                 fontsize=14, x=0.01, ha="left")
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot(extract_dir, out_dir):
    ext = pd.concat([pd.read_csv(f) for f in sorted(extract_dir.glob("impact_weekend_run*.csv"))], ignore_index=True)
    m = metrics(ext)
    out_dir.mkdir(parents=True, exist_ok=True)
    m.round(2).to_csv(extract_dir / "impact_table.csv")
    fig_overview(m, out_dir / "impact_overview.png")
    eff = lever_effects(m)
    eff.round(2).to_csv(extract_dir / "impact_lever_effects.csv", index=False)
    fig_levers(eff, list(m.columns), out_dir / "impact_lever_effects.png")
    print(f"wrote {out_dir}/impact_overview.png, impact_lever_effects.png")


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    mode, root, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if mode == "extract" and len(sys.argv) > 4:
        extract(root, out, sys.argv[4])
    elif mode == "plot":
        plot(root, out)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
