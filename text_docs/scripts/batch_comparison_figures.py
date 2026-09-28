"""
Cross-scenario comparison figures for the weekend batch.

Run from the pypsa-eur root.

  1. extract (needs the solved networks; one call per run, e.g. as a job array):

        python text_docs/scripts/batch_comparison_figures.py extract <results_root> <out_dir> <run>

     writes <out_dir>/extract_<run>.csv: per horizon, CO2 flows by technology on
     the atmosphere and on the captured-CO2 ("co2 stored") buses (same flows as
     co2_market_curves.py) and the shadow prices of CO2Limit, the fossil limits
     and the sequestration limit.

  2. plot (needs the extract files and each run's csvs/costs.csv):

        python text_docs/scripts/batch_comparison_figures.py plot <results_root> <out_dir> <reference> <run> [<run> ...]

     writes:
       comparison_costs_by_year_all_runs.png   stacked cost bars, all runs side by side per year
       comparison_1_cost_and_constraints.png   total cost, cost change vs the reference by
                                               technology group, and the shadow prices
       comparison_2_technology_shift.png       heatmap of the cost change vs the reference
                                               per technology, year and run
       comparison_3_co2_balances_<runs>.png    atmosphere and captured-CO2 balances per year,
                                               with the CO2 price split into disposal and
                                               capture margin

Colours are the official PyPSA-Eur tech_colors (for groups: the colour of a
representative technology), as in the costs plots.
"""

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
import yaml
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch

from scripts._helpers import rename_techs

with open(REPO / "config" / "plotting.default.yaml") as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]


def colour(name):
    return TECH_COLORS.get(name) or TECH_COLORS.get(rename_techs(name)) or "#9e9e9e"


# ---------------------------------------------------------------- groupings
# cost groups (on rename_techs names); first matching rule wins
COST_GROUPS = [
    ("CO2 capture & removal", ["co2", "dac", " cc", "sequest", "afforestation", "perennial", "weathering", "biochar"], "DAC"),
    ("hydrogen & e-fuels", ["h2", "hydrogen", "electrolysis", "fischer", "electrobiofuel", "methanolisation", "sabatier", "methanation", "haber", "smr", "ammonia", "methanol"], "H2 Electrolysis"),
    ("nuclear", ["nuclear", "uranium"], "nuclear"),
    ("networks & storage", ["transmission", "distribution", "pipeline", "battery", "store", "storage"], "transmission lines"),
    ("heat", ["heat pump", "resistive", "boiler", "chp", "water tank", "water pit", "solar thermal"], "air heat pump"),
    ("industry", ["cement", "steel", "eaf", "dri", "bof", "hbi", "clinker", "hvc", "kiln"], "cement kiln"),
    ("biomass & biogas", ["biomass", "biogas", "bioliquid", "biofuel"], "solid biomass"),
    ("fossil fuels", ["oil", "gas", "coal", "lignite", "lng"], "gas"),
    ("renewable power", ["wind", "solar", "hydro", "run of river", "ror"], "onshore wind"),
]


def cost_group(tech):
    t = tech.lower()
    for group, keys, _ in COST_GROUPS:
        if any(k in t for k in keys):
            return group
    return "other"


GROUP_COLOUR = {g: TECH_COLORS.get(rep, "#9e9e9e") for g, _, rep in COST_GROUPS}
GROUP_COLOUR["other"] = "#bdbdbd"

# atmosphere: emissions (+) and removals (-) by source
ATM_EMIT = [
    ("gas", ["gas", "ccgt", "ocgt", "chp", "lng", "methane"], "gas"),
    ("oil & kerosene", ["oil", "kerosene", "naphtha", "diesel"], "oil"),
    ("coal & lignite", ["coal", "lignite"], "coal"),
    ("process & waste", ["process", "cement", "steel", "hvc", "clinker"], "process emissions"),
    ("biomass import", ["import"], "solid biomass import"),
]
ATM_REMOVE = [
    ("novel CDR", ["afforestation", "perennial", "weathering", "biochar"], "co2 afforestation"),
    ("DAC", ["dac"], "DAC"),
    ("BECCS (biomass CC)", [" cc"], "solid biomass for mediumT industry CC"),
    ("biogenic fuels", ["electrobiofuel", "biogas", "biomass to liquid", "biomass-to-methanol", "bioliquid"], "electrobiofuels"),
]
STORED_SUPPLY = [
    ("DAC", ["dac"], "DAC"),
    ("BECCS (biomass CC)", ["biomass", "biogas"], "solid biomass for mediumT industry CC"),
    ("cement, steel & process CC", ["cement", "steel", "process"], "cement emission CC"),
    ("fossil CC", ["gas", "methane", "smr", "oil"], "SMR CC"),
]
STORED_DEMAND = [
    ("geological storage", ["sequest"], "co2 sequestered"),
    ("Fischer-Tropsch", ["fischer"], "Fischer-Tropsch"),
    ("methanation (Sabatier)", ["sabatier", "methanation"], "Sabatier"),
    ("methanolisation", ["methanol"], "methanolisation"),
]


