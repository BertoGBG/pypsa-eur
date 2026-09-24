#!/usr/bin/env bash
# Wave 2a of the post-disaster recovery: finish weekend_run1-run5 all the way
# to 2050 (2040, 2045, 2050 -- 3 horizons x 5 scenarios = 15 solves), so the
# user can start analyzing complete 2025-2050 pathways for these scenarios
# while Wave 2b (run6-run9) is prepared separately.
#
# Concurrent Gurobi solves capped at 10 (WLS limit raised to 10, verified 2026-09-24) via --set-resources/--resources, same
# as Wave 1 -- this is what should prevent a repeat of the original disaster
# (a burst of many jobs hitting the SLURM queue simultaneously after a long
# pending period), since Snakemake will never have more than 2 solve rule
# instances in flight regardless of how many total solves this wave needs.
set -eo pipefail
REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"
source "$HOME/anaconda3/etc/profile.d/conda.sh"
echo "Starting Snakemake (wave 2a: run1-5 -> 2050) at $(date)"
conda activate pypsa-eur

snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml config/config.weekend_batch_50_1095seg.yaml config/config.nuclear_generator.yaml \
  --set-resources \
      solve_sector_network_myopic:gurobi_sessions=1 \
  --resources gurobi_sessions=10 \
  --rerun-incomplete \
  results/weekend_run1/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run1/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run1/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run2/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run2/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run2/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run3/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run3/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run3/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run4/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run4/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run4/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run5/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run5/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run5/networks/base_s_50__1095seg_2050.nc

echo "Finished at $(date)"
