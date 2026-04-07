# Merge Plan: 5 Feature Branches → `a_CDRs`

## Branches to merge
All 5 branches fork from the same commit on `a_CDRs` (cb9ebde5). They are sibling branches with no parent-child dependencies.

## Merge Order

**biometh → biochar → EW → afforestation → perennialisation**

### Rationale
1. **biometh** (12 commits, smallest shared-file footprint) — establishes common "base" changes (costs year→2030, SLURM config, mem_mb fixes) that all other branches also include. Does NOT touch `build_corine_potentials.py` or `rules/retrieve.smk`, minimizing early conflicts.
2. **biochar** (12 commits) — brings in `build_corine_potentials.py` (shared with afforestation + EW). Only 1 unique file.
3. **EW** (10 commits) — also uses `build_corine_potentials.py` (already merged via biochar if identical). Adds EW-specific data/scripts.
4. **afforestation** (25 commits) — uses `build_corine_potentials.py` (already in). Adds `rules/retrieve.smk` changes.
5. **perennialisation** (29 commits, largest) — also touches `rules/retrieve.smk`. By going last, all base infrastructure is in place.

## Expected Conflicts Per Merge

Each merge will likely conflict in these files:
- **`scripts/prepare_sector_network.py`** — each branch adds its own `add_*()` function + call site (additive, resolvable)
- **`rules/build_sector.smk`** — each adds its own rules; common mem_mb deletion will conflict on 2nd+ merge (already applied)
- **`config/config.default.yaml`** — each adds sector-specific options; common costs changes conflict on 2nd+
- **`config/config.CDRs.yaml`** — full-file variants (afforestation/biochar/EW identical; perennialisation/biometh differ)
- **`config/plotting.default.yaml`** — each adds 1-5 lines of tech colors
- **`data/versions.csv`** — each adds 1-2 lines

Lower-risk shared files (likely identical changes, auto-resolve after first merge):
- `rules/build_electricity.smk`, `profiles/default/config.yaml`, `run_snakemake.sh`, `.gitignore`

## Procedure
For each merge:
1. `git checkout a_CDRs`
2. `git merge <branch>`
3. If conflicts arise, resolve by keeping both sets of additions (they are independent features)
4. `git add . && git commit`

## Notes
- `build_corine_potentials.py` is a new file added by 3 branches — if identical, first merge brings it in cleanly
- `.DS_Store` appears in perennialisation and biochar — should be gitignored
