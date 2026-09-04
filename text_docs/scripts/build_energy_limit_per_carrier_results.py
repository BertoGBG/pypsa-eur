"""
Results-side analogue of energy_limit_per_carrier_stacked.png: instead of
the theoretical config caps, this reads ACTUAL solved networks and plots
what the optimizer really dispatched for each capped carrier -- so the two
figures can be compared side by side (design ceiling vs. realized outcome).

Usage: python3 build_energy_limit_per_carrier_results.py <out_dir> <network1.nc> [<network2.nc> ...]

Each network's filename must contain the planning_horizons year (e.g.
"..._2030.nc") so it can be matched against the resolved config values
(pulled from build_fossil_supply_security.py + this fork's config, same as
the design-side companion script -- not read from config.default.yaml
directly, to avoid a yaml dependency here).
"""
import os
import re
import sys
import yaml
import numpy as np
import pypsa
import matplotlib.pyplot as plt

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

out_dir = sys.argv[1]
network_paths = sys.argv[2:]

_config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "plotting.default.yaml"
)
with open(_config_path) as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]

# ---------------------------------------------------------------------------
# Reuse the exact same resolved-cap formulas as the design-side script, so
# the "cap" reference line here is guaranteed consistent with
# energy_limit_per_carrier_stacked.png -- no re-derivation, no drift.
_sibling = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_energy_limit_per_carrier.py")
import io, contextlib
_g = {"__file__": _sibling}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(open(_sibling).read(), _sibling, "exec"), _g)

TOTAL_CAP_TWH = _g["TOTAL_CAP_TWH"]
biomass_import_cap = _g["biomass_import_cap"]
ALL_CARRIERS = _g["ALL_CARRIERS"]
FOSSIL_CARRIERS = _g["FOSSIL_CARRIERS"]

FOSSIL_GEN_CARRIERS = {"gas": ["gas"], "oil": ["oil", "oil primary"], "coal": ["coal"], "lignite": ["lignite"]}


def extract_year(path):
    m = re.search(r"_(\d{4})\.nc$", path)
    if not m:
        raise ValueError(f"Could not find a 4-digit year in filename: {path}")
    return int(m.group(1))


def gen_dispatch_twh(n, wt, carriers):
    gens = n.generators[n.generators.carrier.isin(carriers)]
    if gens.empty:
        return 0.0
    return float((n.generators_t.p[gens.index].mul(wt, axis=0)).sum().sum() / 1e6)


results = {}  # year -> {carrier: dispatch_twh}
for path in sorted(network_paths, key=extract_year):
    year = extract_year(path)
    n = pypsa.Network(path)
    wt = n.snapshot_weightings.generators
    row = {}
    for carrier, gen_carriers in FOSSIL_GEN_CARRIERS.items():
        row[carrier] = gen_dispatch_twh(n, wt, gen_carriers)
    domestic = gen_dispatch_twh(n, wt, ["solid biomass", "unsustainable solid biomass"])
    imp_links = n.links[n.links.carrier == "solid biomass import"]
    import_disp = 0.0
    if not imp_links.empty:
        import_disp = float((n.links_t.p0[imp_links.index].mul(wt, axis=0)).sum().sum() / 1e6)
    row["biomass"] = domestic + import_disp
    row["_biomass_domestic"] = domestic
    row["_biomass_import"] = import_disp
    gc = n.global_constraints
    row["_mu"] = {
        c: float(gc.at[f"energy_limit_security_{c}", "mu"])
        if f"energy_limit_security_{c}" in gc.index else None
        for c in FOSSIL_CARRIERS
    }
    results[year] = row

YEARS = sorted(results)
print("=== Extracted real dispatch [TWh/yr] ===")
for y in YEARS:
    print(f"\n{y}:")
    for c in ALL_CARRIERS:
        cap = TOTAL_CAP_TWH[c](y)
        disp = results[y][c]
        util = 100 * disp / cap if cap > 0 else float("nan")
        print(f"  {c}: dispatch={disp:.1f}  cap={cap:.1f}  utilization={util:.1f}%")

# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 8.2))
bottoms = np.zeros(len(YEARS))
for c in ALL_CARRIERS:
    color = TECH_COLORS.get(c if c != "biomass" else "solid biomass", "tab:blue")
    vals = np.array([results[y][c] for y in YEARS])
    ax.bar(YEARS, vals, bottom=bottoms, width=3, label=f"{c.capitalize()}", color=color)
    for i, y in enumerate(YEARS):
        if vals[i] > 60:
            ax.text(y, bottoms[i] + vals[i] / 2, f"{vals[i]:.0f}", ha="center", va="center", fontsize=7)
    bottoms += vals
for i, y in enumerate(YEARS):
    ax.text(y, bottoms[i] + 150, f"{bottoms[i]:.0f}", ha="center", fontsize=8, fontweight="bold")
ax.set_ylabel("Actual dispatched supply [TWh/yr]")
ax.set_xlabel("Year")
ax.set_xlim(min(YEARS) - 3, max(YEARS) + 3)
ax.set_ylim(0, max(bottoms) * 1.15)
ax.set_title(
    "All carriers, stacked -- ACTUAL SOLVED DISPATCH\n"
    "(right axis: cap utilization per carrier -- 100% = constraint fully binding)"
)

ax2 = ax.twinx()
for c in ALL_CARRIERS:
    color = TECH_COLORS.get(c if c != "biomass" else "solid biomass", "tab:blue")
    util_vals = [100 * results[y][c] / TOTAL_CAP_TWH[c](y) for y in YEARS]
    ax2.plot(YEARS, util_vals, color=color, ls=":", marker="o", lw=2, ms=5,
             label=f"{c.capitalize()} cap utilization")
ax2.set_ylabel("Cap utilization [%]")
ax2.set_ylim(0, 110)
ax2.axhline(100, color="grey", lw=0.8, ls="--", alpha=0.5)

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
fig.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="lower center",
           bbox_to_anchor=(0.5, 0.0), ncol=5, frameon=False)
fig.tight_layout(rect=(0, 0.11, 1, 1))
fig.savefig(f"{out_dir}/energy_limit_per_carrier_results_stacked.png", dpi=150)
plt.close(fig)
print(f"\nSaved {out_dir}/energy_limit_per_carrier_results_stacked.png")
