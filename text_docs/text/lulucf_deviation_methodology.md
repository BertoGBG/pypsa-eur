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

**Scope note**: this document currently addresses only the **LULUCF sink**
side of that gap (Sections 2-4 below). It does **not** yet address the
**agriculture non-CO2 (N2O/CH4)** side — the full AFOLU account beyond
machinery-fuel CO2 — which is a separate, additive correction that belongs
alongside `lulucf_deviation_values`, not inside it. That work has not
started: no literature review, no numbers, no scenario. Treat everything
below as half of the intended scope until agriculture non-CO2 gets its own
equivalent section.

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
  **Verified directly from the downloaded PDF** (`text_docs/literature/IEEP_2025_EU_LULUCF_sink_2040.pdf`,
  page 9, Table 3, sourced there to "EC, 2024"). The Impact Assessment's
  three core scenarios (S1: <=80% GHG reduction by 2040, Fit-for-55 trends
  only, no dedicated non-CO2/land ambition; S2: 85-90%, deeper land + non-CO2
  ambition; S3: 90-95%, closest to the Commission's actual recommended 2040
  target) differ only modestly from each other. The real spread comes from
  an assumed **carbon price for land-sector mitigation** (EUR0/50/200 per
  tCO2e), given as "lower/central/upper" for each scenario:

  | | S1 | S2 | S3 |
  |---|---:|---:|---:|
  | Lower (EUR0/tCO2e) | -218 | -213 | -215 |
  | Central (EUR50/tCO2e) | -319 | -316 | -317 |
  | Upper (EUR200/tCO2e) | -376 | -374 | -376 |

  All values MtCO2e, 2040. S3 is the scenario the IEEP brief identifies as
  aligned with the Commission's actual recommended target. **Superseded
  2026-09-01**: this table was originally used to anchor the two
  optimistic scenarios' 2040 values (S3 lower/upper bounds, -215/-376).
  Section 4 below now uses a simpler, non-literature-derived construction
  for the weak/strong post-2030 shape instead (flat-hold at the 2030
  forecast for weak; return to exactly zero by 2035, held flat, for
  strong) — this table is kept as background/context on the spread the EC's
  own Impact Assessment reports, not as the literal source of the numbers
  below anymore.
- No literature was found projecting the EU-27 LULUCF sink specifically for
  2045 or 2050. The BAU scenario holds its 2040 value flat beyond 2040 for
  lack of any sourced alternative — this is a placeholder, not a forecast.
  The optimistic scenarios' post-2030 shape is now a plain modelling
  assumption rather than an extrapolation (see Section 4).

## 4. Three scenarios

**Relabeling note**: an earlier draft of this table called the EC's weakest
2040 policy scenario "BAU" and the pure historical-trend extrapolation
"pessimistic," because the former was numerically less severe. That
labeling was backwards. The EC's Impact Assessment scenarios (S1/S2/S3) are
all *policy* scenarios — even the weakest one almost certainly embeds
continued Green Deal-era action, not a genuine no-further-action baseline.
The literal continuation of the observed WEM decline is the more honest
**BAU/central** case (it assumes nothing changes, which is what "business as
usual" means), and the EC's modelled scenarios are better read as two
flavours of **optimistic** (the EC only ever models pathways where the EU
keeps acting — there is no "policy stalls" scenario in their own Impact
Assessment to draw a true pessimistic case from). Relabeled below
accordingly. Note this also means we currently have **no sourced case worse
than the plain trend continuation** — a genuine pessimistic tier (e.g.
reflecting the literature's "accelerating, disturbance-driven, no sign of
reversal" finding as a *steeper* decline than the historical WEM slope) does
not exist yet and would need to be constructed separately, not assumed.

All values are `lulucf_deviation_values` in MtCO2/yr (positive =
tighten CO2Limit, i.e. sink underperforms the flat -310 MtCO2e/yr
reference). 2020 = 0 in all scenarios (assumed on-track starting point,
not empirically derived). 2025 values are linear interpolations between
2020's assumed 0 and each scenario's own sourced 2030 anchor — not
independently sourced.

| Year | BAU (central, WEM trend) | Optimistic — weak new policy (EC S1) | Optimistic — strong new policy (EC S3) |
|-----:|--------------------------:|---------------------------------------:|------------------------------------------:|
| 2020 |                         0 |                                       0 |                                          0 |
| 2025 |                        64 |                                      64 |                                         39 |
| 2030 |                       127 |                                     127 |                                         77 |
| 2035 |                       191 |                                     127 |                                          0 |
| 2040 |                       254 |                                     127 |                                          0 |
| 2045 |                       318 |                                     127 |                                          0 |
| 2050 |                       381 |                                     127 |                                          0 |

**How each column is built:**

- **BAU (central)** = straight-line continuation of the 2020->2030 WEM
  decline slope (12.7 MtCO2/yr^2). This is the scenario currently active in
  `config.default.yaml` (unchanged numbers), and the one actually used by
  both `run1_baseline` (deviation disabled) and `run2_full` (deviation
  enabled) — neither run uses either of the two scenarios below. It is the
  most literal reading of "current trends continue, no new policy
  materializes" — consistent with the peer-reviewed literature (Section 2),
  which reports an accelerating, disturbance-driven decline with "no sign
  of reversal." Because that literature suggests the decline could
  accelerate further, even this BAU line may be optimistic relative to
  reality, not pessimistic.
- **Optimistic — weak new policy** (simplified 2026-09-01): 2025/2030
  anchors unchanged (64/127, same WEM-sourced 2030 point as BAU). From 2030
  onward, the deviation is held flat at the 2030 forecast (127) rather than
  continuing to decline — i.e. "existing policy holds the 2030 shortfall
  steady, no further erosion and no further improvement." This replaces an
  earlier, more literature-derived construction (EC S1 2040 Impact
  Assessment anchor); simplified for now to a plain flat-hold assumption.
- **Optimistic — strong new policy** (simplified 2026-09-01): 2025/2030
  anchors unchanged (39/77, same WAM-sourced 2030 point). The deviation is
  assumed to close to exactly **zero by 2035** (sink performance catches
  up to the flat -310 MtCO2e/yr target, neither under- nor over-performing)
  and holds at zero through 2050 — deliberately **not** allowed to go
  negative (which would mean the sink overshoots the target and loosens
  CO2Limit). This replaces an earlier construction that extrapolated to
  the EC's strongest 2040 scenario and went negative from 2040; simplified
  for now to a plain "recovers to on-target by 2035, then flat" assumption.

## 5. Open items / next steps

- **Agriculture non-CO2 (N2O/CH4) gap is entirely unaddressed** (see Section
  1 scope note). This is not a refinement of the existing numbers — it is a
  missing second half of the intended correction, and should get its own
  literature review, sourcing, and scenario table before this document is
  considered complete.
- **No sourced pessimistic tier exists** — see the relabeling note in
  Section 4. If a case worse than the plain WEM-trend continuation is
  wanted, it needs to be built (e.g. a steeper decline rate reflecting the
  disturbance-acceleration literature), not assumed.
- ~~Verify the IEEP-relayed EC Impact Assessment numbers~~ — done: confirmed
  directly from the downloaded PDF's Table 3 (see Section 3).
- Confirm author list and exact figures for the Nature Geoscience (2026)
  paper by reading the full text (currently paywalled to automated fetch).
- Read "Alarming decline in the carbon sink of European forests driven by
  disturbances" (National Science Review) in full before citing it.
- Decide whether `config.default.yaml`'s active `lulucf_deviation_values`
  should switch from the current single "pessimistic" line to one of these
  three, or stay as-is with the others documented as sensitivities.
