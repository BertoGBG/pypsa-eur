"""
Design options for the security limits (2026-11-25), for discussion.

Part 1  Climate paths: EU path (model co2_budget, ~1.7 C) and a smooth 1.9 C
        path (Victoria et al. 2022 budgets, net zero in 2050).
Part 2  Aggregate fossil curves for autarky (100 % in 2050), MtCO2/yr:
        A  old:      L = P / f,  f smoothstep (share formulation)
        B  current:  L = P + M,  M smoothstep from today's imports to 0
        C  tight:    L = max(E_1.7, P)
        D  gradual:  L = max(E_1.9, P)
        E  cumulative ratio: L = P + M0 (1-x)^a, a such that the cumulative
           fossil carbon = kappa x cumulative climate budget
           (kappa = 1, or kappa from the geological storage of lever 1)
        + implied negative emissions = cumulative fossil - climate budget.
Part 3  Split between carriers, for the tight and the gradual aggregate
        (2026-11-25: two cases, both coherent with the aggregate L):
        same pace  limit_c = P_c + sigma_c M  (today's import mix shrinks
                   proportionally; the limits add up to L exactly)
        free       L on the total + limit_c = P_c + M  (the model chooses the
                   mix; the carrier limits only bind in 2050, autarky)

Usage: python3 build_limit_options.py [out_dir]
"""
import contextlib
import io
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out_dir, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))

_pc = {"__file__": os.path.join(HERE, "build_energy_limit_per_carrier.py")}
_argv = sys.argv
sys.argv = [_pc["__file__"], os.path.join(out_dir, "_tmp")]
with open(_pc["__file__"]) as f, contextlib.redirect_stdout(io.StringIO()):
    exec(compile(f.read(), _pc["__file__"], "exec"), _pc)
sys.argv = _argv
_g = _pc["_g"]

YEARS = np.array([2025, 2030, 2035, 2040, 2045, 2050])
YF = np.linspace(2025, 2050, 251)
X = lambda y: (np.asarray(y) - 2025) / 25
FOSSIL = ["gas", "oil", "coal", "lignite"]
INT = _pc["INTENSITY"]
LABEL = _pc["LABEL"]
COLOR = _pc["COLOR"]
s = lambda x: 3 * np.clip(x, 0, 1) ** 2 - 2 * np.clip(x, 0, 1) ** 3


def cum(fn, y0=2025, y1=2050):
    yy = np.linspace(y0, y1, 2501)
    return np.trapezoid([fn(y) for y in yy], yy) / 1000  # Gt


# ------------------------------------------------------------------ part 1
E0 = 2983.3            # CO2 limit 2025, model
SPENT_2020_25 = 15.7   # Gt emitted 2020-2025 on the model path
EU = {2025: 2983.3, 2030: 2071.8, 2035: 1151.0, 2040: 460.4, 2045: 230.2, 2050: 0.0}
eu = lambda y: float(np.interp(y, list(EU), list(EU.values())))


def budget_2020(T):  # Victoria et al. 2022, 67th pct TCRE, Europe 6.43 %
    return (1150 + (T - 2.0) * 1500) * 0.0643


B19 = budget_2020(1.9) - SPENT_2020_25          # Gt from 2025
# Victoria et al. (2022) method: horizon values from e0 (1+mt) exp(-mt),
# m = 2 e0 / B (budget from 2025), net zero forced in 2050, linear between
# the planning horizons (as the model uses them)
M19 = 2 * E0 / 1000 / B19
_h19 = {y: (E0 * (1 + M19 * (y - 2025)) * np.exp(-M19 * (y - 2025)) if y < 2050 else 0.0) for y in YEARS}
e19 = lambda y: float(np.interp(y, list(_h19), list(_h19.values())))
A19 = M19
B19P = None  # set after cum() is available


def victoria_path(T):
    B = budget_2020(T) - SPENT_2020_25
    m = 2 * E0 / 1000 / B
    return lambda y: E0 * (1 + m * (y - 2025)) * np.exp(-m * (y - 2025))


e19_trunc = victoria_path(1.9)
B_EU = cum(eu)
B19P = cum(e19)  # cumulative of the 1.9 C path (net zero forced in 2050)
B_REF_EXP = 25 * E0 / 1000 / B_EU - 1
eu_fit = lambda y: E0 * (1 - X(y)) ** B_REF_EXP

