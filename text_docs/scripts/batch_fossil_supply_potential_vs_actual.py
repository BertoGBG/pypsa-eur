"""
Fossil + biomass resources per scenario: what the model was ALLOWED to use
(top row) vs what it ACTUALLY used (bottom row), one 4-panel figure per run.

Run from the pypsa-eur root:

    python text_docs/scripts/batch_fossil_supply_potential_vs_actual.py <results_root> <out_dir> <run1> [<run2> ...]

Top row, read from each solved network of the run (so it differs per run):
  fossil  per-carrier runs: the four "energy_limit_security_<carrier>" caps
          (MtCO2-eq; TWh = cap / the carrier's security intensity).
          aggregate runs: the single "fossil_fuel_limit" cap (MtCO2-eq), shown
          as one bar because the model may split it between fuels freely;
          its TWh value is the cap at the run's actual fossil mix
          (cap / actual fossil MtCO2 x actual fossil TWh).
          runs without a fossil-use limit: no fossil bars.
  biomass domestic potentials = e_sum_max of the biomass generators
          (sustainable: "solid biomass" + "biogas"; unsustainable: carriers
          starting with "unsustainable"), import cap = e_initial of the
          "solid biomass import" store.
  The European-safe potential (fossil_supply_with_coal_mix_2050.png total)
  is marked as a grey reference line.
Bottom row: supply actually dispatched, same fuels and colours:
  gas "gas" | oil "oil primary"/"oil" | hard coal "coal" | lignite "lignite"
  sustainable / unsustainable biomass generators as above
  biomass import = input of the "solid biomass import" links
Emissions: fossil wellhead intensities of build_energy_limit_per_carrier.py,
30 kgCO2e/GJ iLUC for unsustainable biomass, 0 for sustainable, and the
model's upstream charge for imported solid biomass. Each column shares its
y-axis, and the allowed total is marked on the actual-use panels.

Outputs: fossil_supply_potential_vs_actual_<run>.png per run, and
allowed_vs_actual_fossil_biomass.csv (TWh and MtCO2-eq per run, year, fuel).
"""

import contextlib
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa


def load_potential_module():
    """Execute build_fossil_supply_security.py up to (not including) its
    build_variant() calls, so we get its data and colours without writing
    its figures."""
    src = (HERE / "build_fossil_supply_security.py").read_text()
    cut = src.index('\nbuild_variant(\n    "Norway+UK",')
    g = {"__file__": str(HERE / "build_fossil_supply_security.py")}
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src[:cut], g["__file__"], "exec"), g)
    finally:
        sys.argv = argv
    return g


def load_intensities():
    """Read the two emission-factor constants from build_energy_limit_per_carrier.py
    without running it (running it writes its own figures)."""
    src = (HERE / "build_energy_limit_per_carrier.py").read_text()
    constants = {}
    for name in ("INTENSITY_TCO2_MWH", "BIOMASS_IMPORT_CO2_INTENSITY"):
        m = re.search(rf"^{name}\s*=\s*(.+?)(?:\s*#.*)?$", src, re.M)
        constants[name] = eval(m.group(1), {"__builtins__": {}})
    return constants["INTENSITY_TCO2_MWH"], constants["BIOMASS_IMPORT_CO2_INTENSITY"]


P = load_potential_module()
INTENSITY, IMPORT_INTENSITY = load_intensities()
TECH_COLORS = P["TECH_COLORS"]
YEARS = P["YEARS"]
UNSUST_TCO2_MWH = P["UNSUSTAINABLE_BIOMASS_TCO2_PER_MWH"]

FOSSIL = ["gas", "oil", "hard coal", "lignite"]
MODEL_CARRIER = {"gas": "gas", "oil": "oil", "hard coal": "coal", "lignite": "lignite"}
# European-safe components of build_fossil_supply_security.py, per fuel
SECURE_PARTS = {
    "gas": ["Norway gas", "UK gas"],
    "oil": ["Norway oil", "UK oil"],
    "hard coal": ["EU-domestic hard coal"],
    "lignite": ["EU-domestic lignite"],
}

