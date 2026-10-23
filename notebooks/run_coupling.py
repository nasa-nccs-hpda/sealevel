#!/usr/bin/env python
"""
run_coupling.py - FACTS2 coupling-585-260603 (the facts-experiment-catalog experiment) via FEB + Apptainer

Steps: (optional) feb setup-experiment + generate-apptainer with the catalog's command and workflows -> check the facts-total
--item lists for double counting -> preflight -> pull each distinct image once -> run the generated experiment-apptainer.sh
(timed; the script itself is never edited) -> validate every netCDF output, recompute each facts-total from its items ->
write <experiment>/coupling_results.json.

Catalog: https://github.com/fact-sealevel/facts-experiment-catalog/tree/main/coupling-585-260603
Reuses helpers from run_bam.py (build environment, logging). Run in an environment with numpy, xarray and netCDF4 for the
validation step, isolated from the system conda:

  env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 --with xarray --with netcdf4 --with 'numpy<2' \
      python notebooks/run_coupling.py [--regenerate] [--skip-run] ...
"""

import argparse
import glob
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_bam import FEB_REF, _read, build_env, setup_logging   # noqa: E402

# The catalog's `feb setup-experiment` command (note: the catalog text also lists ipccar5-icesheets, but its experiment-config.yaml
# does not contain it and no workflow uses it, so it is left out here).
SEALEVEL_STEPS = ("fittedismip-gris,deconto21-ais,bamber19-icesheets,emulandice-ais,emulandice-gris,emulandice-glaciers,"
                  "larmip-ais,ipccar5-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage")
WORKFLOWS = {   # verbatim from the catalog's experiment-config.yaml
    "wf1e": "emulandice-ais,emulandice-gris,emulandice-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
    "wf2f": "fittedismip-gris,larmip-ais,ipccar5-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
    "wf2e": "emulandice-gris,emulandice-glaciers,larmip-ais,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
    "wf3f": "fittedismip-gris,deconto21-ais,ipccar5-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
    "wf3e": "deconto21-ais,emulandice-gris,emulandice-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
    "wf4": "bamber19-icesheets,ipccar5-glaciers,tlm-sterodynamics,kopp14-verticallandmotion,ssp-landwaterstorage",
}
FAIR_VARIABLE = {"gsat.nc": "surface_temperature", "oceantemp.nc": "deep_ocean_temperature", "ohc.nc": "ocean_heat_content"}
SLR_VAR = "sea_level_change"

# Per module: (aggregate file, files it already contains). Listing both in one facts-total job counts the parts twice.
# larmip-ais, deconto21-ais, bamber19-icesheets: the aggregate-vs-parts relation was checked on the outputs (see HANDOFF.md), not assumed:
# larmip global AIS = EAIS + WAIS + PEN + SMB, local AIS = EAIS + WAIS; deconto21 and bamber19 AIS = EAIS + WAIS.
OVERLAPS = {
    "bamber19-icesheets": (r"^AIS-[gl]slr\.nc$", r"^(EAIS|WAIS)-[gl]slr\.nc$"),
    "deconto21-ais": (r"^ais-[gl]slr\.nc$", r"^(eais|wais)-[gl]slr\.nc$"),
    "larmip-ais": (r"^ais_(global|local)_output\.nc$", r"^(eais|wais|pen|smb)_(global|local)_output\.nc$"),
    "emulandice-ais": (r"^output-[gl]slr\.nc$", r"^output-[gl]slr-(eais|wais|pen)\.nc$"),
}


@dataclass
class Config:
    workspace: str = "/panfs/ccds02/nobackup/projects/ilab/projects/sealevel/facts2"
    experiment: str = "apptainer_experiments/coupling-585-260603"
    build_dir: str = "/dev/shm/apptainer_build"
    nsamps: int = 2000
    pyear_start: int = 2020
    pyear_end: int = 2150
    pyear_step: int = 10
    baseyear: int = 2005
    pipeline_id: str = "abcd"
    regenerate: bool = False
    skip_run: bool = False
    allow_double_count: bool = False
    gates: Tuple[str, ...] = ()
    resume: bool = False
    share: bool = False
    join: bool = False
    generate_only: bool = False
    verbose: bool = False

    @property
    def exp_dir(self): return os.path.join(self.workspace, self.experiment)
    @property
    def script(self): return os.path.join(self.exp_dir, "experiment-apptainer.sh")
    @property
    def config_yaml(self): return os.path.join(self.exp_dir, "experiment-config.yaml")
    @property
    def out_dir(self): return os.path.join(self.exp_dir, "output-apptainer")
    @property
    def sif_dir(self): return os.path.join(self.workspace, "apptainer_experiments", "sif")


