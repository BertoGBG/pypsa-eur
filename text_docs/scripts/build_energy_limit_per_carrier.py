"""
Plot the AS-IMPLEMENTED per-carrier energy-security limits: the actual
GlobalConstraint values (gas/oil/coal/lignite, via
add_energy_limit_per_carrier() in prepare_sector_network.py) and the solid
biomass import cap (sector.solid_biomass_import.max_amount), both now
computed via the self-sufficiency-fraction methodology documented in
text_docs/text/fossil_supply_security_methodology.md Section 6.

Unlike build_fossil_supply_security.py (which compares an AGGREGATE
fossil ceiling against three illustrative "100/80/60% by 2050" scenario
share targets, for the climate-vs-security discussion), this script plots
the REAL numbers now sitting in config/config.default.yaml, per carrier,
so the two can be visually cross-checked against each other.

Formula, per carrier: frac(year) = share_2020 + (target-share_2020) *
smoothstep((year-2020)/30); total_cap(year) = EU_safe_potential(year) /
frac(year), except for biomass where the domestic Generator is already
unconstrained by real land potential and only the IMPORT top-up is capped:
import_cap(year) = domestic_potential(year) * (1/frac(year) - 1).

Usage: python3 build_energy_limit_per_carrier.py [out_dir]
"""
import os
import sys
import yaml
import numpy as np
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

_config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "plotting.default.yaml"
)
with open(_config_path) as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]

YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
years_fine = np.linspace(2020, 2050, 121)

TARGET_SELF_SUFFICIENCY_2050 = 1.0  # 100% -- base-case scenario choice, see config comment

# ---------------------------------------------------------------------------
# Reuse the EU-safe potential curves from the sibling script (same source
# data, no duplication of the Norway/UK/coal/lignite sourcing).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_bfss_globals = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fossil_supply_security.py")}
with open(_bfss_globals["__file__"]) as f:
    _bfss_src = f.read()
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_bfss_src, _bfss_globals["__file__"], "exec"), _bfss_globals)

no_gas_energy_mwh = _bfss_globals["no_gas_energy_mwh"]
no_oil_energy_mwh = _bfss_globals["no_oil_energy_mwh"]
uk_gas_energy_mwh = _bfss_globals["uk_gas_energy_mwh"]
uk_oil_energy_mwh = _bfss_globals["uk_oil_energy_mwh"]
hard_coal_energy_mwh = _bfss_globals["hard_coal_energy_mwh"]
lignite_energy_mwh = _bfss_globals["lignite_energy_mwh"]
BIOMASS_POTENTIAL_TWH = _bfss_globals["BIOMASS_POTENTIAL_TWH"]

_biomass_table_years = sorted(BIOMASS_POTENTIAL_TWH)
_biomass_table_vals = [
    BIOMASS_POTENTIAL_TWH[y]["sustainable"] + BIOMASS_POTENTIAL_TWH[y]["unsustainable"]
    for y in _biomass_table_years
]


def _biomass_domestic_twh(year):
    # Table only has 2025-2050 points; clamp before 2025 (same convention
    # as the UK/Norway curves), interpolate linearly between table years.
    y = max(year, _biomass_table_years[0])
    return float(np.interp(y, _biomass_table_years, _biomass_table_vals))


EU_SAFE_TWH = {
    "gas": lambda y: (no_gas_energy_mwh(y) + uk_gas_energy_mwh(y)) / 1e6,
    "oil": lambda y: (no_oil_energy_mwh(y) + uk_oil_energy_mwh(y)) / 1e6,
    "coal": lambda y: hard_coal_energy_mwh(y) / 1e6,
    "lignite": lambda y: lignite_energy_mwh(y) / 1e6,
    "biomass": _biomass_domestic_twh,
}

INTENSITY_TCO2_MWH = {"gas": 0.198, "oil": 0.2571, "coal": 0.3361, "lignite": 0.4069}

# ---------------------------------------------------------------------------
# Real 2020 self-sufficiency fractions: EU-safe potential / real Eurostat
# GIC consumption (gas/oil), or domestic/consumption production split
# (coal/lignite, already sourced in the methodology doc Section 4.3), or
# domestic potential / (domestic potential + real extra-EU import) for
# biomass (see config comment for the 21.5 TWh 2024 pellet-import sourcing).
SHARE_2020 = {
    "gas": 1813.4 / 3887.5,
    "oil": 1268.7 / 5259.1,
    "coal": 380259 / 1052769,
    "lignite": 746533 / 762560,
    "biomass": 1609.3 / (1609.3 + 21.5),
}

