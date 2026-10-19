# Running `coupling-585-260603` from the facts-experiment-catalog with FEB + Apptainer: findings

Written 2026-10-19. Catalog: https://github.com/fact-sealevel/facts-experiment-catalog/tree/main/coupling-585-260603 (`example_cli_command.md`
and `experiment-config.yaml`, catalog commit `013a903`). Finding 1 was posted on 2026-10-19 as issue fact-sealevel/facts-experiment-builder#145 and PR fact-sealevel/facts-module-registry#21 (it extends #144 / #20, which cover BAM only); the other findings have not been posted.

Setup: FEB branch `add_apptainer_command` (`main` has no `generate-apptainer`), registry `a085795` plus the local patches in `facts2/patches/`,
Apptainer 1.5.3, 12 cores, ssp585, 2020-2150 step 10, base year 2005, **2000 samples**, `location.lst` (one site: New York), six workflows
(wf1e, wf2f, wf2e, wf3f, wf3e, wf4), 11 sea-level modules, extreme-sea-level module per workflow. Driver: `notebooks/run_coupling.py`.

## 1. facts-total double-counts in three more modules (registry, same cause as BAM)
`pass_to_total` defaults to `true`, so a module that writes an aggregate and its parts has both summed. Checked on the module outputs of this run
(max absolute difference of the aggregate against the sum of its parts, all samples and years):

| Module | Aggregate | = sum of | Max diff | Registry `a085795` passes to the total |
|---|---|---|---|---|
| `bamber19-icesheets` | AIS | EAIS + WAIS | 0.001 mm | all four (AIS, EAIS, WAIS, GIS) |
| `deconto21-ais` | AIS (global and local) | EAIS + WAIS | 0.0002 / 0.0005 mm | all three |
| `larmip-ais`, global | AIS | EAIS + WAIS + PEN + SMB | 0.0005 mm | all five (every output explicitly `pass_to_total: true`) |
| `larmip-ais`, local | AIS | EAIS + WAIS | 0.0005 mm | all three |
| `emulandice-ais` | output-gslr / -lslr | (parts already `false`) | n/a | correct |

Effect on this experiment (global medians, mm, in 2100 and 2150; "generated" = what the unpatched registry would have summed, computed from the same outputs):
see the table in `SUMMARY_coupling_585.md` (2150: wf2f +26%, wf3f +64%, wf4 +21%; 2100: +18%, +33%, +19%).
Fix: `pass_to_total: false` on the parts, 4 lines for `deconto21-ais` and 6 for `larmip-ais`
(`facts2/patches/deconto21_larmip_pass_to_total.patch`; the BAM part is `bamber19_pass_to_total.patch`). With both patches every workflow lists exactly
5 global and 6 local items and no aggregate appears with its parts; every generated total equals the sum of its listed items (max diff 0.001 mm).
One more `larmip-ais` oddity: its global AIS includes the surface-mass-balance term (median -99 mm in 2150) but its local AIS does not (the code
computes local AIS as WAIS + EAIS only), so larmip's local and global Antarctic totals are not consistent with each other.

