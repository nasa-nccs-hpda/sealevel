# Changing the science in `emulandice`: a roadmap

For someone who wants to change how the emulandice modules (ice-sheet and glacier emulators) produce sea-level contributions, and does not know FACTS2. All line numbers refer to **image
`ghcr.io/fact-sealevel/emulandice:0.2.0`** (upstream repo https://github.com/fact-sealevel/emulandice, release v0.2.0); re-check them on any other version. Everything below was read from that image and
exercised in the catalog experiment `facts2/apptainer_experiments/coupling-585-260603` (2000 samples); what was *not* tried is marked as such. Companion document: `SCIENCE_ROADMAP_bamber19.md`.

## 1. What the module does
emulandice emulates the land-ice models of ISMIP6 (Greenland and Antarctica) and GlacierMIP (glaciers) following Edwards et al. (2021, Nature): Gaussian-process emulators, fitted to ~4,800 simulations, map global
temperature (and, for the ice sheets, basal melt and ice-shelf collapse) to sea-level contribution. FACTS2 forces them with the temperature trajectories of `fair-temperature` and runs **three modules from one image**:

| FEB service | Command | Output (global, mm) | Output (local) |
|---|---|---|---|
| `emulandice-ais` | `ais` | Antarctica, plus WAIS, EAIS and Peninsula parts | local AIS, EAIS, WAIS |
| `emulandice-gris` | `gris` | Greenland | local GIS |
| `emulandice-glaciers` | `glaciers` | all glaciers (19 regions; one file per region optional) | local glaciers |

Each module is two programs: a **Python wrapper** (`/opt/emulandice/src/emulandice/`) that prepares the forcing, calls R, and post-processes; and an **R package** (`/emulandice/R/`, installed into R's `site-library`)
that does the emulation. Per module: `gsat.nc` -> Python preprocess -> forcing CSV -> **R `emulandice::main('decades', ...)`** -> results CSV -> Python adds trends, writes the global file, applies fingerprints -> local file.

## 2. Where the science lives
| Where | What |
|---|---|
| `src/emulandice/emulandice_preprocess.py` (120 lines) | reads `surface_temperature` from `gsat.nc`, **subtracts each sample's value in the base year**, keeps **2015-2100** (line 65), writes the forcing CSV (header from `FACTS_CLIMATE_FORCING.csv.head`). |
| `src/emulandice/r_helper.py` (39 lines) | the **only** call into R: `main('decades', dataset=..., N_FACTS=<samples>, outdir=..., ice_sources=c(...))`. Every other R option takes its default. |
| `/emulandice/R/main.R` (1,646 lines) | the emulator. Options 78-130; dataset selection 142-227; Antarctic melt prior 284; climate prior 291; **emulators 541-677** (mean functions 558-561, covariance functions 615-640); **glacier caps 678-707**; year loop 767+; **`years_pred` 125-128** (`decades` = 2020, 2030, ..., 2100). |
| `/emulandice/R/read_data.R` | `read_forcing` (12), `read_sealevel` (336, the calibration data), `read_melt` (882, the melt priors). |
| `src/emulandice/emulandice_{AIS,GrIS,glaciers}_fit.py` | **hard-coded linear trend terms** (section 3). |
| `src/emulandice/emulandice_{AIS,GrIS,glaciers}_project.py` | reads R's CSV (`ExtractProjections`), adds the trends, writes NetCDF. |
| `src/emulandice/emulandice_*_postprocess.py`, `AssignFP.py` | localisation: global x fingerprint per site. |
| `/usr/local/lib/R/site-library/emulandice/extdata/` | the data files (below). A plain directory, so files can be replaced without rebuilding the package. |

Data in `extdata/`: `20201106_SLE_SIMULATIONS.csv` (about 4,800 simulations (4,837 rows): columns `ice_source, region, group, model, resolution, exp_id, GCM, scenario, melt, collapse, y2015 ... y2100`),
`FACTS_CLIMATE_FORCING.csv`, the Antarctic basal-melt prior files `output_gamma0_NonLocal_MeanAnt.dat` and `..._PIGL.dat`, `data_for_tamsin.txt` (Greenland retreat prior), `regionnames.txt`.

## 3. The numbers that are fixed in the code
| Item | Value | Where |
|---|---|---|
| Linear trend added to the AIS samples (mean +/- sd, per year since the base year; units not documented, they appear to be mm per year) | EAIS 0.09 +/- 0.04, WAIS 0.18 +/- 0.09, Peninsula 0.06 +/- 0.03 | `emulandice_AIS_fit.py` 7-8; applied in `emulandice_AIS_project.py` |
| Greenland trend | 0.19 +/- 0.1 | `emulandice_GrIS_fit.py` 7-8 |
| Glaciers trend (a constant, scaled by each region's share of early melt) | 0.7 +/- 0.1 | `emulandice_glaciers_fit.py` 7-8; `..._project.py` 125-150 |
| Trend sampling | truncated normal (ice sheets, lower bound 0) or normal (glaciers) of one shared uniform draw, generator seed **8071**, so the three modules' trends are correlated | each `_project.py` |
| R random seed | `set.seed(2020)` | `main.R` 255 |
| Years | R: 2020-2100 by 10 (assertion: 2016-2100); Python preprocess: 2015-2100 | `main.R` 125-128; `emulandice_preprocess.py` 65 |
| Glacier regional caps (Farinotti et al. table 3) | 19 pairs of volume / sea-level equivalent | `main.R` 678-707 |
| Emulator type and mean functions | RobustGaSP (`"RG"`); `~ temp + melt (+ collapse)` for ice sheets, `~ temp` for each glacier region | `main.R` 546-561 |
| Samples | must equal the number of climate members; R accepts `N_temp` in 501, 1000, 2237, `N_FACTS`, 5000, 10000 and uses `N_FACTS` for `decades` | `main.R` 103, 296 |
There is **no seed, prior or science option** on the module's command line (`cli.py`): only file paths, `--baseyear`, `--chunksize` and the location file.

## 4. Options, from least to most work
| # | Change | Where | Effect on the science | Effort / risk |
|---|---|---|---|---|
| A | **Switch on options that R already has** (never exposed by the wrapper): `gamma0_prior` ("joint", "MeanAnt", "PIGL", "unif", "unif_high"), `collapse_prior` (both, on, off), `risk_averse`, `select_ism` (balanced, single, single_low, high_sensitivity, larmip), `select_gcm` (high_five, high_two), `history_match`, `exclude_open`, `impute_high`, `min_res_is`, `mean_temp`, `mean_melt` | the string `r_cmd` in `r_helper.py` | different priors / model subsets / more pessimistic settings, with no change to the R code | small. Several of them make R run "Antarctic only" or "ice sheets only" (`main.R` 85-98), which interacts with the `ice_sources` the wrapper passes. **Their behaviour inside FACTS' `decades` mode was not tried here.** |
| B | Change the trend terms | the three `*_fit.py` files | changes the long-term drift added on top of the emulated response; ice sheets and glaciers stay correlated through seed 8071 | small; document the new values |
| C | Replace the calibration data (new ice-sheet or glacier simulations) or the melt / retreat priors | `extdata/` files; `read_sealevel` expects the current column layout | changes what is emulated | medium; **no image build needed**: bind-mount the new file over the one in `site-library/emulandice/extdata/` |
| D | Change the glacier caps | `main.R` 678-707 | bounds each region's contribution by its ice volume | small edit, but needs the R package rebuilt (section 5, route 3) |
| E | Change the emulator (mean function, covariance, emulator package, `mean_fn` terms) | `main.R` 541-677 | changes the response surface | medium to large; rebuild; re-validate against the calibration simulations |
| F | **Extend the years past 2100** | R stops at 2100 (assertion at 128, calibration data end at `y2100`); the wrapper has no extrapolation | needed to use the modules in a 2020-2150 experiment: today `facts-total` silently leaves them out after 2100 | a science decision: extrapolate in the Python post-processing (cheap, e.g. continue the last decade's rate), or extend the emulation (large). Make the output cover the whole grid or fill it with NaN, never leave it short. |
| G | Change the climate forcing (reference period, which years) | `emulandice_preprocess.py` 65 and the base-year subtraction | the emulator is driven by temperature **anomalies relative to the base year** (2005 in the catalog); check which reference the emulator was calibrated with before changing it (not checked here) | small code, careful science |
| H | Different fingerprints / localisation | `--fprint-*` data, `AssignFP.py` | local-to-global factors only | small |
| I | Seed options (so ensembles can be repeated with different draws) | `r_helper.py` (pass a seed), the three `_project.py` (replace 8071) | none on the central estimate; gives sampling-noise estimates | small |

## 5. How to run a changed version
1. **Python wrapper changes (A, B, F, G, H, I): bind-mount a patched file** over the original, no build. Copy the file out of the image
   (`apptainer exec --no-home --containall --pwd / facts2/apptainer_experiments/sif/emulandice-ais-0.2.0.sif cat /opt/emulandice/src/emulandice/<file>.py`), keep an untouched `*.orig.py`, edit a copy under
   `facts2/patches/container/`, and register it in `CONTAINER_PATCHES` of `notebooks/run_coupling.py` (an existing example: `emulandice_glaciers_project.py`). The driver's shim binds it only for services whose image name matches.
   `CONTAINER_PATCHES` holds one file per image name; extend it to a list for several files.
2. **Data changes (C): bind-mount the new data file** onto `/usr/local/lib/R/site-library/emulandice/extdata/<file>` in the same way.
3. **R code changes (D, E): rebuild.** The R code is installed as a package (compiled lazy-load database), so editing `/emulandice/R/main.R` in a bind mount has **no effect**. Fork the repo, change `R/main.R`,
   build the image from its `Dockerfile` (it uses `renv`), give it a new tag. Then set `image:` of the three emulandice entries in `experiment-config.yaml` and regenerate the script. **Gotcha:** the generated script pulls
   an image only if `apptainer_experiments/sif/<service>-<version>.sif` does not exist; a new image under an old name is ignored. Use a new tag, or place your `.sif` at the expected path.
4. **Contribute it** with a PR to `fact-sealevel/emulandice`; a new option also needs the registry entries (`emulandice-ais`, `-gris`, `-glaciers` YAML files, section `arguments`) and a registry PR.

**Cost of testing.** Each module takes about **80-100 minutes whatever the sample count** (R single-threaded; at 100 and at 2000 samples the times were within about 10% of each other), and the three modules can run in parallel
(`notebooks/run_coupling.py --share` / `--join`). To test one module, run its container by hand with the arguments from the generated script (block `# --- emulandice-ais ---` of `experiment-apptainer.sh`).
For quick R experiments, `main()` can predict a single year (`expt = "default"`, `years = 2100`) in less time than the 9-decade run; that path was **not timed or validated here**.

## 6. How to check that you changed what you meant to
- **Reference outputs:** `coupling-585-260603/output-apptainer/emulandice-{ais,gris,glaciers}/` (2000 samples, 2020-2100; not tracked in git, regenerate with the driver) and the numbers in `SUMMARY_coupling_585.md` (e.g. wf1e New York 2100 median 969 mm,
  Antarctica 82 mm, Greenland 126 mm, glaciers 175 mm global). The seeds are fixed (R 2020, Python 8071) so a repeat should be bit-identical; **repeatability of emulandice was not tested here**.
- **Compare distributions, not single values:** medians and 5-95% of each module in 2050 and 2100, per region for glaciers, before and after; the per-sample rank correlation with the climate member (the catalog run: glaciers +0.67, Greenland +0.33, Antarctica -0.04) is a quick check of how
  temperature-driven the module is.
- **Driver validation:** `python notebooks/run_coupling.py --skip-run` (see `notebooks/README.md`, "FACTS2 catalog experiment") checks sizes, units, finite values, years, and that each facts-total equals the sum of its listed items. 31 tests: `notebooks/tests/test_run_coupling.py`.

## 7. Gotchas (all hit during the catalog run; details in `REPORT_catalog_run_findings.md`)
- **`/tmp` in the container is a 16 MB tmpfs** (Apptainer `--containall`). At 2000 samples the glaciers run writes a 16 MB CSV, the tmpfs fills in the middle of 2080, R's writes fail silently and the wrapper later fails (or returns NaN years). Two full runs were lost. The driver binds a large directory over `/tmp` and a patched
  `emulandice_glaciers_project.py` (copies the CSV out, raises if it is incomplete): keep both when you run by hand (`--bind=<dir>:/tmp`).
- **`--pwd /` is read-only**; R wants to write `Rplots.pdf` into its working directory. The driver uses `--pwd /tmp`.
- **Years:** outputs end in 2100 while the experiment grid goes to 2150; `facts-total` then omits the module after 2100 without an error. Three of the six catalog workflows are affected.
- **`emulandice-glaciers` input:** the registry default is `climate.nc`, which fails with `KeyError: 'years'`; the module needs `gsat.nc`.
- **Data directories:** `check-data` and the generated script disagree for `emulandice` (an empty `emulandice/` directory is needed).
- **Totals:** `emulandice-ais` already marks its regional outputs `pass_to_total: false` (correct); do the same for any output you add that is a part of another.
- **Samples:** the module needs exactly the climate members as samples (`N_FACTS`); mixing files from runs with different sample counts fails or is silently wrong.
