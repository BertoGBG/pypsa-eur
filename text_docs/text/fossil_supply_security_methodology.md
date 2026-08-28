# Fossil-supply energy-security limit — methodology and sourcing (DRAFT)

Branch: `heat_industry`. Relates to `fossil_limit` / `fossil_limit_values` in
`config/config.default.yaml`, consumed by `add_fossil_fuel_limit()` in
`scripts/prepare_sector_network.py`.

Companion scripts: `text_docs/scripts/build_fossil_supply_security.py`
(produces `fossil_supply_security.png` and `fossil_supply_mix_2050.png`)
and `text_docs/scripts/compare_coal_treatment.py` (produces
`coal_treatment_comparison.png` and `coal_treatment_2050_mix.png`, a
three-way no-coal/flat-coal/phased-coal comparison) — both print their
full numeric tables to stdout.

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
empirically-grounded value `(NO+UK+coal)(2020) / ceiling` (~40.8%, once
coal is included on a production basis — see Section 4.3) for every
variant; `share(2050)` is
set to a chosen target (100%, 80%, or 60% self-sufficiency). Then invert:
`limit(t) = (NO+UK+coal)(t) / share(t)`. Because all three variants share
the same `share(2020)`, they necessarily all start at exactly the same
2020 point (`limit(2020) = ceiling` for every variant), diverging only as
they head toward different 2050 outcomes.

- **Ceiling** (2020, genuine historical actual — not a proxy): **2739.0
  MtCO2-eq/yr**. Computed from **Eurostat's Complete Energy Balances**
  (`nrg_bal_c`), **Gross Inland Consumption (GIC)** — i.e. real physical
  fuel-supply volumes, not derived emissions — of natural gas (SIEC
  `G3000`) + oil & petroleum products excl. biofuels (`O4000XBIO`) + solid
  fossil fuels (`C0000X0350-0370`), summed across 33 of this fork's 34
  countries (all except Switzerland, which this Eurostat dataset does not
  cover). Source file: `data/eurostat_balances/archive/2026-02/estat_nrg_bal_c.tsv.gz`
  on the cluster — this fork's own live-pipeline data cache (Eurostat's own
  published data, archived there Feb 2026, so genuinely current). A compact
  per-country/per-fuel extract is saved at
  `text_docs/literature/eurostat_GIC_fossil_by_country_2020_scope.csv` for
  reproducibility (the 273MB raw bulk file itself was not committed — it is
  pypsa-eur's own re-fetchable data cache, not at risk of being lost the way
  a manually-written note would be).

  This supersedes an earlier draft of this document that used a **2018,
  emissions-based** proxy (EEA/UNFCCC `build_co2_totals.py` pipeline, which
  the fork only has archived up to 2018) — that number ALSO originally
  undercounted by omitting direct industrial fuel combustion and
  agriculture-machinery fuel. Both problems are now fixed: real 2020 data,
  full sector/fuel coverage via Eurostat's economy-wide GIC measure (which
  by construction includes every combustion sector — power, industry,
  transport including road gasoline/diesel, buildings, agriculture — with no
  per-sector column list to accidentally miss one from).

  Cross-check years from the same source: 2018 = 3616.4, 2023 = 2628.7,
  **2024 (latest actual) = 2554.9** MtCO2-eq. The 2024 actual sits close to
  this config's own assumed `fossil_limit_values[2025] = 2600` — a
  reassuring independent cross-validation of that existing assumption.
- **Floor** (2050): the Norway+UK+coal production ceiling, **613.2 MtCO2-eq/yr**
  central case (Section 4, using the corrected production-based coal figure
  — see Section 4.3) — this is exactly the "100% by 2050" variant's
  endpoint; the 80% and 60% variants have higher 2050 endpoints (766.5 and
  1022.0 MtCO2-eq respectively), since they deliberately leave room for
  non-European sources (Africa pipeline + LNG) even at 2050.
- **Three variants**, same shape, different 2050 self-sufficiency target:

  | Variant | Share(2020) | Share(2050) | Total limit(2050) |
  |---|---:|---:|---:|
  | 100% NO+UK+coal by 2050 | 40.8% | 100.0% | 613.2 |
  | 80% NO+UK+coal by 2050 | 40.8% | 80.0% | 766.5 |
  | 60% NO+UK+coal by 2050 | 40.8% | 60.0% | 1022.0 |

  The shape/steepness itself (how fast the share climbs between 2020 and
  2050) is still a free choice baked into the smoothstep polynomial's fixed
  form — this is the remaining "shape matters in the middle years"
  question, now scoped to just that, rather than also needing to separately
  verify the share stays bounded.
  See `fossil_supply_security.png` (single combined figure, Section 4.4).

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

**Three-way comparison** (companion script
`text_docs/scripts/compare_coal_treatment.py`, outputs
`coal_treatment_comparison.png` and `coal_treatment_2050_mix.png`),
produced to directly compare the effect of coal treatment on the
Norway+UK+coal ceiling:

