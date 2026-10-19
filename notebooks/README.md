
# sealevel/notebooks directory

- Python project to orchestrate modules within the Framework for Accessing Changes To Sea-level (FACTS).  

## Objectives

- These Notebooks run in Discover jupyter hub:  https://jh-discover.nccs.nasa.gov.  Execute in the order below and if any fail, consult the NOTE below:
1. [Runs select FACTS modules (e.g., fair, lws, and stereodynamics) and aggregates total sealevel deltas](https://github.com/nasa-nccs-hpda/sealevel/blob/main/notebooks/1_fair_facts_v2_aggregate.ipynb) ~5 minutes
3. [Visualizes total sealevel deltas from previous output ](https://github.com/nasa-nccs-hpda/sealevel/blob/main/notebooks/3_fair_facts_v2_total_viz.ipynb) ~2 minutes

NOTES:

1) For kernel selection, use 'conda env:base' for 3_fair_facts_v2_viz_total, and  'conda env:viz' for the others.  
2) Restart and clear kernel outputs between runs.
3) The workflows will not overwrite existing data files, so manual intervention is required if a workflow fails when attempting to write output files. 
4) Depending on the runtime environment where the Notebooks are launched, certain Python packages may reach out to pull in other dependencies.  If running on 
the Discover jupyter hub, the gpu node has no internet access allowed, so these dependencies cannot be resolved.  A workaround is to temporarily convert the Notebook
to a Python application and run it from the command line.  After a successful run, the Notebook should work also because it can now resolve the dependencies. 

A sample Discover session follows:
```python
gtamkin@GSLAL032412001:/Users/gtamkin$ ssh -XY gtamkin@discover.nccs.nasa.gov
gtamkin@discover14:/home/gtamkin$ cd /tmp
gtamkin@discover14:/tmp$ git clone https://github.com/nasa-nccs-hpda/sealevel.git
Cloning into 'sealevel'...
remote: Enumerating objects: 538, done.
remote: Counting objects: 100% (538/538), done.
remote: Compressing objects: 100% (338/338), done.
remote: Total 538 (delta 176), reused 499 (delta 155), pack-reused 0 (from 0)
Receiving objects: 100% (538/538), 16.56 MiB | 39.89 MiB/s, done.
Resolving deltas: 100% (176/176), done.
gtamkin@discover14:/tmp$ cd sealevel/notebooks/
gtamkin@discover14:/tmp/sealevel/notebooks$ module load anaconda
activate base
(base) gtamkin@discover14:/tmp/sealevel/notebooks$ jupyter nbconvert --to python 3_fair_facts_v2_total_viz.ipynb 
[NbConvertApp] Converting notebook 3_fair_facts_v2_total_viz.ipynb to python
[NbConvertApp] Writing 187627 bytes to 3_fair_facts_v2_total_viz.py
(base) gtamkin@discover14:/tmp/sealevel/notebooks$ python 3_fair_facts_v2_total_viz.py 
```
Error Handling:
```python

# If you see the following error, go back and run the first notebook(s) from Jupyter Hub to seed the input directories

./data/output/fair:
  (directory doesn't exist)

./data/output/lws:
  (directory doesn't exist)

./data/output/sterodynamics:
  (directory doesn't exist)
Loading output files...
  - Not found: data/output/fair/climate.nc
  - Not found: data/output/fair/gsat.nc
  - Not found: data/output/fair/oceantemp.nc
  - Not found: data/output/fair/ohc.nc
  - Not found: data/output/lws/gslr.nc
  - Not found: data/output/lws/lslr.nc
  - Not found: data/output/sterodynamics/gslr.nc
  - Not found: data/output/sterodynamics/lslr.nc

⚠ No datasets loaded. Please run the workflow first to generate outputs.
================================================================================
VERIFYING SEA LEVEL TOTALS
================================================================================
. . . . .

(base) gtamkin@discover14:/tmp/sealevel/notebooks$ python 3_fair_facts_v2_total_viz.py 

./data/output/fair:
  (directory doesn't exist)

./data/output/lws:
  (directory doesn't exist)

./data/output/sterodynamics:
  (directory doesn't exist)
Loading output files...
  - Not found: data/output/fair/climate.nc
  - Not found: data/output/fair/gsat.nc
  - Not found: data/output/fair/oceantemp.nc
  - Not found: data/output/fair/ohc.nc
  - Not found: data/output/lws/gslr.nc
  - Not found: data/output/lws/lslr.nc
  - Not found: data/output/sterodynamics/gslr.nc
  - Not found: data/output/sterodynamics/lslr.nc

⚠ No datasets loaded. Please run the workflow first to generate outputs.
================================================================================
VERIFYING SEA LEVEL TOTALS
================================================================================

============================================================
VERIFYING LSLR TOTALS
============================================================

Traceback (most recent call last):
  File "/home/gtamkin/.local/lib/python3.11/site-packages/xarray/backends/file_manager.py", line 219, in _acquire_with_cache_info
    file = self._cache[self._key]
           ~~~~~~~~~~~^^^^^^^^^^^
  File "/home/gtamkin/.local/lib/python3.11/site-packages/xarray/backends/lru_cache.py", line 56, in __getitem__
    value = self._cache[key]
            ~~~~~~~~~~~^^^^^
KeyError: [<class 'netCDF4._netCDF4.Dataset'>, ('/tmp/sealevel/notebooks/data/output/totaled_output_all_lslr.nc',), 'r', (('clobber', True), ('diskless', False), ('format', 'NETCDF4'), ('persist', False)), 'f3201492-c53a-4140-9ce6-5d36141b7e1a']
```




