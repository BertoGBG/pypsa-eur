"""
Compute monthly GPP seasonal profiles per NUTS2 region from FluxCom data.

Pipeline:
  1. Load FluxCom monthly GPP NetCDF files (gC m⁻² day⁻¹)
  2. Clip to Europe bounding box
  3. Compute multi-year monthly climatology (mean Jan, mean Feb, ..., mean Dec)
  4. Zonal statistics: mean GPP per NUTS2 polygon for each month
  5. Normalise: each region's 12-month profile sums to 1.0
     → monthly_weight[region, month] ∈ [0, 1]
  6. Merge with annual sequestration rates from Pilli et al.
  7. Save: nuts2_monthly_weights.csv  (NUTS2 × 12 months)
           nuts2_monthly_rates.csv    (NUTS2 × 12 months, tCO₂ ha⁻¹ month⁻¹)

Reference:
  Jung, M. et al. (2020). Biogeosciences, 17(5), 1343–1365.
  https://doi.org/10.5194/bg-17-1343-2020

Usage:
    python 02_compute_nuts2_profiles.py [--gpp-dir PATH] [--rates PATH]
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──────────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
GPP_DIR = DATA_DIR / "fluxcom_raw"
OUTPUT_DIR = HERE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

RATES_CSV = HERE.parent / "output" / "afforestation_rates_nuts2.csv"

# Europe bounding box (lon_min, lat_min, lon_max, lat_max)
EUROPE_BBOX = (-25.0, 34.0, 45.0, 72.0)

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Compute NUTS2 monthly GPP profiles")
    p.add_argument(
        "--gpp-dir", type=Path, default=GPP_DIR,
        help="Directory with FluxCom NetCDF files (default: data/fluxcom_raw/)"
    )
    p.add_argument(
        "--rates", type=Path, default=RATES_CSV,
        help="Path to afforestation_rates_nuts2.csv from Pilli et al. step"
    )
    p.add_argument(
        "--nuts-url",
        default=(
            "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
            "NUTS_RG_10M_2021_4326_LEVL_2.geojson"
        ),
        help="URL or local path to NUTS2 GeoJSON (EPSG:4326)"
    )
    return p.parse_args()


# ── Step 1: Load FluxCom files ─────────────────────────────────────────────────

def load_fluxcom_europe(gpp_dir: Path) -> xr.DataArray:
    """
    Load all annual FluxCom NetCDF files, concatenate along time,
    return DataArray clipped to Europe at monthly resolution.

    FluxCom files contain variable 'GPP' with dims (time, lat, lon).
    Units: gC m⁻² day⁻¹  (multiply by days-in-month for monthly totals,
    but for normalised weights the unit cancels out so we keep day⁻¹).
    """
    nc_files = sorted(gpp_dir.glob("GPP_fluxcom_monthly_*.nc"))
    if not nc_files:
        raise FileNotFoundError(
            f"No FluxCom files found in {gpp_dir}.\n"
            "Run 01_download_fluxcom.py first, or place files manually:\n"
            "  GPP_fluxcom_monthly_YYYY.nc"
        )

    print(f"Loading {len(nc_files)} FluxCom file(s): {[f.name for f in nc_files]}")

    ds = xr.open_mfdataset(nc_files, combine="by_coords", engine="netcdf4")

    # Variable may be named 'GPP' or 'gpp' depending on version
    gpp_var = "GPP" if "GPP" in ds else "gpp"
    gpp = ds[gpp_var]

    # Normalise coordinate names to 'lat' / 'lon'
    rename = {}
    for dim in gpp.dims:
        if dim.lower() in ("latitude", "lat"):
            rename[dim] = "lat"
        elif dim.lower() in ("longitude", "lon"):
            rename[dim] = "lon"
    if rename:
        gpp = gpp.rename(rename)

    # Clip to Europe
    lon_min, lat_min, lon_max, lat_max = EUROPE_BBOX
    gpp = gpp.sel(
        lat=slice(lat_max, lat_min),   # lat is stored N→S in most datasets
        lon=slice(lon_min, lon_max),
    )
    # If lat is stored S→N try the other slice direction
    if gpp.lat.size == 0:
        gpp = ds[gpp_var].rename(rename).sel(
            lat=slice(lat_min, lat_max),
            lon=slice(lon_min, lon_max),
        )

    print(f"  Clipped to Europe: {gpp.lat.size} lat × {gpp.lon.size} lon × {gpp.time.size} timesteps")
    return gpp


# ── Step 2: Monthly climatology ────────────────────────────────────────────────

def monthly_climatology(gpp: xr.DataArray) -> xr.DataArray:
    """
    Compute mean GPP for each calendar month across all years.
    Returns DataArray with dim 'month' (1–12) instead of 'time'.
    """
    clim = gpp.groupby("time.month").mean(dim="time")
    print(f"  Climatology: {clim.month.values} → shape {clim.shape}")
    return clim  # dims: (month=12, lat, lon)


# ── Step 3: NUTS2 polygons ─────────────────────────────────────────────────────

def load_nuts2(nuts_source: str) -> gpd.GeoDataFrame:
    """
    Load NUTS2 polygons. Accepts a URL or local file path.
    Returns GeoDataFrame with column 'NUTS_ID' and geometry in EPSG:4326.
    """
    print(f"Loading NUTS2 polygons from: {nuts_source}")
    nuts = gpd.read_file(nuts_source)

    # Filter to NUTS level 2
    if "LEVL_CODE" in nuts.columns:
        nuts = nuts[nuts["LEVL_CODE"] == 2].copy()
    elif "nuts2" in nuts.columns.str.lower().tolist():
        pass  # already level 2

    id_col = next(
        (c for c in nuts.columns if c in ("NUTS_ID", "nuts2", "id", "GID_2")), None
    )
    if id_col and id_col != "NUTS_ID":
        nuts = nuts.rename(columns={id_col: "NUTS_ID"})

    nuts = nuts[["NUTS_ID", "geometry"]].to_crs("EPSG:4326")
    print(f"  {len(nuts)} NUTS2 regions loaded.")
    return nuts


# ── Step 4: Zonal statistics ───────────────────────────────────────────────────

def zonal_mean_per_nuts2(
    clim: xr.DataArray, nuts: gpd.GeoDataFrame
) -> pd.DataFrame:
    """
    For each NUTS2 polygon and each month, compute the mean GPP over all
    0.5° grid cells whose centre falls within the polygon.

    Returns DataFrame: index=NUTS_ID, columns=month (1–12).

    Note: point-in-polygon approach is accurate enough at 0.5° for NUTS2
    (median NUTS2 area ~15,000 km², >> one FluxCom cell ~3,000 km²).
    For small regions (e.g. city-states like AT13, BE10) we fall back to the
    nearest grid cell.
    """
    lons = clim.lon.values
    lats = clim.lat.values
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    lon_flat = lon_grid.ravel()
    lat_flat = lat_grid.ravel()

    # Build a GeoDataFrame of grid cell centres
    from shapely.geometry import Point
    cell_gdf = gpd.GeoDataFrame(
        {"lon_idx": np.tile(np.arange(len(lons)), len(lats)),
         "lat_idx": np.repeat(np.arange(len(lats)), len(lons))},
        geometry=[Point(x, y) for x, y in zip(lon_flat, lat_flat)],
        crs="EPSG:4326",
    )

    # Spatial join: which NUTS2 region does each grid cell belong to?
    print("  Running spatial join (grid cells → NUTS2 polygons)...")
    joined = gpd.sjoin(cell_gdf, nuts[["NUTS_ID", "geometry"]], how="left", predicate="within")

    records = []
    nuts_ids = nuts["NUTS_ID"].tolist()

    for nuts_id in nuts_ids:
        mask = joined["NUTS_ID"] == nuts_id
        cell_rows = joined[mask]

        if cell_rows.empty:
            # Fallback: nearest grid cell centre
            centroid = nuts.loc[nuts["NUTS_ID"] == nuts_id, "geometry"].values[0].centroid
            dist = np.sqrt((lon_flat - centroid.x) ** 2 + (lat_flat - centroid.y) ** 2)
            nearest = np.argmin(dist)
            li = int(joined.iloc[nearest]["lat_idx"]) if nearest < len(joined) else 0
            lo = int(joined.iloc[nearest]["lon_idx"]) if nearest < len(joined) else 0
            monthly_vals = {m: float(clim.sel(month=m).values[li, lo]) for m in range(1, 13)}
        else:
            lat_idxs = cell_rows["lat_idx"].astype(int).values
            lon_idxs = cell_rows["lon_idx"].astype(int).values
            monthly_vals = {}
            for m in range(1, 13):
                month_data = clim.sel(month=m).values
                vals = month_data[lat_idxs, lon_idxs]
                # Mask fill values (FluxCom uses large negative or NaN for ocean)
                vals = np.where(np.isfinite(vals) & (vals > 0), vals, np.nan)
                monthly_vals[m] = float(np.nanmean(vals)) if np.any(np.isfinite(vals)) else np.nan

        row = {"NUTS_ID": nuts_id}
        row.update(monthly_vals)
        records.append(row)

    df = pd.DataFrame(records).set_index("NUTS_ID")
    df.columns = pd.Index(range(1, 13), name="month")
    print(f"  Zonal stats done: {df.shape}")
    return df


# ── Step 5: Normalise to monthly weights ───────────────────────────────────────

def normalise_weights(df_gpp: pd.DataFrame) -> pd.DataFrame:
    """
    For each NUTS2 region, divide monthly GPP by annual sum so weights
    sum to 1.0 across the 12 months.

    Regions with all-NaN (e.g. island regions with no land cover) receive
    uniform weights (1/12 each).
    """
    annual = df_gpp.sum(axis=1)
    weights = df_gpp.div(annual, axis=0)

    # Fill regions with no data with uniform weights
    uniform = pd.Series([1 / 12] * 12, index=df_gpp.columns)
    weights = weights.apply(
        lambda row: uniform if row.isna().all() else row, axis=1
    )
    assert np.allclose(weights.sum(axis=1).dropna(), 1.0, atol=1e-6), \
        "Weights do not sum to 1 for all regions!"
    return weights


# ── Step 6: Merge with annual rates ───────────────────────────────────────────

def compute_monthly_rates(
    weights: pd.DataFrame, rates_csv: Path
) -> pd.DataFrame:
    """
    Multiply monthly weights × annual MAI rate (tCO₂ ha⁻¹ yr⁻¹) to get
    monthly rates (tCO₂ ha⁻¹ month⁻¹) per NUTS2.

    If rates_csv is missing, returns only the weights.
    """
    if not rates_csv.exists():
        print(f"  Rates CSV not found at {rates_csv} — skipping monthly rates.")
        return None

    rates = pd.read_csv(rates_csv, index_col="nuts2")["mai_co2_mean"]
    rates.index.name = "NUTS_ID"

    # Align indices
    common = weights.index.intersection(rates.index)
    w = weights.loc[common]
    r = rates.loc[common]

    monthly_rates = w.mul(r, axis=0)
    monthly_rates.columns = MONTH_NAMES
    print(f"  Monthly rates computed for {len(common)} regions.")
    return monthly_rates


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # 1. Load data
    gpp = load_fluxcom_europe(args.gpp_dir)

    # 2. Monthly climatology
    print("Computing monthly climatology...")
    clim = monthly_climatology(gpp)

    # 3. NUTS2 polygons
    nuts = load_nuts2(args.nuts_url)

    # 4. Zonal statistics
    print("Computing zonal statistics per NUTS2...")
    df_gpp = zonal_mean_per_nuts2(clim, nuts)

    # 5. Normalise
    print("Normalising to monthly weights...")
    weights = normalise_weights(df_gpp)
    weights.columns = MONTH_NAMES

    # 6. Save weights
    out_weights = OUTPUT_DIR / "nuts2_monthly_weights.csv"
    weights.to_csv(out_weights)
    print(f"  Saved: {out_weights}")

    # 7. Compute and save monthly rates
    print("Computing monthly sequestration rates...")
    monthly_rates = compute_monthly_rates(
        weights.copy().rename(columns={n: i + 1 for i, n in enumerate(MONTH_NAMES)}),
        args.rates,
    )
    if monthly_rates is not None:
        out_rates = OUTPUT_DIR / "nuts2_monthly_rates.csv"
        monthly_rates.to_csv(out_rates)
        print(f"  Saved: {out_rates}")

    # 8. Quick sanity print
    print("\n── Sample output (weights for 5 regions) ──")
    print(weights.head())
    print("\n── Row sums (should all be 1.0) ──")
    print(weights.sum(axis=1).describe())


if __name__ == "__main__":
    main()
