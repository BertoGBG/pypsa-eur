# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
#
# SPDX-License-Identifier: MIT


from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.lib.validation.config._base import ConfigModel
from scripts.lib.validation.config.adjustments import AdjustmentsConfig
from scripts.lib.validation.config.afforestation import AfforestationConfig
from scripts.lib.validation.config.atlite import AtliteConfig
from scripts.lib.validation.config.biomass import BiomassConfig
from scripts.lib.validation.config.clustering import ClusteringConfig
from scripts.lib.validation.config.co2_budget import Co2BudgetConfig
from scripts.lib.validation.config.conventional import ConventionalConfig
from scripts.lib.validation.config.costs import CostsConfig
from scripts.lib.validation.config.countries import CountriesConfig
from scripts.lib.validation.config.data import DataConfig
from scripts.lib.validation.config.electricity import ElectricityConfig
from scripts.lib.validation.config.enable import EnableConfig
from scripts.lib.validation.config.energy import EnergyConfig
from scripts.lib.validation.config.existing_capacities import ExistingCapacitiesConfig
from scripts.lib.validation.config.foresight import ForesightConfig
from scripts.lib.validation.config.industry import IndustryConfig
from scripts.lib.validation.config.lines import LinesConfig
from scripts.lib.validation.config.links import LinksConfig
from scripts.lib.validation.config.load import LoadConfig
from scripts.lib.validation.config.overpass_api import OverpassApiConfig
from scripts.lib.validation.config.plotting import PlottingConfig
from scripts.lib.validation.config.perennials import PerennialsConfig
from scripts.lib.validation.config.renewable import RenewableConfig
from scripts.lib.validation.config.rock_weathering import RockWeatheringConfig
from scripts.lib.validation.config.run import RunConfig
from scripts.lib.validation.config.sector import SectorConfig
from scripts.lib.validation.config.snapshots import SnapshotsConfig
from scripts.lib.validation.config.solar_thermal import SolarThermalConfig
from scripts.lib.validation.config.solving import SolvingConfig
from scripts.lib.validation.config.transformers import TransformersConfig
from scripts.lib.validation.config.transmission_projects import (
    TransmissionProjectsConfig,
)


