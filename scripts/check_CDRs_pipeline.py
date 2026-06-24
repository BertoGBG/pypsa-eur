"""
Consolidated check script for all four CDR (Carbon Dioxide Removal) pipelines
in pypsa-eur: afforestation, biochar, perennials, and rock weathering.

Run from the pypsa-eur root directory:

    python scripts/check_CDRs_pipeline.py CDRs_2050

Only checks the CDR techs actually enabled in the run's saved config
(sector.afforestation / sector.biochar.enable / sector.perennials /
sector.rock_weathering). Replaces the four standalone
check_afforestation_pipeline.py / check_biochar_pipeline.py /
check_perennials_pipeline.py / check_rock_weathering_pipeline.py scripts.

Wildcards are read from the saved run config automatically.
Override any value on the CLI:
    --run-name NAME  --clusters N  --horizon YEAR  --sector-opts OPTS
    --potential-type density|growth   (afforestation only)
    --shared-resources NAME           (perennials only)
    --config PATH    (direct path to a saved config YAML)
"""

from pathlib import Path

import pandas as pd
import pypsa

from _check_utils import parse_check_args, load_check_params, print_co2_system_diagnostics

# ── Configuration (from config file + CLI overrides) ──────────────────────────
_args = parse_check_args(extra_args=[
    (["--potential-type"],
     {"default": None,
      "metavar": "TYPE",
      "help": "Override afforestation potential type (density or growth). "
              "Reads afforestation.potential_type from config if not set."}),
    (["--shared-resources"],
     {"default": None,
      "metavar": "NAME",
      "help": "Override shared resources directory name for perennials. "
              "Reads run.shared_resources.policy from config if not set, "
              "falls back to run name."}),
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
SHARED_RES       = _p["SHARED_RES"]
CFG              = _p["cfg"]

POTENTIAL_TYPE = (
    _args.potential_type
    or CFG.get("afforestation", {}).get("potential_type", "density")
)
_assign_capacity_duals = CFG.get("solving", {}).get("options", {}).get("assign_capacity_duals", False)

# ── Active-tech detection ───────────────────────────────────────────────────────
# Mirrors the exact gates used in prepare_sector_network.py's main flow
# (options = snakemake.params.sector = cfg["sector"]):
#   if options.get("biochar", {}).get("enable"): add_biochar(...)
#   if options.get("rock_weathering"):           add_rock_weathering(...)
#   if options.get("afforestation"):             add_afforestation(...)
#   if options.get("perennials"):                add_perennials(...)
_sector_cfg = CFG.get("sector", {})
ACTIVE = {
    "afforestation":    bool(_sector_cfg.get("afforestation")),
    "biochar":          bool(_sector_cfg.get("biochar", {}).get("enable")),
    "perennials":       bool(_sector_cfg.get("perennials")),
    "rock_weathering":  bool(_sector_cfg.get("rock_weathering")),
}

# ── Helpers ──────────────────────────────────────────────────────────────────────
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
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def header(title: str):
    print(f"\n{'#' * 70}")
    print(f"  {title}")
    print("#" * 70)


def mu_ext_e_nom_upper_check(stores, label: str):
    """Shadow price of e_nom_max (assign_capacity_duals), common to all four
    CDR techs now that every CDR Store is e_nom_extendable=True with a
    resource-potential e_nom_max. Dual of "Store-ext-e_nom-upper"
    (e_nom_opt <= e_nom_max): the marginal value of relaxing that potential
    by one more tCO2 of capacity. Only written to
    n.stores["mu_ext_e_nom_upper"] if solving.options.assign_capacity_duals:
    true (see solve_network.py, "Assign scalar capacity duals" block) --
    requires a re-run with that config flag set if not already enabled.
    """
    _dual_status = (
        "enabled" if _assign_capacity_duals
        else "disabled (set solving.options.assign_capacity_duals: true and re-run to enable)"
    )
    print(f"\n  assign_capacity_duals: {_dual_status}")
    if not _assign_capacity_duals:
        return
    if "mu_ext_e_nom_upper" in stores.columns:
        mu = stores["mu_ext_e_nom_upper"].dropna()
        binding = mu[mu.abs() > 1e-6]
        print(f"\n  mu_ext_e_nom_upper (shadow price of e_nom_max) [{len(mu)} {label} stores]:")
        print(f"    non-zero (binding): {len(binding)}")
        if not mu.empty:
            print(f"    min:  {mu.min():,.4f}")
            print(f"    mean: {mu.mean():,.4f}")
            print(f"    max:  {mu.max():,.4f}")
        if not binding.empty:
            print(f"\n    Binding nodes (top 10):")
            print(binding.sort_values().tail(10).to_string())
    else:
        print(f"\n{WARN}  mu_ext_e_nom_upper not found in stores — was "
              f"assign_capacity_duals: true when solving?")


def flow_weighted_bus_price(n_opt, stores, wavg_cost=None):
    """Flow-weighted mean marginal price at each CDR store's own bus.

    Reads flow directly off the STORE (not the feeding link): these CDR
    stores are one-way accumulators (e_cyclic=False, never discharge), so
    the amount delivered each snapshot is unambiguously -stores_t.p (PyPSA's
    Store convention: p>0 discharging, p<0 charging). This sidesteps having
    to track which bus index (bus1, bus2, ...) and sign convention a given
    tech's link uses -- the store's own bus/flow are correct regardless.

    Two-step, node-then-capacity weighting:
      1. Per node: time-weighted average marginal price at that node's bus,
         weighted by (flow into the store) x "stores" snapshot weighting.
      2. Across nodes: weighted average of the per-node prices, weighted by
         e_nom_opt -- the SAME node-weighting used for "Weighted-avg capital
         cost (by e_nom_opt)", so the two numbers are directly comparable
         even when a store isn't fully utilised (flow total can then differ
         from e_nom_opt, where a flow-weighted pooling would diverge from
         this capacity-weighted one).
    """
    mp = n_opt.buses_t.marginal_price if "marginal_price" in n_opt.buses_t else None
    if mp is None or mp.empty or stores.empty:
        print(f"\n{WARN}  buses_t.marginal_price unavailable or empty -- "
              f"check the network was solved with a solver returning duals.")
        return

    weighting = n_opt.snapshot_weightings["stores"]
    store_flow = -n_opt.stores_t.p[stores.index]  # flow into the store (charging is p<0)

    node_prices = {}
    node_flow_total = {}
    for store_name in stores.index:
        bus = stores.at[store_name, "bus"]
        if bus not in mp.columns:
            continue
        qty = store_flow[store_name] * weighting
        total_qty = qty.sum()
        if total_qty > 0:
            node_prices[store_name] = (mp[bus] * qty).sum() / total_qty
            node_flow_total[store_name] = total_qty

    if not node_prices:
        return
    node_price = pd.Series(node_prices)
    node_weight = stores.loc[node_price.index, "e_nom_opt"]
    total_weight = node_weight.sum()
    if total_weight <= 0:
        return

    flow_wavg_price = (node_price * node_weight).sum() / total_weight
    total_flow = sum(node_flow_total.values())
    print(f"\n  Flow-weighted mean marginal price (per-node time-weighted by "
          f"flow x 'stores' weighting, then node-weighted by e_nom_opt): "
          f"{flow_wavg_price:.2f} €/tCO2")
    print(f"    Total CO2 via flow accumulation: {total_flow:,.0f} tCO2  "
          f"vs. total e_nom_opt: {total_weight:,.0f} tCO2  "
          f"(ratio: {total_flow / total_weight:.4f}, expect ~1.0)")
    if wavg_cost:
        print(f"    Ratio flow-weighted price / capacity-weighted cost: "
              f"{flow_wavg_price / wavg_cost:.4f}  (expect ~1.0 at LP optimum)")


# ── Afforestation ────────────────────────────────────────────────────────────────

def check_afforestation_build():
    section("AFFORESTATION 1. RETRIEVE: afforestation NUTS data")
    if POTENTIAL_TYPE == "density":
        nuts_file = RES_RUN / "afforestation_nuts_biomass_densities.xlsx"
        check_file(nuts_file, "NUTS0 biomass densities (Excel, density mode)")
    else:
        nuts_file = RES_RUN / "afforestation_rates_nuts2_full.csv"
        check_file(nuts_file, "NUTS2 growth rates (CSV, growth mode)")
        weights_file = RES_RUN / "afforestation_nuts2_monthly_weights.csv"
        check_file(weights_file, "NUTS2 monthly weights (CSV, growth mode)")

    section("AFFORESTATION 2. BUILD: CORINE afforestation land area")
    corine_csv = RES_RUN / f"afforestation_available_land_s_{CLUSTERS}.csv"
    corine_ok = check_file(corine_csv, f"Available land CSV  s_{CLUSTERS}")
    if corine_ok:
        df_corine = pd.read_csv(corine_csv)
        print(f"        Rows: {len(df_corine)}  |  Columns: {list(df_corine.columns)}")
        if "area [sqkm]" in df_corine.columns:
            total_area = df_corine["area [sqkm]"].sum()
            print(f"        Total available CORINE area: {total_area:,.0f} km²")
        if df_corine.isnull().any().any():
            print(f"{WARN}  NaN values detected in CORINE potentials CSV.")

    section("AFFORESTATION 3. BUILD: afforestation CO2 potentials (clustered)")
    affo_pot = RES_RUN / f"afforestation_potentials_s_{CLUSTERS}.csv"
    pot_ok = check_file(affo_pot, f"Afforestation potentials  s_{CLUSTERS}")
    if pot_ok:
        df_pot = pd.read_csv(affo_pot, index_col="node")
        print(f"        Rows: {len(df_pot)}  |  Columns: {list(df_pot.columns)}")
        if POTENTIAL_TYPE == "density" and "AGB [t]" in df_pot.columns:
            print(f"        AGB [t] — min: {df_pot['AGB [t]'].min():,.0f}, "
                  f"mean: {df_pot['AGB [t]'].mean():,.0f}, "
                  f"max: {df_pot['AGB [t]'].max():,.0f}")
        elif POTENTIAL_TYPE == "growth" and "potential [tCO2/y]" in df_pot.columns:
            total_gross_potential = df_pot["potential [tCO2/y]"].sum()
            print(f"        Total potential (gross, pre-CRCF): {total_gross_potential:,.0f} tCO2/y  "
                  f"({total_gross_potential / 1e6:.3f} MtCO2/y)")
            print(f"        Potential [tCO2/y] — min: {df_pot['potential [tCO2/y]'].min():.1f}, "
                  f"mean: {df_pot['potential [tCO2/y]'].mean():.1f}, "
                  f"max: {df_pot['potential [tCO2/y]'].max():.1f}")
            print(f"        CO2 seq rate [tCO2/(ha y)] — min: {df_pot['CO2 seq rate tCO2/(ha y)'].min():.2f}, "
                  f"mean: {df_pot['CO2 seq rate tCO2/(ha y)'].mean():.2f}, "
                  f"max: {df_pot['CO2 seq rate tCO2/(ha y)'].max():.2f}")
        if df_pot.isnull().any().any():
            print(f"{WARN}  NaN values detected in afforestation potentials CSV.")

    if POTENTIAL_TYPE == "growth":
        section("AFFORESTATION 3b. BUILD: node-level monthly weights and seasonal profile")
        mw_csv = RES_RUN / f"afforestation_monthly_weights_s_{CLUSTERS}.csv"
        sp_csv = RES_RUN / f"afforestation_seasonal_profile_s_{CLUSTERS}.csv"
        pot_png = RES_RUN / f"afforestation_potentials_s_{CLUSTERS}.png"
        mw_ok = check_file(mw_csv, f"Monthly weights CSV  s_{CLUSTERS}")
        check_file(sp_csv, f"Seasonal profile CSV  s_{CLUSTERS}")
        check_file(pot_png, f"Afforestation potentials PNG  s_{CLUSTERS}")
        if mw_ok:
            df_mw = pd.read_csv(mw_csv, index_col="node")
            print(f"        Rows: {len(df_mw)}  |  Columns: {list(df_mw.columns)}")
            row_sums = df_mw.sum(axis=1)
            bad = row_sums[(row_sums - 1.0).abs() > 0.01]
            if bad.empty:
                print(f"        Monthly weights sum to ~1.0 for all nodes  {OK}")
            else:
                print(f"{WARN}  {len(bad)} nodes have weights not summing to 1: {bad.index.tolist()[:5]}")


def check_afforestation_prenet(n):
    section("AFFORESTATION: pre-network components")
    affo_carriers = [c for c in n.carriers.index if "afforestation" in c.lower()]
    print(f"\n  Carriers with 'afforestation': {affo_carriers}")
    if "co2 afforestation" in n.carriers.index:
        co2_em = n.carriers.at["co2 afforestation", "co2_emissions"]
        print(f"    co2_emissions = {co2_em}  (expected 0.0 — removal handled via link flow)")

    affo_buses = n.buses[n.buses.carrier.str.contains("afforestation", case=False, na=False)]
    print(f"\n  Buses (carrier contains 'afforestation'): {len(affo_buses)}")
    if len(affo_buses) != int(CLUSTERS):
        print(f"{WARN}  Expected ~{CLUSTERS} afforestation buses, found {len(affo_buses)}")

    affo_links = n.links[n.links.carrier.str.contains("afforestation", case=False, na=False)]
    print(f"\n  Links (carrier contains 'afforestation'): {len(affo_links)}")
    if not affo_links.empty and "efficiency" in affo_links.columns:
        eff_vals = affo_links["efficiency"].unique()
        print(f"    efficiency values: {eff_vals}")
        if any(abs(e - 1.0) > 1e-6 for e in eff_vals):
            print(f"{WARN}  efficiency != 1.0 detected — link should be mass-conserving; "
                  f"crcf_efficiency belongs on the potential (e_nom_max), not the link.")
        else:
            print(f"{OK}  efficiency = 1.0 (link is mass-conserving, as expected).")

    affo_stores = n.stores[n.stores.carrier.str.contains("afforestation", case=False, na=False)]
    print(f"\n  Stores (carrier contains 'afforestation'): {len(affo_stores)}")
    if not affo_stores.empty and "e_nom_max" in affo_stores.columns:
        finite_max = affo_stores["e_nom_max"][affo_stores["e_nom_max"] < 1e18]
        print(f"\n    Total e_nom_max (net, post-CRCF): {finite_max.sum():,.0f} tCO2  "
              f"({finite_max.sum() / 1e6:.3f} MtCO2)")

    if not affo_carriers:
        print(f"\n{WARN}  No afforestation carrier found — add_afforestation may NOT have run!")
    elif affo_links.empty or affo_stores.empty:
        print(f"\n{WARN}  Missing links or stores — check add_afforestation() execution!")
    else:
        print(f"\n{OK}  Afforestation components present in pre-network.")


def check_afforestation_optimal(n_opt):
    section("AFFORESTATION: optimal solution")
    affo_links  = n_opt.links [n_opt.links .carrier.str.contains("afforestation", case=False, na=False)]
    affo_stores = n_opt.stores[n_opt.stores.carrier.str.contains("afforestation", case=False, na=False)]

    print(f"\n  Links (carrier contains 'afforestation'): {len(affo_links)}")
    total_p_nom_opt = 0.0
    if not affo_links.empty and "p_nom_opt" in affo_links.columns:
        active_links = affo_links[affo_links["p_nom_opt"] > 0]
        total_p_nom_opt = affo_links["p_nom_opt"].sum()
        print(f"  Links with p_nom_opt > 0: {len(active_links)}")
        print(f"  Total p_nom_opt: {total_p_nom_opt:,.2f}")
        if active_links.empty:
            print(f"{WARN}  All afforestation links have p_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  Afforestation links deployed in optimal solution.")

    print(f"\n  Stores (carrier contains 'afforestation'): {len(affo_stores)}")
    total_e_nom_opt = 0.0
    if not affo_stores.empty and "e_nom_opt" in affo_stores.columns:
        active_stores = affo_stores[affo_stores["e_nom_opt"] > 0]
        total_e_nom_opt = affo_stores["e_nom_opt"].sum()
        print(f"  Stores with e_nom_opt > 0: {len(active_stores)}")
        print(f"  Total e_nom_opt: {total_e_nom_opt:,.2f} tCO2  ({total_e_nom_opt/1e6:.3f} MtCO2/yr)")
        if active_stores.empty:
            print(f"{WARN}  All afforestation stores have e_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  Afforestation stores deployed.")

        if "e_nom_max" in affo_stores.columns:
            finite_max = affo_stores["e_nom_max"][affo_stores["e_nom_max"] < 1e18]
            total_e_nom_max = finite_max.sum()
            print(f"\n  Total e_nom_max (available potential): "
                  f"{total_e_nom_max:,.0f} tCO2  ({total_e_nom_max/1e6:.3f} MtCO2/yr)")
            if total_e_nom_max > 0:
                utilisation = total_e_nom_opt / total_e_nom_max * 100
                print(f"  Potential utilisation (e_nom_opt / e_nom_max): {utilisation:.1f}%")

    wavg_cost = None
    if (
        not affo_stores.empty
        and "e_nom_opt" in affo_stores.columns
        and "capital_cost" in affo_stores.columns
    ):
        total_weight = affo_stores["e_nom_opt"].sum()
        if total_weight > 0:
            wavg_cost = (
                affo_stores["capital_cost"] * affo_stores["e_nom_opt"]
            ).sum() / total_weight
            print(f"\n  Weighted-avg capital cost (by e_nom_opt): {wavg_cost:.2f} €/tCO2")

        flow_weighted_bus_price(n_opt, affo_stores, wavg_cost=wavg_cost)

    if affo_links.empty and affo_stores.empty:
        print(f"\n{WARN}  No afforestation components in optimal network!")

    mu_ext_e_nom_upper_check(affo_stores, "afforestation")
    return n_opt


# ── Biochar ──────────────────────────────────────────────────────────────────────

def check_biochar_build():
    section("BIOCHAR 1. BUILD: biochar available land")
    biochar_csv = RES_RUN / f"biochar_available_land_s_{CLUSTERS}.csv"
    csv_ok = check_file(biochar_csv, f"Biochar available land CSV  s_{CLUSTERS}")
    if csv_ok:
        df = pd.read_csv(biochar_csv)
        print(f"        Rows: {len(df)}  |  Columns: {list(df.columns)}")
        if "potential [sqkm]" in df.columns:
            total = df["potential [sqkm]"].sum()
            print(f"        Total potential area: {total:,.0f} km²")
        if df.isnull().any().any():
            print(f"{WARN}  NaN values detected in biochar potentials CSV.")


def check_biochar_prenet(n):
    section("BIOCHAR: pre-network components")
    biochar_carriers = [c for c in n.carriers.index if "biochar" in c.lower()]
    print(f"\n  Carriers with 'biochar': {biochar_carriers}")
    if "co2 biochar" in n.carriers.index:
        co2_em = n.carriers.at["co2 biochar", "co2_emissions"]
        print(f"    co2 biochar co2_emissions = {co2_em}  (expected 0.0 — sequestration via network flow)")
        if abs(co2_em) > 1e-6:
            print(f"{WARN}  co2_emissions != 0.0 — check add_biochar()!")

    co2_bc_links = n.links[n.links.carrier == "co2 biochar"]
    print(f"\n  Links (carrier == 'co2 biochar'): {len(co2_bc_links)}")

    co2_bc_stores = n.stores[n.stores.carrier == "co2 biochar"]
    print(f"\n  Stores (carrier == 'co2 biochar'): {len(co2_bc_stores)}")
    if not co2_bc_stores.empty and "e_nom_max" in co2_bc_stores.columns:
        finite = co2_bc_stores["e_nom_max"][co2_bc_stores["e_nom_max"] < 1e18]
        total_max = finite.sum()
        print(f"    Total e_nom_max (max potential): {total_max:,.0f} tCO2  ({total_max / 1e6:.3f} MtCO2)")

    if not biochar_carriers:
        print(f"\n{WARN}  No biochar carriers found — add_biochar may NOT have run!")
    elif co2_bc_links.empty or co2_bc_stores.empty:
        print(f"\n{WARN}  Missing co2 biochar links or stores — check add_biochar() execution!")
    else:
        print(f"\n{OK}  Biochar components present in pre-network.")


def check_biochar_optimal(n_opt):
    section("BIOCHAR: optimal solution")
    co2_bc_links  = n_opt.links[n_opt.links.carrier == "co2 biochar"]
    co2_bc_stores = n_opt.stores[n_opt.stores.carrier == "co2 biochar"]

    print(f"\n  Links (carrier == 'co2 biochar'): {len(co2_bc_links)}")
    if not co2_bc_links.empty and "p_nom_opt" in co2_bc_links.columns:
        active = co2_bc_links[co2_bc_links["p_nom_opt"] > 0]
        total_link = co2_bc_links["p_nom_opt"].sum()
        print(f"  Links with p_nom_opt > 0: {len(active)}")
        print(f"  Total p_nom_opt: {total_link:,.2f} MW")
        if active.empty:
            print(f"{WARN}  All co2 biochar links have p_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  co2 biochar links deployed in optimal solution.")

    print(f"\n  Stores (carrier == 'co2 biochar'): {len(co2_bc_stores)}")
    total = None
    if not co2_bc_stores.empty and "e_nom_opt" in co2_bc_stores.columns:
        active = co2_bc_stores[co2_bc_stores["e_nom_opt"] > 0]
        total = co2_bc_stores["e_nom_opt"].sum()
        print(f"  Stores with e_nom_opt > 0: {len(active)}")
        print(f"  Total e_nom_opt: {total:,.0f} tCO2  ({total/1e6:.3f} MtCO2)")
        if active.empty:
            print(f"{WARN}  All co2 biochar stores have e_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  Biochar stores deployed.")

    # capital_cost lives on the "<node> biochar" link and is a single global
    # constant from technology-data (not node-varying), so a "weighted
    # average by p_nom_opt" of it is meaningless -- the flow-weighted bus
    # price below is the only meaningful per-tCO2 cost figure for this tech.
    flow_weighted_bus_price(n_opt, co2_bc_stores)

    if co2_bc_links.empty and co2_bc_stores.empty:
        print(f"\n{WARN}  No co2 biochar components in optimal network!")

    mu_ext_e_nom_upper_check(co2_bc_stores, "biochar")


# ── Perennials ───────────────────────────────────────────────────────────────────

def check_perennials_build():
    section("PERENNIALS 1. RETRIEVE: eurostat crops + perennial yields")
    check_file(SHARED_RES / "eurostat_apro_cpshr_nuts2_raw.csv", "Eurostat NUTS2 crops")
    check_file(SHARED_RES / "eurostat_apro_cpshr_nuts0_raw.csv", "Eurostat NUTS0 crops")
    check_file(SHARED_RES / "perennials_yields_1G_biofuels.csv", "Perennials yields (all NUTS)")

    section("PERENNIALS 2. BUILD: perennial potentials (clustered)")
    yields_clustered = SHARED_RES / f"perennials_yields_1G_biofuels_s_{CLUSTERS}.csv"
    if check_file(yields_clustered, f"Perennials yields clustered s_{CLUSTERS}"):
        df = pd.read_csv(yields_clustered)
        print(f"        Rows: {len(df)}  |  Columns: {list(df.columns)}")
        if "perennials" in df.columns:
            print(f"        perennials [tDM/ha] — min: {df['perennials'].min():.2f}, "
                  f"mean: {df['perennials'].mean():.2f}, max: {df['perennials'].max():.2f}")
        else:
            print(f"        {WARN} no 'perennials' column found!")
        biofuels_1G_cols = [c for c in df.columns if "biofuels_1G" in c]
        if not biofuels_1G_cols:
            print(f"        {WARN} No 'biofuels_1G_*' columns found — biomass.classes in config.default.yaml")
            print(f"        {WARN} must use biofuels_1G_* names, NOT 'not included', for perennials to work!")


def check_perennials_prenet(n):
    section("PERENNIALS: pre-network components")
    perenn_carriers = [c for c in n.carriers.index if "perennial" in c.lower()]
    print(f"\n  Carriers with 'perennial': {perenn_carriers}")

    perenn_links = n.links[n.links.carrier.str.contains("perennial", case=False, na=False)]
    print(f"  Links (carrier=perennial): {len(perenn_links)}")

    perenn_stores = n.stores[n.stores.carrier.str.contains("perennial", case=False, na=False)]
    print(f"  Stores (carrier=perennial store): {len(perenn_stores)}")
    if not perenn_stores.empty and "e_nom_max" in perenn_stores.columns:
        finite_max = perenn_stores["e_nom_max"][perenn_stores["e_nom_max"] < 1e18]
        total_cap = finite_max.sum()
        print(f"\n  Total store capacity (e_nom_max): {total_cap:,.0f} tCO2  ({total_cap/1e6:.3f} MtCO2)")
        if total_cap == 0:
            print(f"  {WARN} ALL stores have e_nom_max=0!")
            print(f"  {WARN} This usually means biomass.classes in config.default.yaml")
            print(f"  {WARN} is missing biofuels_1G_* entries — check and re-run prepare_sector_network.")

    if not perenn_carriers:
        print(f"\n{WARN}  No perennial carriers found — add_perennials may NOT have run!")
    else:
        print(f"\n{OK}  Perennial components found in pre-network.")


def check_perennials_optimal(n_opt):
    section("PERENNIALS: optimal solution")
    perenn_links  = n_opt.links[n_opt.links.carrier.str.contains("perennial", case=False, na=False)]
    perenn_stores = n_opt.stores[n_opt.stores.carrier.str.contains("perennial", case=False, na=False)]

    print(f"\n  Links (carrier=perennial): {len(perenn_links)}")
    if not perenn_links.empty and "p_nom_opt" in perenn_links.columns:
        active = perenn_links[perenn_links["p_nom_opt"] > 0]
        print(f"  Links with p_nom_opt > 0: {len(active)}")
        if active.empty:
            print(f"{WARN}  Perennial links exist but have zero optimal capacity.")
        else:
            print(f"{OK}  Perennial links are deployed in the optimal solution.")

    print(f"\n  Stores (carrier=perennial store): {len(perenn_stores)}")
    store_total = 0.0
    if not perenn_stores.empty and "e_nom_opt" in perenn_stores.columns:
        active = perenn_stores[perenn_stores["e_nom_opt"] > 0]
        store_total = perenn_stores["e_nom_opt"].sum()
        print(f"\n  Stores with e_nom_opt > 0: {len(active)}")
        print(f"  Total e_nom_opt: {store_total:,.0f} tCO2  ({store_total / 1e6:.3f} MtCO2)")
        if active.empty:
            print(f"{WARN}  All perennial stores have e_nom_opt = 0 (not deployed).")

    # capital_cost lives on the "<node> perennials GBR" link and is a single
    # global constant from technology-data (not node-varying), so a
    # "weighted average by p_nom_opt" of it is meaningless -- the
    # flow-weighted bus price below is the only meaningful per-tCO2 cost
    # figure for this tech.
    flow_weighted_bus_price(n_opt, perenn_stores)

    if perenn_links.empty and perenn_stores.empty:
        print(f"\n{WARN}  No perennial components in optimal network!")

    mu_ext_e_nom_upper_check(perenn_stores, "perennials")


# ── Rock weathering ──────────────────────────────────────────────────────────────

def check_rock_weathering_build():
    section("ROCK WEATHERING 1. BUILD: available land (CORINE + mean-temperature exclusion)")
    rw_csv = RES_RUN / f"rock_weathering_available_land_s_{CLUSTERS}.csv"
    rw_ok = check_file(rw_csv, f"Rock weathering available land CSV  s_{CLUSTERS}")
    if rw_ok:
        df_rw = pd.read_csv(rw_csv, index_col=0)
        print(f"        Rows: {len(df_rw)}  |  Columns: {list(df_rw.columns)}")
        if "potential [sqkm]" in df_rw.columns:
            removal_per_sqkm = CFG.get("rock_weathering", {}).get("co2_removal_per_sqkm")
            total_sqkm = df_rw["potential [sqkm]"].sum()
            print(f"        Total rock weathering available land: {total_sqkm:,.0f} km²")
            if removal_per_sqkm:
                total_Mt = total_sqkm * removal_per_sqkm / 1e6
                print(f"        Total rock weathering potential: {total_Mt:.2f} Mt CO2  "
                      f"(at {removal_per_sqkm} t CO2/km²)")
        if df_rw.isnull().any().any():
            print(f"{WARN}  NaN values detected in rock weathering available land CSV.")
    return rw_ok, (df_rw if rw_ok else None)


def check_rock_weathering_prenet(n, rw_ok, df_rw):
    section("ROCK WEATHERING: pre-network components")
    rw_carriers = [c for c in n.carriers.index if "rock weathering" in c.lower()]
    print(f"\n  Carriers with 'rock weathering': {rw_carriers}")

    co2_rw_links = n.links[n.links.carrier == "co2 rock weathering"]
    print(f"\n  Links (carrier == 'co2 rock weathering'): {len(co2_rw_links)}")
    if not co2_rw_links.empty and "p_nom_extendable" in co2_rw_links.columns:
        if not co2_rw_links["p_nom_extendable"].all():
            print(f"    {WARN}  Some rock weathering links are NOT extendable — check add_rock_weathering()!")

    co2_rw_stores = n.stores[n.stores.carrier == "co2 rock weathering"]
    print(f"\n  Stores (carrier == 'co2 rock weathering'): {len(co2_rw_stores)}")
    if not co2_rw_stores.empty and "e_nom_max" in co2_rw_stores.columns:
        finite_max = co2_rw_stores["e_nom_max"][co2_rw_stores["e_nom_max"] < 1e18]
        total_enoms = finite_max.sum()
        print(f"    Total e_nom_max: {total_enoms:,.0f} t CO2  ({total_enoms/1e6:.2f} Mt CO2)")
        if rw_ok and df_rw is not None and "potential [t]" in df_rw.columns:
            expected_total = df_rw["potential [t]"].sum() * 0.2  # default max_land_usage=0.2
            if abs(total_enoms - expected_total) / max(expected_total, 1) > 0.01:
                print(f"    {WARN}  e_nom_max total ({total_enoms:,.0f} t) differs from "
                      f"expected ({expected_total:,.0f} t, assuming max_land_usage=0.2)")

    if not rw_carriers:
        print(f"\n{WARN}  No rock weathering carriers found — add_rock_weathering may NOT have run!")
    elif co2_rw_links.empty or co2_rw_stores.empty:
        print(f"\n{WARN}  Missing co2 rock weathering links or stores — check add_rock_weathering() execution!")
    else:
        print(f"\n{OK}  Rock weathering components present in pre-network.")


def check_rock_weathering_optimal(n_opt):
    section("ROCK WEATHERING: optimal solution")
    co2_rw_links  = n_opt.links [n_opt.links .carrier == "co2 rock weathering"]
    co2_rw_stores = n_opt.stores[n_opt.stores.carrier == "co2 rock weathering"]

    print(f"\n  Links (carrier == 'co2 rock weathering'): {len(co2_rw_links)}")
    if not co2_rw_links.empty and "p_nom_opt" in co2_rw_links.columns:
        active = co2_rw_links[co2_rw_links["p_nom_opt"] > 0]
        print(f"  Links with p_nom_opt > 0: {len(active)}")
        if active.empty:
            print(f"{WARN}  All co2 rock weathering links have p_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  Rock weathering links deployed in optimal solution.")

    print(f"\n  Stores (carrier == 'co2 rock weathering'): {len(co2_rw_stores)}")
    total_stored = None
    total_max = 0.0
    if not co2_rw_stores.empty:
        if "e_nom_max" in co2_rw_stores.columns:
            finite_max = co2_rw_stores["e_nom_max"][co2_rw_stores["e_nom_max"] < 1e18]
            total_max = finite_max.sum()
            print(f"  Total e_nom_max (available potential): {total_max:,.0f} t CO2  "
                  f"({total_max/1e6:.3f} Mt CO2)")
        if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
            rw_store_e = n_opt.stores_t["e"][co2_rw_stores.index]
            if not rw_store_e.empty:
                final_e = rw_store_e.iloc[-1]
                total_stored = final_e.sum()
                print(f"  CO2 stored at end of horizon: {total_stored:,.0f} t CO2  "
                      f"({total_stored/1e6:.3f} Mt CO2)")
                if total_max > 0:
                    utilisation = total_stored / total_max * 100
                    print(f"  Potential utilisation (stored / e_nom_max): {utilisation:.1f}%")
                if total_stored == 0:
                    print(f"{WARN}  No CO2 sequestered — rock weathering not utilised in solution.")
                else:
                    print(f"{OK}  Rock weathering CO2 sequestration active in optimal solution.")

    # add_rock_weathering() sets no capital_cost anywhere and marginal_cost
    # (VOM) is a single global constant from technology-data (not
    # node-varying), so a "weighted average by p_nom_opt" of it is
    # meaningless -- the flow-weighted bus price below is the only
    # meaningful per-tCO2 cost figure for this tech.
    flow_weighted_bus_price(n_opt, co2_rw_stores)

    if co2_rw_links.empty and co2_rw_stores.empty:
        print(f"\n{WARN}  No co2 rock weathering components in optimal network!")

    mu_ext_e_nom_upper_check(co2_rw_stores, "rock weathering")


# ── Main ──────────────────────────────────────────────────────────────────────────

active_names = [name for name, on in ACTIVE.items() if on]
header("ACTIVE CDR TECHNOLOGIES")
for name, on in ACTIVE.items():
    print(f"  {OK if on else '  [off]'}  {name}")
if not active_names:
    print(f"\n{WARN}  No CDR technology is enabled in this run's config "
          f"(sector.afforestation / sector.biochar.enable / "
          f"sector.perennials / sector.rock_weathering all false).")

# --- Build-stage checks (tech-specific files) ---
header("BUILD-STAGE CHECKS")
_rw_ok, _df_rw = False, None
if ACTIVE["afforestation"]:
    check_afforestation_build()
if ACTIVE["biochar"]:
    check_biochar_build()
if ACTIVE["perennials"]:
    check_perennials_build()
if ACTIVE["rock_weathering"]:
    _rw_ok, _df_rw = check_rock_weathering_build()

# --- Pre-network (shared single load for all active techs) ---
header("PRE-NETWORK: sector-coupled (prepare_sector_network)")
prenet_path = SHARED_RES / "networks" / f"{WC}.nc"
prenet_ok = check_file(prenet_path, f"Pre-network  {WC}.nc")
if prenet_ok:
    try:
        n = pypsa.Network(str(prenet_path))
        if ACTIVE["afforestation"]:
            check_afforestation_prenet(n)
        if ACTIVE["biochar"]:
            check_biochar_prenet(n)
        if ACTIVE["perennials"]:
            check_perennials_prenet(n)
        if ACTIVE["rock_weathering"]:
            check_rock_weathering_prenet(n, _rw_ok, _df_rw)
    except Exception as e:
        print(f"\n{WARN}  Could not load pre-network: {e}")
else:
    print(f"\n{FAIL}  Pre-network missing — prepare_sector_network has not run yet.")

# --- Optimal solution (shared single load for all active techs) ---
header("OPTIMAL SOLUTION: solved network (solve_sector_network)")
opt_path = RESULTS / "networks" / f"{WC}.nc"
opt_ok = check_file(opt_path, f"Optimal network  {WC}.nc")
if opt_ok:
    try:
        n_opt = pypsa.Network(str(opt_path))
        if ACTIVE["afforestation"]:
            check_afforestation_optimal(n_opt)
        if ACTIVE["biochar"]:
            check_biochar_optimal(n_opt)
        if ACTIVE["perennials"]:
            check_perennials_optimal(n_opt)
        if ACTIVE["rock_weathering"]:
            check_rock_weathering_optimal(n_opt)

        print_co2_system_diagnostics(n_opt, OK=OK, WARN=WARN)
    except Exception as e:
        print(f"\n{WARN}  Could not load optimal network: {e}")
else:
    print(f"\n{FAIL}  Optimal network missing — solve_sector_network has not run yet.")

# ── Summary ───────────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  Run:            {RDIR}")
print(f"  Wildcard:       {WC}")
print(f"  Active CDRs:    {', '.join(active_names) if active_names else '(none)'}")
print(f"  Resources dir:  {RES_RUN.resolve()}")
print(f"  Results dir:    {RESULTS.resolve()}")
print()
print(f"  Passed: {len(passed)}")
print(f"  Failed: {len(failed)}")
if failed:
    print(f"\n  Missing files:")
    for f in failed:
        print(f"    - {f}")