## 1b. Workflows with an emulandice module are only valid through 2100, and nothing says so
The `emulandice-{ais,gris,glaciers}` containers emulate 2020-2100 only (R `emulandice::main('decades', ...)` has `years_pred <- seq(2020, 2100, by = 10)`; the Python
wrapper reads 2015-2100), so their outputs have **9 years**, while the experiment grid is 2020-2150 (14 years) and the generated script passes `--pyear-*` only to
facts-total. facts-total then warns ("The dataset being processed has a years dimension from 2020 to 2100, which does not match the provided pyear-start (2020) and
pyear-end (2150). Subsetting dataset to provided pyear values.") and, for each year, **adds only the items that have that year**: the 2110-2150 totals of wf1e, wf2e
and wf3e silently omit emulandice-ais/-gris/-glaciers (test: wf1e global with emulandice-ais + TLM only: median 378 mm in 2100, then 337 mm in 2110, and the 2150 value equals
TLM alone). The totals file looks complete (14 years, no NaN). The driver recomputes every total the same way and records `valid_through_year`; the summary
therefore compares all six workflows in 2100 and reports 2150 only for wf2f, wf3f and wf4. Possible fixes: have emulandice extrapolate to the experiment's years or
write NaN after 2100; have facts-total fail (or write NaN) when items do not cover the requested years; or have FEB refuse a workflow whose modules do not share a year range.

## 2. FEB starts every container with `--pwd /`, which breaks the R-based emulandice modules
`emulandice-{ais,gris,glaciers}` stop with `Error in (function (file = if (onefile) "Rplots.pdf" ...): cannot open file 'Rplots.pdf'`: R writes
`Rplots.pdf` into the working directory, which is the read-only image root. `run_service` in the generated script says `--pwd /` because the home
directory is hidden by `--containall`. A writable working directory (`--pwd /tmp`, or `--writable-tmpfs`) fixes it. The driver does this with a PATH shim for
`apptainer` (the generated script is not edited): `--pwd /` is replaced by `--pwd /tmp` for emulandice only.

## 3. Registry default for `emulandice-glaciers` reads the wrong climate file
`emulandice-glaciers` has `input-data-file` = `fair-temperature/climate.nc` (`climate_step_output: output-climate-file`); the container then stops with
`KeyError: 'years'` because only `gsat.nc` has a `years` variable. `emulandice-ais` and `-gris` use `gsat.nc`, and so does the catalog's
`experiment-config.yaml` (generated with an older registry). The driver sets it to `gsat.nc` after `setup-experiment`.

## 3b. `emulandice-glaciers:0.2.0` loses its results when R's working files do not fit the container's 16 MB `/tmp`
With 2000 samples the glaciers run takes about 1.5-1.8 h of single-threaded R (decades 2020-2100) and then the Python wrapper stops in `ExtractProjections`
(`emulandice_glaciers_project.py`, line 31, `regions.append(lp[1])`): `IndexError: list index out of range`. Two full-length runs (1 h 44 min and 1 h 38 min) were lost this way (the CSV lives in the
container's `/tmp`, which disappears with the container). **Cause (found by keeping the CSV):** under `--containall` Apptainer gives the container a `/tmp` tmpfs of
**16 MB** (`sessiondir max size = 16` in `/etc/apptainer/apptainer.conf`; `df -h /tmp` inside the image shows `tmpfs 16M`). The R emulation writes its results
CSV there; at 2000 samples (19 regions x 2000 samples x 9 decades = 342,000 rows, more than 12 MB) the tmpfs fills in the middle of the year 2080 (region_13, sample 741), R's
writes fail without any message, R exits normally, and the file ends in a half-written line (`Glaciers`), which is what the parser trips over. With 100 samples (about
0.8 MB) the same code runs to the end, which is why a small test does not show it. Worse, if the parser tolerates the bad line (as our first workaround did) it returns an
output with 7 years and an all-NaN last year, and facts-total and ESL run on it without complaint; that happened once and the outputs were set aside (`output-invalid-glaciers-tmp16mb/`).
`emulandice-ais` and `-gris` write much less and are unaffected.
Workaround (driver, generated script untouched): the shim binds a fresh directory on `/dev/shm` over `/tmp` for emulandice (`BIG_TMP`), and
`patches/container/emulandice_glaciers_project.py` (diff against `emulandice_glaciers_project.orig.py`, taken from the image) is bound over the original: it copies R's
CSV to `output-apptainer/emulandice-glaciers/projections_FAIR_FACTS.csv`, skips lines with fewer than 8 fields and raises if any region, sample or year is missing.
Suggested upstream fixes: have the wrapper write R's `outdir` to the mounted output volume (or check R's exit and the CSV's length) and raise if the CSV is incomplete; have FEB
bind a scratch directory over `/tmp` for emulandice (or `--workdir`, or raise `sessiondir max size`).
This also bears on "run time": the glaciers module is the longest step of the experiment (about 1.7 h) and it had to be run three times here.

## 4. Data directory names differ between `feb check-data` and the generated script
`check-data` looks in `module_specific_input_data/<module name>` (`ipccar5-glaciers`, `emulandice-*`); the first generated script mounted
`.../emulandice` and `.../ipccar5` (named after the image), which did not exist, and the container start failed
(`mount hook function failure`). Fixed here by creating `emulandice/` and the symlink `ipccar5 -> ipccar5-glaciers` (`facts2/fetch_catalog_data.sh`);
with a directory named `ipccar5` present, regenerating gives a script that mounts `ipccar5-glaciers` (without it, the non-existent `ipccar5`), so FEB's rule
for picking the directory depends on what happens to exist; and `check-data` then reports a spurious `ipccar5-icesheets` module with missing files.
The driver's preflight now fails early when any bind-mounted source directory is missing. Likewise the extreme-sea-level archive unpacks to `gesla_data/`
while the registry default is `gesla_data_full/` (symlink).

## 5. Smaller things
- **Catalog text vs catalog config.** The CLI command lists `ipccar5-icesheets` but the config's `sealevel_modules` does not and no workflow uses it;
  this run follows the config. The config pins older images (e.g. `bamber19-icesheets:0.1.0`, `emulandice:0.1.1`, `facts-total:0.1.3`) and uses older
  key names (`temperature_module`, underscores); the current registry gives newer images and hyphenated keys, which is what ran here. The command passes no
  `--pipeline-id`, data paths or workflow definitions; the config has `abcd` and the six workflows, which the driver supplies (workflow prompts answered
  by the driver; FEB also adds an `all-modules` workflow that the catalog does not have, removed).
- **Years.** `kopp14-verticallandmotion` and `ssp-landwaterstorage` outputs have 15 years (2005 plus the 14 projection years); emulandice has 9 (2020-2100, see 1b); the others have 14.
  facts-total subsets correctly (the totals equal the sum of the 14-year columns); anything summing the files by hand must select years first.
- **Run time.** The generated script runs its services one after the other. With 2000 samples `fair-temperature` took 14.5 min and each emulandice module
  (single-threaded R, one decade per 7-11 min) over 1.5 hours, so a 12-core node sits almost idle. The driver can run several instances of the same
  script that share the work through claim directories (`--share` / `--join`); this reduced the experiment from roughly 4 hours sequential to the time of the slowest
  module. A scheduler in FEB (stage 2 services are independent) would make this unnecessary.
- **Image pulls.** The script pulls the same image once per service name (30 pulls for 12 distinct images); the driver pulls each once and copies it.
- **TLM data.** `tlm_sterodynamics_cmip6_data.tgz` is 31 GB; a single Zenodo stream ran at about 9 MB/s, eight parallel byte ranges at 15-45 MB/s.
