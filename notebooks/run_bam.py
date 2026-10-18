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
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


FEB_REF = "git+https://github.com/fact-sealevel/facts-experiment-builder@add_apptainer_command"

EXPECTED = {
    "fair-temperature": ["climate.nc", "gsat.nc", "oceantemp.nc", "ohc.nc"],
    "bamber19-icesheets": [f"{r}-{k}.nc" for r in ("AIS", "EAIS", "WAIS", "GIS") for k in ("gslr", "lslr")],
}


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


# =============================================================================
# Config
# =============================================================================

@dataclass
class Config:
    workspace: str = "/panfs/ccds02/nobackup/projects/ilab/projects/sealevel/facts2"
    experiment: str = "apptainer_experiments/bam_ssp585"
    build_dir: str = "/dev/shm/apptainer_build"  # must be exec-capable local space; /tmp is noexec here
    nsamps: int = 500
    scenario: str = "ssp585"
    pipeline_id: str = "bam001"
    pyear_start: int = 2020
    pyear_end: int = 2150
    pyear_step: int = 10
    regenerate: bool = False
    skip_run: bool = False
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
    text = open(cfg.config_yaml).read()
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


def regenerate(cfg: Config, log) -> bool:
    """feb setup-experiment refuses to overwrite an existing config; remove the experiment dir first if redoing."""
    if os.path.exists(cfg.config_yaml):
        log.error(f"{cfg.config_yaml} exists; move it aside before --regenerate")
        return False
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


def build_env(cfg: Config, log) -> Dict[str, str]:
    """Env for the subprocess: build/cache/proot dirs on an exec-capable filesystem."""
    env = os.environ.copy()
    for var in ("APPTAINER_TMPDIR", "APPTAINER_CACHEDIR"):
        old = env.get(var)
        if old and not os.path.isdir(old):
            log.warning(f"{var}={old} does not exist (pull would fail); overriding")
    if "noexec" in _mount_opts(cfg.build_dir).split(","):
        log.warning(f"{cfg.build_dir} is on a noexec mount; apptainer build will fail")
    os.makedirs(os.path.join(cfg.build_dir, "proot"), exist_ok=True)
    os.makedirs(os.path.join(cfg.build_dir, "cache"), exist_ok=True)
    env["APPTAINER_TMPDIR"] = cfg.build_dir
    env["APPTAINER_CACHEDIR"] = os.path.join(cfg.build_dir, "cache")
    env["PROOT_TMP_DIR"] = os.path.join(cfg.build_dir, "proot")
    return env


def preflight(cfg: Config, log) -> bool:
    ok = True
    if not shutil.which("apptainer"):
        log.error("apptainer not on PATH")
        ok = False
    if not os.path.isfile(cfg.script):
        log.error(f"missing {cfg.script}")
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
    env = build_env(cfg, log)
    log_path = os.path.join(cfg.workspace, "run.log")
    timing = ["/usr/bin/time", "-v"] if os.path.exists("/usr/bin/time") else []
    cmd = timing + ["bash", cfg.script]
    log.info(f"running {shlex.join(cmd)} (log: {log_path})")
    start = time.time()
    with open(log_path, "w") as fh:
        rc = subprocess.run(cmd, cwd=cfg.workspace, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
    wall = time.time() - start
    text = open(log_path).read()
    shutil.rmtree(cfg.build_dir, ignore_errors=True)  # build dir may live in RAM (/dev/shm)

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

    years = list(range(cfg.pyear_start, cfg.pyear_end + 1, cfg.pyear_step))
    report, ok = {}, True
    for mod, files in EXPECTED.items():
        for fn in files:
            path = os.path.join(cfg.out_dir, mod, fn)
            if not os.path.isfile(path):
                log.error(f"MISSING {mod}/{fn}")
                ok = False
                continue
            ds = xr.open_dataset(path)
            entry = {"dims": dict(ds.sizes)}
            if mod == "bamber19-icesheets":  # projection files: samples x years x locations
                v = ds["sea_level_change"]
                got = [int(y) for y in ds["years"].values]
                bad = int(np.isnan(v.values).sum())
                entry.update(units=v.attrs.get("units"), nan=bad,
                             p50_last=float(np.percentile(v.isel(years=-1), 50)))
                if ds.sizes["samples"] != cfg.nsamps or got != years or bad:
                    log.error(f"{mod}/{fn}: samples={ds.sizes['samples']} years={got} nan={bad}")
                    ok = False
            elif fn != "climate.nc":  # climate.nc holds only a 'year' coord; others are samples x years
                if ds.sizes.get("samples") != cfg.nsamps:
                    log.error(f"{mod}/{fn}: samples={ds.sizes.get('samples')}")
                    ok = False
            report[f"{mod}/{fn}"] = entry
            log.debug(f"{mod}/{fn}: {entry}")
    # Consistency: AIS = EAIS + WAIS (global, final year)
    g = lambda r: xr.open_dataset(os.path.join(cfg.out_dir, "bamber19-icesheets", f"{r}-gslr.nc"))["sea_level_change"].isel(years=-1).values
    if all(os.path.isfile(os.path.join(cfg.out_dir, "bamber19-icesheets", f"{r}-gslr.nc")) for r in ("AIS", "EAIS", "WAIS")):
        diff = float(np.abs(g("AIS") - g("EAIS") - g("WAIS")).max())
        report["AIS_minus_EAIS_WAIS_maxabs_mm"] = diff
        if diff > 0.01:
            log.error(f"AIS != EAIS+WAIS (max diff {diff} mm)")
            ok = False
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
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    cfg = Config(workspace=a.workspace, experiment=a.experiment, build_dir=a.build_dir, nsamps=a.nsamps,
                 regenerate=a.regenerate, skip_run=a.skip_run, verbose=a.verbose)
    log = setup_logging(cfg.verbose)
    summary: Dict = {}
    t0 = time.time()

    if cfg.regenerate and not regenerate(cfg, log):
        return 1
    if not validate_config(cfg, log):
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
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"summary -> {out} (total {summary['total_s']}s)")
    return 0 if summary["outputs"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