# ------------------------------------------------------------------ part 2
P = lambda y: sum(_pc["SECURE_TWH"][c](y) * INT[c] for c in FOSSIL)  # secure, MtCO2
USE_2024 = 2993.2
M0 = USE_2024 - P(2025)
OLD = {2025: 2993.2, 2030: 2254.9, 2035: 1368.3, 2040: 942.3, 2045: 718.1, 2050: 613.2}
curves = {
    "A  old (share formulation)": lambda y: float(np.interp(y, list(OLD), list(OLD.values()))),
    "B  tight: max(reference path, secure)": lambda y: max(eu(y), P(y)),
    "C  gradual: max(1.9 C path, secure)": lambda y: max(e19(y), P(y)),
}
# non-fuel process CO2 of industry in our model (solved lever-test networks):
# cement calcination 112.1 Mt clinker x 0.5071 = 56.8 Mt + remaining
# "process emissions" load (ceramics, glass, electrodes, anodes) 13.1-15.2 Mt
PROC = lambda y: float(np.interp(y, [2025, 2030, 2040, 2050], [69.9, 70.3, 71.3, 72.0]))
STOR_LOW = {2025: 0, 2030: 40, 2035: 100, 2040: 180, 2045: 250, 2050: 250}
STOR_HIGH = {k: v * 1.6 for k, v in STOR_LOW.items()}
stor = lambda d: (lambda y: float(np.interp(y, list(d), list(d.values()))))
C_PROC, C_SL, C_SH = cum(PROC), cum(stor(STOR_LOW)), cum(stor(STOR_HIGH))
ERW = 36.5  # MtCO2/yr, rock weathering potential in the model; enlarges the durable storage


def ratio_curve(target_gt):
    """L = P + M0 (1-x)^a with cumulative = target; None if not reachable."""
    f = lambda a: cum(lambda y: P(y) + M0 * (1 - X(y)) ** a) - target_gt
    lo, hi = 1e-3, 200.0
    if f(lo) < 0 or f(hi) > 0:
        return None, None
    a = brentq(f, lo, hi)
    return (lambda y: P(y) + M0 * (1 - X(y)) ** a), a


ratio_specs = {}
for clim, Bc in [("reference path", B_EU), ("1.9 C path", B19P)]:
    for kname, tgt in [("kappa = 1", Bc - C_PROC)]:  # cumulative fossil = fossil part of the budget
        fn, a = ratio_curve(tgt)
        tag = "D1" if clim == "reference path" else "D2"
        ratio_specs[f"D  {tag} limit case, {clim} (a = {a:.1f})"] = (fn, a, tgt / Bc)
for k, (fn, a, kap) in ratio_specs.items():
    if fn is not None:
        curves[k] = fn


# ------------------------------------------------------------------ figures part 1
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.5))
a1.plot(YF, [eu(y) for y in YF], "k-", lw=2.3, marker="o", markevery=50, label=f"Reference path (PyPSA-Eur, EU targets), {B_EU:.1f} Gt from 2025, about 1.7 °C")
a1.plot(YF, [e19(y) for y in YF], color="tab:red", lw=2.3, marker="o", markevery=50,
        label=f"1.9 °C budget, method of Victoria et al. (m = {M19:.3f}), net zero in 2050, {cum(e19):.1f} Gt")
a1.set_ylabel("MtCO2/yr"); a1.set_xlim(2025, 2050); a1.set_ylim(0, 3200); a1.grid(alpha=.3); a1.legend(fontsize=7.5)
a1.set_title("Annual CO2 limit")
for fn, c, lab in [(eu, "k", "Reference path (PyPSA-Eur)"), (e19, "tab:red", "1.9 °C path")]:
    a2.plot(YF, [cum(fn, 2025, y) for y in YF], color=c, lw=2, label=lab)
for T in [1.6, 1.7, 1.8, 1.9, 2.0]:
    b = budget_2020(T) - SPENT_2020_25
    a2.axhline(b, color="grey", lw=.7, ls=":"); a2.text(2025.3, b + .6, f"{T} °C budget from 2025: {b:.1f} Gt", fontsize=7)
