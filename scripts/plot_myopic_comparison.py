"""
Build the three stacked-area plots from analyze_run.py's CSV outputs.
Usage: python3 make_plots.py <csv_prefix> <run_label> <out_dir>
"""
import sys
import pandas as pd
import matplotlib.pyplot as plt

prefix, label, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]

FOSSIL_COLORS = {"oil": "#4d4d4d", "gas": "#d9822b", "coal": "#8c1d1d"}

# --- Plot 1: fossil CO2 by carrier, stacked area, + CO2Limit line ---
df = pd.read_csv(f"{prefix}_fossil_co2_by_carrier.csv", index_col=0) / 1e6  # -> MtCO2
fig, ax1 = plt.subplots(figsize=(8, 5))
ax1.stackplot(
    df.index,
    df["oil"], df["gas"], df["coal"],
    labels=["oil", "gas", "coal"],
    colors=[FOSSIL_COLORS["oil"], FOSSIL_COLORS["gas"], FOSSIL_COLORS["coal"]],
    alpha=0.85,
)
ax1.set_xlabel("Year")
ax1.set_ylabel("Fossil CO2 emissions (MtCO2/yr)")
ax1.plot(df.index, df["total"], color="tab:blue", lw=2, marker="o", label="Total fossil CO2 (oil+gas+coal)")
ax1.plot(df.index, df["CO2Limit_tCO2"], color="black", lw=2, ls="--", label="CO2Limit")
ax1.plot(df.index, df["FossilLimit_tCO2"], color="tab:red", lw=2, ls=":", label="Fossil fuel limit (config; NOT enforced this run)")
ax1.legend(loc="upper right")
ax1.set_title(f"Fossil fuel CO2 by carrier vs CO2 limit — {label}")
fig.tight_layout()
fig.savefig(f"{out_dir}/{label}_1_fossil_co2.png", dpi=150)
plt.close(fig)

# --- Plot 2: total fuel MWh, stacked by fuel (oil/gas/coal/biomass), + CO2Limit ---
# CO2 (MtCO2/yr) always on the LEFT axis, fuel (TWh/yr) on the right, so
# both plots 1 and 2 keep emissions on the same side for easy comparison.
df2 = pd.read_csv(f"{prefix}_total_fuel_mwh.csv", index_col=0) / 1e6  # -> TWh (CO2Limit col fixed below)
FUEL_COLORS = {"oil": FOSSIL_COLORS["oil"], "gas": FOSSIL_COLORS["gas"], "coal": FOSSIL_COLORS["coal"], "biomass": "#4a8c3a"}
fig, ax_co2 = plt.subplots(figsize=(8, 5))
ax_co2.plot(df2.index, df2["CO2Limit_tCO2"], color="black", lw=2, ls="--", label="CO2Limit")
ax_co2.set_xlabel("Year")
ax_co2.set_ylabel("CO2Limit (MtCO2/yr)")
ax_fuel = ax_co2.twinx()
ax_fuel.stackplot(
    df2.index,
    df2["oil"], df2["gas"], df2["coal"], df2["biomass"],
    labels=["oil", "gas", "coal", "biomass"],
    colors=[FUEL_COLORS[f] for f in ["oil", "gas", "coal", "biomass"]],
    alpha=0.85,
)
ax_fuel.plot(
    df2.index, df2["FossilLimit_MWh"], color="tab:red", lw=2, ls=":",
    label="Fossil fuel limit (implied energy; NOT enforced this run)",
)
ax_fuel.set_ylabel("Fuel injected (TWh/yr)")
lines1, labels1 = ax_co2.get_legend_handles_labels()
lines2, labels2 = ax_fuel.get_legend_handles_labels()
ax_co2.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
ax_co2.set_title(f"Total fossil+biomass energy vs CO2 limit — {label}")
ax_co2.set_zorder(ax_fuel.get_zorder() + 1)
ax_co2.patch.set_visible(False)
fig.tight_layout()
fig.savefig(f"{out_dir}/{label}_2_total_fuel.png", dpi=150)
plt.close(fig)

# --- Plot 3: CO2 balance terms, stacked area (positive and negative) ---
df3 = pd.read_csv(f"{prefix}_co2_balance_terms.csv", index_col=0).fillna(0) / 1e6  # -> MtCO2
# drop near-zero-everywhere columns for legibility
keep = df3.columns[df3.abs().max() > 0.5]
df3 = df3[keep]
pos = df3.clip(lower=0)
neg = df3.clip(upper=0)
fig, ax = plt.subplots(figsize=(10, 6))
cmap = plt.get_cmap("tab20")
colors = {c: cmap(i % 20) for i, c in enumerate(df3.columns)}
ax.stackplot(pos.index, [pos[c] for c in pos.columns], colors=[colors[c] for c in pos.columns], alpha=0.85)
ax.stackplot(neg.index, [neg[c] for c in neg.columns], colors=[colors[c] for c in neg.columns], alpha=0.85)
ax.axhline(0, color="black", lw=0.8)
handles = [plt.Rectangle((0, 0), 1, 1, color=colors[c]) for c in df3.columns]
ax.legend(handles, df3.columns, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7)
ax.set_xlabel("Year")
ax.set_ylabel("CO2 balance term (MtCO2/yr)")
ax.set_title(f"CO2-atmosphere-bus balance by term — {label}")
fig.tight_layout()
fig.savefig(f"{out_dir}/{label}_3_co2_balance_terms.png", dpi=150)
plt.close(fig)

print("done:", label)
