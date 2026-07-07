# SPDX-FileCopyrightText: Contributors to PyPSA-Eur <https://github.com/pypsa/pypsa-eur>
# SPDX-License-Identifier: MIT
"""
Plot CDR diagnostic maps.

Figure 1 — 2×2 panels, one per CDR technology:
  choropleth = Levelized Cost of CDR (gross cost, excl. CO2 credit) [€/tCO2]
  circles    = split: colored = e_nom_opt deployed, grey = unused potential (e_nom_max)
  shared colorscale and circle-size scale across all four panels.

Figure 2 — composite CDR portfolio map:
  choropleth = e_nom_opt-weighted mean LCCDR across all active CDRs at each node
  pie charts = CDR deployment mix per node (total area ∝ sum of potentials)
"""

from pathlib import Path
from types import SimpleNamespace

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Wedge

CO2_ATM_CARRIER = "co2"

CDR_TECHS = [
    ("Afforestation",    "co2 afforestation"),
    ("Perennialisation", "co2 perennials"),
    ("Biochar",          "co2 biochar"),
    ("Rock Weathering",  "co2 rock weathering"),
]

# Maximum circle radius in EqualEarth projection units (metres)
MAX_RADIUS = 160_000


# ── data extraction ───────────────────────────────────────────────────────────

def compute_cdr_per_node(n, store_carrier):
    """
    Per-node CDR metrics for one technology.

    Returns DataFrame indexed by region name (e.g. 'DE0') with columns:
      e_nom_max   — available potential [tCO2/yr]
      e_nom_opt   — deployed capacity   [tCO2/yr]
      co2_seq     — actual sequestration in the optimised year [tCO2]
      lccdr_gross — gross LCCDR excl. CO2 atmospheric credit [€/tCO2],
                    NaN for undeployed nodes
    """
    stores = n.stores[n.stores.carrier == store_carrier]
    links  = n.links[n.links.carrier == store_carrier]
    if stores.empty:
        return pd.DataFrame(columns=["e_nom_max", "e_nom_opt", "co2_seq", "lccdr_gross"])

    sw    = n.snapshot_weightings["stores"]
    mp    = getattr(n.buses_t, "marginal_price", None)
    p0_df = getattr(n.links_t, "p0", None)

    # CDR store bus → link name (link whose output bus has carrier == store_carrier)
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

        # LCCDR gross = Capex + VOM + other bus costs (excluding CO2 atmosphere credit)
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
                            continue  # skip CDR store bus and CO2 atmosphere (credit)
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

        records.append(dict(
            node=node, e_nom_max=e_nom_max, e_nom_opt=e_nom_opt,
            co2_seq=co2_seq, lccdr_gross=lccdr_gross,
        ))

    if not records:
        return pd.DataFrame(columns=["e_nom_max", "e_nom_opt", "co2_seq", "lccdr_gross"])
    return pd.DataFrame(records).set_index("node")


# ── geometry helpers ──────────────────────────────────────────────────────────

def node_xy(n, nodes, crs):
    """Return projected (x, y) arrays for a list of region-node names."""
    lons = n.buses.loc[nodes, "x"].values.astype(float)
    lats = n.buses.loc[nodes, "y"].values.astype(float)
    pts  = crs.transform_points(ccrs.PlateCarree(), lons, lats)
    return pts[:, 0], pts[:, 1]


# ── circle / wedge drawing ────────────────────────────────────────────────────

def draw_split_circles(ax, df, n, crs, color, max_potential, zorder=5):
    """
    For each node: grey circle (full potential), colored wedge (deployed fraction).
    Circle area ∝ e_nom_max; shared max_potential scale across panels.
    """
    valid = [nd for nd in df.index if nd in n.buses.index and df.at[nd, "e_nom_max"] > 0]
    if not valid:
        return
    xs, ys = node_xy(n, valid, crs)
    for x, y, nd in zip(xs, ys, valid):
        row = df.loc[nd]
        r = MAX_RADIUS * np.sqrt(row["e_nom_max"] / max_potential)
        ax.add_patch(Circle(
            (x, y), r, color="lightgrey", zorder=zorder,
            linewidth=0.3, edgecolor="grey",
        ))
        frac = float(np.clip(row["e_nom_opt"] / row["e_nom_max"], 0, 1))
        if frac > 1e-4:
            # wedge from 90° (top) clockwise by frac×360°
            ax.add_patch(Wedge(
                (x, y), r, 90 - frac * 360, 90,
                color=color, zorder=zorder + 1, linewidth=0,
            ))


