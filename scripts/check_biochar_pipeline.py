"""
Check script for the biochar pipeline in pypsa-eur.
Run from the pypsa-eur root directory:

    python scripts/check_biochar_pipeline.py

Adjust BASE_DIR, RDIR, CLUSTERS, PLANNING_HORIZON, SECTOR_OPTS if needed.
"""

import sys
from pathlib import Path

import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR         = Path(".")       # run from pypsa-eur root
RDIR             = "biochar_2050"
CLUSTERS         = "50"
OPTS             = ""
SECTOR_OPTS      = "168h"
PLANNING_HORIZON = "2050"

# derived paths
# derived paths
RES     = BASE_DIR / "resources"
RES_RUN = BASE_DIR / "resources" / RDIR
RESULTS = BASE_DIR / "results"    / RDIR

# wildcard-based filename stem
WC = f"base_s_{CLUSTERS}_{OPTS}_{SECTOR_OPTS}_{PLANNING_HORIZON}"

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


# ── 1. BUILD: biochar CORINE potentials (build_biochar_potentials) ─────────────
section("1. BUILD: biochar CORINE land potentials")

biochar_csv = RES_RUN / f"biochar_potentials_s_{CLUSTERS}.csv"
biochar_png = RES_RUN / f"biochar_potentials_s_{CLUSTERS}.png"

csv_ok = check_file(biochar_csv, f"Biochar potentials CSV  s_{CLUSTERS}")
check_file(biochar_png, f"Biochar potentials PNG  s_{CLUSTERS}")

if csv_ok:
    df = pd.read_csv(biochar_csv)
    print(f"        Rows: {len(df)}  |  Columns: {list(df.columns)}")
    if "potential [sqkm]" in df.columns:
        total = df["potential [sqkm]"].sum()
        print(f"        Total potential area: {total:,.0f} km²")
        print(f"        Per-node [km²] — min: {df['potential [sqkm]'].min():.1f}, "
              f"mean: {df['potential [sqkm]'].mean():.1f}, "
              f"max: {df['potential [sqkm]'].max():.1f}")
    if df.isnull().any().any():
        print(f"{WARN}  NaN values detected in biochar potentials CSV.")

# ── 2. Pre-network (prepare_sector_network) ───────────────────────────────────
section("2. PRE-NETWORK: sector-coupled (prepare_sector_network)")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa

        n = pypsa.Network(str(prenet_path))

        # --- Carriers ---
        biochar_carriers = [c for c in n.carriers.index if "biochar" in c.lower()]
        print(f"\n  Carriers with 'biochar': {biochar_carriers}")

        if "co2 biochar" in n.carriers.index:
            co2_em = n.carriers.at["co2 biochar", "co2_emissions"]
            print(f"    co2 biochar co2_emissions = {co2_em}  (expected -1.0)")
            if abs(co2_em - (-1.0)) > 1e-6:
                print(f"{WARN}  co2_emissions != -1.0 — check add_biochar()!")

        # --- Buses ---
        bc_buses = n.buses[n.buses.carrier.str.contains("biochar", case=False, na=False)]
        print(f"\n  Buses (carrier contains 'biochar'): {len(bc_buses)}")
        if not bc_buses.empty:
            print(f"    Carriers present: {bc_buses['carrier'].unique().tolist()}")
            print(f"    Sample (first 5):\n{bc_buses[['location','carrier','unit']].head().to_string()}")

        # --- Links ---
        bc_links = n.links[n.links.carrier.str.contains("biochar", case=False, na=False)]
        print(f"\n  Links (carrier contains 'biochar'): {len(bc_links)}")
        if not bc_links.empty:
            print(f"    Carriers present: {bc_links['carrier'].unique().tolist()}")
            cols = [c for c in ["bus0","bus1","bus2","carrier","p_nom_extendable","capital_cost"] if c in bc_links.columns]
            print(bc_links[cols].head(10).to_string())

        # --- Stores ---
        bc_stores = n.stores[n.stores.carrier.str.contains("biochar", case=False, na=False)]
        print(f"\n  Stores (carrier contains 'biochar'): {len(bc_stores)}")
        if not bc_stores.empty:
            cols = [c for c in ["bus","carrier","e_nom_max","capital_cost","e_nom_extendable"] if c in bc_stores.columns]
            print(bc_stores[cols].head(10).to_string())
            if "e_nom_max" in bc_stores.columns:
                finite = bc_stores["e_nom_max"][bc_stores["e_nom_max"] < 1e18]
                print(f"\n    e_nom_max (finite) [tCO2] — "
                      f"min: {finite.min():.0f}, mean: {finite.mean():.0f}, max: {finite.max():.0f}")

        if not biochar_carriers:
            print(f"\n{WARN}  No biochar carriers found — add_biochar may NOT have run!")
        elif bc_links.empty or bc_stores.empty:
            print(f"\n{WARN}  Missing links or stores — check add_biochar() execution!")
        else:
            print(f"\n{OK}  Biochar components present in pre-network.")

    except Exception as e:
        print(f"\n{WARN}  Could not load pre-network: {e}")