def classify(carrier, rules):
    c = carrier.lower()
    for name, keys, _ in rules:
        if any(k in c for k in keys):
            return name
    return "other"


def rule_colour(rules, name):
    for n_, _, rep in rules:
        if n_ == name:
            return colour(rep)
    return "#bdbdbd"


# ---------------------------------------------------------------- extract
def extract(results_root, out_dir, run):
    import re

    import pypsa

    from co2_market_curves import break_even_table

    rows = []
    for path in sorted((results_root / run / "networks").glob("*.nc")):
        m = re.search(r"_(\d{4})\.nc$", path.name)
        if not m:
            continue
        year = int(m.group(1))
        print(f"{run} {year}", flush=True)
        n = pypsa.Network(str(path))
        gc = n.global_constraints
        for name in gc.index:
            rows.append(dict(run=run, year=year, kind="shadow_price", name=name, value=-float(gc.at[name, "mu"])))
        for market, bus_carrier in [("atmosphere", "co2"), ("co2 stored", "co2 stored")]:
            t = break_even_table(n, bus_carrier)
            if t.empty:
                continue
            for carrier, q in t.groupby("carrier").q.sum().items():
                rows.append(dict(run=run, year=year, kind=f"flow {market}", name=carrier, value=q / 1e6))
            if market == "co2 stored":
                sup = t[t.q > 0]
                if len(sup) and sup.q.sum() > 0:
                    rows.append(dict(run=run, year=year, kind="price", name="co2 stored",
                                     value=sup.lam_q.sum() / sup.q.sum()))
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / f"extract_{run}.csv", index=False)
    print(f"wrote {out_dir / f'extract_{run}.csv'}")


# ---------------------------------------------------------------- plot helpers
def load_costs(results_root, run):
    df = pd.read_csv(results_root / run / "csvs" / "costs.csv", index_col=[0, 1, 2], header=[0, 1, 2])
    df = df.groupby("carrier").sum() / 1e9
    df = df.groupby(df.index.map(rename_techs)).sum()
    df.columns = [int(c[2]) for c in df.columns]
    return df


def short(run):
    return run.replace("weekend_", "")


CAVEAT = ("Reference run1 differs from the others in three ways at once: no fossil limit, no LULUCF correction "
          "(looser CO2 limit) and no CDR/biomethanation. Differences vs run1 combine all three; run2/6 vs run4/8 "
          "also differ in biomass import (on only in run4/5/8/9).")


