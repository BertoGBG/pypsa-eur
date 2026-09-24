#!/usr/bin/env bash
# Wave 2b of the post-disaster recovery: finish weekend_run6-run9 all the way
# to 2050 (2040, 2045, 2050 -- 3 horizons x 4 scenarios = 12 solves). This is
# the final wave -- once complete, all 9 scenarios are fully solved 2025-2050.
#
# Concurrent Gurobi solves capped at 10 (WLS limit raised to 10, verified 2026-09-24) via --set-resources/--resources, same
# as Wave 1 and Wave 2a -- this is what prevented a repeat of the original
# disaster (a burst of many jobs hitting the SLURM queue simultaneously after
# a long pending period), since Snakemake will never have more than 2 solve
# rule instances in flight regardless of how many total solves this wave needs.
set -eo pipefail
REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"
source "$HOME/anaconda3/etc/profile.d/conda.sh"
echo "Starting Snakemake (wave 2b: run6-9 -> 2050) at $(date)"
conda activate pypsa-eur

snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml config/config.weekend_batch_50_1095seg.yaml config/config.nuclear_generator.yaml \
  --set-resources \
      solve_sector_network_myopic:gurobi_sessions=1 \
  --resources gurobi_sessions=10 \
  --rerun-incomplete \
  results/weekend_run6/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run6/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run6/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run7/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run7/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run7/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run8/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run8/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run8/networks/base_s_50__1095seg_2050.nc \
  results/weekend_run9/networks/base_s_50__1095seg_2040.nc \
  results/weekend_run9/networks/base_s_50__1095seg_2045.nc \
  results/weekend_run9/networks/base_s_50__1095seg_2050.nc

echo "Finished at $(date)"
