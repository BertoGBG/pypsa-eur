# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""
Plot CDR diagnostic maps.

Figure 1 — 2×2 panels, one per CDR technology:
  choropleth = Levelized Cost of CDR gross [€/tCO₂] (excl. CO₂ credit)
  circles    = area ∝ e_nom_max (potential); colored fraction = co2_seq/e_nom_max
  shared Purples colorscale and circle-size scale across all four panels
  weighted LCCDR annotated in each panel

Figure 2 — composite CDR portfolio map:
  choropleth = co2_seq-weighted mean LCCDR across all active CDRs per node
  pie charts = CDR deployment mix (total area ∝ sum of potentials)
"""

from pathlib import Path
from types import SimpleNamespace

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Wedge

CO2_ATM_CARRIER = "co2"
CMAP = "Purples"

CDR_TECHS = [
    ("Afforestation",    "co2 afforestation"),
    ("Perennialisation", "co2 perennials"),
    ("Biochar",          "co2 biochar"),
    ("Rock Weathering",  "co2 rock weathering"),
]

MAX_RADIUS = 160_000  # metres in EqualEarth projection
# Nodes whose actual CO2 flow is below this fraction of their potential are
# treated as undeployed: lccdr_gross is set to NaN and shown white on the map.
MIN_DEPLOYMENT_FRAC = 1e-3


def load_projection(plotting_params):
    proj_kwargs = plotting_params.get("projection", {"name": "EqualEarth"}).copy()
    proj_func = getattr(ccrs, proj_kwargs.pop("name"))
    return proj_func(**proj_kwargs)


# ── data extraction ───────────────────────────────────────────────────────────

def compute_cdr_per_node(n, store_carrier):
    """
    Per-node CDR metrics. Returns DataFrame indexed by region name with:
      e_nom_max, e_nom_opt, co2_seq [tCO2], lccdr_gross [€/tCO2] (NaN if undeployed)
    """
    stores = n.stores[n.stores.carrier == store_carrier]
    links  = n.links[n.links.carrier == store_carrier]
    if stores.empty:
        return pd.DataFrame(columns=["e_nom_max", "e_nom_opt", "co2_seq", "lccdr_gross"])

    sw    = n.snapshot_weightings["stores"]
    mp    = getattr(n.buses_t, "marginal_price", None)
    p0_df = getattr(n.links_t, "p0", None)

    store_bus_to_link: dict = {}
    for lk_name, lk in links.iterrows():
        for i in range(5):
            bc = f"bus{i}"
            if bc not in links.columns:
                continue
            bus = lk.get(bc)
            if not isinstance(bus, str) or not bus or bus not in n.buses.index:
                continue
            if n.buses.at[bus, "carrier"] == store_carrier:
                store_bus_to_link[bus] = lk_name

    records = []
    for st_name, st in stores.iterrows():
        store_bus = st["bus"]
        if store_bus not in n.buses.index:
            continue
        node = n.buses.at[store_bus, "location"]
        if not isinstance(node, str) or not node:
            continue

        e_nom_max = float(st.get("e_nom_max", np.inf))
        if not np.isfinite(e_nom_max):
            e_nom_max = 0.0
        e_nom_opt = float(st.get("e_nom_opt", 0.0))

        co2_seq = 0.0
        if st_name in n.stores_t.p.columns:
            co2_seq = max(0.0, (-n.stores_t.p[st_name] * sw).sum())

        lccdr_gross = np.nan
        if co2_seq > 0 and mp is not None:
            lk_name = store_bus_to_link.get(store_bus)
            capex_n = st.get("capital_cost", 0.0) * e_nom_opt
            vom_n = bus_other_n = 0.0

            if lk_name is not None and lk_name in links.index:
                lk = links.loc[lk_name]
                capex_n += lk.get("capital_cost", 0.0) * lk.get("p_nom_opt", 0.0)

                if p0_df is not None and lk_name in p0_df.columns:
                    p0_t = p0_df[lk_name]
                    vom_n = (lk.get("marginal_cost", 0.0) * p0_t * sw).sum()

                    for i in range(5):
                        bc = f"bus{i}"
                        if bc not in links.columns:
                            continue
                        bus_name = lk.get(bc)
                        if not isinstance(bus_name, str) or not bus_name:
                            continue
                        if bus_name not in n.buses.index:
                            continue
                        bus_car = n.buses.at[bus_name, "carrier"]
                        if bus_car in (store_carrier, CO2_ATM_CARRIER):
                            continue
                        if bus_name not in mp.columns:
                            continue
                        price_t = mp[bus_name]
                        if i == 0:
                            p_i_t = p0_t
                        else:
                            p_i_df = getattr(n.links_t, f"p{i}", None)
                            if p_i_df is not None and lk_name in p_i_df.columns:
                                p_i_t = p_i_df[lk_name]
                            else:
                                eff_col = "efficiency" if i == 1 else f"efficiency{i}"
                                if eff_col not in links.columns:
                                    continue
                                eff = lk.get(eff_col, 0.0)
                                if eff == 0.0:
                                    continue
                                p_i_t = -eff * p0_t
                        bus_other_n += (price_t * p_i_t * sw).sum()

            lccdr_gross = (capex_n + vom_n + bus_other_n) / co2_seq
            # Null out LCCDR for essentially undeployed nodes (e.g. biochar with
            # epsilon capital_cost giving spurious e_nom_opt but near-zero dispatch).
            if e_nom_max > 0 and co2_seq / e_nom_max < MIN_DEPLOYMENT_FRAC:
                lccdr_gross = np.nan

        records.append(dict(
            node=node, e_nom_max=e_nom_max, e_nom_opt=e_nom_opt,
            co2_seq=co2_seq, lccdr_gross=lccdr_gross,
        ))

    if not records:
        return pd.DataFrame(columns=["e_nom_max", "e_nom_opt", "co2_seq", "lccdr_gross"])
    return pd.DataFrame(records).set_index("node")


def cdr_summary(df):
    """Return (e_nom_opt-weighted mean LCCDR gross, total co2_seq in MtCO2)."""
    total_seq = df["co2_seq"].sum() / 1e6
    mask = df["lccdr_gross"].notna() & (df["e_nom_opt"] > 0)
    if mask.any():
        w = df.loc[mask, "e_nom_opt"]
        wlccdr = (df.loc[mask, "lccdr_gross"] * w).sum() / w.sum()
    else:
        wlccdr = np.nan
    return wlccdr, total_seq


# ── geometry ──────────────────────────────────────────────────────────────────

def node_xy(n, nodes, crs):
    lons = n.buses.loc[nodes, "x"].values.astype(float)
    lats = n.buses.loc[nodes, "y"].values.astype(float)
    pts  = crs.transform_points(ccrs.PlateCarree(), lons, lats)
    return pts[:, 0], pts[:, 1]


# ── drawing ───────────────────────────────────────────────────────────────────

def draw_split_circles(ax, df, n, crs, color, max_potential, zorder=5):
    """
    Grey circle (area ∝ e_nom_max) with a colored wedge (fraction = co2_seq/e_nom_max).
    Using co2_seq avoids showing spurious e_nom_opt allocations from epsilon capital costs.
    """
    valid = [nd for nd in df.index if nd in n.buses.index and df.at[nd, "e_nom_max"] > 0]
    if not valid:
        return
    xs, ys = node_xy(n, valid, crs)
    for x, y, nd in zip(xs, ys, valid):
        row = df.loc[nd]
        r = MAX_RADIUS * np.sqrt(row["e_nom_max"] / max_potential)
        ax.add_patch(Circle(
            (x, y), r, facecolor="lightgrey", edgecolor="grey",
            linewidth=0.3, zorder=zorder,
        ))
        frac = float(np.clip(row["co2_seq"] / row["e_nom_max"], 0, 1))
        if frac > 1e-4:
            ax.add_patch(Wedge(
                (x, y), r, 90 - frac * 360, 90,
                facecolor=color, linewidth=0, zorder=zorder + 1,
            ))


def draw_pie_charts(ax, cdr_data, carriers_order, n, crs, colors, max_total, zorder=5):
    all_nodes = sorted({nd for df in cdr_data.values() for nd in df.index
                        if nd in n.buses.index})
    if not all_nodes:
        return
    xs, ys = node_xy(n, all_nodes, crs)
    for x, y, node in zip(xs, ys, all_nodes):
        total_max = sum(
            cdr_data[c].at[node, "e_nom_max"] if node in cdr_data[c].index else 0.0
            for c in carriers_order
        )
        if total_max <= 0:
            continue
        r = MAX_RADIUS * np.sqrt(total_max / max_total)
        ax.add_patch(Circle(
            (x, y), r, facecolor="lightgrey", edgecolor="grey",
            linewidth=0.3, zorder=zorder,
        ))
        angle = 90.0
        for carrier in carriers_order:
            df = cdr_data[carrier]
            if node not in df.index:
                continue
            co2 = float(df.at[node, "co2_seq"])
            if co2 <= 0:
                continue
            frac = co2 / total_max
            ax.add_patch(Wedge(
                (x, y), r, angle - frac * 360, angle,
                facecolor=colors[carrier], linewidth=0, zorder=zorder + 1,
            ))
            angle -= frac * 360


# ── map background + choropleth ───────────────────────────────────────────────

def setup_ax(ax, regions, column, crs, boundaries, vmin, vmax):
    ax.set_extent(boundaries, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN, facecolor="white", zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="darkgrey", zorder=3)
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor="grey", zorder=3)
    regions.to_crs(crs.proj4_init).plot(
        ax=ax, column=column, cmap=CMAP,
        vmin=vmin, vmax=vmax,
        missing_kwds={"color": "white"},
        edgecolor="none", linewidth=0, zorder=2,
    )


# ── legend panel helpers ──────────────────────────────────────────────────────

def fill_legend_panel(ax_leg, colors, max_potential):
    """Draw CDR tech color patches + circle size reference in the legend axis."""
    ax_leg.set_xlim(0, 1)
    ax_leg.set_ylim(0, 1)
    ax_leg.axis("off")

    # CDR colour legend
    ax_leg.text(0.05, 0.98, "CDR technology", fontsize=9, fontweight="bold", va="top")
    tech_y = 0.91
    for lbl, carrier in CDR_TECHS:
        ax_leg.add_patch(mpatches.FancyBboxPatch(
            (0.05, tech_y - 0.025), 0.12, 0.05,
            boxstyle="round,pad=0.01", facecolor=colors[carrier], linewidth=0,
            transform=ax_leg.transAxes, clip_on=False,
        ))
        ax_leg.text(0.21, tech_y, lbl, fontsize=8, va="center",
                    transform=ax_leg.transAxes)
        tech_y -= 0.09

    ax_leg.add_patch(mpatches.FancyBboxPatch(
        (0.05, tech_y - 0.025), 0.12, 0.05,
        boxstyle="round,pad=0.01", facecolor="lightgrey",
        edgecolor="grey", linewidth=0.5,
        transform=ax_leg.transAxes, clip_on=False,
    ))
    ax_leg.text(0.21, tech_y, "Unused potential", fontsize=8, va="center",
                transform=ax_leg.transAxes)

    # Circle size legend
    size_y0 = tech_y - 0.12
    ax_leg.text(0.05, size_y0, "Potential (MtCO₂/yr)", fontsize=9,
                fontweight="bold", va="top", transform=ax_leg.transAxes)
    ref_fracs = [1.0, 0.5, 0.25]
    y_cursor = size_y0 - 0.06
    for frac in ref_fracs:
        val = frac * max_potential / 1e6
        marker_size = 12 * np.sqrt(frac)
        ax_leg.plot(
            0.15, y_cursor, "o", markersize=marker_size,
            markerfacecolor="none", markeredgecolor="grey", markeredgewidth=0.8,
            transform=ax_leg.transAxes,
        )
        ax_leg.text(0.28, y_cursor, f"{val:.0f}", fontsize=8, va="center",
                    transform=ax_leg.transAxes)
        y_cursor -= 0.07 + 0.03 * np.sqrt(frac)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "snakemake" not in globals():
        import argparse
        import yaml

        parser = argparse.ArgumentParser(description="Plot CDR diagnostic maps.")
        parser.add_argument("--network", required=True,
                            help="Path to optimised network .nc file")
        parser.add_argument("--regions", default=None,
                            help="Path to regions GeoJSON (auto-derived if omitted)")
        parser.add_argument("--out-fig1", default=None,
                            help="Output PDF for Figure 1")
        parser.add_argument("--out-fig2", default=None,
                            help="Output PDF for Figure 2")
        parser.add_argument("--plotting-config",
                            default="config/plotting.default.yaml",
                            help="Path to plotting config YAML")
        args = parser.parse_args()

        net_path  = Path(args.network)
        maps_dir  = net_path.parent.parent / "maps" / "static"
        run_name  = net_path.parent.parent.name
        clusters  = net_path.stem.split("_")[2]

        regions_path = Path(args.regions) if args.regions else (
            Path("resources") / run_name / f"regions_onshore_base_s_{clusters}.geojson"
        )

        with open(args.plotting_config) as _f:
            _plotting = yaml.safe_load(_f)["plotting"]

        snakemake = SimpleNamespace(
            input=SimpleNamespace(
                network=str(net_path),
                regions=str(regions_path),
            ),
            output=[
                args.out_fig1 or str(maps_dir / "CDR_costs_map.pdf"),
                args.out_fig2 or str(maps_dir / "CDR_portfolio_map.pdf"),
            ],
            params=SimpleNamespace(plotting=_plotting),
        )
    else:
        from scripts._helpers import (
            configure_logging,
            set_scenario_config,
            update_config_from_wildcards,
        )
        configure_logging(snakemake)
        set_scenario_config(snakemake)
        update_config_from_wildcards(snakemake.config, snakemake.wildcards)

    # ── load network + config ─────────────────────────────────────────────────
    n = pypsa.Network(snakemake.input.network)
    regions = gpd.read_file(snakemake.input.regions).set_index("name")
    plotting = snakemake.params.plotting
    crs = load_projection(plotting)
    boundaries = plotting["map"]["boundaries"]
    tech_colors = plotting["tech_colors"]

    # fix bus coordinates (CDR buses → inherit spatial node lon/lat)
    eu_loc = plotting.get("eu_node_location", {"x": -5.5, "y": 46.0})
    if "EU" in n.buses.index:
        n.buses.loc["EU", ["x", "y"]] = eu_loc["x"], eu_loc["y"]
    n.buses["location"] = n.buses["location"].replace("", "EU").fillna("EU")
    _x0 = n.buses["x"].copy()
    _y0 = n.buses["y"].copy()
    n.buses["x"] = n.buses.location.map(_x0).fillna(_x0)
    n.buses["y"] = n.buses.location.map(_y0).fillna(_y0)

    plt.rcParams.update({"font.size": 9, "axes.titlesize": 11})

    # ── compute per-node data ─────────────────────────────────────────────────
    carriers_order = [c for _, c in CDR_TECHS]
    cdr_data  = {c: compute_cdr_per_node(n, c) for c in carriers_order}
    colors    = {c: tech_colors.get(c, "steelblue") for c in carriers_order}
    summaries = {c: cdr_summary(df) for c, df in cdr_data.items()}

    max_potential = max(
        (df["e_nom_max"].max() if not df.empty else 0.0)
        for df in cdr_data.values()
    )
    all_lccdr = pd.concat([
        df["lccdr_gross"].dropna() for df in cdr_data.values() if not df.empty
    ]) if any(not df.empty for df in cdr_data.values()) else pd.Series(dtype=float)
    lccdr_max = float(all_lccdr.max()) if not all_lccdr.empty else 1000.0

    # ── Figure 1: 2×2 panels + right legend strip ─────────────────────────────
    fig1 = plt.figure(figsize=(17, 12), layout="constrained")
    gs1  = fig1.add_gridspec(2, 3, width_ratios=[1, 1, 0.22], wspace=0.04, hspace=0.08)

    map_axes = [
        [fig1.add_subplot(gs1[0, 0], projection=crs),
         fig1.add_subplot(gs1[0, 1], projection=crs)],
        [fig1.add_subplot(gs1[1, 0], projection=crs),
         fig1.add_subplot(gs1[1, 1], projection=crs)],
    ]
    ax_leg1 = fig1.add_subplot(gs1[:, 2])

    for (label, carrier), ax in zip(CDR_TECHS, [map_axes[r][c]
                                                 for r in range(2) for c in range(2)]):
        df = cdr_data[carrier]
        reg = regions.copy()
        reg["lccdr"] = df["lccdr_gross"].reindex(reg.index) if not df.empty else np.nan

        setup_ax(ax, reg, "lccdr", crs, boundaries, vmin=0, vmax=lccdr_max)

        wlccdr, co2_mt = summaries[carrier]
        title_str = label
        ax.set_title(title_str, fontsize=11, fontweight="bold", pad=4)

        if not df.empty and max_potential > 0:
            draw_split_circles(ax, df, n, crs, colors[carrier], max_potential)

        # per-panel annotation
        if np.isfinite(wlccdr):
            ann = f"LCCDR: {wlccdr:+.0f} €/tCO₂\nCO₂ removed: {co2_mt:.1f} MtCO₂/yr"
        else:
            ann = f"LCCDR: n/a\nCO₂ removed: {co2_mt:.1f} MtCO₂/yr"
        ax.text(
            0.97, 0.03, ann, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.5,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="lightgrey",
                      boxstyle="round,pad=0.3"),
            zorder=10,
        )

    # shared colorbar below map columns only
    sm1 = plt.cm.ScalarMappable(
        cmap=CMAP, norm=plt.Normalize(vmin=0, vmax=lccdr_max)
    )
    all_map_axes = [map_axes[r][c] for r in range(2) for c in range(2)]
    cb1 = fig1.colorbar(
        sm1, ax=all_map_axes,
        label="Levelized Cost of CDR  [€/tCO₂]  (excl. CO₂ credit)",
        orientation="horizontal", shrink=0.7, pad=0.02, aspect=40,
    )
    cb1.outline.set_edgecolor("none")

    fill_legend_panel(ax_leg1, colors, max_potential)

    Path(snakemake.output[0]).parent.mkdir(parents=True, exist_ok=True)
    fig1.savefig(snakemake.output[0], dpi=150, bbox_inches="tight")
    plt.close(fig1)
    print(f"Saved Figure 1 → {snakemake.output[0]}")

    # ── Figure 2: composite map + right legend strip ──────────────────────────
    all_nodes = sorted({nd for df in cdr_data.values() for nd in df.index})
    wnum = pd.Series(0.0, index=all_nodes)
    wden = pd.Series(0.0, index=all_nodes)
    for carrier, df in cdr_data.items():
        for nd in df.index:
            if nd not in wnum.index:
                continue
            lcc   = df.at[nd, "lccdr_gross"]
            co2   = df.at[nd, "co2_seq"]
            if np.isfinite(lcc) and co2 > 0:
                wnum[nd] += lcc * co2
                wden[nd]  += co2
    wlccdr_map = (wnum / wden.replace(0.0, np.nan)).reindex(regions.index)

    max_total = max(
        (sum(cdr_data[c].at[nd, "e_nom_max"] if nd in cdr_data[c].index else 0.0
             for c in carriers_order)
         for nd in all_nodes),
        default=1.0,
    )

    fig2 = plt.figure(figsize=(13, 10), layout="constrained")
    gs2  = fig2.add_gridspec(1, 2, width_ratios=[1, 0.22], wspace=0.04)
    ax2      = fig2.add_subplot(gs2[0, 0], projection=crs)
    ax_leg2  = fig2.add_subplot(gs2[0, 1])

    reg2 = regions.copy()
    reg2["wlccdr"] = wlccdr_map
    setup_ax(ax2, reg2, "wlccdr", crs, boundaries, vmin=0, vmax=lccdr_max)
    ax2.set_title(
        "CDR portfolio — deployment mix and weighted LCCDR per node",
        fontsize=11, fontweight="bold", pad=4,
    )

    draw_pie_charts(ax2, cdr_data, carriers_order, n, crs, colors, max_total)

    sm2 = plt.cm.ScalarMappable(
        cmap=CMAP, norm=plt.Normalize(vmin=0, vmax=lccdr_max)
    )
    cb2 = fig2.colorbar(
        sm2, ax=ax2,
        label="Weighted LCCDR  [€/tCO₂]  (excl. CO₂ credit)",
        orientation="horizontal", shrink=0.9, pad=0.02, aspect=40,
    )
    cb2.outline.set_edgecolor("none")

    fill_legend_panel(ax_leg2, colors, max_total)

    fig2.savefig(snakemake.output[1], dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved Figure 2 → {snakemake.output[1]}")