# =============================================================================
# Reading the generated script
# =============================================================================

def parse_totals(script_text: str) -> Dict[str, List[str]]:
    """{'wf1e-global': ['emulandice-ais/output-gslr.nc', ...], ...} from the facts-total run_service blocks."""
    totals: Dict[str, List[str]] = {}
    for m in re.finditer(r'run_service "facts-total-([\w]+-(?:global|local))-[\d.]+"(.*?)(?=\n\n|\Z)', script_text, re.S):
        totals[m.group(1)] = re.findall(r'--item=/mnt/total_out/([^"\s]+)', m.group(2))
    return totals


def parse_images(script_text: str) -> List[Tuple[str, str]]:
    return re.findall(r'^pull_image "([^"]+)" "([^"]+)"', script_text, re.M)


def check_total_items(script_text: str) -> List[str]:
    """Problems in the facts-total --item lists: an aggregate output listed together with the parts it contains."""
    problems = []
    for key, items in sorted(parse_totals(script_text).items()):
        by_mod: Dict[str, List[str]] = {}
        for it in items:
            mod, _, fn = it.partition("/")
            by_mod.setdefault(mod, []).append(fn)
        for mod, files in by_mod.items():
            if mod not in OVERLAPS:
                continue
            agg, parts = (re.compile(p) for p in OVERLAPS[mod])
            a = [f for f in files if agg.match(f)]
            p = [f for f in files if parts.match(f)]
            if a and p:
                problems.append(f"facts-total {key} sums {mod}'s {a[0]} together with {', '.join(p)}: the parts are counted twice")
    return problems


def expected_files(script_text: str) -> List[str]:
    """Every .nc a module writes (relative to output-apptainer/), including the facts-total outputs."""
    return sorted(set(re.findall(r'=/mnt/(?:out|total_out)/([\w./-]+\.nc)"', script_text)))


# =============================================================================
# FEB setup / generate
# =============================================================================

def feb(cfg: Config, args: List[str], log, stdin: Optional[str] = None) -> int:
    cmd = ["uvx", "--from", FEB_REF, "feb"] + args
    log.info("FEB: " + shlex.join(cmd))
    return subprocess.run(cmd, cwd=cfg.workspace, input=stdin, text=True).returncode


def regenerate(cfg: Config, log) -> bool:
    """The catalog's setup command; the workflow prompts are answered with the catalog's six workflows."""
    if os.path.exists(cfg.config_yaml):
        log.error(f"{cfg.config_yaml} exists; move it aside before --regenerate")
        return False
    os.makedirs(os.path.dirname(cfg.exp_dir), exist_ok=True)
    answers = ["y"]
    for i, (name, mods) in enumerate(WORKFLOWS.items()):
        answers += [name, mods, "y" if i < len(WORKFLOWS) - 1 else "n"]
    rc = feb(cfg, ["setup-experiment", "--experiment-name", cfg.experiment, "--climate-step", "fair-temperature",
                   "--sealevel-step", SEALEVEL_STEPS, "--extremesealevel-step", "extremesealevel-pointsoverthreshold",
                   "--nsamps", str(cfg.nsamps), "--scenario", "ssp585", "--pyear-start", str(cfg.pyear_start),
                   "--pyear-end", str(cfg.pyear_end), "--pyear-step", str(cfg.pyear_step), "--baseyear", "2005"],
             log, stdin="\n".join(answers) + "\n")
    if rc != 0:
        return False
    text = _read(cfg.config_yaml)
    # setup-experiment adds an 'all-modules' workflow the catalog does not have, and leaves pipeline-id and the data
    # directories empty (the catalog's command passes none of them); fill them in as the catalog's config has them.
    text = re.sub(r'\n  all-modules: "[^\n]*"', "", text, count=1)
    text = text.replace("pipeline-id:\n", f"pipeline-id:\n        {cfg.pipeline_id}\n", 1)
    for key, sub in (("module-specific-input-data", "module_specific_input_data"), ("shared-input-data", "shared_input_data")):
        if re.search(rf"^{key}:[ \t]*\n(?:[ \t]+#.*\n)*[ \t]+[^\s#]", text, re.M) is None:   # no indented value line yet
            text = text.replace(f"{key}:\n", f'{key}:\n        "{os.path.join(cfg.workspace, "data", sub)}"\n', 1)
    # The registry's default input for emulandice-glaciers is climate.nc, which has no `years` variable, and the container stops with
    # KeyError: 'years'. The catalog's config (like emulandice-ais and -gris) uses gsat.nc.
    i = text.find("\nemulandice-glaciers:\n")
    if i >= 0:
        head, tail = text[:i], text[i:]
        tail = tail.replace('"fair-temperature/climate.nc"', '"fair-temperature/gsat.nc"', 1)
        text = head + tail
    with open(cfg.config_yaml, "w") as f:
        f.write(text)
    return feb(cfg, ["generate-apptainer", "--experiment-name", cfg.experiment], log) == 0


