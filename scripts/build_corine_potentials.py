# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Build available land area per network node from CORINE Land Cover data.

Used upstream of build_afforestation_potentials.py.
"""

import logging

import geopandas
from scripts._helpers import configure_logging
import matplotlib.pyplot as plt
import pandas
from atlite.gis import ExclusionContainer, shape_availability
from rasterio.plot import show

logger = logging.getLogger(__name__)


def build_corine_potentials(
    network_geojson,
    corine_dataset,
    resolution,
    component,
    corine_codes,
    csv_file,
    png_file,
):
    logger.info("Calculate CORINE potentials for %s" % component)

    nodes_geojson = geopandas.read_file(network_geojson).set_index("name")

    excluder = ExclusionContainer(crs=3035, res=resolution)
    excluder.add_raster(corine_dataset, codes=corine_codes, invert=True, crs=3035)
    cell_area = excluder.res**2

    df = pandas.DataFrame(columns=["node", "area [sqkm]", "potential [sqkm]"])
    for node in nodes_geojson.index:
        shape = nodes_geojson.to_crs(excluder.crs).loc[[node]].geometry
        band, transform = shape_availability(shape, excluder)
        area = shape.geometry.area.sum() / 1e6
        selected_cells = band.sum() * cell_area / 1e6
        df.loc[len(df)] = [node, area, selected_cells]
        logger.info(
            "Node=%s * Area=%0.f [sqkm] * Potential=%0.f [sqkm]"
            % (node, area, selected_cells)
        )

    df.set_index("node", inplace=True)

    if csv_file is not None:
        logger.info(
            "Save CORINE potentials for %s into CSV file '%s'" % (component, csv_file)
        )
        df.to_csv(csv_file)

    if png_file is not None:
        logger.info(
            "Save CORINE potentials for %s into PNG file '%s'" % (component, png_file)
        )
        shape = nodes_geojson.to_crs(excluder.crs).geometry
        band, transform = shape_availability(shape, excluder)
        fig, ax = plt.subplots(figsize=(20, 23))
        ax.set_axis_off()
        shape.plot(ax=ax, color="none")
        show(band, transform=transform, cmap="Greens", ax=ax)
        plt.savefig(png_file)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake(
            "build_afforestation_corine_potentials", clusters="39"
        )

    configure_logging(snakemake)

    build_corine_potentials(
        network_geojson=snakemake.input["network_geojson"],
        corine_dataset=snakemake.input["corine_dataset"],
        resolution=snakemake.params["resolution"],
        component=snakemake.params["component"],
        corine_codes=snakemake.params["corine_codes"],
        csv_file=snakemake.output["csv_file"],
        png_file=snakemake.output["png_file"],
    )
