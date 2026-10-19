#!/usr/bin/env python
"""
run_bam.py - FACTS2 BAM (bamber19-icesheets) + fair-temperature ssp585 driver (Apptainer)

Steps: validate config -> (optional) feb setup/generate -> preflight -> run the
generated experiment-apptainer.sh (timed) -> validate netCDF outputs -> write JSON summary.
The generated FEB script is never edited; environment overrides are applied to the subprocess only.
"""

import argparse
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


FEB_REF = "git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command"

EXPECTED = {
    "fair-temperature": ["climate.nc", "gsat.nc", "oceantemp.nc", "ohc.nc"],
    "bamber19-icesheets": [f"{r}-{k}.nc" for r in ("AIS", "EAIS", "WAIS", "GIS") for k in ("gslr", "lslr")],
    "facts-total": ["all-modules_global_total.nc", "all-modules_local_total.nc"],
}

# Data variable expected in each netCDF file (climate.nc holds only a 'year' coordinate)
VARIABLE = {
    "gsat.nc": "surface_temperature",
    "oceantemp.nc": "deep_ocean_temperature",
    "ohc.nc": "ocean_heat_content",
}
SLR_VAR = "sea_level_change"  # bamber19-icesheets and facts-total, units mm


# =============================================================================
# Logging
# =============================================================================

def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    return logging.getLogger(__name__)


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


# =============================================================================
# Config
# =============================================================================

@dataclass
class Config:
    workspace: str = "/panfs/ccds02/nobackup/projects/ilab/projects/sealevel/facts2"
    experiment: str = "apptainer_experiments/bam_ssp585_fixed"   # registry fix applied; bam_ssp585 double-counts Antarctica
    build_dir: str = "/dev/shm/apptainer_build"  # must be exec-capable local space; /tmp is noexec here
    nsamps: int = 500
    scenario: str = "ssp585"
    pipeline_id: str = "bam001"
    pyear_start: int = 2020
    pyear_end: int = 2150
    pyear_step: int = 10
    regenerate: bool = False
    skip_run: bool = False
    allow_double_count: bool = False
    verbose: bool = False
    steps: List[str] = field(default_factory=list)

    @property
    def exp_dir(self): return os.path.join(self.workspace, self.experiment)
    @property
    def script(self): return os.path.join(self.exp_dir, "experiment-apptainer.sh")
    @property
    def config_yaml(self): return os.path.join(self.exp_dir, "experiment-config.yaml")
    @property
    def out_dir(self): return os.path.join(self.exp_dir, "output-apptainer")


# =============================================================================
# Config validation
# =============================================================================

def validate_config(cfg: Config, log) -> bool:
    """Check experiment-config.yaml matches the requested parameters."""
    if not os.path.isfile(cfg.config_yaml):
        log.error(f"missing {cfg.config_yaml} (run with --regenerate)")
        return False
    text = _read(cfg.config_yaml)
    ok = True
    # keys sit on one line, value on the next non-comment line
    want = {"pipeline-id": cfg.pipeline_id, "nsamps": cfg.nsamps, "scenario": cfg.scenario,
            "pyear_start": cfg.pyear_start, "pyear_end": cfg.pyear_end, "pyear_step": cfg.pyear_step}
    for key, val in want.items():
        m = re.search(rf"^{re.escape(key)}:\s*\n(?:\s*#.*\n)*\s*(\S+)", text, re.M)
        got = m.group(1) if m else None
        if got != str(val):
            log.error(f"config {key}: expected {val}, found {got}")
            ok = False
        else:
            log.debug(f"config {key}={got} OK")
    for mod in ("fair-temperature", "bamber19-icesheets"):
        if f"ghcr.io/fact-sealevel/{mod}:" not in text:
            log.error(f"module image for {mod} not in config")
            ok = False
    log.info(f"config validation: {'OK' if ok else 'FAILED'}")
    return ok


# =============================================================================
# FEB setup / generate
# =============================================================================

def feb(cfg: Config, args: List[str], log) -> int:
    cmd = ["uvx", "--from", FEB_REF, "feb"] + args
    log.info("FEB: " + shlex.join(cmd))
    return subprocess.run(cmd, cwd=cfg.workspace).returncode