# =============================================================================
# Preflight, image pulls, gates, run
# =============================================================================

def preflight(cfg: Config, log) -> bool:
    ok = True
    if not shutil.which("apptainer"):
        log.error("apptainer not on PATH")
        ok = False
    if not os.path.isfile(cfg.script):
        log.error(f"missing {cfg.script} (run with --regenerate)")
        return False
    text = _read(cfg.script)
    m = re.search(r'^WORKSPACE="([^"]+)"', text, re.M)
    if m and os.path.realpath(m.group(1)) != os.path.realpath(cfg.workspace):
        log.error(f"{cfg.script} was generated for workspace {m.group(1)}, not {cfg.workspace}; regenerate here")
        ok = False
    for problem in check_total_items(text):
        (log.warning if cfg.allow_double_count or cfg.skip_run else log.error)(problem)
        ok = ok and (cfg.allow_double_count or cfg.skip_run)
    # Every directory the script bind-mounts must exist, or that service dies at container start. FEB names a module's data
    # directory after its image for some modules (emulandice, ipccar5) but `feb check-data` uses the module name.
    for src in sorted(set(re.findall(r'"--bind=([^:"]+):', text))):
        if not os.path.isdir(src):
            log.error(f"bind source {src} does not exist (the script mounts it; see fetch_catalog_data.sh for the links)")
            ok = False
    for sub in ("shared_input_data/FPRINT", "shared_input_data/location.lst"):
        if not os.path.exists(os.path.join(cfg.workspace, "data", sub)):
            log.error(f"missing input data/{sub}")
            ok = False
    log.info(f"preflight: {'OK' if ok else 'FAILED'}")
    return ok


def pull_images(cfg: Config, env: Dict[str, str], log) -> int:
    """Pull each distinct image once and copy it to the per-service names the script expects (the script pulls the
    same facts-total / emulandice / ESL image once per name, which costs minutes)."""
    os.makedirs(cfg.sif_dir, exist_ok=True)
    first: Dict[str, str] = {}
    pulled = 0
    for name, ref in parse_images(_read(cfg.script)):
        sif = os.path.join(cfg.sif_dir, f"{name}.sif")
        if os.path.isfile(sif):
            first.setdefault(ref, sif)
        elif ref in first:
            shutil.copyfile(first[ref], sif)
            log.info(f"copied {os.path.basename(first[ref])} -> {name}.sif")
        else:
            log.info(f"pulling {ref}")
            r = subprocess.run(["apptainer", "pull", "--disable-cache", sif, f"docker://{ref}"], env=env,
                               capture_output=True, text=True)
            if r.returncode != 0:
                log.error(f"pull of {ref} failed:\n{r.stderr[-800:]}")
                return -1
            first[ref] = sif
            pulled += 1
    return pulled


# Services whose container needs a writable working directory. The generated script starts every container with `--pwd /`
# (read-only); emulandice calls R, which writes Rplots.pdf into the working directory and stops with "cannot open file
# 'Rplots.pdf'". /tmp is a writable tmpfs under --containall.
CWD_RULES = {"emulandice": "/tmp"}