REAL_CONSUMPTION_2020_TWH = {
    "gas": 3887.5,
    "oil": 5259.1,
    "coal": 1052769 / 1000,
    "lignite": 762560 / 1000,
}


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return 3 * x**2 - 2 * x**3


def frac_curve(year, carrier, target=TARGET_SELF_SUFFICIENCY_2050):
    x = (year - 2020) / 30
    return SHARE_2020[carrier] + (target - SHARE_2020[carrier]) * smoothstep(x)


def total_cap_fossil(year, carrier):
    return EU_SAFE_TWH[carrier](year) / frac_curve(year, carrier)


def biomass_import_cap(year):
    domestic = EU_SAFE_TWH["biomass"](year)
    frac = frac_curve(year, "biomass")
    return domestic * (1 / frac - 1)


# ---------------------------------------------------------------------------
# Figure 1: gas/oil/coal/lignite (2x2, top) -- EU-safe potential vs. total
# supply cap vs. self-sufficiency fraction -- then ONE combined solid-biomass
# panel (bottom, full width): domestic potential (left axis) and import cap
# (right axis, since it's ~80x smaller and would be invisible on a shared
# linear scale) plotted together in the same panel.
FOSSIL_CARRIERS = ["gas", "oil", "coal", "lignite"]
fig = plt.figure(figsize=(13, 12))
gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1])
fossil_axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]),
               fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]

for ax, carrier in zip(fossil_axes, FOSSIL_CARRIERS):
    color = TECH_COLORS.get(carrier, "tab:blue")
    safe_vals = [EU_SAFE_TWH[carrier](y) for y in years_fine]
    total_vals = [total_cap_fossil(y, carrier) for y in years_fine]
    ax.plot(years_fine, safe_vals, color=color, ls="--", lw=1.5, label="EU-safe potential (domestic-only)")
    ax.plot(years_fine, total_vals, color=color, ls="-", lw=2.5, label="Total supply cap (config value)")
    ax.scatter([2020], [REAL_CONSUMPTION_2020_TWH[carrier]], color="black", zorder=5, s=40,
               label="Real 2020 consumption (Eurostat)")
    for y in YEARS:
        ax.annotate(f"{total_cap_fossil(y, carrier):.0f}", (y, total_cap_fossil(y, carrier)),
                    textcoords="offset points", xytext=(0, 6), fontsize=7, ha="center")
    ax2 = ax.twinx()
    frac_vals = [100 * frac_curve(y, carrier) for y in years_fine]
    ax2.plot(years_fine, frac_vals, color="grey", ls=":", lw=1.5, label="Self-sufficiency fraction")
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Self-sufficiency [%]", color="grey", fontsize=8)
    ax.set_title(f"{carrier.capitalize()} (2020 self-sufficiency: {100*SHARE_2020[carrier]:.1f}%)")
    ax.set_ylabel("TWh/yr")
    ax.set_xlim(2020, 2050)
    ax.grid(alpha=0.3)
    if carrier == "gas":
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=7, loc="upper right")

ax_bio = fig.add_subplot(gs[2, :])
domestic_vals = [EU_SAFE_TWH["biomass"](y) for y in years_fine]
import_vals = [biomass_import_cap(y) for y in years_fine]
ln1 = ax_bio.plot(years_fine, domestic_vals, color=TECH_COLORS.get("solid biomass", "#baa741"), lw=2.5,
                    label="Domestic potential (sustainable+unsustainable, unconstrained; left axis)")
ax_bio.scatter([2025], [1609.3], color="black", zorder=5, s=40, label="Real 2025 domestic potential (model)")
for y in YEARS:
    ax_bio.annotate(f"{EU_SAFE_TWH['biomass'](y):.0f}", (y, EU_SAFE_TWH["biomass"](y)),
                     textcoords="offset points", xytext=(0, 8), fontsize=7, ha="center")
ax_bio.set_ylabel("Domestic potential [TWh/yr]")
ax_bio.set_ylim(0, 1750)
ax_bio.set_xlim(2020, 2050)
ax_bio.grid(alpha=0.3)

ax_bio2 = ax_bio.twinx()
ln2 = ax_bio2.plot(years_fine, import_vals, color=TECH_COLORS.get("solid biomass import", "#d5ca8d"), lw=2.5,
                     label="Import cap (solid_biomass_import.max_amount; right axis)")
ax_bio2.scatter([2025], [21.5], color="black", marker="s", zorder=5, s=40,
                 label="Real 2024 extra-EU pellet imports (USDA FAS)")