## FACTS2 BAM (bamber19-icesheets) + fair-temperature, ssp585, via Apptainer

Emulates `experiments/coupling.ssp585` workflow `wf4` (bamber19) using the `fact-sealevel` containers and
facts-experiment-builder (FEB) branch `add_apptainer_command`. Workspace: `facts2/`. No Docker; Apptainer 1.5.3.

### Setup from scratch (verified in an empty workspace with its own downloads and a cold image pull, 2026-10-18)
Needs Apptainer, `uv`/`uvx`, and network access to `zenodo.org` and `ghcr.io`. About 340 MB of input data and about 700 MB of images (four SIF files) are fetched.
```bash
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH     # uv
git clone <this repository> && cd sealevel/facts2                    # facts2/ is the workspace
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
$FEB init                                      # creates experiments/ and clones the module registry (pristine upstream)
# REQUIRED until the registry is fixed upstream: without it facts-total double-counts Antarctica (see Assumptions below)
git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch

# Input data: the four Zenodo archives listed in the registry YAML headers, unpacked into the layout FEB expects.
# (location.lst and psmsl_gauges.lst are already in the repo; tar prints harmless "unknown extended header" warnings.)
Z=https://zenodo.org/record/7478192/files; D=$(mktemp -d); M=data/module_specific_input_data
for f in bamber19_icesheets_preprocess_data fair_temperature_fit_data fair_temperature_preprocess_data grd_fingerprints_data; do
  curl -L -o $D/$f.tgz $Z/$f.tgz; done
mkdir -p $M/bamber19-icesheets $M/fair-temperature data/shared_input_data
tar xzf $D/bamber19_icesheets_preprocess_data.tgz -C $M/bamber19-icesheets
tar xzf $D/fair_temperature_fit_data.tgz          -C $M/fair-temperature
tar xzf $D/fair_temperature_preprocess_data.tgz   -C $M/fair-temperature
tar xzf $D/grd_fingerprints_data.tgz              -C data/shared_input_data
$FEB check-data                                # expect: bamber19-icesheets 1/1, fair-temperature 2/2, all modules complete

# Generate a NEW experiment, run it and validate it, in one step and with no hand edits (the driver adds the facts-total workflow,
# creates apptainer_experiments/, sets the Apptainer build env, times the run and checks the outputs; the first run also pulls the images)
uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py --regenerate \
    --experiment apptainer_experiments/my_run -v
```
Result of this exact sequence in an empty workspace: input data byte-identical to the original workspace's, `check-data` complete, a generated script and config
identical to `bam_ssp585_fixed`, a cold run of 10m23s (about 6m53s of it pulling images, 3m30s of models), exit 0, totals equal to AIS + GIS, 19/19 output checks,
and all 11 compared output files bit-identical to the original run.