# Files bound over files inside a container image: image-name substring -> (path relative to the workspace, path in the container).
# emulandice-glaciers 0.2.0 reads the CSV that R wrote after about 1.7 hours of R; if that CSV is cut short (see BIG_TMP) it stops with `IndexError`
# on the last partial line (or, tolerated, would return NaN years) and the CSV is lost with the container's /tmp. The patched file copies the CSV to
# the output volume first, skips lines that are not data rows, and raises if any region, sample or year is missing (facts2/patches/container/,
# diff against emulandice_glaciers_project.orig.py).
# Several keys may match one image (a service gets the files of every matching key).
#
# "emulandice" (all three emulandice services): the R code runs 9 decade years, and for each year it looked up the temperature of every simulation row (about
# 4,800) with a dplyr filter and print() calls, 0.1 s a row, about 10 minutes a year, 80-90 minutes a run whatever the sample count. The patched main.R does the
# same lookup with one match(); outputs are bit-identical (checked for emulandice-gris, all 9 years, global and local) and a run takes minutes. r_helper.py
# loads the patched main.R into the installed package (diffs: facts2/patches/container/emulandice_main.orig.R, emulandice_r_helper.orig.py).
#
# "fair-temperature": the 2,000 FaIR runs were a serial Python loop (14.5 minutes). They are independent, so the patched file spreads them over worker
# processes (FAIR_NPROC, default all cores): 1.5 minutes on 12 cores, bit-identical outputs (checked: gsat, climate, oceantemp, ohc).
CONTAINER_PATCHES = {
    "fair-temperature": [("patches/container/fair_temperature_project.py",
                          "/opt/fair-temperature/src/fair_temperature/fair_temperature_project.py")],
    "emulandice": [("patches/container/emulandice_r_helper.py", "/opt/emulandice/src/emulandice/r_helper.py"),
                   ("patches/container/emulandice_main.R", "/opt/emulandice/modules/emulandice/shared/emulandice/R/main.R")],
    "emulandice-glaciers": [("patches/container/emulandice_glaciers_project.py",
                             "/opt/emulandice/src/emulandice/emulandice_glaciers_project.py")],
}

# Services that need a /tmp larger than the 16 MB tmpfs a --containall container gets (`sessiondir max size = 16` in apptainer.conf). emulandice keeps
# its working files in /tmp; with 2000 samples the glaciers run writes a CSV of more than 12 MB plus other files, the tmpfs fills up in the middle of
# the year 2080, R's writes fail silently and the run ends with a truncated CSV (root cause of the `IndexError` above). The shim binds a fresh directory
# under the run's build dir (RAM-backed /dev/shm by default) over /tmp for these services and removes it afterwards.
BIG_TMP = ("emulandice",)


