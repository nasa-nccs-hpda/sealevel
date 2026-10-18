# BAM + FACTS2 workflow: handoff notes (written 2026-10-17)

Goal: run FACTS2 with BAM (bamber19-icesheets) using FEB branch `add_apptainer_command`,
emulating the reference `experiments/coupling.ssp585/config.yml` (the "experiment-ssp585" workflow).

## Findings / assumptions
- "experiment-ssp585" = `../experiments/coupling.ssp585/config.yml` (legacy FACTS config). In it, bamber19 is in workflow `wf4`.
- "FACTS2" = the `fact-sealevel` org + facts-experiment-builder (FEB) + per-module containers (NOT the legacy `../facts/` dir).
- `/explore/.../sealevel` and `/panfs/.../sealevel` are the same directory (same inode). Workspace is `facts2/`.
- No Docker; Apptainer 1.5.3 at /usr/bin/apptainer. ghcr.io and zenodo.org are reachable from this node.
- `uv` is not on PATH; installed at /panfs/ccds02/nobackup/people/gtamkin/uv-bin (add to PATH).
- FEB requires a climate step, so the experiment uses fair-temperature (as the reference does) + bamber19-icesheets.
- `--extremesealevel-step NONE` fails on this branch (looks up a module named NONE); omit the flag.
- Scratch worktree of the FEB branch for reading: $SCRATCH/feb-apptainer (can be removed with `git worktree remove`).
- Do NOT touch the uncommitted edits to notebooks/example-coupling-apptainer.sh and notebooks/fair_config.yaml.

## Done
- `feb init` in facts2/ (workspace, module registry clone)
- Data downloaded: data/module_specific_input_data/{bamber19-icesheets,fair-temperature}, data/shared_input_data/{FPRINT,location.lst}
  (location.lst copied from ../facts/experiments/coupling.ssp585/)
- `feb check-data`: 2/2 modules complete
- `feb setup-experiment` -> apptainer_experiments/bam_ssp585/experiment-config.yaml
  (ssp585, 2020-2150 step 10, baseyear 2005, nsamps 500, pipeline-id bam001, local scale)
- `feb generate-apptainer` -> apptainer_experiments/bam_ssp585/experiment-apptainer.sh
  (images: fair-temperature:0.2.1, bamber19-icesheets:0.2.0; SIFs go to apptainer_experiments/sif/)

## TODO (stages 4-6)
1. Run: `/usr/bin/time -v bash apptainer_experiments/bam_ssp585/experiment-apptainer.sh 2>&1 | tee run.log` (use sbatch/screen; pulls images first).
2. Verify outputs in apptainer_experiments/bam_ssp585/output-apptainer/{fair-temperature,bamber19-icesheets}/
   (expect climate.nc and {AIS,EAIS,WAIS,GIS}-{gslr,lslr}.nc); check dims with xarray (years 2020-2150, 500 samples).
3. Write Python driver notebooks/run_bam.py (style of notebooks/run_facts.py): validate config, run feb setup/generate, run the script, validate outputs. Do not edit the FEB script.
4. Add concise diagnostic comments to the driver/config, rerun, record evidence.
5. Write README section with copy-paste commands, I/O mapping table, runtime metrics, assumptions.

## Commands
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
