
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
$FEB setup-experiment --experiment-name apptainer_experiments/bam_ssp585 --climate-step fair-temperature \
    --sealevel-step bamber19-icesheets --pipeline-id bam001 --scenario ssp585 --baseyear 2005 \
    --pyear-start 2020 --pyear-end 2150 --pyear-step 10 --nsamps 500 --location-file location.lst
$FEB generate-apptainer --experiment-name apptainer_experiments/bam_ssp585

# Run + validate (driver sets the build env, times the run, checks the netCDF outputs -> facts2/bam_results.json)
uv run --with xarray --with netcdf4 --with 'numpy<2' --with pyyaml python ../notebooks/run_bam.py -v

# Or run the generated script directly (export the three env vars below first)
D=/dev/shm/apptainer_build; mkdir -p $D/proot $D/cache
APPTAINER_TMPDIR=$D APPTAINER_CACHEDIR=$D/cache PROOT_TMP_DIR=$D/proot \
  /usr/bin/time -v bash apptainer_experiments/bam_ssp585/experiment-apptainer.sh 2>&1 | tee run.log
```

### Inputs / outputs
| Stage | Module (image) | Inputs (under `facts2/data/`) | Outputs (under `apptainer_experiments/bam_ssp585/output-apptainer/`) |
|---|---|---|---|
| 1 | fair-temperature (`ghcr.io/fact-sealevel/fair-temperature:0.2.1`) | `module_specific_input_data/fair-temperature/{rcmip,parameters}` | `fair-temperature/{climate,gsat,oceantemp,ohc}.nc` |
| 2 | bamber19-icesheets (`ghcr.io/fact-sealevel/bamber19-icesheets:0.2.0`) | `fair-temperature/climate.nc`, `module_specific_input_data/bamber19-icesheets/SLRProjections190726core_SEJ_full.mat`, `shared_input_data/{FPRINT,location.lst}` | `bamber19-icesheets/{AIS,EAIS,WAIS,GIS}-{gslr,lslr}.nc` |

Parameters: ssp585, years 2020-2150 step 10 (14 steps), baseyear 2005, nsamps 500, pipeline-id bam001, seeds 2314 (fair) / 1423 (bamber).
Output shape: `sea_level_change(samples=500, years=14, locations=1)` in mm; AIS = EAIS + WAIS (checked to 0.001 mm).
Example 2150 global medians (mm): AIS 403, EAIS 49, WAIS 344, GIS 420.

### Runtime metrics (forest204, 12 cores)
| Run | Wall | fair-temperature | bamber19 | Peak RSS | Notes |
|---|---|---|---|---|---|
| First (cold) | 8m54s | 3m50s | 7s | 618 MB | includes pulling 2 images (~5 min) |
| Rerun via `run_bam.py` (images cached) | 3m58s | 3m51s | 8s | 412 MB | 13/13 output checks OK |

SIFs: fair-temperature 200 MB, bamber19-icesheets 165 MB (`apptainer_experiments/sif/`).

### Assumptions / known issues
- "experiment-ssp585" = `experiments/coupling.ssp585/config.yml`; FACTS2 = `fact-sealevel` org + FEB + per-module containers (not the legacy `facts/` dir).
- FEB requires a climate step, so fair-temperature is included (as in the reference). `--extremesealevel-step NONE` fails on this branch; omit the flag.
- `location.lst` is copied from the legacy coupling.ssp585 experiment and holds one site (40.7, -74), so `*-lslr.nc` have 1 location and bamber19 runs in seconds.
- The generated script has no facts-total step (`output-apptainer/facts-total/` stays empty).
- Image pulls need an exec-capable build dir. Here `APPTAINER_TMPDIR`/`APPTAINER_CACHEDIR` pointed at a nonexistent `/explore/.../containers/cache`,
  panfs failed in mksquashfs under proot, and `/tmp` and `/var/tmp` are `noexec`; `/dev/shm` works. The generated script is not edited; env is set per run.
- The numpy 1.x/2.x warnings printed on import come from the system conda (bottleneck/numexpr) and are harmless; use `numpy<2` to silence them.
