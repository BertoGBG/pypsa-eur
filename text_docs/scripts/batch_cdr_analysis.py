"""
CDR analysis for a batch of myopic scenario runs: merit-order curves per
scenario and planning horizon, plus a cross-scenario deployment summary.

Run from the pypsa-eur root (so scripts/ helpers and config/ resolve):

    python text_docs/scripts/batch_cdr_analysis.py <results_root> <out_dir> <run1> [<run2> ...]

e.g. python text_docs/scripts/batch_cdr_analysis.py results results/weekend_batch_analysis/cdr \
         weekend_run1 weekend_run2 ... weekend_run9

For every results/<run>/networks/*_<year>.nc it writes:
  merit_order/<run>/CDR_merit_order_<run>_<year>.png  -- same curve as
      scripts/plot_CDR_merit_order.py (four CDR techs + geological CO2 storage,
      bar width = potential, height = gross LCCDR, dashed line = CO2 price),
      built from the same helpers. One deliberate difference: geological
      storage width is this year's injection, not the store size (see
      sequestration_annual).
  merit_order/<run>/merit_order_supply_<year>.csv    -- the bars behind it.
and across all runs:
  cdr_summary.csv                    -- one row per (run, year).
  cdr_deployment_by_scenario.png     -- 3x3 grid: removal by CDR tech and CO2
      captured by source per horizon, CO2 price on the right axis.

Missing horizons (e.g. a 2050 solve still running) are skipped.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
import yaml
from matplotlib.patches import Patch

from plot_CDR_map import CDR_TECHS, compute_cdr_per_node
from plot_CDR_merit_order import hypothetical_lccdr


def sequestration_annual(n, co2_price, sw):
    """
    Geological CO2 storage bars for a myopic horizon. Same cost as
    plot_CDR_merit_order.sequestration_lccdr (CO2 price + mean price at the
    node's "co2 sequestered" bus), but the width is the CO2 injected in THIS
    year (store level at the last snapshot minus e_initial). The store's
    e_nom_opt is the storage size, which in a myopic run keeps the capacity
    of earlier horizons and so is far larger than one year's injection.
    """
    stores = n.stores[n.stores.carrier == "co2 sequestered"]
    if stores.empty:
        return pd.DataFrame(columns=["potential", "lccdr"])
    mp = n.buses_t.marginal_price
    mean_price = mp.mul(sw, axis=0).sum() / sw.sum()
    injected = n.stores_t.e[stores.index].iloc[-1] - stores["e_initial"]
    records = []
    for name, store in stores.iterrows():
        if float(store["e_nom_max"]) <= 0 or injected[name] <= 0 or store["bus"] not in mean_price.index:
            continue
        node = n.buses.at[store["bus"], "location"]
        records.append(dict(node=node, potential=float(injected[name]), lccdr=mean_price[store["bus"]] + co2_price))
    if not records:
        return pd.DataFrame(columns=["potential", "lccdr"])
    return pd.DataFrame(records).set_index("node")

with open(REPO / "config" / "plotting.default.yaml") as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]

SEQ = ("Geological CO2 storage", "co2 sequestered")
ALL_SERIES = list(CDR_TECHS) + [SEQ]

# Captured-CO2 sources feeding the "co2 stored" buses, grouped for the summary.
BIOGENIC_KEYS = ("biomass", "biogas", "bioliquids", "biomethanation", "biosng", "bioSNG")


def co2_price_of(n):
    gc = n.global_constraints
    if "CO2Limit" in gc.index and pd.notna(gc.at["CO2Limit", "mu"]):
        return -float(gc.at["CO2Limit", "mu"])
    return None


def build_supply(n):
    """Same steps as plot_CDR_merit_order.main(), minus plotting."""
    sw = n.snapshot_weightings["stores"]
    mp = n.buses_t.marginal_price if "marginal_price" in n.buses_t else None
    co2_price = co2_price_of(n)
    frames = []
    for label, carrier in CDR_TECHS:
        df = compute_cdr_per_node(n, carrier)
        if df.empty:
            continue
        df = df.rename(columns={"e_nom_max": "potential", "lccdr_gross": "lccdr"})
        # actual CO2 removed this year; e_nom_opt equals the potential for
        # techs whose store size is fixed, so it cannot show deployment
        df["deployed"] = df["co2_seq"].fillna(0.0)
        df["hypothetical"] = False
        missing = df["lccdr"].isna()
        if missing.any():
            # a node can appear more than once, so fill by lookup, not .loc
            hyp = hypothetical_lccdr(n, carrier, sw, mp, df.index[missing].unique())
            est = df.index.to_series().map(hyp)
            fill = missing & est.notna().values
            df.loc[fill.values, "lccdr"] = est[fill.values].values
            df.loc[fill.values, "hypothetical"] = True
        df = df.dropna(subset=["lccdr"])
        if df.empty:
            continue
        df["tech"], df["carrier"] = label, carrier
        frames.append(df[["potential", "deployed", "lccdr", "hypothetical", "tech", "carrier"]])
    if co2_price is not None:
        seq = sequestration_annual(n, co2_price, sw)
        if not seq.empty:
            seq["deployed"] = seq["potential"]  # width is already this year's injection
            seq["hypothetical"] = False
            seq["tech"], seq["carrier"] = SEQ
            frames.append(seq[["potential", "deployed", "lccdr", "hypothetical", "tech", "carrier"]])
    if not frames:
        return pd.DataFrame(), co2_price
    supply = pd.concat(frames).rename_axis("node").reset_index().sort_values("lccdr").reset_index(drop=True)
    supply["left_edge"] = supply["potential"].cumsum() - supply["potential"]
    return supply, co2_price


def plot_merit_order(supply, co2_price, title, out_path):
    fig, ax = plt.subplots(figsize=(13, 6))
    present, any_hyp = [], False
    for label, carrier in ALL_SERIES:
        mask = supply["tech"] == label
        if not mask.any():
            continue
        present.append((label, carrier))
        for hyp, hatch in [(False, None), (True, "///")]:
            sub = supply[mask & (supply["hypothetical"] == hyp)]
            if sub.empty:
                continue
            any_hyp |= hyp
            ax.bar(sub["left_edge"] / 1e6, sub["lccdr"], width=sub["potential"] / 1e6, align="edge",
                   color=TECH_COLORS.get(carrier, "grey"), edgecolor="white", linewidth=0.2, hatch=hatch)
    total = supply["potential"].sum() / 1e6
    if co2_price is not None:
        ax.axhline(co2_price, color="black", ls="--", lw=1.2, zorder=5)
        ax.text(total * 0.99, co2_price, f" CO2 price: {co2_price:.0f} EUR/tCO2", ha="right", va="bottom",
                fontsize=9, bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.5))
    cdr = supply[supply["tech"] != SEQ[0]]
    if not cdr.empty:
        ax.text(0.99, 0.97, f"CDR deployed: {cdr['deployed'].sum() / 1e6:.1f} of {cdr['potential'].sum() / 1e6:.1f} MtCO2 potential",
                transform=ax.transAxes, ha="right", va="top", fontsize=9)
    ax.set_xlabel("Cumulative CO2 removal potential [MtCO2]")
    ax.set_ylabel("Levelized Cost of CDR [EUR/tCO2]  (excl. CO2 credit)")
    ax.set_title(title)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.spines[["top", "right"]].set_visible(False)
    handles = [Patch(facecolor=TECH_COLORS.get(c, "grey"), edgecolor="white", label=l) for l, c in present]
    if any_hyp:
        handles.append(Patch(facecolor="white", edgecolor="black", hatch="///",
                             label="Undeployed: hypothetical, mean local price"))
    ax.legend(handles=handles, frameon=False, loc="upper left")
    notes = []
    if any_hyp:
        notes.append("Hatched bars: no observed dispatch, cost estimated at uniform all-year dispatch and the node's mean "
                     "local prices (likely an overestimate for flexibly dispatched techs such as biochar and rock weathering).")
    if (supply["tech"] == SEQ[0]).any():
        notes.append("Geological CO2 storage: cost = CO2 price + price at the node's 'co2 sequestered' bus (capture + transport "
                     "+ injection), width = CO2 injected this year; shown for cost comparison, it does not compete 1:1 with the CDR techs.")
    if notes:
        fig.text(0.01, -0.02, "\n".join(notes), fontsize=7.5, color="dimgrey", ha="left", va="top")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def captured_co2_by_source(n):
    """MtCO2/yr flowing into 'co2 stored' buses, by source group."""
    w = n.snapshot_weightings.generators
    stored = set(n.buses.index[n.buses.carrier == "co2 stored"])
    out = {"DAC": 0.0, "biogenic CC": 0.0, "fossil/process CC": 0.0}
    L = n.links
    for i in range(5):
        col = f"bus{i}"
        if col not in L.columns:
            continue
        sel = L.index[L[col].isin(stored)]
        if sel.empty or f"p{i}" not in n.links_t or n.links_t[f"p{i}"].empty:
            continue
        cols = [c for c in sel if c in n.links_t[f"p{i}"].columns]
        if not cols:
            continue
        flow = (-n.links_t[f"p{i}"][cols]).clip(lower=0).mul(w, axis=0).sum() / 1e6
        for link, v in flow.items():
            car = L.at[link, "carrier"]
            if car == "DAC":
                out["DAC"] += v
            elif any(k.lower() in car.lower() for k in BIOGENIC_KEYS):
                out["biogenic CC"] += v
            elif car in ("co2 sequestered", "CO2 pipeline", "co2 stored"):
                continue
            else:
                out["fossil/process CC"] += v
    return out


def summarise(n, supply, co2_price, run, year):
    row = {"run": run, "year": year, "co2_price": co2_price}
    gc = n.global_constraints
    row["co2_limit_Mt"] = gc.at["CO2Limit", "constant"] / 1e6 if "CO2Limit" in gc.index else np.nan
    row["seq_limit_price"] = gc.at["co2_sequestration_limit", "mu"] if "co2_sequestration_limit" in gc.index else np.nan
    for label, carrier in CDR_TECHS:
        sub = supply[supply["tech"] == label] if not supply.empty else supply
        row[f"{label} potential Mt"] = sub["potential"].sum() / 1e6 if len(sub) else 0.0
        row[f"{label} deployed Mt"] = sub["deployed"].sum() / 1e6 if len(sub) else 0.0
    row.update({f"captured {k} Mt": v for k, v in captured_co2_by_source(n).items()})
    seq = n.stores[n.stores.carrier == "co2 sequestered"]
    injected = (n.stores_t.e[seq.index].iloc[-1] - seq["e_initial"]).sum() if len(seq) else 0.0
    row["sequestered Mt"] = injected / 1e6
    row["seq_limit_Mt"] = -gc.at["co2_sequestration_limit", "constant"] / 1e6 if "co2_sequestration_limit" in gc.index else np.nan
    return row


def plot_comparison(summary, out_path):
    runs = list(dict.fromkeys(summary["run"]))
    ncol = 3
    nrow = int(np.ceil(len(runs) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(18, 4.6 * nrow), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    removal = [(f"{l} deployed Mt", TECH_COLORS.get(c, "grey"), l) for l, c in CDR_TECHS]
    capture = [("captured DAC Mt", TECH_COLORS.get("DAC", "#ff5270"), "DAC (to storage)"),
               ("captured biogenic CC Mt", "#8a9a2a", "Biogenic CC (BECCS etc.)")]
    years_all = sorted(summary["year"].unique())
    price_max = summary["co2_price"].max() * 1.1
    twins = []
    for ax, run in zip(axes, runs):
        d = summary[summary["run"] == run].set_index("year").reindex(years_all)
        x = np.arange(len(years_all))
        bottom = np.zeros(len(x))
        for col, color, label in removal + capture:
            v = d[col].fillna(0).values
            ax.bar(x, v, bottom=bottom, color=color, width=0.65, label=label, edgecolor="white", lw=0.3)
            bottom += v
        for xi, yr in enumerate(years_all):
            if pd.isna(d.at[yr, "co2_price"]):
                ax.text(xi, 5, "not solved", rotation=90, ha="center", va="bottom", fontsize=8, color="dimgrey")
        ax.set_xticks(x, [str(y) for y in years_all])
        ax.set_title(run)
        ax.spines[["top"]].set_visible(False)
        t = ax.twinx()
        t.plot(x, d["co2_price"].values, color="black", marker="o", lw=1.5, label="CO2 price")
        t.set_ylim(0, price_max)
        twins.append(t)
    for ax in axes[len(runs):]:
        ax.set_visible(False)
    for i, ax in enumerate(axes[: len(runs)]):
        if i % ncol == 0:
            ax.set_ylabel("MtCO2/yr removed or captured to storage")
        if i % ncol != ncol - 1:
            twins[i].set_yticklabels([])
        else:
            twins[i].set_ylabel("CO2 price [EUR/tCO2]")
    h, l = axes[0].get_legend_handles_labels()
    h2, l2 = twins[0].get_legend_handles_labels()
    fig.legend(h + h2, l + l2, loc="lower center", ncol=7, frameon=False, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("CDR deployment and CO2 capture to storage by scenario and horizon", fontsize=14)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    results_root, out_dir, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, failed = [], []
    for run in runs:
        nets = sorted((results_root / run / "networks").glob("*.nc"))
        for path in nets:
            m = re.search(r"_(\d{4})\.nc$", path.name)
            if not m:
                continue
            year = int(m.group(1))
            print(f"{run} {year}: loading {path.name}", flush=True)
            n = pypsa.Network(str(path))
            try:
                supply, co2_price = build_supply(n)
            except Exception as e:  # keep the batch going; report at the end
                print(f"  !! {run} {year}: merit order failed: {e!r}", flush=True)
                failed.append(f"{run} {year}")
                supply, co2_price = pd.DataFrame(), co2_price_of(n)
            rundir = out_dir / "merit_order" / run
            rundir.mkdir(parents=True, exist_ok=True)
            if not supply.empty:
                supply.to_csv(rundir / f"merit_order_supply_{year}.csv", index=False)
                plot_merit_order(supply, co2_price, f"CDR merit order — {run}, {year}",
                                 rundir / f"CDR_merit_order_{run}_{year}.png")
            rows.append(summarise(n, supply, co2_price, run, year))
    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "cdr_summary.csv", index=False)
    plot_comparison(summary, out_dir / "cdr_deployment_by_scenario.png")
    print(f"Wrote {len(rows)} scenario-years to {out_dir}")
    if failed:
        print("Merit order FAILED for: " + ", ".join(failed))


if __name__ == "__main__":
    main()
