# BAM + FACTS2 workflow: handoff notes (written 2026-10-17, updated 2026-10-18)

Goal: run FACTS2 with BAM (bamber19-icesheets) using FEB branch `add_apptainer_command`,
emulating the reference `experiments/coupling.ssp585/config.yml` (the "experiment-ssp585" workflow).

## Status: working end to end
Pipeline: ssp585 -> fair-temperature -> bamber19-icesheets -> facts-total, run with Apptainer. Latest full run via the driver:
221.5 s wall, exit 0, 410 MB peak, 18/18 output checks OK (images cached). A cold run with image pulls takes ~7-9 min.
Details, I/O table and timings: `notebooks/README.md` (section "FACTS2 BAM ..."). Results: `notebooks/4_bam_ssp585_viz.ipynb`.

## Known problems (read before trusting the totals)
- **facts-total double-counts Antarctica.** FEB passes all four bamber19 outputs (AIS, EAIS, WAIS, GIS) to facts-total; AIS already equals
  EAIS + WAIS, so the generated total = AIS+EAIS+WAIS+GIS exactly. Correct total = AIS + GIS. 2150 global median: 1312 mm generated vs 914 mm
  correct (+44%). Not fixable from the config (workflows select modules, not outputs); the generated script was deliberately not edited.
  Suspected cause (unconfirmed): output tagging in the module registry. Should be raised with the FEB / registry maintainers.
  `notebooks/run_bam.py` reports it as a warning; the notebook plots the correct total.
- **Apptainer build env on this node.** Shell has `APPTAINER_TMPDIR`/`APPTAINER_CACHEDIR` pointing at a nonexistent
  `/explore/nobackup/people/gtamkin/containers/cache`; panfs builds fail in mksquashfs under proot; `/tmp` and `/var/tmp` are `noexec`.
  `/dev/shm` works. `run_bam.py` sets the three env vars per run (APPTAINER_TMPDIR, APPTAINER_CACHEDIR, PROOT_TMP_DIR) in a per-run subdir
  it deletes afterward; the generated script is not edited. If running the script by hand, export them yourself.
- `generate-apptainer` emits no facts-total stage unless `experiment-config.yaml` has a `workflows:` entry
  (`all-modules: "bamber19-icesheets"`, under the "Workflows (facts-total)" heading). `setup-experiment` leaves it empty non-interactively.
- `location.lst` has one site (New_York, 40.70, -74.01), so `*-lslr.nc` have one location and BAM runs in seconds. Local = global x a constant
  per ice sheet (EAIS 1.04, WAIS 1.22, GIS 0.44) for all samples.
- Not checked: whether BAM sample i pairs with fair-temperature sample i (module sampling logic not read); do not claim paired trajectories.

## Findings / assumptions
- "experiment-ssp585" = `../experiments/coupling.ssp585/config.yml` (legacy FACTS config). In it, bamber19 is in workflow `wf4`.
- "FACTS2" = the `fact-sealevel` org + facts-experiment-builder (FEB) + per-module containers (NOT the legacy `../facts/` dir).
- `/explore/.../sealevel` and `/panfs/.../sealevel` are the same directory (same inode). Workspace is `facts2/`.
- No Docker; Apptainer 1.5.3 at /usr/bin/apptainer. ghcr.io and zenodo.org are reachable from this node. No `node` (so the dataviz palette
  validator was not run; notebook colours rely on the reference palette's documented all-pairs result for its first three slots).
- `uv` is not on PATH; installed at /panfs/ccds02/nobackup/people/gtamkin/uv-bin (add to PATH).
- FEB requires a climate step, so the experiment uses fair-temperature (as the reference does) + bamber19-icesheets.
- `--extremesealevel-step NONE` fails on this branch (looks up a module named NONE); omit the flag.
- The facts-total image is pulled twice (same image, two names, ~1.5 min each, one time only).
- Do NOT touch the uncommitted edits to notebooks/example-coupling-apptainer.sh and notebooks/fair_config.yaml
  (the root .gitignore also has an uncommitted line from someone else; leave it).

## Done
- `feb init` in facts2/ (workspace, module registry clone); data downloaded; `feb check-data` 2/2 complete.
- `feb setup-experiment` + `feb generate-apptainer` -> apptainer_experiments/bam_ssp585/{experiment-config.yaml,experiment-apptainer.sh}
  (ssp585, 2020-2150 step 10, baseyear 2005, nsamps 500, pipeline-id bam001, local scale; images fair-temperature:0.2.1,
  bamber19-icesheets:0.2.0, facts-total:0.2.1).
- Ran the experiment; verified outputs with xarray (500 samples, 14 years 2020-2150, no NaNs, AIS = EAIS + WAIS to 0.001 mm).
- `notebooks/run_bam.py` (driver: config validation, preflight, timed run, output validation incl. facts-total check -> `bam_results.json`).
- README section and `notebooks/4_bam_ssp585_viz.ipynb` (stored without outputs; run it before viewing).
- Git: experiment config, generated script, `location.lst` and ignore rules are tracked; data, SIFs, outputs, logs, backups are ignored.

## Open items
1. Raise the facts-total double-count with FEB / registry maintainers.
2. Use a real location list if local results matter (currently one site).
3. `run_bam.py --regenerate` has not been run (setup + generate + workflows injection are untested).
4. Optional: confirm FAIR/BAM sample pairing from the bamber19 module's sampling code.

## Commands
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
cd facts2 && uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v   # run + validate
