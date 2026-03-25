# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT

"""
Build Enhanced Weathering (EW) CO2 sequestration potentials per network node.

Takes the available CORINE agricultural land area (sqkm) per node from
build_EW_corine_potentials and multiplies by a uniform potential_per_sqkm
(tonnes CO2 per sqkm) from the config to estimate total sequestration potential.

Output: CSV with columns [node, area [sqkm], potential [t]].
"""

import logging

import pandas
from scripts._helpers import configure_logging

logger = logging.getLogger(__name__)


def build_EW_potentials(corine_potentials_csv, potential_per_sqkm, output_csv):
    corine = pandas.read_csv(corine_potentials_csv).set_index("node")

    data_frame = pandas.DataFrame(columns=["node", "area [sqkm]", "potential [t]"])

    for node in corine.index:
        area_sqkm = corine.loc[node, "potential [sqkm]"]
        potential = area_sqkm * potential_per_sqkm
        logger.info(
            "Node '%s': area = %.1f sqkm, EW potential = %.1f t CO2"
            % (node, area_sqkm, potential)
        )
        data_frame.loc[len(data_frame)] = [node, area_sqkm, potential]

    data_frame.set_index("node", inplace=True)
    logger.info("Saving EW potentials to '%s'" % output_csv)
    data_frame.to_csv(output_csv)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from scripts._helpers import mock_snakemake

        snakemake = mock_snakemake("build_EW_potentials", clusters="39")

    configure_logging(snakemake)

    build_EW_potentials(
        corine_potentials_csv=snakemake.input["EW_corine_potentials_csv_file"],
        potential_per_sqkm=snakemake.params["potential_per_sqkm"],
        output_csv=snakemake.output["csv_file"],
    )
