"""
Check script for the heat_industry branch modifications in pypsa-eur.

Verifies that:
  1. Config: industry_t and fossil_limit blocks read correctly
  2. Pre-network: industry heat buses, loads, links present
  3. Technology links: correct carriers per temperature band
  4. p_min_pu (must_run) applied to all new heat links
  5. Backward compat: exogenous path (endogen=false) keeps original buses
  6. Solved network: heat technology links deployed (p_nom_opt > 0)
  7. Fossil constraint: GlobalConstraint present, shadow price readable,
     fossil_co2_eq attribute on carriers

Run from the pypsa-eur root directory:

    python scripts/check_heat_industry_pipeline.py --config config/config.default.yaml

Override wildcards on the CLI:
    --run-name NAME  --clusters N  --horizon YEAR  --sector-opts OPTS
"""

import sys
from pathlib import Path

import pandas as pd

from _check_utils import parse_check_args, load_check_params

# ── Configuration ─────────────────────────────────────────────────────────────
_args = parse_check_args()
_p    = load_check_params(_args)

BASE_DIR         = _p["BASE_DIR"]
RDIR             = _p["RDIR"]
CLUSTERS         = _p["CLUSTERS"]
OPTS             = _p["OPTS"]
SECTOR_OPTS      = _p["SECTOR_OPTS"]
PLANNING_HORIZON = _p["PLANNING_HORIZON"]
WC               = _p["WC"]
RES              = _p["RES"]
RES_RUN          = _p["RES_RUN"]
RESULTS          = _p["RESULTS"]
cfg              = _p["cfg"]

sector_cfg   = cfg.get("sector", {})
industry_t   = sector_cfg.get("industry_t", {})
ENDOGEN      = industry_t.get("endogen", False)
MUST_RUN     = industry_t.get("must_run", 0.6)
FOSSIL_LIMIT = sector_cfg.get("fossil_limit", False)

# ── Helpers ───────────────────────────────────────────────────────────────────
OK   = "  [OK]"
FAIL = "  [MISSING]"
WARN = "  [WARN]"

passed = []
failed = []
warned = []


def check_file(path: Path, label: str) -> bool:
    exists = path.exists()
    status = OK if exists else FAIL
    size   = f"  ({path.stat().st_size / 1e6:.1f} MB)" if exists else ""
    print(f"{status}  {label}{size}")
    print(f"        {path}")
    if exists:
        passed.append(label)
    else:
        failed.append(label)
    return exists


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def record(ok: bool, label: str, warn_only: bool = False):
    if ok:
        passed.append(label)
    elif warn_only:
        warned.append(label)
    else:
        failed.append(label)


# ── 1. Config sanity check ────────────────────────────────────────────────────
section("1. CONFIG: industry_t and fossil_limit settings")

print(f"\n  sector.industry_t.endogen   = {ENDOGEN}")
print(f"  sector.industry_t.must_run  = {MUST_RUN}")
print(f"  sector.fossil_limit         = {FOSSIL_LIMIT}")

if ENDOGEN:
    share_m = industry_t.get("share_medium", None)
    share_h = industry_t.get("share_high",   None)
    print(f"  sector.industry_t.share_medium = {share_m}")
    print(f"  sector.industry_t.share_high   = {share_h}")
    low_T    = industry_t.get("low_T",    {})
    medium_T = industry_t.get("medium_T", {})
    high_T   = industry_t.get("high_T",   {})
    print(f"  low_T    enabled carriers: {[k for k,v in low_T.items()    if v]}")
    print(f"  medium_T enabled carriers: {[k for k,v in medium_T.items() if v]}")
    print(f"  high_T   enabled carriers: {[k for k,v in high_T.items()   if v]}")
    record(True, "Config: endogen=true block present")
else:
    print(f"\n{WARN}  endogen=False → exogenous industry heat (original behaviour).")
    print(f"       Checks will verify old solid biomass / gas for industry buses.")
    record(True, "Config: endogen=false (exogenous mode)")

if FOSSIL_LIMIT:
    fossil_values = sector_cfg.get("fossil_limit_values", {})
    print(f"\n  fossil_limit_values (MtCO2-eq): {fossil_values}")
    if PLANNING_HORIZON in [str(y) for y in fossil_values.keys()] or \
       int(PLANNING_HORIZON) in fossil_values:
        yr = int(PLANNING_HORIZON)
        cap = fossil_values.get(yr, fossil_values.get(str(yr), None))
        print(f"  Cap for {PLANNING_HORIZON}: {cap} MtCO2-eq")
        record(cap is not None, "Config: fossil_limit_values entry for planning horizon")
    else:
        print(f"{WARN}  No fossil_limit_values entry for horizon {PLANNING_HORIZON}")
        record(False, "Config: fossil_limit_values entry for planning horizon")
