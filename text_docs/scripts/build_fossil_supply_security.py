"""
Build the fossil-supply-security curves documented in
text_docs/text/fossil_supply_security_methodology.md:

1. A sigmoid transition of the TOTAL fossil-use limit (MtCO2-eq/yr) from a
   real historical anchor (~2018, EEA/UNFCCC data, this fork's own 34-country
   scope) down to a 2050 floor set by Norway+UK production alone.
2. Norway (SODIR/Norwegian Offshore Directorate) + UK (NSTA) production,
   converted to MtCO2-eq/yr, as the "European-safe" supply ceiling.
3. The ratio of (2) over (1) per year -- how much of the allowed total
   fossil use could, in principle, be met from Norway+UK alone.

All conversion factors and anchors are documented inline and in the
methodology .md; nothing here is a hidden assumption.

Usage: python3 build_fossil_supply_security.py [out_dir]
"""
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

YEARS = [2020, 2025, 2030, 2035, 2040, 2045, 2050]

# ---------------------------------------------------------------------------
# 1. Historical anchor: 2018 fossil-combustion CO2, this fork's own
#    EEA/UNFCCC data (scripts/build_co2_totals.py), summed over individual
#    EU28+CH+NO+GB countries (not the EU28 aggregate row, to avoid double
#    counting). 2018 is the latest year in the locally-archived UNFCCC_v23
#    data; used as a proxy for "2020" per the methodology doc's caveat
#    (2020 itself was a COVID-depressed outlier year, so 2018 is arguably a
#    more representative "pre-transition" anchor anyway).
ANCHOR_2018_MTCO2 = 2765.4

# ---------------------------------------------------------------------------
# 2. Norway: Norwegian Offshore Directorate (Sodir) "Resource Report 2024",
#    three scenarios to 2050, million Sm3 o.e./yr. Central ("gradual
#    decline") scenario points are directly reported; other years are
#    linearly interpolated between reported points (flagged, not sourced).
NO_SCM_OE = {2025: 243, 2030: 215, 2035: 160, 2050: 83}  # 2030 back-solved from ~3.5M boed
NO_SCM_OE_HIGH_2050 = 158  # "High" scenario: ~65% of 2025 level

SCM_OE_TO_MWH = 9.9  # 1 Sm3 oil equivalent ~ 9.9 MWh (IEA toe convention: 1 toe=11.63 MWh, ~0.85 toe/m3 oil)
NO_BLENDED_INTENSITY = 0.22  # tCO2/MWh, Norway's gas-majority (~60-65% energy) oil/gas export mix,
# interpolated between gas (0.198) and oil (0.2571) -- see methodology doc.

# ---------------------------------------------------------------------------
# 3. UK: NSTA-reported 2025 rate (1.09 million boed --> annualised) as e0,
#    and NSTA's own remaining-recoverable-resource estimate to 2050 (218 Mt
#    oil + 2060 TWh gas) as the cumulative "budget" B. Because a remaining
#    recoverable reserve genuinely is a bounded, roughly-conserved physical
#    quantity (unlike an assumed political fossil-supply target), the
#    Victoria/Zeyen/Brown (Joule, 2022, supplemental S1) exponential-decay-
#    to-a-budget functional form is legitimately applicable here -- see
#    methodology doc Section 2 for why this is NOT used for the overall
#    sigmoid.
BOE_TO_MWH = 1.7
TONNE_OIL_TO_MWH = 11.63

uk_2025_boed = 1.09e6
UK_E0_TWH = uk_2025_boed * 365 * BOE_TO_MWH / 1e6  # MWh -> TWh
uk_oil_mt, uk_gas_twh = 218, 2060
# uk_oil_mt is in MILLION tonnes; million-tonnes x MWh/tonne = million MWh = TWh directly.
UK_BUDGET_TWH = uk_oil_mt * TONNE_OIL_TO_MWH + uk_gas_twh  # cumulative TWh, 2025-2050 (25 yr)

# r=0 case of Victoria et al. eq. 2-3: m = 2*e0/B
UK_M = 2 * UK_E0_TWH / UK_BUDGET_TWH

def uk_decay_twh(t_since_2025):
    return UK_E0_TWH * (1 + UK_M * t_since_2025) * np.exp(-UK_M * t_since_2025)

UK_BLENDED_INTENSITY = (uk_oil_mt * TONNE_OIL_TO_MWH) / UK_BUDGET_TWH * 0.2571 + \
                       (uk_gas_twh / UK_BUDGET_TWH) * 0.198  # energy-weighted oil/gas intensity

def uk_mtco2(year):
    return uk_decay_twh(year - 2025) * UK_BLENDED_INTENSITY

# ---------------------------------------------------------------------------
# Build Norway MtCO2/yr per year (interpolate the reported Sodir points)
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

# ---------------------------------------------------------------------------
# European-safe (NO+UK) ceiling, central case
ceiling = {y: no_mtco2(y) + (uk_mtco2(y) if y >= 2025 else uk_mtco2(2025)) for y in YEARS}
ceiling[2020] = no_mtco2(2020) + uk_mtco2(2025)  # no UK trend info before 2025; hold at 2025 rate

