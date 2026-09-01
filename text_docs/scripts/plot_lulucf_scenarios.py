"""
Plot the three LULUCF-deviation scenarios documented in
text_docs/text/lulucf_deviation_methodology.md.

Usage: python3 plot_lulucf_scenarios.py [out_dir]
"""
import sys
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

# MtCO2/yr deviation from the flat -310 MtCO2e/yr 2030 target held as the
# reference for all years (see methodology doc section 1 for why).
SCENARIOS = {
    "BAU / central (WEM trend continuation)": {
        2020: 0, 2025: 64, 2030: 127, 2035: 191, 2040: 254, 2045: 318, 2050: 381,
    },
    "Optimistic - weak new policy (EC S1)": {
        2020: 0, 2025: 64, 2030: 127, 2035: 127, 2040: 127, 2045: 127, 2050: 127,
    },
    "Optimistic - strong new policy (EC S3)": {
        2020: 0, 2025: 39, 2030: 77, 2035: 0, 2040: 0, 2045: 0, 2050: 0,
    },
}
COLORS = {
    "BAU / central (WEM trend continuation)": "#8c1d1d",
    "Optimistic - weak new policy (EC S1)": "#d9822b",
    "Optimistic - strong new policy (EC S3)": "#2b7a4b",
}

fig, ax = plt.subplots(figsize=(8, 5))
for label, series in SCENARIOS.items():
    years = sorted(series)
    ax.plot(years, [series[y] for y in years], marker="o", lw=2, label=label, color=COLORS[label])

ax.axhline(0, color="black", lw=0.8, ls=":")
ax.set_xlabel("Year")
ax.set_ylabel("lulucf_deviation_values (MtCO2/yr)\npositive = CO2Limit tightened, negative = loosened")
ax.set_title("LULUCF sink deviation from flat 2030 target (-310 MtCO2e/yr)")
ax.legend(loc="upper right", fontsize=9)
fig.tight_layout()
fig.savefig(f"{out_dir}/lulucf_deviation_scenarios.png", dpi=150)
print(f"Saved {out_dir}/lulucf_deviation_scenarios.png")