a2.set_ylabel("Cumulative CO2 from 2025 (Gt)"); a2.set_xlim(2025, 2050); a2.grid(alpha=.3); a2.legend(fontsize=8, loc="lower right")
a2.set_title("Cumulative emissions and budgets (67 %)")
fig.tight_layout(); fig.savefig(f"{out_dir}/opt1_climate_paths.png", dpi=150); plt.close(fig)

# ------------------------------------------------------------------ figures part 2
sty = {"A": ("tab:gray", "--"), "B": ("black", "-"), "C": ("tab:red", "-")}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 6))
for k, fn in curves.items():
    col, ls = sty.get(k[0], (None, "-."))
    a1.plot(YF, [fn(y) for y in YF], color=col, ls=ls, lw=2 if k[0] in "BC" else 1.4, label=k)
    a2.plot(YF, [cum(fn, 2025, y) for y in YF], color=col, ls=ls, lw=2 if k[0] in "BC" else 1.4, label=k)

a1.plot(YF, [P(y) for y in YF], color="dimgray", ls=":", lw=1.5, label="European-safe production")
a1.plot(YF, [eu(y) for y in YF], color="k", lw=1.6, ls=(0, (4, 2)), marker="s", markevery=50, ms=4,
        label="CO2 limit, reference path (PyPSA-Eur)")
a1.plot(YF, [e19(y) for y in YF], color="tab:red", lw=1.6, ls=(0, (4, 2)), marker="s", markevery=50, ms=4,
        label="CO2 limit, 1.9 °C path")
a1.set_ylabel("MtCO2/yr (CO2 content of fossil fuels)"); a1.set_title("Aggregate fossil limit, autarky in 2050")
a2.axhline(B_EU, color="k", lw=.8, ls=":"); a2.text(2025.3, B_EU + .5, "reference budget", fontsize=7)
a2.axhline(B19P, color="tab:red", lw=.8, ls=":"); a2.text(2025.3, B19P + .5, "1.9 °C path", fontsize=7, color="tab:red")
a2.axhline(B_EU - C_PROC, color="k", lw=.8, ls="--"); a2.text(2025.3, B_EU - C_PROC - 1.6, "reference: fossil budget (minus process CO2)", fontsize=7)
a2.axhline(B19P - C_PROC, color="tab:red", lw=.8, ls="--"); a2.text(2025.3, B19P - C_PROC - 1.6, "1.9 °C: fossil budget (minus process CO2)", fontsize=7, color="tab:red")
a2.set_ylabel("Cumulative from 2025 (Gt)"); a2.set_title("Cumulative fossil carbon allowed")
for a in (a1, a2):
    a.set_xlim(2025, 2050); a.grid(alpha=.3)
a1.legend(fontsize=7, loc="upper right")
fig.tight_layout(); fig.savefig(f"{out_dir}/opt2_aggregate_curves.png", dpi=150); plt.close(fig)

# implied negative emissions
names, need_eu, need_19 = [], [], []
_e = 0
for k, fn in curves.items():
    c = cum(fn)
    names.append(k.split()[1] if k.startswith("D") else k[0])
    need_eu.append(c + C_PROC - B_EU)
    need_19.append(c + C_PROC - B19P)
fig, (ax0, ax) = plt.subplots(1, 2, figsize=(16, 5.8), gridspec_kw={"width_ratios": [1, 1.15]})
xx = np.arange(len(names))
cumf = [cum(fn) for fn in curves.values()]
ax0.bar(xx, cumf, .55, color="tab:gray", label="cumulative fossil carbon allowed")
ax0.bar(xx, [C_PROC] * len(xx), .55, bottom=cumf, color="white", edgecolor="black", hatch="///", lw=.5,
        label="process CO2 of industry")
