# BAM + FACTS2 workflow: handoff notes (written 2026-10-17, updated 2026-10-18)

Goal: run FACTS2 with BAM (bamber19-icesheets) using FEB branch `add_apptainer_command`,
emulating the reference `experiments/coupling.ssp585/config.yml` (the "experiment-ssp585" workflow).

## Status: working end to end
Pipeline: ssp585 -> fair-temperature -> bamber19-icesheets -> facts-total, run with Apptainer. Experiments in `facts2/apptainer_experiments/`:
- `bam_ssp585_fixed` (the default of `run_bam.py` and the notebook): one site (New York), registry fix applied, totals = AIS + GIS.
- `bam_ssp585_fixed_gauges`: the same with 1,030 PSMSL tide gauges (`psmsl_gauges.lst`).
- `bam_ssp585`: the ORIGINAL experiment. Its totals double-count Antarctica; it is kept on purpose as the "before" for the notebook and the report.
  Do not use its totals.
Full driver runs (images cached): 221-233 s wall, exit 0, ~410 MB peak, 19/19 output checks. A cold run with image pulls takes ~7-9 min.
Details, I/O table and timings: `notebooks/README.md` (section "FACTS2 BAM ..."). Results: `notebooks/4_bam_ssp585_viz.ipynb`.

**Clean-workspace smoke test (2026-10-18).** A fresh `feb init` workspace (pristine registry `a085795`, inputs and images symlinked from this one),
driven only by `run_bam.py --workspace <fresh> --regenerate --experiment ...`, with no hand edits:
- *Without the patch:* it injected the facts-total workflow, generated the script, warned that the registry lacks the fix, found AIS listed with EAIS/WAIS and
  refused to run (exit 1, nothing executed, no run log).
- *After `git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch`:* no warning, the script passes only AIS and GIS, and the full run
  (233 s, exit 0, 19/19 checks) gave totals equal to AIS + GIS; its 10 output files are identical to `bam_ssp585_fixed` (max diff 0 mm).
**Clean-environment test (2026-10-18), nothing symlinked:** an empty workspace with its OWN downloads (the four Zenodo archives, record 7478192, about 340 MB:
`bamber19_icesheets_preprocess_data` -> `module_specific_input_data/bamber19-icesheets/`, `fair_temperature_fit_data` and `fair_temperature_preprocess_data`
-> `.../fair-temperature/`, `grd_fingerprints_data` -> `shared_input_data/`), `feb check-data` complete, patch applied, then `run_bam.py --regenerate`
with cold image pulls: 622.8 s (pulls 6m53s, models 3m30s), exit 0, totals = AIS+GIS, 19/19 checks; generated script and config identical to
`bam_ssp585_fixed`, 11 output files bit-identical. It also showed that `feb init` works inside a cloned `facts2/` (tracked marker and .gitignore do not conflict).
**Two defects found by this test and fixed in `run_bam.py`:** (1) FEB's `setup-experiment` never creates the parent dir `apptainer_experiments/`, so
`--regenerate` failed in an empty workspace (the driver now creates it; the earlier smoke test had missed this because symlinking the images created it);
(2) the generated scripts embed the absolute workspace path, so running a committed script from another checkout would read/write the ORIGINAL workspace;
preflight now refuses when a script's `WORKSPACE=` differs from the workspace in use. The README's setup section is the verified sequence.

