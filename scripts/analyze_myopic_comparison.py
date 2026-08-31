"""
Analyze a myopic run's solved horizon networks and produce three CSVs:
  - fossil_co2_by_carrier.csv : tCO2 by {oil, gas, coal} per year (supply-side,
    mirrors add_fossil_fuel_limit's own definition: fossil generator dispatch
    x CO2 intensity, no CCS credit), plus the actual CO2Limit constant per
    year, plus FossilLimit_tCO2 (the fossil_limit_values cap from
    config.default.yaml, read regardless of whether fossil_limit was
    actually enabled for this run).
  - total_fuel_mwh.csv : total fossil + total biomass (incl. unsustainable
    bioliquids) primary energy in MWh per year, plus CO2Limit, plus
    FossilLimit_MWh (the fossil cap converted to an implied energy volume
    using this run's own blended tCO2/MWh fuel mix for that year).
  - co2_balance_terms.csv : full co2-atmosphere-bus energy balance by
    carrier/term per year (tCO2), for the stacked term plot.

Usage: python3 analyze_run.py <networks_dir> <output_prefix>
"""
import sys
import glob
import os
import re
import pypsa
import pandas as pd
import yaml

FOSSIL_CO2_INTENSITY = {  # tCO2/MWh_th, read directly off this fork's combustion
    # Links (bus2/bus3 efficiency into the "co2 atmosphere" bus) rather than
    # assumed: gas=0.198, oil=0.2571, coal=0.3361, lignite=0.4069. These are
    # the technology-data physical CO2 content of each fuel and do not vary
    # by horizon.
    "gas": 0.198,
    "oil": 0.2571,
    "oil primary": 0.2571,
    "coal": 0.3361,
    "lignite": 0.4069,
}
FOSSIL_GROUP = {  # 3-way stack: oil / gas / coal (lignite folded into coal)
    "gas": "gas",
    "oil": "oil",
    "oil primary": "oil",
    "coal": "coal",
    "lignite": "coal",
}

BIOMASS_CARRIERS_HINT = [
    "solid biomass",
    "biogas",
    "unsustainable solid biomass",
    "unsustainable biogas",
    "unsustainable bioliquids",
]


def year_from_path(path):
    m = re.search(r"_(\d{4})\.nc$", path)
    return int(m.group(1))


def raw_carrier_mwh(n):
    """
    Single source of truth: injection-side Generator dispatch (MWh) per raw
    carrier name (not yet grouped), shared by both the fossil-CO2 plot and
    the total-fuel plot so they can never disagree with each other.

    Must weight by snapshot_weightings: at reduced temporal resolution (e.g.
    8h) each snapshot represents multiple real hours, so summing p directly
    undercounts annual MWh by exactly the resolution factor (8x for 8h).
    """
    w = n.snapshot_weightings["generators"]
    out = {}
    for carrier in FOSSIL_GROUP:
        idx = n.generators.index[n.generators.carrier == carrier]
        out[carrier] = (
            n.generators_t.p[idx].clip(lower=0).multiply(w, axis=0).sum().sum()
            if len(idx)
            else 0.0
        )
    for carrier in BIOMASS_CARRIERS_HINT:
        idx = n.generators.index[n.generators.carrier == carrier]
        out[carrier] = (
            n.generators_t.p[idx].clip(lower=0).multiply(w, axis=0).sum().sum()
            if len(idx)
            else 0.0
        )
    return out


def fuel_mwh_by_group(raw_mwh):
    """oil/gas/coal/biomass MWh, grouped from the raw per-carrier dict."""
    out = {"oil": 0.0, "gas": 0.0, "coal": 0.0, "biomass": 0.0}
    for carrier, group in FOSSIL_GROUP.items():
        out[group] += raw_mwh[carrier]
    for carrier in BIOMASS_CARRIERS_HINT:
        out["biomass"] += raw_mwh[carrier]
    return out


