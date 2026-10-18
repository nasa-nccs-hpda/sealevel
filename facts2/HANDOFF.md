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
  **Cause (confirmed):** `facts-module-registry/bamber19-icesheets/bamber19_icesheets_module.yaml` (registry `a085795`) sets no `pass_to_total`
  on any output; FEB defaults it to `True` (`core/module/arg_specs.py`) and only skips outputs marked `false` (`application/execution_plan.py`).
  `emulandice-ais` already does it right (AIS total `true`, EAIS/WAIS/PEN `false`). The registry's contributor guide never mentions `pass_to_total`.
  **Fix (tested end to end, 2026-10-18):** add `pass_to_total: false` to `output-{EAIS,WAIS}-{gslr,lslr}-file` (4 lines). In a scratch workspace
  with that change, the full pipeline (4:00, exit 0) passed only AIS+GIS to facts-total and the totals equal AIS+GIS exactly (max diff 0 mm;
  2150 medians 914 mm global / 707 mm New York vs 1312 / 1181 generated). Bamber outputs were bit-identical to the earlier run (seeded).
  The scratch test lived in the session scratchpad and is not kept; to redo it: patch a fresh `feb init` registry, run setup-experiment, add the
  `workflows:` entry, generate-apptainer, check the `--item=` lines, run.
  `notebooks/run_bam.py` reports the double-count as a warning; the notebook plots the correct total. The real workspace still has the unfixed totals.
  Write-up for the maintainers: `facts2/REPORT_facts_total_double_count.md`.
- **Apptainer build env on this node.** Shell has `APPTAINER_TMPDIR`/`APPTAINER_CACHEDIR` pointing at a nonexistent
  `/explore/nobackup/people/gtamkin/containers/cache`; panfs builds fail in mksquashfs under proot; `/tmp` and `/var/tmp` are `noexec`.
  `/dev/shm` works. `run_bam.py` sets the three env vars per run (APPTAINER_TMPDIR, APPTAINER_CACHEDIR, PROOT_TMP_DIR) in a per-run subdir
  it deletes afterward; the generated script is not edited. If running the script by hand, export them yourself.
- `generate-apptainer` emits no facts-total stage unless `experiment-config.yaml` has a `workflows:` entry
  (`all-modules: "bamber19-icesheets"`, under the "Workflows (facts-total)" heading). `setup-experiment` leaves it empty non-interactively.
- `location.lst` has one site (New_York, 40.70, -74.01), so `*-lslr.nc` have one location and BAM runs in seconds. For a real list use
  `data/shared_input_data/psmsl_gauges.lst` (1,030 tide gauges = entries with id <= 10000 of `../facts/input_files/location.lst`; the other ~65,000
  entries are a 1-degree grid and were left out) via the experiment `bam_ssp585_fixed_gauges`. Local = global x a constant per ice sheet AND site
  (New York: EAIS 1.04, WAIS 1.22, GIS 0.44), identical for all samples. Station names are not unique (e.g. two SYDNEY), ids are.
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
- Result figures in `facts2/figures/` (from the notebook); recipe for adding a module, with BAM annotated: `INTEGRATING_A_MODULE.md`.
- Real location list (2026-10-18): `psmsl_gauges.lst` + experiment `bam_ssp585_fixed_gauges` (fixed registry, 1,030 sites). Run 227.5 s, exit 0, 18/18 checks.
  Verified: global outputs and the New York site identical to the one-site run (0 mm), local total = AIS + GIS at all sites. `run_bam.py` now
  reports final-year medians correctly for many sites; the notebook has a site selector and a factor map (`facts2/figures/4b_site_factor_map.png`).
  (The `bam_results.json` inside `bam_ssp585_fixed_gauges/` was written by the older driver; its pooled local medians are not meaningful.)
- Git: experiment config, generated script, `location.lst` and ignore rules are tracked; data, SIFs, outputs, logs, backups are ignored.

## Open items
1. Send the double-count report to the maintainers: issue on `fact-sealevel/facts-experiment-builder` plus a 4-line PR to
   `fact-sealevel/facts-module-registry` (text in `REPORT_facts_total_double_count.md`). Not posted yet; posting is outward-facing, user decides.
2. (done) Real location list: see "Done". Open question: a different or smaller site set (e.g. a curated few dozen coastal cities) if 1,030 is too many to show.
3. `run_bam.py --regenerate` has not been run (setup + generate + workflows injection are untested).
4. Optional: confirm FAIR/BAM sample pairing from the bamber19 module's sampling code.

## Commands
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
cd facts2 && uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v   # run + validate
