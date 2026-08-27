# Fossil-supply energy-security limit — methodology and sourcing (DRAFT)

Branch: `heat_industry`. Relates to `fossil_limit` / `fossil_limit_values` in
`config/config.default.yaml`, consumed by `add_fossil_fuel_limit()` in
`scripts/prepare_sector_network.py`.

Companion script: `text_docs/scripts/build_fossil_supply_security.py`
(produces the two plots below and prints the full numeric table).

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

## 3. The sigmoid — total fossil-use limit, 2020-2050

`limit(t) = floor + (ceiling - floor) / (1 + exp(k(t - t0)))`

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
- **Floor** (2050): the Norway+UK production ceiling, **181.6 MtCO2-eq/yr**
  central case (Section 4).
- **t0, k** (inflection year, steepness): **not settled** — this is exactly
  the "shape matters in the middle years" question. Three variants are
  plotted for comparison:

  | Variant | t0 | k |
  |---|---:|---:|
  | Early, steep | 2032 | 0.35 |
  | Central, medium | 2036 | 0.28 |
  | Late, gradual | 2040 | 0.22 |

  These are placeholder choices for discussion, not derived from anything.
  See `fossil_supply_sigmoid_variants.png`.

## 4. The Norway+UK ceiling ("European-safe" fossil supply)

**Scope decision needed**: currently strictly Norway+UK. Post-Groningen
closure (NL, 2023/24, induced-seismicity driven), remaining EU-domestic
production (Denmark's declining North Sea fields, Romania's Neptun Deep gas
development, Poland's small conventional/shale output) is real but small and
**not yet included**. Worth a decision on whether to add a "second EU-domestic
tier" alongside Norway+UK, or fold it into the pipeline/LNG residual.

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

### 4.3. Combined ceiling and comparison

| Year | Norway (MtCO2eq) | UK (MtCO2eq) | **NO+UK ceiling** | Existing `fossil_limit_values` | Sigmoid (central) | NO+UK share of sigmoid |
|-----:|------:|------:|------:|------:|------:|------:|
| 2020 | 529.3 | (n/a, held at 2025 rate) | 685.2 | -- | 2710.3 | 25.3% |
| 2025 | 529.3 | 156.0 | 685.2 | 2600 | 2626.6 | 26.1% |
| 2030 | 468.3 |  88.5 | 556.8 | 1378 | 2337.2 | 23.8% |
| 2035 | 348.5 |  32.4 | 380.9 |  456 | 1638.2 | 23.3% |
| 2040 | 292.6 |  10.2 | 302.8 |  129 |  810.8 | 37.3% |
| 2045 | 236.7 |   3.0 | 239.7 |  103 |  372.0 | 64.4% |
| 2050 | 180.8 |   0.8 | 181.6 |   78 |  231.4 | 78.5% |

**The key finding**: the existing (climate-driven) `fossil_limit_values`
falls *below* the Norway+UK physical ceiling from 2040 onward — by 2040 the
existing cap (129) is only 43% of what Norway+UK alone could still supply
(303). In other words, **from ~2040 the climate constraint is already
tighter than the security-of-supply constraint** — hitting the existing
medium-scenario CO2 target would automatically keep the model within
Norway+UK's safe capacity, with no additional security-driven restriction
needed. The years where security-of-supply might actually be the *binding*
concern (i.e. total fossil use plausibly wants to exceed 100% domestic-safe
capacity) are **2025-2035**, where the ratio sits at only 23-26% — meaning
under a purely climate-driven trajectory, Europe would still be relying on
non-European sources (Africa pipeline + LNG, per your framing) for roughly
three-quarters of its fossil supply through the mid-2030s.

See `fossil_supply_security_ratio.png` for the central-sigmoid version of
this comparison (secondary axis).

## 5. Coal

Not yet incorporated into the ceiling/floor calculation above (Sections 3-4
treat "fossil" as gas+oil only, matching Norway/UK's actual output). Your
suggestion: keep a coal allowance in the early years, phased out around
2030, using whatever aggregate target is available.

Source found: Beyond Fossil Fuels, "National coal phase-out announcements in
Europe" (2021) —
`text_docs/literature/BeyondFossilFuels_2021_coal_phaseout_announcements.pdf`
— plus more recent tracker updates via
<https://beyondfossilfuels.org/europes-coal-exit/>. Picture: most Western/
Southern European coal-burning countries target **2025-2033** (Greece 2025,
Spain/Slovakia 2030, Croatia/Slovenia 2033), a middle cluster around
**2032-2040** (Romania 2032, Bulgaria 2038-40, Germany legally 2038 though
its current government is discussing 2030), and **Poland is the major
outlier**, holding a 2049 hard-coal phase-out date. A single "EU coal
phase-out by 2030" simplification is reasonable for most of Europe but
materially wrong for Poland specifically, which is not a small producer.
**Not yet modelled numerically** — needs a decision on whether to (a)
ignore Poland's later date as a simplification, explicitly flagged, or (b)
carry a small residual coal allowance out to ~2040-2049 to reflect it.

## 6. Open items / next steps

- **Scope decision**: Norway+UK only, or add a small "EU-domestic tier 2"
  (Denmark, Romania Neptun Deep, Poland)?
- **Sigmoid shape (t0, k)**: needs discussion — the three variants above are
  placeholders. Worth deciding whether the choice should itself be
  anchored to something (e.g. matching the NO+UK ceiling's own inflection
  shape) rather than picked freely.
- **Coal**: not yet quantified; needs the 2030-vs-Poland decision above
  before adding numbers.
- **Download Sodir's primary Resource Report 2024 PDF** directly (currently
  only searched/summarized, not saved to `text_docs/literature/`).
- **NSTA source is the 2019-vintage PDF**, not the current 2025 data used
  for the actual e0/2030 figures (those came from 2025 news coverage of
  NSTA's more recent output, not a directly downloaded primary document).
  Should locate and download NSTA's current production-projection report.
- **African pipeline tier and LNG residual** (your second/third tiers)
  entirely unaddressed — this document only covers the Norway+UK "safe
  domestic" tier.
- Norway's 2030/2040/2045 figures are back-solved/interpolated, not
  directly reported — flagged inline above, worth tightening if the Sodir
  primary report has more granular year-by-year figures.
