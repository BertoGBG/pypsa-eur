"""
Build the three stacked-area plots from analyze_run.py's CSV outputs.
Usage: python3 make_plots.py <csv_prefix> <run_label> <out_dir>
"""
import os
import sys
import yaml
import pandas as pd
import matplotlib.pyplot as plt

prefix, label, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]

# --- pull this fork's own tech_colors so custom plots use the same palette
# as pypsa-eur's native plots (costs.pdf, plot_power_network, etc.) instead
# of an arbitrary colormap. Falls back to tab20-by-position for any carrier
# not in the official dict (there shouldn't be many).
_config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config", "plotting.default.yaml"
)
with open(_config_path) as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]
_fallback_cmap = plt.get_cmap("tab20")


def tech_color(carrier, fallback_index=0):
    return TECH_COLORS.get(carrier, _fallback_cmap(fallback_index % 20))


FOSSIL_COLORS = {c: tech_color(c) for c in ["oil", "gas", "coal"]}
FUEL_COLORS = {**FOSSIL_COLORS, "biomass": tech_color("solid biomass")}

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
ax1.plot(df.index, df["CO2Limit_tCO2"], color="black", lw=2, ls="--", label="CO2Limit (enforced)")
if "LULUCF_delta_tCO2" in df.columns and df["LULUCF_delta_tCO2"].abs().max() > 0:
    ax1.plot(df.index, df["LULUCF_delta_tCO2"], color="#2e7d32", lw=1.5, ls="-.", marker="^",
              label="LULUCF deviation (budget tightening, MtCO2/yr)")
ax1.plot(df.index, df["FossilLimit_tCO2"], color="tab:red", lw=2, ls=":",
          label="Fossil fuel limit (config, medium scenario; NOT enforced)")
ax1.plot(df.index, df["FossilSupplyLimit80_tCO2"], color="tab:purple", lw=2, ls=":", marker="s",
          label="Fossil supply limit (80% EU security, no coal; NOT enforced)")
ax1.legend(loc="upper right", fontsize=8)
ax1.set_title(f"Fossil fuel CO2 by carrier vs CO2 limit — {label}")
fig.tight_layout()
fig.savefig(f"{out_dir}/{label}_1_fossil_co2.png", dpi=150)
plt.close(fig)

# --- Plot 2: total fuel MWh, stacked by fuel (oil/gas/coal/biomass), + CO2Limit ---
# CO2 (MtCO2/yr) always on the LEFT axis, fuel (TWh/yr) on the right, so
# both plots 1 and 2 keep emissions on the same side for easy comparison.
df2 = pd.read_csv(f"{prefix}_total_fuel_mwh.csv", index_col=0) / 1e6  # -> TWh (CO2 cols fixed below)
fig, ax_co2 = plt.subplots(figsize=(8, 5))
ax_co2.plot(df2.index, df2["CO2Limit_tCO2"], color="black", lw=2, ls="--", label="CO2Limit (enforced)")
if "LULUCF_delta_tCO2" in df2.columns and df2["LULUCF_delta_tCO2"].abs().max() > 0:
    ax_co2.plot(df2.index, df2["LULUCF_delta_tCO2"], color="#2e7d32", lw=1.5, ls="-.", marker="^",
                 label="LULUCF deviation (budget tightening, MtCO2/yr)")
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
    label="Fossil fuel limit (config, medium scenario; NOT enforced)",
)
ax_fuel.plot(
    df2.index, df2["FossilSupplyLimit80_MWh"], color="tab:purple", lw=2, ls=":", marker="s",
    label="Fossil supply limit (80% EU security, no coal; NOT enforced)",
)
ax_fuel.set_ylabel("Fuel injected (TWh/yr)")
lines1, labels1 = ax_co2.get_legend_handles_labels()
lines2, labels2 = ax_fuel.get_legend_handles_labels()
ax_co2.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)
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
fig, ax = plt.subplots(figsize=(13, 6.5))
colors = {c: tech_color(c, fallback_index=i) for i, c in enumerate(df3.columns)}
ax.stackplot(pos.index, [pos[c] for c in pos.columns], colors=[colors[c] for c in pos.columns], alpha=0.85)
ax.stackplot(neg.index, [neg[c] for c in neg.columns], colors=[colors[c] for c in neg.columns], alpha=0.85)
ax.axhline(0, color="black", lw=0.8)
handles = [plt.Rectangle((0, 0), 1, 1, color=colors[c]) for c in df3.columns]

# CO2 shadow price (CO2Limit dual, EUR/tCO2) on the first right-side axis --
# same extraction convention as scripts/plot_CDR_merit_order.py (a_CDRs).
price_handles, price_labels = [], []
try:
    price = pd.read_csv(f"{prefix}_co2_price.csv", index_col=0).iloc[:, 0]
except FileNotFoundError:
    price = None
if price is not None:
    ax_price = ax.twinx()
    ax_price.plot(price.index, price.values, "D-", color="black", lw=1.2,
                   markersize=6, label="CO2 price (EUR/tCO2)")
    ax_price.set_ylabel("CO2 shadow price (EUR/tCO2)")
    price_handles, price_labels = ax_price.get_legend_handles_labels()

# Exogenous CO2Limit (MtCO2, same units as the left axis's balance terms
# but a different KIND of quantity -- a constraint bound, not a balance
# term that nets to ~0 by construction) on a SECOND right-side axis, offset
# outward so it doesn't overlap the price axis's tick labels.
limit_handles, limit_labels = [], []
try:
    limit_series = pd.read_csv(f"{prefix}_fossil_co2_by_carrier.csv", index_col=0)["CO2Limit_tCO2"] / 1e6
    ax_limit = ax.twinx()
    ax_limit.spines["right"].set_position(("outward", 85))
    ax_limit.plot(limit_series.index, limit_series.values, "o--", color="tab:purple", lw=1.5,
                   markersize=5, label="Exogenous CO2Limit (MtCO2/yr)")
    ax_limit.set_ylabel("Exogenous CO2Limit (MtCO2/yr)")
    limit_handles, limit_labels = ax_limit.get_legend_handles_labels()
except (FileNotFoundError, KeyError):
    pass

ax.legend(handles + price_handles + limit_handles,
           list(df3.columns) + price_labels + limit_labels,
           loc="center left", bbox_to_anchor=(1.22, 0.5), fontsize=7)
ax.set_xlabel("Year")
ax.set_ylabel("CO2 balance term (MtCO2/yr)")
ax.set_title(f"CO2-atmosphere-bus balance by term — {label}")
fig.subplots_adjust(left=0.07, right=0.68, top=0.93, bottom=0.09)
fig.savefig(f"{out_dir}/{label}_3_co2_balance_terms.png", dpi=150)
plt.close(fig)

print("done:", label)
