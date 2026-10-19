# Changing the science in `bamber19-icesheets` (BAM): a roadmap

For someone who wants to change how BAM turns temperature into ice-sheet sea-level contributions, and does not know FACTS2. All line numbers refer to **image `ghcr.io/fact-sealevel/bamber19-icesheets:0.2.0`**
(upstream repo https://github.com/fact-sealevel/bamber19-icesheets, release v0.2.0); check them again if you work on another version. Everything below was read from that image and exercised in
the BAM experiments of this repository (`facts2/apptainer_experiments/bam_ssp585_fixed*`); what was not tried is marked as such.

## 1. What the module does
BAM re-uses the ice-sheet projections of Bamber et al. (2019), a structured expert elicitation, for two scenarios (a *low* one with 2.0 degC of warming in 2100 and a *high* one with 5.0 degC).
Each scenario is a data file of many equally likely ice-sheet realisations for the West Antarctic (WAIS), East Antarctic (EAIS) and Greenland (GIS) ice sheets.
Run inside FACTS2 with a climate file, BAM does three things:

1. **Choose a pool per sample.** Each climate member (one temperature trajectory from `fair-temperature`) decides, with a probability that rises with its warming, whether its output sample is drawn
   from the high or the low pool (`pickScenario`).
2. **Draw a realisation.** For every sample one row of the chosen pool is drawn at random; the same row index is used for WAIS, EAIS, GIS and AIS (= EAIS + WAIS), so the components of one sample come from one expert realisation.
3. **Localise.** `local = global x fingerprint` per ice sheet and site (`postprocess`), where the fingerprints are the static sea-level patterns in `FPRINT/`.

Inputs: the climate file (`climate.nc`), `SLRProjections190726core_SEJ_full.mat` (the elicitation data), the location file, the fingerprints. Outputs: `{AIS,EAIS,WAIS,GIS}-{gslr,lslr}.nc`, in mm,
samples x years x locations. There is no temperature-to-ice-loss physics here: temperature only picks the pool.

## 2. Where the science lives
| File (in `/opt/bamber19-icesheets/src/bamber19_icesheets/`) | Lines | What it holds |
|---|---|---|
| `bamber19_icesheets_project.py` | 395-427 | `pickScenario`: the high/low selection (section 3). **The place to change how BAM responds to temperature.** |
| | 342-392 | `GetSATData`: reads `surface_temperature` per scenario from the climate file, subtracts the 1850-1900 mean, crops to 1900-2300. |
| | 221-339 | `bamber19_project_icesheets_temperaturedriven`: picks the pool, draws the realisations (lines 278-297), writes the global files. |
| | 91-220 | the older path without a climate file (scenario argument). Not used by FACTS2 runs with a climate step. |
| `bamber19_icesheets_preprocess.py` | 119-177 | `ExtractSamples`: reads the `.mat` file (`corefileH`, `corefileL`), picks the target years, subtracts each sample's value in the base year. Uses **positional indices** into the MATLAB structure (`[0, 0][27]` years, `[0, 0][21]` samples). |
| `bamber19_icesheets_postprocess.py` | 27-277 | fingerprints (`fprint_gis.nc`, `fprint_wais.nc`, `fprint_eais.nc`) applied to the samples (lines 100-105; local AIS = local WAIS + local EAIS). |
| `cli.py` | whole file | the options. There is **no science option**: `--rngseed`, `--replace`, `--chunksize`, `--nsamps` (ignored when a climate file is given: the sample count is the number of climate members). |

## 3. The selection, line by line (`bamber19_icesheets_project.py`)
```python
395  def pickScenario(climate_data_file, scenario, rng):
403      SAT, Time, NumTensemble = GetSATData(climate_data_file, scenario)
         # find integrated SAT over 2000-2099
406      x2 = np.where((Time[:] < 2100) * (Time[:] >= 2000))
407      SAT2 = SAT[x2]
408      iSAT = SAT2.sum(axis=0)                     # degC*yr above 1850-1900, per climate member
         # Bamber 19 low scenario:  0.7 C in 2000, 1.5 C in 2050, 2.0 C in 2100 = 142.5 C*yr
         # Bamber 19 high scenario: 0.7 C in 2000, 2.0 C in 2050, 5.0 C in 2100 = 242.5 C*yr
418      iSAT_marker = np.array([142.5, 242.5])
420      f2 = np.minimum(1, np.maximum(0, (iSAT - iSAT_marker[0]) / (iSAT_marker[1] - iSAT_marker[0])))
423      weights = f2                                # P(high pool) per member
425      selector = rng.random(iSAT.size)
426      useHigh = selector < weights
427      return useHigh
```
Then, in `bamber19_project_icesheets_temperaturedriven`:
```python
278      rng = np.random.default_rng(rngseed)
281      useHigh = pickScenario(climate_data_file=climate_data_file, scenario=scenario, rng=rng)
284      nsamps = useHigh.size
287      sample_inds = rng.choice(ais_samplesL.shape[0], size=nsamps, replace=replace)   # same row index for every component
289-292  eais/wais/ais/gis_samps = <component>_samplesL[sample_inds, :]                  # start from the low pool ...
294-297  <component>_samps[useHigh, :] = <component>_samplesH[sample_inds[useHigh], :]    # ... overwrite the "high" samples from the high pool
```
Measured on the reference run (ssp585, 500 members): 300 members have weight 1 and the mean weight is 0.91, so 91% of the samples come from the high pool whatever the member; the rank correlation between a
member's warming and its output is only +0.05 to +0.07 (null 0.00 +/- 0.045). BAM is therefore *not* a paired temperature-to-ice-loss model (`HANDOFF.md`, "Sample pairing"; `notebooks/check_bam_pairing.py`).

## 4. Options, from least to most work
| # | Change | Where | Effect on the science | Effort / risk |
|---|---|---|---|---|
| A | Change the two marker values (142.5, 242.5) or make them options | line 418 (+ `cli.py`, registry YAML) | moves the warming range over which the weight rises; e.g. higher markers = fewer high-pool samples | small; the markers are the integrals of Bamber's two scenarios, so changing them changes what "low" and "high" mean |
| B | Replace the linear ramp by another function (steeper, S-shaped, a step) | lines 420-423 | changes how sharply temperature selects the pool; a step makes the choice deterministic | small |
| C | Change the integration window (2000-2099) or use another temperature measure (peak, end-of-century) | lines 406-408 | changes which warming matters; the markers must be recomputed for the new measure | small, but recompute the markers |
| D | **Pair samples more strongly with temperature**: choose the realisation row by rank (hotter member -> larger ice loss in the pool) instead of at random | line 287, and the lines that use `sample_inds` (289-297) | turns BAM into a trajectory-like model; narrows the ensemble spread and correlates the totals with temperature; a scientific decision, not a bug fix | medium; document the choice, compare spreads |
| E | Use other pools (other scenarios, a third pool, different weights per ice sheet) | `ExtractSamples` and the `.mat` file (`corefileH`, `corefileL`) | needs data; the code assumes exactly two pools | large; needs new data in the same MATLAB layout or a rewrite of the reader |
| F | Per-ice-sheet selection (each component picks its own pool) | lines 289-297 (use separate `useHigh` per component) | decorrelates GIS and AIS within one sample | small to medium |
| G | Different fingerprints or a different localisation | `FPRINT/` data, `postprocess` | changes the local-to-global factors only (not the global files) | small if only the data change |
| H | New outputs (e.g. the pool each sample used) | `make_projection_ds`, `cli.py`, registry YAML | none; useful for diagnostics | small; every new output must be listed in the registry YAML, and think about `pass_to_total` (section 7) |

If you change the number of random numbers drawn before line 287 (anything that adds or removes calls on `rng`), every sample after it changes, including those your change did not intend to touch: the
comparison in section 6 is then no longer like for like.

## 5. How to run a changed version
1. **Quick experiment: bind a patched file over the original (no image build).**
   - Copy the file out of the image: `apptainer exec --no-home --containall --pwd / facts2/apptainer_experiments/sif/bamber19-icesheets-0.2.0.sif cat /opt/bamber19-icesheets/src/bamber19_icesheets/bamber19_icesheets_project.py > facts2/patches/container/bamber19_icesheets_project.py`, keep an untouched `*.orig.py` next to it, edit the copy.
   - Add an entry to `CONTAINER_PATCHES` in `notebooks/run_coupling.py` (`"bamber19-icesheets": ("patches/container/bamber19_icesheets_project.py", "/opt/bamber19-icesheets/src/bamber19_icesheets/bamber19_icesheets_project.py")`). The shim then binds it for that service in any experiment run through that driver. `run_bam.py` has no such feature yet; add the same `--bind` or run the container by hand (below).
   - Or run the container by hand with the arguments from the generated script (`experiment-apptainer.sh`, block `# --- bamber19-icesheets ---`) and add `--bind=<patched file>:<path in image>:ro`.
2. **A proper version: fork, build an image, point the experiment at it.** The upstream repo has a `Dockerfile`, a `justfile` and a CI workflow that publishes the image. Edit the code, build, tag it (a *new* tag), then set `image:` of `bamber19-icesheets` in the
   experiment's `experiment-config.yaml` and regenerate the script. **Gotcha:** the generated script pulls an image only if `apptainer_experiments/sif/<service>-<version>.sif` does not exist, so a new image under an old name is silently ignored.
   Give the new image a new version tag, or put your own `.sif` at the expected path.
3. **Contribute it.** Pull request on `fact-sealevel/bamber19-icesheets`; a new option also needs the registry entry (`facts-module-registry/bamber19-icesheets/bamber19_icesheets_module.yaml`, section `arguments`)
   and a registry PR. `facts2/INTEGRATING_A_MODULE.md` explains the YAML.

## 6. How to check that you changed what you meant to
- **Reference outputs:** experiment `bam_ssp585_fixed` (one site, 500 samples, seeds fixed) and `bam_ssp585_fixed_gauges` (1,030 gauges); tag `FACTS2-bam_ssp585_fixed_gauges-20261019`. The BAM runs were bit-identical on repetition.
- **Like-for-like comparison:** same climate file, same `--rngseed`, only your change. Samples your change does not affect stay bit-identical; `notebooks/check_bam_pairing.py` shows the method (it replicates `pickScenario` and
  predicts which samples change when the climate members are shuffled; update its copy of the logic if you change `pickScenario`). Run it with the command in its docstring.
- **Driver and validator:** `python3 notebooks/run_bam.py` (see `notebooks/README.md`, BAM section; about 4 minutes with images cached) checks sizes, units, finite values, AIS = EAIS + WAIS, and the totals. Tests: `notebooks/tests/test_run_bam.py`.
- **Look at the spread, not only the median:** compare the 5-95% range, the high-pool share and the per-sample rank correlation with temperature before and after.

## 7. Gotchas
- `nsamps` = number of climate members, whatever `--nsamps` says (read from the code; not tested).
- The three random draws share one generator: seed -> `useHigh` (n numbers) -> `sample_inds`.
- `facts-total` adds every output marked for the total. The registry fix `facts2/patches/bamber19_pass_to_total.patch` (PR fact-sealevel/facts-module-registry#20, open) keeps AIS and GIS and drops EAIS and WAIS from the total, because AIS = EAIS + WAIS. Without it the total counts Antarctica twice.
- The `.mat` file is read by position, not by name; a replacement must keep the layout.
- BAM covers the years in the `.mat` file; check `mat_years` before asking for years beyond 2100.
- The result has no regional dynamics beyond the fixed fingerprints; do not describe local values as independent regional projections.