def check_total_items(cfg: Config, log) -> List[str]:
    """Problems in the facts-total --item lists of the generated script (empty list = fine).

    AIS (all of Antarctica) already equals EAIS + WAIS, so a total that lists AIS together with EAIS or WAIS
    for the same module and result type counts Antarctica twice. Checked on the script, before anything runs.
    """
    try:
        text = _read(cfg.script)
    except OSError:
        return []                                  # preflight reports a missing script
    groups: Dict[tuple, List[str]] = {}
    for module, comp, kind in re.findall(r'--item=[^"\s]*/([^/"\s]+)/([A-Za-z0-9_]+)-(gslr|lslr)\.nc', text):
        groups.setdefault((module, kind), []).append(comp)
    if not groups:
        log.warning("no facts-total --item lines in the generated script (no facts-total stage); total not checked")
        return []
    problems = []
    for (module, kind), comps in sorted(groups.items()):
        log.info(f"facts-total {kind} items from {module}: {', '.join(comps)}")
        if "AIS" in comps and ({"EAIS", "WAIS"} & set(comps)):
            problems.append(f"facts-total {kind} adds AIS together with {' and '.join(sorted({'EAIS', 'WAIS'} & set(comps)))} "
                            f"({module}): Antarctica is counted twice. Apply facts2/patches/bamber19_pass_to_total.patch to the "
                            f"registry and regenerate, or use bam_ssp585_fixed.")
    return problems


def registry_has_fix(cfg: Config) -> bool:
    """True if the workspace's registry clone marks bamber19 outputs pass_to_total: false (see facts2/patches/)."""
    path = os.path.join(cfg.workspace, "facts-module-registry/bamber19-icesheets/bamber19_icesheets_module.yaml")
    try:
        return "pass_to_total: false" in _read(path)
    except OSError:
        return False


def regenerate(cfg: Config, log) -> bool:
    """feb setup-experiment refuses to overwrite an existing config; remove the experiment dir first if redoing."""
    if os.path.exists(cfg.config_yaml):
        log.error(f"{cfg.config_yaml} exists; move it aside before --regenerate")
        return False
    os.makedirs(os.path.dirname(cfg.exp_dir), exist_ok=True)   # feb setup-experiment never creates the parent directory
    if not registry_has_fix(cfg):
        log.warning("registry clone lacks the bamber19 pass_to_total fix: facts-total will double-count Antarctica. "
                    "Apply it first: git -C facts-module-registry apply ../patches/bamber19_pass_to_total.patch")
    # --extremesealevel-step NONE fails on this FEB branch, so the flag is omitted
    rc = feb(cfg, ["setup-experiment", "--experiment-name", cfg.experiment,
                   "--climate-step", "fair-temperature", "--sealevel-step", "bamber19-icesheets",
                   "--pipeline-id", cfg.pipeline_id, "--scenario", cfg.scenario, "--baseyear", "2005",
                   "--pyear-start", str(cfg.pyear_start), "--pyear-end", str(cfg.pyear_end),
                   "--pyear-step", str(cfg.pyear_step), "--nsamps", str(cfg.nsamps),
                   "--location-file", "location.lst",
                   "--module-specific-input-data", os.path.join(cfg.workspace, "data/module_specific_input_data"),
                   "--shared-input-data", os.path.join(cfg.workspace, "data/shared_input_data")], log)
    if rc != 0:
        return False
    # setup-experiment leaves 'workflows' empty when run non-interactively, and generate-apptainer
    # then emits no facts-total stage. Add the workflow to the config (the script itself is never edited).
    text = _read(cfg.config_yaml)
    marker = "##----- Workflows (facts-total) -----##\n"
    if "\nworkflows:" not in text and marker in text:
        open(cfg.config_yaml, "w").write(text.replace(marker, marker + 'workflows:\n  all-modules: "bamber19-icesheets"\n'))
        log.info("added workflows.all-modules to experiment-config.yaml")
    return feb(cfg, ["generate-apptainer", "--experiment-name", cfg.experiment], log) == 0