AGG = "fossil, aggregate cap"
FUELS = [
    # label, colour, hatch, emission factor tCO2/MWh
    (AGG, "#3d3d3d", "//", np.nan),
    ("gas", TECH_COLORS["gas"], "", INTENSITY["gas"]),
    ("oil", TECH_COLORS["oil"], "", INTENSITY["oil"]),
    ("hard coal", TECH_COLORS["coal"], "", INTENSITY["coal"]),
    ("lignite", TECH_COLORS["lignite"], "", INTENSITY["lignite"]),
    ("sustainable biomass", P["BIOMASS_COLORS"]["sustainable biomass"], P["BIOMASS_HATCHES"]["sustainable biomass"], 0.0),
    ("unsustainable biomass", P["BIOMASS_COLORS"]["unsustainable biomass"], P["BIOMASS_HATCHES"]["unsustainable biomass"], UNSUST_TCO2_MWH),
    ("biomass import", "#6e5a1e", "..", IMPORT_INTENSITY),
]
EF = {f: ef for f, _, _, ef in FUELS}


def secure_twh_mt(fuel, year):
    twh = sum(P["FUEL_COMPONENTS"][k][1](year) for k in SECURE_PARTS[fuel]) / 1e6
    mt = sum(P["FUEL_COMPONENTS"][k][0](year) for k in SECURE_PARTS[fuel])
    return twh, mt


def european_safe_total(year):
    """Totals of fossil_supply_with_coal_mix_2050.png (fossil + biomass), (MtCO2eq, TWh)."""
    mt = sum(secure_twh_mt(f, year)[1] for f in FOSSIL)
    twh = sum(secure_twh_mt(f, year)[0] for f in FOSSIL)
    for kind in ("sustainable", "unsustainable"):
        mt += P["biomass_mtco2"](year, kind)
        twh += P["BIOMASS_POTENTIAL_TWH"][year][kind]
    return mt, twh


def gen_twh(n, w, carriers=None, prefix=None):
    g = n.generators
    sel = g.index[g.carrier.isin(carriers)] if carriers else g.index[g.carrier.str.startswith(prefix)]
    if sel.empty:
        return 0.0
    return float(n.generators_t.p[sel].mul(w, axis=0).sum().sum() / 1e6)


def actual_use(n):
    """TWh actually supplied per fuel."""
    w = n.snapshot_weightings.generators
    imp = n.links.index[n.links.carrier == "solid biomass import"]
    imp_twh = float(n.links_t.p0[imp].mul(w, axis=0).sum().sum() / 1e6) if len(imp) else 0.0
    return {
        "gas": gen_twh(n, w, ["gas"]),
        "oil": gen_twh(n, w, ["oil primary", "oil"]),
        "hard coal": gen_twh(n, w, ["coal"]),
        "lignite": gen_twh(n, w, ["lignite"]),
        "sustainable biomass": gen_twh(n, w, ["solid biomass", "biogas"]),
        "unsustainable biomass": gen_twh(n, w, prefix="unsustainable"),
        "biomass import": imp_twh,
    }


def e_sum_max_twh(n, carriers=None, prefix=None):
    g = n.generators
    sel = g.index[g.carrier.isin(carriers)] if carriers else g.index[g.carrier.str.startswith(prefix)]
    v = g.loc[sel, "e_sum_max"].replace([np.inf, -np.inf], np.nan)
    return float(v.sum() / 1e6)


