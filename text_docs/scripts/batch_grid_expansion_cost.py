"""
Annualised cost of grid expansion per run and horizon (bn EUR/yr), for the
batch summary: power (AC lines + DC links, expansion beyond the existing
grid only), H2 pipelines (new + retrofitted) and CO2 pipelines.

Cost = capital_cost x (optimal - existing) capacity, summed over all
vintages present in the horizon, i.e. what the grid adds to that year's
total system cost. Cumulative = sum over horizons x 5 years (undiscounted),
same convention as the cumulative total system cost.

Usage: python batch_grid_expansion_cost.py <run> <out.csv>
       (reads results/<run>/networks/base_s_50__1095seg_<year>.nc)
"""

import sys
from pathlib import Path

import pandas as pd
import pypsa

run, out = sys.argv[1], Path(sys.argv[2])
rows = []
for path in sorted(Path(f"results/{run}/networks").glob("base_s_50__1095seg_*.nc")):
    year = int(path.stem[-4:])
    n = pypsa.Network(str(path))
    lines = n.lines
    ac = (lines.capital_cost * (lines.s_nom_opt - lines.s_nom).clip(lower=0)).sum()
    links = n.links
    dc = links[links.carrier == "DC"]
    dc = (dc.capital_cost * (dc.p_nom_opt - dc.p_nom).clip(lower=0)).sum()
    h2 = links[links.carrier.isin(["H2 pipeline", "H2 pipeline retrofitted"])]
    h2 = (h2.capital_cost * h2.p_nom_opt).sum()
    co2 = links[links.carrier == "CO2 pipeline"]
    co2 = (co2.capital_cost * co2.p_nom_opt).sum()
    rows.append({"run": run, "year": year, "power (AC+DC)": (ac + dc) / 1e9,
                 "H2 pipelines": h2 / 1e9, "CO2 pipelines": co2 / 1e9})
    print(rows[-1], flush=True)

pd.DataFrame(rows).to_csv(out, index=False)
