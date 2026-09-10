#!/usr/bin/env bash
set -eo pipefail
REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"
source "$HOME/anaconda3/etc/profile.d/conda.sh"
echo "Starting Snakemake at $(date)"
conda activate pypsa-eur
snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml config/config.weekend_batch_50_1095seg.yaml config/config.nuclear_generator.yaml \
  --rerun-incomplete \
  all
echo "Finished at $(date)"
