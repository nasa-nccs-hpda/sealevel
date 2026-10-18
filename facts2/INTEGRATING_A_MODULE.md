# Recipe: integrate a module into FACTS2 (worked example: BAM)

BAM = `bamber19-icesheets`, the ice-sheet module run in `apptainer_experiments/bam_ssp585/`.
Sources: `facts-module-registry/module_contributor_documentation.md` (the official guide), BAM's registry entry
`facts-module-registry/bamber19-icesheets/bamber19_icesheets_module.yaml`, and BAM's container CLI (`<image> --help`).

## 0. How the pieces fit

```
module container (a CLI)  <--described by-->  registry YAML  --read by-->  FEB (facts-experiment-builder)
                                                                              |-> experiment-config.yaml  (user edits values)
                                                                              |-> experiment-apptainer.sh (runs containers in stages)
stage 1 climate module -> stage 2 sea-level modules (read climate.nc) -> stage 3 facts-total (sums chosen outputs)
```
The **registry YAML is the contract**: FEB never looks inside your container. It only builds the command line and mounts from the YAML.

## 1. Make the container a well-behaved CLI (the API)
One command, every input and output given as a flag, results written as NetCDF with `samples x years x locations` and units mm.
BAM's real flags (`apptainer run bamber19-icesheets-0.2.0.sif --help`):

