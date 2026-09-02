# Fossil-supply energy-security limit — methodology and sourcing (DRAFT)

Branch: `heat_industry`. Relates to `fossil_limit` / `fossil_limit_values` in
`config/config.default.yaml`, consumed by `add_fossil_fuel_limit()` in
`scripts/prepare_sector_network.py`.

Companion scripts: `text_docs/scripts/build_fossil_supply_security.py`
builds the **two kept variants** — `fossil_supply_no_coal_security.png` /
`_mix_2050.png` (Norway+UK gas+oil only) and
`fossil_supply_with_coal_security.png` / `_mix_2050.png` (Norway+UK+EU-
domestic coal+lignite, production-based, flat — the recommended
treatment, see Section 4.3). Each `_mix_2050.png` is a two-panel figure:
emissions basis (MtCO2-eq/yr, left) and energy basis (TWh/yr, right), both
now including sustainable/unsustainable biomass potential as additional
hatched segments (Section 5). `text_docs/scripts/compare_coal_treatment.py`
produces `coal_treatment_comparison.png` / `_2050_mix.png`, a three-way
no-coal/flat-coal/phased-coal-out comparison kept only as a labeled
sensitivity case (Section 4.3.1) — the phase-out variant is **not** the
recommended treatment. Both scripts print their full numeric tables to
stdout.

**Scope note**: everything in this document is about *potential* (what
could be supplied/available), not solved dispatch — the `results/`
folder's plots (`analyze_myopic_comparison.py` / `plot_myopic_comparison.py`)
cover actual myopic-run usage instead; the two are deliberately different
questions and use different data sources.

**Implementation status (2026-09-02)**: Section 4's per-carrier gas/oil/hard
coal/lignite ceiling values are now wired into the model as an actual
constraint, not just this document's comparison plots — see
`add_fossil_fuel_limit_per_carrier()` in `scripts/prepare_sector_network.py`,
config `fossil_limit_per_carrier` / `fossil_limit_per_carrier_values`.
Structurally separate from `fossil_limit` (the aggregate climate-driven
budget this document compares against) — both can be active together, each
carrier's cap independent. Verified via a standalone unit test with the real
costs table and config values (constants match this doc's Section 4.4 table
exactly); a full solved-network run confirming the caps actually bind as
expected was not yet completed — see git log for the commit adding this.

## 1. The idea

The existing `fossil_limit_values` ("medium scenario, T*=2040": 2600 -> 78
MtCO2-eq, 2025-2050) is a **climate-driven** gross-supply cap — see its own
docstring in `prepare_sector_network.py`. This document explores a
**different, additional lens**: energy-security / import-independence.
Rather than "how much fossil CO2-eq can we burn under a climate budget," the
question is "how much fossil supply could Europe realistically source from
its own, geopolitically reliable production — and how does that ceiling
evolve as North Sea fields deplete?"

The two are not the same curve, and — see Section 4 — they currently imply
quite different things.

## 2. Why not reuse the CO2-budget math wholesale

Victoria, Zeyen & Brown, "Speed of technological transformations required in
Europe to achieve different climate goals," *Joule* 6 (2022), Supplemental
S1 (`text_docs/literature/1-s2.0-S2542435122001830-mmc2.pdf`), fits emissions
to `e(t) = e0(1+(r+m)t)e^{-mt}`, solving `m` so the integral of `e(t)` equals
a **physically-derived cumulative carbon budget** `B` (from the TCRE
temperature-emissions relationship), with a terminal net-zero-by-2050
condition.

That machinery is only justified because `B` is physically meaningful.
For an *overall* fossil-security target there is no equivalent physical
law forcing a specific cumulative import volume — any such number would be
a political choice dressed as a derived constant. So the overall transition
curve uses a **plain sigmoid** instead (Section 3), not the budget-integral
method.

**One place the budget-integral method genuinely does apply**: a country's
*remaining recoverable hydrocarbon reserves* really is a bounded, roughly
conserved physical quantity (bounded by geology, not politics). The UK
component of the Norway+UK ceiling (Section 4.2) legitimately reuses the
exact Victoria et al. formula for exactly this reason.

## 3. The total fossil-use limit curves, 2020-2050

**Construction method (revised)**: an earlier draft picked a sigmoid shape
`limit(t) = floor + (ceiling - floor) / (1 + exp(k(t-t0)))` freehand and
then *checked* the resulting Norway+UK share after the fact — which broke,
producing a >100% share at 2045 for one variant. The share cannot exceed
100% by definition (Norway+UK cannot supply more than exists), so the
share needs to be bounded **by construction**, not by accident.

Fixed method: define the **share** curve `share(t) = (NO+UK+coal)(t) / limit(t)`
directly, using a **smoothstep polynomial** `3x^2 - 2x^3` (`x` normalized
to [0,1] over 2020-2050) — a genuine polynomial, monotonic, and one that
hits both of its endpoints *exactly* (unlike a logistic sigmoid, which only
asymptotically approaches its limit). `share(2020)` is fixed at the real,
empirically-grounded value `(NO+UK+coal)(2020) / ceiling` (~40.3%, once
coal is included on a production basis — see Section 4.3 — and the anchor
covers all 34 model countries, see below) for every
variant; `share(2050)` is
set to a chosen target (100%, 80%, or 60% self-sufficiency). Then invert:
`limit(t) = (NO+UK+coal)(t) / share(t)`. Because all three variants share
the same `share(2020)`, they necessarily all start at exactly the same
2020 point (`limit(2020) = ceiling` for every variant), diverging only as
they head toward different 2050 outcomes.

