"""
Build the two fossil-supply-security plot sets documented in
text_docs/text/fossil_supply_security_methodology.md:

  - "no coal": ceiling = Norway + UK gas+oil production only.
  - "with coal": ceiling = Norway + UK + EU-domestic coal+lignite
    PRODUCTION (not consumption), held flat at 2020 level -- the
    recommended treatment (see doc Section 4.3): since steel is
    endogenous and the model's own CO2Limit will squeeze out coal
    economically anyway, the security ceiling should reflect real
    national production potential, not an assumed political phase-out.

Each variant gets:
  1. A main plot: three total-fossil-limit curves (Norway+UK[+coal] share
     reaching 100%/80%/60% by 2050, share bounded by construction via a
     smoothstep polynomial -- see doc Section 3) + the ceiling + CO2Limit
     (~1.9C pathway, extended back to 2020) on the left axis, the three
     share curves (dotted, colour-matched) on the right axis.
  2. A 2020-vs-2050 resource mix breakdown (stacked bars).

Usage: python3 build_fossil_supply_security.py [out_dir]
"""
import sys
import numpy as np
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

# 2020 is still used internally as the share-curve's anchor point (real
# Eurostat actual, see ANCHOR_2020_MTCO2 below) -- Section 3.1's caveat
# means it's not a great *displayed* reference year (this model's own
# CO2Limit(2020) checkpoint isn't independently validated the way 2030 is),
# so plots/tables now start at 2025, the first year these myopic runs
# actually solve.
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
years_fine = np.linspace(2025, 2050, 101)

# ---------------------------------------------------------------------------
# Historical anchor: GENUINE 2020 actual, all 34 model countries.
# Eurostat Complete Energy Balances (nrg_bal_c), Gross Inland Consumption
# (GIC) of natural gas (G3000) + oil & petroleum products excl. biofuels
# (O4000XBIO) + solid fossil fuels (C0000X0350-0370), summed across 33 of
# this fork's 34 countries (all except Switzerland, which Eurostat's
# nrg_bal_c does not cover). Source:
# data/eurostat_balances/archive/2026-02/estat_nrg_bal_c.tsv.gz on the
# cluster; compact extract at
# text_docs/literature/eurostat_GIC_fossil_by_country_2020_scope.csv.
# 33-country cross-check years: 2018=3616.4, 2023=2628.7, 2024=2554.9.
#
# Switzerland (added 2026-09-01, see doc Section 3 for full sourcing):
# Swiss Federal Office for the Environment (BAFU/FOEN), "CO2-Statistik:
# Emissionen aus Brenn- und Treibstoffen" (thermal + motor fuel CO2),
# <https://www.bafu.admin.ch/en/co2-statistics>, data table
# CO2-Statistik-2026-07_DE.xlsx (published 2026-07-13), sheet "Brenn- und
# Treibstoffe", columns "Treibstoffe total" (motor fuels) + "Brennstoffe
# total" (thermal/heating fuels) -- Switzerland has no material domestic
# coal use, so this genuinely covers the same oil+gas(+trace other) scope
# as the Eurostat GIC figure above. File saved at
# text_docs/literature/BAFU_CO2-Statistik_2026-07_DE.xlsx; compact extract
# at text_docs/literature/switzerland_BAFU_fossil_co2_2018-2024.csv.
# 2020: 29.2, 2023: 27.2, 2024: 26.6 MtCO2.
#
# Combined 34-country totals: 2018=3648.2, 2020=2768.2, 2023=2655.9,
# 2024=2581.5 MtCO2-eq -- 2024 sits close to this config's own
# fossil_limit_values[2025]=2600.
ANCHOR_2020_MTCO2 = 2768.2

