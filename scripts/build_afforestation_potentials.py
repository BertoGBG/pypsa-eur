# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Build afforestation CO2 sequestration potentials per network node.

Two calculation methods are supported (set via config["afforestation"]["potential_type"]):

density
    Uses country-level NUTS0 biomass densities (t/ha) from an Excel file
    (downloaded from figshare) to estimate total CO2 sequestration potential
    per node based on available CORINE land area.

growth
    Uses NUTS2-level annual growth rates (t/ha/y) to estimate CO2 sequestration
    potential by spatially intersecting network regions with NUTS2 geometries.

Output: CSV with columns [node, potential [t/ha]] (density mode also includes
        "biomass density [t/ha]").
"""

import logging

import geopandas
import pandas
from scripts._helpers import configure_logging

logger = logging.getLogger(__name__)


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def build_afforestation_potentials(
    network_geojson,
    nuts2_geojson,
    corine_potentials_csv,
    afforestation_nuts_file,
    potential_type,
    output_csv,
    monthly_weights_file=None,
    output_monthly_weights_csv=None,
    snapshot_config=None,
    output_seasonal_profile_csv=None,
):
    network = geopandas.read_file(network_geojson)
    corine_potentials = pandas.read_csv(corine_potentials_csv).set_index("node")
    monthly_weights_rows = []  # populated only in growth mode

    if potential_type == "density":
        logger.info("Calculating afforestation potentials based on biomass densities.")
        nuts_biomass_density = (
            pandas.read_excel(
                afforestation_nuts_file, sheet_name="BIOMASS 2020", skiprows=2
            )
            .iloc[:, [2, 7]]
            .set_index("NUTS")
        )
        nuts_biomass_density = nuts_biomass_density[
            nuts_biomass_density.index.str.len() == 2
        ]

        # Use the different column names as growth mode hence branching is needed in prepare_sector_network.py
        #   "biomass density [t/ha] [t/ha]" → weighted-average growth rate [t/(ha y)]
        #   "AGB [t]"    → total Above Ground Biomass in forest per node [t]
        data_frame = pandas.DataFrame(
            columns=["node", "biomass density [t/ha]", "AGB [t]"]
        )

        for i in range(len(network)):
            node_name = network.iloc[i]["name"]
            country = node_name[:2]
            if country in nuts_biomass_density.index:
                biomass_density = nuts_biomass_density.loc[country]["(Tons/ha)"]
            else:
                logger.warning(
                    "Set biomass density to 117 t/ha for node '%s' "
                    "(country '%s' not in dataset)" % (node_name, country)
                )
                biomass_density = 117
            potential = (
                corine_potentials.loc[node_name]["potential [sqkm]"] * 100
            ) * biomass_density
            logger.info(
                "Node '%s': afforestation potential (AGB) = %d t" % (node_name, potential)
            )
            data_frame.loc[len(data_frame)] = [node_name, biomass_density, potential]

    else:  # growth
        logger.info("Calculating afforestation potentials based on growth rates.")
        nuts2 = geopandas.read_file(nuts2_geojson)
        nuts2_growth_rates = pandas.read_csv(afforestation_nuts_file).set_index("NUTS2")
        nuts2_monthly_weights = pandas.read_csv(monthly_weights_file, index_col="NUTS_ID")

        # harmonize NUTS2 indexes (EL → GR, UK → GB)
        def harmonize_idx(idx):
            return idx.map(
                lambda x: ("GR" if x[:2] == "EL" else ("GB" if x[:2] == "UK" else x[:2])) + x[2:]
            )

        nuts2["NUTS_ID"] = harmonize_idx(nuts2["NUTS_ID"])
        nuts2_growth_rates.index = harmonize_idx(nuts2_growth_rates.index)
        nuts2_monthly_weights.index = harmonize_idx(nuts2_monthly_weights.index)

        # Build NUTS2 GeoDataFrame with rates and monthly weights joined
        nuts2_gdf = nuts2[["NUTS_ID", "geometry"]].set_index("NUTS_ID")
        nuts2_gdf = nuts2_gdf.join(nuts2_growth_rates[["CO2 seq rate tCO2/(ha y)"]])
        nuts2_gdf = nuts2_gdf.join(nuts2_monthly_weights[MONTH_NAMES])

        # Warn about NUTS2 regions missing monthly weights; fill with uniform 1/12 - it should not happen
        missing_w = nuts2_gdf[nuts2_gdf[MONTH_NAMES].isna().any(axis=1)].index.tolist()
        if missing_w:
            logger.warning(
                "NUTS2 regions missing monthly weights (using uniform 1/12): %s" % missing_w
            )
        nuts2_gdf[MONTH_NAMES] = nuts2_gdf[MONTH_NAMES].fillna(1.0 / 12)
        nuts2_gdf = nuts2_gdf.reset_index()  # NUTS_ID back as column for overlay

        # Project to EPSG:3035 for area calculations
        network_3035 = network.to_crs(3035)
        nuts2_3035 = nuts2_gdf.to_crs(3035)

        # Spatial overlay: one call replaces the manual double loop
        overlay = geopandas.overlay(
            network_3035[["name", "geometry"]],
            nuts2_3035,
            how="intersection",
            keep_geom_type=True,
        )

        # Share of node area covered by each NUTS2 region (weights for intensive quantities)
        node_areas = network_3035.set_index("name").geometry.area
        overlay["share"] = overlay.geometry.area / overlay["name"].map(node_areas)

        # CORINE available land per node [ha]
        overlay["total_area_ha"] = overlay["name"].map(
            corine_potentials["potential [sqkm]"] * 100
        )

        # Weighted potential and monthly weight contributions per intersection
        overlay["potential_contrib"] = (
            overlay["total_area_ha"] * overlay["CO2 seq rate tCO2/(ha y)"] * overlay["share"]
        )
        for m in MONTH_NAMES:
            overlay[f"w_{m}"] = overlay[m] * overlay["share"]

        # Aggregate per node
        w_cols = [f"w_{m}" for m in MONTH_NAMES]
        agg = overlay.groupby("name").agg({"potential_contrib": "sum", **{c: "sum" for c in w_cols}})

        # Normalise monthly weights to sum to 1
        agg[w_cols] = agg[w_cols].div(agg[w_cols].sum(axis=1), axis=0)

        # Weighted-average growth rate [tCO2/(ha·y)] — used for capital cost
        node_area_ha = corine_potentials["potential [sqkm]"] * 100
        agg["CO2 seq rate tCO2/(ha y)"] = (
            agg["potential_contrib"] / node_area_ha.reindex(agg.index)
        )

        for node_name, row in agg.iterrows():
            logger.info(
                "Node '%s': afforestation potential = %.1f tCO2/y  "
                "(CO2 seq rate = %.3f tCO2/(ha y))"
                % (node_name, row["potential_contrib"], row["CO2 seq rate tCO2/(ha y)"])
            )

        # Build data_frame with "node" as column (set_index called in shared save block below)
        agg.index.name = "node"
        data_frame = agg[["CO2 seq rate tCO2/(ha y)", "potential_contrib"]].rename(
            columns={"potential_contrib": "potential [tCO2/y]"}
        ).reset_index()

        # Node-level monthly weights for seasonal profile generation
        monthly_weights_rows = [
            {"node": node, **{m: agg.at[node, f"w_{m}"] for m in MONTH_NAMES}}
            for node in agg.index
        ]

    data_frame.set_index("node", inplace=True)
    logger.info("Saving afforestation potentials to '%s'" % output_csv)
    data_frame.to_csv(output_csv)

    if output_monthly_weights_csv is not None:
        if monthly_weights_rows:
            mw_df = pandas.DataFrame(monthly_weights_rows).set_index("node")
            logger.info(
                "Saving node-level monthly weights to '%s'" % output_monthly_weights_csv
            )
            mw_df.to_csv(output_monthly_weights_csv)
        else:
            # density mode: write empty placeholder so Snakemake output is satisfied
            pandas.DataFrame(columns=["node"] + MONTH_NAMES).set_index("node").to_csv(
                output_monthly_weights_csv
            )

    if output_seasonal_profile_csv is not None:
        if monthly_weights_rows and snapshot_config is not None:
            logger.info("Building hourly seasonal profile for growth mode ...")
            mw_df = pandas.DataFrame(monthly_weights_rows).set_index("node")
            snapshots = pandas.date_range(
                start=snapshot_config["start"],
                end=snapshot_config["end"],
                freq=snapshot_config.get("freq", "h"),
                inclusive="left",
            )
            T_year = len(snapshots)
            H_m = {m: int((snapshots.month == m).sum()) for m in range(1, 13)}
            profile = pandas.DataFrame(index=snapshots, columns=mw_df.index, dtype=float)
            for m_idx, m_name in enumerate(MONTH_NAMES, 1):
                mask = snapshots.month == m_idx
                h_m = H_m[m_idx]
                scale = T_year / h_m if h_m > 0 else 1.0 / 12
                profile.loc[mask] = (mw_df[m_name] * scale).values
            profile.index.name = "snapshot"
            logger.info("Saving seasonal profile to '%s'" % output_seasonal_profile_csv)
            profile.to_csv(output_seasonal_profile_csv)
        else:
            # density mode or no snapshot config: write empty placeholder
            pandas.DataFrame(columns=["snapshot"]).set_index("snapshot").to_csv(
                output_seasonal_profile_csv
            )


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_afforestation_potentials", clusters="39")

    configure_logging(snakemake)

    potential_type = snakemake.params.afforestation_potential_type

    # monthly_weights_file is empty list ([]) for density mode
    monthly_weights_file = snakemake.input.get("afforestation_monthly_weights_file") or None
    if isinstance(monthly_weights_file, list):
        monthly_weights_file = monthly_weights_file[0] if monthly_weights_file else None

    build_afforestation_potentials(
        network_geojson=snakemake.params["network_geojson"],
        nuts2_geojson=snakemake.params["nuts2_geojson"],
        corine_potentials_csv=snakemake.input["afforestation_corine_potentials_csv_file"],
        afforestation_nuts_file=snakemake.input["afforestation_nuts_file"],
        potential_type=potential_type,
        output_csv=snakemake.output["csv_file"],
        monthly_weights_file=monthly_weights_file,
        output_monthly_weights_csv=snakemake.output["monthly_weights_csv_file"],
        snapshot_config=snakemake.params.get("snapshots"),
        output_seasonal_profile_csv=snakemake.output["seasonal_profile_csv_file"],
    )