**Do not run the committed experiments from another checkout.** The generated `experiment-apptainer.sh` files embed the absolute path of the workspace
they were generated in (`WORKSPACE=...`), so a clone elsewhere would read and write the original location. `run_bam.py` now refuses (exit 1, nothing executed)
when a script's workspace differs from the one it is run in; use `--regenerate --experiment <new name>` as above. The committed configs and scripts are the
record of what was run, not portable run scripts.

### Other ways to run
```bash
cd .../facts2        # the workspace in which the experiment was generated
# Run + validate an existing experiment (defaults to apptainer_experiments/bam_ssp585_fixed; the original, double-counting experiment is bam_ssp585,
# kept as the "before"). Results go to <experiment>/bam_results.json.
uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v
# Before running, the driver checks the script's facts-total --item lines and refuses (exit 1, nothing executed) if AIS is added together with
# EAIS/WAIS; --allow-double-count overrides it (e.g. to redo bam_ssp585), and --skip-run only validates existing outputs and warns.

# Or run the generated script directly (export the three env vars first; /tmp is noexec here, /dev/shm works)
D=/dev/shm/apptainer_build; mkdir -p $D/proot $D/cache
APPTAINER_TMPDIR=$D APPTAINER_CACHEDIR=$D/cache PROOT_TMP_DIR=$D/proot \
  /usr/bin/time -v bash apptainer_experiments/bam_ssp585_fixed/experiment-apptainer.sh 2>&1 | tee run.log
```

### Inputs / outputs
| Stage | Module (image) | Inputs (under `facts2/data/`) | Outputs (under `apptainer_experiments/<experiment>/output-apptainer/`) |
|---|---|---|---|
| 1 | fair-temperature (`ghcr.io/fact-sealevel/fair-temperature:0.2.1`) | `module_specific_input_data/fair-temperature/{rcmip,parameters}` | `fair-temperature/{climate,gsat,oceantemp,ohc}.nc` |
| 2 | bamber19-icesheets (`ghcr.io/fact-sealevel/bamber19-icesheets:0.2.0`) | `fair-temperature/climate.nc`, `module_specific_input_data/bamber19-icesheets/SLRProjections190726core_SEJ_full.mat`, `shared_input_data/{FPRINT,location.lst}` | `bamber19-icesheets/{AIS,EAIS,WAIS,GIS}-{gslr,lslr}.nc` |
| 3 | facts-total (`ghcr.io/fact-sealevel/facts-total:0.2.1`), one global + one local job | all 8 `bamber19-icesheets/*.nc` files | `facts-total/all-modules_{global,local}_total.nc` (**double-counts Antarctica in `bam_ssp585`; fixed in `bam_ssp585_fixed`, see below**) |

Parameters: ssp585, years 2020-2150 step 10 (14 steps), baseyear 2005, nsamps 500, pipeline-id bam001, seeds 2314 (fair) / 1423 (bamber).
Output shape: `sea_level_change(samples=500, years=14, locations=1)` in mm; AIS = EAIS + WAIS (checked to 0.001 mm).
Example 2150 global medians (mm): AIS 403, EAIS 49, WAIS 344, GIS 420.

### Runtime metrics (forest204, 12 cores)
| Run | Wall | fair-temperature | bamber19 | Peak RSS | Notes |
|---|---|---|---|---|---|
| First (cold) | 8m54s | 3m50s | 7s | 618 MB | includes pulling 2 images (~5 min) |
| Rerun via `run_bam.py` (images cached) | 3m58s | 3m51s | 8s | 412 MB | 13/13 output checks OK (before facts-total was added) |
| With facts-total (first run, pulls its image) | 7m20s | 3m57s | 8s | 413 MB | the facts-total image is pulled twice (same image, two names), ~1.5 min each |
| Full `run_bam.py` run with facts-total (images cached) | 3m42s | 3m30s | 7s | 410 MB | facts-total 4s (global and local run in parallel); 18/18 output checks OK |

