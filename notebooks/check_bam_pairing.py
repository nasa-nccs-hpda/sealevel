#!/usr/bin/env python
"""
check_bam_pairing.py - how strongly does climate member j drive BAM output sample j?

bamber19-icesheets (temperature-driven mode) uses climate member j only to pick the probability that output sample j
is drawn from Bamber's HIGH rather than LOW scenario pool (pickScenario in the container's
bamber19_icesheets_project.py); the ice-sheet realisation within the pool is an independent random draw. This script
verifies that on an existing experiment:

  1. replicates pickScenario from climate.nc (iSAT over 2000-2099 -> P(high), selector = rng.random(), same seed);
  2. re-runs the BAM container twice with the same seed: a control (original climate.nc) and a copy whose climate members
     are shuffled;
  3. checks that (a) the control reproduces the experiment's outputs, (b) exactly the samples predicted in step 1 change
     and all others are bit-identical, and reports (c) the per-sample rank correlation between warming and output
     against a shuffled-pairing null.

Exit code 0 only if (a) and (b) hold. Needs apptainer, the experiment's outputs and its SIF. Run in an environment
isolated from the system conda (its h5py/numpy clash with uv's):

  cd facts2 && env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 \
      --with h5py --with xarray --with netcdf4 --with 'numpy<2' python ../notebooks/check_bam_pairing.py

Only global outputs are written by the re-runs (about 10 s each).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import h5py
import numpy as np
import xarray as xr

COMPONENTS = ("AIS", "EAIS", "WAIS", "GIS")
IMAX_LOW, IMAX_HIGH = 142.5, 242.5          # Bamber 2019 low / high scenario, integrated SAT 2000-2099 (degC*yr)


def p_high(sat, years, ref=(1850, 1900), window=(2000, 2100)):
    """Replicates GetSATData + pickScenario weights: sat is (years, members). Returns (iSAT, P(high)) per member."""
    idx = lambda y: int(np.flatnonzero(years == y)[0])
    sat_ave = sat[idx(ref[0]):idx(ref[1]), :].mean(axis=0)
    t = np.arange(1900, 2301)
    anomaly = sat[idx(1900):idx(2300) + 1, :] - sat_ave
    isat = anomaly[(t >= window[0]) & (t < window[1])].sum(axis=0)
    return isat, np.clip((isat - IMAX_LOW) / (IMAX_HIGH - IMAX_LOW), 0, 1)


def rank_corr(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def run_bam(ws, sif, out_dir, tmp, a):
    """Run the BAM container as the generated experiment script does, writing only the global outputs."""
    env = dict(os.environ, APPTAINER_TMPDIR=tmp, APPTAINER_CACHEDIR=os.path.join(tmp, "cache"))
    os.makedirs(env["APPTAINER_CACHEDIR"], exist_ok=True)
    outs = [f"--output-{c}-gslr-file=/mnt/out/bamber19-icesheets/{c}-gslr.nc" for c in COMPONENTS]
    cmd = ["apptainer", "run", "--no-home", "--containall", "--pwd", "/",
           f"--bind={ws}/data/module_specific_input_data/bamber19-icesheets:/mnt/module_specific_in",
           f"--bind={ws}/data/shared_input_data:/mnt/shared_in", f"--bind={out_dir}:/mnt/out", sif,
           "--pipeline-id=bam001", f"--nsamps={a.nsamps}", f"--scenario={a.scenario}", f"--pyear-start={a.pyear_start}",
           f"--pyear-end={a.pyear_end}", f"--pyear-step={a.pyear_step}", f"--baseyear={a.baseyear}",
           f"--location-file=/mnt/shared_in/{a.location_file}", "--fingerprint-dir=/mnt/shared_in/FPRINT",
           "--replace=1", "--chunksize=50", f"--rngseed={a.rngseed}",
           "--climate-data-file=/mnt/out/fair-temperature/climate.nc",
           "--slr-proj-mat-file=/mnt/module_specific_in/SLRProjections190726core_SEJ_full.mat"] + outs
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"BAM container failed ({r.returncode}):\n{r.stderr[-1500:]}")


def read_gslr(base):
    d = {c: xr.open_dataset(os.path.join(base, f"{c}-gslr.nc")) for c in COMPONENTS}
    years = d["GIS"]["years"].values
    return years, {c: d[c]["sea_level_change"].values.squeeze() for c in COMPONENTS}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workspace", default=os.path.join(here, "..", "facts2"))
    p.add_argument("--experiment", default="apptainer_experiments/bam_ssp585_fixed")
    p.add_argument("--sif", help="default: <workspace>/apptainer_experiments/sif/bamber19-icesheets-0.2.0.sif")
    p.add_argument("--build-dir", default="/dev/shm", help="exec-capable dir for temporary files (default /dev/shm)")
    p.add_argument("--scenario", default="ssp585")
    p.add_argument("--nsamps", type=int, default=500)
    p.add_argument("--pyear-start", type=int, default=2020)
    p.add_argument("--pyear-end", type=int, default=2150)
    p.add_argument("--pyear-step", type=int, default=10)
    p.add_argument("--baseyear", type=int, default=2005)
    p.add_argument("--rngseed", type=int, default=1423, help="BAM seed used by the experiment")
    p.add_argument("--location-file", default="location.lst")
    p.add_argument("--shuffle-seed", type=int, default=0)
    a = p.parse_args()

    ws = os.path.realpath(a.workspace)
    exp = os.path.join(ws, a.experiment, "output-apptainer")
    sif = a.sif or os.path.join(ws, "apptainer_experiments/sif/bamber19-icesheets-0.2.0.sif")
    clim = os.path.join(exp, "fair-temperature/climate.nc")
    for path in (clim, sif, os.path.join(exp, "bamber19-icesheets/GIS-gslr.nc")):
        if not os.path.exists(path):
            sys.exit(f"missing {path}")

    # 1. replicate the module's high/low selection
    with h5py.File(clim, "r") as f:
        g = f[a.scenario]
        sat, years_c = g["surface_temperature"][()], g["years"][()]
    isat, w = p_high(sat, years_c)
    n = w.size
    sel = np.random.default_rng(a.rngseed).random(n)
    use_high = sel < w
    print(f"experiment: {a.experiment}   members: {n}   seed: {a.rngseed}")
    print(f"integrated SAT 2000-2099 (degC*yr): min {isat.min():.0f}, median {np.median(isat):.0f}, max {isat.max():.0f} "
          f"(low {IMAX_LOW}, high {IMAX_HIGH})")
    print(f"P(high): members at 1.0: {(w >= 1).sum()}/{n}; mean {w.mean():.3f}; realised high-pool share {use_high.mean():.3f}")

    # 2. control + shuffled-members re-runs
    tmp = tempfile.mkdtemp(prefix="bam_pairing_", dir=a.build_dir)       # the only thing deleted afterwards
    try:
        perm = np.random.default_rng(a.shuffle_seed).permutation(n)
        outs = {}
        for name in ("ctl", "perm"):
            d = os.path.join(tmp, name)
            os.makedirs(os.path.join(d, "fair-temperature"))
            os.makedirs(os.path.join(d, "bamber19-icesheets"))
            shutil.copy(clim, os.path.join(d, "fair-temperature/climate.nc"))
            if name == "perm":
                with h5py.File(os.path.join(d, "fair-temperature/climate.nc"), "r+") as f:
                    ds = f[a.scenario]["surface_temperature"]
                    ds[...] = ds[()][:, perm]
            run_bam(ws, sif, d, tmp, a)
            outs[name] = read_gslr(os.path.join(d, "bamber19-icesheets"))[1]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    years, orig = read_gslr(os.path.join(exp, "bamber19-icesheets"))
    ctl, prm = outs["ctl"], outs["perm"]

    # 3. checks
    diff_ctl = max(float(np.abs(ctl[c] - orig[c]).max()) for c in COMPONENTS)
    pred_changed = use_high != (sel < w[perm])
    changed = np.array([any(not np.array_equal(prm[c][j], ctl[c][j]) for c in COMPONENTS) for j in range(n)])
    same_ok = all(np.array_equal(prm[c][~pred_changed], ctl[c][~pred_changed]) for c in COMPONENTS)
    ok_a, ok_b = diff_ctl == 0.0, bool(np.array_equal(changed, pred_changed)) and same_ok
    print(f"\n(a) control re-run vs the experiment's outputs: max abs diff {diff_ctl:.3g} mm -> {'PASS' if ok_a else 'FAIL'}")
    print(f"(b) shuffling the climate members: predicted {pred_changed.sum()} of {n} samples change, actually {changed.sum()}; "
          f"prediction exact and the rest bit-identical -> {'PASS' if ok_b else 'FAIL'}")

    print("(c) per-sample link between warming and output (Spearman; null = shuffled pairing, 300 draws):")
    for yr in (2100, 2150):
        if yr not in years:
            continue
        i = int(np.flatnonzero(years == yr)[0])
        for c in ("GIS", "AIS"):
            rho = rank_corr(isat, orig[c][:, i])
            null = [rank_corr(np.random.default_rng(k).permutation(isat), orig[c][:, i]) for k in range(300)]
            print(f"    {c} {yr}: rho = {rho:+.3f}   null {np.mean(null):+.3f} +/- {np.std(null):.3f}")
    last = len(years) - 1
    print(f"    {years[last]} GIS median: high-pool samples {np.median(orig['GIS'][use_high, last]):.0f} mm (n={use_high.sum()}) "
          f"vs low-pool {np.median(orig['GIS'][~use_high, last]):.0f} mm (n={(~use_high).sum()}); "
          f"shuffled climate: {np.median(ctl['GIS'][:, last]):.0f} -> {np.median(prm['GIS'][:, last]):.0f} mm")
    return 0 if (ok_a and ok_b) else 1


if __name__ == "__main__":
    sys.exit(main())