def write_shim(run_dir: str, gates: Tuple[str, ...], resume: bool, log, claims_dir: Optional[str] = None,
               workspace: Optional[str] = None) -> str:
    """A PATH shim for `apptainer` so the generated script can stay unedited. For `apptainer run <flags> <image>.sif ...` it
      - holds back a service until a file exists            (gates: 'image-name-substring=/path')
      - replaces `--pwd /` by `--pwd /tmp` for CWD_RULES    (the emulandice R problem above)
      - binds a patched file into the image for CONTAINER_PATCHES (needs `workspace`; skipped if the file is missing)
      - with resume: skips a service whose declared output files (and inputs) all exist already (logged as [resume]); needed to continue a
        run that stopped part-way without redoing the 14-minute fair-temperature step. Opt-in, because it trusts files on disk.
      - with claims_dir: lets several instances of the script share the work. The first instance to reach a service claims it
        (mkdir <claims_dir>/<image name>); another instance skips it at once and moves on. facts-total and ESL services wait
        until their --item / --total-localsl-file inputs exist. The generated script runs its services one after the other,
        so a second instance on a 12-core node cuts the wall time of the R-based (single-threaded) modules.
    """
    real = shutil.which("apptainer")
    bindir = os.path.join(run_dir, "shim")
    os.makedirs(bindir)
    gate_cases = "".join(
        f'    *{name}*) until [ -e {shlex.quote(path)} ]; do echo "[gate] waiting for {path} ({name})" >&2; sleep 20; done ;;\n'
        for name, _, path in (g.partition("=") for g in gates))
    patch_cases = "".join(
        f'case "$sif" in\n    *{name}*) args=("run" {" ".join(binds)} "${{args[@]:1}}") ;;\nesac\n'
        for name, binds in ((name, [f'"--bind={os.path.join(workspace, host)}:{cont}:ro"' for host, cont in files
                                    if workspace and os.path.isfile(os.path.join(workspace, host))])
                            for name, files in CONTAINER_PATCHES.items())
        if binds)
    cwd_cases = "".join(f"    *{name}*) cwd={shlex.quote(cwd)} ;;\n" for name, cwd in CWD_RULES.items())
    tmp_cases = "".join(
        f'    *{name}*) want_tmp=1 ;;\n'
        for name in BIG_TMP)
    for g in gates:
        log.info(f"gate: service '{g.partition('=')[0]}' waits for {g.partition('=')[2]}")
    script = f"""#!/usr/bin/env bash
real={shlex.quote(real)}
[ "$1" = run ] || exec "$real" "$@"
args=("$@"); sif=""; declare -A bind
for a in "${{args[@]}}"; do
  case "$a" in
    *.sif) sif=$a ;;
    --bind=*) v=${{a#--bind=}}; bind[${{v#*:}}]=${{v%%:*}} ;;      # container path -> host path
  esac
done
case "$sif" in
{gate_cases}esac
cwd=""
case "$sif" in
{cwd_cases}esac
{patch_cases}want_tmp=""
case "$sif" in
{tmp_cases}esac
if [ -n "$cwd" ]; then
  for i in "${{!args[@]}}"; do
    if [ "${{args[$i]}}" = "--pwd" ] && [ "${{args[$((i+1))]}}" = "/" ]; then args[$((i+1))]=$cwd; fi
  done
fi
if [ {1 if resume else 0} = 1 ]; then
  n=0; missing=0
  for a in "${{args[@]}}"; do
    case "$a" in
      --*=/mnt/*)                      # any flag whose value is a mounted path (outputs, and the inputs they need)
        v=${{a#*=}}; mp=${{v%/*}}
        while [ -n "$mp" ] && [ -z "${{bind[$mp]:-}}" ]; do mp=${{mp%/*}}; done
        [ -z "$mp" ] && continue
        host=${{bind[$mp]}}${{v#$mp}}; n=$((n+1))
        if [ -d "$host" ]; then [ -n "$(ls -A "$host")" ] || missing=1; elif [ ! -s "$host" ]; then missing=1; fi ;;
    esac
  done
  if [ $n -gt 0 ] && [ $missing = 0 ]; then echo "[resume] skipping $(basename "$sif"): its $n declared paths already exist" >&2; exit 0; fi
fi
if [ -n {shlex.quote(claims_dir or "")} ]; then
  name=$(basename "$sif" .sif)
  if ! mkdir {shlex.quote(claims_dir or "x")}/"$name" 2>/dev/null; then
    echo "[claim] $name is being run by another instance; skipping" >&2; exit 0
  fi
  for a in "${{args[@]}}"; do
    case "$a" in
      --item=*|--total-localsl-file=*)
        v=${{a#*=}}; mp=${{v%/*}}
        while [ -n "$mp" ] && [ -z "${{bind[$mp]:-}}" ]; do mp=${{mp%/*}}; done
        host=${{bind[$mp]}}${{v#$mp}}
        until [ -s "$host" ]; do echo "[wait] $name waits for $host" >&2; sleep 15; done ;;
    esac
  done
fi
if [ -n "$want_tmp" ]; then                  # created only now, so a service skipped above leaves nothing behind
  bigtmp=$(mktemp -d {shlex.quote(run_dir)}/tmp.XXXXXX)
  "$real" run "--bind=$bigtmp:/tmp" "${{args[@]:1}}"; rc=$?
  [ -d "$bigtmp" ] && rm -rf -- "$bigtmp"
  exit $rc
fi
exec "$real" "${{args[@]}}"
"""
    shim = os.path.join(bindir, "apptainer")
    with open(shim, "w") as f:
        f.write(script)
    os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR)
    return bindir


def reserve_join_log(exp_dir: str) -> str:
    """Create and return the next free run.join[.N].log. O_EXCL: joins started within the same second must not pick the same name
    (two did, once, and wrote into one file, which also broke the per-service times read back from the logs)."""
    k = 1
    while True:
        path = os.path.join(exp_dir, "run.join.log" if k == 1 else f"run.join.{k}.log")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            k += 1