FLOOR_2050 = ceiling[2050]

# ---------------------------------------------------------------------------
# Sigmoid total-fossil-limit transition: ceiling (2018 anchor) -> floor (2050,
# European-safe supply). Three steepness variants for sensitivity, per the
# "shape matters in the middle years" discussion.
def sigmoid(year, t0, k, top=ANCHOR_2018_MTCO2, bottom=FLOOR_2050):
    return bottom + (top - bottom) / (1 + np.exp(k * (year - t0)))

VARIANTS = {
    "Early transition (t0=2032, steep)": dict(t0=2032, k=0.35),
    "Central transition (t0=2036, medium)": dict(t0=2036, k=0.28),
    "Late transition (t0=2040, gradual)": dict(t0=2040, k=0.22),
}

years_fine = np.linspace(2020, 2050, 121)

# ---------------------------------------------------------------------------
# Plot 1: sigmoid variants + NO+UK ceiling + existing config values
fig, ax1 = plt.subplots(figsize=(9, 5.5))
for label, p in VARIANTS.items():
    ax1.plot(years_fine, [sigmoid(y, **p) for y in years_fine], lw=2, label=label)

ceiling_years = sorted(ceiling)
ax1.plot(ceiling_years, [ceiling[y] for y in ceiling_years], "o--", color="black",
          lw=1.5, label="Norway+UK ceiling (central)")

existing = {2025: 2600, 2030: 1378, 2035: 456, 2040: 129, 2045: 103, 2050: 78}
ax1.plot(list(existing), list(existing.values()), "s:", color="tab:red",
          lw=1.5, label="Existing fossil_limit_values (medium scenario)")

ax1.axhline(FLOOR_2050, color="grey", lw=0.8, ls=":")
ax1.set_xlabel("Year")
ax1.set_ylabel("Total fossil-use limit (MtCO2-eq/yr)")
ax1.set_title("Fossil-use limit transition: sigmoid shapes vs. Norway+UK ceiling")
ax1.legend(fontsize=8, loc="upper right")
fig.tight_layout()
fig.savefig(f"{out_dir}/fossil_supply_sigmoid_variants.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Plot 2: central sigmoid + ratio of NO+UK ceiling / sigmoid on secondary axis
central = VARIANTS["Central transition (t0=2036, medium)"]
sig_years = YEARS
sig_vals = {y: sigmoid(y, **central) for y in sig_years}
ratio = {y: 100 * ceiling[y] / sig_vals[y] for y in sig_years}

fig, ax1 = plt.subplots(figsize=(8, 5))
ax1.plot(years_fine, [sigmoid(y, **central) for y in years_fine], color="tab:blue", lw=2,
          label="Total fossil-use limit (sigmoid, central)")
ax1.plot(ceiling_years, [ceiling[y] for y in ceiling_years], "o--", color="black", lw=1.5,
          label="Norway+UK ceiling (central)")
ax1.set_xlabel("Year")
ax1.set_ylabel("MtCO2-eq/yr")
ax2 = ax1.twinx()
ax2.plot(sig_years, [ratio[y] for y in sig_years], "^-", color="tab:green", lw=2,
          label="Norway+UK share of total limit (%)")
ax2.set_ylabel("Norway+UK share of total fossil-use limit (%)")
ax2.set_ylim(0, max(110, max(ratio.values()) * 1.1))
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
ax1.set_title("Central sigmoid vs. Norway+UK self-sufficiency share")
fig.tight_layout()
fig.savefig(f"{out_dir}/fossil_supply_security_ratio.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
print("Norway+UK ceiling (MtCO2-eq/yr):")
for y in ceiling_years:
    print(f"  {y}: NO={no_mtco2(y):.1f}  UK={uk_mtco2(y) if y>=2025 else float('nan'):.1f}  total={ceiling[y]:.1f}")
print(f"\nUK decay fit: e0={UK_E0_TWH:.1f} TWh/yr, budget={UK_BUDGET_TWH:.1f} TWh, m={UK_M:.4f}/yr")
print(f"UK blended intensity: {UK_BLENDED_INTENSITY:.4f} tCO2/MWh")
print(f"\nFLOOR_2050 (Norway+UK central): {FLOOR_2050:.1f} MtCO2-eq/yr")
print(f"ANCHOR_2018: {ANCHOR_2018_MTCO2} MtCO2-eq/yr")
print("\nCentral sigmoid vs existing fossil_limit_values vs Norway+UK ceiling, and ratio:")
for y in sig_years:
    ex = existing.get(y)
    print(f"  {y}: sigmoid={sig_vals[y]:.1f}  existing={ex}  NO+UK_ceiling={ceiling[y]:.1f}  ratio={ratio[y]:.1f}%")

print(f"\nSaved {out_dir}/fossil_supply_sigmoid_variants.png")
print(f"Saved {out_dir}/fossil_supply_security_ratio.png")
