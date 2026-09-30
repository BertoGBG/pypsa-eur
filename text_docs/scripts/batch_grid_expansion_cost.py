"""
Overnight investment in grid expansion per run and horizon (bn EUR), for the
batch summary: power (AC lines + DC links), H2 pipelines (new + retrofitted)
and CO2 pipelines. Only capacity newly built in that horizon counts:

- AC lines / DC links are single components whose capacity grows over the
  horizons: new = s_nom_opt - max(s_nom, s_nom_min) (s_nom = existing grid,
  s_nom_min = capacity built up to the previous horizon).
- H2 / CO2 pipelines are added as a new extendable vintage every horizon:
  new = p_nom_opt of the extendable links.

Investment = new capacity x capital_cost / k, where k = annuity(7 %,
lifetime) + FOM turns the annualised capital_cost back into the overnight
investment of technology-data (checked against costs_{year}_processed.csv):
AC 0.0900 (40 y, FOM 1.5 %); DC 0.0900 overhead/converters, 0.1000 submarine
(FOM 2.5 %), blended by the submarine share of the link's cost; CO2 pipeline
0.0815 onshore (50 y, FOM 0.9 %), 0.0908 submarine; H2 pipeline 50 y + the
year's FOM (3.58 % in 2025 falling to 1.5 % in 2050).
Cumulative = sum over horizons (undiscounted).

Usage: python batch_grid_expansion_cost.py <run> <out.csv>
       (reads results/<run>/networks/base_s_50__1095seg_<year>.nc)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

R = 0.07


def annuity(lifetime, r=R):
    return r / (1 - (1 + r) ** -lifetime)


H2_FOM = {2025: 3.5833, 2030: 3.1667, 2035: 2.75, 2040: 2.3333, 2045: 1.9167, 2050: 1.5}


def uw(df):
    return df["underwater_fraction"].fillna(0) if "underwater_fraction" in df else pd.Series(0.0, df.index)


run, out = sys.argv[1], Path(sys.argv[2])
rows = []
for path in sorted(Path(f"results/{run}/networks").glob("base_s_50__1095seg_*.nc")):
    year = int(path.stem[-4:])
    n = pypsa.Network(str(path))

    l = n.lines
    new_ac = (l.s_nom_opt - np.maximum(l.s_nom, l.s_nom_min)).clip(lower=0)
    inv_ac = (new_ac * l.capital_cost / 0.0900).sum()

    d = n.links[n.links.carrier == "DC"]
    new_dc = (d.p_nom_opt - np.maximum(d.p_nom, d.p_nom_min)).clip(lower=0)
    u = uw(d)
    sub_share = u * 322.0 / ((1 - u) * 54.0 + u * 322.0)  # submarine share of the per-km cost
    k_dc = 0.0900 * (1 - sub_share) + 0.1000 * sub_share
    inv_dc = (new_dc * d.capital_cost / k_dc).sum()

    h2 = n.links[n.links.carrier.isin(["H2 pipeline", "H2 pipeline retrofitted"]) & n.links.p_nom_extendable]
    k_h2 = annuity(50) + H2_FOM[year] / 100
    inv_h2 = (h2.p_nom_opt * h2.capital_cost / k_h2).sum()

    co2 = n.links[(n.links.carrier == "CO2 pipeline") & n.links.p_nom_extendable]
    u = uw(co2)
    sub_share = u * 485.2 / ((1 - u) * 217.6 + u * 485.2)
    k_co2 = 0.0815 * (1 - sub_share) + 0.0908 * sub_share
    inv_co2 = (co2.p_nom_opt * co2.capital_cost / k_co2).sum()

    rows.append({"run": run, "year": year,
                 "AC new [TW km]": (new_ac * l.length).sum() / 1e6,
                 "DC new [TW km]": (new_dc * d.length).sum() / 1e6,
                 "power (AC+DC)": (inv_ac + inv_dc) / 1e9,
                 "H2 pipelines": inv_h2 / 1e9, "CO2 pipelines": inv_co2 / 1e9})
    print(rows[-1], flush=True)

pd.DataFrame(rows).to_csv(out, index=False)
