# LULUCF / Agriculture CO2-limit deviation — methodology and sourcing

Branch: `heat_industry`. Implements `lulucf_deviation_values` in
`config/config.default.yaml`, consumed by `add_co2limit()` in
`scripts/prepare_sector_network.py`.

## 1. The assumption being challenged

PyPSA-Eur's `co2_budget.limit` (fraction of 1990 sectoral CO2 emissions) is a
**CO2-only** budget over the sectors the model represents (power, industry,
transport, heat, etc.). It never includes LULUCF, and its only representation
of "agriculture" is CO2 from agricultural-machinery fuel combustion — not the
full N2O/CH4 AFOLU account (see `determine_emission_sectors` in
`scripts/prepare_sector_network.py`).

The EU's own net-zero framing, however, is economy-wide **including**
LULUCF: the pledge implicitly assumes the land sink absorbs a specific amount
of CO2 every year, on top of the modelled sectors' own reductions. If the real
LULUCF sink under- or over-performs relative to that implicit assumption, the
modelled sectors must pick up the slack to preserve the same net climate
outcome — otherwise the model silently inherits a sink that doesn't exist.
`lulucf_deviation_values` is a year-indexed MtCO2/yr correction applied to the
`CO2Limit` GlobalConstraint to compensate for this gap. Positive value = sink
underperforms -> CO2Limit tightened by that amount; negative = sink
overperforms -> CO2Limit loosened.

**Baseline assumption (explicit, not sourced)**: the LULUCF Regulation (EU)
2023/839 sets a binding EU-27 net removal target only for 2030 (-310
MtCO2e/yr). No binding target exists for 2035-2050. We hold the 2030 target
flat as the reference for all later years. This is a modelling choice, not a
literature fact — an equally defensible alternative would let the reference
itself tighten in line with the EU's deepening 2040/2050 ambition, which
would produce larger deviations than reported here. We chose the flat
reference because it is simpler and avoids stacking one uncertain assumption
(the 2040/2050 reference itself) on top of another (the sink's future
performance).

## 2. Why the sink is underperforming — literature review

**Primary EU legal/official sources:**

- LULUCF Regulation (EU) 2023/839, Art. 4 / Annex IIa — sets the -310
  MtCO2e/yr EU-27 net removal target for 2030. This is the *target* side of
  every deviation number below.
- European Commission, *EU Climate Action Progress Report 2025*, Ch. 4
  "Land use sector" —
  <https://climate.ec.europa.eu/eu-action/climate-strategies-targets/progress-climate-action/eu-climate-action-progress-report-2025/chapter-4-land-use-sector_en>.
  Official EC status document; confirms the land sink is on a declining
  trajectory relative to the Regulation's target.
- European Environment Agency, "Europe's land carbon sink declines but its
  potential stays high" (newsroom, 2024/2025) —
  <https://www.eea.europa.eu/en/newsroom/news/europes-land-carbon-sink-declines-but-its-potential-stays-high>.
  Net sink fell ~30% from 2014-2023 versus the prior decade.
- CAP Reform, "LULUCF targets off-course" (2025) —
  <https://capreform.eu/lulucf-targets-off-course/>. Not itself a primary
  source, but the clearest available relay of the EEA Member State 2024 GHG
  projections submissions (the actual WEM/WAM 2030 numbers used below); the
  underlying EEA submissions are not published as a single readable EU-27
  aggregate elsewhere.

**Peer-reviewed, high-impact-journal sources on *why*:**

- Migliavacca, Grassi, et al., "Securing the forest carbon sink for the
  European Union's climate ambition," *Nature* 643, 1203-1213 (2025).
  <https://www.nature.com/articles/s41586-025-08967-3>. Using the EU GHG
  inventory (EEA, 2024), documents the EU forest sink falling from an average
  of -456.9 MtCO2e/yr (2010-2014) to -332.6 MtCO2e/yr (2020-2022), a ~27%
  decline, driven by ageing stands, increased harvest, and climate-driven
  disturbances, "with no sign of the trend reversing under current policy."
- [authors not yet confirmed against the primary article — see caveat below],
  "Accelerating biomass loss from forest disturbances across Europe," *Nature
  Geoscience* (2026). <https://www.nature.com/articles/s41561-026-02032-y>.
  Satellite-based (ESA Climate Change Initiative), covering 1985-2023: gross
  aboveground biomass loss totalled 6.5 +/- 0.8 Pg, 82% from stand-replacing
  harvest and 18% from high-severity natural disturbance. From 2018 onward,
  annual losses increased 46% to levels unprecedented in the prior four
  decades, coinciding with a surge in drought-linked bark-beetle outbreaks.
  Estimates that European forest carbon-sink capacity "likely decreased by
  39%" over 2010-2030. **Caveat**: I could not obtain the full text (paywalled
  redirect); the figures above come from search-result summaries and a
  secondary press digest, not a direct read of the article. Verify author
  list, exact wording, and the 39% figure's precise definition before citing
  this in any publication-facing text.
- "EU policy on forest carbon sinks revisited," *ScienceDirect* (Feb 2026).
  <https://www.sciencedirect.com/science/article/pii/S1462901126000250>.
  Global forest-sector economic model: closing the gap to the 2030 sink
  target through forest management alone would require cutting EU+Norway
  roundwood harvest by 113-117 million m3/yr in 2030-2035 relative to a
  market-driven baseline, at a marginal abatement cost exceeding EUR
  700/tCO2. Supports treating the shortfall as structurally persistent rather
  than self-correcting: the cheapest lever (reduced harvest) is far more
  expensive here than in most other sectors, so it is unlikely to be pulled
  at the scale needed.