# ---------------------------------------------------------------------------
# Norway: Sodir "Resource Report 2024", three scenarios to 2050, million
# Sm3 o.e./yr. Central ("gradual decline") points directly reported; other
# years linearly interpolated (flagged, not sourced). 2030 back-solved
# from a separately-reported ~3.5M boe/d rate.
NO_SCM_OE = {2025: 243, 2030: 215, 2035: 160, 2050: 83}
SCM_OE_TO_MWH = 9.9  # 1 Sm3 o.e. ~ 9.9 MWh (IEA: 1 toe=11.63 MWh, ~0.85 toe/m3 oil)
NO_BLENDED_INTENSITY = 0.22  # tCO2/MWh, gas-majority oil/gas export mix blend
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
# UK: NSTA 2025 rate (1.09M boe/d) as e0, remaining-recoverable-resource
# (218 Mt oil + 2060 TWh gas) as the cumulative "budget" B -- legitimately
# fit with the Victoria/Zeyen/Brown (Joule 2022) decay-to-a-budget formula
# since a remaining reserve genuinely is a bounded physical quantity
# (unlike an assumed political target -- see doc Section 2).
BOE_TO_MWH = 1.7
TONNE_OIL_TO_MWH = 11.63
UK_E0_TWH = 1.09e6 * 365 * BOE_TO_MWH / 1e6
uk_oil_mt, uk_gas_twh = 218, 2060
UK_BUDGET_TWH = uk_oil_mt * TONNE_OIL_TO_MWH + uk_gas_twh
UK_M = 2 * UK_E0_TWH / UK_BUDGET_TWH  # r=0 closed form: m = 2*e0/B
UK_BLENDED_INTENSITY = (uk_oil_mt * TONNE_OIL_TO_MWH) / UK_BUDGET_TWH * 0.2571 + \
                       (uk_gas_twh / UK_BUDGET_TWH) * 0.198

def uk_mtco2(year):
    t = max(year, 2025) - 2025
    return UK_E0_TWH * (1 + UK_M * t) * np.exp(-UK_M * t) * UK_BLENDED_INTENSITY

def nouk_mtco2(year):
    return no_mtco2(year) + uk_mtco2(year)

# ---------------------------------------------------------------------------
# EU-domestic coal+lignite: PRODUCTION (not consumption -- hard coal is
# ~64% imported in this scope, lignite ~100% domestic; see doc Section
# 4.3), held flat at 2020 level as the RECOMMENDED treatment: since steel
# is endogenous in this model and competes coal(BOF)-route against
# EAF+H2-DRI, and CO2Limit will squeeze out coal economically anyway, the
# security ceiling should reflect real national production potential, not
# an assumed political phase-out (that was tried as an exploratory Poland
# 2035 override -- see compare_coal_treatment.py -- and dropped as the
# recommended path per that discussion).
# 2020 = 431.6 MtCO2-eq (hard coal 127.8 @ 0.3361 tCO2/MWh + lignite 303.8
# @ 0.4069 tCO2/MWh). Top contributors: PL 163.8 (effectively all this
# scope's domestic hard coal, plus its own lignite), DE 110.7 (lignite
# only -- German hard-coal mining ended 2018), CZ 47.0.
COAL_2020_MTCO2 = 431.6

def coal_mtco2(year):
    return COAL_2020_MTCO2

# ---------------------------------------------------------------------------
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return 3 * x**2 - 2 * x**3

SHARE_TARGETS = {
    "100% by 2050": 1.00,
    "80% by 2050": 0.80,
    "60% by 2050": 0.60,
}
VARIANT_COLORS = {
    "100% by 2050": "tab:blue",
    "80% by 2050": "tab:orange",
    "60% by 2050": "tab:red",
}

# Current CO2Limit trajectory (net, CCS-credited), from this config's
# co2_budget fractions of 1990 levels -- ~1.9C pathway. 2020 added:
# CO2Limit(year) = base_1990 x fraction[year], base_1990 back-solved as
# 2983.3/0.648 = 4603.6 MtCO2, consistent across all points to rounding.
CO2LIMIT_1P9C = {2020: 3314.9, 2025: 2983.3, 2030: 2071.8, 2035: 1151.0,
                 2040: 460.4, 2045: 230.2, 2050: 0.0}


