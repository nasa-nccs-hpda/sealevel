# Local patches to the module registry

`facts2/facts-module-registry/` is a git-ignored clone of `fact-sealevel/facts-module-registry` (pristine upstream `a085795`). The patches here are
applied on top of it; `feb setup-experiment` copies the module definitions into the experiment's config, so apply them BEFORE setting up an experiment
(an experiment generated earlier keeps the old definitions and must be regenerated).

```bash
cd facts2
git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch            # needed by every experiment that uses bamber19-icesheets
git -C facts-module-registry apply ../patches/deconto21_larmip_pass_to_total.patch    # needed by coupling-585-260603 (workflows wf2f, wf2e, wf3f, wf3e)
```

| Patch | Lines | What it does | Upstream |
|---|---|---|---|
| `bamber19_pass_to_total.patch` | +4 | `pass_to_total: false` on the EAIS and WAIS global and local outputs of `bamber19-icesheets` | issue facts-experiment-builder#144, PR facts-module-registry#20 (open) |
| `deconto21_larmip_pass_to_total.patch` | +10 −5 | the same for `deconto21-ais` (EAIS, WAIS; 4 outputs) and `larmip-ais` (EAIS, WAIS, PEN, SMB global; EAIS, WAIS local; 6 outputs) | issue facts-experiment-builder#145, PR facts-module-registry#21 (open, 2026-10-19); see `../REPORT_catalog_run_findings.md` |

Why: `facts-total` adds up every output a module lists unless it is marked `pass_to_total: false` (the default is `true`). In these three modules the AIS
output already equals the sum of the regional outputs (checked on real outputs to 0.001 mm), so listing both counts Antarctica twice. The patches keep the
aggregate and drop the parts, as `emulandice-ais` does upstream. `notebooks/run_bam.py` and `notebooks/run_coupling.py` read the generated script's `--item`
lines and refuse to run when an aggregate is listed with its parts (`--allow-double-count` overrides).

### Container patch
`container/emulandice_glaciers_project.py` is not a registry patch: `run_coupling.py` binds it over `/opt/emulandice/src/emulandice/emulandice_glaciers_project.py`
inside the `emulandice:0.2.0` image when it runs emulandice-glaciers (`diff container/emulandice_glaciers_project.orig.py container/emulandice_glaciers_project.py` shows the
change). It copies R's CSV to the output volume, skips lines that are not data rows, and raises if the CSV is incomplete. It goes together with the larger `/tmp` the driver
gives emulandice (the container's own `/tmp` is a 16 MB tmpfs that the glaciers run fills up at 2000 samples). See `../REPORT_catalog_run_findings.md`, 3b.

If a patch fails with "patch does not apply", the registry already contains the change (for example after the upstream PR was merged): skip that step.
Check with `git -C facts-module-registry diff --stat` which patches are currently applied.
