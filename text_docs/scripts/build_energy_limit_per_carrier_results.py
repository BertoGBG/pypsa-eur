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
TOTAL_CAP_MTCO2 = _g["TOTAL_CAP_MTCO2"]
INTENSITY_TCO2_MWH = _g["INTENSITY_TCO2_MWH"]
BIOMASS_IMPORT_CO2_INTENSITY = _g["BIOMASS_IMPORT_CO2_INTENSITY"]
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
    # Real emitted MtCO2-eq: fossil carriers at their standard wellhead
    # intensity (same convention as the design-side cap, so dispatch and
    # cap are directly comparable in the same units); biomass = import
    # share only, at its real upstream charge -- domestic biomass carries
    # no CO2 charge in this model (verified in code, see methodology doc
    # Section 5.1), so it contributes zero here regardless of volume.
    row_mtco2 = {c: row[c] * INTENSITY_TCO2_MWH[c] for c in FOSSIL_CARRIERS}
    row_mtco2["biomass"] = import_disp * BIOMASS_IMPORT_CO2_INTENSITY
    row["_mtco2"] = row_mtco2
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
# Two panels: left = actual dispatched TWh, right = actual emitted MtCO2-eq
# (biomass = import share only, since domestic biomass carries no CO2
# charge in this model -- see the row_mtco2 comment above). Right axis on
# both panels: cap utilization per carrier, labeled "Self-sufficiency [%]"
# for consistency with the design-side figure's axis naming -- note this
# is still utilization (dispatch/cap), not a separately-modeled realized
# self-sufficiency (the model doesn't track domestic-vs-import origin for
# the fossil carriers, only for biomass, so a true achieved-self-sufficiency
# metric isn't computable for gas/oil/coal/lignite from the solve).
fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(18, 8.2))
legend_handles, legend_labels = None, None

for ax, unit, value_key, cap_fn in [
    (ax_l, "TWh/yr", None, TOTAL_CAP_TWH),
    (ax_r, "MtCO2-eq/yr", "_mtco2", TOTAL_CAP_MTCO2),
]:
    def get_val(y, c):
        return results[y][c] if value_key is None else results[y][value_key][c]

    bottoms = np.zeros(len(YEARS))
    stack_vals = {c: np.array([get_val(y, c) for y in YEARS]) for c in ALL_CARRIERS}
    top_est = sum(stack_vals[c] for c in ALL_CARRIERS).max() * 1.15
    label_thresh = 0.005 * top_est
    for c in ALL_CARRIERS:
        color = TECH_COLORS.get(c if c != "biomass" else "solid biomass", "tab:blue")
        vals = stack_vals[c]
        ax.bar(YEARS, vals, bottom=bottoms, width=3, label=f"{c.capitalize()}", color=color)
        for i, y in enumerate(YEARS):
            if vals[i] > label_thresh:
                ax.text(y, bottoms[i] + vals[i] / 2, f"{vals[i]:.0f}", ha="center", va="center", fontsize=7)
        bottoms += vals
    top = bottoms.max() * 1.15
    for i, y in enumerate(YEARS):
        ax.text(y, bottoms[i] + 0.012 * top, f"{bottoms[i]:.0f}", ha="center", fontsize=8, fontweight="bold")
    ax.set_ylabel(f"Actual dispatched supply [{unit}]")
    ax.set_xlabel("Year")
    ax.set_xlim(min(YEARS) - 3, max(YEARS) + 3)
    ax.set_ylim(0, top)

    ax2 = ax.twinx()
    for c in ALL_CARRIERS:
        color = TECH_COLORS.get(c if c != "biomass" else "solid biomass", "tab:blue")
        util_vals = [100 * results[y][c] / TOTAL_CAP_TWH[c](y) for y in YEARS]
        ax2.plot(YEARS, util_vals, color=color, ls=":", marker="o", lw=2, ms=5,
                 label=f"{c.capitalize()} self-sufficiency")
    ax2.set_ylabel("Self-sufficiency [%]")
    ax2.set_ylim(0, 110)
    ax2.axhline(100, color="grey", lw=0.8, ls="--", alpha=0.5)

    if legend_handles is None:
        handles_bar, labels_bar = ax.get_legend_handles_labels()
        handles_line, labels_line = ax2.get_legend_handles_labels()
        legend_handles = handles_bar + handles_line
        legend_labels = labels_bar + labels_line

ax_l.set_title("Left: TWh/yr")
ax_r.set_title("Right: MtCO2-eq/yr (biomass = import share only; domestic biomass carries no CO2 charge)")
fig.suptitle(
    "All carriers, stacked -- ACTUAL SOLVED DISPATCH\n"
    "(right axis: cap utilization per carrier, both panels -- 100% = constraint fully binding)",
    fontsize=12,
)

fig.legend(legend_handles, legend_labels, fontsize=8, loc="lower center",
           bbox_to_anchor=(0.5, 0.0), ncol=5, frameon=False)
fig.tight_layout(rect=(0, 0.11, 1, 0.94))
fig.savefig(f"{out_dir}/energy_limit_per_carrier_results_stacked.png", dpi=150)
plt.close(fig)
print(f"\nSaved {out_dir}/energy_limit_per_carrier_results_stacked.png")
