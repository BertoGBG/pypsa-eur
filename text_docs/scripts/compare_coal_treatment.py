"""
Compare three treatments of coal in the "European-safe" fossil-supply
ceiling (Norway + UK + coal), documented in
text_docs/text/fossil_supply_security_methodology.md Section 4.3:

1. "No coal" (old version): ceiling = Norway + UK gas+oil only.
2. "With coal" (corrected): ceiling = Norway + UK + domestic coal+lignite
   PRODUCTION (not consumption -- see the correction note below), held
   flat at 2020 level.
3. "With coal phase-out": same domestic coal+lignite base, but each
   producing country's contribution steps to zero at its own phase-out
   year (Poland overridden to 2035 per instruction, vs. its real 2049
   target).

CORRECTION vs. the original "with coal" draft: that version used Eurostat
Gross Inland CONSUMPTION (GIC) of all solid fossil fuels, which counts
imported hard coal as if it were domestic supply. Hard coal is ~64%
imported in this country scope (2020: 1,052,769 GWh consumed vs. only
380,259 GWh domestically produced) -- import dependent, not secure by this
document's own definition. Lignite, by contrast, is ~100% domestic (2020:
762,560 GWh consumed vs. 746,533 GWh produced -- lignite's low energy
density makes it uneconomical to transport/import). So the corrected
"domestic-safe" coal figure uses PRODUCTION, split into hard coal (0.3361
tCO2/MWh) and lignite (0.4069 tCO2/MWh) with their own model intensities,
not consumption with one blended rate.

Usage: python3 compare_coal_treatment.py [out_dir]
"""
import sys
import numpy as np
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

YEARS = [2020, 2025, 2030, 2035, 2040, 2045, 2050]
GRID = YEARS  # phase-out years get rounded onto this same 5-year grid

# ---------------------------------------------------------------------------
# Norway + UK (unchanged from build_fossil_supply_security.py -- see that
# script's comments for full sourcing).
NO_SCM_OE = {2025: 243, 2030: 215, 2035: 160, 2050: 83}
SCM_OE_TO_MWH = 9.9
NO_BLENDED_INTENSITY = 0.22
no_years_reported = sorted(NO_SCM_OE)

def no_mtco2(year):
    if year in NO_SCM_OE:
        scm = NO_SCM_OE[year]
    elif year > max(no_years_reported):
        scm = NO_SCM_OE[max(no_years_reported)]
    elif year < min(no_years_reported):
        scm = NO_SCM_OE[min(no_years_reported)]
    else:
        lo = max(y for y in no_years_reported if y <= year)
        hi = min(y for y in no_years_reported if y >= year)
        scm = NO_SCM_OE[lo] + (NO_SCM_OE[hi] - NO_SCM_OE[lo]) * (year - lo) / (hi - lo)
    return scm * SCM_OE_TO_MWH * NO_BLENDED_INTENSITY

BOE_TO_MWH = 1.7
TONNE_OIL_TO_MWH = 11.63
UK_E0_TWH = 1.09e6 * 365 * BOE_TO_MWH / 1e6
uk_oil_mt, uk_gas_twh = 218, 2060
UK_BUDGET_TWH = uk_oil_mt * TONNE_OIL_TO_MWH + uk_gas_twh
UK_M = 2 * UK_E0_TWH / UK_BUDGET_TWH
UK_BLENDED_INTENSITY = (uk_oil_mt * TONNE_OIL_TO_MWH) / UK_BUDGET_TWH * 0.2571 + \
                       (uk_gas_twh / UK_BUDGET_TWH) * 0.198

def uk_mtco2(year):
    t = max(year, 2025) - 2025
    return UK_E0_TWH * (1 + UK_M * t) * np.exp(-UK_M * t) * UK_BLENDED_INTENSITY

def nouk_mtco2(year):
    return no_mtco2(year) + uk_mtco2(year)

# ---------------------------------------------------------------------------
# Coal/lignite domestic PRODUCTION by country, 2020, MtCO2-eq (Eurostat
# nrg_bal_c, nrg_bal="PPRD", hard coal codes C0110/C0121/C0129/C0311/C0312/
# C0320/C0330 x 0.3361 tCO2/MWh, lignite codes C0210/C0220/C0340 x 0.4069
# tCO2/MWh). Only countries with non-negligible production are modelled
# individually; the small remainder (~10 MtCO2-eq: PT, LV, ME, MK, NL, and
# other trace producers) is held flat throughout in all three "with coal"
# variants, no phase-out applied (too small to matter for the comparison).
COUNTRY_COAL_2020 = {
    "PL": 163.8,  # hard coal 122.0 + lignite 41.8 -- by far the largest domestic hard-coal producer
    "DE": 110.7,  # lignite only -- German hard-coal mining ended in 2018
    "CZ": 47.0,   # hard coal 5.4 + lignite 41.6
    "RS": 34.1,   # lignite, non-EU (Serbia)
    "BG": 17.7,   # lignite
    "BA": 15.8,   # lignite, non-EU (Bosnia)
    "RO": 12.3,   # lignite
    "EL": 7.7,    # lignite (Greece)
    "XK": 7.4,    # lignite, non-EU (Kosovo)
    "HU": 4.4,    # lignite
}
COAL_RESIDUAL_2020 = 431.6 - sum(COUNTRY_COAL_2020.values())  # ~10.4 MtCO2-eq, other trace producers

