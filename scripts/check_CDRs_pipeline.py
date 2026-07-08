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

import sys
from pathlib import Path

# Ensure sibling modules in scripts/ are importable regardless of CWD
sys.path.insert(0, str(Path(__file__).parent))

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

# CSV export: every numeric result recorded alongside its print statement,
# written out as results/<run_name>/csvs/check_CDRs_pipeline_<WC>.csv at the
# end of the run (see bottom of this script).
CSV_ROWS = []


def record(technology: str, metric: str, value, unit: str = ""):
    CSV_ROWS.append({
        "technology": technology,
        "metric": metric,
        "value": value,
        "unit": unit,
    })


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
    """Shadow price of the land-potential constraint μ(e_nom_max) for CDR stores.

    Dual of "Store-ext-e_nom-upper" (e_nom_opt ≤ e_nom_max): the marginal
    improvement in the objective from relaxing the potential by 1 tCO2.
    Negative = beneficial (relaxing costs → cheaper system).
    Written to n.stores["mu_ext_e_nom_upper"] only when
    solving.options.assign_capacity_duals: true.
    """
    print(f"\n  ── Shadow price of CDR potential  μ(e_nom_max) {'─'*36}")
    if not _assign_capacity_duals:
        print(f"     assign_capacity_duals: disabled"
              f"  (set solving.options.assign_capacity_duals: true and re-run)")
        return
    print(f"     assign_capacity_duals: enabled")
    if "mu_ext_e_nom_upper" not in stores.columns:
        print(f"     {WARN}  column not found in stores — was assign_capacity_duals: true when solving?")
        return

    mu = stores["mu_ext_e_nom_upper"].dropna()
    if mu.empty:
        return
    binding = mu[mu.abs() > 1e-6]
    print(f"     binding: {len(binding)}/{len(mu)} nodes")

    w = stores["e_nom_opt"].reindex(mu.index).fillna(0.0) if "e_nom_opt" in stores.columns else pd.Series(1.0, index=mu.index)
    w_total = w.sum()
    wavg = (mu * w).sum() / w_total if w_total > 0 else float("nan")
    print(f"     e_nom_opt-weighted mean:  {wavg:+.2f}  €/tCO2")
    print(f"     unweighted  mean ± std:   {mu.mean():+.2f} ± {mu.std():.2f}  €/tCO2"
          f"    [min: {mu.min():+.2f}  max: {mu.max():+.2f}]")

    record(label, "mu_ext_e_nom_upper_weighted_mean", wavg, "EUR/tCO2")
    record(label, "mu_ext_e_nom_upper_unweighted_mean", mu.mean(), "EUR/tCO2")
    record(label, "mu_ext_e_nom_upper_binding_nodes", len(binding), "count")


def flow_weighted_bus_price(n_opt, stores, label: str = ""):
    """Marginal price at the CDR store bus, flow-time-weighted per node then
    CO2-flow-weighted across nodes.

    Flow is read off the store directly (stores_t.p, sign-flipped: charging
    p<0 → positive inflow). Per-node price = time-weighted mean marginal price
    at that node's CDR store bus, weighted by inflow × snapshot weight.
    Across nodes: weighted by each node's actual CO2 flow (not by potential —
    for non-extendable stores e_nom_opt is just an alias for the fixed e_nom,
    so it would weight unused-potential nodes the same as fully-used ones).
    """
    mp = n_opt.buses_t.marginal_price if "marginal_price" in n_opt.buses_t else None
    if mp is None or mp.empty or stores.empty:
        print(f"\n{WARN}  buses_t.marginal_price unavailable or empty — "
              f"check the network was solved with a solver returning duals.")
        return

    weighting = n_opt.snapshot_weightings["stores"]
    store_flow = -n_opt.stores_t.p[stores.index]

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
    node_weight = pd.Series(node_flow_total).reindex(node_price.index).fillna(0.0)
    total_weight = node_weight.sum()
    if total_weight <= 0:
        return

    flow_wavg_price = (node_price * node_weight).sum() / total_weight
    total_flow = sum(node_flow_total.values())

    potential_col = "e_nom_max" if "e_nom_max" in stores.columns else "e_nom"
    total_potential = None
    if potential_col in stores.columns:
        potential = stores[potential_col]
        total_potential = potential[potential < 1e18].sum()

    print(f"\n  ── Marginal price at CDR store bus {'─'*46}")
    if total_potential:
        print(f"     n={len(node_price)} nodes  |  total CO2 flow: {total_flow:,.0f} tCO2"
              f"  |  flow/potential: {total_flow / total_potential:.4f}")
    else:
        print(f"     n={len(node_price)} nodes  |  total CO2 flow: {total_flow:,.0f} tCO2")
    print(f"     CO2-flow-weighted mean:   {flow_wavg_price:+.2f}  €/tCO2")
    print(f"     unweighted  mean ± std:   {node_price.mean():+.2f} ± {node_price.std():.2f}  €/tCO2"
          f"    [min: {node_price.min():+.2f}  max: {node_price.max():+.2f}]")

    if label:
        record(label, "store_bus_price_flow_weighted_mean", flow_wavg_price, "EUR/tCO2")
        record(label, "store_bus_price_unweighted_mean", node_price.mean(), "EUR/tCO2")
        record(label, "total_co2_flow", total_flow, "tCO2")


