"""
Shared utilities for CDR pipeline check scripts.

Loads run parameters from pypsa-eur config files so check scripts do not
need hardcoded wildcards. Merges config/config.default.yaml with a
user-supplied config file, then exposes a clean dict of check parameters.

Usage in any check script:
    from _check_utils import parse_check_args, load_check_params

    args   = parse_check_args()          # handles --config / --horizon / etc.
    params = load_check_params(args)     # returns dict with RDIR, WC, paths, …
"""

import argparse
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(".")   # check scripts are run from the pypsa-eur root

SNAKEMAKE_SCRIPT = BASE_DIR / "run_snakemake.sh"


# ── Auto-detect config from run_snakemake.sh ───────────────────────────────────

def _detect_configfile() -> str | None:
    """
    Parse run_snakemake.sh and return the --configfile value, or None.
    Looks for:   --configfile config/config.*.yaml
    """
    if not SNAKEMAKE_SCRIPT.exists():
        return None
    import re
    text = SNAKEMAKE_SCRIPT.read_text()
    m = re.search(r"--configfile\s+(\S+)", text)
    if m:
        return m.group(1)
    return None


# ── Config loading ─────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (override wins)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(user_config_path: str | None) -> dict:
    """
    Load config/config.default.yaml and (optionally) a user config,
    returning the merged dict.

    If user_config_path is None, auto-detects from run_snakemake.sh.
    """
    default_path = BASE_DIR / "config" / "config.default.yaml"
    if not default_path.exists():
        print(f"WARNING: default config not found at {default_path}, using empty base.")
        cfg = {}
    else:
        cfg = _load_yaml(default_path)

    resolved = user_config_path or _detect_configfile()
    if resolved:
        user_path = Path(resolved)
        if not user_path.exists():
            print(f"ERROR: config file not found: {user_path}", file=sys.stderr)
            sys.exit(1)
        print(f"  Using config: {user_path}")
        cfg = _deep_merge(cfg, _load_yaml(user_path))
    else:
        print("  No user config found — using config.default.yaml only.")

    return cfg


# ── CLI arguments ──────────────────────────────────────────────────────────────

def parse_check_args(extra_args: list[tuple] | None = None) -> argparse.Namespace:
    """
    Common CLI argument parser for all check scripts.

    extra_args: list of (flags, kwargs) tuples for script-specific arguments.
    Example:
        extra_args=[
            (["--potential-type"], {"help": "density or growth"}),
        ]
    """
    p = argparse.ArgumentParser(
        description="CDR pipeline check — reads wildcards from config file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--config", "-c",
        default=None,
        metavar="PATH",
        help=(
            "Path to user config YAML (e.g. config/config.CDRs.yaml). "
            "Merged on top of config/config.default.yaml. "
            "If omitted, only config.default.yaml is used."
        ),
    )
    p.add_argument(
        "--run-name",
        default=None,
        metavar="NAME",
        help="Override run name (= results/resources sub-directory). "
             "Reads run.name from config if not set.",
    )
    p.add_argument(
        "--clusters",
        default=None,
        metavar="N",
        help="Override cluster count (e.g. 50). "
             "Reads scenario.clusters[0] from config if not set.",
    )
    p.add_argument(
        "--opts",
        default=None,
        metavar="OPTS",
        help="Override opts wildcard (e.g. '' or 'Co2L'). "
             "Reads scenario.opts[0] from config if not set.",
    )
    p.add_argument(
        "--sector-opts",
        default=None,
        metavar="OPTS",
        help="Override sector opts wildcard (e.g. '168h'). "
             "Reads scenario.sector_opts[0] from config if not set.",
    )
    p.add_argument(
        "--horizon",
        default=None,
        metavar="YEAR",
        help="Override planning horizon (e.g. 2050). "
             "Reads scenario.planning_horizons[-1] from config if not set.",
    )
    if extra_args:
        for flags, kwargs in extra_args:
            p.add_argument(*flags, **kwargs)

    return p.parse_args()


# ── Parameter extraction ───────────────────────────────────────────────────────

def load_check_params(args: argparse.Namespace) -> dict:
    """
    Merge config files, apply CLI overrides, and return a dict with:

      RDIR             – run directory name (results/<RDIR>/, resources/<RDIR>/)
      CLUSTERS         – cluster count string (e.g. "50")
      OPTS             – opts wildcard (e.g. "" or "Co2L")
      SECTOR_OPTS      – sector opts wildcard (e.g. "168h")
      PLANNING_HORIZON – planning horizon string (e.g. "2050")
      WC               – full wildcard stem (e.g. "base_s_50__168h_2050")
      BASE_DIR         – Path to pypsa-eur root
      RES              – Path to resources/
      RES_RUN          – Path to resources/<RDIR>/
      RESULTS          – Path to results/<RDIR>/
      cfg              – full merged config dict (for script-specific lookups)
    """
    cfg = load_config(getattr(args, "config", None))

    # ── Wildcard resolution: CLI > config > fallback ──────────────────────────
    run_cfg      = cfg.get("run", {})
    scenario_cfg = cfg.get("scenario", {})

    RDIR = (
        args.run_name
        or run_cfg.get("name")
        or "run"
    )
    CLUSTERS = str(
        args.clusters
        or (scenario_cfg.get("clusters") or [50])[0]
    )
    OPTS = (
        args.opts
        if args.opts is not None
        else str((scenario_cfg.get("opts") or [""])[0])
    )
    SECTOR_OPTS = str(
        args.sector_opts
        or (scenario_cfg.get("sector_opts") or [""])[0]
    )
    PLANNING_HORIZON = str(
        args.horizon
        or (scenario_cfg.get("planning_horizons") or [2050])[-1]
    )

    WC = f"base_s_{CLUSTERS}_{OPTS}_{SECTOR_OPTS}_{PLANNING_HORIZON}"

    RES     = BASE_DIR / "resources"
    RES_RUN = BASE_DIR / "resources" / RDIR
    RESULTS = BASE_DIR / "results"   / RDIR

    return dict(
        RDIR=RDIR,
        CLUSTERS=CLUSTERS,
        OPTS=OPTS,
        SECTOR_OPTS=SECTOR_OPTS,
        PLANNING_HORIZON=PLANNING_HORIZON,
        WC=WC,
        BASE_DIR=BASE_DIR,
        RES=RES,
        RES_RUN=RES_RUN,
        RESULTS=RESULTS,
        cfg=cfg,
    )
