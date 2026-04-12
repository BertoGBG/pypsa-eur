"""
Check script for the afforestation pipeline in pypsa-eur.
Run from the pypsa-eur root directory:

    python scripts/check_afforestation_pipeline.py --config config/config.CDRs.yaml

Wildcards are read from the config file. Override any value on the CLI:
    --run-name NAME  --clusters N  --horizon YEAR  --sector-opts OPTS
    --potential-type density|growth
"""

import sys
from pathlib import Path

import pandas as pd

from _check_utils import parse_check_args, load_check_params

# ── Configuration (from config file + CLI overrides) ──────────────────────────
_args = parse_check_args(extra_args=[
    (["--potential-type"],
     {"default": None,
      "metavar": "TYPE",
      "help": "Override potential type (density or growth). "
              "Reads afforestation.potential_type from config if not set."}),
])
_p = load_check_params(_args)

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
POTENTIAL_TYPE   = (
    _args.potential_type
    or _p["cfg"].get("afforestation", {}).get("potential_type", "density")
)

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


# ── 1. Retrieved files (get_afforestation_nuts_file) ──────────────────────────
section("1. RETRIEVE: afforestation NUTS data")

if POTENTIAL_TYPE == "density":
    nuts_file = RES / "afforestation_nuts_biomass_densities.xlsx"
    check_file(nuts_file, "NUTS0 biomass densities (Excel, density mode)")
else:
    nuts_file = RES / "afforestation_nuts2_growth_rates.csv"
    check_file(nuts_file, "NUTS2 growth rates (CSV, growth mode)")

# ── 2. CORINE potentials (build_afforestation_corine_potentials) ───────────────
section("2. BUILD: CORINE afforestation land area")

corine_csv = RES_RUN / f"afforestation_corine_potentials_s_{CLUSTERS}.csv"
corine_png = RES_RUN / f"afforestation_corine_potentials_s_{CLUSTERS}.png"

corine_ok = check_file(corine_csv, f"CORINE potentials CSV  s_{CLUSTERS}")
check_file(corine_png, f"CORINE potentials PNG  s_{CLUSTERS}")

if corine_ok:
    df_corine = pd.read_csv(corine_csv)
    print(f"        Rows: {len(df_corine)}  |  Columns: {list(df_corine.columns)}")
    if "area [sqkm]" in df_corine.columns:
        total_area = df_corine["area [sqkm]"].sum()
        print(f"        Total available CORINE area: {total_area:,.0f} km²")
    if df_corine.isnull().any().any():
        print(f"{WARN}  NaN values detected in CORINE potentials CSV.")

# ── 3. afforestation potentials (build_afforestation_potentials) ───────────────
section("3. BUILD: afforestation CO2 potentials (clustered)")

affo_pot = RES_RUN / f"afforestation_potentials_s_{CLUSTERS}.csv"
pot_ok = check_file(affo_pot, f"Afforestation potentials  s_{CLUSTERS}")

if pot_ok:
    df_pot = pd.read_csv(affo_pot)
    print(f"        Rows: {len(df_pot)}  |  Columns: {list(df_pot.columns)}")
    if "potential [t/ha]" in df_pot.columns:
        print(f"        Potential [t/ha] — min: {df_pot['potential [t/ha]'].min():.2f}, "
              f"mean: {df_pot['potential [t/ha]'].mean():.2f}, "
              f"max: {df_pot['potential [t/ha]'].max():.2f}")
    if df_pot.isnull().any().any():
        print(f"{WARN}  NaN values detected in afforestation potentials CSV.")

# ── 4. Pre-network (prepare_sector_network) ───────────────────────────────────
section("4. PRE-NETWORK: sector-coupled (prepare_sector_network)")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa

        n = pypsa.Network(str(prenet_path))

        # --- Carrier ---
        affo_carriers = [c for c in n.carriers.index if "afforestation" in c.lower()]
        print(f"\n  Carriers with 'afforestation': {affo_carriers}")
        if "co2 afforestation" in n.carriers.index:
            co2_em = n.carriers.at["co2 afforestation", "co2_emissions"]
            print(f"    co2_emissions = {co2_em}  (expected 0.0 — removal handled via link flow)")

        # --- Buses ---
        affo_buses = n.buses[n.buses.carrier.str.contains("afforestation", case=False, na=False)]
        print(f"\n  Buses (carrier contains 'afforestation'): {len(affo_buses)}")
        if not affo_buses.empty:
            print(f"    Sample (first 5):\n{affo_buses[['location','carrier','unit']].head().to_string()}")
        if len(affo_buses) != int(CLUSTERS):
            print(f"{WARN}  Expected ~{CLUSTERS} afforestation buses, found {len(affo_buses)}")

        # --- Links ---
        affo_links = n.links[n.links.carrier.str.contains("afforestation", case=False, na=False)]
        print(f"\n  Links (carrier contains 'afforestation'): {len(affo_links)}")
        if not affo_links.empty:
            print(affo_links[["bus0", "bus1", "carrier", "p_nom_extendable",
                               "p_min_pu", "p_max_pu"]].head(10).to_string())

        # --- Stores ---
        affo_stores = n.stores[n.stores.carrier.str.contains("afforestation", case=False, na=False)]
        print(f"\n  Stores (carrier contains 'afforestation'): {len(affo_stores)}")
        if not affo_stores.empty:
            cols = ["bus", "carrier", "e_nom_max", "capital_cost", "e_nom_extendable"]
            available_cols = [c for c in cols if c in affo_stores.columns]
            print(affo_stores[available_cols].head(10).to_string())
            if "e_nom_max" in affo_stores.columns:
                finite_max = affo_stores["e_nom_max"][affo_stores["e_nom_max"] < 1e18]
                print(f"\n    e_nom_max (finite) — "
                      f"min: {finite_max.min():.0f}, "
                      f"mean: {finite_max.mean():.0f}, "
                      f"max: {finite_max.max():.0f}  [tCO2]")
            if "capital_cost" in affo_stores.columns:
                print(f"    capital_cost — "
                      f"min: {affo_stores['capital_cost'].min():.2f}, "
                      f"mean: {affo_stores['capital_cost'].mean():.2f}, "
                      f"max: {affo_stores['capital_cost'].max():.2f}")

        if not affo_carriers:
            print(f"\n{WARN}  No afforestation carrier found — add_afforestation may NOT have run!")
        elif affo_links.empty or affo_stores.empty:
            print(f"\n{WARN}  Missing links or stores — check add_afforestation() execution!")
        else:
            print(f"\n{OK}  Afforestation components present in pre-network.")

    except Exception as e:
        print(f"\n{WARN}  Could not load pre-network: {e}")