# Phase-out years, rounded onto the model's own 5-year grid. Non-EU Western
# Balkans (RS, BA, XK) have no binding coal phase-out commitment found --
# held flat (no phase-out) in the "phase-out" variant too, which is the
# realistic assumption, not an oversight.
PHASEOUT_YEAR = {
    "EL": 2025,  # already effectively phased out (Beyond Fossil Fuels tracker)
    "HU": 2030,
    "RO": 2030,  # real target ~2032, rounded to grid
    "PL": 2035,  # OVERRIDDEN per instruction -- real Polish target is 2049
    "CZ": 2035,  # real target ~2033, rounded to grid
    "DE": 2040,  # legislated Kohleausstiegsgesetz 2038, rounded to grid
    "BG": 2040,  # real target 2038-40
    # RS, BA, XK: no entry -> held flat, no phase-out
}

def coal_none(year):
    return 0.0

def coal_flat(year):
    return sum(COUNTRY_COAL_2020.values()) + COAL_RESIDUAL_2020

def coal_phaseout(year):
    total = COAL_RESIDUAL_2020
    for country, level in COUNTRY_COAL_2020.items():
        cutoff = PHASEOUT_YEAR.get(country)
        total += 0.0 if (cutoff is not None and year >= cutoff) else level
    return total

MODES = {
    "No coal (old version)": (coal_none, "tab:blue"),
    "With coal, production-based (new version)": (coal_flat, "tab:orange"),
    "With coal phase-out (Poland 2035)": (coal_phaseout, "tab:red"),
}

# ---------------------------------------------------------------------------
# Plot 1: ceiling composition over time, one line per mode (NO+UK+coal_mode)
years_fine = np.linspace(2020, 2050, 121)
fig, ax = plt.subplots(figsize=(9, 5.5))
for label, (coal_fn, color) in MODES.items():
    ax.plot(years_fine, [nouk_mtco2(y) + coal_fn(y) for y in years_fine], color=color, lw=2, label=label)
ax.set_xlabel("Year")
ax.set_ylabel("Norway+UK+coal ceiling (MtCO2-eq/yr)")
ax.set_title("European-safe fossil ceiling: effect of coal treatment")
ax.legend(fontsize=9, loc="upper right")
fig.tight_layout()
fig.savefig(f"{out_dir}/coal_treatment_comparison.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Plot 2: 2050 mix breakdown, grouped bars, one group per mode
components = ["Norway (gas+oil)", "UK (gas+oil)", "Coal+lignite"]
mix_colors = ["#1f77b4", "#7f7f7f", "#2c2c2c"]
mode_labels = list(MODES)
x = np.arange(len(mode_labels))
fig, ax = plt.subplots(figsize=(8, 5.5))
bottoms = np.zeros(len(mode_labels))
for comp, color in zip(components, mix_colors):
    vals = []
    for label in mode_labels:
        coal_fn = MODES[label][0]
        if comp == "Norway (gas+oil)":
            vals.append(no_mtco2(2050))
        elif comp == "UK (gas+oil)":
            vals.append(uk_mtco2(2050))
        else:
            vals.append(coal_fn(2050))
    ax.bar(x, vals, bottom=bottoms, label=comp, color=color, width=0.5)
    for xi, (v, b) in enumerate(zip(vals, bottoms)):
        if v > 10:
            ax.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white")
    bottoms += np.array(vals)
for xi, v in enumerate(bottoms):
    ax.text(xi, v + 10, f"total: {v:.0f}", ha="center", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(mode_labels, fontsize=8)
ax.set_ylabel("MtCO2-eq/yr")
ax.set_title("2050 European-safe fossil mix, by coal treatment")
ax.legend(loc="upper right", fontsize=9)
fig.tight_layout()
fig.savefig(f"{out_dir}/coal_treatment_2050_mix.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
print(f"Domestic coal+lignite production total (2020): {sum(COUNTRY_COAL_2020.values()) + COAL_RESIDUAL_2020:.1f} MtCO2-eq")
print(f"  (vs. the earlier, incorrect consumption-based figure: 617.2 MtCO2-eq)")
print(f"\nPer-country coal+lignite, phase-out year, MtCO2-eq (2020):")
for c, v in COUNTRY_COAL_2020.items():
    print(f"  {c}: {v:.1f}  phase-out={PHASEOUT_YEAR.get(c, 'none (held flat)')}")
print(f"  other trace producers: {COAL_RESIDUAL_2020:.1f}  (held flat, no phase-out modelled)")

print("\nCeiling by year and mode (MtCO2-eq):")
for y in YEARS:
    row = "  ".join(f"{label.split(' (')[0]}={nouk_mtco2(y)+fn(y):.1f}" for label, (fn, _) in MODES.items())
    print(f"  {y}: {row}")

print(f"\nSaved {out_dir}/coal_treatment_comparison.png")
print(f"Saved {out_dir}/coal_treatment_2050_mix.png")
