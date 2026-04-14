# Running PyPSA-Eur on GenomeDK

## 1. Submit controller job - short
sbatch \
  --partition=short \
  --account=albal \
  --time=12:00:00 \
  --cpus-per-task=1 \
  --mem=4G \
  -J smk-pypsaeur \
  -o /home/albal/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.out \
  -e /home/albal/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.err \
  /home/albal/workspace/pypsa-eur_AA/pypsa-eur/run_snakemake_DTU.sh

## 1. Submit controller job - long
sbatch \
  --partition=normal \
  --account=albal \
  --time=24:00:00 \
  --cpus-per-task=1 \
  --mem=4G \
  -J smk-pypsaeur \
  -o /home/albal/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.out \
  -e /home/albal/workspace/pypsa-eur_AA/pypsa-eur/log_snakemake/smk-%j.err \
  /home/albal/workspace/pypsa-eur_AA/pypsa-eur/run_snakemake_DTU.sh


## 2. Monitor

squeue -u $USER

tail -f log_snakemake/smk-<jobid>.out
tail -f log_snakemake/smk-<jobid>.err