else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run yet.")

# ── 5. Solved network (solve_sector_network) ──────────────────────────────────
section("5. OPTIMAL SOLUTION: solved network (solve_sector_network)")

opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok   = check_file(opt_path, f"Optimal network  {WC}.nc")

if opt_ok:
    try:
        import pypsa

        n_opt = pypsa.Network(str(opt_path))

        affo_links  = n_opt.links [n_opt.links .carrier.str.contains("afforestation", case=False, na=False)]
        affo_stores = n_opt.stores[n_opt.stores.carrier.str.contains("afforestation", case=False, na=False)]

        # --- Links optimal ---
        print(f"\n  Links (carrier contains 'afforestation'): {len(affo_links)}")
        if not affo_links.empty:
            if "p_nom_opt" in affo_links.columns:
                active_links = affo_links[affo_links["p_nom_opt"] > 0]
                print(f"  Links with p_nom_opt > 0: {len(active_links)}")
                total_p_nom_opt = affo_links["p_nom_opt"].sum()
                print(f"  Total p_nom_opt (all afforestation links): {total_p_nom_opt:,.2f}")
                if active_links.empty:
                    print(f"{WARN}  All afforestation links have p_nom_opt = 0 (not deployed).")
                else:
                    print(f"{OK}  Afforestation links deployed in optimal solution.")
                    print(active_links[["bus0","bus1","carrier","p_nom_opt"]].to_string())

        # --- Stores optimal ---
        print(f"\n  Stores (carrier contains 'afforestation'): {len(affo_stores)}")
        if not affo_stores.empty:
            if "e_nom_opt" in affo_stores.columns:
                active_stores = affo_stores[affo_stores["e_nom_opt"] > 0]
                total_e_nom_opt = affo_stores["e_nom_opt"].sum()
                print(f"  Stores with e_nom_opt > 0: {len(active_stores)}")
                print(f"  Total e_nom_opt (all afforestation stores): {total_e_nom_opt:,.2f} tCO2")
                if active_stores.empty:
                    print(f"{WARN}  All afforestation stores have e_nom_opt = 0 (not deployed).")
                else:
                    print(f"{OK}  Afforestation stores deployed. Total CO2 stored: "
                          f"{total_e_nom_opt/1e6:.3f} MtCO2")

        # --- Statistics ---------------------------------------------------------
        if not affo_stores.empty and "e_nom_opt" in affo_stores.columns:
            print(f"\n  Per-node e_nom_opt [tCO2] stats:")
            print(f"    min:  {affo_stores['e_nom_opt'].min():,.0f}")
            print(f"    mean: {affo_stores['e_nom_opt'].mean():,.0f}")
            print(f"    max:  {affo_stores['e_nom_opt'].max():,.0f}")

        # --- Capital cost per node + weighted average ---------------------------
        if (
            not affo_stores.empty
            and "e_nom_opt" in affo_stores.columns
            and "capital_cost" in affo_stores.columns
        ):
            print(f"\n  Capital cost per node [€/tCO2]:")
            node_costs = affo_stores[["capital_cost", "e_nom_opt"]].copy()
            print(node_costs["capital_cost"].to_string())

            total_weight = affo_stores["e_nom_opt"].sum()
            if total_weight > 0:
                wavg_cost = (
                    affo_stores["capital_cost"] * affo_stores["e_nom_opt"]
                ).sum() / total_weight
                print(f"\n  Weighted-avg capital cost (by e_nom_opt): {wavg_cost:.2f} €/tCO2")

        if affo_links.empty and affo_stores.empty:
            print(f"\n{WARN}  No afforestation components in optimal network!")

    except Exception as e:
        print(f"\n{WARN}  Could not load optimal network: {e}")
else:
    print(f"\n{FAIL}  Optimal network missing — solve_sector_network has not run yet.")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  Run:            {RDIR}")
print(f"  Wildcard:       {WC}")
print(f"  Potential type: {POTENTIAL_TYPE}")
print(f"  Resources dir:  {RES_RUN.resolve()}")
print(f"  Results dir:    {RESULTS.resolve()}")
print()
print(f"  Passed: {len(passed)}")
print(f"  Failed: {len(failed)}")
if failed:
    print(f"\n  Missing files:")
    for f in failed:
        print(f"    - {f}")
