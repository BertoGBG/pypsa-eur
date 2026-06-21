# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT
"""
Land eligibility analysis for Enhanced Rock Weathering (ERW), reusing the
same `atlite <https://github.com/pypsa/atlite>`_ `ExclusionContainer`
machinery as ``determine_availability_matrix.py`` (used for wind/solar), with
two differences:

- Only CORINE Land Cover grid-code exclusion is applied (no Natura2000,
  LUISA, bathymetry, shipping, or shore-distance exclusions, none of which
  are relevant to land-based ERW).
- An additional exclusion removes grid cells whose annual mean air
  temperature (from the atlite cutout) exceeds ``max_mean_temp_C``, replacing
  the previous CORINE+bioclimate-zone "hot"/"temperate" subclass split.

Output
------

- ``resources/availability_matrix_{clusters}_ERW.nc``: same format as
  ``determine_availability_matrix.py``'s output, consumed by
  ``build_available_land.py``.
"""

import functools
import logging
import time

import atlite
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from atlite.gis import shape_availability
from rasterio.io import MemoryFile
from rasterio.plot import show

from scripts._helpers import configure_logging, load_cutout, set_scenario_config

logger = logging.getLogger(__name__)


def _mean_temperature_raster(cutout):
    """
    Build an in-memory, georeferenced raster of the cutout's per-grid-cell
    annual mean air temperature (Kelvin), suitable for
    ``atlite.ExclusionContainer.add_raster``.
    """
    mean_temp = (
        cutout.data["temperature"].mean(dim="time").transpose("y", "x").values
    ).astype("float32")

    memfile = MemoryFile()
    with memfile.open(
        driver="GTiff",
        height=mean_temp.shape[0],
        width=mean_temp.shape[1],
        count=1,
        dtype=mean_temp.dtype,
        crs=cutout.crs,
        transform=cutout.transform,
    ) as dataset:
        dataset.write(mean_temp, 1)

    return memfile, memfile.open()


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("determine_ERW_availability_matrix", clusters="adm")
    configure_logging(snakemake)
    set_scenario_config(snakemake)

    nprocesses = int(snakemake.threads)
    noprogress = snakemake.config["run"].get("disable_progressbar", True)
    noprogress = noprogress or not snakemake.config["atlite"]["show_progress"]
    params = snakemake.params.renewable["ERW"]

    cutout = load_cutout(snakemake.input.cutout)
    regions = gpd.read_file(snakemake.input.regions)
    assert not regions.empty, (
        f"List of regions in {snakemake.input.regions} is empty, please "
        "disable ERW"
    )
    # do not pull up, set_index does not work if geo dataframe is empty
    regions = regions.set_index("name").rename_axis("bus")

    res = params.get("excluder_resolution", 100)
    excluder = atlite.ExclusionContainer(crs=3035, res=res)

    excluder.add_raster(
        snakemake.input.corine, codes=params["corine"], invert=True, crs=3035
    )

    memfile, temp_raster = _mean_temperature_raster(cutout)
    max_mean_temp_K = params["max_mean_temp_C"] + 273.15
    excluder.add_raster(
        temp_raster, codes=functools.partial(np.less, max_mean_temp_K), crs=cutout.crs
    )

    logger.info("Calculate landuse availability for ERW...")
    start = time.time()

    kwargs = dict(nprocesses=nprocesses, disable_progressbar=noprogress)
    availability = cutout.availabilitymatrix(regions, excluder, **kwargs)

    duration = time.time() - start
    logger.info(f"Completed landuse availability calculation for ERW ({duration:2.2f}s)")

    if params.get("plot_availability_matrix", False):
        logger.info("Plotting landuse availability matrix for ERW.")
        band, transform = shape_availability(
            regions.geometry.to_crs(excluder.crs), excluder
        )
        fig, ax = plt.subplots(figsize=(10, 10))
        regions.to_crs(excluder.crs).plot(ax=ax, color="none")
        show(band, transform=transform, cmap="Greens", ax=ax)
        plt.savefig(snakemake.output[0].replace(".nc", ".png"), dpi=300)

    availability.to_netcdf(snakemake.output[0])

    temp_raster.close()
    memfile.close()