def print_lccdr(n_opt, links, stores, cdr_store_carrier: str, label: str):
    """Levelized Cost of CDR (LCCDR) — unified for all four CDR technologies.

    Picks up capital cost from BOTH the store (afforestation: real cost ~83 €/tCO2)
    and the link (biochar/perennials/RW: pyrolysis / weathering capex). Indexed on
    the store (one per spatial node).

    Per-node breakdown:
      Capex        = link.capital_cost × p_nom_opt  +  store.capital_cost × e_nom
      VOM          = link.marginal_cost × Σ(p0 × sw)
      Net CDR cost = Σ_buses_≠_CDR_store  price_bus × p_i_stored × sw
                     (CO2 atm credit − energy inputs + co-products)
      CO2 seq      = Σ(−store_p × sw)
      LCCDR_node   = (Capex + VOM + Net CDR cost) / CO2 seq

    From KKT: LCCDR ≈ marginal price at CDR store bus ≈ μ(e_nom_max).
    """
    mp = getattr(n_opt.buses_t, "marginal_price", None)
    if mp is None or mp.empty:
        print(f"\n{WARN}  buses_t.marginal_price unavailable — cannot compute LCCDR")
        return
    if stores.empty:
        return

    sw    = n_opt.snapshot_weightings["stores"]
    p0_df = getattr(n_opt.links_t, "p0", None)

    # CDR store bus → link name (link that feeds the store at that bus)
    store_bus_to_link: dict = {}
    for link_name, link in links.iterrows():
        for i in range(5):
            bus_col = f"bus{i}"
            if bus_col not in links.columns:
                continue
            bus = link.get(bus_col)
            if not isinstance(bus, str) or not bus:
                continue
            if bus not in n_opt.buses.index:
                continue
            if n_opt.buses.at[bus, "carrier"] == cdr_store_carrier:
                store_bus_to_link[bus] = link_name

    tot_capex = tot_vom = tot_co2atm = tot_bus_other = tot_co2 = 0.0
    node_lccdr:       dict = {}
    node_gross_lccdr: dict = {}
    node_co2:         dict = {}

    for store_name, store in stores.iterrows():
        store_bus = store["bus"]
        link_name = store_bus_to_link.get(store_bus)

        if store_name not in n_opt.stores_t.p.columns:
            continue
        co2_n = (-n_opt.stores_t.p[store_name] * sw).sum()
        if co2_n <= 0:
            continue

        capex_n      = store.get("capital_cost", 0.0) * store.get("e_nom", store.get("e_nom_opt", 0.0))
        vom_n        = 0.0
        bus_co2atm_n = 0.0
        bus_other_n  = 0.0

        if link_name is not None:
            link = links.loc[link_name]
            capex_n += link.get("capital_cost", 0.0) * link.get("p_nom_opt", 0.0)

            if p0_df is not None and link_name in p0_df.columns:
                p0_t = p0_df[link_name]
                vom_n = (link.get("marginal_cost", 0.0) * p0_t * sw).sum()

                for i in range(5):
                    bus_col = f"bus{i}"
                    if bus_col not in links.columns:
                        continue
                    bus_name = link.get(bus_col)
                    if not isinstance(bus_name, str) or not bus_name:
                        continue
                    if bus_name not in n_opt.buses.index:
                        continue
                    bus_carrier = n_opt.buses.at[bus_name, "carrier"]
                    if bus_carrier == cdr_store_carrier:
                        continue  # skip CDR store bus
                    if bus_name not in mp.columns:
                        continue
                    price_t = mp[bus_name]
                    if i == 0:
                        p_i_t = p0_t
                    else:
                        p_i_df = getattr(n_opt.links_t, f"p{i}", None)
                        if p_i_df is not None and link_name in p_i_df.columns:
                            p_i_t = p_i_df[link_name]
                        else:
                            eff_col = "efficiency" if i == 1 else f"efficiency{i}"
                            if eff_col not in links.columns:
                                continue
                            eff = link.get(eff_col, 0.0)
                            if eff == 0.0:
                                continue
                            p_i_t = -eff * p0_t
                    # PyPSA: p_i = -eff_i × p0, positive = consuming from bus_i
                    contrib = (price_t * p_i_t * sw).sum()
                    if bus_carrier == "co2":  # CO2 atmosphere bus
                        bus_co2atm_n += contrib
                    else:
                        bus_other_n += contrib

        gross_n = capex_n + vom_n + bus_other_n
        bus_n   = bus_co2atm_n + bus_other_n
        tot_capex      += capex_n
        tot_vom        += vom_n
        tot_co2atm     += bus_co2atm_n
        tot_bus_other  += bus_other_n
        tot_co2        += co2_n
        node_lccdr[store_name]       = (gross_n + bus_co2atm_n) / co2_n  # CDR net revenue
        node_gross_lccdr[store_name] = gross_n / co2_n                   # LCCDR (cost only)
        node_co2[store_name]         = co2_n

    if tot_co2 <= 0:
        print(f"\n{WARN}  No CO2 flow — cannot compute LCCDR")
        return

    tot_gross        = tot_capex + tot_vom + tot_bus_other
    tot_net_revenue  = tot_gross + tot_co2atm
    node_lccdr_s     = pd.Series(node_lccdr)
    node_gross_s     = pd.Series(node_gross_lccdr)
    node_w           = pd.Series(node_co2).reindex(node_lccdr_s.index).fillna(0.0)
    w_total          = node_w.sum()
    wavg             = lambda s: (s * node_w).sum() / w_total if w_total > 0 else s.mean()

    print(f"\n  ── Levelized Cost of CDR  (LCCDR) {'─'*46}")
    print(f"     Cost breakdown (pooled, {len(node_lccdr)} nodes):")
    print(f"       Capex (link + store):        {tot_capex     / tot_co2:+.2f}  €/tCO2")
    print(f"       VOM:                         {tot_vom        / tot_co2:+.2f}  €/tCO2")
    print(f"       Other variable costs:        {tot_bus_other  / tot_co2:+.2f}  €/tCO2"
          f"   (energy inputs − co-products)")
    print(f"       {'─'*54}")
    print(f"       Levelized Cost of CDR:       {tot_gross      / tot_co2:+.2f}  €/tCO2"
          f"   (cost to remove 1 tCO2, excl. CO2 value)")
    print(f"     + CO2 credit:                  {tot_co2atm     / tot_co2:+.2f}  €/tCO2"
          f"   (CO2 atm price × CO2 flow)")
    print(f"       {'─'*54}")
    print(f"     = CDR net revenue:             {tot_net_revenue / tot_co2:+.2f}  €/tCO2")
    print(f"     Per-node distribution ({len(node_lccdr)} nodes):")
    print(f"       Levelized Cost of CDR  —  CO2-flow-weighted mean:  {wavg(node_gross_s):+.2f}  €/tCO2")
    print(f"                                 unweighted  mean ± std:   {node_gross_s.mean():+.2f} ± {node_gross_s.std():.2f}  €/tCO2"
          f"    [min: {node_gross_s.min():+.2f}  max: {node_gross_s.max():+.2f}]")
    print(f"       CDR net revenue        —  CO2-flow-weighted mean:  {wavg(node_lccdr_s):+.2f}  €/tCO2")
    print(f"                                 unweighted  mean ± std:   {node_lccdr_s.mean():+.2f} ± {node_lccdr_s.std():.2f}  €/tCO2"
          f"    [min: {node_lccdr_s.min():+.2f}  max: {node_lccdr_s.max():+.2f}]")

    record(label, "lccdr_capex", tot_capex / tot_co2, "EUR/tCO2")
    record(label, "lccdr_vom", tot_vom / tot_co2, "EUR/tCO2")
    record(label, "lccdr_other_variable_costs", tot_bus_other / tot_co2, "EUR/tCO2")
    record(label, "lccdr_gross", tot_gross / tot_co2, "EUR/tCO2")
    record(label, "lccdr_co2_credit", tot_co2atm / tot_co2, "EUR/tCO2")
    record(label, "lccdr_net_revenue", tot_net_revenue / tot_co2, "EUR/tCO2")
    record(label, "lccdr_gross_flow_weighted_mean", wavg(node_gross_s), "EUR/tCO2")
    record(label, "lccdr_net_revenue_flow_weighted_mean", wavg(node_lccdr_s), "EUR/tCO2")
    record(label, "lccdr_total_co2_flow", tot_co2, "tCO2")


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
            record("afforestation", "available_land_area", total_area, "km2")
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
            record("afforestation", "gross_potential_pre_crcf", total_gross_potential, "tCO2/y")
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
        record("afforestation", "prenet_e_nom_max_net_post_crcf", finite_max.sum(), "tCO2")

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
        record("afforestation", "link_p_nom_opt", total_p_nom_opt, "MW")
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
        record("afforestation", "deployed_e_nom_opt", total_e_nom_opt, "tCO2/yr")
        if active_stores.empty:
            print(f"{WARN}  All afforestation stores have e_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  Afforestation stores deployed.")

        if "e_nom_max" in affo_stores.columns:
            finite_max = affo_stores["e_nom_max"][affo_stores["e_nom_max"] < 1e18]
            total_e_nom_max = finite_max.sum()
            print(f"\n  Total e_nom_max (available potential): "
                  f"{total_e_nom_max:,.0f} tCO2  ({total_e_nom_max/1e6:.3f} MtCO2/yr)")
            record("afforestation", "optimal_potential_e_nom_max", total_e_nom_max, "tCO2/yr")
            if total_e_nom_max > 0:
                utilisation = total_e_nom_opt / total_e_nom_max * 100
                print(f"  Potential utilisation (e_nom_opt / e_nom_max): {utilisation:.1f}%")
                record("afforestation", "potential_utilisation", utilisation, "%")

    flow_weighted_bus_price(n_opt, affo_stores, "afforestation")
    print_lccdr(n_opt, affo_links, affo_stores, "co2 afforestation", "afforestation")

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
            record("biochar", "available_land_area", total, "km2")
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
    if not co2_bc_stores.empty and "e_nom" in co2_bc_stores.columns:
        total_max = co2_bc_stores["e_nom"].sum()
        print(f"    Total e_nom (fixed potential): {total_max:,.0f} tCO2  ({total_max / 1e6:.3f} MtCO2)")
        record("biochar", "prenet_e_nom_potential", total_max, "tCO2")

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
        record("biochar", "link_p_nom_opt", total_link, "MW")
        if active.empty:
            print(f"{WARN}  All co2 biochar links have p_nom_opt = 0 (not deployed).")
        else:
            print(f"{OK}  co2 biochar links deployed in optimal solution.")

    print(f"\n  Stores (carrier == 'co2 biochar'): {len(co2_bc_stores)}")
    total_stored = None
    total_cap = 0.0
    if not co2_bc_stores.empty:
        if "e_nom" in co2_bc_stores.columns:
            total_cap = co2_bc_stores["e_nom"].sum()
            print(f"  Total e_nom (fixed potential): {total_cap:,.0f} tCO2  ({total_cap/1e6:.3f} MtCO2)")
            record("biochar", "optimal_potential_e_nom", total_cap, "tCO2")
        # Stores are non-extendable (e_nom fixed = potential); e_nom_opt is
        # just an alias for e_nom and would always read as "fully deployed"
        # regardless of actual usage, so read the state of charge instead.
        if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
            bc_store_e = n_opt.stores_t["e"][co2_bc_stores.index]
            if not bc_store_e.empty:
                final_e = bc_store_e.iloc[-1]
                total_stored = final_e.sum()
                print(f"  CO2 stored at end of horizon: {total_stored:,.0f} tCO2  "
                      f"({total_stored/1e6:.3f} MtCO2)")
                record("biochar", "deployed_stored_at_horizon_end", total_stored, "tCO2")
                if total_cap > 0:
                    utilisation = total_stored / total_cap * 100
                    print(f"  Potential utilisation (stored / e_nom): {utilisation:.1f}%")
                    record("biochar", "potential_utilisation", utilisation, "%")
                if total_stored == 0:
                    print(f"{WARN}  No CO2 sequestered — biochar not utilised in solution.")
                else:
                    print(f"{OK}  Biochar stores deployed.")

    # capital_cost lives on the "<node> biochar" link and is a single global
    # constant from technology-data (not node-varying), so a "weighted
    # average by p_nom_opt" of it is meaningless -- the flow-weighted bus
    # price below is the only meaningful per-tCO2 cost figure for this tech.
    flow_weighted_bus_price(n_opt, co2_bc_stores, "biochar")
    print_lccdr(n_opt, co2_bc_links, co2_bc_stores, "co2 biochar", "biochar")

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
            record("perennials", "yield_mean", df["perennials"].mean(), "tDM/ha")
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
    if not perenn_stores.empty and "e_nom" in perenn_stores.columns:
        total_cap = perenn_stores["e_nom"].sum()
        print(f"\n  Total store capacity (e_nom, fixed potential): {total_cap:,.0f} tCO2  ({total_cap/1e6:.3f} MtCO2)")
        record("perennials", "prenet_e_nom_potential", total_cap, "tCO2")
        if total_cap == 0:
            print(f"  {WARN} ALL stores have e_nom=0!")
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
    total_stored = None
    total_cap = 0.0
    if not perenn_stores.empty:
        if "e_nom" in perenn_stores.columns:
            total_cap = perenn_stores["e_nom"].sum()
            print(f"\n  Total e_nom (fixed potential): {total_cap:,.0f} tCO2  ({total_cap / 1e6:.3f} MtCO2)")
            record("perennials", "optimal_potential_e_nom", total_cap, "tCO2")
        # Stores are non-extendable (e_nom fixed = potential); e_nom_opt is
        # just an alias for e_nom and would always read as "fully deployed"
        # regardless of actual usage, so read the state of charge instead.
        if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
            perenn_store_e = n_opt.stores_t["e"][perenn_stores.index]
            if not perenn_store_e.empty:
                final_e = perenn_store_e.iloc[-1]
                total_stored = final_e.sum()
                print(f"  CO2 stored at end of horizon: {total_stored:,.0f} tCO2  "
                      f"({total_stored/1e6:.3f} MtCO2)")
                record("perennials", "deployed_stored_at_horizon_end", total_stored, "tCO2")
                if total_cap > 0:
                    utilisation = total_stored / total_cap * 100
                    print(f"  Potential utilisation (stored / e_nom): {utilisation:.1f}%")
                    record("perennials", "potential_utilisation", utilisation, "%")
                if total_stored == 0:
                    print(f"{WARN}  All perennial stores are empty (not deployed).")

    # capital_cost lives on the "<node> perennials GBR" link and is a single
    # global constant from technology-data (not node-varying), so a
    # "weighted average by p_nom_opt" of it is meaningless -- the
    # flow-weighted bus price below is the only meaningful per-tCO2 cost
    # figure for this tech.
    flow_weighted_bus_price(n_opt, perenn_stores, "perennials")
    print_lccdr(n_opt, perenn_links, perenn_stores, "co2 perennials", "perennials")

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
            record("rock_weathering", "available_land_area", total_sqkm, "km2")
            if removal_per_sqkm:
                total_Mt = total_sqkm * removal_per_sqkm / 1e6
                print(f"        Total rock weathering potential: {total_Mt:.2f} Mt CO2  "
                      f"(at {removal_per_sqkm} t CO2/km²)")
                record("rock_weathering", "gross_potential", total_Mt * 1e6, "tCO2")
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
    if not co2_rw_stores.empty and "e_nom" in co2_rw_stores.columns:
        total_enoms = co2_rw_stores["e_nom"].sum()
        print(f"    Total e_nom (fixed potential): {total_enoms:,.0f} t CO2  ({total_enoms/1e6:.2f} Mt CO2)")
        record("rock_weathering", "prenet_e_nom_potential", total_enoms, "tCO2")
        if rw_ok and df_rw is not None and "potential [t]" in df_rw.columns:
            expected_total = df_rw["potential [t]"].sum() * 0.2  # default max_land_usage=0.2
            if abs(total_enoms - expected_total) / max(expected_total, 1) > 0.01:
                print(f"    {WARN}  e_nom total ({total_enoms:,.0f} t) differs from "
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
        if "e_nom" in co2_rw_stores.columns:
            total_max = co2_rw_stores["e_nom"].sum()
            print(f"  Total e_nom (fixed potential): {total_max:,.0f} t CO2  "
                  f"({total_max/1e6:.3f} Mt CO2)")
            record("rock_weathering", "optimal_potential_e_nom", total_max, "tCO2")
        if hasattr(n_opt, "stores_t") and "e" in n_opt.stores_t:
            rw_store_e = n_opt.stores_t["e"][co2_rw_stores.index]
            if not rw_store_e.empty:
                final_e = rw_store_e.iloc[-1]
                total_stored = final_e.sum()
                print(f"  CO2 stored at end of horizon: {total_stored:,.0f} t CO2  "
                      f"({total_stored/1e6:.3f} Mt CO2)")
                record("rock_weathering", "deployed_stored_at_horizon_end", total_stored, "tCO2")
                if total_max > 0:
                    utilisation = total_stored / total_max * 100
                    print(f"  Potential utilisation (stored / e_nom): {utilisation:.1f}%")
                    record("rock_weathering", "potential_utilisation", utilisation, "%")
                if total_stored == 0:
                    print(f"{WARN}  No CO2 sequestered — rock weathering not utilised in solution.")
                else:
                    print(f"{OK}  Rock weathering CO2 sequestration active in optimal solution.")

    # add_rock_weathering() sets no capital_cost anywhere and marginal_cost
    # (VOM) is a single global constant from technology-data (not
    # node-varying), so a "weighted average by p_nom_opt" of it is
    # meaningless -- the flow-weighted bus price below is the only
    # meaningful per-tCO2 cost figure for this tech.
    flow_weighted_bus_price(n_opt, co2_rw_stores, "rock_weathering")
    print_lccdr(n_opt, co2_rw_links, co2_rw_stores, "co2 rock weathering", "rock_weathering")

    if co2_rw_links.empty and co2_rw_stores.empty:
        print(f"\n{WARN}  No co2 rock weathering components in optimal network!")

    mu_ext_e_nom_upper_check(co2_rw_stores, "rock_weathering")


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

        print_co2_system_diagnostics(n_opt, OK=OK, WARN=WARN, record_fn=record)
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

# ── CSV export ────────────────────────────────────────────────────────────────────
# A flat (technology, metric, value, unit) table of every numeric result
# printed above, for downstream analysis without re-parsing console output.
csv_dir = RESULTS / "csvs"
csv_dir.mkdir(parents=True, exist_ok=True)
csv_path = csv_dir / f"check_CDRs_pipeline_{WC}.csv"
pd.DataFrame(CSV_ROWS, columns=["technology", "metric", "value", "unit"]).to_csv(csv_path, index=False)
print(f"\n  CSV results saved: {csv_path.resolve()}  ({len(CSV_ROWS)} rows)")