def fig_costs_by_year(costs, runs, years, out):
    techs = set()
    for df in costs.values():
        techs |= set(df.index[df.max(axis=1) >= 1.0])
    techs = sorted(techs, key=lambda t: -max(costs[r].reindex(index=[t]).fillna(0).values.max() for r in runs))
    fig, ax = plt.subplots(figsize=(22, 8.5))
    nr = len(runs)
    width = 0.8 / nr
    for j, run in enumerate(runs):
        df = costs[run]
        x = np.arange(len(years)) + (j - (nr - 1) / 2) * width
        bottom = np.zeros(len(years))
        for t in techs:
            v = df.reindex(index=[t], columns=years).fillna(0).values[0]
            ax.bar(x, v, bottom=bottom, width=width * 0.92, color=colour(t), label=t if j == 0 else None,
                   edgecolor="white", linewidth=0.15)
            bottom += v
        other = df.reindex(columns=years).fillna(0).sum().values - bottom
        ax.bar(x, other, bottom=bottom, width=width * 0.92, color="#d9d9d9", label="other" if j == 0 else None)
        for xi, tot in zip(x, df.reindex(columns=years).fillna(0).sum().values):
            ax.text(xi, tot + 8, short(run).replace("run", ""), ha="center", fontsize=7, rotation=90)
    ax.set_xticks(np.arange(len(years)), [str(y) for y in years])
    ax.set_ylabel("System cost [EUR billion per year]")
    ax.set_title("Total system cost by technology — all runs side by side per year (label above each bar = run number)")
    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], loc="upper left", bbox_to_anchor=(1.005, 1), fontsize=7, frameon=False)
    ax.set_ylim(0, max(df.sum().max() for df in costs.values()) * 1.1)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig1(costs, prices, ref, runs, years, out):
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(3, len(runs), height_ratios=[1.0, 1.4, 1.1], hspace=0.35, wspace=0.12)
    # (a) totals
    ax0 = fig.add_subplot(gs[0, :])
    for run in [ref] + runs:
        tot = costs[run].reindex(columns=years).fillna(0).sum()
        ax0.plot(years, tot.values, marker="o", lw=2.5 if run == ref else 2, ls="--" if run == ref else "-", label=short(run))
    ax0.set_ylabel("Total system cost\n[bn€/yr]")
    ax0.set_xticks(years)
    ax0.legend(ncol=len(runs) + 1, frameon=False, loc="upper left")
    ax0.set_title("(a) Total system cost", loc="left")
    # (b) change vs reference by group
    groups = [g for g, _, _ in COST_GROUPS] + ["other"]
    ref_g = costs[ref].groupby(costs[ref].index.map(cost_group)).sum().reindex(index=groups, columns=years).fillna(0)
    lims = []
    axes_b = []
    for j, run in enumerate(runs):
        ax = fig.add_subplot(gs[1, j], sharey=axes_b[0] if axes_b else None)
        axes_b.append(ax)
        g = costs[run].groupby(costs[run].index.map(cost_group)).sum().reindex(index=groups, columns=years).fillna(0)
        d = g - ref_g
        pos = np.zeros(len(years)); neg = np.zeros(len(years))
        for grp in groups:
            v = d.loc[grp].values
            ax.bar(years, np.where(v > 0, v, 0), bottom=pos, width=3.6, color=GROUP_COLOUR[grp], label=grp if j == 0 else None)
            ax.bar(years, np.where(v < 0, v, 0), bottom=neg, width=3.6, color=GROUP_COLOUR[grp])
            pos += np.where(v > 0, v, 0); neg += np.where(v < 0, v, 0)
        net = d.sum().values
        ax.plot(years, net, color="black", marker="D", lw=1.5, label="net change" if j == 0 else None)
        ax.axhline(0, color="black", lw=0.6)
        ax.set_xticks(years, [str(y)[2:] for y in years])
        ax.set_title(f"(b) {short(run)} − {short(ref)}", loc="left", fontsize=10)
        lims += [pos.max(), neg.min()]
        if j:
            plt.setp(ax.get_yticklabels(), visible=False)
    axes_b[0].set_ylabel("Cost change vs reference\n[bn€/yr]")
    fig.legend(*axes_b[0].get_legend_handles_labels(), loc="center right", bbox_to_anchor=(1.0, 0.52), frameon=False, fontsize=8)
    # (c) shadow prices
    axes_c = []
    for j, run in enumerate(runs):
        ax = fig.add_subplot(gs[2, j], sharey=axes_c[0] if axes_c else None)
        axes_c.append(ax)
        p = prices[prices["run"] == run]
        for name, lab, st in [("CO2Limit", "CO2 price", dict(color="black", lw=2.5)),
                              ("fossil_fuel_limit", "fossil limit (aggregate)", dict(color=colour("oil"), lw=2)),
                              ("energy_limit_security_gas", "fossil limit: gas", dict(color=colour("gas"), lw=2)),
                              ("energy_limit_security_oil", "fossil limit: oil", dict(color=colour("oil"), lw=2, ls=":")),
                              ("energy_limit_security_coal", "fossil limit: coal", dict(color=colour("coal"), lw=2)),
                              ("energy_limit_security_lignite", "fossil limit: lignite", dict(color=colour("lignite"), lw=2)),
                              ("co2_sequestration_limit", "storage limit", dict(color=colour("co2 sequestered"), lw=2, ls="--"))]:
            s = p[p["name"] == name].set_index("year")["value"].reindex(years)
            if s.notna().any():
                ax.plot(years, s.abs().values, marker="o", ms=4, label=lab, **st)
        ax.set_xticks(years, [str(y)[2:] for y in years])
        ax.set_title(f"(c) shadow prices — {short(run)}", loc="left", fontsize=10)
        if j:
            plt.setp(ax.get_yticklabels(), visible=False)
    axes_c[0].set_ylabel("€/tCO2")
    hc, lc = [], []
    for ax in axes_c:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in lc:
                hc.append(h); lc.append(l)
    fig.legend(hc, lc, loc="center right", bbox_to_anchor=(1.0, 0.17), frameon=False, fontsize=8)
    fig.suptitle("Cost of energy independence and when the constraints bind", fontsize=14, y=0.995)
    fig.text(0.01, 0.005, CAVEAT, fontsize=8, color="dimgrey")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig2(costs, ref, runs, years, out, n_rows=24):
    ref_df = costs[ref].reindex(columns=years).fillna(0)
    deltas = {}
    for run in runs:
        d = costs[run].reindex(columns=years).fillna(0).sub(ref_df, fill_value=0).fillna(0)
        deltas[run] = d
    allidx = sorted(set().union(*[d.index for d in deltas.values()]))
    score = pd.Series({t: max(deltas[r].reindex(index=[t]).fillna(0).abs().values.max() for r in runs) for t in allidx})
    rows = list(score.sort_values(ascending=False).index[:n_rows])
    rows = sorted(rows, key=lambda t: (cost_group(t), t))
    mat = np.column_stack([deltas[r].reindex(index=rows).fillna(0).values for r in runs])
    lim = np.nanmax(np.abs(mat))
    fig, ax = plt.subplots(figsize=(2.2 + 1.9 * len(runs), 0.36 * len(rows) + 2.5))
    im = ax.imshow(mat, aspect="auto", cmap="RdBu_r", norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim))
    ax.set_yticks(range(len(rows)), rows, fontsize=8)
    xt = [str(y)[2:] for _ in runs for y in years]
    ax.set_xticks(range(mat.shape[1]), xt, fontsize=7)
    for j, run in enumerate(runs):
        ax.axvline(j * len(years) - 0.5, color="black", lw=1.2)
        ax.text(j * len(years) + (len(years) - 1) / 2, -0.9, f"{short(run)} − {short(ref)}", ha="center", fontsize=10, fontweight="bold")
    for i in range(mat.shape[0]):
        for k in range(mat.shape[1]):
            v = mat[i, k]
            if abs(v) >= 0.15 * lim:
                ax.text(k, i, f"{v:.0f}", ha="center", va="center", fontsize=6, color="white" if abs(v) > 0.55 * lim else "black")
    cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("Cost change vs reference [bn€/yr]\n(red: more, blue: less)")
    ax.set_title(f"Technology shift by year: change in annual cost vs {short(ref)} ({len(rows)} technologies with the largest changes)",
                 fontsize=11, pad=28)
    fig.text(0.01, -0.01, CAVEAT, fontsize=8, color="dimgrey", wrap=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig3(ext, runs, years, out):
    """Atmosphere (left) and captured CO2 (right), grouped bars per year, plus the price split."""
    fig = plt.figure(figsize=(20, 12.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[3.2, 1.2], hspace=0.55, wspace=0.18)
    axA, axB, axP = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    nr = len(runs)
    width = 0.8 / nr
    hatches = ["", "//", "xx", "..", "\\\\"]

    def panel(ax, market, up_rules, down_rules, title):
        tops = []
        for j, run in enumerate(runs):
            x = np.arange(len(years)) + (j - (nr - 1) / 2) * width
            f = ext[(ext["run"] == run) & (ext["kind"] == f"flow {market}")].copy()
            up = np.zeros(len(years)); dn = np.zeros(len(years))
            for rules, sign in [(up_rules, 1), (down_rules, -1)]:
                side = f[f["value"] * sign > 0].copy()
                side["group"] = side["name"].map(lambda c: classify(c, rules))
                tab = side.groupby(["group", "year"])["value"].sum()
                for name in [r[0] for r in rules] + ["other"]:
                    v = np.array([tab.get((name, y), 0.0) for y in years])
                    base = up if sign > 0 else dn
                    ax.bar(x, v, bottom=base, width=width * 0.92, color=rule_colour(rules, name), hatch=hatches[j % 5],
                           edgecolor="white", linewidth=0.3, label=name if j == 0 else None)
                    if sign > 0:
                        up += v
                    else:
                        dn += v
            ax.plot(x, up + dn, ls="none", marker="D", color="black", ms=4, label="net" if j == 0 else None)
            tops.append((x, up))
        top = max(u.max() for _, u in tops) if tops else 1.0
        for (x, up), run in zip(tops, runs):
            for xi, u in zip(x, up):
                ax.text(xi, u + 0.01 * top, short(run).replace("run", ""), ha="center", fontsize=7)
        ax.axhline(0, color="black", lw=0.7)
        ax.set_xticks(np.arange(len(years)), [str(y) for y in years])
        ax.set_ylabel("MtCO2/yr  (up: into the bus, down: out of it)")
        ax.set_title(title, loc="left")
        h, l = ax.get_legend_handles_labels()
        seen = {}
        for hh, ll in zip(h, l):
            seen.setdefault(ll, hh)
        ax.legend(seen.values(), seen.keys(), fontsize=8, frameon=False, loc="upper center",
                  bbox_to_anchor=(0.5, -0.07), ncol=4)

    panel(axA, "atmosphere", ATM_EMIT, ATM_REMOVE, "(a) CO2 atmosphere: emissions (up) and removals (down); ◆ = net = CO2 limit")
    panel(axB, "co2 stored", STORED_SUPPLY, STORED_DEMAND, "(b) Captured CO2: capture (up) and storage / use (down)")

    # (c) price split: CO2 price = disposal (-co2 stored price) + capture margin
    for j, run in enumerate(runs):
        x = np.arange(len(years)) + (j - (nr - 1) / 2) * width
        sp = ext[(ext["run"] == run) & (ext["kind"] == "shadow_price") & (ext["name"] == "CO2Limit")].set_index("year")["value"].reindex(years).fillna(0).values
        cs = ext[(ext["run"] == run) & (ext["kind"] == "price") & (ext["name"] == "co2 stored")].set_index("year")["value"].reindex(years)
        has = cs.notna().values  # the split only exists where CO2 is captured
        disposal = np.where(has, np.clip(-cs.fillna(0).values, 0, None), 0.0)
        margin = np.where(has, sp - disposal, 0.0)
        axP.bar(x, disposal, width=width * 0.92, color=colour("co2 sequestered"), hatch=hatches[j % 5], edgecolor="white",
                label="disposal: −(captured CO2 price)" if j == 0 else None)
        axP.bar(x, margin, bottom=disposal, width=width * 0.92, color=colour("DAC"), hatch=hatches[j % 5], edgecolor="white",
                label="capture margin" if j == 0 else None)
        axP.plot(x[~has], sp[~has], ls="none", marker="_", ms=18, mew=2.5, color="black",
                 label="CO2 price, no CO2 captured" if j == 0 else None)
        for xi, v in zip(x, sp):
            axP.text(xi, v + 8, short(run).replace("run", ""), ha="center", fontsize=7)
    axP.set_xticks(np.arange(len(years)), [str(y) for y in years])
    axP.set_ylabel("€/tCO2")
    axP.set_title("(c) CO2 price split: disposal of a captured tonne + capture margin (bar top = CO2 price)", loc="left")
    axP.legend(fontsize=8, frameon=False, loc="upper left")
    fig.suptitle(f"CO2 balances by year — runs {', '.join(short(r) for r in runs)} (bar order and hatch per run, label above bar = run number)",
                 fontsize=13, y=0.995)
    fig.text(0.01, 0.0, CAVEAT, fontsize=8, color="dimgrey")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot(results_root, out_dir, ref, runs, all_runs):
    years = [2025, 2030, 2035, 2040, 2045, 2050]
    costs = {r: load_costs(results_root, r) for r in set(all_runs) | {ref} | set(runs)}
    fig_costs_by_year(costs, sorted(all_runs, key=lambda r: int(r.replace("weekend_run", ""))), years,
                      out_dir / "comparison_costs_by_year_all_runs.png")
    ext = pd.concat([pd.read_csv(out_dir / f"extract_{r}.csv") for r in [ref] + runs if (out_dir / f"extract_{r}.csv").exists()])
    prices = ext[ext["kind"] == "shadow_price"]
    fig1(costs, prices, ref, runs, years, out_dir / "comparison_1_cost_and_constraints.png")
    fig2(costs, ref, runs, years, out_dir / "comparison_2_technology_shift.png")
    for group in ([r for r in runs if r in ("weekend_run2", "weekend_run4")], [r for r in runs if r in ("weekend_run6", "weekend_run8")]):
        if group:
            sel = [ref] + group
            fig3(ext, sel, years, out_dir / f"comparison_3_co2_balances_{'_'.join(short(r) for r in sel)}.png")
    print(f"figures in {out_dir}")


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    mode, results_root, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    if mode == "extract":
        extract(results_root, out_dir, sys.argv[4])
    elif mode == "plot":
        ref, runs = sys.argv[4], sys.argv[5:]
        all_runs = [f"weekend_run{i}" for i in range(1, 10) if (results_root / f"weekend_run{i}" / "csvs" / "costs.csv").exists()]
        plot(results_root, out_dir, ref, runs, all_runs)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
