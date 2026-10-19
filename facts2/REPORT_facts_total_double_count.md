# `bamber19-icesheets` outputs double-count Antarctica in `facts-total` (missing `pass_to_total: false`)

> **Status (2026-10-18):** posted as fact-sealevel/facts-experiment-builder#144 (this text, below this note, is the issue body) with the fix proposed as
> fact-sealevel/facts-module-registry#20 (4 lines, from the `gtamkin` fork). Both open at the time of writing.
>
> **Update 2026-10-19 (posted as facts-experiment-builder#145 and PR facts-module-registry#21):** running the catalog experiment `coupling-585-260603` showed the same defect in `deconto21-ais` and `larmip-ais`
> (checked on real outputs). Findings, the extra patch and the effect on that experiment's totals: `REPORT_catalog_run_findings.md`. Issue #144 and PR #20 cover
> `bamber19-icesheets` only.

## Summary
With the default `--total-all-modules`, the generated `facts-total` job for `bamber19-icesheets` sums all four ice-sheet outputs: AIS, EAIS, WAIS and GIS.
AIS is already EAIS + WAIS, so Antarctica is counted twice and the total is too high. The cause is in the registry entry, and a 4-line change fixes it (tested end to end, below).

## Environment
- facts-experiment-builder: branch `add_apptainer_command` (package version 0.6.0)
- facts-module-registry: `a085795` ("remove old transform ref")
- Images: `bamber19-icesheets:0.2.0`, `fair-temperature:0.2.1`, `facts-total:0.2.1`; Apptainer 1.5.3
- ssp585, 2020-2150 step 10, baseyear 2005, nsamps 500, `projection_scale: local`, one location (New York)

## What happens
The generated script passes these inputs to `facts-total` (the local job gets the four `-lslr.nc` equivalents):
```
--item=.../bamber19-icesheets/AIS-gslr.nc
--item=.../bamber19-icesheets/EAIS-gslr.nc
--item=.../bamber19-icesheets/WAIS-gslr.nc
--item=.../bamber19-icesheets/GIS-gslr.nc
```
Checked on the outputs of a full run:
- `AIS - (EAIS + WAIS)`: max absolute difference 0.0005 mm over all 500 samples and 14 years.
- The `facts-total` output equals AIS + EAIS + WAIS + GIS exactly (max difference 0) and differs from AIS + GIS by up to ~9,500 mm (global) and ~10,700 mm (local).

| 2150 median | `facts-total` as generated | Correct (AIS + GIS) |
|---|---|---|
| Global mean | 1312 mm (+44%) | 914 mm |
| Single site (New York) | 1181 mm (+67%) | 707 mm |

## Root cause
- `OutputFileSpec.pass_to_total` defaults to `True` (`core/module/arg_specs.py`).
- `_collect_workflow_output_paths_by_type` (`application/execution_plan.py`) skips an output only when `pass_to_total` is false.
- `bamber19-icesheets/bamber19_icesheets_module.yaml` sets `pass_to_total` on none of its eight outputs, so all of them are passed to the total.
- Other entries already handle this. `emulandice-ais` keeps `output-gslr-file` and `output-lslr-file` as `true` and marks its EAIS, WAIS and PEN outputs `false`.
- `module_contributor_documentation.md` does not mention `pass_to_total`, so a contributor has no way to learn that it decides what the total sums.

## Proposed fix (registry only)
Add `pass_to_total: false` to four outputs in `bamber19_icesheets_module.yaml`: `output-EAIS-gslr-file`, `output-WAIS-gslr-file`,
`output-EAIS-lslr-file`, `output-WAIS-lslr-file`. This keeps AIS and GIS and mirrors `emulandice-ais`. (Keeping EAIS + WAIS and dropping AIS would also work.)

## Verification of the fix (end to end)
In a separate scratch workspace on registry `a085795` with only that 4-line change, I ran the whole pipeline
(`fair-temperature` -> `bamber19-icesheets` -> `facts-total`): exit 0, 4:00 wall time.
- `generate-apptainer` logs `pass_to_total=false, skipping` for the four outputs, and the script passes only `AIS-{gslr,lslr}.nc` and `GIS-{gslr,lslr}.nc`.
- Totals (500 samples x 14 years, global and local):

| Check | Global | Local |
|---|---|---|
| max abs difference, total vs AIS + GIS | 0 mm | 0 mm |
| max abs difference, total vs EAIS + WAIS + GIS | 0.001 mm | 0.001 mm |
| max abs difference, total vs the old four-way sum | ~9,458 mm | ~10,690 mm |
| 2150 median, fixed total / old generated total | 914 / 1312 mm | 707 / 1181 mm |

- The `bamber19-icesheets` outputs of this run are bit-identical to those of the earlier (unfixed) run, so the seeded runs are deterministic and the
  difference above comes only from the fix.

## Reproduce
1. `feb init`; download the `bamber19-icesheets` and `fair-temperature` input data and the shared data.
2. `feb setup-experiment` with `--climate-step fair-temperature --sealevel-step bamber19-icesheets` plus the parameters above.
3. Add to `experiment-config.yaml` under the "Workflows (facts-total)" heading, because the setup run leaves it empty (see below):
   ```yaml
   workflows:
     all-modules: "bamber19-icesheets"
   ```
4. `feb generate-apptainer`, then read the `--item=` lines of the Stage 3 block. To test the fix, apply the 4-line change to the registry clone before step 2.

## Other things noticed
- `setup-experiment`, run non-interactively, leaves `workflows:` empty, and `generate-apptainer` then silently emits no `facts-total` stage at all.
- `--extremesealevel-step NONE`, which the help text advertises, failed in an earlier setup attempt (it looks up a module named `NONE`); not re-tested recently.
- The Apptainer script pulls the `facts-total` image twice under two file names (global and local jobs), adding about 3 minutes to a cold run.
- The `bamber19-icesheets` YAML mounts `location-file` and `fingerprint-dir` through a volume named `input`, which is not declared under `volumes`
  (the contributor guide requires declared volumes). FEB still generated a working script.

## Possible hardening in FEB (optional)
Document `pass_to_total` in the contributor guide. A warning when one output of a module is the sum of other outputs in the same workflow would
catch this class of problem; I do not know of a way for FEB to detect that today.