- **Ceiling** (2020, genuine historical actual, all 34 model countries —
  not a proxy): **2768.2 MtCO2-eq/yr**. Two components, added together:

  1. **33 of the 34 model countries (all except Switzerland): 2739.0
     MtCO2-eq.** Computed from **Eurostat's Complete Energy Balances**
     (`nrg_bal_c`), **Gross Inland Consumption (GIC)** — i.e. real physical
     fuel-supply volumes, not derived emissions — of natural gas (SIEC
     `G3000`) + oil & petroleum products excl. biofuels (`O4000XBIO`) +
     solid fossil fuels (`C0000X0350-0370`). Source file:
     `data/eurostat_balances/archive/2026-02/estat_nrg_bal_c.tsv.gz` on the
     cluster — this fork's own live-pipeline data cache (Eurostat's own
     published data, archived there Feb 2026, so genuinely current). A
     compact per-country/per-fuel extract is saved at
     `text_docs/literature/eurostat_GIC_fossil_by_country_2020_scope.csv`
     for reproducibility (the 273MB raw bulk file itself was not committed
     — it is pypsa-eur's own re-fetchable data cache, not at risk of being
     lost the way a manually-written note would be). Eurostat's `nrg_bal_c`
     does not cover Switzerland at all, hence the gap this section closes.
  2. **Switzerland (added 2026-09-01): 29.2 MtCO2.** Source: **Swiss
     Federal Office for the Environment (BAFU/FOEN)**, official CO2
     statistics, "CO2-Statistik: Emissionen aus Brenn- und Treibstoffen"
     (CO2 emissions from thermal and motor fuels),
     <https://www.bafu.admin.ch/en/co2-statistics>, data table
     `CO2-Statistik-2026-07_DE.xlsx` (published 2026-07-13), sheet
     "Brenn- und Treibstoffe", columns "Treibstoffe total" (motor fuels:
     petrol + diesel) + "Brennstoffe total" (thermal/heating fuels: heating
     oil + natural gas + a small "Andere"/other residual, ~0.5-0.7
     MtCO2/yr, that is NOT material domestic coal — Switzerland has no coal
     mining and negligible coal combustion; confirmed via the same file's
     "HEL, Gas, Andere" breakdown sheet). This is the same combustion scope
     (oil + gas, all sectors including road transport) as the Eurostat
     figure above, so the two genuinely add. File saved at
     `text_docs/literature/BAFU_CO2-Statistik_2026-07_DE.xlsx`; compact
     extract at
     `text_docs/literature/switzerland_BAFU_fossil_co2_2018-2024.csv`.

  This supersedes an earlier draft of this document that used a **2018,
  emissions-based** proxy (EEA/UNFCCC `build_co2_totals.py` pipeline, which
  the fork only has archived up to 2018) — that number ALSO originally
  undercounted by omitting direct industrial fuel combustion and
  agriculture-machinery fuel. Both problems are now fixed: real 2020 data,
  full sector/fuel coverage via Eurostat's economy-wide GIC measure (which
  by construction includes every combustion sector — power, industry,
  transport including road gasoline/diesel, buildings, agriculture — with no
  per-sector column list to accidentally miss one from) plus Switzerland's
  own official equivalent.

  Cross-check years (34-country totals, Eurostat + BAFU): **2018 = 3648.2,
  2023 = 2655.9, 2024 (latest actual) = 2581.5** MtCO2-eq. The 2024 actual
  sits close to this config's own assumed `fossil_limit_values[2025] =
  2600` — a reassuring independent cross-validation of that existing
  assumption (closer than the earlier 33-country-only figure of 2554.9,
  since adding Switzerland's real ~26.6 MtCO2/yr for 2024 moves the total
  up towards 2600, not away from it).
- **Floor** (2050): the Norway+UK+coal production ceiling, **613.2 MtCO2-eq/yr**
  central case (Section 4, using the corrected production-based coal figure
  — see Section 4.3) — this is exactly the "100% by 2050" variant's
  endpoint; the 80% and 60% variants have higher 2050 endpoints (766.5 and
  1022.0 MtCO2-eq respectively), since they deliberately leave room for
  non-European sources (Africa pipeline + LNG) even at 2050.
- **Three variants**, same shape, different 2050 self-sufficiency target:

  | Variant | Share(2020) | Share(2050) | Total limit(2050) |
  |---|---:|---:|---:|
  | 100% NO+UK+coal by 2050 | 40.3% | 100.0% | 613.2 |
  | 80% NO+UK+coal by 2050 | 40.3% | 80.0% | 766.5 |
  | 60% NO+UK+coal by 2050 | 40.3% | 60.0% | 1022.0 |

  The shape/steepness itself (how fast the share climbs between 2020 and
  2050) is still a free choice baked into the smoothstep polynomial's fixed
  form — this is the remaining "shape matters in the middle years"
  question, now scoped to just that, rather than also needing to separately
  verify the share stays bounded.
  See `fossil_supply_with_coal_security.png` (Section 4.4) and, for the
  no-coal comparison, `fossil_supply_no_coal_security.png`.

### 3.1. Caveat: is the model's CO2Limit path validated against real EU emissions? (added 2026-08-31)

Added after a direct question about why real 2020/2025 fossil consumption
sits notably below this doc's CO2Limit(~1.9C) line -- **this is not evidence
Europe is "doing great" against a genuinely binding target**. Checked
against real, sourced data, not just internal derivation:

- **One checkpoint is genuinely anchored to an official target**:
  `config.default.yaml`'s `co2_budget[2030] = 0.45` (fraction of 1990)
  implies exactly a 55% cut by 2030 -- this matches the EU's legally
  binding European Climate Law (Regulation (EU) 2021/1119) / "Fit for 55"
  target (at least 55% net GHG reduction vs. 1990 by 2030) almost exactly.
  This one point is real, not arbitrary.
- **The interim years (2020, 2025) are looser than what the EU had ALREADY
  achieved in reality**: `co2_budget[2020]=0.72` implies only a 28.0% cut
  by 2020, and `co2_budget[2025]=0.648` implies 35.2% by 2025. But the
  EEA's own published figures (*Trends and projections in Europe 2024/2025*,
  <https://www.eea.europa.eu/en/analysis/indicators/total-greenhouse-gas-emission-trends>,
  press release
  <https://www.eea.europa.eu/en/newsroom/news/trends-and-projections-greenhouse-gas-emissions-largely-on-track-to-2030-targets>)
  report the EU27's real net GHG emissions were already roughly 31-34%
  below 1990 by 2020 (a COVID-depressed year), reaching ~36-37% below 1990
  by 2023 and ~40% (preliminary, varies by source vintage) by 2024. Real-
  world progress had already overtaken this config's 2020 and 2025
  checkpoints before those years even arrived.
- **Two scope mismatches mean the above is directional, not precise**:
  (1) this model's ~33-34-country scope (EU + UK + Norway + Balkans) differs
  from the EU27-only scope of the official target and the EEA figures;
  (2) this config's `base_1990` (4603.6 MtCO2, back-solved from
  `co2_budget`) is a CO2-only, energy-system figure from this model's own
  accounting, not the EU's full all-gas (CO2+CH4+N2O+F-gas), LULUCF-netted
  ~4.9-5.0 GtCO2eq 1990 baseline -- the two "1990" denominators are close in
  magnitude but not identical in composition.
- **Conclusion**: the earlier finding that actual 2020 fossil consumption
  (2768.2 MtCO2-eq, all 34 model countries — Eurostat GIC + Switzerland/
  BAFU, see Section 3) sits below this doc's CO2Limit(2020)=
  3314.9 reflects this model's own interim-year budget shape being
  deliberately backloaded (shallow before 2030, steep after) rather than
  tracking the real observed emissions trajectory -- not independent
  confirmation that Europe is ahead of a real target. The 2030 checkpoint
  is real and binding; 2020/2025 are not independently validated against
  any official target and are, by the EEA's own numbers, already looser
  than reality.

## 4. The Norway+UK+coal ceiling ("European-safe" fossil supply)

**Scope**: Norway + UK (gas+oil) + EU-domestic coal (Section 4.3). Beyond
that, remaining EU-domestic production (Denmark's declining North Sea
fields, Romania's Neptun Deep gas development, Poland's small conventional/
shale gas output) is real but small and **still not included** — a
possible "tier 2" if more precision is wanted later.

### 4.1. Norway

Source: Norwegian Offshore Directorate (Sodir), *Resource Report 2024*,
"Three potential scenarios for the NCS leading up to 2050" —
<https://www.sodir.no/en/whats-new/publications/reports/resource-report/resource-report-2024/three-potential-scenarios-for-the-ncs-leading-up-to-2050/>
(official Norwegian government regulator; primary source, not yet
downloaded as PDF — see open items).

Reported points (million Sm3 oil equivalent/yr, combined oil+gas):
2025: 243; 2050 "gradual decline" (central) scenario: 83; 2050 "High"
scenario (robust exploration + new discoveries): ~65% of 2025 level (~158).
2030 (~215) is back-solved from a separately reported ~3.5 million boe/d
2030 rate (Sodir/NSTA-style press coverage of the same report), not read
directly off the resource report's own scm-oe series — flagged as
approximate. 2035 (160 million scm oe) is directly reported. 2040/2045 are
linear interpolations between 2035 and 2050 — not sourced.

Conversion: 1 Sm3 oil equivalent ~ 9.9 MWh (IEA convention: 1 toe = 11.63
MWh; ~0.85 toe per m3 of oil). Applied a blended CO2 intensity of 0.22
tCO2/MWh (between gas 0.198 and oil 0.2571, weighted toward gas since
Norway's recent export mix is majority gas by energy) — this blend is an
approximation, not derived from Norway's actual annual oil/gas split.

### 4.2. United Kingdom

Source: North Sea Transition Authority (NSTA) — UK government regulator —
2025 production update (via press coverage; NSTA's own primary "Projections
of UK Oil and Gas Production and Expenditure" report series,
`text_docs/literature/NSTA_2019_UK_oil_gas_production_projections.pdf`,
downloaded but is the 2019 vintage, not the current one — see open items).

- 2025 rate (e0): 1.09 million boe/d -> annualised, 1.7 MWh/boe -> **676.3
  TWh/yr**.
- Remaining recoverable resource to 2050 (the "budget" B): 218 million
  tonnes oil (-> 2535.3 TWh at 11.63 MWh/tonne) + 2060 TWh gas = **4595.3
  TWh cumulative, 2025-2050**. NSTA's own framing: "93% of what could be
  extracted since the 1960s-70s has already been removed, leaving just 7%
  for the next 25 years" — i.e. a strongly front-loaded decline, which is
  exactly what the decay fit below reproduces.
- Applying Victoria et al.'s r=0 closed form, `m = 2*e0/B` = **0.294/yr**.
  The resulting curve: 2025=676, 2030=384, 2035=141, 2040=44, 2045=13,
  2050=0.8 TWh/yr.
  **Validation**: NSTA separately reports a 2030 rate of ~0.62 million
  boe/d (-> ~385 TWh/yr) — the fitted curve's independent 2030 value (384
  TWh/yr) matches this almost exactly, despite not being used as a fitting
  constraint. This is a good sign the r=0 exponential-decay shape is a
  reasonable match to the UK's actual depletion profile.
- Blended intensity (energy-weighted from the 218 Mt oil / 2060 TWh gas
  split): **0.2306 tCO2/MWh**.

### 4.3. EU-domestic coal

**Treated symmetrically with Norway/UK gas+oil, per your explicit
direction**: coal is included as a full available domestic resource, not
pre-excluded by an assumed political phase-out date. The reasoning: if coal
ends up unused in an actual model run, that should be because the CO2Limit
constraint made it uneconomic/infeasible to burn — not because this
security-ceiling calculation silently assumed it away first. Baking a
phase-out schedule into the *ceiling* would be circular: it would make coal
"secure but unavailable" by construction, pre-empting exactly the question
the CO2 constraint is supposed to answer.

Unlike UK's North Sea fields, coal's binding constraint isn't geological
depletion — Germany's lignite basins and Poland's coal reserves alone cover
decades at current extraction rates. Absent a production-decline curve
grounded in actual mine-closure schedules (a real research task, time-boxed
out of this session), the simplest defensible choice is to **hold domestic
coal supply flat at its 2020 actual level for the whole 2020-2050 horizon**.
This is a deliberate upper-bound simplification — it ignores mines/plants
already retired since 2020 — not a forecast of likely coal demand.

**Correction (2026-08-28): production, not consumption, and coal/lignite
split.** The original draft used Eurostat's Gross Inland Consumption (GIC)
of all solid fossil fuels combined (SIEC `C0000X0350-0370`) at a single
blended 0.34 tCO2/MWh intensity, giving 617.2 MtCO2-eq. That double-counts
imports as if they were domestic supply: in this country scope, **hard
coal is ~64% imported** (2020: 1,052,769 GWh consumed vs. only 380,259 GWh
domestically produced), while **lignite is ~100% domestic** (762,560 GWh
consumed vs. 746,533 GWh produced — lignite's low energy density makes it
uneconomical to transport, so there's essentially no import/export market
for it). "Domestic-safe" should mean *production*, not consumption, and
hard coal and lignite should use their own model intensities (0.3361 and
0.4069 tCO2/MWh respectively) rather than one blended rate.

**Corrected 2020 domestic coal+lignite production: 431.6 MtCO2-eq** (hard
coal 127.8 + lignite 303.8), not 617.2. Per-country (production-based):
**Poland 163.8** (hard coal 122.0 — effectively ALL of this scope's
domestic hard coal — plus lignite 41.8), **Germany 110.7** (lignite only;
German hard-coal mining ended in 2018, so Germany's remaining "coal" use is
mostly imported hard coal, correctly excluded here), **Czechia 47.0**,
Serbia 34.1, Bulgaria 17.7, Bosnia 15.8, Romania 12.3, Greece 7.7, Kosovo
7.4, Hungary 4.4, plus ~10.4 MtCO2-eq of trace producers. Serbia, Bosnia,
and Kosovo are non-EU and have no binding coal phase-out commitment found —
treated as indefinitely available (no phase-out) in the comparison below,
which is the realistic assumption, not an oversight.

#### 4.3.1. Why "flat, no phase-out" is the recommended treatment (not just a default)

Checked directly against the model's own code (`scripts/prepare_sector_network.py`),
not assumed:

- **Coal is one shared, fungible pool.** A single `"EU coal"` bus/Generator
  feeds *all three* downstream uses this fork models: coal power plants,
  the generic `"coal for industry"` Load (JRC-IDEES industrial coal+coke
  demand), and — since steel is now endogenous (upstream PR #1719) — the
  **BOF steelmaking route**, which draws coking coal from `bus0="EU coal"`
  (`costs.at["blast furnace-basic oxygen furnace", "coal-input"]`) and
  competes economically against the EAF+H2-DRI route. The model does not
  distinguish coal grade (coking vs. thermal) — it's all interchangeable
  MWh from one pool at one CO2 intensity.
- **Lignite is a fully separate pool, power-only.** A dedicated `"EU
  lignite"` bus with no industrial or steel pathway found anywhere in the
  code — matches reality (lignite is too low-grade for blast furnaces).