else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run yet.")

# ── 3. Solved network (solve_sector_network) ──────────────────────────────────
section("3. OPTIMAL SOLUTION: solved network (solve_sector_network)")

opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok   = check_file(opt_path, f"Optimal network  {WC}.nc")

if opt_ok:
    try:
        import pypsa

        n_opt = pypsa.Network(str(opt_path))

        bc_links  = n_opt.links [n_opt.links .carrier.str.contains("biochar", case=False, na=False)]
        bc_stores = n_opt.stores[n_opt.stores.carrier.str.contains("biochar", case=False, na=False)]

        # --- Links optimal ---
        print(f"\n  Links (carrier contains 'biochar'): {len(bc_links)}")
        if not bc_links.empty and "p_nom_opt" in bc_links.columns:
            active = bc_links[bc_links["p_nom_opt"] > 0]
            total  = bc_links["p_nom_opt"].sum()
            print(f"  Links with p_nom_opt > 0: {len(active)}")
            print(f"  Total p_nom_opt (all biochar links): {total:,.2f} MW")
            if active.empty:
                print(f"{WARN}  All biochar links have p_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  Biochar links deployed in optimal solution.")
                print(active[["bus0","bus1","carrier","p_nom_opt"]].to_string())

        # --- Stores optimal ---
        print(f"\n  Stores (carrier contains 'biochar'): {len(bc_stores)}")
        if not bc_stores.empty and "e_nom_opt" in bc_stores.columns:
            active = bc_stores[bc_stores["e_nom_opt"] > 0]
            total  = bc_stores["e_nom_opt"].sum()
            print(f"  Stores with e_nom_opt > 0: {len(active)}")
            print(f"  Total e_nom_opt: {total:,.0f} tCO2  ({total/1e6:.3f} MtCO2)")
            if active.empty:
                print(f"{WARN}  All biochar stores have e_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  Biochar stores deployed. Total CO2 stored: {total/1e6:.3f} MtCO2")
                print(f"\n  Per-node e_nom_opt [tCO2] stats:")
                print(f"    min:  {bc_stores['e_nom_opt'].min():,.0f}")
                print(f"    mean: {bc_stores['e_nom_opt'].mean():,.0f}")
                print(f"    max:  {bc_stores['e_nom_opt'].max():,.0f}")

        if bc_links.empty and bc_stores.empty:
            print(f"\n{WARN}  No biochar components in optimal network!")

    except Exception as e:
        print(f"\n{WARN}  Could not load optimal network: {e}")
else:
    print(f"\n{FAIL}  Optimal network missing — solve_sector_network has not run yet.")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  Run:            {RDIR if RDIR else '(none)'}")
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