| Year | No coal | With coal (corrected, flat) | With coal phase-out (Poland 2035) |
|-----:|------:|------:|------:|
| 2020 | 685.2 | 1116.8 | 1116.8 |
| 2025 | 685.2 | 1116.8 | 1109.1 |
| 2030 | 556.8 |  988.4 |  964.0 |
| 2035 | 380.9 |  812.5 |  577.3 |
| 2040 | 302.8 |  734.4 |  370.8 |
| 2045 | 239.7 |  671.3 |  307.7 |
| 2050 | 181.6 |  613.2 |  249.6 |

Phase-out years used (rounded onto the model's own 5-year grid): Greece
2025, Hungary/Romania 2030, **Poland 2035 (overridden from its real 2049
target, per instruction)**, Czechia 2035, Germany/Bulgaria 2040. Poland's
override has an outsized effect — as ~38% of this scope's domestic
coal+lignite, moving its phase-out 14 years earlier is most of the gap
between the "flat" and "phase-out" curves from 2035 onward.

(The phase-out timeline research done earlier — Beyond Fossil Fuels,
"National coal phase-out announcements in Europe," 2021,
`text_docs/literature/BeyondFossilFuels_2021_coal_phaseout_announcements.pdf`
— most of Western/Southern Europe targeting 2025-2033, Poland the outlier
at 2049 — remains useful context for interpreting model *output*, i.e. for
sanity-checking whether the solved model's own coal phase-down looks
plausible against real policy commitments. It is deliberately NOT used to
constrain the security ceiling itself, per the reasoning above.)

### 4.4. Combined ceiling and comparison

All three variants share the same 2020 point (`limit(2020) = 2739.0`,
`share = 40.8%`) by construction, and reach their target share EXACTLY at
2050 — no more checking after the fact whether the share exceeded 100%.
Numbers below use the corrected production-based coal figure (431.6, not
617.2 — see Section 4.3).

| Year | NO+UK+coal ceiling | **100% by 2050** total (share) | **80% by 2050** total (share) | **60% by 2050** total (share) | CO2Limit (~1.9C) |
|-----:|------:|------:|------:|------:|------:|
| 2020 | 1116.8 | 2739.0 (40.8%) | 2739.0 (40.8%) | 2739.0 (40.8%) | 3314.9 |
| 2025 | 1116.8 | 2472.9 (45.2%) | 2556.8 (43.7%) | 2646.6 (42.2%) | 2983.3 |
| 2030 |  988.4 | 1760.8 (56.1%) | 1940.1 (50.9%) | 2159.9 (45.8%) | 2071.8 |
| 2035 |  812.5 | 1154.3 (70.4%) | 1345.4 (60.4%) | 1612.5 (50.4%) | 1151.0 |
| 2040 |  734.4 |  867.6 (84.6%) | 1051.7 (69.8%) | 1334.9 (55.0%) |  460.4 |
| 2045 |  671.3 |  702.1 (95.6%) |  870.7 (77.1%) | 1146.0 (58.6%) |  230.2 |
| 2050 |  613.2 |  613.2 (100.0%) |  766.5 (80.0%) | 1022.0 (60.0%) |    0.0 |

**Key findings, now with coal properly counted (production-based)**:
- **Domestic-safe share at 2020 rises from 25.0% to 40.8%** once coal
  production (not consumption) is added — less dramatic than the earlier
  draft's 47.6%, because most of what looked like "domestic coal" in the
  consumption-based figure was actually imported hard coal. Still a large
  correction to the gas+oil-only framing: over 40% of 2020 fossil use could
  in principle come from Norway+UK+domestic coal+lignite alone.
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
- See `coal_treatment_comparison.png` / `coal_treatment_2050_mix.png`
  (companion script `compare_coal_treatment.py`) for a direct three-way
  comparison of no-coal vs. flat-coal vs. phased-coal-out (Poland 2035)
  treatments — phasing out coal on realistic national schedules (Poland
  overridden to 2035 vs. its real 2049 target) cuts the 2050 domestic
  ceiling from 613 down to 250 MtCO2-eq, since Poland alone is ~38% of
  this scope's domestic coal+lignite.

See `fossil_supply_security.png` for the combined figure and
`fossil_supply_mix_2050.png` for the 2020-vs-2050 resource-mix breakdown
(Norway / UK / EU-domestic coal, stacked).

## 5. Open items / next steps

- **Coal decline curve**: currently held flat at the 2020 level for the
  whole horizon (a deliberate upper bound, see Section 4.3) rather than
  reflecting actual mine/plant retirements already underway. A real
  production-decline curve grounded in national retirement schedules
  (Germany's Kohleausstiegsgesetz, Poland's PEP2040, etc.) would tighten
  this, but was time-boxed out of this session.
  Additionally: consider a "second EU-domestic tier" for Denmark, Romania
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