Because the model can't distinguish "coal reserved for steel" from "coal
for power" (it's one pool, allocated by the LP's own economics), imposing
an external phase-out schedule on the *security ceiling* fights a
distinction the model doesn't make, and pre-judges an outcome (how much
coal survives, and for which use) that the model's own CO2Limit constraint
plus the endogenous BOF-vs-EAF+H2-DRI competition is already set up to
determine. **Conclusion: set the ceiling to real national production
potential (flat, 431.6 MtCO2-eq) and let the model decide how much of it
actually gets used, and for what — consistent with the general principle
in Section 4 ("treat coal like the other fossil fuels")**.

#### 4.3.2. Sensitivity case: phase-out schedule (NOT the recommended treatment)

An earlier exploratory pass built a per-country phase-out schedule
(companion script `text_docs/scripts/compare_coal_treatment.py`, outputs
`coal_treatment_comparison.png` / `coal_treatment_2050_mix.png`), kept
here only as a labeled sensitivity case:

| Year | No coal | With coal (flat, recommended) | With coal phase-out (sensitivity) |
|-----:|------:|------:|------:|
| 2020 | 685.2 | 1116.8 | 1116.8 |
| 2025 | 685.2 | 1116.8 | 1109.1 |
| 2030 | 556.8 |  988.4 |  964.0 |
| 2035 | 380.9 |  812.5 |  577.3 |
| 2040 | 302.8 |  734.4 |  370.8 |
| 2045 | 239.7 |  671.3 |  307.7 |
| 2050 | 181.6 |  613.2 |  249.6 |

