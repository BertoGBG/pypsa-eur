"""
Balance map of the CO2 atmosphere, in the style of PyPSA-Eur's balance_map
(e.g. balance_map_co2_stored), but for the single "co2 atmosphere" bus.

    python text_docs/scripts/co2_atmosphere_map.py <network.nc> <regions_onshore.geojson> <out.png> <label>

The atmosphere has no location, so every link's atmospheric flow is assigned
to the node of the link (the same technology-by-node flows as the market
curves of co2_market_curves.py, so map and curves always agree):
  - split circle per node: upper half = emissions (warm colours), lower half =
    removals (cool colours), slices by technology, area ~ MtCO2/yr;
  - regions coloured by the node's NET atmospheric balance (emissions minus
    removals, MtCO2/yr): red = net emitter, blue = net remover;
  - links without a node (EU-level fuels such as kerosene) sit on the "EU"
    point from plotting.eu_node_location, as in PyPSA-Eur's balance maps.
The CO2 price is read from the atmosphere bus in every snapshot (it is uniform
when the CO2 limit binds) and reported in the title.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
import yaml
from matplotlib.colors import TwoSlopeNorm
from pypsa.plot import add_legend_patches, add_legend_semicircles

from co2_market_curves import break_even_table, official_colour
from scripts.plot_power_network import load_projection

BUS_FACTOR = 0.008  # PyPSA's co2 stored map uses 0.015 for flows about half this size
LEGEND_SIZES = [100, 25]  # MtCO2/yr
SEMICIRCLE_CORRECTION_FACTOR = 2  # as in scripts/plot_balance_map.py


def side_totals(flows, sign):
    """Mt per carrier on one side (emissions sign=+1, removals sign=-1), largest first."""
    return flows[flows * sign > 0].abs().groupby(level="carrier").sum().sort_values(ascending=False)


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    path, regions_path, out_path, label = sys.argv[1:5]
    with open(REPO / "config" / "plotting.default.yaml") as f:
        plotting = yaml.safe_load(f)["plotting"]

    n = pypsa.Network(path)
    regions = gpd.read_file(regions_path).set_index("name")

    atm = n.buses.index[n.buses.carrier == "co2"]
    w = n.snapshot_weightings.generators
    atm_price = n.buses_t.marginal_price[atm]
    co2_price = -float((atm_price.mul(w, axis=0).sum() / w.sum()).mean())
    spread = float(atm_price.values.max() - atm_price.values.min())

    A = break_even_table(n, "co2")
    A["node"] = A["node"].where(A["node"].isin(regions.index), "EU")
    flows = A.groupby(["node", "carrier"]).q.sum() / 1e6  # Mt into the atmosphere: + emit, - remove
    flows = flows[flows.abs() > 1e-3]
    flows.index = flows.index.set_names(["bus", "carrier"])

    # official PyPSA-Eur colours, identical to the costs plot and the market curves
    emit_tot, rem_tot = side_totals(flows, 1), side_totals(flows, -1)
    carrier_colour = {c: official_colour(c) for c in flows.index.unique("carrier")}

    # locate the nodes on the map; EU-level flows on the configured EU point
    eu = plotting["eu_node_location"]
    if "EU" not in n.buses.index:
        n.add("Bus", "EU", x=eu["x"], y=eu["y"])
    else:
        n.buses.loc["EU", ["x", "y"]] = eu["x"], eu["y"]

    net = flows.groupby(level="bus").sum()
    regions["net"] = net.reindex(regions.index).fillna(0.0)

    crs = load_projection(plotting)
    fig, ax = plt.subplots(figsize=(7, 8.5), subplot_kw={"projection": crs}, layout="constrained")
    n.plot(
        bus_size=flows * BUS_FACTOR,
        bus_color=pd.Series(carrier_colour),
        bus_split_circle=True,
        line_width=0,
        link_width=0,
        transformer_width=0,
        ax=ax,
        margin=0.2,
        geomap_color={"border": "darkgrey", "coastline": "darkgrey"},
        geomap=True,
        boundaries=plotting["map"]["boundaries"],
    )
    lim = max(abs(regions.net.min()), abs(regions.net.max()), 1e-3)
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    regions.to_crs(crs.proj4_init).plot(ax=ax, column="net", cmap="RdBu_r", norm=norm, edgecolor="None", linewidth=0)

    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=norm)
    cbr = fig.colorbar(sm, ax=ax, label="Net atmospheric balance [MtCO2/yr]  (red: net emitter, blue: net remover)",
                       shrink=0.95, pad=0.03, aspect=50, orientation="horizontal")
    cbr.outline.set_edgecolor("None")

    total_e = flows[flows > 0].sum()
    total_r = -flows[flows < 0].sum()
    price_note = f"{co2_price:.0f} €/t" + ("" if spread < 0.5 else f" (varies by {spread:.0f} €/t over time)")
    ax.set_title(f"CO2 atmosphere — {label}\nemitted {total_e:.0f} Mt, removed {total_r:.0f} Mt, net {total_e - total_r:.0f} Mt; "
                 f"CO2 price {price_note}", fontsize=10)

    legend_kw = {"loc": "upper left", "frameon": False, "alignment": "left", "title_fontproperties": {"weight": "bold"}}
    pad = 0.2
    emit_labels = [f"{c} ({emit_tot[c]:.0f} Mt)" for c in emit_tot.index]
    rem_labels = [f"{c} ({rem_tot[c]:.0f} Mt)" for c in rem_tot.index]
    small = {"loc": "upper left", "frameon": False, "alignment": "left", "fontsize": 7,
             "title_fontproperties": {"weight": "bold"}}
    add_legend_patches(ax, [carrier_colour[c] for c in emit_tot.index], emit_labels,
                       legend_kw={"bbox_to_anchor": (0, -pad), "ncol": 1, "title": "Emissions (upper half)", **small})
    add_legend_patches(ax, [carrier_colour[c] for c in rem_tot.index], rem_labels,
                       legend_kw={"bbox_to_anchor": (0.52, -pad), "ncol": 1, "title": "Removals (lower half)", **small})
    add_legend_semicircles(ax, [s * BUS_FACTOR * SEMICIRCLE_CORRECTION_FACTOR for s in LEGEND_SIZES],
                           [f"{s} Mt" for s in LEGEND_SIZES], patch_kw={"color": "#666"},
                           legend_kw={"bbox_to_anchor": (0, 1), **legend_kw})
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"emitted {total_e:.1f} Mt, removed {total_r:.1f} Mt, net {total_e - total_r:.1f} Mt; "
          f"EU-level node: {flows.get('EU', pd.Series(dtype=float)).sum():.1f} Mt net; CO2 price {co2_price:.1f} €/t "
          f"(time spread {spread:.2f})")
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
