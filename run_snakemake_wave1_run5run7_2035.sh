#!/usr/bin/env bash
# Wave 1 of the post-disaster recovery: bring weekend_run5 and weekend_run7
# up to 2035, matching the other 7 scenarios. This is the smallest, safest
# resubmission -- only 2 solves (~11.5k billing-minutes) vs. the 60k account
# GrpTRESMins cap that killed the previous controller (60,568 used against
# 60,000). Deliberately targets the two output files directly rather than
# `all`, so Snakemake doesn't pull in the remaining ~27-solve backlog
# (2040/2045/2050 for everyone) in this wave.
#
# Concurrent Gurobi solves are capped at 10 (WLS limit raised to 10, verified 2026-09-24) via --set-resources/--resources
# (see run_snakemake_weekend_batch_capped.sh for the full rationale) so this
# can't repeat the license-collision failure even though only 2 jobs run here.
set -eo pipefail
REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"
source "$HOME/anaconda3/etc/profile.d/conda.sh"
echo "Starting Snakemake (wave 1: run5/run7 -> 2035) at $(date)"
conda activate pypsa-eur

snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml config/config.weekend_batch_50_1095seg.yaml config/config.nuclear_generator.yaml \
  --set-resources \
      solve_sector_network_myopic:gurobi_sessions=1 \
  --resources gurobi_sessions=10 \
  --rerun-incomplete \
  results/weekend_run5/networks/base_s_50__1095seg_2035.nc \
  results/weekend_run7/networks/base_s_50__1095seg_2035.nc

echo "Finished at $(date)"