def draw_pie_charts(ax, cdr_data, carriers_order, n, crs, colors, max_total, zorder=5):
    """
    Pie chart per node: total area ∝ sum(e_nom_max) across CDRs.
    Slices = deployed fraction per CDR; grey remainder = unused potential.
    """
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
            (x, y), r, color="lightgrey", zorder=zorder,
            linewidth=0.3, edgecolor="grey",
        ))
        angle = 90.0  # start at top, go clockwise
        for carrier in carriers_order:
            df = cdr_data[carrier]
            if node not in df.index:
                continue
            e_opt = float(df.at[node, "e_nom_opt"])
            if e_opt <= 0:
                continue
            frac = e_opt / total_max
            ax.add_patch(Wedge(
                (x, y), r, angle - frac * 360, angle,
                color=colors[carrier], zorder=zorder + 1, linewidth=0,
            ))
            angle -= frac * 360


# ── map background ────────────────────────────────────────────────────────────

def setup_ax(ax, regions, column, crs, boundaries, vmin, vmax, cmap="YlOrRd"):
    ax.set_extent(boundaries, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN, facecolor="white", zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.4, edgecolor="darkgrey", zorder=1)
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor="grey", zorder=1)
    reg = regions.copy()
    reg[column] = regions[column]
    reg.to_crs(crs.proj4_init).plot(
        ax=ax, column=column, cmap=cmap,
        vmin=vmin, vmax=vmax,
        missing_kwds={"color": "white"},
        edgecolor="white", linewidth=0.2, zorder=2,
    )


# ── size legend ───────────────────────────────────────────────────────────────