## Known problems (read before trusting the totals)
- **facts-total double-counts Antarctica: fixed in our experiments by a local registry patch; upstream fix proposed (fact-sealevel/facts-module-registry#20, open), not merged.**
  *Current state:* `bam_ssp585_fixed` and `bam_ssp585_fixed_gauges` give correct totals (AIS + GIS) because the registry change is applied. The change is
  tracked as `facts2/patches/bamber19_pass_to_total.patch` (4 lines, applies cleanly to registry `a085795`). The workspace's registry clone
  (`facts2/facts-module-registry`, git-ignored) has it applied; a fresh `feb init` does NOT, so run
  `git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch` first (the README commands do). `run_bam.py --regenerate` warns if it is missing,
  and before any run `run_bam.py` checks the generated script's facts-total `--item` lines and refuses if AIS is listed with EAIS/WAIS
  (`--allow-double-count` overrides; `--skip-run` only warns); after a run it checks the output totals. The upstream registry still lacks the fix:
  reported as issue fact-sealevel/facts-experiment-builder#144 and fix proposed as PR fact-sealevel/facts-module-registry#20, both opened 2026-10-18 and open at the time of writing (the PR is from the
  `gtamkin` fork, branch `bamber19-pass-to-total-eais-wais`, +4 lines); the write-up text is `facts2/REPORT_facts_total_double_count.md`.
  If the PR is merged and the registry clone is updated, `git apply` of the local patch will fail because the change is already there: then drop the patch step.
  *Background, kept for the record:* FEB passes all four bamber19 outputs (AIS, EAIS, WAIS, GIS) to facts-total; AIS already equals EAIS + WAIS, so the
  original experiment's total is AIS+EAIS+WAIS+GIS exactly. Correct total = AIS + GIS. 2150 global median: 1312 mm generated vs 914 mm correct (+44%).
  The experiment config cannot fix this (its workflows select modules, not outputs); the fix belongs in the registry entry, and the generated scripts
  were deliberately not edited.
  **Cause (confirmed):** `facts-module-registry/bamber19-icesheets/bamber19_icesheets_module.yaml` (registry `a085795`) sets no `pass_to_total`
  on any output; FEB defaults it to `True` (`core/module/arg_specs.py`) and only skips outputs marked `false` (`application/execution_plan.py`).
  `emulandice-ais` already does it right (AIS total `true`, EAIS/WAIS/PEN `false`). The registry's contributor guide never mentions `pass_to_total`.
  **Fix (tested end to end):** `pass_to_total: false` on `output-{EAIS,WAIS}-{gslr,lslr}-file`. With it the full pipeline (4:00, exit 0) passed only
  AIS+GIS to facts-total and the totals equal AIS+GIS exactly (max diff 0 mm; 2150 medians 914 mm global / 707 mm New York vs 1312 / 1181 for the
  original). Bamber outputs were bit-identical to the earlier run (seeded).
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
- **Sample pairing (checked 2026-10-18): weak and stochastic, NOT paired trajectories.** In the container's code
  (`/opt/bamber19-icesheets/src/bamber19_icesheets/bamber19_icesheets_project.py`, `pickScenario`), climate member j only decides whether output
  sample j is drawn from Bamber's HIGH or LOW pool: P(high) = clip((iSAT_j - 142.5)/100, 0, 1), iSAT = temperature (vs 1850-1900) summed over 2000-2099 in
  degC*yr, via `rng.random() < P`. Which ice-sheet realisation is drawn from the pool (`sample_inds`) is an independent random draw. Under ssp585
  300 of 500 members have P = 1 and the mean P is 0.91, so 91% of samples come from the high pool whatever the member (2150 GIS median 457 mm high pool vs
  209 mm low pool). Tests: (1) replicating the selection from climate.nc predicted exactly which 68 of 500 samples change when the climate members are
  shuffled and BAM is re-run with the same seed; all 68 changed and the other 432 stayed bit-identical (unshuffled control reproduces the real run, 0 mm);
  (2) Spearman(iSAT_j, output_j) is +0.05 to +0.07 vs a shuffled-pairing null of 0.00 +/- 0.045, i.e. almost no per-sample link. Consequence: do not plot or
  describe per-sample temperature vs ice-loss as paired trajectories; ensemble-level statements are fine. Also from the code (not tested here): with a
  climate file BAM ignores `--nsamps` and uses the number of climate members.

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
- Real location list (2026-10-18): `psmsl_gauges.lst` + experiment `bam_ssp585_fixed_gauges` (fixed registry, 1,030 sites). Run 227.5 s, exit 0, all output checks OK.
  Verified: global outputs and the New York site identical to the one-site run (0 mm), local total = AIS + GIS at all sites. `run_bam.py` now
  reports final-year medians correctly for many sites; the notebook has a site selector and a factor map (`facts2/figures/4b_site_factor_map.png`).
  (The `bam_results.json` inside `bam_ssp585_fixed_gauges/` was written by the older driver; its pooled local medians are not meaningful.)
- Git: experiment config, generated script, `location.lst` and ignore rules are tracked; data, SIFs, outputs, logs, backups are ignored.

## Tests
`notebooks/tests/test_run_bam.py` (25 unittest tests, standard library; netCDF tests need xarray + netCDF4 + numpy and skip otherwise) guard the driver's
safeguards: AIS-with-EAIS/WAIS script check, other-workspace script refusal, `registry_has_fix` and the tracked patch, `main()` run/override/skip-run behaviour, and
`validate_outputs` (totals, many-site median definition, missing files). Verified by mutation: seven deliberate breakages in a scratch copy were all caught.
Command and caveats: `notebooks/README.md`, section "Tests". What to present and the caveats that must accompany it: section "What to present".

## Open items
1. (posted 2026-10-18) Issue fact-sealevel/facts-experiment-builder#144 and 4-line PR fact-sealevel/facts-module-registry#20 (links: https://github.com/fact-sealevel/facts-experiment-builder/issues/144 ,
   https://github.com/fact-sealevel/facts-module-registry/pull/20). Follow up: watch both for maintainer feedback (they may prefer keeping EAIS+WAIS and dropping
   AIS instead; the same four lines then apply to the AIS outputs). When merged: update the registry clone, remove the patch step from the README and
   `facts2/patches/`, and re-verify `--regenerate` against the unpatched upstream registry.
   Housekeeping: the fork `gtamkin/facts-module-registry` was created for the PR (delete it once the PR is closed); `gh` v2.102.0 is installed at
   `/panfs/ccds02/nobackup/people/gtamkin/uv-bin/gh` and is currently LOGGED OUT (2026-10-18; the local token was removed). The login used for the issue/PR
   had scopes repo, read:org, gist; logging out does not revoke it on GitHub, so revoke "GitHub CLI" at github.com/settings/applications if not done yet.
   Any follow-up on the PR needs a fresh `gh auth login`.
2. (done) Real location list: see "Done". Open question: a different or smaller site set (e.g. a curated few dozen coastal cities) if 1,030 is too many to show.
3. (done 2026-10-18) `run_bam.py --regenerate` verified from a clean workspace, including the model run: see "Clean-workspace smoke test" under Status.
4. (done 2026-10-18) FAIR/BAM sample pairing checked: see "Sample pairing" above. Reproduce with `notebooks/check_bam_pairing.py` (replicates `pickScenario`, re-runs BAM with shuffled climate members, ~40 s; exit 0 = predictions held):
   `cd facts2 && env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 --with h5py --with xarray --with netcdf4 --with 'numpy<2' python ../notebooks/check_bam_pairing.py`

## Commands
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
cd facts2 && uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v   # run + validate