| `bam_ssp585_fixed_gauges`, 1,030 sites (images cached) | 3m48s | 3m25s | 17s | 412 MB | facts-total 3-5 s; 18/18 checks OK |
| Clean workspace, own downloads, cold image pulls (4 pulls) | 10m23s | 3m19s | 7s | 445 MB | pulls 6m53s; facts-total 4 s; 19/19 checks OK |

SIFs: fair-temperature 200 MB, bamber19-icesheets 165 MB (`apptainer_experiments/sif/`); facts-total is pulled under two names.

### Real location list: 1,030 tide gauges (`bam_ssp585_fixed_gauges`)
`facts2/data/shared_input_data/psmsl_gauges.lst` is the tide-gauge part of the master FACTS list (`facts/input_files/location.lst`): its first 1,030 entries,
ids up to 10000, tab-separated `name id lat lon`, latitudes -65 to 81. The other ~65,000 entries of the master list are a 1-degree global grid
(`grid_<lat>_<lon>`) and were left out. `location.lst` (New York only) is unchanged, so the earlier experiments still reproduce.
The experiment `apptainer_experiments/bam_ssp585_fixed_gauges` is `bam_ssp585_fixed` with `--location-file psmsl_gauges.lst`; its script differs
only in that one flag. Run it with `run_bam.py --experiment apptainer_experiments/bam_ssp585_fixed_gauges` (3m48s; BAM takes 17 s instead of 7 s).
Note on summary numbers: with many sites the driver's `p50_last_*` values (in `bam_results.json`, defined in its `p50_last_definition` entry) and the
medians in its warnings are the median across sites of the per-site final-year medians, not a pooled median over all samples and sites.
Local outputs then have `locations = 1030` (the `locations` coordinate holds the station ids, in list order; `lat`/`lon` per site); global outputs
still have one location. Checks against the one-site run: global outputs and the New York site (id 12) are identical (max diff 0 mm), and the local
total equals AIS + GIS at every site (max diff 0 mm). The local / global factor is still constant per site, but varies strongly by site, for example
Greenland 1.22 at Honolulu, 0.44 at New York and 0.10 at Stockholm, and below 0 close to the ice sheet (Reykjavik -1.71; West Antarctica at the Argentine
Islands -4.57), i.e. sea level falls locally there.