# =============================================================================
# Preflight (diagnostics for the failures seen on this node)
# =============================================================================

def _mount_opts(path: str) -> str:
    best, opts = "", ""
    for line in open("/proc/mounts"):
        dev, mp, _, o = line.split()[:4]
        if path.startswith(mp.rstrip("/") + "/") or path == mp:
            if len(mp) > len(best):
                best, opts = mp, o
    return opts


def build_env(cfg: Config, log):
    """Env for the subprocess: build/cache/proot dirs on an exec-capable filesystem.

    Returns (env, run_dir). run_dir is a fresh subdirectory created here; it is the only
    thing the driver deletes afterward, so a user-supplied --build-dir is never wiped."""
    env = os.environ.copy()
    for var in ("APPTAINER_TMPDIR", "APPTAINER_CACHEDIR"):
        old = env.get(var)
        if old and not os.path.isdir(old):
            log.warning(f"{var}={old} does not exist (pull would fail); overriding")
    if "noexec" in _mount_opts(cfg.build_dir).split(","):
        log.warning(f"{cfg.build_dir} is on a noexec mount; apptainer build will fail")
    os.makedirs(cfg.build_dir, exist_ok=True)
    run_dir = tempfile.mkdtemp(prefix="run_bam_", dir=cfg.build_dir)
    os.makedirs(os.path.join(run_dir, "proot"))
    os.makedirs(os.path.join(run_dir, "cache"))
    env["APPTAINER_TMPDIR"] = run_dir
    env["APPTAINER_CACHEDIR"] = os.path.join(run_dir, "cache")
    env["PROOT_TMP_DIR"] = os.path.join(run_dir, "proot")
    return env, run_dir


def preflight(cfg: Config, log) -> bool:
    ok = True
    if not shutil.which("apptainer"):
        log.error("apptainer not on PATH")
        ok = False
    if not os.path.isfile(cfg.script):
        log.error(f"missing {cfg.script}")
        ok = False
    else:
        # generated scripts embed absolute paths (WORKSPACE=...); one generated elsewhere would read and write THAT workspace
        m = re.search(r'^WORKSPACE="([^"]+)"', _read(cfg.script), re.M)
        if m and os.path.realpath(m.group(1)) != os.path.realpath(cfg.workspace):
            log.error(f"{cfg.script} was generated for workspace {m.group(1)}, not {cfg.workspace}; running it would use "
                      f"that workspace's data and outputs. Regenerate here (run_bam.py --regenerate --experiment <new name>).")
            ok = False
    for sub in ("module_specific_input_data/bamber19-icesheets", "module_specific_input_data/fair-temperature",
                "shared_input_data/FPRINT", "shared_input_data/location.lst"):
        p = os.path.join(cfg.workspace, "data", sub)
        if not os.path.exists(p):
            log.error(f"missing input {p}")
            ok = False
    log.info(f"preflight: {'OK' if ok else 'FAILED'}")
    return ok


# =============================================================================
# Run
# =============================================================================