def allowed_use(n, year, act):
    """(TWh, MtCO2eq) per fuel the model was allowed to use, and the fossil-limit mode.
    act: actual TWh per fuel (needed to express an aggregate cap in TWh)."""
    gc = n.global_constraints
    twh, mt = {}, {}
    per_carrier = [f for f in FOSSIL if f"energy_limit_security_{MODEL_CARRIER[f]}" in gc.index]
    if per_carrier:
        mode = "per-carrier fossil caps"
        for f in FOSSIL:
            key = f"energy_limit_security_{MODEL_CARRIER[f]}"
            if key not in gc.index:
                twh[f], mt[f] = np.nan, np.nan
                continue
            attr = gc.at[key, "carrier_attribute"]
            c = MODEL_CARRIER[f]
            intensity = float(n.carriers.at[c, attr]) if attr in n.carriers and c in n.carriers.index else EF[f]
            mt[f] = gc.at[key, "constant"] / 1e6
            twh[f] = mt[f] / intensity
    elif "fossil_fuel_limit" in gc.index:
        mode = "one aggregate fossil cap (TWh at the actual fossil mix)"
        cap = gc.at["fossil_fuel_limit", "constant"] / 1e6
        act_mt = sum(act[f] * EF[f] for f in FOSSIL)
        act_twh = sum(act[f] for f in FOSSIL)
        mt[AGG] = cap
        twh[AGG] = cap / (act_mt / act_twh) if act_mt > 0 else np.nan
        for f in FOSSIL:
            twh[f], mt[f] = np.nan, np.nan
    else:
        mode = "no fossil-use limit"
        for f in FOSSIL:
            twh[f], mt[f] = np.nan, np.nan
    twh["sustainable biomass"] = e_sum_max_twh(n, ["solid biomass", "biogas"])
    twh["unsustainable biomass"] = e_sum_max_twh(n, prefix="unsustainable")
    imp = n.stores[n.stores.carrier == "solid biomass import"]
    twh["biomass import"] = float(imp["e_initial"].sum() / 1e6) if len(imp) else 0.0
    for f in ("sustainable biomass", "unsustainable biomass", "biomass import"):
        mt[f] = twh[f] * EF[f]
    return twh, mt, mode


def stack(ax, x, series, label_min):
    """series: list of (label, values, colour, hatch). Returns bar tops."""
    bottom = np.zeros(len(x))
    for label, vals, color, hatch in series:
        vals = np.nan_to_num(np.asarray(vals, dtype=float))
        if not vals.any():  # nothing to draw, keep it out of the legend too
            continue
        ax.bar(x, vals, bottom=bottom, color=color, hatch=hatch, width=0.6, edgecolor="white", label=label)
        for xi, (v, b) in enumerate(zip(vals, bottom)):
            if v > label_min:
                ax.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if (not hatch or hatch in (".", "..", "x") or label == AGG) else "black")
        bottom += vals
    return bottom


