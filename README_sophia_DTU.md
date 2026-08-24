# Running PyPSA-Eur on Sophia (DTU)

## 0. Connect

```
ssh albal@sophia.dtu.dk
cd /home/albal/workspace/pypsa-eur_AA/pypsa-eur
```

## 1. Start tmux session

```
tmux new -t pypsa
```

To reconnect after disconnect:
```
tmux a -t pypsa
```

## 2. Check cluster status

```
sinfo
```

## 3. Activate environment

```
conda activate pypsa-eur
```

## 4. Dry run (always do this first)

```
./snakemake_cluster prepare_sector_networks -j 10 --configfile config/config.default.yaml config/config.sophia.yaml -n
```

## 5. Run preparation steps

```
./snakemake_cluster prepare_sector_networks -j 10 --configfile config/config.default.yaml config/config.sophia.yaml --keep-going
```

## 6. Run solve (FAT nodes, 256 GB RAM)

Dry run first:
```
./snakemake_solve_fat solve_sector_networks -j 4 --configfile config/config.default.yaml config/config.sophia.yaml -n
```

Then run:
```
./snakemake_solve_fat solve_sector_networks -j 4 --configfile config/config.default.yaml config/config.sophia.yaml --keep-going
```

## 7. Monitor

```
squeue -u $USER

tail -f slurm_logs/slurm-<jobid>.out
tail -f slurm_logs/slurm-<jobid>.err
```

## After first git pull (or cloning)

```
chmod u+x snakemake_cluster snakemake_solve_fat
```

Git does not preserve execute permissions on new files, so this is required once after pulling these scripts for the first time.

## Notes

- Submit from login node if jobs take long to dispatch (no time limit)
- Submit from interactive node (`ssh sn402`) for faster disk I/O on short runs
- `-j 4` on solve limits simultaneous fat node jobs — do not increase without checking fatq availability
- Always use `tmux` so a dropped connection does not kill the Snakemake controller