def add_size_legend(ax, max_potential, ref_fracs=(0.25, 0.5, 1.0)):
    """Add a small inset showing reference circle sizes (in MtCO2/yr)."""
    handles, labels = [], []
    for frac in sorted(ref_fracs, reverse=True):
        val_mt = frac * max_potential / 1e6
        handles.append(Line2D(
            [0], [0], marker="o", color="w",
            markerfacecolor="lightgrey", markeredgecolor="grey",
            markersize=6 * np.sqrt(frac) * 2,
        ))
        labels.append(f"{val_mt:.0f} MtCO₂/yr")
    leg = ax.legend(
        handles, labels, title="Potential", loc="lower left",
        framealpha=0.85, fontsize=6.5, title_fontsize=7,
        handletextpad=0.4, borderpad=0.6,
    )
    return leg


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "snakemake" not in globals():
        import yaml
        run_dir = Path("results/F_lim_H_ind/F_limit_H_ind_test")
        with open("config/plotting.default.yaml") as _f:
            _plotting = yaml.safe_load(_f)
        snakemake = SimpleNamespace(
            input=SimpleNamespace(
                network=str(run_dir / "networks/base_s_90__168h_2050.nc"),
                regions="resources/regions_onshore_base_s_90.geojson",
            ),
            output=[
                str(run_dir / "maps/static/CDR_costs_map.pdf"),
                str(run_dir / "maps/static/CDR_portfolio_map.pdf"),
            ],
            params=SimpleNamespace(plotting=_plotting),
        )
    else:
        from scripts._helpers import configure_logging, set_scenario_config, update_config_from_wildcards
        configure_logging(snakemake)
        set_scenario_config(snakemake)
        update_config_from_wildcards(snakemake.config, snakemake.wildcards)

    from scripts.plot_power_network import load_projection

    n = pypsa.Network(snakemake.input.network)
    regions = gpd.read_file(snakemake.input.regions).set_index("name")
    plotting = snakemake.params.plotting
    crs = load_projection(plotting)
    boundaries = plotting["map"]["boundaries"]
    tech_colors = plotting["tech_colors"]

    # Fix bus coordinates so CDR buses inherit their spatial node position
    eu_loc = plotting.get("eu_node_location", {"x": -5.5, "y": 46.0})
    if "EU" in n.buses.index:
        n.buses.loc["EU", ["x", "y"]] = eu_loc["x"], eu_loc["y"]
    n.buses["location"] = n.buses["location"].replace("", "EU").fillna("EU")
    _x0 = n.buses["x"].copy()
    _y0 = n.buses["y"].copy()
    n.buses["x"] = n.buses.location.map(_x0).fillna(_x0)
    n.buses["y"] = n.buses.location.map(_y0).fillna(_y0)

    # ── compute per-node data ─────────────────────────────────────────────────
    carriers_order = [c for _, c in CDR_TECHS]
    cdr_data = {c: compute_cdr_per_node(n, c) for c in carriers_order}

    # Shared scales across all panels
    max_potential = max(
        (df["e_nom_max"].max() if not df.empty else 0.0)
        for df in cdr_data.values()
    )
    all_lccdr = pd.concat([
        df["lccdr_gross"].dropna() for df in cdr_data.values() if not df.empty
    ]) if any(not df.empty for df in cdr_data.values()) else pd.Series(dtype=float)
    lccdr_max = float(all_lccdr.max()) if not all_lccdr.empty else 1000.0

    colors = {c: tech_colors.get(c, "steelblue") for c in carriers_order}

    # ── Figure 1: 2×2 panels ─────────────────────────────────────────────────
    fig1, axes = plt.subplots(
        2, 2, figsize=(16, 13),
        subplot_kw={"projection": crs},
        layout="constrained",
    )

    for ax, (label, carrier) in zip(axes.ravel(), CDR_TECHS):
        df = cdr_data[carrier]
        reg = regions.copy()
        reg["lccdr"] = df["lccdr_gross"].reindex(reg.index) if not df.empty else np.nan

        setup_ax(ax, reg, "lccdr", crs, boundaries, vmin=0, vmax=lccdr_max)
        ax.set_title(label, fontsize=12, fontweight="bold", pad=5)

        if not df.empty and max_potential > 0:
            draw_split_circles(ax, df, n, crs, colors[carrier], max_potential)

    # Shared colorbar below all panels
    sm1 = plt.cm.ScalarMappable(
        cmap="YlOrRd", norm=plt.Normalize(vmin=0, vmax=lccdr_max)
    )
    cb1 = fig1.colorbar(
        sm1, ax=axes.ravel().tolist(),
        label="Levelized Cost of CDR  [€/tCO₂]  (excl. CO₂ credit)",
        orientation="horizontal", shrink=0.55, pad=0.02, aspect=40,
    )
    cb1.outline.set_edgecolor("none")

    # Size legend on the bottom-left panel
    add_size_legend(axes[1, 0], max_potential)

    # Tech color legend on the bottom-right panel
    tech_handles = [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=colors[c], markersize=9, label=lbl)
        for lbl, c in CDR_TECHS
    ]
    axes[1, 1].legend(
        handles=tech_handles, loc="lower left",
        framealpha=0.85, fontsize=7, title="Deployed", title_fontsize=7.5,
    )

    Path(snakemake.output[0]).parent.mkdir(parents=True, exist_ok=True)
    fig1.savefig(snakemake.output[0], dpi=150)
    plt.close(fig1)
    print(f"Saved Figure 1 → {snakemake.output[0]}")

    # ── Figure 2: composite portfolio map ────────────────────────────────────
    # Weighted average LCCDR per node
    all_nodes = sorted({nd for df in cdr_data.values() for nd in df.index})
    wnum = pd.Series(0.0, index=all_nodes)
    wden = pd.Series(0.0, index=all_nodes)
    for carrier, df in cdr_data.items():
        for nd in df.index:
            if nd not in wnum.index:
                continue
            lcc = df.at[nd, "lccdr_gross"]
            e_opt = df.at[nd, "e_nom_opt"]
            if np.isfinite(lcc) and e_opt > 0:
                wnum[nd] += lcc * e_opt
                wden[nd]  += e_opt
    wlccdr = (wnum / wden.replace(0.0, np.nan)).reindex(regions.index)

    # Max total potential per node (for pie-chart size scale)
    def total_max(nd):
        return sum(
            cdr_data[c].at[nd, "e_nom_max"] if nd in cdr_data[c].index else 0.0
            for c in carriers_order
        )
    max_total = max((total_max(nd) for nd in all_nodes), default=1.0)

    fig2, ax2 = plt.subplots(
        1, 1, figsize=(10, 8),
        subplot_kw={"projection": crs},
        layout="constrained",
    )

    reg2 = regions.copy()
    reg2["wlccdr"] = wlccdr
    setup_ax(ax2, reg2, "wlccdr", crs, boundaries, vmin=0, vmax=lccdr_max)
    ax2.set_title(
        "CDR portfolio — weighted LCCDR and deployment mix per node",
        fontsize=11, fontweight="bold", pad=5,
    )

    draw_pie_charts(ax2, cdr_data, carriers_order, n, crs, colors, max_total)

    sm2 = plt.cm.ScalarMappable(
        cmap="YlOrRd", norm=plt.Normalize(vmin=0, vmax=lccdr_max)
    )
    cb2 = fig2.colorbar(
        sm2, ax=ax2,
        label="Weighted LCCDR  [€/tCO₂]  (excl. CO₂ credit)",
        orientation="horizontal", shrink=0.75, pad=0.02, aspect=40,
    )
    cb2.outline.set_edgecolor("none")

    # Legend: CDR colors + unused
    legend_handles = [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=colors[c], markersize=9, label=lbl)
        for lbl, c in CDR_TECHS
    ] + [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor="lightgrey", markeredgecolor="grey",
               markersize=9, label="Unused potential"),
    ]
    ax2.legend(
        handles=legend_handles, loc="upper left",
        framealpha=0.85, fontsize=8,
    )
    add_size_legend(ax2, max_total)

    fig2.savefig(snakemake.output[1], dpi=150)
    plt.close(fig2)
    print(f"Saved Figure 2 → {snakemake.output[1]}")