This used **Poland overridden to 2035** (real target: 2049) alongside
other countries' real dates (Greece 2025, Hungary/Romania 2030, Czechia
2035, Germany/Bulgaria 2040). Poland alone is ~38% of this scope's
domestic coal+lignite, so the override drove most of the gap. Beyond the
override itself being unrealistic, this approach has two structural
problems (see 4.3.1): it applies one cutoff to a mixed coal+lignite total
that should really be split by end-use (lignite → power-only, hard coal →
power *and* steel), and it bakes in a policy outcome the model's own
CO2Limit + endogenous steel competition should be left to determine
instead. The real per-country phase-out dates (Beyond Fossil Fuels,
"National coal phase-out announcements in Europe," 2021,
`text_docs/literature/BeyondFossilFuels_2021_coal_phaseout_announcements.pdf`)
remain useful for sanity-checking a solved model's own coal phase-down
against real policy commitments — as a check on model *output*, not as an
input constraint on the security ceiling.

### 4.4. Combined ceiling and comparison

All three variants share the same 2020 point (`limit(2020) = 2768.2`,
`share = 40.3%`) by construction, and reach their target share EXACTLY at
2050 — no more checking after the fact whether the share exceeded 100%.
Numbers below use the corrected production-based coal figure (431.6, not
617.2 — see Section 4.3) and the 34-country anchor (2768.2, Eurostat +
Switzerland/BAFU — see Section 3). Displayed plots start at 2025 (Section
3.1's caveat on 2020 as a displayed year), but the 2020 anchor point is
kept in this table for reference.

| Year | NO+UK+coal ceiling | **100% by 2050** total (share) | **80% by 2050** total (share) | **60% by 2050** total (share) | CO2Limit (~1.9C) |
|-----:|------:|------:|------:|------:|------:|
| 2020 | 1116.8 | 2768.2 (40.3%) | 2768.2 (40.3%) | 2768.2 (40.3%) | 3314.9 |
| 2025 | 1116.8 | 2494.9 (44.8%) | 2580.3 (43.3%) | 2671.8 (41.8%) | 2983.3 |
| 2030 |  988.4 | 1770.9 (55.8%) | 1952.3 (50.6%) | 2175.0 (45.4%) | 2071.8 |
| 2035 |  812.5 | 1157.8 (70.2%) | 1350.3 (60.2%) | 1619.4 (50.2%) | 1151.0 |
| 2040 |  734.4 |  868.8 (84.5%) | 1053.4 (69.7%) | 1337.6 (54.9%) |  460.4 |
| 2045 |  671.3 |  702.3 (95.6%) |  871.1 (77.1%) | 1146.6 (58.5%) |  230.2 |
| 2050 |  613.2 |  613.2 (100.0%) |  766.5 (80.0%) | 1022.0 (60.0%) |    0.0 |

**Key findings, now with coal properly counted (production-based) and
Switzerland included in the anchor**:
- **Domestic-safe share at 2020 rises from 24.8% (gas+oil only) to 40.3%**
  once coal production (not consumption) is added — less dramatic than the
  earlier draft's 47.6%, because most of what looked like "domestic coal"
  in the consumption-based figure was actually imported hard coal. Still a
  large correction to the gas+oil-only framing: over 40% of 2020 fossil use
  could in principle come from Norway+UK+domestic coal+lignite alone.
  Adding Switzerland (Section 3) shifted this from an earlier 33-country
  40.8%/25.0% split to the current 40.3%/24.8% — a small dilution, since
  Switzerland adds only to the denominator (it has no domestic gas/oil/coal
  production of its own to add to the Norway+UK+coal numerator).
- **From 2035 onward, the NO+UK+coal ceiling (813, 734, 671, 613) exceeds
  CO2Limit (1151→0).** Confirms your framing: coal availability is not the
  late-horizon constraint, the climate target is — though the crossover is
  a bit later than the pre-correction estimate suggested (2035 vs. 2040).
- All three self-sufficiency variants' 2050 floors (613 / 767 / 1022) sit
  **far above** CO2Limit's 2050 value of zero — the security-vs-net-zero
  tension holds regardless of the coal correction. Reconciling "use
  domestic coal for security" with "net-zero by 2050" essentially requires
  CCS on nearly all coal-fired generation/industry by 2050, or accepting
  that coal (however "secure") simply isn't used at that point regardless
  of availability.
- The phase-out sensitivity case (Section 4.3.2) shows what an *unrealistic*
  Poland-2035 override would do (2050 ceiling drops from 613 to 250
  MtCO2-eq) — not adopted; kept only to illustrate how much Poland's own
  date choice would matter if it were ever revisited with real dates.

See `fossil_supply_with_coal_security.png` for the combined figure and
`fossil_supply_with_coal_mix_2050.png` for the 2025-vs-2050 resource-mix
breakdown (Norway / UK / EU-domestic coal+lignite, stacked). For the
no-coal comparison, see `fossil_supply_no_coal_security.png` /
`fossil_supply_no_coal_mix_2050.png`.

## 5. Biomass: sustainable vs. unsustainable potential (added 2026-09-01)

The mix-breakdown charts (Section 4.4's figures) now add sustainable and
unsustainable biomass potential as two further stacked segments, alongside
Norway/UK(/coal). This is a genuinely different kind of quantity from the
rest of the chart — biomass is not part of the "how much fossil supply can
Europe secure domestically" question Sections 1-4 are about — so it is
shown with a hatched fill, visually distinct from the solid-fill fossil
segments, rather than implying it counts toward the same security ceiling.
It is included because it is a real substitute/alternative that eases
reliance on the uncertain fossil residual, which is directly relevant
context for the same chart.

### 5.1. How the model currently treats biomass CO2 (checked directly in code)

Checked against `scripts/prepare_sector_network.py`, not assumed:

- **Sustainable solid biomass and biogas** (the plain `"solid biomass"` /
  `"biogas"` Generators, `add_generators`-region, ~line 4895-4913): feed
  directly into their own dedicated bus with **no `bus2`/CO2-atmosphere
  connection at all** — genuinely zero CO2 charged anywhere for direct
  combustion of these carriers, consistent with treating them as carbon-
  neutral (combustion CO2 assumed reabsorbed by regrowth).
- **Unsustainable solid biomass and unsustainable biogas** (~line
  4977-4988): same treatment — plain Generators, no CO2-atmosphere link.
  Zero CO2 charged, identical to the sustainable case. This confirms the
  premise motivating this section: whatever upstream/indirect land-use
  emissions these feedstocks carry in reality, this model currently
  allocates none of them here (implicitly assuming they are accounted for
  elsewhere, e.g. in the agricultural sector's own inventory — which this
  model does not otherwise represent in detail, see the note on
  agriculture non-CO2 emissions in
  `text_docs/text/lulucf_deviation_methodology.md` Section 1).
- **Unsustainable bioliquids is the one exception**, but not in the way it
  first appears: its conversion Link into the shared oil pool
  (`bus0=`unsustainable bioliquids`, bus1=oil, bus2="co2 atmosphere"`) carries
  `efficiency2 = -costs.at["oil", "CO2 intensity"]`. Working through
  PyPSA's multi-link sign convention (positive efficiency on an output bus
  = injects into it; negative = withdraws from it), this is a **credit**
  that cancels out the fixed fossil-equivalent CO2 charge every downstream
  oil-consuming link applies regardless of the oil pool's actual blend
  (the same "blend-origin blindness" pattern noted elsewhere in this
  fork's work — pooled fuel buses can't track where their contents
  actually came from). Net effect: unsustainable bioliquids' carbon is
  *also* effectively treated as zero/neutral overall, just via a different
  mechanical route (a supply-side credit instead of simply no link at
  all). Not directly relevant to the solid biomass/biogas potential
  plotted here, but worth knowing before extending this treatment to
  liquid biofuels.
- **A real precedent for exactly this kind of correction already exists in
  the code**: `options["solid_biomass_import"]["upstream_emissions_factor"]`
  (~line 4914-4949) applies `efficiency2 = upstream_emissions_factor *
  costs.at["solid biomass", "CO2 intensity"]` on a *separate* "solid
  biomass import" pathway (traded/imported biomass), a positive charge
  (genuine emission) proportional to a configurable fraction of solid
  biomass's own CO2 intensity. The proxy introduced below for
  unsustainable (domestic) biomass follows the same pattern, just applied
  to a different biomass category that currently has no equivalent
  config option.

### 5.2. The upstream-emissions proxy

- **Unsustainable biomass: 30 kgCO2e/GJ = 0.108 tCO2/MWh**, applied
  uniformly (not per-feedstock) as a general placeholder for the indirect
  land-use-change (iLUC) and cultivation/processing emissions this
  category's real-world feedstocks would carry. Sourcing check: the EU's
  own default iLUC emission factors (Directive (EU) 2018/2001, "RED II",
  Annex VIII Part A, as amended by Delegated Regulation (EU) 2019/807,
  <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=uriserv%3AOJ.L_.2019.133.01.0001.01.ENG>)
  span roughly 12-13 gCO2eq/MJ for cereal/other-starch/sugar-crop
  feedstocks up to ~55 gCO2eq/MJ for oil crops (oil crops' iLUC factor is
  reported as roughly 4x the cereal/sugar-crop tier). 30 gCO2eq/MJ sits
  between these two tiers — a reasonable general "mixed feedstock"
  placeholder for a first pass, not a feedstock-specific estimate. **Caveat**:
  the exact numeric table in Annex VIII Part A was not independently
  re-verified against the primary legal text in this session (site
  rendering issues); the 12/13/55 figures above are recalled from prior
  general knowledge of this regulation, corroborated only for the
  relative structure (oil crops ~4x cereals/sugar), not re-confirmed
  digit-for-digit. Re-verify directly from the Delegated Regulation's own
  Annex table before using this document's number in anything
  publication-grade.
- **Sustainable biomass (forest residues, in this simplification): 0
  tCO2/MWh** — no upstream charge, per the model's own existing treatment
  and the assumption that genuine forest-residue sourcing carries no
  material iLUC risk.
- Implemented as `UNSUSTAINABLE_BIOMASS_TCO2_PER_MWH` /
  `SUSTAINABLE_BIOMASS_TCO2_PER_MWH` in
  `text_docs/scripts/build_fossil_supply_security.py`.

### 5.3. Biomass potential volumes (2025 vs. 2050)

Source: `resources/base_myopic_50_8h/biomass_potentials_s_50_{year}.csv`
on the cluster — this fork's own biomass-potential-building pipeline
output (per-node potentials across all 50 clustered nodes, summed here to
a network-wide total). This is a **potential/cap**, matching the rest of
this document's framing — not solved dispatch (see the scope note at the
top of this document). "Sustainable" = `solid biomass` + `biogas` columns;
"unsustainable" = `unsustainable solid biomass` + `unsustainable biogas` +
`unsustainable bioliquids` columns (`municipal solid waste` and `not
included` excluded — not a combustible biomass potential relevant here).

