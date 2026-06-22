"""
Check script for the enhanced rock weathering pipeline in pypsa-eur.
Run from the pypsa-eur root directory:

    python scripts/check_rock_weathering_pipeline.py rock_weathering_2050

Wildcards are read from the saved run config automatically.
Override any value on the CLI:
    --run-name NAME  --clusters N  --horizon YEAR  --sector-opts OPTS
    --config PATH    (direct path to a saved config YAML)
"""

from pathlib import Path

import pandas as pd

from _check_utils import parse_check_args, load_check_params

# ── Configuration (from config file + CLI overrides) ──────────────────────────
_args = parse_check_args()
_p    = load_check_params(_args)

RDIR             = _p["RDIR"]
CLUSTERS         = _p["CLUSTERS"]
OPTS             = _p["OPTS"]
SECTOR_OPTS      = _p["SECTOR_OPTS"]
PLANNING_HORIZON = _p["PLANNING_HORIZON"]
WC               = _p["WC"]
RES              = _p["RES"]
RES_RUN          = _p["RES_RUN"]
RESULTS          = _p["RESULTS"]
CFG              = _p["cfg"]

# ── Helpers ───────────────────────────────────────────────────────────────────
OK   = "  [OK]"
FAIL = "  [MISSING]"
WARN = "  [WARN]"

passed = []
failed = []


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


# ── 1. BUILD: rock weathering available land (determine_rock_weathering_availability_matrix + build_available_land) ──
section("1. BUILD: rock weathering available land (CORINE + mean-temperature exclusion)")

rw_csv = RES_RUN / f"rock_weathering_available_land_s_{CLUSTERS}.csv"

rw_ok = check_file(rw_csv, f"Rock weathering available land CSV  s_{CLUSTERS}")

if rw_ok:
    df_rw = pd.read_csv(rw_csv, index_col=0)
    print(f"        Rows: {len(df_rw)}  |  Columns: {list(df_rw.columns)}")
    if "potential [sqkm]" in df_rw.columns:
        potential_per_sqkm = CFG.get("rock_weathering", {}).get("potential_per_sqkm")
        total_sqkm = df_rw["potential [sqkm]"].sum()
        print(f"        Total rock weathering available land: {total_sqkm:,.0f} km²")
        if potential_per_sqkm:
            total_Mt = total_sqkm * potential_per_sqkm / 1e6
            print(f"        Total rock weathering potential: {total_Mt:.2f} Mt CO2  "
                  f"(at {potential_per_sqkm} t CO2/km²)")
        print(f"        Per-node [km²] — min: {df_rw['potential [sqkm]'].min():,.1f}, "
              f"mean: {df_rw['potential [sqkm]'].mean():,.1f}, "
              f"max: {df_rw['potential [sqkm]'].max():,.1f}")
    if df_rw.isnull().any().any():
        print(f"{WARN}  NaN values detected in rock weathering available land CSV.")

# ── 2. Pre-network (prepare_sector_network) ────────────────────────────────────
section("2. PRE-NETWORK: sector-coupled (prepare_sector_network)")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa

        n = pypsa.Network(str(prenet_path))

        # --- Carriers ---
        rw_carriers = [c for c in n.carriers.index if "rock_weathering" in c.lower()]
        print(f"\n  Carriers with 'rock_weathering': {rw_carriers}")
        for expected_carrier in ["rock_weathering", "rock_weathering store"]:
            if expected_carrier in n.carriers.index:
                print(f"    {OK}  Carrier '{expected_carrier}' present.")
            else:
                print(f"    {WARN}  Carrier '{expected_carrier}' NOT found!")

        # --- Buses ---
        rw_buses = n.buses[n.buses.carrier.str.contains("rock_weathering", case=True, na=False)]
        print(f"\n  Buses (carrier contains 'rock_weathering'): {len(rw_buses)}")
        if not rw_buses.empty:
            print(f"    Carriers present: {rw_buses['carrier'].unique().tolist()}")
            cols = [c for c in ["location", "carrier", "unit"] if c in rw_buses.columns]
            print(rw_buses[cols].head(5).to_string())
        if len(rw_buses) != int(CLUSTERS):
            print(f"    {WARN}  Expected ~{CLUSTERS} rock_weathering buses, found {len(rw_buses)}")

        # --- Links ---
        rw_links = n.links[n.links.carrier.str.contains("rock_weathering", case=True, na=False)]
        print(f"\n  Links (carrier contains 'rock_weathering'): {len(rw_links)}")
        if not rw_links.empty:
            cols = [c for c in ["bus0", "bus1", "bus2", "carrier",
                                 "p_nom_extendable", "efficiency", "efficiency2",
                                 "marginal_cost"] if c in rw_links.columns]
            print(rw_links[cols].head(10).to_string())
            if "p_nom_extendable" in rw_links.columns:
                if not rw_links["p_nom_extendable"].all():
                    print(f"    {WARN}  Some rock_weathering links are NOT extendable — check add_rock_weathering()!")
            # check bus2 points to rock_weathering co2 store
            if "bus2" in rw_links.columns:
                wrong_bus2 = rw_links[~rw_links["bus2"].str.contains("rock_weathering co2 store", na=False)]
                if not wrong_bus2.empty:
                    print(f"    {WARN}  Some rock_weathering links have unexpected bus2: {wrong_bus2['bus2'].tolist()}")

        # --- Stores ---
        rw_stores = n.stores[n.stores.carrier.str.contains("rock_weathering", case=True, na=False)]
        print(f"\n  Stores (carrier contains 'rock_weathering'): {len(rw_stores)}")
        if not rw_stores.empty:
            cols = [c for c in ["bus", "carrier", "e_nom", "e_nom_extendable"] if c in rw_stores.columns]
            print(rw_stores[cols].head(10).to_string())
            if "e_nom" in rw_stores.columns:
                total_enoms = rw_stores["e_nom"].sum()
                print(f"\n    e_nom [t CO2] — "
                      f"min: {rw_stores['e_nom'].min():,.0f}, "
                      f"mean: {rw_stores['e_nom'].mean():,.0f}, "
                      f"max: {rw_stores['e_nom'].max():,.0f}")
                print(f"    Total e_nom: {total_enoms:,.0f} t CO2  ({total_enoms/1e6:.2f} Mt CO2)")
                # cross-check against rock weathering potentials CSV
                if rw_ok and "potential [t]" in df_rw.columns:
                    expected_total = df_rw["potential [t]"].sum() * 0.2  # default max_land_usage=0.2
                    if abs(total_enoms - expected_total) / max(expected_total, 1) > 0.01:
                        print(f"    {WARN}  e_nom total ({total_enoms:,.0f} t) differs from "
                              f"expected ({expected_total:,.0f} t, assuming max_land_usage=0.2)")

        if not rw_carriers:
            print(f"\n{WARN}  No rock_weathering carriers found — add_rock_weathering may NOT have run!")
        elif rw_links.empty or rw_stores.empty:
            print(f"\n{WARN}  Missing rock_weathering links or stores — check add_rock_weathering() execution!")
        else:
            print(f"\n{OK}  Rock weathering components present in pre-network.")

    except Exception as e:
        print(f"\n{WARN}  Could not load pre-network: {e}")