def run_script(cfg: Config, log) -> Dict:
    env, run_dir = build_env(cfg, log)
    log_path = os.path.join(cfg.exp_dir, "run.log")
    if cfg.join:                                        # one log per joining instance: run.join.log, run.join.2.log, ...
        log_path = reserve_join_log(cfg.exp_dir)
    if os.path.exists(log_path) and not cfg.join:                       # keep the log of an earlier (e.g. stopped) attempt
        os.replace(log_path, os.path.join(cfg.exp_dir, f"run.{int(os.path.getmtime(log_path))}.log"))
    claims = os.path.join(cfg.exp_dir, ".claims") if (cfg.share or cfg.join) else None
    if claims and not cfg.join:
        shutil.rmtree(claims, ignore_errors=True)
        os.makedirs(claims)
    env["PATH"] = write_shim(run_dir, cfg.gates, cfg.resume or cfg.join, log, claims, cfg.workspace) + os.pathsep + env["PATH"]
    t0 = time.time()
    pulled = 0 if cfg.join else pull_images(cfg, env, log)
    pull_s = time.time() - t0
    if pulled < 0:
        shutil.rmtree(run_dir, ignore_errors=True)
        return {"exit": 1, "wall_s": 0.0, "service_s": {}, "images_pulled": 0}
    timing = ["/usr/bin/time", "-v"] if os.path.exists("/usr/bin/time") else []
    cmd = timing + ["bash", cfg.script]
    log.info(f"running {shlex.join(cmd)} (log: {log_path})")
    start = time.time()
    with open(log_path, "w") as fh:
        rc = subprocess.run(cmd, cwd=cfg.workspace, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
    wall = time.time() - start
    text = _read(log_path)
    shutil.rmtree(run_dir, ignore_errors=True)
    svc: Dict[str, Dict] = {}
    for h, m, s, kind, name in re.findall(r"^\[(\d\d):(\d\d):(\d\d)\] (Running service|Completed): (\S+)", text, re.M):
        t = int(h) * 3600 + int(m) * 60 + int(s)
        svc.setdefault(name, {})["start" if kind.startswith("Running") else "end"] = t
    service_s = {n: (v["end"] - v["start"]) % 86400 for n, v in svc.items() if "start" in v and "end" in v}
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    res = {"exit": rc, "wall_s": round(wall, 1), "image_prep_s": round(pull_s, 1), "images_pulled_by_driver": pulled,
           "service_s": service_s, "max_rss_mb": round(int(rss.group(1)) / 1024, 1) if rss else None}
    log.info(f"run exit={rc} wall={wall:.0f}s (+{pull_s:.0f}s image prep)")
    if rc != 0:
        log.error("tail of run.log:\n" + "\n".join(l for l in text.splitlines() if "warn" not in l)[-1800:])
    return res


def collect_service_times(exp_dir: str) -> Dict:
    """Per-service start/end/seconds from every run*.log of the experiment (several instances may have shared the work).
    A service an instance skipped ([claim] / [resume]) is not counted there. facts-total and ESL services wait for their inputs
    inside the shim, so their seconds include that wait (marked)."""
    services: Dict[str, Dict] = {}
    logs = sorted(glob.glob(os.path.join(exp_dir, "run*.log")))
    for path in logs:
        text = _read(path)
        skipped = set(re.findall(r"^\[(?:claim|resume)\] (?:skipping )?(\S+?)(?:\.sif)?[: ]", text, re.M))
        stamps: Dict[str, Dict[str, int]] = {}
        for h, m, s, kind, name in re.findall(r"^\[(\d\d):(\d\d):(\d\d)\] (Running service|Completed): (\S+)", text, re.M):
            stamps.setdefault(name, {})["start" if kind.startswith("Running") else "end"] = int(h) * 3600 + int(m) * 60 + int(s)
        for name, v in stamps.items():
            if name in skipped or "start" not in v or "end" not in v:
                continue
            e = {"log": os.path.basename(path), "start_s": v["start"], "end_s": v["end"], "seconds": (v["end"] - v["start"]) % 86400}
            if name.startswith(("facts-total", "extremesealevel")):
                e["includes_wait_for_inputs"] = True
            if name not in services or e["end_s"] > services[name]["end_s"]:      # the latest completed run of a service is the one whose output stands
                services[name] = e
    fmt = lambda x: f"{x // 3600:02d}:{x % 3600 // 60:02d}:{x % 60:02d}"          # noqa: E731
    for e in services.values():
        e["start"], e["end"] = fmt(e["start_s"]), fmt(e["end_s"])
    return {"logs": [os.path.basename(p) for p in logs], "services": services}


# =============================================================================
# Output validation
# =============================================================================

def validate_outputs(cfg: Config, log) -> Dict:
    import numpy as np
    import xarray as xr

    script = _read(cfg.script)
    years = list(range(cfg.pyear_start, cfg.pyear_end + 1, cfg.pyear_step))
    report: Dict = {"files": {}}
    ok = True
    warnings: List[str] = []

    def fail(msg):
        nonlocal ok
        log.error(msg)
        ok = False

    def final_median(a):                 # a: (samples, years[, sites]); median over samples, then across sites
        return float(np.median(np.median(a[:, -1], axis=0)))

    def load(rel):
        """(samples, projection years, sites); some modules also write the base year as a first column, dropped here."""
        ds = xr.open_dataset(os.path.join(cfg.out_dir, rel))
        v = ds[SLR_VAR]
        a = v.transpose("samples", "years", ...).values.reshape(v.sizes["samples"], v.sizes["years"], -1)
        return a[:, np.isin(ds["years"].values, years), :]

    def file_years(rel):
        return [int(y) for y in xr.open_dataset(os.path.join(cfg.out_dir, rel))["years"].values if int(y) in years]

    for rel in expected_files(script):
        path = os.path.join(cfg.out_dir, rel)
        if not os.path.isfile(path):
            fail(f"MISSING {rel}")
            continue
        ds = xr.open_dataset(path)
        entry = {"dims": dict(ds.sizes)}
        fn = os.path.basename(rel)
        if fn == "climate.nc":
            report["files"][rel] = entry
            continue
        var = FAIR_VARIABLE.get(fn, SLR_VAR)
        if var not in ds:
            fail(f"{rel}: variable {var!r} missing (has {list(ds.data_vars)})")
            report["files"][rel] = entry
            continue
        v = ds[var]
        bad = int((~np.isfinite(v.values)).sum())
        entry.update(variable=var, units=v.attrs.get("units"), nonfinite=bad)
        if ds.sizes.get("samples") != cfg.nsamps or bad:
            fail(f"{rel}: samples={ds.sizes.get('samples')} (expected {cfg.nsamps}) nonfinite={bad}")
        if var == SLR_VAR:
            got = [int(y) for y in ds["years"].values]
            proj = [y for y in got if y != cfg.baseyear]
            if proj != years[:len(proj)] or not proj or got not in (proj, [cfg.baseyear] + proj):
                fail(f"{rel}: years={got}, expected {years} (or the start of it)")
            if len(proj) < len(years):                               # emulandice emulates 2020-2100 only
                entry["years_end"] = proj[-1]
                warnings.append(f"{rel} ends in {proj[-1]} (the grid goes to {years[-1]})")
            if got != proj:
                entry["extra_baseyear_column"] = True
            if v.attrs.get("units") != "mm":
                fail(f"{rel}: units={v.attrs.get('units')!r}, expected 'mm'")
            entry["p50_last"] = final_median(load(rel))
        report["files"][rel] = entry

    # Recompute each facts-total from the items the script gave it
    report["totals"] = {}
    for key, items in parse_totals(script).items():
        tot_rel = f"facts-total/{key.replace('-global', '_global').replace('-local', '_local')}_total.nc"
        if not os.path.isfile(os.path.join(cfg.out_dir, tot_rel)):
            continue                                                  # already reported as missing
        try:
            tot = load(tot_rel)
            parts = [(load(i), file_years(i)) for i in items]
            # facts-total subsets to the grid and adds, for every year, the items that HAVE that year (it only warns about the rest),
            # so a total that includes a module ending in 2100 silently lacks that module after 2100.
            s = np.zeros_like(tot)
            for a, ys in parts:
                s[:, [years.index(y) for y in ys], :] += a
            valid_through = min(ys[-1] for _, ys in parts)
        except Exception as e:                                        # shape mismatch, unreadable file
            fail(f"{tot_rel}: cannot recompute from its items ({e})")
            continue
        diff = float(np.abs(tot - s).max())
        report["totals"][key] = {"items": items, "max_abs_diff_vs_sum_of_items_mm": diff, "valid_through_year": valid_through,
                                 "p05_last": float(np.percentile(np.median(tot[:, -1:], axis=2)[:, 0], 5)),
                                 "p50_last": final_median(tot),
                                 "p95_last": float(np.percentile(np.median(tot[:, -1:], axis=2)[:, 0], 95)),
                                 "n_sites": int(tot.shape[2])}
        if diff > 0.01:
            fail(f"{tot_rel} != sum of its items (max diff {diff} mm)")
        if valid_through < years[-1]:
            short = sorted({i.split("/")[0] for i, (_, ys) in zip(items, parts) if ys[-1] < years[-1]})
            warnings.append(f"{tot_rel}: only valid through {valid_through}; {', '.join(short)} end{'s' if len(short) == 1 else ''} there, so "
                            f"{years[years.index(valid_through) + 1]}-{years[-1]} omit {'it' if len(short) == 1 else 'them'}")

    # Extreme sea level: one directory per workflow, one file per site and target year, all values finite
    report["extreme_sea_level"] = {}
    for wf in sorted({k.rsplit("-", 1)[0] for k in parse_totals(script)}):
        d = os.path.join(cfg.out_dir, f"extremesealevel-pointsoverthreshold-{wf}")
        files = sorted(f for f in os.listdir(d) if f.endswith("_extremesl.nc")) if os.path.isdir(d) else []
        if not files:
            fail(f"MISSING extreme sea level output for {wf} ({d})")
            continue
        bad = sum(int((~np.isfinite(xr.open_dataset(os.path.join(d, f))["allowance_quantiles"].values)).sum()) for f in files)
        report["extreme_sea_level"][wf] = {"files": files, "nonfinite_allowance": bad}
        if bad:
            fail(f"{wf}: extreme sea level allowance has {bad} non-finite values")

    # Which components does each aggregate contain? (decides what must not be summed together)
    report["aggregates"] = {}
    for mod, (agg_re, part_re) in OVERLAPS.items():
        d = os.path.join(cfg.out_dir, mod)
        if not os.path.isdir(d):
            continue
        files = [f for f in os.listdir(d) if f.endswith(".nc")]
        for scale in ("global", "local"):
            sc = [f for f in files if (scale == "global" and re.search(r"gslr|global", f)) or
                  (scale == "local" and re.search(r"lslr|local", f))]
            agg = [f for f in sc if re.match(agg_re, f)]
            parts = sorted(f for f in sc if re.match(part_re, f))
            if len(agg) != 1 or not parts:
                continue
            a = load(f"{mod}/{agg[0]}")
            combos = {}
            for k in range(1, len(parts) + 1):
                s = sum(load(f"{mod}/{f}") for f in parts[:k])
                combos["+".join(p[:-3] for p in parts[:k])] = float(np.abs(a - s).max())
            report["aggregates"][f"{mod}/{scale}"] = {"aggregate": agg[0], "max_abs_diff_aggregate_vs_cumulative_parts_mm": combos}
    for w in warnings:
        log.warning(w)
    report["warnings"] = warnings
    report["p50_last_definition"] = ("final-year median over samples; with several sites, the median across sites of those "
                                     "per-site medians (not a pooled median over all samples and sites)")
    report["ok"] = ok
    log.info(f"output validation: {'OK' if ok else 'FAILED'} ({len(report['files'])} files, {len(report['totals'])} totals)")
    return report


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Run the facts-experiment-catalog experiment coupling-585-260603 via FEB + Apptainer")
    d = Config()
    p.add_argument("--workspace", default=d.workspace)
    p.add_argument("--experiment", default=d.experiment)
    p.add_argument("--build-dir", default=d.build_dir)
    p.add_argument("--nsamps", type=int, default=d.nsamps)
    p.add_argument("--regenerate", action="store_true", help="run feb setup-experiment (catalog command) + generate-apptainer first")
    p.add_argument("--skip-run", action="store_true", help="only validate existing outputs")
    p.add_argument("--allow-double-count", action="store_true", help="run even if a facts-total job lists an aggregate with its parts")
    p.add_argument("--gate", action="append", default=[], metavar="SERVICE=FILE",
                   help="hold the service whose image name contains SERVICE until FILE exists (e.g. tlm-sterodynamics=<data>/cmip6/.complete)")
    p.add_argument("--resume", action="store_true",
                   help="skip services whose declared output files all exist (continue a run that stopped part-way)")
    p.add_argument("--share", action="store_true",
                   help="claim services so that a second instance (--join) can run the others at the same time")
    p.add_argument("--generate-only", action="store_true",
                   help="with --regenerate: create the experiment, run the preflight and the double-count check, run nothing")
    p.add_argument("--join", action="store_true",
                   help="run the script as a second instance next to a --share run (no preflight, no validation; implies --resume)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    cfg = Config(workspace=a.workspace, experiment=a.experiment, build_dir=a.build_dir, nsamps=a.nsamps, regenerate=a.regenerate,
                 skip_run=a.skip_run, allow_double_count=a.allow_double_count, gates=tuple(a.gate), resume=a.resume, share=a.share, join=a.join, generate_only=a.generate_only, verbose=a.verbose)
    log = setup_logging(cfg.verbose)
    t0 = time.time()
    summary: Dict = {}
    if cfg.join:
        return 0 if run_script(cfg, log)["exit"] == 0 else 1
    if cfg.regenerate and not regenerate(cfg, log):
        return 1
    if cfg.generate_only:
        return 0 if preflight(cfg, log) else 1
    if not cfg.skip_run:
        if not preflight(cfg, log):
            return 1
        summary["run"] = run_script(cfg, log)
        if summary["run"]["exit"] != 0:
            return 1
    out = os.path.join(cfg.exp_dir, "coupling_results.json")
    if cfg.skip_run and os.path.isfile(out):
        try:
            prev = json.loads(_read(out)).get("run")
            if prev:
                summary["run"] = prev
        except (OSError, ValueError):
            pass
    if cfg.skip_run:                                       # timings of runs made by earlier invocations (possibly several instances)
        summary["service_times_from_logs"] = collect_service_times(cfg.exp_dir)
    summary["outputs"] = validate_outputs(cfg, log)
    summary["total_s"] = round(time.time() - t0, 1)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"summary -> {out}")
    return 0 if summary["outputs"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