| Year | Sustainable (TWh) | Unsustainable (TWh) |
|-----:|------:|------:|
| 2025 | 13.6 | 1595.7 |
| 2050 | 1371.1 | 0.0 |

**A striking transition, directly visible in the model's own input data**:
unsustainable biomass potential is large in 2025 (a legacy resource pool
not yet meeting stricter future sustainability criteria) and falls to
exactly zero by 2050, while sustainable (certified) potential grows from a
small base to become the dominant biomass resource — matching the "biomass
transitions from unsustainable to sustainable with a cap" framing this
section started from. Converting each to MtCO2-eq with the factors above:

| Year | Sustainable (MtCO2-eq) | Unsustainable (MtCO2-eq) |
|-----:|------:|------:|
| 2025 | 0.0 | 172.3 |
| 2050 | 0.0 | 0.0 |

**Key finding**: the upstream-emissions penalty from biomass is a
**2025-only, transitional issue** in this model's own input data — it
disappears entirely by 2050 as unsustainable biomass potential is fully
retired, not because the emissions factor changes, but because the
underlying volume goes to zero. The energy-basis panel of each
`_mix_2050.png` figure shows the full magnitude of this transition (up to
~1600 TWh/yr of unsustainable biomass potential in 2025, replaced by
~1370 TWh/yr of sustainable potential by 2050) even though the
emissions-basis panel shows almost nothing by 2050.