else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run yet.")

# ── 3. Solved network (solve_sector_network) ───────────────────────────────────
section("3. OPTIMAL SOLUTION: solved network (solve_sector_network)")

opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok   = check_file(opt_path, f"Optimal network  {WC}.nc")

if opt_ok:
    try:
        import pypsa

        n_opt = pypsa.Network(str(opt_path))

        rw_links  = n_opt.links [n_opt.links .carrier.str.contains("rock_weathering", case=True, na=False)]
        rw_stores = n_opt.stores[n_opt.stores.carrier.str.contains("rock_weathering", case=True, na=False)]

        # --- Links optimal ---
        print(f"\n  Links (carrier contains 'rock_weathering'): {len(rw_links)}")
        if not rw_links.empty and "p_nom_opt" in rw_links.columns:
            active = rw_links[rw_links["p_nom_opt"] > 0]
            total  = rw_links["p_nom_opt"].sum()
            print(f"  Links with p_nom_opt > 0: {len(active)}")
            print(f"  Total p_nom_opt (all rock_weathering links): {total:,.2f} MW_el")
            if active.empty:
                print(f"{WARN}  All rock_weathering links have p_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  Rock weathering links deployed in optimal solution.")
                cols = [c for c in ["bus0", "bus1", "bus2", "carrier", "p_nom_opt"] if c in active.columns]
                print(active[cols].to_string())

        # --- Stores optimal ---
        print(f"\n  Stores (carrier contains 'rock_weathering'): {len(rw_stores)}")
        if not rw_stores.empty:
            # rock_weathering stores are fixed capacity (e_nom, not e_nom_extendable)
            # check the dispatch: how much CO2 was actually sequestered
            if "e_nom" in rw_stores.columns:
                total_cap = rw_stores["e_nom"].sum()
                print(f"  Total store capacity (e_nom): {total_cap:,.0f} t CO2  ({total_cap/1e6:.3f} Mt CO2)")

            # check time series for actual sequestration
            if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
                rw_store_e = n_opt.stores_t["e"][rw_stores.index]
                if not rw_store_e.empty:
                    final_e = rw_store_e.iloc[-1]
                    total_stored = final_e.sum()
                    print(f"  CO2 stored at end of horizon: {total_stored:,.0f} t CO2  "
                          f"({total_stored/1e6:.3f} Mt CO2)")
                    if "e_nom" in rw_stores.columns:
                        utilisation = (final_e / rw_stores["e_nom"]).mean() * 100
                        print(f"  Mean store utilisation: {utilisation:.1f}%")
                    if total_stored == 0:
                        print(f"{WARN}  No CO2 sequestered — rock weathering not utilised in solution.")
                    else:
                        print(f"{OK}  Rock weathering CO2 sequestration active in optimal solution.")

        if rw_links.empty and rw_stores.empty:
            print(f"\n{WARN}  No rock_weathering components in optimal network!")

    except Exception as e:
        print(f"\n{WARN}  Could not load optimal network: {e}")
else:
    print(f"\n{FAIL}  Optimal network missing — solve_sector_network has not run yet.")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  Run:            {RDIR}")
print(f"  Wildcard:       {WC}")
print(f"  Resources dir:  {RES_RUN.resolve()}")
print(f"  Results dir:    {RESULTS.resolve()}")
print()
print(f"  Passed: {len(passed)}")
print(f"  Failed: {len(failed)}")
if failed:
    print(f"\n  Missing files:")
    for f in failed:
        print(f"    - {f}")