def build_variant(name, ceiling_fn, mix_components, out_prefix):
    """ceiling_fn(year) -> MtCO2-eq; mix_components: dict label -> fn(year)."""
    ceiling = {y: ceiling_fn(y) for y in YEARS}
    anchor = ANCHOR_2020_MTCO2
    share_2020 = ceiling_fn(2020) / anchor  # still the curve's anchor point, just not displayed

    def share_curve(year, target):
        x = (year - 2020) / 30
        return share_2020 + (target - share_2020) * smoothstep(x)

    def total_curve(year, target):
        return ceiling_fn(year) / share_curve(year, target)

    # --- main plot ---
    fig, ax1 = plt.subplots(figsize=(9.5, 6))
    ax2 = ax1.twinx()
    for label, target in SHARE_TARGETS.items():
        color = VARIANT_COLORS[label]
        ax1.plot(years_fine, [total_curve(y, target) for y in years_fine], color=color, lw=2,
                  label=f"Total fossil-use limit ({label})")
        ax2.plot(years_fine, [100 * share_curve(y, target) for y in years_fine], color=color,
                  lw=1.5, ls=":", label=f"{name} share ({label})")
    ceiling_years = sorted(ceiling)
    ax1.plot(ceiling_years, [ceiling[y] for y in ceiling_years], "o--", color="black", lw=1.5,
              label=f"{name} ceiling")
    co2limit_shown = {y: v for y, v in CO2LIMIT_1P9C.items() if y in YEARS}
    ax1.plot(list(co2limit_shown), list(co2limit_shown.values()), "D-", color="tab:purple",
              lw=1.5, label="CO2Limit, current config (~1.9C)")
    ax1.set_xlabel("Year")
    ax1.set_ylabel("MtCO2-eq/yr")
    ax2.set_ylabel(f"{name} share of total fossil-use limit (%)")
    ax2.set_ylim(0, 110)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=7.5)
    ax1.set_title(f"Fossil-use limit variants -- {name}")
    fig.tight_layout()
    fig.savefig(f"{out_dir}/{out_prefix}_security.png", dpi=150)
    plt.close(fig)

    # --- 2050 mix breakdown ---
    mix_years = [2025, 2050]
    colors = plt.get_cmap("tab10").colors
    fig, ax = plt.subplots(figsize=(7, 5))
    bottoms = np.zeros(len(mix_years))
    x = np.arange(len(mix_years))
    for i, (comp, fn) in enumerate(mix_components.items()):
        vals = [fn(y) for y in mix_years]
        ax.bar(x, vals, bottom=bottoms, label=comp, color=colors[i % 10], width=0.5)
        for xi, (v, b) in enumerate(zip(vals, bottoms)):
            if v > 15:
                ax.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white")
        bottoms += np.array(vals)
    for xi in range(len(mix_years)):
        ax.text(xi, bottoms[xi] + 15, f"total: {bottoms[xi]:.0f}", ha="center", fontsize=9)
    ax.axhline(ANCHOR_2020_MTCO2, color="red", ls="--", lw=1)
    ax.text(len(mix_years) - 0.3, ANCHOR_2020_MTCO2 - 70,
             f"2020 actual total fossil use: {ANCHOR_2020_MTCO2:.0f}", color="red", fontsize=8, ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in mix_years])
    ax.set_ylabel("MtCO2-eq/yr")
    ax.set_title(f"European-safe fossil resource mix: 2025 vs. 2050 -- {name}")
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(f"{out_dir}/{out_prefix}_mix_2050.png", dpi=150)
    plt.close(fig)

    # --- print table ---
    print(f"\n=== {name} ===")
    print(f"share(2020) = {share_2020*100:.1f}%")
    for y in YEARS:
        comps = "  ".join(f"{c}={fn(y):.1f}" for c, fn in mix_components.items())
        print(f"  {y}: ceiling={ceiling[y]:.1f}  ({comps})  CO2Limit={CO2LIMIT_1P9C.get(y)}")
    for label, target in SHARE_TARGETS.items():
        print(f"  -- {label} --")
        for y in YEARS:
            print(f"    {y}: total={total_curve(y, target):.1f}  share={100*share_curve(y, target):.1f}%")
    print(f"Saved {out_dir}/{out_prefix}_security.png")
    print(f"Saved {out_dir}/{out_prefix}_mix_2050.png")


# ---------------------------------------------------------------------------
build_variant(
    "Norway+UK",
    nouk_mtco2,
    {"Norway (gas+oil)": no_mtco2, "UK (gas+oil)": uk_mtco2},
    "fossil_supply_no_coal",
)
build_variant(
    "Norway+UK+coal",
    lambda y: nouk_mtco2(y) + coal_mtco2(y),
    {"Norway (gas+oil)": no_mtco2, "UK (gas+oil)": uk_mtco2, "EU-domestic coal+lignite": coal_mtco2},
    "fossil_supply_with_coal",
)
