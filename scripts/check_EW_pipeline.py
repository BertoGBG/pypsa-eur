"""
Check script for the Enhanced Weathering (ERW) pipeline in pypsa-eur.
Run from the pypsa-eur root directory:

    python scripts/check_EW_pipeline.py EW_2050

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


# ── 0. INPUT DATA ──────────────────────────────────────────────────────────────
section("0. INPUT DATA")

bioclimate_tif = BASE_DIR / "data" / "World_Ecological_BioVal_cluster.tif"
check_file(bioclimate_tif, "Bioclimate TIF (World_Ecological_BioVal_cluster.tif)")

# ── 1. BUILD: ERW potentials (build_EW_potentials) ─────────────────────────────
section("1. BUILD: ERW CO2 sequestration potentials (CORINE + bioclimate)")

ew_csv = RES_RUN / f"EW_potentials_s_{CLUSTERS}.csv"
ew_png = RES_RUN / f"EW_potentials_s_{CLUSTERS}.png"

ew_ok = check_file(ew_csv, f"ERW potentials CSV  s_{CLUSTERS}")
check_file(ew_png, f"ERW potentials PNG  s_{CLUSTERS}")

if ew_ok:
    df_ew = pd.read_csv(ew_csv, index_col=0)
    print(f"        Rows: {len(df_ew)}  |  Columns: {list(df_ew.columns)}")
    if "potential [t]" in df_ew.columns:
        total_t  = df_ew["potential [t]"].sum()
        total_Mt = total_t / 1e6
        print(f"        Total ERW potential: {total_t:,.0f} t CO2  ({total_Mt:.2f} Mt CO2)")
        print(f"        Per-node [t CO2] — min: {df_ew['potential [t]'].min():,.0f}, "
              f"mean: {df_ew['potential [t]'].mean():,.0f}, "
              f"max: {df_ew['potential [t]'].max():,.0f}")
    if df_ew.isnull().any().any():
        print(f"{WARN}  NaN values detected in ERW potentials CSV.")

# ── 2. Pre-network (prepare_sector_network) ────────────────────────────────────
section("2. PRE-NETWORK: sector-coupled (prepare_sector_network)")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa

        n = pypsa.Network(str(prenet_path))

        # --- Carriers ---
        ew_carriers = [c for c in n.carriers.index if "ERW" in c or "ew" in c.lower()]
        print(f"\n  Carriers with 'ERW': {ew_carriers}")
        for expected_carrier in ["ERW", "ERW store"]:
            if expected_carrier in n.carriers.index:
                print(f"    {OK}  Carrier '{expected_carrier}' present.")
            else:
                print(f"    {WARN}  Carrier '{expected_carrier}' NOT found!")

        # --- Buses ---
        ew_buses = n.buses[n.buses.carrier.str.contains("ERW", case=True, na=False)]
        print(f"\n  Buses (carrier contains 'ERW'): {len(ew_buses)}")
        if not ew_buses.empty:
            print(f"    Carriers present: {ew_buses['carrier'].unique().tolist()}")
            cols = [c for c in ["location", "carrier", "unit"] if c in ew_buses.columns]
            print(ew_buses[cols].head(5).to_string())
        if len(ew_buses) != int(CLUSTERS):
            print(f"    {WARN}  Expected ~{CLUSTERS} ERW buses, found {len(ew_buses)}")

        # --- Links ---
        ew_links = n.links[n.links.carrier.str.contains("ERW", case=True, na=False)]
        print(f"\n  Links (carrier contains 'ERW'): {len(ew_links)}")
        if not ew_links.empty:
            cols = [c for c in ["bus0", "bus1", "bus2", "carrier",
                                 "p_nom_extendable", "efficiency", "efficiency2",
                                 "marginal_cost"] if c in ew_links.columns]
            print(ew_links[cols].head(10).to_string())
            if "p_nom_extendable" in ew_links.columns:
                if not ew_links["p_nom_extendable"].all():
                    print(f"    {WARN}  Some ERW links are NOT extendable — check add_EW()!")
            # check bus2 points to ERW co2 store
            if "bus2" in ew_links.columns:
                wrong_bus2 = ew_links[~ew_links["bus2"].str.contains("ERW co2 store", na=False)]
                if not wrong_bus2.empty:
                    print(f"    {WARN}  Some ERW links have unexpected bus2: {wrong_bus2['bus2'].tolist()}")

        # --- Stores ---
        ew_stores = n.stores[n.stores.carrier.str.contains("ERW", case=True, na=False)]
        print(f"\n  Stores (carrier contains 'ERW'): {len(ew_stores)}")
        if not ew_stores.empty:
            cols = [c for c in ["bus", "carrier", "e_nom", "e_nom_extendable"] if c in ew_stores.columns]
            print(ew_stores[cols].head(10).to_string())
            if "e_nom" in ew_stores.columns:
                total_enoms = ew_stores["e_nom"].sum()
                print(f"\n    e_nom [t CO2] — "
                      f"min: {ew_stores['e_nom'].min():,.0f}, "
                      f"mean: {ew_stores['e_nom'].mean():,.0f}, "
                      f"max: {ew_stores['e_nom'].max():,.0f}")
                print(f"    Total e_nom: {total_enoms:,.0f} t CO2  ({total_enoms/1e6:.2f} Mt CO2)")
                # cross-check against ERW potentials CSV
                if ew_ok and "potential [t]" in df_ew.columns:
                    expected_total = df_ew["potential [t]"].sum() * 0.2  # default max_land_usage=0.2
                    if abs(total_enoms - expected_total) / max(expected_total, 1) > 0.01:
                        print(f"    {WARN}  e_nom total ({total_enoms:,.0f} t) differs from "
                              f"expected ({expected_total:,.0f} t, assuming max_land_usage=0.2)")

        if not ew_carriers:
            print(f"\n{WARN}  No ERW carriers found — add_EW may NOT have run!")
        elif ew_links.empty or ew_stores.empty:
            print(f"\n{WARN}  Missing ERW links or stores — check add_EW() execution!")
        else:
            print(f"\n{OK}  ERW components present in pre-network.")

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

        ew_links  = n_opt.links [n_opt.links .carrier.str.contains("ERW", case=True, na=False)]
        ew_stores = n_opt.stores[n_opt.stores.carrier.str.contains("ERW", case=True, na=False)]

        # --- Links optimal ---
        print(f"\n  Links (carrier contains 'ERW'): {len(ew_links)}")
        if not ew_links.empty and "p_nom_opt" in ew_links.columns:
            active = ew_links[ew_links["p_nom_opt"] > 0]
            total  = ew_links["p_nom_opt"].sum()
            print(f"  Links with p_nom_opt > 0: {len(active)}")
            print(f"  Total p_nom_opt (all ERW links): {total:,.2f} MW_el")
            if active.empty:
                print(f"{WARN}  All ERW links have p_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  ERW links deployed in optimal solution.")
                cols = [c for c in ["bus0", "bus1", "bus2", "carrier", "p_nom_opt"] if c in active.columns]
                print(active[cols].to_string())

        # --- Stores optimal ---
        print(f"\n  Stores (carrier contains 'ERW'): {len(ew_stores)}")
        if not ew_stores.empty:
            # ERW stores are fixed capacity (e_nom, not e_nom_extendable)
            # check the dispatch: how much CO2 was actually sequestered
            if "e_nom" in ew_stores.columns:
                total_cap = ew_stores["e_nom"].sum()
                print(f"  Total store capacity (e_nom): {total_cap:,.0f} t CO2  ({total_cap/1e6:.3f} Mt CO2)")

            # check time series for actual sequestration
            if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
                ew_store_e = n_opt.stores_t["e"][ew_stores.index]
                if not ew_store_e.empty:
                    final_e = ew_store_e.iloc[-1]
                    total_stored = final_e.sum()
                    print(f"  CO2 stored at end of horizon: {total_stored:,.0f} t CO2  "
                          f"({total_stored/1e6:.3f} Mt CO2)")
                    if "e_nom" in ew_stores.columns:
                        utilisation = (final_e / ew_stores["e_nom"]).mean() * 100
                        print(f"  Mean store utilisation: {utilisation:.1f}%")
                    if total_stored == 0:
                        print(f"{WARN}  No CO2 sequestered — ERW not utilised in solution.")
                    else:
                        print(f"{OK}  ERW CO2 sequestration active in optimal solution.")

        if ew_links.empty and ew_stores.empty:
            print(f"\n{WARN}  No ERW components in optimal network!")

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