### 5.4. Per-fuel, per-region split for the mix chart (added 2026-09-01)

The mix charts now show all six horizons (2025-2050), not just the
2025/2050 endpoints, and split each region into its underlying fuels
(Norway gas/oil, UK gas/oil, EU-domestic hard coal/lignite) instead of one
combined bar per region. Colour identifies the **fuel** (this fork's own
`config/plotting.default.yaml` `tech_colors` — the same palette the
`results/` folder's plots use, so the two sets of figures are visually
consistent), hatch identifies the **country/region** (Norway = dots, UK =
cross-hatch, EU-domestic = solid/no hatch, since there is nothing else
EU-domestic to distinguish it from on this chart — deliberately different
symbols (for Norway/UK) from
the biomass sustainability hatches, `//`/`\\`, used on the same chart, so
the two hatch "dimensions" don't visually collide).

**Norway's gas/oil split** is backed out of the blended intensity already
chosen in Section 4.1 (`NO_BLENDED_INTENSITY = 0.22` tCO2/MWh) rather than
introducing new unsourced per-fuel production data: solving
`0.22 = x·0.198 + (1-x)·0.2571` for the gas energy-share `x` gives
**62.8% gas / 37.2% oil by energy**, held constant across all years (the
blend itself was never assumed to shift over time).

**UK's gas/oil split** reuses the same 218 Mt oil / 2060 TWh gas
cumulative remaining-reserve split already used to build
`UK_BLENDED_INTENSITY` (Section 4.2): **55.2% oil / 44.8% gas by energy**.
This assumes oil and gas deplete at the same relative rate under the
single decay curve fitted to the *combined* boe/d rate — a simplification,
since in reality the reserve mix could shift over 2025-2050 (e.g. if gas
fields deplete faster than oil fields or vice versa); no separate
oil-only/gas-only decay data was found to check this against.

**EU-domestic coal** was already split into hard coal (127.8 MtCO2-eq)
and lignite (303.8 MtCO2-eq) with their own model intensities in Section
4.3 — the mix chart now simply displays that existing split rather than
combining it into one segment.

**Biomass potential volumes, all six years** (extending Section 5.3's
2025/2050-only table): same source
(`resources/base_myopic_50_8h/biomass_potentials_s_50_{year}.csv`), now
read for every horizon.

| Year | Sustainable (TWh) | Unsustainable (TWh) |
|-----:|------:|------:|
| 2025 | 13.6 | 1595.7 |
| 2030 | 465.6 | 1053.2 |
| 2035 | 912.2 | 526.6 |
| 2040 | 1366.7 | 0.0 |
| 2045 | 1368.9 | 0.0 |
| 2050 | 1371.1 | 0.0 |

This fills in the transition shape only sketched by the two endpoints
before: unsustainable potential declines roughly linearly 2025-2040
(reaching exactly zero at 2040, not gradually approaching it), while
sustainable potential grows to fill the gap and plateaus from 2040
onward.

Each `_mix_2050.png` figure also now carries an on-figure note stating the
30 kgCO2e/GJ unsustainable-biomass assumption directly (Section 5.2),
rather than requiring the reader to consult this document separately.

## 6. Open items / next steps

- **Re-verify the RED II Annex VIII iLUC factor table** (Section 5.2)
  against the Delegated Regulation (EU) 2019/807 primary text directly —
  the 12/13/55 gCO2eq/MJ figures used to sanity-check the 30 gCO2eq/MJ
  proxy were recalled, not re-confirmed digit-for-digit, in this session.
- **The 30 kgCO2e/GJ unsustainable-biomass factor is a flat, feedstock-
  agnostic placeholder** — refining it (e.g. separately for unsustainable
  solid biomass vs. unsustainable biogas vs. unsustainable bioliquids,
  which likely have quite different real feedstock mixes) is a natural
  next step if this needs to be more than a first-pass proxy.
- ~~Coal decline curve~~ — resolved (Section 4.3.1): held flat at 2020
  production level deliberately, not a placeholder-pending-more-research.
  A political phase-out schedule is explicitly NOT applied to the ceiling,
  since the model's own CO2Limit + endogenous BOF-vs-EAF+H2-DRI steel
  competition should determine actual coal use, and the model can't
  distinguish coal end-use anyway (one fungible "EU coal" pool). The
  phase-out sensitivity case (4.3.2) remains for comparison only.
  Still open: consider a "second EU-domestic tier" for Denmark, Romania
  (Neptun Deep gas), and Poland's small conventional/shale gas output,
  which are still folded into the non-European residual.
- **Smoothstep shape**: the three variants' *target* endpoints (100/80/60%
  by 2050) are now bounded correctly by construction, but the *steepness*
  of the climb between 2020 and 2050 is still a free choice baked into the
  smoothstep polynomial's fixed form — worth discussing whether that should
  itself be anchored to something.
- **Download Sodir's primary Resource Report 2024 PDF** directly (currently
  only searched/summarized, not saved to `text_docs/literature/`).
- **NSTA source is the 2019-vintage PDF**, not the current 2025 data used
  for the actual e0/2030 figures (those came from 2025 news coverage of
  NSTA's more recent output, not a directly downloaded primary document).
  Should locate and download NSTA's current production-projection report.
- **African pipeline tier and LNG residual** (your second/third tiers)
  entirely unaddressed — this document only covers the "safe domestic"
  tier (Norway + UK + EU coal).
- Norway's 2030/2040/2045 figures are back-solved/interpolated, not
  directly reported — flagged inline above, worth tightening if the Sodir
  primary report has more granular year-by-year figures.
