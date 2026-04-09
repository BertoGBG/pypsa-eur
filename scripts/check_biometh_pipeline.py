"""
Check script for the biomethanation pipeline in pypsa-eur.
Run from the pypsa-eur root directory:

    python scripts/check_biometh_pipeline.py --config config/config.CDRs.yaml

Wildcards are read from the config file. Override any value on the CLI:
    --run-name NAME  --clusters N  --horizon YEAR  --sector-opts OPTS

Note: biomethanation has no separate potential calculation step (unlike biochar/EW/
afforestation). The two technologies added are:
  - biomethanation biogas  (H2 + biogas -> biomethane, in add_biomass)
  - biomethanation CO2     (H2 + CO2   -> biomethane, in add_power_to_gas)
"""

from pathlib import Path

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


# ── 1. Pre-network (prepare_sector_network) ───────────────────────────────────
section("1. PRE-NETWORK: sector-coupled (prepare_sector_network)")

prenet_path = RES_RUN / "networks" / f"{WC}.nc"
prenet_ok   = check_file(prenet_path, f"Pre-network  {WC}.nc")

if prenet_ok:
    try:
        import pypsa

        n = pypsa.Network(str(prenet_path))

        # --- Carriers ---
        bm_carriers = [c for c in n.carriers.index if "biomethan" in c.lower()]
        print(f"\n  Carriers with 'biomethan': {bm_carriers}")
        for expected in ["biomethanation biogas", "biomethanation CO2"]:
            if expected in n.carriers.index:
                print(f"    {OK}  Carrier '{expected}' present.")
            else:
                print(f"    {WARN}  Carrier '{expected}' NOT found!")

        # --- Links: biomethanation biogas (H2 + biogas -> biomethane) ---
        bm_biogas_links = n.links[
            n.links.carrier.str.contains("biomethanation biogas", case=False, na=False)
        ]
        print(f"\n  Links 'biomethanation biogas' (H2 + biogas -> gas): {len(bm_biogas_links)}")
        if not bm_biogas_links.empty:
            cols = [c for c in ["bus0", "bus1", "bus2", "carrier",
                                 "p_nom_extendable", "efficiency", "efficiency2",
                                 "capital_cost", "marginal_cost"] if c in bm_biogas_links.columns]
            print(bm_biogas_links[cols].head(10).to_string())
            if "p_nom_extendable" in bm_biogas_links.columns:
                if not bm_biogas_links["p_nom_extendable"].all():
                    print(f"    {WARN}  Some biomethanation biogas links are NOT extendable!")
            # bus0 should be H2, bus1 biogas, bus2 gas
            if "bus0" in bm_biogas_links.columns:
                unexpected_bus0 = bm_biogas_links[~bm_biogas_links["bus0"].str.contains(" H2", na=False)]
                if not unexpected_bus0.empty:
                    print(f"    {WARN}  Unexpected bus0 (expected H2 bus): {unexpected_bus0['bus0'].tolist()}")
        else:
            print(f"    {WARN}  No biomethanation biogas links found — check biomethanation_biogas option!")

        # --- Links: biomethanation CO2 (H2 + CO2 -> biomethane) ---
        bm_co2_links = n.links[
            n.links.carrier.str.contains("biomethanation CO2", case=False, na=False)
        ]
        print(f"\n  Links 'biomethanation CO2' (H2 + CO2 -> gas): {len(bm_co2_links)}")
        if not bm_co2_links.empty:
            cols = [c for c in ["bus0", "bus1", "bus2", "carrier",
                                 "p_nom_extendable", "efficiency", "efficiency2",
                                 "capital_cost", "marginal_cost"] if c in bm_co2_links.columns]
            print(bm_co2_links[cols].head(10).to_string())
            if "p_nom_extendable" in bm_co2_links.columns:
                if not bm_co2_links["p_nom_extendable"].all():
                    print(f"    {WARN}  Some biomethanation CO2 links are NOT extendable!")
            # bus0 should be H2, bus1 CO2 node, bus2 gas
            if "bus1" in bm_co2_links.columns:
                unexpected_bus1 = bm_co2_links[~bm_co2_links["bus1"].str.contains("co2|CO2", na=False, regex=True)]
                if not unexpected_bus1.empty:
                    print(f"    {WARN}  Unexpected bus1 (expected CO2 bus): {unexpected_bus1['bus1'].tolist()}")
        else:
            print(f"    {WARN}  No biomethanation CO2 links found — check biomethanation_CO2 option!")

        # --- Summary for pre-network ---
        if not bm_carriers:
            print(f"\n{WARN}  No biomethanation carriers found — add_biomass / add_power_to_gas may NOT have run!")
        elif bm_biogas_links.empty and bm_co2_links.empty:
            print(f"\n{WARN}  Missing all biomethanation links — check options in config!")
        else:
            print(f"\n{OK}  Biomethanation components present in pre-network.")

    except Exception as e:
        print(f"\n{WARN}  Could not load pre-network: {e}")