| Kind | BAM flags | Comes from |
|---|---|---|
| Experiment-wide | `--pipeline-id --scenario --nsamps --baseyear --pyear-start/-end/-step --location-file` | experiment metadata, shared by every module |
| Module knobs | `--replace --chunksize --rngseed` | module section of `experiment-config.yaml` |
| Fingerprints | `--fingerprint-dir` | shared input data (`FPRINT/`) |
| Input files | `--slr-proj-mat-file` (module data), `--climate-data-file` (**another module's output**) | see section 3 |
| Output files | `--output-{AIS,EAIS,WAIS,GIS}-{gslr,lslr}-file` | see section 4 |

Rule: an output flag you omit is not written ("If not provided, file will not be written"). FEB passes every output listed in the YAML.

## 2. Write the registry YAML
Directory `bamber19-icesheets/` (kebab-case) containing `bamber19_icesheets_module.yaml` (snake_case + `_module`). Skeleton, annotated:

```yaml
module_name: "bamber19-icesheets"
container_image: "ghcr.io/fact-sealevel/bamber19-icesheets:0.2.0"   # pin a tag or sha256
command: "main"
uses_climate_file: true        # run in stage 2, after the climate module
climate_file_required: false   # BAM's --climate-data-file is optional
arguments:
  top_level:   [pipeline-id, nsamps, scenario, pyear-*, baseyear, location-file]   # source: metadata.*
  options:     [replace, chunksize, rngseed]                                       # source: module_inputs.options.*
  fingerprint_params: [fingerprint-dir]                                            # mounted at /mnt/shared_in
  inputs:      [climate-data-file, slr-proj-mat-file]
  outputs: {files: [output-AIS-gslr-file, ... 8 in all]}
volumes: {module_specific_input, shared_input, output}   # host dir -> /mnt/module_specific_in, /mnt/shared_in, /mnt/out
```
Every argument has `name` (= CLI flag), `type`, `source` (a dot-path into FEB's config) and optionally `mount`, `filename`, `default_value`.
The guide says every `mount.volume` must exist under `volumes`. (BAM's own YAML does not follow this: its `location-file` and `fingerprint-dir` mounts
use a volume named `input` that is not declared; FEB still generated a working script, but new entries should follow the guide.)
Put the input-data archive URL (Zenodo) in a header comment.

## 3. Inputs: three places data can come from
| Where | BAM example | YAML detail | Where it lives on disk |
|---|---|---|---|
| Experiment metadata | `--nsamps 500`, `--scenario ssp585` | `source: metadata.*` | `experiment-config.yaml` top section |
| Module-specific data | `SLRProjections190726core_SEJ_full.mat` | `filename:` + mount `module_specific_input` | `data/module_specific_input_data/bamber19-icesheets/` |
| Shared data | `FPRINT/`, `location.lst` | `fingerprint_params` / `location-file` | `data/shared_input_data/` |
| **Another module's output** | `climate.nc` from fair-temperature | `external_volume: true`, `climate_step_output: output-climate-file` | `output/fair-temperature/climate.nc` |

`feb check-data` verifies the `filename:` entries exist. The `external_volume` input is what makes FEB schedule BAM **after** the climate step
(the generated script waits for `climate.nc` before starting it).

## 4. Outputs: what you declare, and what it controls
```yaml
- name: "output-GIS-gslr-file"      # becomes --output-GIS-gslr-file=/mnt/out/bamber19-icesheets/GIS-gslr.nc
  filename: "GIS-gslr.nc"
  output_type: "global"             # global | local | total   -> which facts-total job may pick it up
  pass_to_total: true               # default true; see section 5
  mount: {volume: "output", container_path: "/mnt/out", transform: "filename"}
```
In the BAM run (`--projection-scale local`, the default) both the global and the local outputs and jobs were generated; I did not test `--projection-scale global`.
BAM's CLI requires `--location-file` in either case.

## 5. Impact on facts-total (read this before you submit)
`facts-total` (`per_workflow: true`) is not a normal module: FEB creates **one job per workflow and output type**.
1. A *workflow* is a named list of sea-level modules, e.g. `all-modules: "bamber19-icesheets"`.
2. For each workflow, FEB gathers that module's outputs of type `global` (and, separately, `local`), skipping any with `pass_to_total: false`.
3. Each gathered file becomes one `--item=` flag; facts-total **adds them** into `facts-total/<workflow>_<type>_total.nc`.

So every output you mark `output_type` and leave `pass_to_total: true` **is added into the total**. Consequences for module authors:
- Items must share `nsamps` and the projection-year grid, or they cannot be summed.
- If your module writes both an aggregate and its parts, mark all but one set `pass_to_total: false`.
  **BAM currently does not**: it writes AIS and also EAIS + WAIS, so the total counts Antarctica twice
  (2150 global median 1312 mm generated vs 914 mm correct). The fix is `pass_to_total: false` on the EAIS and WAIS outputs, as `emulandice-ais` does.
  The official contributor guide does not mention `pass_to_total`; use `emulandice-ais` or `ebm3-sterodynamics` as references.
- Diagnostic outputs (quantiles, intermediate files) should also be `pass_to_total: false`.

## 6. Test it end to end
```bash
FEB="uvx --from git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command feb"
$FEB list-modules                                    # your module appears once the registry has your YAML
$FEB init                                            # workspace + registry clone (or point --module-registry at your branch)
# put data under data/module_specific_input_data/<module>/ and data/shared_input_data/, then:
$FEB check-data
$FEB setup-experiment --experiment-name apptainer_experiments/my_exp --climate-step fair-temperature \
     --sealevel-step <your-module> --pipeline-id id001 --scenario ssp585 --baseyear 2005 \
     --pyear-start 2020 --pyear-end 2150 --pyear-step 10 --nsamps 500 --location-file location.lst
# add to experiment-config.yaml under "Workflows (facts-total)", otherwise NO facts-total stage is generated:
#   workflows:
#     all-modules: "<your-module>"
$FEB generate-apptainer --experiment-name apptainer_experiments/my_exp
grep -- '--item=' apptainer_experiments/my_exp/experiment-apptainer.sh    # CHECK exactly what gets summed
bash apptainer_experiments/my_exp/experiment-apptainer.sh                 # needs the build env in the note below
```
What to verify on the outputs: expected files exist; `samples` = nsamps; years = the projection grid; units `mm`; no NaNs; the total equals the sum
you intend. For BAM, `notebooks/run_bam.py` does all of this and `notebooks/4_bam_ssp585_viz.ipynb` plots it.

## 7. Submit
Fork `fact-sealevel/facts-module-registry`, add `<module>/<module>_module.yaml`, check volumes/sources (section 2), open a PR against `main`.

## Gotchas seen while doing BAM
- `setup-experiment` run non-interactively leaves `workflows:` empty, so the generated script silently has no `facts-total` stage.
- `--extremesealevel-step NONE` failed on the `add_apptainer_command` branch (looks up a module called NONE); omit the flag.
- FEB needs a climate step, so a sea-level-only test still runs fair-temperature first.
- Apptainer image builds need an exec-capable temp dir. On this node `/tmp` is `noexec` and the shell's `APPTAINER_TMPDIR` pointed at a missing path;
  `/dev/shm` works. `notebooks/run_bam.py` sets `APPTAINER_TMPDIR`, `APPTAINER_CACHEDIR` and `PROOT_TMP_DIR` for you.
- Whether sample *i* of a sea-level module pairs with sample *i* of the climate module is a property of the module's own sampling logic; check it
  before claiming paired uncertainty.
