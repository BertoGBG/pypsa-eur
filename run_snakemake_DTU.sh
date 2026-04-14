#!/usr/bin/env bash

set -eo pipefail

REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"

source "$HOME/anaconda3/etc/profile.d/conda.sh"

echo "Starting Snakemake at $(date)"
echo "Running on node: $(hostname)"
echo "Working directory: $(pwd)"

conda activate pypsa-eur

# Run workflow
snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml \
  --rerun-incomplete \
  all

echo "Finished at $(date)"

# Send tail of err log by email (only when running on normal partition)
if [ "${SLURM_JOB_PARTITION:-}" = "normal" ]; then
    ERR_FILE="$REPO/log_snakemake/smk-${SLURM_JOB_ID}.err"
    {
        echo "Job ${SLURM_JOB_ID} finished at $(date)"
        echo "Exit status: $?"
        echo ""
        echo "--- Last 50 lines of err log ---"
        tail -50 "$ERR_FILE"
    } | mail -s "PyPSA-Eur job ${SLURM_JOB_ID} finished" albal@dtu.dk
fi