def figure_for_run(run, data, out_path):
    """data: year -> dict(actual_twh, allowed_twh, allowed_mt, mode)."""
    x = np.arange(len(YEARS))
    get = lambda key, f, y: data[y][key].get(f, np.nan) if y in data else np.nan
    series = {}
    for tag, key_twh, key_mt in [("allowed", "allowed_twh", "allowed_mt"), ("actual", "actual_twh", None)]:
        series[(tag, "twh")] = [(f, [get(key_twh, f, y) for y in YEARS], c, h) for f, c, h, _ in FUELS]
        if key_mt:
            series[(tag, "mt")] = [(f, [get(key_mt, f, y) for y in YEARS], c, h) for f, c, h, _ in FUELS]
        else:
            series[(tag, "mt")] = [(f, [get(key_twh, f, y) * ef for y in YEARS], c, h) for f, c, h, ef in FUELS]

    fig, axes = plt.subplots(2, 2, figsize=(19, 11), sharey="col")
    (a_lc, a_le), (a_ac, a_ae) = axes
    tops = {
        "lc": stack(a_lc, x, series[("allowed", "mt")], 15),
        "le": stack(a_le, x, series[("allowed", "twh")], 15),
        "ac": stack(a_ac, x, series[("actual", "mt")], 15),
        "ae": stack(a_ae, x, series[("actual", "twh")], 15),
    }
    safe = [european_safe_total(y) for y in YEARS]
    ymax_c = max(tops["lc"].max(), tops["ac"].max(), max(s[0] for s in safe)) * 1.1
    ymax_e = max(tops["le"].max(), tops["ae"].max(), max(s[1] for s in safe)) * 1.1
    for ax, key, ymax in [(a_lc, "lc", ymax_c), (a_ac, "ac", ymax_c), (a_le, "le", ymax_e), (a_ae, "ae", ymax_e)]:
        for xi, y in enumerate(YEARS):
            if y not in data:
                ax.text(xi, ymax * 0.02, "not solved", rotation=90, ha="center", va="bottom", fontsize=9, color="dimgrey")
                continue
            ax.text(xi, tops[key][xi] + ymax * 0.01, f"{tops[key][xi]:.0f}", ha="center", fontsize=8, fontweight="bold")
        ax.set_xticks(x, [str(y) for y in YEARS])
        ax.set_ylim(0, ymax)
        ax.spines[["top", "right"]].set_visible(False)
    # reference marks: European-safe potential on the allowed row, allowed total on the actual row
    solved = np.array([y in data for y in YEARS])
    for ax, idx in [(a_lc, 0), (a_le, 1)]:
        ax.plot(x, [s[idx] for s in safe], ls="none", marker="_", ms=34, mew=2, color="grey",
                label="European-safe potential (reference)")
    for ax, key in [(a_ac, "lc"), (a_ae, "le")]:
        ax.plot(x[solved], tops[key][solved], ls="none", marker="_", ms=34, mew=2, color="black",
                label="Allowed in this run (top-row total)")
    modes = sorted({d["mode"] for d in data.values()})
    mode_txt = "; ".join(modes)
    a_lc.set_title(f"ALLOWED in {run}, emissions basis (MtCO2-eq/yr)\n{mode_txt}", fontsize=11)
    a_le.set_title(f"ALLOWED in {run}, energy basis (TWh/yr)\n{mode_txt}", fontsize=11)
    a_ac.set_title(f"ACTUAL USE in {run}, emissions basis (MtCO2-eq/yr)", fontsize=11)
    a_ae.set_title(f"ACTUAL USE in {run}, energy basis (TWh/yr)", fontsize=11)
    if modes == ["no fossil-use limit"]:
        for ax in (a_lc, a_le):
            ax.text(0.5, 0.6, "no fossil-use limit in this run:\nonly biomass availability is bounded",
                    transform=ax.transAxes, ha="center", fontsize=11, color="dimgrey")
    for ax in (a_lc, a_ac):
        ax.set_ylabel("MtCO2-eq/yr")
    for ax in (a_le, a_ae):
        ax.set_ylabel("TWh/yr")
    a_le.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8, borderaxespad=0, frameon=False)
    a_ae.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8, borderaxespad=0, frameon=False)
    fig.suptitle(f"Fossil + biomass: allowed by the run's limits vs actual use — {run}", fontsize=14)
    fig.text(0.5, 0.005,
             "Allowed: fossil-use caps and biomass potentials read from each solved network (an aggregate cap is one bar; its TWh value "
             "is the cap at the run's actual fossil mix). Grey marks: European-safe Norway+UK+coal potential of fossil_supply_with_coal_mix_2050.png. "
             f"Emissions: fossil wellhead intensities, unsustainable biomass {UNSUST_TCO2_MWH * 1000 / 3.6:.0f} kgCO2e/GJ, "
             f"imported solid biomass {IMPORT_INTENSITY:.3f} tCO2/MWh, sustainable biomass 0.",
             ha="center", fontsize=8.5, style="italic", wrap=True)
    fig.tight_layout(rect=(0, 0.03, 0.9, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    results_root, out_dir, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for run in runs:
        data = {}
        for path in sorted((results_root / run / "networks").glob("*.nc")):
            m = re.search(r"_(\d{4})\.nc$", path.name)
            if not m or int(m.group(1)) not in YEARS:
                continue
            year = int(m.group(1))
            print(f"{run} {year}", flush=True)
            n = pypsa.Network(str(path))
            act = actual_use(n)
            a_twh, a_mt, mode = allowed_use(n, year, act)
            data[year] = dict(actual_twh=act, allowed_twh=a_twh, allowed_mt=a_mt, mode=mode)
            for f in EF:
                rows.append({"run": run, "year": year, "fuel": f, "mode": mode,
                             "allowed_TWh": a_twh.get(f), "allowed_MtCO2eq": a_mt.get(f),
                             "actual_TWh": act.get(f), "actual_MtCO2eq": act[f] * EF[f] if f in act else np.nan})
            # sanity: actual fossil use must not exceed a per-carrier cap
            for f in FOSSIL:
                if np.isfinite(a_twh[f]) and act[f] > a_twh[f] * 1.001 and mode.startswith("per-carrier"):
                    print(f"  !! {run} {year} {f}: actual {act[f]:.1f} > cap {a_twh[f]:.1f} TWh", flush=True)
        figure_for_run(run, data, out_dir / f"fossil_supply_potential_vs_actual_{run}.png")
    pd.DataFrame(rows).to_csv(out_dir / "allowed_vs_actual_fossil_biomass.csv", index=False)
    print(f"Wrote {len(runs)} figures to {out_dir}")


if __name__ == "__main__":
    main()