else:
    print(f"\n  fossil_limit=False → fossil_fuel_limit GlobalConstraint will NOT be added.")

# ── 2. Pre-network file ───────────────────────────────────────────────────────
section("2. PRE-NETWORK: prepare_sector_network output")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa
        n = pypsa.Network(str(prenet_path))
        n_clusters = int(CLUSTERS)

        # ── 3. Temperature band buses ─────────────────────────────────────────
        section("3. PRE-NETWORK: industry heat buses")

        for band in ["lowT industry", "mediumT industry", "highT industry"]:
            band_buses = n.buses[n.buses.carrier == band]
            n_found    = len(band_buses)
            if ENDOGEN:
                ok = n_found == n_clusters
                status = OK if ok else WARN
                print(f"{status}  '{band}' buses: {n_found} "
                      f"(expected ~{n_clusters})")
                record(ok, f"Buses: {band} count == clusters", warn_only=not ok)
            else:
                if n_found > 0:
                    print(f"{WARN}  '{band}' buses found ({n_found}) but endogen=False!")
                    record(False, f"Buses: {band} unexpected in exogen mode", warn_only=True)
                else:
                    print(f"{OK}  '{band}' buses absent (endogen=False — correct).")
                    record(True, f"Buses: {band} correctly absent in exogen mode")

        # ── 3b. Exogenous fallback buses ──────────────────────────────────────
        section("3b. PRE-NETWORK: exogenous industry buses (endogen=False path)")

        for band_name in ["solid biomass for industry", "gas for industry"]:
            band_buses = n.buses[n.buses.carrier == band_name]
            n_found    = len(band_buses)
            if not ENDOGEN:
                ok = n_found == n_clusters
                status = OK if ok else WARN
                print(f"{status}  '{band_name}' buses: {n_found} "
                      f"(expected ~{n_clusters})")
                record(ok, f"Buses: {band_name} present in exogen mode", warn_only=not ok)
            else:
                # When endogen=True the old buses should not exist
                if n_found > 0:
                    print(f"{WARN}  '{band_name}' buses found ({n_found}) with endogen=True "
                          f"— old code path may still be active!")
                    record(False, f"Buses: {band_name} should be absent in endogen mode",
                           warn_only=True)
                else:
                    print(f"{OK}  '{band_name}' buses absent (endogen=True — correct).")
                    record(True, f"Buses: {band_name} correctly absent in endogen mode")

        # ── 4. Industry heat loads ────────────────────────────────────────────
        if ENDOGEN:
            section("4. PRE-NETWORK: industry heat loads")

            for band in ["lowT industry", "mediumT industry", "highT industry"]:
                band_loads = n.loads[n.loads.carrier == band]
                n_loads    = len(band_loads)
                ok = n_loads > 0
                status = OK if ok else FAIL
                print(f"{status}  '{band}' loads: {n_loads}")
                record(ok, f"Loads: {band}")

                if ok and "p_set" in n.loads_t:
                    bus_ids = band_loads.index
                    if bus_ids.isin(n.loads_t.p_set.columns).any():
                        ps = n.loads_t.p_set[bus_ids.intersection(n.loads_t.p_set.columns)]
                        nonzero = (ps > 0).any().sum()
                        print(f"       Non-zero p_set snapshots in at least {nonzero} loads.")
                        if nonzero == 0:
                            print(f"{WARN}  All p_set values are zero for {band} loads!")
                            record(False, f"Loads: {band} p_set non-zero", warn_only=True)

        # ── 5. Technology links per temperature band ──────────────────────────
        if ENDOGEN:
            section("5. PRE-NETWORK: technology links per temperature band")

            EXPECTED_CARRIERS = {
                "lowT industry": [
                    c for c, v in industry_t.get("low_T", {}).items() if v
                ],
                "mediumT industry": [
                    c for c, v in industry_t.get("medium_T", {}).items() if v
                ],
                "highT industry": [
                    c for c, v in industry_t.get("high_T", {}).items() if v
                ],
            }

            # Carrier name mappings used in add_*_t_industry functions
            CARRIER_KEYWORDS = {
                "biomass":        ["solid biomass", "biomass"],
                "methane":        ["gas", "methane", "CCGT", "boiler"],
                "heat_pumps":     ["heat pump"],
                "electric_boiler":["electric boiler"],
                "methanol":       ["methanol"],
                "hydrogen":       ["H2", "hydrogen"],
            }

            for band, techs in EXPECTED_CARRIERS.items():
                band_buses = n.buses[n.buses.carrier == band].index
                if band_buses.empty:
                    print(f"\n{FAIL}  No '{band}' buses — cannot check links.")
                    record(False, f"Links: {band} buses present for link check")
                    continue

                # Links whose bus1 is an industry heat bus of this band
                band_links = n.links[n.links["bus1"].isin(band_buses)]
                print(f"\n  '{band}' links (bus1 in band): {len(band_links)}")
                if band_links.empty:
                    print(f"{FAIL}  No links found for {band}!")
                    record(False, f"Links: {band} has technology links")
                    continue

                record(True, f"Links: {band} has technology links")
                print(f"  Carriers: {sorted(band_links['carrier'].unique())}")

                # Check each expected carrier keyword is represented
                for tech in techs:
                    keywords = CARRIER_KEYWORDS.get(tech, [tech])
                    found = band_links["carrier"].str.contains(
                        "|".join(keywords), case=False, regex=True
                    ).any()
                    status = OK if found else WARN
                    print(f"{status}  Expected technology '{tech}' in {band}: "
                          f"{'found' if found else 'NOT FOUND'}")
                    record(found, f"Links: {tech} in {band}", warn_only=not found)

            # ── 6. p_min_pu (must_run) on new links ──────────────────────────
            section("6. PRE-NETWORK: p_min_pu = must_run on industry heat links")

            all_heat_links = pd.concat([
                n.links[n.links["bus1"].isin(
                    n.buses[n.buses.carrier == band].index
                )]
                for band in ["lowT industry", "mediumT industry", "highT industry"]
                if not n.buses[n.buses.carrier == band].empty
            ])

            if all_heat_links.empty:
                print(f"{WARN}  No industry heat links found — cannot check p_min_pu.")
                record(False, "Links: p_min_pu check", warn_only=True)
            else:
                if "p_min_pu" in all_heat_links.columns:
                    pmin_vals  = all_heat_links["p_min_pu"].dropna().unique()
                    correct    = all(abs(v - MUST_RUN) < 1e-6 for v in pmin_vals
                                     if not pd.isna(v))
                    wrong_mask = (all_heat_links["p_min_pu"] - MUST_RUN).abs() > 1e-6
                    n_wrong    = wrong_mask.sum()
                    if n_wrong == 0:
                        print(f"{OK}  All {len(all_heat_links)} industry heat links have "
                              f"p_min_pu = {MUST_RUN}.")
                        record(True, "Links: p_min_pu == must_run")
                    else:
                        print(f"{WARN}  {n_wrong} links have p_min_pu != {MUST_RUN}:")
                        print(all_heat_links[wrong_mask][["carrier", "p_min_pu"]].to_string())
                        record(False, "Links: p_min_pu == must_run", warn_only=True)
                else:
                    print(f"{WARN}  p_min_pu column missing from links.")
                    record(False, "Links: p_min_pu column present", warn_only=True)

        # ── 7. Fossil GlobalConstraint ────────────────────────────────────────
        section("7. PRE-NETWORK: fossil_fuel_limit GlobalConstraint")

        if "fossil_fuel_limit" in n.global_constraints.index:
            gc = n.global_constraints.loc["fossil_fuel_limit"]
            print(f"{OK}  'fossil_fuel_limit' GlobalConstraint present.")
            print(f"       type       = {gc.get('type', '?')}")
            print(f"       carrier_attribute = {gc.get('carrier_attribute', '?')}")
            print(f"       sense      = {gc.get('sense', '?')}")
            constant_mt = gc.get("constant", 0) / 1e6
            print(f"       constant   = {gc.get('constant', '?')}  "
                  f"({constant_mt:.1f} MtCO2-eq)")
            record(True, "GlobalConstraint: fossil_fuel_limit present")

            if gc.get("type") != "primary_energy":
                print(f"{WARN}  Expected type='primary_energy', got '{gc.get('type')}'.")
                record(False, "GlobalConstraint: type==primary_energy", warn_only=True)
            else:
                record(True, "GlobalConstraint: type==primary_energy")

            if gc.get("carrier_attribute") != "fossil_co2_eq":
                print(f"{WARN}  Expected carrier_attribute='fossil_co2_eq', "
                      f"got '{gc.get('carrier_attribute')}'.")
                record(False, "GlobalConstraint: carrier_attribute==fossil_co2_eq",
                       warn_only=True)
            else:
                record(True, "GlobalConstraint: carrier_attribute==fossil_co2_eq")
        else:
            if FOSSIL_LIMIT:
                print(f"{FAIL}  'fossil_fuel_limit' GlobalConstraint MISSING "
                      f"(fossil_limit=True in config — expected it!).")
                record(False, "GlobalConstraint: fossil_fuel_limit present")
            else:
                print(f"{OK}  'fossil_fuel_limit' absent (fossil_limit=False — correct).")
                record(True, "GlobalConstraint: fossil_fuel_limit absent (correct)")

        # ── 7b. fossil_co2_eq attribute on carriers ───────────────────────────
        if FOSSIL_LIMIT and "fossil_fuel_limit" in n.global_constraints.index:
            print()
            for carrier in ["gas", "oil primary", "coal", "lignite"]:
                if carrier not in n.carriers.index:
                    print(f"       '{carrier}' not in network carriers (may be phased out).")
                    continue
                if "fossil_co2_eq" in n.carriers.columns:
                    val = n.carriers.at[carrier, "fossil_co2_eq"]
                    ok  = not pd.isna(val) and val > 0
                    status = OK if ok else WARN
                    print(f"{status}  carriers['{carrier}'].fossil_co2_eq = {val}")
                    record(ok, f"Carriers: {carrier} fossil_co2_eq > 0", warn_only=not ok)
                else:
                    print(f"{FAIL}  'fossil_co2_eq' column missing from n.carriers!")
                    record(False, "Carriers: fossil_co2_eq column present")
                    break

    except Exception as e:
        print(f"\n{WARN}  Could not fully analyse pre-network: {e}")
        import traceback; traceback.print_exc()

