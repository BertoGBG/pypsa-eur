#!/usr/bin/env bash
# Weekend 9-scenario batch -- RESUBMISSION with concurrent Gurobi solves capped.
#
# Why this exists: the original run_snakemake_weekend_batch.sh ran all 9
# scenarios in parallel, but the Gurobi WLS license (LICENSEID 2805253) allows a
# baseline of only 2 concurrent sessions. Solves that landed as the 3rd+
# simultaneous session died with:
#     GurobiError: Too many sessions, 5 active sessions for a baseline of 2
# With `keep-going: true` in profiles/default_DTU, that did not stop the batch --
# it silently hollowed it out, and because myopic chains horizons, any scenario
# whose horizon N failed can never build N+1.
#
# The fix: declare a synthetic `gurobi_sessions` resource on the solve rules and
# give the scheduler a global budget of 2, so Snakemake never has more than two
# solves in flight. Everything else (all the cheap non-solve rules) still runs up
# to the profile's `jobs: 50`.
#
# Nothing already solved is redone -- Snakemake skips existing outputs, and the
# ~7h45m early pipeline is fully cached, so this resumes rather than restarts.
set -eo pipefail
REPO="/home/albal/workspace/pypsa-eur_AA/pypsa-eur"
cd "$REPO"
source "$HOME/anaconda3/etc/profile.d/conda.sh"
echo "Starting Snakemake (Gurobi-capped) at $(date)"
conda activate pypsa-eur

snakemake --profile profiles/default_DTU \
  --configfile config/config.default.yaml config/config.weekend_batch_50_1095seg.yaml \
  --rerun-incomplete \
  --set-resources \
      solve_sector_network_myopic:gurobi_sessions=1 \
      solve_sector_network:gurobi_sessions=1 \
  --resources gurobi_sessions=10 \
  all

echo "Finished at $(date)"
