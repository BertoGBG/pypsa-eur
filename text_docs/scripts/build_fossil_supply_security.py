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
import os
import sys
import yaml
import numpy as np
import matplotlib.pyplot as plt

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

# Same official tech_colors as the results/ folder's plots (plot_myopic_
# comparison.py), so fuel colours are consistent across every plot in this
# fork, not just within this one script.
_config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "plotting.default.yaml"
)
with open(_config_path) as f:
    TECH_COLORS = yaml.safe_load(f)["plotting"]["tech_colors"]

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

# Native-energy (MWh) versions of the same two components, for the
# energy-basis mix panel (Section 4.5) -- same lookup/decay shape, just
# without the CO2-intensity multiplication.
def no_energy_mwh(year):
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
    return scm * SCM_OE_TO_MWH * 1e6  # -> MWh

def uk_energy_mwh(year):
    t = max(year, 2025) - 2025
    return UK_E0_TWH * (1 + UK_M * t) * np.exp(-UK_M * t) * 1e6  # -> MWh

# ---------------------------------------------------------------------------
# Gas/oil split for Norway and UK (added 2026-09-01, see doc Section 4.6),
# for the per-fuel-coloured mix chart. Both back out an ENERGY-share
# fraction from the blended intensity already chosen above, rather than
# introducing new unsourced per-fuel data -- the fraction is held constant
# across years in both cases (a simplification, flagged in the doc).
#
# Norway: NO_BLENDED_INTENSITY = 0.22 = x*0.198 + (1-x)*0.2571 (gas/oil
# CO2 intensities) => x (gas energy share) = 0.6278.
NO_GAS_ENERGY_SHARE = (0.2571 - NO_BLENDED_INTENSITY) / (0.2571 - 0.198)

def no_gas_mtco2(year):
    return no_energy_mwh(year) * NO_GAS_ENERGY_SHARE * 0.198 / 1e6

def no_oil_mtco2(year):
    return no_energy_mwh(year) * (1 - NO_GAS_ENERGY_SHARE) * 0.2571 / 1e6

def no_gas_energy_mwh(year):
    return no_energy_mwh(year) * NO_GAS_ENERGY_SHARE

def no_oil_energy_mwh(year):
    return no_energy_mwh(year) * (1 - NO_GAS_ENERGY_SHARE)

# UK: same energy-share fraction as the cumulative 218 Mt oil / 2060 TWh
# gas remaining-reserve budget used to build UK_BLENDED_INTENSITY --
# assumes oil and gas deplete at the same relative rate under the single
# decay curve (a simplification: the reserve mix could in reality shift
# over 2025-2050, but no separate oil-only/gas-only decay data was found).
UK_OIL_ENERGY_SHARE = (uk_oil_mt * TONNE_OIL_TO_MWH) / UK_BUDGET_TWH

def uk_oil_mtco2(year):
    return uk_energy_mwh(year) * UK_OIL_ENERGY_SHARE * 0.2571 / 1e6

def uk_gas_mtco2(year):
    return uk_energy_mwh(year) * (1 - UK_OIL_ENERGY_SHARE) * 0.198 / 1e6

def uk_oil_energy_mwh(year):
    return uk_energy_mwh(year) * UK_OIL_ENERGY_SHARE

def uk_gas_energy_mwh(year):
    return uk_energy_mwh(year) * (1 - UK_OIL_ENERGY_SHARE)

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
HARD_COAL_2020_MTCO2, HARD_COAL_INTENSITY = 127.8, 0.3361  # tCO2/MWh
LIGNITE_2020_MTCO2, LIGNITE_INTENSITY = 303.8, 0.4069  # tCO2/MWh

def coal_mtco2(year):
    return COAL_2020_MTCO2

def coal_energy_mwh(year):
    """Native-energy (MWh) version, split by hard coal / lignite's own
    intensities since they're genuinely different fuels (see doc Section
    4.3) -- flat, same as coal_mtco2."""
    return (
        HARD_COAL_2020_MTCO2 * 1e6 / HARD_COAL_INTENSITY
        + LIGNITE_2020_MTCO2 * 1e6 / LIGNITE_INTENSITY
    )

def hard_coal_mtco2(year):
    return HARD_COAL_2020_MTCO2

def lignite_mtco2(year):
    return LIGNITE_2020_MTCO2

def hard_coal_energy_mwh(year):
    return HARD_COAL_2020_MTCO2 * 1e6 / HARD_COAL_INTENSITY

def lignite_energy_mwh(year):
    return LIGNITE_2020_MTCO2 * 1e6 / LIGNITE_INTENSITY