else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run.")

# ── 8. Solved network ─────────────────────────────────────────────────────────
section("8. OPTIMAL SOLUTION: solved network (solve_sector_network)")

opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok   = check_file(opt_path, f"Optimal network  {WC}.nc")

if opt_ok:
    try:
        import pypsa
        n_opt = pypsa.Network(str(opt_path))

        # ── 8a. p_nom_opt for industry heat links ─────────────────────────────
        if ENDOGEN:
            print()
            for band in ["lowT industry", "mediumT industry", "highT industry"]:
                band_buses = n_opt.buses[n_opt.buses.carrier == band].index
                if band_buses.empty:
                    print(f"{FAIL}  No '{band}' buses in solved network!")
                    record(False, f"Solved: {band} buses present")
                    continue
                band_links = n_opt.links[n_opt.links["bus1"].isin(band_buses)]
                if band_links.empty:
                    print(f"{WARN}  No technology links for '{band}' in solved network.")
                    record(False, f"Solved: {band} links present", warn_only=True)
                    continue
                if "p_nom_opt" in band_links.columns:
                    deployed   = band_links[band_links["p_nom_opt"] > 0]
                    total_pnom = band_links["p_nom_opt"].sum()
                    print(f"\n  {band}:")
                    print(f"    Links total: {len(band_links)}  |  "
                          f"Deployed (p_nom_opt>0): {len(deployed)}")
                    print(f"    Total p_nom_opt: {total_pnom:,.1f} MW")
                    if deployed.empty:
                        print(f"  {WARN}  No {band} technology deployed (all p_nom_opt=0).")
                        record(False, f"Solved: {band} deployed", warn_only=True)
                    else:
                        record(True, f"Solved: {band} deployed")
                        by_carrier = (
                            deployed.groupby("carrier")["p_nom_opt"]
                            .sum()
                            .sort_values(ascending=False)
                        )
                        print(f"    By carrier (p_nom_opt MW):")
                        for c, v in by_carrier.items():
                            print(f"      {c:<45} {v:>12,.1f}")

        # ── 8b. Fossil GlobalConstraint shadow price ───────────────────────────
        section("8b. SOLVED: fossil constraint shadow price")

        if "fossil_fuel_limit" in n_opt.global_constraints.index:
            gc_opt = n_opt.global_constraints.loc["fossil_fuel_limit"]
            mu     = gc_opt.get("mu", None)
            constant_mt = gc_opt.get("constant", 0) / 1e6
            print(f"{OK}  'fossil_fuel_limit' in solved network.")
            print(f"       Cap (constant): {constant_mt:.1f} MtCO2-eq")
            if mu is not None and not pd.isna(mu):
                print(f"       Shadow price (mu): {abs(mu):.2f} EUR/tCO2-eq")
                if abs(mu) > 0:
                    print(f"{OK}  Constraint is binding (mu > 0).")
                    record(True, "Solved: fossil_fuel_limit shadow price > 0")
                else:
                    print(f"{WARN}  Shadow price = 0 — constraint is NOT binding.")
                    record(False, "Solved: fossil_fuel_limit shadow price > 0", warn_only=True)
            else:
                print(f"{WARN}  mu is None or NaN — solver may not have returned dual.")
                record(False, "Solved: fossil_fuel_limit mu readable", warn_only=True)

            # Compare with CO2 cap shadow price
            if "CO2Limit" in n_opt.global_constraints.index:
                co2_mu = n_opt.global_constraints.loc["CO2Limit", "mu"]
                if not pd.isna(co2_mu):
                    print(f"\n       CO2Limit shadow price (mu): {abs(co2_mu):.2f} EUR/tCO2")
                    if mu is not None and not pd.isna(mu) and abs(co2_mu) > 0:
                        ratio = abs(mu) / abs(co2_mu)
                        print(f"       fossil_price / co2_price ratio: {ratio:.2f}")
                        if ratio > 1:
                            print(f"       (fossil constraint more binding than CO2 cap)")
                        else:
                            print(f"       (CO2 cap more binding than fossil constraint)")

        else:
            if FOSSIL_LIMIT:
                print(f"{FAIL}  'fossil_fuel_limit' missing from solved network "
                      f"(fossil_limit=True in config!).")
                record(False, "Solved: fossil_fuel_limit present")
            else:
                print(f"{OK}  'fossil_fuel_limit' absent (fossil_limit=False — correct).")
                record(True, "Solved: fossil_fuel_limit absent (correct)")

        # ── 8c. Quick fossil fuel use check ───────────────────────────────────
        if FOSSIL_LIMIT:
            section("8c. SOLVED: actual fossil fuel use vs. cap")
            wt = n_opt.snapshot_weightings["generators"]
            CO2_INTENSITY = {"gas": 0.198e-6, "oil primary": 0.276e-6,
                             "coal": 0.341e-6, "lignite": 0.412e-6}
            total_mt = 0.0
            for carrier, intensity in CO2_INTENSITY.items():
                gens = n_opt.generators[n_opt.generators.carrier == carrier].index
                if gens.empty:
                    continue
                if gens.isin(n_opt.generators_t.p.columns).any():
                    use = (n_opt.generators_t.p[gens.intersection(
                        n_opt.generators_t.p.columns)].mul(wt, axis=0).sum().sum() * intensity)
                else:
                    use = 0.0
                total_mt += use
                print(f"  {carrier:<15} use: {use:.2f} MtCO2-eq/yr")

            if "fossil_fuel_limit" in n_opt.global_constraints.index:
                cap_mt = (n_opt.global_constraints.loc["fossil_fuel_limit", "constant"]
                          / 1e6)
                print(f"\n  Total fossil:  {total_mt:.2f} MtCO2-eq/yr")
                print(f"  Cap:           {cap_mt:.2f} MtCO2-eq/yr")
                slack = cap_mt - total_mt
                print(f"  Slack:         {slack:.2f} MtCO2-eq/yr")
                if abs(slack) < 0.01 * cap_mt:
                    print(f"{OK}  Constraint fully used (slack < 1% of cap).")
                    record(True, "Solved: fossil use matches cap")
                elif slack >= 0:
                    print(f"{WARN}  {slack:.2f} MtCO2-eq unused from fossil budget.")
                    record(False, "Solved: fossil use matches cap", warn_only=True)
                else:
                    print(f"{FAIL}  Total fossil use EXCEEDS cap by {-slack:.2f} MtCO2-eq!")
                    record(False, "Solved: fossil use within cap")

    except Exception as e:
        print(f"\n{WARN}  Could not fully analyse solved network: {e}")
        import traceback; traceback.print_exc()

else:
    print(f"\n  Solved network missing — solve_sector_network has not run yet.")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  Run:              {RDIR}")
print(f"  Wildcard:         {WC}")
print(f"  Planning horizon: {PLANNING_HORIZON}")
print(f"  Clusters:         {CLUSTERS}")
print(f"  endogen:          {ENDOGEN}")
print(f"  fossil_limit:     {FOSSIL_LIMIT}")
print(f"  Resources dir:    {RES_RUN.resolve()}")
print(f"  Results dir:      {RESULTS.resolve()}")
print()
print(f"  Passed: {len(passed)}")
print(f"  Warned: {len(warned)}")
print(f"  Failed: {len(failed)}")

if warned:
    print(f"\n  Warnings:")
    for w in warned:
        print(f"    ~ {w}")
if failed:
    print(f"\n  Missing / failed:")
    for f in failed:
        print(f"    - {f}")

sys.exit(len(failed))