- "Alarming decline in the carbon sink of European forests driven by
  disturbances," *National Science Review* (Oxford Academic). Found via
  search; not yet read in full — listed here as a candidate corroborating
  source, not yet verified or cited with confidence.

## 3. Forecast / extrapolation literature for 2035-2050

- European Commission, Impact Assessment accompanying the Communication on
  the 2040 climate target (the "90% net GHG reduction by 2040" proposal).
  Summarized in: Springer, K. & Bognar, J., "EU LULUCF sink development
  until 2040: Trends, projections and uncertainties," IEEP briefing (13
  March 2025) —
  <https://ieep.eu/publications/eu-lulucf-sink-development-until-2040-trends-projections-and-uncertainties/>,
  PDF:
  <https://ieep.eu/wp-content/uploads/2025/03/EU-LULUCF-sink-development-until-2040-Trends-projections-and-uncertainties-IEEP-2025.pdf>.
  This is the only source found that models the EU-27 LULUCF sink out to
  2040 under the Commission's own core policy scenarios (S1/S2/S3, varying
  overall climate ambition and associated land-use/bioeconomy policy). The
  reported 2040 range is approximately **-215 to -218 MtCO2e/yr** under the
  weakest scenario (little additional LULUCF-specific policy beyond what's
  already legislated) up to **-317 to -376 MtCO2e/yr** under stronger
  scenarios (active post-2030 land-sink policy).
  **Caveat, important**: I was not able to extract clean text from the
  primary PDF (it returned as a compressed/scanned stream) or reach the
  Commission's own Impact Assessment SWD directly. The numbers above are
  triangulated from two different secondary search summaries and differ
  slightly between them (215 vs. 217/218; the identity of which scenario
  produces which number is not confirmed). **Before this is used for
  anything beyond an internal working assumption, the primary SWD should be
  located and these numbers re-extracted directly.**
- No literature was found projecting the EU-27 LULUCF sink specifically for
  2045 or 2050. Both the BAU and optimistic scenarios below hold their 2040
  value flat beyond 2040, purely for lack of any sourced alternative — this
  is a placeholder, not a forecast.

## 4. Three scenarios

All values are `lulucf_deviation_values` in MtCO2/yr (positive =
tighten CO2Limit, i.e. sink underperforms the flat -310 MtCO2e/yr
reference). 2020 = 0 in all scenarios (assumed on-track starting point,
not empirically derived). 2025 values are linear interpolations between
2020's assumed 0 and each scenario's own sourced 2030 anchor — not
independently sourced.

| Year | Pessimistic | BAU (central) | Optimistic |
|-----:|------------:|---------------:|-----------:|
| 2020 |           0 |              0 |          0 |
| 2025 |          64 |             64 |         39 |
| 2030 |         127 |            127 |         77 |
| 2035 |         191 |            110 |          6 |
| 2040 |         254 |             94 |        -66 |
| 2045 |         318 |             94 |        -66 |
| 2050 |         381 |             94 |        -66 |

**How each column is built:**

- **Pessimistic** = straight-line continuation of the 2020->2030 WEM
  decline slope (12.7 MtCO2/yr^2). This is the scenario currently active in
  `config.default.yaml` (unchanged numbers). Justification for calling it
  *pessimistic* rather than *central*: the peer-reviewed literature (Section
  2) reports an accelerating, disturbance-driven decline with "no sign of
  reversal," so a naive continuation of even the historical WEM slope may
  understate the true risk, not overstate it.
- **BAU (central)** = 2030 WEM anchor (-183 MtCO2e/yr, same as pessimistic's
  2030 point by construction) interpolated/extrapolated to the EC's own
  weakest 2040 Impact-Assessment scenario (~-216.5 MtCO2e/yr, midpoint of
  the 215-218 range), then held flat 2040-2050 for lack of further sourced
  data. Represents "existing EU policy continues, no new dedicated LULUCF
  intervention" — the EC's own default assumption, which happens to be less
  severe than the pure trend extrapolation.
- **Optimistic** = 2030 WAM anchor (-233 MtCO2e/yr, "with additional
  measures") interpolated/extrapolated to the EC's strongest 2040 scenario
  (-376 MtCO2e/yr), held flat thereafter. Represents effective new
  post-2030 EU land-sink/bioeconomy policy landing as intended — this
  scenario actually **overshoots** the 2030 target by 2040 (negative
  deviation, i.e. CO2Limit would be loosened, not tightened).

## 5. Open items / next steps

- Verify the IEEP-relayed EC Impact Assessment numbers (215/218/317/376)
  against the primary Commission SWD directly; current sourcing is two
  secondary summaries that don't fully agree.
- Confirm author list and exact figures for the Nature Geoscience (2026)
  paper by reading the full text (currently paywalled to automated fetch).
- Read "Alarming decline in the carbon sink of European forests driven by
  disturbances" (National Science Review) in full before citing it.
- Decide whether `config.default.yaml`'s active `lulucf_deviation_values`
  should switch from the current single "pessimistic" line to one of these
  three, or stay as-is with the others documented as sensitivities.
