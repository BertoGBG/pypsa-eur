"""
Build a co2_balance_terms-style stacked plot of total system cost by
carrier, across the myopic horizon, from pypsa-eur's own already-computed
per-carrier cost summary (results/<run>/csvs/costs.csv -- capital+marginal
cost per (component, carrier) per planning_horizon, produced by the
existing make_summary rule; no new network access needed).

Usage: python3 plot_cost_breakdown.py <costs_csv> <run_label> <out_dir>
"""
import sys
import pandas as pd
import matplotlib.pyplot as plt

costs_csv, label, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]

# --- load and reshape: pypsa-eur's own csvs/costs.csv has 3 metadata rows
# (cluster/opt/planning_horizon) followed by a header row (cost,component,
# carrier,,,,,,) then data -- not a standard pandas MultiIndex CSV.
with open(costs_csv) as f:
    header_lines = [f.readline() for _ in range(4)]
years = [int(y) for y in header_lines[2].strip().split(",")[3:]]

raw = pd.read_csv(costs_csv, skiprows=3, header=0, index_col=[0, 1, 2])
raw.columns = years
raw = raw.apply(pd.to_numeric, errors="coerce").fillna(0.0)

# sum capital + marginal per carrier (drop the cost/component split)
by_carrier = raw.groupby(level="carrier").sum() / 1e9  # -> billion EUR/yr

# drop negligible carriers for legibility (matches plot_summary's own
# "drop technology with costs below 1 EUR billion per year" convention)
keep = by_carrier.index[by_carrier.abs().max(axis=1) > 1.0]
by_carrier = by_carrier.loc[keep].sort_index(axis=1)

by_carrier.to_csv(f"{out_dir}/{label}_cost_breakdown_by_carrier.csv")

# --- plot: stacked area, positive/negative split (a cost can be negative
# e.g. heat-pump COP-driven negative marginal costs), tab20 colours,
# legend outside -- same visual convention as plot 3 (co2_balance_terms) ---
pos = by_carrier.clip(lower=0)
neg = by_carrier.clip(upper=0)
years = by_carrier.columns.tolist()

fig, ax = plt.subplots(figsize=(11, 6.5))
cmap = plt.get_cmap("tab20")
colors = {c: cmap(i % 20) for i, c in enumerate(by_carrier.index)}
ax.stackplot(years, [pos.loc[c] for c in pos.index], colors=[colors[c] for c in pos.index], alpha=0.85)
ax.stackplot(years, [neg.loc[c] for c in neg.index], colors=[colors[c] for c in neg.index], alpha=0.85)
ax.axhline(0, color="black", lw=0.8)
handles = [plt.Rectangle((0, 0), 1, 1, color=colors[c]) for c in by_carrier.index]
ax.legend(handles, by_carrier.index, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7)
ax.set_xlabel("Year")
ax.set_ylabel("System cost (billion EUR/yr)")
ax.set_title(f"Total system cost by carrier — {label}")
fig.tight_layout()
fig.savefig(f"{out_dir}/{label}_cost_breakdown_by_carrier.png", dpi=150)
plt.close(fig)

print(f"Saved {out_dir}/{label}_cost_breakdown_by_carrier.png")
print(f"Saved {out_dir}/{label}_cost_breakdown_by_carrier.csv")
print(f"\nTotal system cost (billion EUR/yr) by year:\n{by_carrier.sum().round(1)}")