def run_script(cfg: Config, log) -> Dict:
    env, run_dir = build_env(cfg, log)
    log_path = os.path.join(cfg.workspace, "run.log")
    timing = ["/usr/bin/time", "-v"] if os.path.exists("/usr/bin/time") else []
    cmd = timing + ["bash", cfg.script]
    log.info(f"running {shlex.join(cmd)} (log: {log_path})")
    start = time.time()
    with open(log_path, "w") as fh:
        rc = subprocess.run(cmd, cwd=cfg.workspace, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
    wall = time.time() - start
    text = _read(log_path)
    shutil.rmtree(run_dir, ignore_errors=True)  # per-run dir only; may live in RAM (/dev/shm)

    # Stage timings from the script's own "[HH:MM:SS] ..." log lines
    stamps = re.findall(r"^\[(\d\d):(\d\d):(\d\d)\] (Running service|Completed): (\S+)", text, re.M)
    svc: Dict[str, Dict] = {}
    for h, m, s, kind, name in stamps:
        t = int(h) * 3600 + int(m) * 60 + int(s)
        svc.setdefault(name, {})["start" if kind.startswith("Running") else "end"] = t
    service_s = {n: v["end"] - v["start"] for n, v in svc.items() if "start" in v and "end" in v}
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    pulled = len(re.findall(r"^\[[\d:]+\] Pulling ", text, re.M))
    res = {"exit": rc, "wall_s": round(wall, 1), "service_s": service_s, "images_pulled": pulled,
           "max_rss_mb": round(int(rss.group(1)) / 1024, 1) if rss else None}
    log.info(f"run exit={rc} wall={wall:.1f}s services={service_s} images_pulled={pulled} max_rss_mb={res['max_rss_mb']}")
    if rc != 0:
        log.error("tail of run.log:\n" + "\n".join(l for l in text.splitlines() if "warn" not in l)[-1500:])
    return res


# =============================================================================
# Output validation
# =============================================================================

def validate_outputs(cfg: Config, log) -> Dict:
    import numpy as np
    import xarray as xr

    def p50_final(a):
        """Final-year median over samples; with several sites, the median across sites of those."""
        return float(np.median(np.median(a[:, -1], axis=0)))

    years = list(range(cfg.pyear_start, cfg.pyear_end + 1, cfg.pyear_step))
    report, ok, warnings = {}, True, []
    bam = os.path.join(cfg.out_dir, "bamber19-icesheets")

    def fail(msg):
        nonlocal ok
        log.error(msg)
        ok = False

    for mod, files in EXPECTED.items():
        for fn in files:
            path = os.path.join(cfg.out_dir, mod, fn)
            if not os.path.isfile(path):
                fail(f"MISSING {mod}/{fn}")
                continue
            ds = xr.open_dataset(path)
            entry = {"dims": dict(ds.sizes)}
            if fn == "climate.nc":  # only a 'year' coordinate, no data variables
                report[f"{mod}/{fn}"] = entry
                continue
            var = VARIABLE.get(fn, SLR_VAR)
            if var not in ds:
                fail(f"{mod}/{fn}: variable {var!r} missing (has {list(ds.data_vars)})")
                continue
            v = ds[var]
            bad = int((~np.isfinite(v.values)).sum())
            entry.update(variable=var, units=v.attrs.get("units"), nonfinite=bad)
            if ds.sizes.get("samples") != cfg.nsamps or bad:
                fail(f"{mod}/{fn}: samples={ds.sizes.get('samples')} nonfinite={bad}")
            if var == SLR_VAR:  # projection files: samples x years x locations, mm
                got = [int(y) for y in ds["years"].values]
                entry["p50_last"] = p50_final(v.transpose("samples", "years", ...).values)
                if got != years:
                    fail(f"{mod}/{fn}: years={got}, expected {years}")
                if v.attrs.get("units") != "mm":
                    fail(f"{mod}/{fn}: units={v.attrs.get('units')!r}, expected 'mm'")
            report[f"{mod}/{fn}"] = entry
            log.debug(f"{mod}/{fn}: {entry}")

    def series(path):
        return xr.open_dataset(path)[SLR_VAR].values.squeeze()  # (samples, years) or (samples, years, sites)

    # Consistency: AIS = EAIS + WAIS (all years, global)
    comps = {r: os.path.join(bam, f"{r}-gslr.nc") for r in ("AIS", "EAIS", "WAIS", "GIS")}
    if all(os.path.isfile(f) for f in comps.values()):
        diff = float(np.abs(series(comps["AIS"]) - series(comps["EAIS"]) - series(comps["WAIS"])).max())
        report["AIS_minus_EAIS_WAIS_maxabs_mm"] = diff
        if diff > 0.01:
            fail(f"AIS != EAIS+WAIS (max diff {diff} mm)")

    # facts-total sums every bamber19 output it is given. AIS already contains EAIS + WAIS,
    # so the correct total is AIS + GIS; the sum of all four double-counts Antarctica.
    for scale, kind in (("global", "gslr"), ("local", "lslr")):
        tot = os.path.join(cfg.out_dir, "facts-total", f"all-modules_{scale}_total.nc")
        parts = {r: os.path.join(bam, f"{r}-{kind}.nc") for r in ("AIS", "EAIS", "WAIS", "GIS")}
        if not (os.path.isfile(tot) and all(os.path.isfile(f) for f in parts.values())):
            continue
        t = series(tot)
        c = {r: series(f) for r, f in parts.items()}
        correct, four = c["AIS"] + c["GIS"], sum(c.values())
        d_correct, d_four = float(np.abs(t - correct).max()), float(np.abs(t - four).max())
        report[f"total_{scale}"] = {"max_abs_diff_vs_AIS_plus_GIS_mm": d_correct,
                                    "max_abs_diff_vs_all_four_mm": d_four,
                                    "p50_last_total": p50_final(t),
                                    "p50_last_AIS_plus_GIS": p50_final(correct)}
        if d_correct < 0.01:
            log.info(f"facts-total {scale}: equals AIS+GIS")
        elif d_four < 0.01:
            warnings.append(f"facts-total {scale} = AIS+EAIS+WAIS+GIS (double-counts Antarctica); "
                            f"final-year median {p50_final(t):.0f} mm vs {p50_final(correct):.0f} mm for AIS+GIS"
                            + (f" (median across {t.shape[-1]} sites)" if t.ndim == 3 else ""))
        else:
            fail(f"facts-total {scale} matches neither AIS+GIS (diff {d_correct}) nor all four (diff {d_four})")
    for w in warnings:
        log.warning(w)
    report["warnings"] = warnings
    report["p50_last_definition"] = ("final-year median over samples; with several sites, the median across sites of those "
                                     "per-site medians (not a pooled median over all samples and sites)")
    log.info(f"output validation: {'OK' if ok else 'FAILED'} ({len(report)} checks)")
    report["ok"] = ok
    return report


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Run FACTS2 fair-temperature + bamber19-icesheets (ssp585) via Apptainer")
    d = Config()
    p.add_argument("--workspace", default=d.workspace)
    p.add_argument("--experiment", default=d.experiment)
    p.add_argument("--build-dir", default=d.build_dir, help="exec-capable dir for apptainer build/cache (default /dev/shm)")
    p.add_argument("--nsamps", type=int, default=d.nsamps)
    p.add_argument("--regenerate", action="store_true", help="run feb setup-experiment + generate-apptainer first")
    p.add_argument("--skip-run", action="store_true", help="only validate config and existing outputs")
    p.add_argument("--allow-double-count", action="store_true",
                   help="run even if the script's facts-total would count Antarctica twice (e.g. to redo the original bam_ssp585)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    cfg = Config(workspace=a.workspace, experiment=a.experiment, build_dir=a.build_dir, nsamps=a.nsamps,
                 regenerate=a.regenerate, skip_run=a.skip_run, allow_double_count=a.allow_double_count,
                 verbose=a.verbose)
    log = setup_logging(cfg.verbose)
    summary: Dict = {}
    t0 = time.time()

    if cfg.regenerate and not regenerate(cfg, log):
        return 1
    if not validate_config(cfg, log):
        return 1
    problems = check_total_items(cfg, log)
    blocking = bool(problems) and not (cfg.skip_run or cfg.allow_double_count)
    for msg in problems:
        (log.error if blocking else log.warning)(msg)
    if blocking:
        log.error("refusing to run (nothing was executed); pass --allow-double-count to run it anyway")
        return 1
    if not cfg.skip_run:
        if not preflight(cfg, log):
            return 1
        summary["run"] = run_script(cfg, log)
        if summary["run"]["exit"] != 0:
            return 1
    summary["outputs"] = validate_outputs(cfg, log)
    summary["total_s"] = round(time.time() - t0, 1)

    out = os.path.join(cfg.workspace, "bam_results.json")
    if cfg.skip_run and "run" not in summary and os.path.isfile(out):  # keep timing from the last real run
        try:
            prev = json.loads(_read(out)).get("run")
            if prev:
                summary["run"] = prev
        except (OSError, ValueError):
            pass
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"summary -> {out} (total {summary['total_s']}s)")
    return 0 if summary["outputs"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
