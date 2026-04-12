# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Build Enhanced Weathering (ERW) CO2 sequestration potentials per network node.

Intersects CORINE Land Cover data with bioclimatic zone data for each ERW
subclass (e.g. EW_hot, EW_temperate) defined in the config. Each subclass
specifies its own CORINE land-use codes, bioclimatic zone codes, and
sequestration rate (potential_per_sqkm). Potentials from all subclasses are
summed per node.

The bioclimatic dataset ``World_Ecological_BioVal_cluster.tif`` must be placed
at ``data/World_Ecological_BioVal_cluster.tif`` before running the workflow.

Output: CSV with column ``potential [t]`` indexed by node name.
"""

import logging

import geopandas
import matplotlib.pyplot as plt
import pandas
from atlite.gis import ExclusionContainer, shape_availability
from rasterio.plot import show

from scripts._helpers import configure_logging

logger = logging.getLogger(__name__)

_EW_NON_SUBCLASS_KEYS = {"max_land_usage"}


def build_EW_potentials(
    network_geojson,
    corine_dataset,
    bioclimate_dataset,
    ew_config,
    resolution,
    csv_file,
    png_file,
):
    nodes_geojson = geopandas.read_file(network_geojson).set_index("name")
    subclasses = {k: v for k, v in ew_config.items() if k not in _EW_NON_SUBCLASS_KEYS}

    node_potentials = {node: 0.0 for node in nodes_geojson.index}
    excluder = None

    for comp, cfg in subclasses.items():
        logger.info("Calculating potentials for ERW subclass '%s'", comp)
        excluder = ExclusionContainer(crs=3035, res=resolution)
        excluder.add_raster(corine_dataset, codes=cfg["corine"], invert=True, crs=3035)
        excluder.add_raster(
            bioclimate_dataset, codes=cfg["climate"], invert=True, crs=3035
        )
        cell_area_sqkm = excluder.res**2 / 1e6

        for node in nodes_geojson.index:
            shape = nodes_geojson.to_crs(excluder.crs).loc[[node]].geometry
            band, _ = shape_availability(shape, excluder)
            area_sqkm = band.sum() * cell_area_sqkm
            potential = area_sqkm * cfg["potential_per_sqkm"]
            node_potentials[node] += potential
            logger.debug(
                "  %s / %s: area=%.1f sqkm, potential=%.1f t CO2",
                comp,
                node,
                area_sqkm,
                potential,
            )

    df = pandas.DataFrame.from_dict(
        node_potentials, orient="index", columns=["potential [t]"]
    )
    df.index.name = "node"

    logger.info("Total ERW potential: %.2f Mt CO2", df["potential [t]"].sum() / 1e6)

    if csv_file is not None:
        logger.info("Saving ERW potentials to '%s'", csv_file)
        df.to_csv(csv_file)

    if png_file is not None:
        logger.info("Saving ERW potentials map to '%s'", png_file)
        shape = nodes_geojson.to_crs(excluder.crs).geometry
        band, transform = shape_availability(shape, excluder)
        fig, ax = plt.subplots(figsize=(20, 23))
        ax.set_axis_off()
        shape.plot(ax=ax, color="none")
        show(band, transform=transform, cmap="Greens", ax=ax)
        plt.savefig(png_file)
        plt.close(fig)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_EW_potentials")

    configure_logging(snakemake)

    build_EW_potentials(
        network_geojson=snakemake.input["network_geojson"],
        corine_dataset=snakemake.input["corine_dataset"],
        bioclimate_dataset=snakemake.input["bioclimate_dataset"],
        ew_config=snakemake.config["ERW"],
        resolution=snakemake.params["resolution"],
        csv_file=snakemake.output["csv_file"],
        png_file=snakemake.output.get("png_file"),
    )
