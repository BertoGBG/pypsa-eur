<!-- SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur> -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Biomass, Gas and Carbon

The rules on this page prepare the regional potentials and infrastructure of
the carriers that are not electricity: biomass potentials and transport costs,
the gas network with its entry points, salt caverns for hydrogen storage and
geological CO~2~ sequestration potentials. See [Biomass](../design/biomass.md),
[Methane](../design/methane.md), [Hydrogen](../design/hydrogen.md) and [Carbon
management](../design/carbon-management.md) in the design section.

## Biomass

{{ rules("build_biomass_potentials", "build_biomass_transport_costs") }}

## Gas network and hydrogen storage

{{ rules("build_gas_network", "build_gas_input_locations", "cluster_gas_network", "build_salt_cavern_potentials") }}

## Carbon sequestration

{{ rules("build_co2_sequestration_potentials", "build_clustered_co2_sequestration_potentials") }}

## Carbon dioxide removal

Afforestation (`sector: afforestation`): eligible land from CORINE, potentials
and seasonal profiles from the CO2-removal dataset.

{{ rules("determine_carbon_dioxide_removal_availability_matrix", "build_available_land", "build_afforestation_potentials") }}

Perennialisation (`sector: perennials`): Eurostat crop yields per region for
the 1st-generation biofuel cropland freed by the phase-out of the
unsustainable bioliquids (the freed land itself is computed in
`build_biomass_potentials`).

{{ rules("build_perennials_yields_eurostat_average", "build_perennials_yields") }}
