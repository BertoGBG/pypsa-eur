"""
Download FluxCom monthly GPP data for Europe.

FluxCom (Jung et al. 2020, Biogeosciences) provides machine-learning upscaled
GPP from FLUXNET eddy-covariance towers at 0.5° resolution, monthly timestep.

Dataset: RS (remote sensing) ensemble, GPP variable
  - Unit: gC m⁻² day⁻¹
  - Resolution: 0.5° × 0.5°, monthly, global
  - Period: 2001–2015 (RS version)

Registration required at: http://www.fluxcom.org/CF-Download/
After registering you receive credentials for the THREDDS/HTTP server.

Reference:
  Jung, M. et al. (2020). Scaling carbon fluxes from eddy covariance sites to
  globe: synthesis and evaluation of the FLUX COM approach.
  Biogeosciences, 17(5), 1343–1365. https://doi.org/10.5194/bg-17-1343-2020

Usage:
    # Set your credentials as environment variables first:
    export FLUXCOM_USER="your_username"
    export FLUXCOM_PASS="your_password"

    python 01_download_fluxcom.py

    # Or run in test mode with a single year (no credentials needed if using
    # the public TRENDY mirror — see NOTE below):
    python 01_download_fluxcom.py --test

NOTE on public access:
    FluxCom RS GPP is also mirrored on the ICOS Carbon Portal and can be
    accessed via the ESA CCI Land Cover portal. If you have access to the
    full dataset, set YEARS to the full 2001–2015 range. For a seasonal
    climatology, any 5+ year subset is sufficient.

    Alternatively, the FluxCom data can be obtained via:
    https://doi.org/10.17871/FluxCom-RS-v006 (requires registration)
"""

import os
import sys
import argparse
from pathlib import Path

import requests
import numpy as np

# ── Configuration ─────────────────────────────────────────────────────────────

# Years to download (2001–2015 for RS ensemble)
# For a test or climatology purpose, 5 years is enough
YEARS = list(range(2008, 2013))  # 5-year subset by default

# FluxCom RS ensemble base URL (after login)
# Files follow the pattern: GPP.RS_V006.FP-ALL.MLM-ALL.METEO-NONE.720_360.monthly.YYYY.nc
BASE_URL = (
    "http://www.fluxcom.org/CF-Download/RS_V006/"
    "GPP.RS_V006.FP-ALL.MLM-ALL.METEO-NONE.720_360.monthly.{year}.nc"
)

OUTPUT_DIR = Path(__file__).parent / "data" / "fluxcom_raw"

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Download FluxCom monthly GPP")
    p.add_argument(
        "--test",
        action="store_true",
        help="Download only the first year (quick smoke test)",
    )
    p.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=YEARS,
        help="Years to download (default: 2008–2012)",
    )
    return p.parse_args()


# ── Download ──────────────────────────────────────────────────────────────────

def download_year(year: int, user: str, password: str) -> Path:
    url = BASE_URL.format(year=year)
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"GPP_fluxcom_monthly_{year}.nc"

    if out_path.exists():
        print(f"  {year}: already downloaded, skipping.")
        return out_path

    print(f"  {year}: downloading from {url} ...")
    resp = requests.get(url, auth=(user, password), stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = 100 * downloaded / total
                print(f"\r    {pct:.1f}%", end="", flush=True)
    print()
    return out_path


def main():
    args = parse_args()
    years = args.years[:1] if args.test else args.years

    user = os.environ.get("FLUXCOM_USER", "")
    password = os.environ.get("FLUXCOM_PASS", "")

    if not user or not password:
        print(
            "ERROR: set FLUXCOM_USER and FLUXCOM_PASS environment variables.\n"
            "Register at http://www.fluxcom.org/CF-Download/ to get credentials.\n"
            "\n"
            "If you already have the files, place them in:\n"
            f"  {OUTPUT_DIR}/\n"
            "named as: GPP_fluxcom_monthly_YYYY.nc\n"
            "Then run 02_compute_nuts2_profiles.py directly."
        )
        sys.exit(1)

    print(f"Downloading FluxCom GPP for years: {years}")
    for year in years:
        download_year(year, user, password)

    print(f"\nDone. Files saved to: {OUTPUT_DIR}")
    print("Next step: run 02_compute_nuts2_profiles.py")


if __name__ == "__main__":
    main()
