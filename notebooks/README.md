
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

### Copy-paste commands
```bash
export PATH=/panfs/ccds02/nobackup/people/gtamkin/uv-bin:$PATH     # uv
cd /panfs/ccds02/nobackup/projects/ilab/projects/sealevel/facts2

# One-time setup (already done in this workspace; setup-experiment refuses to overwrite an existing config)
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
$FEB init
# REQUIRED until the registry is fixed upstream: without it facts-total double-counts Antarctica (see Assumptions below)
git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch
$FEB setup-experiment --experiment-name apptainer_experiments/bam_ssp585_fixed --climate-step fair-temperature \
    --sealevel-step bamber19-icesheets --pipeline-id bam001 --scenario ssp585 --baseyear 2005 \
    --pyear-start 2020 --pyear-end 2150 --pyear-step 10 --nsamps 500 --location-file location.lst
# setup-experiment leaves the facts-total workflow empty when run non-interactively, so add it to the config
# (under the "Workflows (facts-total)" heading of experiment-config.yaml) BEFORE generating the script:
#   workflows:
#     all-modules: "bamber19-icesheets"
$FEB generate-apptainer --experiment-name apptainer_experiments/bam_ssp585_fixed
# (or do all of the above in one step: run_bam.py --regenerate --experiment apptainer_experiments/<new-name>)

# Run + validate (driver sets the build env, times the run, checks the netCDF outputs -> <experiment>/bam_results.json).
# Defaults to apptainer_experiments/bam_ssp585_fixed. The original, double-counting experiment is bam_ssp585 (kept as the "before").
uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v

# Or run the generated script directly (export the three env vars below first)
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
  registry clone, or `run_bam.py --regenerate` will warn that the registry lacks the fix. Run it with `run_bam.py --experiment apptainer_experiments/bam_ssp585_fixed`. The upstream registry is not fixed yet; the report for the
  maintainers is `facts2/REPORT_facts_total_double_count.md`. The generated scripts were deliberately not edited, and `run_bam.py` warns when a total
  double-counts.
- Without a `workflows:` entry in `experiment-config.yaml`, `generate-apptainer` emits no facts-total stage at all.
- Local (New York) results are the global results times a constant per ice sheet (EAIS 1.04, WAIS 1.22, GIS 0.44) for all 500 samples.
- Image pulls need an exec-capable build dir. Here `APPTAINER_TMPDIR`/`APPTAINER_CACHEDIR` pointed at a nonexistent `/explore/.../containers/cache`,
  panfs failed in mksquashfs under proot, and `/tmp` and `/var/tmp` are `noexec`; `/dev/shm` works. The generated script is not edited; env is set per run.
- The numpy 1.x/2.x warnings printed on import come from the system conda (bottleneck/numexpr) and are harmless; use `numpy<2` to silence them.