### Results notebook
[`4_bam_ssp585_viz.ipynb`](4_bam_ssp585_viz.ipynb) reads the netCDF outputs (no containers needed, runs in seconds) and shows: the ssp585 warming
fan, the three ice-sheet contributions through time, their 2150 distributions, the local / global factor per ice sheet at one site (`BAM_SITE`, a station name or id, default New York), a map of that factor
across every site (when the experiment has several, e.g. `BAM_EXPERIMENT=bam_ssp585_fixed_gauges`), the total before and after the registry fix (the fixed experiment's `facts-total`
against the original's), and a run card from the experiment's `bam_results.json`. It reads `bam_ssp585_fixed` by default; set `BAM_EXPERIMENT` to read another
experiment (pointed at `bam_ssp585` it prints a double-count warning). It needs `xarray`, `netcdf4`, `matplotlib` and `pandas`; set `FACTS2_WORKSPACE` if the
workspace is not at `../facts2`, and `FIG_DIR` to also save the PNGs (saved copies are in `facts2/figures/`). It is stored without outputs, so run it before viewing. The older `fair_facts_v2_*` / `3_fair_facts_v2_*`
viz notebooks expect the lws / sterodynamics layout under `./data/output` and were not reused.

### What to present
- **Lead with the 1,030-gauge run** (`bam_ssp585_fixed_gauges`, notebook with `BAM_EXPERIMENT=bam_ssp585_fixed_gauges`): it shows the global ice-sheet
  contributions and how the same melt lands very differently at different coasts (the factor map, with sea level falling near the ice sheets).
- **Use the one-site run** (`bam_ssp585_fixed`, New York) as the quick validation and the default of `run_bam.py`; its global results are identical to the gauge run's.
- **Show `bam_ssp585` only as the "before"** of the Antarctica fix (the dashed line in the total chart), never as a result: its totals are 44% too high.
- **Always state the pairing caveat** wherever warming and ice loss appear together: BAM uses climate member j only to set the probability of drawing from
  Bamber's high rather than low pool, and the ice-sheet realisation is an independent draw (per-sample correlation about +0.05). Present spreads, medians and
  totals as ensemble statistics, not as temperature-to-ice-loss trajectories. Also state that this is the ice-sheet part only (no glaciers, thermal expansion,
  land water or vertical land motion), so it is not total sea-level rise.
- Say that the Antarctica correction is a local registry patch (`facts2/patches/`), not yet fixed upstream.

### Tests
`python3 notebooks/tests/test_run_bam.py -v` (standard library only; about 1 s, 4 s with the netCDF tests, which run when xarray, netCDF4 and numpy are importable and
are skipped otherwise; for the full set use an environment isolated from the system conda:
`env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 --with xarray --with netcdf4 --with 'numpy<2' python notebooks/tests/test_run_bam.py`).
25 tests guard the driver's safeguards: the facts-total `--item` check (AIS listed with EAIS/WAIS, global and local, plus the committed experiments), the refusal of a script
generated for another workspace, `registry_has_fix` and the tracked patch (exactly four `pass_to_total: false` lines), `main()` (refuses a double-counting script and
runs nothing; `--allow-double-count` overrides; `--skip-run` only warns), and `validate_outputs` on synthetic netCDF files (correct totals pass; the four-way sum warns;
many-site medians are medians across sites; missing files and wrong sample counts fail). Each safeguard was also deliberately broken in a scratch copy (seven
mutations) and the suite failed every time, so the tests do detect regressions. They do not run containers or check the science; the clean-environment run does.

### Assumptions / known issues
- "experiment-ssp585" = `experiments/coupling.ssp585/config.yml`; FACTS2 = `fact-sealevel` org + FEB + per-module containers (not the legacy `facts/` dir).
- FEB requires a climate step, so fair-temperature is included (as in the reference). `--extremesealevel-step NONE` fails on this branch; omit the flag.
- `location.lst` is copied from the legacy coupling.ssp585 experiment and holds one site (40.7, -74), so `*-lslr.nc` have 1 location and bamber19 runs in seconds.
  For many sites use `psmsl_gauges.lst` (see "Real location list" above).
- **facts-total double-counts Antarctica in the original experiment (`bam_ssp585`).** FEB passes all four bamber19 outputs (AIS, EAIS, WAIS, GIS) to
  facts-total, but AIS already equals EAIS + WAIS, so that total equals AIS+EAIS+WAIS+GIS exactly. The correct total is AIS + GIS. 2150 global median:
  1312 mm generated vs 914 mm correct (+44%); New York: 1181 vs 707 mm.
  **Cause (confirmed):** the registry entry for bamber19-icesheets (registry `a085795`) sets no `pass_to_total` on any output, so FEB's default `true`
  sends all of them to the total. **Fix:** `pass_to_total: false` on the four EAIS/WAIS outputs, as `emulandice-ais` does. The experiment
  `bam_ssp585_fixed` was regenerated against a locally patched registry clone and its totals equal AIS + GIS (914 / 707 mm); its config and script are
  committed. The patch itself is tracked as `facts2/patches/bamber19_pass_to_total.patch` (4 lines; applies cleanly to registry `a085795`): apply it to any fresh
  registry clone, or `run_bam.py --regenerate` will warn that the registry lacks the fix. Run it with `run_bam.py --experiment apptainer_experiments/bam_ssp585_fixed`. The upstream registry is not fixed yet: the problem is reported as
  fact-sealevel/facts-experiment-builder#144 and the fix proposed as fact-sealevel/facts-module-registry#20 (both open, 2026-10-18); the report text is `facts2/REPORT_facts_total_double_count.md`. The generated scripts were deliberately not edited. `run_bam.py` checks the script's
  `facts-total` items before running and refuses a double-counting one (`--allow-double-count` to override), and it also checks the output totals afterwards.
- Without a `workflows:` entry in `experiment-config.yaml`, `generate-apptainer` emits no facts-total stage at all.
- **Sample pairing with the climate model is weak.** BAM uses climate member j only to set the probability (from its 2000-2099 integrated warming) of drawing
  output sample j from Bamber's high rather than low scenario pool; the ice-sheet realisation itself is an independent random draw. Under ssp585 91% of
  samples come from the high pool. Verified by shuffling the climate members (exactly the predicted 68 of 500 samples changed) and by a per-sample
  correlation of only +0.05 to +0.07 (null 0.00 +/- 0.045). Treat the outputs as ensemble statistics, not temperature-to-ice-loss trajectories.
  Reproduce with `check_bam_pairing.py` (docstring has the command; about 40 s; exit 0 if the code-based prediction holds).
- Local (New York) results are the global results times a constant per ice sheet (EAIS 1.04, WAIS 1.22, GIS 0.44) for all 500 samples.
- Image pulls need an exec-capable build dir. Here `APPTAINER_TMPDIR`/`APPTAINER_CACHEDIR` pointed at a nonexistent `/explore/.../containers/cache`,
  panfs failed in mksquashfs under proot, and `/tmp` and `/var/tmp` are `noexec`; `/dev/shm` works. The generated script is not edited; env is set per run.
- The numpy 1.x/2.x warnings printed on import come from the system conda (bottleneck/numexpr) and are harmless; use `numpy<2` to silence them.


## FACTS2 catalog experiment `coupling-585-260603` (11 sea-level modules, 6 workflows, extreme sea level), via Apptainer

The second exercise: instead of BAM alone, run the experiment published in the facts-experiment-catalog
(https://github.com/fact-sealevel/facts-experiment-catalog/tree/main/coupling-585-260603) with the same FEB branch, registry and Apptainer, driven by
`notebooks/run_coupling.py`. ssp585, 2020-2150 step 10, base year 2005, **2000 samples**, `location.lst` (New York), pipeline id `abcd`;
fair-temperature, then fittedismip-gris, deconto21-ais, bamber19-icesheets, emulandice-{ais,gris,glaciers}, larmip-ais, ipccar5-glaciers, tlm-sterodynamics,
kopp14-verticallandmotion and ssp-landwaterstorage, combined by facts-total in the catalog's six workflows (wf1e, wf2f, wf2e, wf3f, wf3e, wf4), then
extremesealevel-pointsoverthreshold on each workflow's local total. Results and caveats: `facts2/SUMMARY_coupling_585.md`; every difference from the
catalog and every FEB/registry problem met on the way: `facts2/REPORT_catalog_run_findings.md`.

### Setup from scratch (the data download is about 33 GB, almost all of it the TLM CMIP6 archive; the 12 distinct images are copied to 30 per-service files of about 9 GB in total)
```bash
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH
git clone <this repository> && cd sealevel/facts2
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
$FEB init
git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch            # both patches BEFORE setup-experiment (see patches/README.md)
git -C facts-module-registry apply ../patches/deconto21_larmip_pass_to_total.patch
bash fetch_catalog_data.sh                    # Zenodo 7478192 archives -> data/; resumable; SKIP_TLM=1 / SKIP_ESL=1 leave out the big ones
$FEB check-data                               # expect all complete except ipccar5-icesheets (a phantom caused by the ipccar5 link, not in this experiment)
cd .. && env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 --with xarray --with netcdf4 --with 'numpy<2' \
    python notebooks/run_coupling.py --regenerate --generate-only        # catalog command + workflows, then the preflight and double-count check; runs nothing
```
`--regenerate` runs the catalog's `feb setup-experiment` command (without `ipccar5-icesheets`, see the findings report), answers the workflow prompts with the
catalog's six workflows, removes the extra `all-modules` workflow FEB adds, fills in `pipeline-id: abcd` and the data paths, points emulandice-glaciers at
`gsat.nc`, and calls `feb generate-apptainer`. Verified in an empty workspace (own `feb init` and downloads): the generated config and script are identical
to the committed ones apart from the creation date and the absolute workspace path.

### Running
```bash
# one instance, sequential (about 4.6 h: the script runs one service at a time; fair-temperature takes 14.5 min and each emulandice module 1.3-1.6 h at any sample count)
python notebooks/run_coupling.py [-v]                        # pulls each distinct image once, runs, validates every output, writes <experiment>/coupling_results.json
# the same work shared by several instances of the script (this is how the committed results were produced): claims are directories in <experiment>/.claims
python notebooks/run_coupling.py --share &                   # first instance
python notebooks/run_coupling.py --join &                    # as many more as there are independent services; each takes the next unclaimed service
python notebooks/run_coupling.py --skip-run                  # when all have finished: validate the outputs and write the JSON
python notebooks/summarize_coupling.py                       # figures facts2/figures/coupling_585_*.png, <experiment>/coupling_summary.json and coupling_tables.md
```
Options: `--resume` skips services whose paths all exist (continue a stopped run), `--gate SERVICE=FILE` holds a service until a file exists (used to start while the
31 GB archive was still downloading), `--allow-double-count` runs even if a facts-total job lists an aggregate with its parts. The generated script is never edited:
the driver puts a shim for `apptainer` first on `PATH` that (a) runs emulandice with `--pwd /tmp` instead of the read-only `/` (R writes `Rplots.pdf` there),
(b) binds a large directory (on `/dev/shm`) over `/tmp` for emulandice (the container's own `/tmp` is a 16 MB tmpfs; the glaciers run at 2000 samples fills it, R stops writing
in the middle of 2080 without a message and the wrapper later fails or, worse, returns NaN years) and a patched `emulandice_glaciers_project.py` that keeps R's CSV and raises when
it is incomplete (`facts2/patches/container/`), (c) implements the gate, resume and claim options. Run it in an environment isolated from the system conda (see Tests).
emulandice emulates 2020-2100 only, so wf1e, wf2e and wf3e are valid through 2100; the summary compares all workflows in 2100.

### Checks the driver makes
Before: every bind-mounted source directory exists; the script was generated for this workspace; no facts-total job lists an aggregate (AIS) with its parts
(bamber19, deconto21, larmip, emulandice). After: every `.nc` the script names exists, has 2000 samples, finite values, units mm and the 14 projection
years (a leading 2005 column, which kopp14 and ssp-landwaterstorage write, is accepted, and so is a series that stops early, which emulandice's does, with a warning); every facts-total file equals the sum of the `--item` files it was
given (max difference 0.001 mm; for each year the sum covers the items that have that year, which is what facts-total does) and `valid_through_year`
is recorded: emulandice's outputs end in 2100, so wf1e, wf2e and wf3e are only valid through 2100 (a warning, see the findings report, 1b); the extreme-sea-level
output exists per workflow and is finite; for the four modules above, the aggregate is compared with the cumulative sum of its parts.

### Tests
`python3 notebooks/tests/test_run_coupling.py -v` (standard library; the 7 netCDF tests also need xarray, netCDF4 and numpy, see the command in the BAM Tests section).
31 tests: script parsing, the double-count check for each module family, preflight (double count, foreign workspace, missing bind source), the PATH shim executed against a
fake `apptainer` (non-run passthrough, emulandice working directory, gate, resume, claims, waiting for inputs), `regenerate` (catalog command and answers, config fix-ups,
existing values kept, refusal to overwrite) and output validation on synthetic files (consistent total passes; a total that is not the sum of its items, a missing file, a wrong
sample count fail; base-year column accepted; a module ending in 2100 is reported and the total matches the partial sum; extreme-sea-level output required per workflow). Each safeguard was also deliberately broken in a scratch copy
(16 mutations: the double-count regex and the larmip part list, the preflight checks, each shim feature including the large `/tmp` and the container patch, the config fix-ups,
the total-vs-items comparison, year alignment, the ESL requirement) and the suite failed every time.