for y in YEARS:
    ax_bio2.annotate(f"{biomass_import_cap(y):.1f}", (y, biomass_import_cap(y)),
                      textcoords="offset points", xytext=(0, -12), fontsize=7, ha="center", color="#8a7d3a")
ax_bio2.set_ylabel("Import cap [TWh/yr]", color="#8a7d3a")
ax_bio2.set_ylim(0, 25)

ax_bio.set_title(
    f"Solid biomass: domestic potential + import cap "
    f"(2020 self-sufficiency: {100*SHARE_2020['biomass']:.1f}% -> 100% by 2050)"
)
lines = ln1 + ln2
labels = [l.get_label() for l in lines]
handles2, labels2 = ax_bio.get_legend_handles_labels()
handles3, labels3 = ax_bio2.get_legend_handles_labels()
ax_bio.legend(handles2 + handles3, labels2 + labels3, fontsize=7.5, loc="lower left")

fig.suptitle(
    f"Per-carrier energy-security supply caps -- self-sufficiency-fraction methodology\n"
    f"(target: {100*TARGET_SELF_SUFFICIENCY_2050:.0f}% self-sufficient by 2050, shared across all carriers)",
    fontsize=12,
)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(f"{out_dir}/energy_limit_per_carrier.png", dpi=150)
plt.close(fig)
print(f"Saved {out_dir}/energy_limit_per_carrier.png")

# ---------------------------------------------------------------------------
# Figure 2: all carriers stacked -- the combined "total energy-security-
# capped supply" picture, gas+oil+coal+lignite total caps (MtCO2-eq, primary
# axis) plus the biomass import cap (TWh, not CO2-comparable -- shown as a
# separate thin line on its own small-scale right axis rather than stacked
# into the same CO2 total, to avoid mixing energy and emissions units).
fig, ax = plt.subplots(figsize=(11, 6.5))
stack_vals = {c: [total_cap_fossil(y, c) * INTENSITY_TCO2_MWH[c] for y in YEARS] for c in FOSSIL_CARRIERS}
bottoms = np.zeros(len(YEARS))
for c in FOSSIL_CARRIERS:
    vals = np.array(stack_vals[c])
    ax.bar(YEARS, vals, bottom=bottoms, width=3, label=f"{c.capitalize()} (MtCO2-eq)",
           color=TECH_COLORS.get(c, "tab:blue"))
    for i, y in enumerate(YEARS):
        if vals[i] > 30:
            ax.text(y, bottoms[i] + vals[i] / 2, f"{vals[i]:.0f}", ha="center", va="center", fontsize=7)
    bottoms += vals
for i, y in enumerate(YEARS):
    ax.text(y, bottoms[i] + 20, f"{bottoms[i]:.0f}", ha="center", fontsize=8, fontweight="bold")
ax.set_ylabel("Total per-carrier supply cap [MtCO2-eq/yr]")
ax.set_xlabel("Year")
ax.set_xlim(2022, 2053)
ax.set_title(
    f"All carriers, stacked -- energy_limit_per_carrier resolved values\n"
    f"(target: {100*TARGET_SELF_SUFFICIENCY_2050:.0f}% self-sufficient by 2050; "
    f"biomass import cap shown separately, right axis, since it's TWh not MtCO2-eq)"
)

ax2 = ax.twinx()
import_vals_years = [biomass_import_cap(y) for y in YEARS]
ax2.plot(YEARS, import_vals_years, color=TECH_COLORS.get("solid biomass import", "#d5ca8d"),
          marker="o", lw=2, label="Solid biomass import cap (TWh)")
ax2.set_ylabel("Solid biomass import cap [TWh/yr]", color="#8a7d3a")
ax2.set_ylim(0, 25)

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")
fig.tight_layout()
fig.savefig(f"{out_dir}/energy_limit_per_carrier_stacked.png", dpi=150)
plt.close(fig)
print(f"Saved {out_dir}/energy_limit_per_carrier_stacked.png")

# ---------------------------------------------------------------------------
print("\n=== Resolved config values (cross-check against config.default.yaml) ===")
for carrier in FOSSIL_CARRIERS:
    print(f"\n{carrier}:")
    for y in YEARS:
        twh = total_cap_fossil(y, carrier)
        mtco2 = twh * INTENSITY_TCO2_MWH[carrier]
        print(f"  {y}: {twh:.1f} TWh -> {mtco2:.1f} MtCO2-eq")
print("\nsolid_biomass_import.max_amount:")
for y in YEARS:
    print(f"  {y}: {biomass_import_cap(y):.1f} TWh")
