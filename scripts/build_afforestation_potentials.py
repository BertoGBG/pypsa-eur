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


def build_afforestation_potentials(
    network_geojson,
    nuts2_geojson,
    corine_potentials_csv,
    afforestation_nuts_file,
    potential_type,
    output_csv,
):
    network = geopandas.read_file(network_geojson)
    corine_potentials = pandas.read_csv(corine_potentials_csv).set_index("node")

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
                "Node '%s': afforestation potential = %d t/ha" % (node_name, potential) # this is dimensionally not correct!
            )
            data_frame.loc[len(data_frame)] = [node_name, biomass_density, potential]

    else:  # growth
        logger.info("Calculating afforestation potentials based on growth rates.")
        nuts2 = geopandas.read_file(nuts2_geojson)
        nuts2_growth_rates = pandas.read_csv(afforestation_nuts_file).set_index(
            "NUTS2"
        )

        # harmonize NUTS2 indexes (EL → GR, UK → GB)
        nuts2["NUTS_ID"] = nuts2["NUTS_ID"].apply(
            lambda x: "GR%s" % x[2:] if x[:2] == "EL" else x
        )
        nuts2["NUTS_ID"] = nuts2["NUTS_ID"].apply(
            lambda x: "GB%s" % x[2:] if x[:2] == "UK" else x
        )
        nuts2_growth_rates = nuts2_growth_rates.rename(
            index=lambda x: "GR%s" % x[2:] if x[:2] == "EL" else x
        )
        nuts2_growth_rates = nuts2_growth_rates.rename(
            index=lambda x: "GB%s" % x[2:] if x[:2] == "UK" else x
        )

        # Use the different column names as density mode hence branching is needed in prepare_sector_network.py
        #   "growth rate [t/ha]" → weighted-average growth rate [t/(ha y)]
        #   "potential [t/y]"    → total annual sequestration potential [t/y]
        data_frame = pandas.DataFrame(
            columns=["node", "growth rate [t/ha]", "potential [t/y]"]
        )

        for i in range(len(network)):
            node_row = network.iloc[i]
            node_name = node_row["name"]
            node_geometry = geopandas.GeoSeries(node_row["geometry"], crs=3035)
            total_area_ha = corine_potentials.loc[node_name]["potential [sqkm]"] * 100

            total_fraction = 0
            node_potential = 0
            for j in range(len(nuts2)):
                nuts2_row = nuts2.iloc[j]
                nuts2_name = nuts2_row["NUTS_ID"]
                if nuts2_name[:2] != node_name[:2]:
                    continue
                nuts2_geometry = geopandas.GeoSeries(nuts2_row["geometry"], crs=3035)
                intersection = nuts2_geometry.intersection(node_geometry.iloc[0])
                fraction = float(intersection.area.iloc[0]) / float(
                    node_geometry.area.iloc[0]
                )
                total_fraction += fraction
                node_potential += (
                    total_area_ha
                    * nuts2_growth_rates.loc[nuts2_name]["affo rate (t/ha/y)"]
                    * fraction
                )

            if total_fraction > 0 and (
                total_fraction < 0.99 or total_fraction > 1.01
            ):
                logger.error(
                    "Node '%s' has unexpected total fraction %.4f (expected ~1)"
                    % (node_name, total_fraction)
                )

            # weighted-average growth rate [t/ha/y] — used for capital cost
            weighted_growth_rate = node_potential / total_area_ha if total_area_ha > 0 else 0.0

            logger.info(
                "Node '%s': afforestation potential = %.1f t/y  (growth rate = %.3f t/ha/y)"
                % (node_name, node_potential, weighted_growth_rate)
            )
            data_frame.loc[len(data_frame)] = [node_name, weighted_growth_rate, node_potential]

    data_frame.set_index("node", inplace=True)
    logger.info("Saving afforestation potentials to '%s'" % output_csv)
    data_frame.to_csv(output_csv)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_afforestation_potentials", clusters="39")

    configure_logging(snakemake)

    potential_type = snakemake.params.afforestation_potential_type

    build_afforestation_potentials(
        network_geojson=snakemake.params["network_geojson"],
        nuts2_geojson=snakemake.params["nuts2_geojson"],
        corine_potentials_csv=snakemake.input["afforestation_corine_potentials_csv_file"],
        afforestation_nuts_file=snakemake.input["afforestation_nuts_file"],
        potential_type=potential_type,
        output_csv=snakemake.output["csv_file"],
    )
