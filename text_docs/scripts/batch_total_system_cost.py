"""
Total system cost by technology for a batch of myopic runs, from each run's
csvs/costs.csv (make_summary output).

Run from the pypsa-eur root:

    python text_docs/scripts/batch_total_system_cost.py <results_root> <out_dir> <run1> [<run2> ...]

Same grouping and colours as scripts/plot_summary.py (rename_techs, the
plotting.costs_threshold of 1 bn EUR/yr, preferred_order, tech_colors), with
two deliberate differences:
  - the y-axis scales to the data. plot_summary.py fixes it at
    plotting.costs_max (1000 bn EUR/yr), which cuts off every bar above that;
  - technologies below the threshold are kept as "other" instead of dropped,
    so each bar adds up to the full total system cost.
The same technology set is used for every run, so colours and stacking order
match across scenarios.

Outputs:
  costs_<run>.png                      one stacked bar chart per run
  costs_all_scenarios.png              3x3 grid, shared y-axis
  total_system_cost_by_scenario.png    total system cost per run and year
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
import yaml

from scripts._helpers import rename_techs
from scripts.plot_summary import preferred_order

plt.style.use("bmh")

with open(REPO / "config" / "plotting.default.yaml") as f:
    PLOTTING = yaml.safe_load(f)["plotting"]
TECH_COLORS = dict(PLOTTING["tech_colors"])
THRESHOLD = PLOTTING["costs_threshold"]
OTHER = "other (below threshold)"
TECH_COLORS[OTHER] = "#bdbdbd"


def load_costs(results_root, run):
    """bn EUR/yr per renamed technology (rows) and planning horizon (columns)."""
    df = pd.read_csv(results_root / run / "csvs" / "costs.csv", index_col=[0, 1, 2], header=[0, 1, 2])
    df = df.groupby("carrier").sum() / 1e9
    df = df.groupby(df.index.map(rename_techs)).sum()
    df.columns = [int(c[2]) for c in df.columns]
    return df


def ordered(techs):
    techs = pd.Index(techs)
    return list(preferred_order.intersection(techs).append(techs.difference(preferred_order)))


def stacked(ax, df, techs, years):
    bottom = np.zeros(len(years))
    x = np.arange(len(years))
    for t in techs:
        v = df.reindex(index=[t], columns=years).fillna(0).values[0]
        ax.bar(x, v, bottom=bottom, width=0.7, color=TECH_COLORS.get(t, "#999999"), label=t)
        bottom += v
    ax.set_xticks(x, [str(y) for y in years])
    ax.grid(axis="x")
    return bottom


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    results_root, out_dir, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    out_dir.mkdir(parents=True, exist_ok=True)

    costs = {run: load_costs(results_root, run) for run in runs}
    years = sorted({y for df in costs.values() for y in df.columns})

    # one technology set for all runs: above the threshold in any run and year
    keep = set()
    for df in costs.values():
        keep |= set(df.index[df.max(axis=1) >= THRESHOLD])
    techs = ordered(keep)
    missing = [t for t in techs if t not in TECH_COLORS]
    if missing:
        print(f"no tech colour for {missing}; drawn in grey")
    for run, df in costs.items():
        other = df.loc[~df.index.isin(keep)].sum()
        costs[run] = pd.concat([df.loc[df.index.isin(keep)], other.rename(OTHER).to_frame().T])
    techs = techs + [OTHER]

    totals = pd.DataFrame({run: df.sum() for run, df in costs.items()}).T.reindex(columns=years)
    ymax = totals.max().max() * 1.08

    # per run
    for run, df in costs.items():
        fig, ax = plt.subplots(figsize=(12, 8))
        tops = stacked(ax, df, techs, years)
        for xi, v in enumerate(tops):
            ax.text(xi, v + ymax * 0.01, f"{v:.0f}", ha="center", fontsize=10, fontweight="bold")
        ax.set_ylim(0, ymax)
        ax.set_ylabel("System Cost [EUR billion per year]")
        ax.set_title(f"Total system cost by technology — {run}")
        h, l = ax.get_legend_handles_labels()
        ax.legend(h[::-1], l[::-1], ncol=1, loc="upper left", bbox_to_anchor=[1, 1], frameon=False, fontsize=8)
        fig.savefig(out_dir / f"costs_{run}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

    # 3x3 comparison, shared y-axis
    ncol = 3
    nrow = int(np.ceil(len(runs) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(20, 5.2 * nrow), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, run in zip(axes, runs):
        tops = stacked(ax, costs[run], techs, years)
        for xi, v in enumerate(tops):
            ax.text(xi, v + ymax * 0.01, f"{v:.0f}", ha="center", fontsize=8, fontweight="bold")
        ax.set_title(run)
        ax.set_ylim(0, ymax)
    for ax in axes[len(runs):]:
        ax.set_visible(False)
    for i in range(0, len(runs), ncol):
        axes[i].set_ylabel("System Cost [EUR billion per year]")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h[::-1], l[::-1], loc="center left", bbox_to_anchor=(0.995, 0.5), frameon=False, fontsize=8)
    fig.suptitle("Total system cost by technology, all scenarios (shared y-axis)", fontsize=15)
    fig.tight_layout(rect=(0, 0, 0.995, 0.97))
    fig.savefig(out_dir / "costs_all_scenarios.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    # totals per scenario
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for run in runs:
        ax.plot(years, totals.loc[run].values, marker="o", lw=2, label=run)
    ax.set_xticks(years)
    ax.set_ylabel("Total system cost [EUR billion per year]")
    ax.set_title("Total system cost by scenario and planning horizon")
    ax.legend(frameon=False, ncol=3)
    fig.savefig(out_dir / "total_system_cost_by_scenario.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(totals.round(0).to_string())
    print(f"Wrote {len(runs) + 2} figures to {out_dir}")


if __name__ == "__main__":
    main()