ax0.axhline(B_EU, color="k", ls=(0, (4, 2)), lw=1.6, label=f"cumulative CO2 limit, reference path: {B_EU:.1f} Gt")
ax0.axhline(B19P, color="tab:red", ls=(0, (4, 2)), lw=1.6, label=f"cumulative CO2 limit, 1.9 °C path: {B19P:.1f} Gt")
ax0.set_xticks(xx); ax0.set_xticklabels(names, fontsize=10)
ax0.set_ylabel("Gt CO2, 2025-2050"); ax0.set_title("Cumulative fossil and process CO2 vs cumulative CO2 limit")
ax0.legend(fontsize=7.5, loc="lower right"); ax0.grid(alpha=.3, axis="y")
ax.bar(xx - .2, need_eu, .4, color="k", label="under the reference path")
ax.bar(xx + .2, need_19, .4, color="tab:red", label="under the 1.9 °C path")
for xo, vals, col in [(-.2, need_eu, "k"), (.2, need_19, "tab:red")]:
    for xi, v in zip(xx, vals):
        ax.text(xi + xo, v + (0.4 if v >= 0 else -0.4), f"{v:.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=7, color=col)
C_ERW = ERW * 25 / 1000
for v, lab in [(C_SL + C_ERW, "durable capacity, low storage + ERW"), (C_SH + C_ERW, "durable capacity, high storage + ERW")]:
    ax.axhline(v, color="tab:green", ls="--", lw=1); ax.text(len(names) - .5, v + .3, f"{lab}: {v:.1f} Gt", ha="right", fontsize=8, color="tab:green")
ax.axhline(0, color="grey", lw=.8)
ax.set_xticks(xx); ax.set_xticklabels(names, fontsize=10)
ax.set_ylabel("Gt CO2, 2025-2050")
ax.set_title("Capture and removal needed if fully used (difference)")
ax.legend(fontsize=8); ax.grid(alpha=.3, axis="y")
fig.tight_layout(); fig.savefig(f"{out_dir}/opt2_implied_removals.png", dpi=150); plt.close(fig)

# ------------------------------------------------------------------ part 3
SEC = {c: (lambda c: (lambda y: _pc["SECURE_TWH"][c](y) * INT[c]))(c) for c in FOSSIL}
USE24 = {c: _pc["CONSUMPTION_2024_TWH"][c] * INT[c] for c in FOSSIL}
IMP0 = {c: max(USE24[c] - SEC[c](2025), 0.0) for c in FOSSIL}  # lignite: no imports
TOT_IMP0 = sum(IMP0.values())
SIGMA0 = {c: IMP0[c] / TOT_IMP0 for c in FOSSIL}


def split_methods(agg):
    m_tot = lambda y: max(agg(y) - P(y), 0.0)
    out = {
        "same pace: P_c + sigma_c M": {c: (lambda c: (lambda y: SEC[c](y) + SIGMA0[c] * m_tot(y)))(c) for c in FOSSIL},
        "free: P_c + M (aggregate decides)": {c: (lambda c: (lambda y: SEC[c](y) + (m_tot(y) if SIGMA0[c] > 0 else 0.0)))(c) for c in FOSSIL},
    }
    return out


msty = {"s": ("black", "-"), "f": ("tab:green", "--")}
for tag, agg, clim, clab, ccol in [
    ("tight", curves["B  tight: max(reference path, secure)"], eu, "CO2 limit, reference path (right axis)", "k"),
    ("gradual", curves["C  gradual: max(1.9 C path, secure)"], e19, "CO2 limit, 1.9 °C path (right axis)", "tab:red"),
]:
    meth = split_methods(agg)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, c in zip(axes.flat, FOSSIL):
        for k, d in meth.items():
            col, ls = msty[k[0]]
            ax.plot(YF, [d[c](y) for y in YF], color=col, ls=ls, lw=2, label=k)
        ax.plot(YF, [SEC[c](y) for y in YF], color="dimgray", ls=":", lw=1.2, label="European-safe production")
        ax.scatter([2025], [USE24[c]], color="k", s=25, zorder=5, label="use in 2024")
        ax.set_title(LABEL[c]); ax.set_ylabel("MtCO2/yr"); ax.set_xlim(2025, 2050); ax.set_ylim(0, None); ax.grid(alpha=.3)
        axr = ax.twinx()
        axr.plot(YF, [clim(y) for y in YF], color=ccol, lw=1.4, ls=(0, (4, 2)), marker="s", markevery=50, ms=4, alpha=.7, label=clab)
        axr.set_ylim(0, 3200); axr.set_ylabel("CO2 limit, MtCO2/yr", color="dimgray", fontsize=8)
        axr.tick_params(axis="y", labelsize=7, colors="dimgray")
    h1, l1 = axes.flat[0].get_legend_handles_labels()
    h2, l2 = axr.get_legend_handles_labels()
    axes.flat[0].legend(h1 + h2, l1 + l2, fontsize=7)
    fig.suptitle(f"Carrier limits, {tag} aggregate curve (autarky in 2050): same pace, and free within the aggregate")
    fig.tight_layout(rect=(0, 0, 1, .96)); fig.savefig(f"{out_dir}/opt3_split_{tag}.png", dpi=150); plt.close(fig)

# ------------------------------------------------------------------ print
print(f"EU budget from 2025 {B_EU:.1f} Gt; 1.9 C budget from 2025 {B19:.1f} Gt, smooth exponent a={A19:.2f}")
print("1.9 smooth path:", [round(e19(y)) for y in YEARS])
print(f"process CO2 2025-50 {C_PROC:.1f} Gt; storage low/high {C_SL:.1f}/{C_SH:.1f} Gt")
print("\naggregate curves (MtCO2/yr) | cumulative Gt | removals needed under EU / 1.9:")
for k, fn in curves.items():
    c = cum(fn)
    print(f"  {k:55s}", [round(fn(y)) for y in YEARS], f"| {c:.1f} | {c + C_PROC - B_EU:.1f} / {c + C_PROC - B19P:.1f}")
for k, (fn, a, kap) in ratio_specs.items():
    print(f"  {k}: kappa={kap:.2f}, exponent a={a if a is None else round(a, 2)}" + ("" if fn else "  -> NOT reachable with fixed end points"))
print("\nimport shares today (sigma):", {c: round(v, 3) for c, v in SIGMA0.items()})
for tag, agg in [("tight", curves["B  tight: max(reference path, secure)"]), ("gradual", curves["C  gradual: max(1.9 C path, secure)"])]:
    meth = split_methods(agg)
    print(f"\nsplit, {tag} (MtCO2/yr):")
    for k, d in meth.items():
        print(f"  {k}")
        for c in FOSSIL:
            print(f"     {c:8s}", [round(d[c](y)) for y in YEARS])


# ------------------------------------------------------------------ config values, two split cases
import yaml as _yaml
BIO_IMP_2024 = 21.5  # TWh, extra-EU pellet imports 2024
CO2_1990 = 4603.6    # MtCO2, base of co2_budget fractions
def split_config(agg, case):
    m_tot = lambda y: max(agg(y) - P(y), 0.0)
    lim = split_methods(agg)[case]
    out = {
        # same pace: the carrier limits add up to L, the aggregate is kept as a check
        "fossil_limit": True,
        "fossil_limit_values": {int(y): round(float(agg(y)), 1) for y in YEARS},
        "energy_limit_per_carrier": True,
        "energy_limit_per_carrier_values": {
            c: {int(y): round(float(lim[c](y)), 1) for y in YEARS} for c in FOSSIL
        },
        "sector": {"solid_biomass_import": {"enable": True, "max_amount": {
            int(y): float(round(BIO_IMP_2024 * m_tot(y) / m_tot(2025), 1)) for y in YEARS}}},
    }
    return out
_T, _G = curves["B  tight: max(reference path, secure)"], curves["C  gradual: max(1.9 C path, secure)"]
_S, _F = "same pace: P_c + sigma_c M", "free: P_c + M (aggregate decides)"
scen = {
    "limits_tight_pace": split_config(_T, _S),
    "limits_tight_free": split_config(_T, _F),
    "limits_gradual_pace": split_config(_G, _S),
    "limits_gradual_free": split_config(_G, _F),
    "limits_share_pace": split_config(curves["A  old (share formulation)"], _S),
    "limits_share_free": split_config(curves["A  old (share formulation)"], _F),
    "limits_limitcase_ref_pace": split_config(next(v for k, v in curves.items() if k.startswith("D  D1")), _S),
    "limits_limitcase_ref_free": split_config(next(v for k, v in curves.items() if k.startswith("D  D1")), _F),
    "climate_19": {"co2_budget": {"upper": {int(y): round(float(e19(y)) / CO2_1990, 4) for y in YEARS}}},
}
with open(f"{out_dir}/scenarios.limits_split.yaml", "w") as f:
    _yaml.safe_dump(scen, f, sort_keys=False, default_flow_style=None)
print("\nwrote", f"{out_dir}/scenarios.limits_split.yaml")
print(open(f"{out_dir}/scenarios.limits_split.yaml").read())
