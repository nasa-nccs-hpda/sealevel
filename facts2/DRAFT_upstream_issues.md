# Draft upstream issues (NOT posted)

Written 2026-10-19 from the catalog run `coupling-585-260603`. **Held back on purpose:** FEB is under development, so these are to be revisited and re-checked against the then-current FEB and registry before anything is posted.
Background and evidence: `REPORT_catalog_run_findings.md` (sections 1b, 2, 3, 3b, 4). Already posted: facts-experiment-builder#144 / registry PR #20 (bamber19-icesheets) and #145 / registry PR #21 (deconto21-ais, larmip-ais).
Before posting: re-test each on the current FEB `main` / registry, update the environment line, and log in with `gh auth login` (the CLI is logged out).

## 1. Apptainer scripts start every container with --pwd /, which breaks emulandice (R cannot write Rplots.pdf)
Repository: `fact-sealevel/facts-experiment-builder`

`generate-apptainer` writes `apptainer run --no-home --containall --pwd / ...` for every service. `/` is read-only in the image, so `emulandice-ais`, `-gris` and `-glaciers` stop at once with
`Error in (function (file = if (onefile) "Rplots.pdf" ...): cannot open file 'Rplots.pdf'` (R writes `Rplots.pdf` into its working directory).

Workaround that works: `--pwd /tmp` for these services (see also the /tmp size issue). Suggested fix: start containers in a writable directory (`/tmp`, or `--writable-tmpfs`), or only use `--pwd /` for modules that need no writable cwd.

Environment: FEB branch `add_apptainer_command`, registry `a085795`, Apptainer 1.5.3, catalog experiment `coupling-585-260603` (2000 samples). Details and logs: https://github.com/nasa-nccs-hpda/sealevel (facts2/REPORT_catalog_run_findings.md).

## 2. Containers get a 16 MB /tmp (Apptainer --containall): emulandice-glaciers silently truncates its results at 2000 samples
Repository: `fact-sealevel/facts-experiment-builder`

Under `--containall` Apptainer mounts `/tmp` as a tmpfs of **16 MB** (`sessiondir max size = 16` in `apptainer.conf`; `df -h /tmp` inside the image shows `tmpfs 16M`). `emulandice` keeps its working files there.
With 2000 samples the glaciers run (19 regions x 2000 samples x 9 decades = 342,000 CSV rows, 16.4 MB in the end) fills it in the middle of the year 2080: R's writes fail without any message, R exits normally and
its CSV ends in a half-written line. The wrapper then stops in `ExtractProjections` with `IndexError: list index out of range` (`emulandice_glaciers_project.py`, `regions.append(lp[1])`) after about 1.7 hours,
and the CSV is lost with the container. A run with 100 samples (0.8 MB) works, so a small test does not show it. (If the parser tolerates the bad line, it writes an output with 7 years and an all-NaN last year.)
Two full runs were lost this way.

Suggested: have FEB bind a scratch directory over `/tmp` for such modules (or pass `--workdir`), and have the emulandice wrapper fail loudly when R's CSV is incomplete.

Environment: FEB branch `add_apptainer_command`, registry `a085795`, Apptainer 1.5.3, catalog experiment `coupling-585-260603` (2000 samples). Details and logs: https://github.com/nasa-nccs-hpda/sealevel (facts2/REPORT_catalog_run_findings.md).

## 3. Module data directory for emulandice and ipccar5 differs between feb check-data and the generated script
Repository: `fact-sealevel/facts-experiment-builder`

`feb check-data` looks in `data/module_specific_input_data/<module name>` (`ipccar5-glaciers`, `emulandice-ais`, ...). The generated script mounted `.../emulandice` (for emulandice-gris) and `.../ipccar5` (for ipccar5-glaciers),
named after the image; neither existed, and the service died at container start (`mount hook function failure`). Creating an empty `emulandice/` fixed the first. For ipccar5, the choice depends on what exists: with a directory
(or symlink) named `ipccar5` present the regenerated script mounts `ipccar5-glaciers`, without it the non-existent `ipccar5`; `check-data` then also reports a spurious `ipccar5-icesheets` module as incomplete.
Similarly the extreme-sea-level archive unpacks to `gesla_data/`, while the default is `gesla_data_full/`.

Suggested: use one rule for the directory name in `check-data` and in `generate-apptainer`, and check that every bind source exists before the script runs.

Environment: FEB branch `add_apptainer_command`, registry `a085795`, Apptainer 1.5.3, catalog experiment `coupling-585-260603` (2000 samples). Details and logs: https://github.com/nasa-nccs-hpda/sealevel (facts2/REPORT_catalog_run_findings.md).

## 4. facts-total silently omits items that do not cover the experiment's years (emulandice ends in 2100)
Repository: `fact-sealevel/facts-experiment-builder`

The emulandice modules emulate 2020-2100 only, so their outputs have 9 years while the experiment grid (2020-2150) has 14. `facts-total` logs a warning ("The dataset being processed has a years dimension from 2020 to 2100, which does not match
the provided pyear-start (2020) and pyear-end (2150). Subsetting dataset to provided pyear values.") but writes a complete-looking file (14 years, no NaN) in which, for each later year, only the items that have that year are added.
Test: wf1e global total of emulandice-ais + tlm-sterodynamics: median 378 mm in 2100, then 337 mm in 2110, and the 2150 value equals TLM alone. The totals of every workflow with an emulandice module (3 of the 6 in the catalog experiment) are therefore wrong after 2100
with no error. (Other modules also write the base year 2005 as an extra first column, which is handled.)

Suggested: fail (or write NaN) when an item does not cover the requested years, and/or have FEB check module year ranges against the experiment grid.

Environment: FEB branch `add_apptainer_command`, registry `a085795`, Apptainer 1.5.3, catalog experiment `coupling-585-260603` (2000 samples). Details and logs: https://github.com/nasa-nccs-hpda/sealevel (facts2/REPORT_catalog_run_findings.md).

## 5. emulandice-glaciers reads climate.nc by default but needs gsat.nc (KeyError: 'years')
Repository: `fact-sealevel/facts-module-registry`

In `emulandice-glaciers/emulandice_glaciers_module.yaml` the input `input-data-file` defaults to `fair-temperature/climate.nc` (`climate_step_output: output-climate-file`). The container then stops with `KeyError: 'years'`
in `GetSamples` because only `gsat.nc` has a `years` variable. `emulandice-ais` and `-gris` use `gsat.nc`, and so does the catalog's `experiment-config.yaml` for `coupling-585-260603` (generated with an older registry).
Setting the value to `fair-temperature/gsat.nc` in the experiment config works. I have not tested a change of the registry default itself (it probably also needs `climate_step_output: output-gsat-file`).

Environment: FEB branch `add_apptainer_command`, registry `a085795`, Apptainer 1.5.3, catalog experiment `coupling-585-260603` (2000 samples). Details and logs: https://github.com/nasa-nccs-hpda/sealevel (facts2/REPORT_catalog_run_findings.md).