class LoggingConfig(ConfigModel):
    """Configuration for top level `logging` settings."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO",
        description="Root log level. Messages below this level are discarded before reaching any handler.",
    )
    console_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "WARNING",
        description="Minimum level emitted to the console (stderr). Defaults to ``WARNING`` so parallel rule output stays readable; the full log is kept in the rule's log file.",
    )
    file_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = Field(
        None,
        description="Minimum level written to the rule log file. Defaults to ``level`` when unset.",
    )
    format: str = Field(
        "%(levelname)s:%(name)s:%(message)s",
        description="Custom format for log messages. See `LogRecord <https://docs.python.org/3/library/logging.html#logging.LogRecord>`_ attributes.",
    )


class RemoteConfig(ConfigModel):
    """Configuration for top level `remote` settings."""

    ssh: str = Field(
        "",
        description="Optionally specify the SSH of a remote cluster to be synchronized.",
    )
    path: str = Field(
        "",
        description="Optionally specify the file path within the remote cluster to be synchronized.",
    )


class ConfigSchema(BaseModel):
    """
    Combined configuration schema for PyPSA-EUR.
    """

    # TODO Change to extra='forbid' once schema covers all config options
    # For soft-forks it is recommended to either extend the schema for full config
    # coverage or allow extra fields with extra='allow'
    model_config = ConfigDict(extra="allow", title="PyPSA-Eur Configuration")

    _name: str = "default"
    """internal attribute to track the config filename following the application of config updates"""
    _docs_url: str = (
        "https://pypsa-eur.readthedocs.io/en/latest/configuration/#{field_name}_cf"
    )

    # Top-level fields (from TopLevelConfig)
    version: str = Field(
        "v2026.09.0", description="Version of PyPSA-Eur. Descriptive only."
    )
    tutorial: bool = Field(
        False,
        description="Switch to retrieve the tutorial data set instead of the full data set.",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration for the workflow",
    )
    remote: RemoteConfig = Field(
        default_factory=RemoteConfig,
        description="Configuration for remote workflow execution",
    )

    run: RunConfig = Field(
        default_factory=RunConfig,
        description="Run configuration for PyPSA-EUR workflow execution.",
    )
    foresight: ForesightConfig = Field(
        default_factory=ForesightConfig,
        description="Foresight mode for the optimization. See Foresight Options for detailed explanations.",
    )
    planning_horizons: list[int] = Field(
        [2050],
        description="Planning horizon year(s) for the optimization.",
    )

    @field_validator("planning_horizons", mode="before")
    @classmethod
    def normalize_planning_horizons(cls, v):
        if isinstance(v, (int, str)):
            return [int(v)]
        return [int(h) for h in v]

    countries: CountriesConfig = Field(
        default_factory=CountriesConfig,
        description="European countries defined by their Two-letter country codes (ISO 3166-1) which should be included in the energy system model.",
    )
    snapshots: SnapshotsConfig = Field(
        default_factory=SnapshotsConfig,
        description="Configuration for the time period snapshots.",
    )
    enable: EnableConfig = Field(
        default_factory=EnableConfig,
        description="Flags to enable/disable workflow features.",
    )
    co2_budget: Co2BudgetConfig = Field(
        default_factory=Co2BudgetConfig,
        description="CO2 budget as fraction of 1990 emissions per planning horizon year.",
    )
    lulucf_deviation: bool = Field(
        False,
        description="Correct the CO2 budget for the deviation of the real LULUCF sink from the sink the budget implicitly assumes: `lulucf_deviation_values` (MtCO2/yr) are subtracted from the upper CO2 bound of each planning horizon (positive: sink underperforms, budget tightened).",
    )
    lulucf_deviation_values: dict[int, float] = Field(
        default_factory=lambda: {
            2020: 73.2,
            2025: 54.4,
            2030: 69.5,
            2035: 96.1,
            2040: 112.8,
            2045: 116.7,
            2050: 129.3,
        },
        description="Shortfall of the EU-27 LULUCF sink against the -310 MtCO2e target of 2030 (Regulation (EU) 2023/839), held as reference to 2050, in MtCO2/yr per planning horizon. Single source: EEA (2026), Trends and projections in Europe 2026, Figure 3.2: Member State projections (2025 submissions) with additional measures (WAM) for 2030-2050 (-240, -214, -197, -193, -181 MtCO2e); 2025 from the approximated inventory (-256), 2020 from the inventory (-237).",
    )
    fossil_limit: bool = Field(
        False,
        description="Annual cap on the total fossil fuel supply (gas, oil, coal, lignite) in MtCO2-eq at the wellhead (`fossil_limit_values`); unlike the CO2 budget, carbon capture gives no credit. Implemented as a `primary_energy` GlobalConstraint (add_fossil_fuel_limit).",
    )
    fossil_limit_values: dict[int, float] = Field(
        default_factory=lambda: {
            2025: 2600,
            2030: 1378,
            2035: 456,
            2040: 129,
            2045: 103,
            2050: 78,
        },
        description="Cap on the total fossil fuel supply in MtCO2-eq per year (medium scenario).",
    )
    energy_limit_per_carrier: bool = Field(
        False,
        description="Independent supply cap per fossil carrier (energy-security lens), one `primary_energy` GlobalConstraint per carrier (add_energy_limit_per_carrier); can be combined with `fossil_limit`.",
    )
    energy_limit_per_carrier_values: dict[str, dict[int, float]] = Field(
        default_factory=lambda: {
            "gas": {2025: 768.0, 2030: 665.0, 2035: 474.3, 2040: 313.2, 2045: 177.4, 2050: 102.5},
            "oil": {2025: 1653.9, 2030: 1447.8, 2035: 1031.9, 2040: 600.9, 2045: 242.9, 2050: 79.2},
            "coal": {2025: 289.7, 2030: 272.8, 2035: 232.7, 2040: 184.8, 2045: 144.6, 2050: 127.8},
            "lignite": {2025: 255.0, 2030: 260.1, 2035: 272.2, 2040: 286.6, 2045: 298.7, 2050: 303.8},
        },
        description="Supply cap per carrier in MtCO2-eq per year: EU-safe production (Norway+UK for gas and oil, EU coal and lignite) plus an import allowance that moves from today's imports (Eurostat nrg_bal_c 2024, UK from DESNZ DUKES) to the 2050 target (here 100% self-sufficiency) along a smoothstep.",
    )
    like_for_like: bool = Field(
        False,
        description="Like-for-like constraint G - D <= E: geological carbon used (fossil fuel supply at the wellhead/mine plus fossil process CO2 of industry, before capture) minus durable storage (CO2 sequestered plus enhanced rock weathering) must stay below the CO2 limit of the climate path without the LULUCF correction. Biochar, afforestation and perennialisation do not count. Myopic/overnight only (add_like_for_like in prepare_sector_network, enforced in solve_network).",
    )
    like_for_like_values: dict[int, float] | None = Field(
        None,
        description="Right-hand side E of the like-for-like constraint in MtCO2 per year. If null, the CO2 limit of the planning horizon without the LULUCF correction is used, so the constraint becomes the strict condition G <= D in the net-zero year.",
    )
    electricity: ElectricityConfig = Field(
        default_factory=ElectricityConfig,
        description="Electricity sector configuration.",
    )
    atlite: AtliteConfig = Field(
        default_factory=AtliteConfig,
        description="Atlite cutout configuration for weather data.",
    )
    renewable: RenewableConfig = Field(
        default_factory=RenewableConfig,
        description="Renewable energy technologies configuration.",
    )
    perennials: PerennialsConfig = Field(
        default_factory=PerennialsConfig,
        description="Perennialisation (carbon dioxide removal) configuration.",
    )
    conventional: ConventionalConfig = Field(
        default_factory=ConventionalConfig,
        description="Conventional power plants configuration.",
    )
    lines: LinesConfig = Field(
        default_factory=LinesConfig,
        description="Transmission lines configuration.",
    )
    links: LinksConfig = Field(
        default_factory=LinksConfig,
        description="HVDC links configuration.",
    )
    transmission_projects: TransmissionProjectsConfig = Field(
        default_factory=TransmissionProjectsConfig,
        description="Transmission projects configuration.",
    )
    transformers: TransformersConfig = Field(
        default_factory=TransformersConfig,
        description="Transformers configuration.",
    )
    load: LoadConfig = Field(
        default_factory=LoadConfig,
        description="Electrical load configuration.",
    )
    energy: EnergyConfig = Field(
        default_factory=EnergyConfig,
        description="Energy totals configuration.",
    )
    biomass: BiomassConfig = Field(
        default_factory=BiomassConfig,
        description="Biomass configuration.",
    )
    solar_thermal: SolarThermalConfig = Field(
        default_factory=SolarThermalConfig,
        description="Solar thermal configuration.",
    )
    existing_capacities: ExistingCapacitiesConfig = Field(
        default_factory=ExistingCapacitiesConfig,
        description="Existing capacities grouping configuration.",
    )
    sector: SectorConfig = Field(
        default_factory=SectorConfig,
        description="Sector coupling configuration.",
    )
    industry: IndustryConfig = Field(
        default_factory=IndustryConfig,
        description="Industry sector configuration.",
    )
    afforestation: AfforestationConfig = Field(
        default_factory=AfforestationConfig,
        description="Afforestation configuration.",
    )
    rock_weathering: RockWeatheringConfig = Field(
        default_factory=RockWeatheringConfig,
        description="Enhanced rock weathering configuration.",
    )
    costs: CostsConfig = Field(
        default_factory=CostsConfig,
        description="Cost assumptions configuration.",
    )
    clustering: ClusteringConfig = Field(
        default_factory=ClusteringConfig,
        description="Network clustering configuration.",
    )
    adjustments: AdjustmentsConfig = Field(
        default_factory=AdjustmentsConfig,
        description="Network adjustments configuration.",
    )
    solving: SolvingConfig = Field(
        default_factory=SolvingConfig,
        description="Solver and optimization configuration.",
    )
    data: DataConfig = Field(
        default_factory=DataConfig,
        description="Data source configuration.",
    )
    overpass_api: OverpassApiConfig = Field(
        default_factory=OverpassApiConfig,
        description="Overpass API configuration for OSM data retrieval.",
    )
    plotting: PlottingConfig = Field(
        default_factory=PlottingConfig,
        description="Plotting and summary settings.",
    )

    @model_validator(mode="before")
    @classmethod
    def check_no_secrets_section(cls, data):
        """Prevent secrets from being stored in config."""
        if isinstance(data, dict) and "secrets" in data:
            raise ValueError(
                "The 'secrets:' section is no longer supported in config to avoid "
                "leaking credentials. Use environment variables instead (e.g., "
                "CORINE_API_TOKEN). You can set these in a .env file in the project root."
            )
        return data

    @model_validator(mode="before")
    @classmethod
    def check_no_pypsa_eur_section(cls, data):
        """Reject the removed `pypsa_eur` section."""
        if isinstance(data, dict) and "pypsa_eur" in data:
            raise ValueError(
                "The 'pypsa_eur:' section is removed. Select power plants with "
                "'electricity: renewable_carriers' and 'electricity: conventional_carriers'."
            )
        return data