def fossil_co2_by_carrier(raw_mwh):
    """tCO2 per fossil group (oil/gas/coal), each carrier's own intensity
    applied before grouping (lignite != coal, oil primary == oil)."""
    out = {"oil": 0.0, "gas": 0.0, "coal": 0.0}
    for carrier, group in FOSSIL_GROUP.items():
        out[group] += raw_mwh[carrier] * FOSSIL_CO2_INTENSITY[carrier]
    return out


def fossil_limit_values_from_config():
    """
    Read the (possibly-disabled) fossil_limit_values {year: MtCO2} from
    config/config.default.yaml, regardless of whether fossil_limit was
    actually turned on for this run -- used to overlay the constraint's
    would-be bound on the plots even when it wasn't enforced.
    """
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config", "config.default.yaml"
    )
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    values = cfg.get("fossil_limit_values", {})
    return {int(year): mtco2 * 1e6 for year, mtco2 in values.items()}  # -> tCO2


def co2limit_constant(n):
    if "CO2Limit" in n.global_constraints.index:
        return n.global_constraints.loc["CO2Limit", "constant"]
    return None


def co2_balance_terms(n):
    try:
        eb = n.statistics.energy_balance(bus_carrier="co2", groupby=["carrier"])
    except Exception as e:
        print(f"  warning: energy_balance(bus_carrier='co2') failed: {e}")
        return pd.Series(dtype=float)
    # collapse the (component, carrier) MultiIndex to just carrier
    if isinstance(eb.index, pd.MultiIndex):
        eb = eb.groupby(level=-1).sum()
    return eb


def main():
    networks_dir, out_prefix = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(f"{networks_dir}/*.nc"), key=year_from_path)

    fossil_rows = {}
    fuel_rows = {}
    balance_rows = {}
    co2limit = {}

    for f in files:
        year = year_from_path(f)
        print(f"Loading {year} ...")
        n = pypsa.Network(f)

        raw_mwh = raw_carrier_mwh(n)
        fossil_rows[year] = fossil_co2_by_carrier(raw_mwh)
        fuel_rows[year] = fuel_mwh_by_group(raw_mwh)
        co2limit[year] = co2limit_constant(n)
        balance_rows[year] = co2_balance_terms(n)

    fossil_limit_tco2 = fossil_limit_values_from_config()

    fossil_df = pd.DataFrame(fossil_rows).T.sort_index()
    fossil_df["total"] = fossil_df[["oil", "gas", "coal"]].sum(axis=1)
    fossil_df["CO2Limit_tCO2"] = pd.Series(co2limit)
    fossil_df["FossilLimit_tCO2"] = pd.Series(fossil_limit_tco2).reindex(fossil_df.index)
    fossil_df.to_csv(f"{out_prefix}_fossil_co2_by_carrier.csv")
    print(fossil_df)

    fuel_df = pd.DataFrame(fuel_rows).T.sort_index()
    fuel_df["CO2Limit_tCO2"] = pd.Series(co2limit)
    # implied energy equivalent of the (possibly-disabled) fossil limit: the
    # limit is defined in MtCO2-eq across a mix of fuels, so there's no
    # single physical MWh figure -- convert using THIS run's own blended
    # tCO2/MWh intensity for that year (its actual oil/gas/coal mix).
    blended_intensity = fossil_df["total"] / fuel_df[["oil", "gas", "coal"]].sum(axis=1)
    fuel_df["FossilLimit_MWh"] = pd.Series(fossil_limit_tco2).reindex(fuel_df.index) / blended_intensity
    fuel_df.to_csv(f"{out_prefix}_total_fuel_mwh.csv")
    print(fuel_df)

    balance_df = pd.DataFrame(balance_rows).T.sort_index()
    balance_df.to_csv(f"{out_prefix}_co2_balance_terms.csv")
    print(balance_df)


if __name__ == "__main__":
    main()