# ---------------------------------------------------------------------------
# Per-fuel colour (matching the results/ folder's plots, config/plotting.
# default.yaml tech_colors) + per-region hatch pattern (added 2026-09-01,
# see doc Section 4.6), for the mix chart: colour identifies the FUEL,
# hatch identifies the COUNTRY/REGION it comes from. Region hatches are
# deliberately different symbols from the biomass sustainability hatches
# ("//" / "\\") used on the same chart, so the two hatch "dimensions"
# (origin vs. sustainability) don't visually collide.
REGION_HATCH = {"Norway": ".", "UK": "x", "EU-domestic": "o"}
FUEL_COMPONENTS = {
    "Norway gas": (no_gas_mtco2, no_gas_energy_mwh, TECH_COLORS["gas"], REGION_HATCH["Norway"]),
    "Norway oil": (no_oil_mtco2, no_oil_energy_mwh, TECH_COLORS["oil"], REGION_HATCH["Norway"]),
    "UK gas": (uk_gas_mtco2, uk_gas_energy_mwh, TECH_COLORS["gas"], REGION_HATCH["UK"]),
    "UK oil": (uk_oil_mtco2, uk_oil_energy_mwh, TECH_COLORS["oil"], REGION_HATCH["UK"]),
    "EU-domestic hard coal": (hard_coal_mtco2, hard_coal_energy_mwh, TECH_COLORS["coal"], REGION_HATCH["EU-domestic"]),
    "EU-domestic lignite": (lignite_mtco2, lignite_energy_mwh, TECH_COLORS["lignite"], REGION_HATCH["EU-domestic"]),
}

# ---------------------------------------------------------------------------
# Biomass potential, sustainable vs unsustainable (added 2026-09-01, see doc
# Section 4.5). Source: resources/base_myopic_50_8h/biomass_potentials_s_50_
# {year}.csv on the cluster (this fork's own biomass-potential-building
# pipeline, summed across all 50 clustered nodes). "Sustainable" = solid
# biomass + biogas columns; "unsustainable" = unsustainable solid biomass +
# unsustainable biogas + unsustainable bioliquids columns (municipal solid
# waste and "not included" excluded -- not combustible biomass potential).
# This is a POTENTIAL/cap, like the rest of this document -- not solved
# dispatch (see the results/ folder's plots for actual myopic-run usage).
BIOMASS_POTENTIAL_TWH = {
    2025: {"sustainable": 13.62, "unsustainable": 1595.69},
    2030: {"sustainable": 465.64, "unsustainable": 1053.15},
    2035: {"sustainable": 912.20, "unsustainable": 526.58},
    2040: {"sustainable": 1366.73, "unsustainable": 0.0},
    2045: {"sustainable": 1368.85, "unsustainable": 0.0},
    2050: {"sustainable": 1371.10, "unsustainable": 0.0},
}

# Upstream/indirect-land-use-change emissions proxy for unsustainable
# biomass (see doc Section 4.5 for full sourcing): EU RED II Annex VIII /
# Delegated Regulation (EU) 2019/807 default iLUC factors span roughly
# 12-55 gCO2eq/MJ depending on feedstock; 30 is a general mid-range proxy
# for now, not a per-feedstock estimate. Sustainable biomass (forest
# residues, in this simplification) carries no upstream charge.
UNSUSTAINABLE_BIOMASS_TCO2_PER_MWH = 30 * 3.6 / 1000  # 30 kgCO2e/GJ -> 0.108 tCO2/MWh
SUSTAINABLE_BIOMASS_TCO2_PER_MWH = 0.0

def biomass_mtco2(year, kind):
    twh = BIOMASS_POTENTIAL_TWH[year][kind]
    factor = UNSUSTAINABLE_BIOMASS_TCO2_PER_MWH if kind == "unsustainable" else SUSTAINABLE_BIOMASS_TCO2_PER_MWH
    return twh * 1e6 * factor / 1e6  # TWh -> MWh -> tCO2 -> MtCO2

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


BIOMASS_COLORS = {"sustainable biomass": "#baa741", "unsustainable biomass": "#998622"}
BIOMASS_HATCHES = {"sustainable biomass": "//", "unsustainable biomass": "\\\\"}