else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run yet.")


# ── 2. Solved network (solve_sector_network) ──────────────────────────────────
section("2. OPTIMAL SOLUTION: solved network (solve_sector_network)")

opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok   = check_file(opt_path, f"Optimal network  {WC}.nc")

if opt_ok:
    try:
        import pypsa

        n_opt = pypsa.Network(str(opt_path))

        bm_links_all = n_opt.links[
            n_opt.links.carrier.str.contains("biomethanation", case=False, na=False)
        ]

        # --- biomethanation biogas optimal ---
        bm_biogas_opt = bm_links_all[
            bm_links_all.carrier.str.contains("biomethanation biogas", case=False, na=False)
        ]
        print(f"\n  Links 'biomethanation biogas': {len(bm_biogas_opt)}")
        if not bm_biogas_opt.empty and "p_nom_opt" in bm_biogas_opt.columns:
            active = bm_biogas_opt[bm_biogas_opt["p_nom_opt"] > 0]
            total  = bm_biogas_opt["p_nom_opt"].sum()
            print(f"  Active links (p_nom_opt > 0): {len(active)}")
            print(f"  Total p_nom_opt: {total:,.2f} MW_H2")
            if active.empty:
                print(f"{WARN}  All biomethanation biogas links have p_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  Biomethanation biogas deployed in optimal solution.")
                cols = [c for c in ["bus0", "bus1", "bus2", "carrier", "p_nom_opt"] if c in active.columns]
                print(active[cols].to_string())

        # --- biomethanation CO2 optimal ---
        bm_co2_opt = bm_links_all[
            bm_links_all.carrier.str.contains("biomethanation CO2", case=False, na=False)
        ]
        print(f"\n  Links 'biomethanation CO2': {len(bm_co2_opt)}")
        if not bm_co2_opt.empty and "p_nom_opt" in bm_co2_opt.columns:
            active = bm_co2_opt[bm_co2_opt["p_nom_opt"] > 0]
            total  = bm_co2_opt["p_nom_opt"].sum()
            print(f"  Active links (p_nom_opt > 0): {len(active)}")
            print(f"  Total p_nom_opt: {total:,.2f} MW_H2")
            if active.empty:
                print(f"{WARN}  All biomethanation CO2 links have p_nom_opt = 0 (not deployed).")
            else:
                print(f"{OK}  Biomethanation CO2 deployed in optimal solution.")
                cols = [c for c in ["bus0", "bus1", "bus2", "carrier", "p_nom_opt"] if c in active.columns]
                print(active[cols].to_string())

        # --- Combined summary ---
        if bm_links_all.empty:
            print(f"\n{WARN}  No biomethanation links found in optimal network!")
        else:
            total_opt = bm_links_all["p_nom_opt"].sum() if "p_nom_opt" in bm_links_all.columns else 0
            print(f"\n  Combined biomethanation total p_nom_opt: {total_opt:,.2f} MW_H2")
            if total_opt == 0:
                print(f"{WARN}  Biomethanation not utilised in solution.")
            else:
                print(f"{OK}  Biomethanation active in optimal solution.")

        # --- Check dispatch (p0 time series) ---
        if hasattr(n_opt, "links_t") and "p0" in n_opt.links_t:
            bm_cols = [c for c in n_opt.links_t["p0"].columns if "biomethan" in c.lower()]
            if bm_cols:
                p0 = n_opt.links_t["p0"][bm_cols]
                print(f"\n  Dispatch time series found for {len(bm_cols)} biomethanation link(s).")
                annual_MWh = p0.sum()
                print(f"  Annual dispatch [MWh H2 consumed]:")
                print(f"    Total:  {annual_MWh.sum():,.0f} MWh")
                print(f"    Per link — min: {annual_MWh.min():,.0f}, "
                      f"mean: {annual_MWh.mean():,.0f}, "
                      f"max: {annual_MWh.max():,.0f}")

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
