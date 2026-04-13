# Running PyPSA-Eur on GenomeDK

## 1. Submit controller job

sbatch \
  --partition=short \
  --account=alamia \
  --time=12:00:00 \
  --cpus-per-task=1 \
  --mem=4G \
  -J smk-pypsaeur \
  -o /home/alamia/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.out \
  -e /home/alamia/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.err \
  /home/alamia/workspace/pypsa-eur_AA/pypsa-eur/run_snakemake_AU.sh

## 2. Monitor

squeue -u $USER

tail -f log_snakemake/smk-<jobid>.out