def build_variant(name, ceiling_fn, mix_components, out_prefix, energy_components=None, mix_component_keys=None):
    """ceiling_fn(year) -> MtCO2-eq; mix_components: dict label -> fn(year)
    (used for the ceiling/print-table, grouped by country); mix_component_keys:
    list of FUEL_COMPONENTS keys (used for the mix chart, split by fuel)."""
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

    # --- 2050 mix breakdown: two panels, MtCO2-eq (left) and TWh (right) ---
    # Biomass (sustainable + unsustainable potential, see doc Section 4.5)
    # is added as additional, hatched stacked segments on BOTH panels --
    # visually distinct from the fossil/coal components since it represents
    # a different kind of quantity (a non-fossil alternative/substitute,
    # not part of the "secure fossil supply" ceiling itself).
    mix_years = YEARS  # all six horizons, not just the 2025/2050 endpoints
    x = np.arange(len(mix_years))
    fig, (ax_co2, ax_energy) = plt.subplots(1, 2, figsize=(19, 5.5))

    # -- left panel: MtCO2-eq --
    bottoms = np.zeros(len(mix_years))
    for comp in mix_component_keys:
        fn, _, color, hatch = FUEL_COMPONENTS[comp]
        vals = [fn(y) for y in mix_years]
        ax_co2.bar(x, vals, bottom=bottoms, label=comp, color=color, width=0.6, hatch=hatch, edgecolor="white")
        for xi, (v, b) in enumerate(zip(vals, bottoms)):
            if v > 15:
                ax_co2.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white")
        bottoms += np.array(vals)
    for comp, kind in [("sustainable biomass", "sustainable"), ("unsustainable biomass", "unsustainable")]:
        vals = [biomass_mtco2(y, kind) for y in mix_years]
        ax_co2.bar(x, vals, bottom=bottoms, label=comp, color=BIOMASS_COLORS[comp], width=0.6, hatch=BIOMASS_HATCHES[comp], edgecolor="white")
        for xi, (v, b) in enumerate(zip(vals, bottoms)):
            if v > 15:
                ax_co2.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7)
        bottoms += np.array(vals)
    for xi in range(len(mix_years)):
        ax_co2.text(xi, bottoms[xi] + 15, f"{bottoms[xi]:.0f}", ha="center", fontsize=8)
    ax_co2.axhline(ANCHOR_2020_MTCO2, color="red", ls="--", lw=1)
    ax_co2.text(0.3, ANCHOR_2020_MTCO2 - 70,
             f"2020 actual total fossil use: {ANCHOR_2020_MTCO2:.0f}", color="red", fontsize=8, ha="left")
    ax_co2.set_xticks(x)
    ax_co2.set_xticklabels([str(y) for y in mix_years])
    ax_co2.set_ylabel("MtCO2-eq/yr")
    ax_co2.set_title("Emissions basis (MtCO2-eq/yr)")
    ax_co2.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7.5, borderaxespad=0)

    # -- right panel: TWh (native energy, fossil components + biomass) --
    if mix_component_keys is not None:
        bottoms_e = np.zeros(len(mix_years))
        for comp in mix_component_keys:
            _, energy_fn, color, hatch = FUEL_COMPONENTS[comp]
            vals = [energy_fn(y) / 1e6 for y in mix_years]  # MWh -> TWh
            ax_energy.bar(x, vals, bottom=bottoms_e, label=comp, color=color, width=0.6, hatch=hatch, edgecolor="white")
            for xi, (v, b) in enumerate(zip(vals, bottoms_e)):
                if v > 15:
                    ax_energy.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7, color="white")
            bottoms_e += np.array(vals)
        for comp, kind in [("sustainable biomass", "sustainable"), ("unsustainable biomass", "unsustainable")]:
            vals = [BIOMASS_POTENTIAL_TWH[y][kind] for y in mix_years]
            ax_energy.bar(x, vals, bottom=bottoms_e, label=comp, color=BIOMASS_COLORS[comp], width=0.6, hatch=BIOMASS_HATCHES[comp], edgecolor="white")
            for xi, (v, b) in enumerate(zip(vals, bottoms_e)):
                if v > 15:
                    ax_energy.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7)
            bottoms_e += np.array(vals)
        for xi in range(len(mix_years)):
            ax_energy.text(xi, bottoms_e[xi] + 15, f"{bottoms_e[xi]:.0f}", ha="center", fontsize=8)
        ax_energy.set_xticks(x)
        ax_energy.set_xticklabels([str(y) for y in mix_years])
        ax_energy.set_ylabel("TWh/yr")
        ax_energy.set_title("Energy basis (TWh/yr)")
        ax_energy.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7.5, borderaxespad=0)

    unsustainable_kgco2_per_gj = UNSUSTAINABLE_BIOMASS_TCO2_PER_MWH * 1000 / 3.6
    fig.suptitle(f"European-safe fossil + biomass resource mix, 2025-2050 -- {name}")
    fig.text(0.5, 0.005,
              f"Note: assuming {unsustainable_kgco2_per_gj:.0f} kgCO2e/GJ upstream (iLUC) "
              f"emissions for unsustainable biofuels; 0 for sustainable biomass (see doc Section 5.2).",
              ha="center", fontsize=8, style="italic")
    fig.tight_layout(rect=(0, 0.03, 0.9, 1))
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
    energy_components={"Norway (gas+oil)": no_energy_mwh, "UK (gas+oil)": uk_energy_mwh},
    mix_component_keys=["Norway gas", "Norway oil", "UK gas", "UK oil"],
)
build_variant(
    "Norway+UK+coal",
    lambda y: nouk_mtco2(y) + coal_mtco2(y),
    {"Norway (gas+oil)": no_mtco2, "UK (gas+oil)": uk_mtco2, "EU-domestic coal+lignite": coal_mtco2},
    "fossil_supply_with_coal",
    energy_components={"Norway (gas+oil)": no_energy_mwh, "UK (gas+oil)": uk_energy_mwh, "EU-domestic coal+lignite": coal_energy_mwh},
    mix_component_keys=["Norway gas", "Norway oil", "UK gas", "UK oil", "EU-domestic hard coal", "EU-domestic lignite"],
)
