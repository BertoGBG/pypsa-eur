#!/usr/bin/env bash

set -eo pipefail

REPO="/home/alamia/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"

source "$HOME/anaconda3/etc/profile.d/conda.sh"

echo "Starting Snakemake at $(date)"
echo "Running on node: $(hostname)"
echo "Working directory: $(pwd)"

conda activate pypsa-eur

# Run workflow
snakemake --profile profiles/default \
  --configfile config/config.default.yaml \
  --rerun-incomplete \
  all

echo "Finished at $(date)"
