"""
Build the fossil-supply-security plot documented in
text_docs/text/fossil_supply_security_methodology.md: a single figure with

1. A sigmoid transition of the TOTAL fossil-use limit (MtCO2-eq/yr) from a
   real historical anchor (genuine 2020 actual, Eurostat Complete Energy
   Balances / nrg_bal_c, Gross Inland Consumption, this fork's own
   33-country data scope) down to a 2050 floor set by Norway+UK production
   alone. Uses the "early transition" (t0=2032, k=0.35) shape as the single
   reference curve, since it's the only one of the three originally-plotted
   variants that actually reaches the Norway+UK floor by 2050.
2. Norway (SODIR/Norwegian Offshore Directorate) + UK (NSTA) production,
   converted to MtCO2-eq/yr, as the "European-safe" supply ceiling.
3. The current CO2Limit trajectory (~1.9C pathway), extended back to 2020.
4. On the secondary axis: the ratio of (2) over (1) per year -- how much of
   the allowed total fossil use could, in principle, be met from Norway+UK
   alone.

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
# 1. Historical anchor: GENUINE 2020 actual (not a proxy), Eurostat Complete
#    Energy Balances (nrg_bal_c), Gross Inland Consumption (GIC) of natural
#    gas (G3000) + oil & petroleum products excl. biofuels (O4000XBIO) +
#    solid fossil fuels (C0000X0350-0370), summed across this fork's
#    33-country scope (all 34 minus CH, which this Eurostat dataset does not
#    cover). Source: data/eurostat_balances/archive/2026-02/estat_nrg_bal_c.tsv.gz
#    on the cluster (this fork's own live-pipeline data cache, published by
#    Eurostat, archived there Feb 2026) -- a compact per-country extract is
#    saved at text_docs/literature/eurostat_GIC_fossil_by_country_2020_scope.csv.
#    Cross-check years also computed: 2018=3616.4, 2023=2628.7, 2024=2554.9
#    MtCO2-eq -- note 2024 (latest actual) sits close to this config's own
#    assumed fossil_limit_values[2025]=2600, a reassuring cross-validation.
ANCHOR_YEAR = 2020
ANCHOR_2020_MTCO2 = 2739.0  # genuine 2020 actual, MtCO2-eq -- see comment above.

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
# Total-fossil-limit curves, constructed so the Norway+UK share is bounded
# by construction (never exceeds its own 2050 target) rather than picked
# freehand and checked after the fact (which is how the earlier draft ended
# up with a >100% share at 2045).
#
# Method: define a SHARE curve share(t) = NO+UK(t) / TOTAL(t) directly,
# using a smoothstep polynomial (3x^2 - 2x^3, x in [0,1]) that starts at the
# real, empirically-grounded 2020 share (NO+UK(2020) / ANCHOR_2020, ~25%)
# and reaches EXACTLY a chosen target share at 2050 -- smoothstep is a
# genuine polynomial, monotonic, and hits both endpoints exactly (unlike a
# logistic sigmoid, which only approaches its asymptote). Then invert:
# TOTAL(t) = NO+UK(t) / share(t). Three variants share the same shape,
# scaled to different 2050 targets (100% / 80% / 60% self-sufficiency),
# per your request -- all three necessarily agree at 2020 (they all reduce
# to TOTAL(2020) = ANCHOR_2020 exactly, since share(2020) is defined as
# NO+UK(2020)/ANCHOR_2020 for every variant).
def ceiling_continuous(year):
    return no_mtco2(year) + (uk_mtco2(year) if year >= 2025 else uk_mtco2(2025))

def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return 3 * x**2 - 2 * x**3

SHARE_2020 = ceiling_continuous(2020) / ANCHOR_2020_MTCO2

SHARE_TARGETS = {
    "100% Norway+UK by 2050": 1.00,
    "80% Norway+UK by 2050": 0.80,
    "60% Norway+UK by 2050": 0.60,
}
VARIANT_COLORS = {
    "100% Norway+UK by 2050": "tab:blue",
    "80% Norway+UK by 2050": "tab:orange",
    "60% Norway+UK by 2050": "tab:red",
}

def share_curve(year, target):
    x = (year - 2020) / (2050 - 2020)
    return SHARE_2020 + (target - SHARE_2020) * smoothstep(x)

def total_curve(year, target):
    return ceiling_continuous(year) / share_curve(year, target)

years_fine = np.linspace(2020, 2050, 121)
ceiling_years = sorted(ceiling)

# Current CO2Limit trajectory (net, CCS-credited), from this config's
# co2_budget fractions of 1990 levels -- corresponds to a ~1.9C global
# temperature-increase pathway (per user's own model calibration).
# 2020 added: CO2Limit(year) = base_1990 x co2_budget_fraction[year], with
# base_1990 back-solved from the 2025-2050 values (base_1990 = 2983.3/0.648
# = 4603.6 MtCO2, consistent to within rounding across all five points).
# co2_budget fractions: 2020=0.72, 2025=0.648, 2030=0.45, 2035=0.25,
# 2040=0.1, 2045=0.05, 2050=0.0.
CO2LIMIT_1P9C = {2020: 3314.9, 2025: 2983.3, 2030: 2071.8, 2035: 1151.0,
                 2040: 460.4, 2045: 230.2, 2050: 0.0}

# ---------------------------------------------------------------------------
# Single combined plot: left axis = MtCO2-eq/yr (three total-limit curves,
# NO+UK ceiling, CO2Limit); right axis = the three share curves, dotted,
# each colour-matched to its total-limit curve.
fig, ax1 = plt.subplots(figsize=(9.5, 6))
ax2 = ax1.twinx()

for label, target in SHARE_TARGETS.items():
    color = VARIANT_COLORS[label]
    ax1.plot(years_fine, [total_curve(y, target) for y in years_fine], color=color, lw=2,
              label=f"Total fossil-use limit ({label})")
    ax2.plot(years_fine, [100 * share_curve(y, target) for y in years_fine], color=color,
              lw=1.5, ls=":", label=f"Norway+UK share ({label})")

ax1.plot(ceiling_years, [ceiling[y] for y in ceiling_years], "o--", color="black", lw=1.5,
          label="Norway+UK ceiling (central)")
ax1.plot(list(CO2LIMIT_1P9C), list(CO2LIMIT_1P9C.values()), "D-", color="tab:purple",
          lw=1.5, label="CO2Limit, current config (~1.9C)")
ax1.set_xlabel("Year")
ax1.set_ylabel("MtCO2-eq/yr")

ax2.set_ylabel("Norway+UK share of total fossil-use limit (%)")
ax2.set_ylim(0, 110)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=7.5)
ax1.set_title("Fossil-use limit variants (Norway+UK share reaches 100%/80%/60% by 2050)")
fig.tight_layout()
fig.savefig(f"{out_dir}/fossil_supply_security.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
print("Norway+UK ceiling (MtCO2-eq/yr):")
for y in ceiling_years:
    print(f"  {y}: NO={no_mtco2(y):.1f}  UK={uk_mtco2(y) if y>=2025 else float('nan'):.1f}  total={ceiling[y]:.1f}")
print(f"\nUK decay fit: e0={UK_E0_TWH:.1f} TWh/yr, budget={UK_BUDGET_TWH:.1f} TWh, m={UK_M:.4f}/yr")
print(f"UK blended intensity: {UK_BLENDED_INTENSITY:.4f} tCO2/MWh")
print(f"\nSHARE_2020 (Norway+UK / ANCHOR_2020): {SHARE_2020*100:.1f}%")
print(f"ANCHOR_2020: {ANCHOR_2020_MTCO2} MtCO2-eq/yr")
print("\nThree total-limit variants vs Norway+UK ceiling vs CO2Limit:")
for label, target in SHARE_TARGETS.items():
    print(f"\n-- {label} --")
    for y in YEARS:
        print(f"  {y}: total={total_curve(y, target):.1f}  NO+UK_ceiling={ceiling[y]:.1f}  "
              f"CO2Limit={CO2LIMIT_1P9C.get(y)}  share={100*share_curve(y, target):.1f}%")

print(f"\nSaved {out_dir}/fossil_supply_security.png")
