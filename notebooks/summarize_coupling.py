#!/usr/bin/env python
"""
summarize_coupling.py - figures and headline numbers for the catalog experiment coupling-585-260603

Reads <experiment>/output-apptainer/facts-total/<wf>_{global,local}_total.nc (one pair per workflow), the module outputs the script fed
into each total and the extreme-sea-level files, and writes
  <fig-dir>/coupling_585_totals.png      global total over time per workflow, and the 2100 spread (global mean, one site)
  <fig-dir>/coupling_585_components.png  what each workflow's 2100 global total is made of (median of each component)
  <experiment>/coupling_summary.json     the numbers behind both figures
  <experiment>/coupling_tables.md        the same as markdown tables (pasted into facts2/SUMMARY_coupling_585.md)

Years: the emulandice modules only emulate 2020-2100, and facts-total adds, for each year, the items that have it, so a workflow that includes
an emulandice module is valid through 2100 only (later years silently omit that module). 2100 is therefore the common comparison year and
2150 is reported only for the workflows that are complete there.

  cd facts2 && env -u PYTHONPATH PYTHONNOUSERSITE=1 uv run --isolated --python 3.12 --with xarray --with netcdf4 \
      --with 'numpy<2' --with matplotlib python ../notebooks/summarize_coupling.py
"""

import argparse
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import xarray as xr               # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_coupling import parse_totals  # noqa: E402

# Reference categorical palette, slots 1-6 in fixed order (never cycled) + neutral inks, light surface
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e4e3df"
WORKFLOWS = ["wf1e", "wf2f", "wf2e", "wf3f", "wf3e", "wf4"]
WF_COLOR = dict(zip(WORKFLOWS, SLOT))
PARTS = ["Antarctica", "Greenland", "Glaciers", "Ocean (sterodynamics)", "Land water", "Vertical land motion"]
PART_COLOR = dict(zip(PARTS, SLOT))
PCT = [5, 17, 50, 83, 95]
YA, YB = 2100, 2150                      # common comparison year; final year of the grid

# Outputs the UNPATCHED registry (a085795) would also pass to facts-total although their aggregate already contains them
# (see facts2/patches/ and HANDOFF.md). Used only to show what the generated totals would have been.
UNPATCHED_EXTRA = {
    "bamber19-icesheets": {"global": ["EAIS-gslr.nc", "WAIS-gslr.nc"], "local": ["EAIS-lslr.nc", "WAIS-lslr.nc"]},
    "deconto21-ais": {"global": ["eais-gslr.nc", "wais-gslr.nc"], "local": ["eais-lslr.nc", "wais-lslr.nc"]},
    "larmip-ais": {"global": ["eais_global_output.nc", "wais_global_output.nc", "pen_global_output.nc", "smb_global_output.nc"],
                   "local": ["eais_local_output.nc", "wais_local_output.nc"]},
}

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 160, "font.size": 10.5, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "legend.frameon": False,
})


def part_of(item: str) -> str:
    """Component class of one facts-total input file ('module/file.nc')."""
    mod, _, fn = item.partition("/")
    if mod in ("larmip-ais", "deconto21-ais", "emulandice-ais"):
        return "Antarctica"
    if mod == "bamber19-icesheets":
        return "Antarctica" if fn.startswith("AIS") else "Greenland"
    if mod in ("fittedismip-gris", "emulandice-gris"):
        return "Greenland"
    if mod in ("ipccar5-glaciers", "emulandice-glaciers"):
        return "Glaciers"
    if mod == "tlm-sterodynamics":
        return "Ocean (sterodynamics)"
    if mod == "ssp-landwaterstorage":
        return "Land water"
    if mod == "kopp14-verticallandmotion":
        return "Vertical land motion"
    raise ValueError(f"no component class for {item}")


def load(out, rel, site):
    """(years, samples x years array) of one projection file; for local files column `site`. Years before 2020 (base year) dropped."""
    ds = xr.open_dataset(os.path.join(out, rel))
    a = ds["sea_level_change"].transpose("samples", "years", ...).values
    a = a.reshape(a.shape[0], a.shape[1], -1)[:, :, site]
    y = ds["years"].values
    keep = y >= 2020
    return y[keep], a[:, keep]


def at(years, a, yr):
    return a[:, int(np.flatnonzero(years == yr)[0])]


def pct(x):
    p = np.percentile(x, PCT)
    return {"p05": float(p[0]), "p17": float(p[1]), "p50": float(p[2]), "p83": float(p[3]), "p95": float(p[4])}


def run_facts(exp):
    """Wall-clock span and per-service minutes of the run, from coupling_results.json (written by run_coupling.py --skip-run)."""
    try:
        r = json.load(open(os.path.join(exp, "coupling_results.json")))["service_times_from_logs"]["services"]
    except (OSError, KeyError, ValueError):
        return None
    ok = {k: v for k, v in r.items() if not v.get("includes_wait_for_inputs")}
    return {"first_start": min(v["start"] for v in r.values()), "last_end": max(v["end"] for v in r.values()),
            "minutes": {k.rsplit("-", 1)[0]: round(v["seconds"] / 60, 1) for k, v in sorted(ok.items(), key=lambda kv: -kv[1]["seconds"])}}


def label(item):
    """Short name of a module output for prose: 'bamber19 GIS', 'larmip-ais', ..."""
    mod, _, fn = item.partition("/")
    return f"bamber19 {fn.split('-')[0]}" if mod == "bamber19-icesheets" else mod


def write_summary_md(path, exp, res, done, totals_table, comp, comp_site, esl, link, valid, gsat):
    import datetime
    ya, yb = str(YA), str(YB)
    w = res["workflows"]
    site = {wf: w[wf]["local"][ya]["p50"] for wf in done}
    hi, lo = max(site, key=site.get), min(site, key=site.get)
    wide = max(done, key=lambda wf: w[wf]["local"][ya]["p95"] - w[wf]["local"][ya]["p05"])
    full = [wf for wf in done if yb in w[wf]["global"]]
    short_wf = [wf for wf in done if yb not in w[wf]["global"]]
    pending = res["missing_workflows"]
    rf = run_facts(exp)
    gen = [wf for wf in full if "as_generated_p50" in w[wf]["global"][yb]]
    pct_gen = ", ".join(f"{wf} +{100 * (w[wf]['global'][yb]['as_generated_p50'] / w[wf]['global'][yb]['p50'] - 1):.0f}%" for wf in gen)
    pct_gen_a = ", ".join(f"{wf} +{100 * (w[wf]['global'][ya]['as_generated_p50'] / w[wf]['global'][ya]['p50'] - 1):.0f}%"
                          for wf in done if "as_generated_p50" in w[wf]["global"][ya])
    g_a = gsat[ya]
    sdm = res["site_minus_global_2100"]
    sd_txt = "; ".join(f"{k.lower() if k != 'Vertical land motion' else 'vertical land motion'} {lo_:+.0f}" + (f" to {hi_:+.0f}" if abs(hi_ - lo_) >= 1 else "")
                       for k, (lo_, hi_) in sdm.items() if max(abs(lo_), abs(hi_)) >= 1)
    md = f"""# Sea-level projections under SSP5-8.5, FACTS2 catalog experiment `coupling-585-260603`: one-page summary

Generated by `notebooks/summarize_coupling.py` on {datetime.date.today()} from `facts2/apptainer_experiments/coupling-585-260603/`; figures `figures/coupling_585_totals.png` and
`figures/coupling_585_components.png`; every number below is in `coupling_summary.json` / `coupling_tables.md` next to the experiment. Instructions followed: the
facts-experiment-catalog entry https://github.com/fact-sealevel/facts-experiment-catalog/tree/main/coupling-585-260603 (deviations: see the end).

## What this is
The catalog's experiment, run with FEB and Apptainer: fair-temperature, then 11 sea-level modules (fittedismip-gris, deconto21-ais, bamber19-icesheets, emulandice-ais/-gris/-glaciers,
larmip-ais, ipccar5-glaciers, tlm-sterodynamics, kopp14-verticallandmotion, ssp-landwaterstorage), combined by facts-total in the catalog's six workflows, plus the extreme-sea-level
module. ssp585, 2020-2150 step 10, base year 2005, **{res['nsamps']} samples**, one site (New York, 40.70 N, -74.01 E). Each workflow is one choice of ice-sheet and glacier models on top of the same
ocean (TLM), land-water and vertical-land-motion modules, so the spread between workflows is structural uncertainty. Global mean warming from the same run: {g_a['p50']:.1f} degC in {ya}
(5-95%: {g_a['p05']:.1f}-{g_a['p95']:.1f}).

## Result in {ya}, the year all workflows share (mm since 2005; global mean and the New York site)
{totals_table(YA)}

New York is above the global mean. Site minus global median in {ya}, by component (range over the workflows, mm): {sd_txt}. New York medians range from {site[lo]:.0f} mm ({lo}) to
{site[hi]:.0f} mm ({hi}); the widest 5-95% range is {wide}'s ({w[wide]['local'][ya]['p05']:.0f}-{w[wide]['local'][ya]['p95']:.0f} mm).{(' Not yet available: ' + ', '.join(pending) + '.') if pending else ''}

## Result in {yb}, for the workflows that are complete there ({', '.join(full)})
{totals_table(YB)}

## What the totals are made of ({ya}, median of each component in mm)
Global mean:

{chr(10).join(comp)}

New York (local; ocean includes the local dynamic sea level, and vertical land motion appears):

{chr(10).join(comp_site)}

The medians of the parts do not add exactly to the median of the total (skewed distributions). Greenland and Antarctica come from different modules in different workflows; glaciers are ipccar5 or
emulandice; ocean (TLM), land water and vertical land motion are the same in every workflow.

## Extreme sea level, New York, 2100
{chr(10).join(esl)}

`allowance` is the module's height allowance at an allowance frequency of 0.01 per year (a file attribute) and the amplification factor is the module's factor by which the frequency of extreme
levels increases; both are quantiles over the {res['nsamps']} samples, one file per workflow, target year 2100, for site id 12 of `location.lst`. I did not review the module's method.

## What to know before using these numbers
1. **Two registry fixes were needed (local patches, `facts2/patches/`).** facts-total adds every output a module lists, and `bamber19-icesheets`, `deconto21-ais` and `larmip-ais` list an aggregate (AIS) together
   with the parts it already contains, so Antarctica is counted twice. The totals above use AIS only. The unpatched registry would have given global medians higher by {pct_gen_a} in {ya} and {pct_gen} in {yb}
   (last column of the tables). The BAM part is issue #144 / PR #20, the other two modules issue #145 / PR #21 (all open).
2. **emulandice stops at 2100.** The three emulandice modules emulate 2020-2100 only; facts-total then silently adds only the items that have a year, so {('the totals of ' + ', '.join(short_wf) + ' are valid through 2100 only (later years omit the emulandice modules and drop)') if short_wf else 'no workflow is affected here'}. That is why {ya} is the comparison year and {yb} is shown for {', '.join(full)} only.
3. **Samples are not paired trajectories.** facts-total adds sample j of every module. How closely sample j follows climate member j differs a lot (rank correlation with the sample's {ya} warming, null 0 +/- {res['climate_link_null_sd']:.3f}):
   {', '.join(f"{label(k)} {v:+.2f}" for k, v in sorted(res['climate_link'].items(), key=lambda kv: -kv[1]))}.
   Read spreads, medians and totals as ensemble statistics, not as temperature-to-sea-level paths.
4. One site only; local = global-scale contribution x a site factor, plus vertical land motion; no regional ocean dynamics beyond what TLM provides at global scale.
5. Not compared with published projections (e.g. AR6) or with the legacy FACTS run; this checks that the pipeline ran correctly (every output validated, every total equals the sum of its listed items to 0.001 mm), not that the science is right.

## Run facts
{('Started ' + rf['first_start'] + ', last service ended ' + rf['last_end'] + ' (clock times of the day of the run; several instances of the generated script shared the work; the first attempt stopped at emulandice (R could not write `Rplots.pdf`), two more failed at once (a mount directory that did not exist, a wrong input file), and emulandice-glaciers had to be run three times at full length, the first two lost to the 16 MB `/tmp` of the container; see the findings report). Minutes per module service: ' + ', '.join(f'{k} {v}' for k, v in list(rf['minutes'].items())[:12]) + '.') if rf else 'Timing: run `run_coupling.py --skip-run` to collect it from the logs.'}
Reproduce: `notebooks/README.md`, section "FACTS2 catalog experiment" (about 33 GB of data, 9 GB of images, two registry patches, one container patch). The driver's tests pass (`notebooks/tests/test_run_coupling.py`).

## Differences from the catalog
`ipccar5-icesheets` is in the catalog's command but not its config and no workflow uses it (left out); the config pins older images than the current registry (current ones ran); the catalog command passes no pipeline id, data paths or
workflows (`abcd`, this workspace's data and the catalog's six workflows were used); FEB's extra `all-modules` workflow was removed. Details and every FEB/registry/container problem met: `facts2/REPORT_catalog_run_findings.md`.
"""
    with open(path, "w") as f:
        f.write(md)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workspace", default=os.path.join(here, "..", "facts2"))
    ap.add_argument("--experiment", default="apptainer_experiments/coupling-585-260603")
    ap.add_argument("--fig-dir", default=None, help="default: <workspace>/figures")
    ap.add_argument("--site", type=int, default=0, help="column of the local files to show (default 0; location.lst has one site)")
    ap.add_argument("--summary-md", default=None, help="write the one-page summary here (default: <workspace>/SUMMARY_coupling_585.md)")
    a = ap.parse_args()
    ws = os.path.realpath(a.workspace)
    exp = os.path.join(ws, a.experiment)
    out = os.path.join(exp, "output-apptainer")
    figs = a.fig_dir or os.path.join(ws, "figures")
    os.makedirs(figs, exist_ok=True)
    items = parse_totals(open(os.path.join(exp, "experiment-apptainer.sh")).read())

    res = {"site_column": a.site, "common_year": YA, "final_year": YB, "workflows": {}, "missing_workflows": []}
    series, done = {}, []
    for wf in WORKFLOWS:
        if not all(os.path.isfile(os.path.join(out, f"facts-total/{wf}_{s}_total.nc")) for s in ("global", "local")):
            res["missing_workflows"].append(wf)
            continue
        done.append(wf)
        all_items = items[f"{wf}-global"] + items[f"{wf}-local"]
        valid = min(int(xr.open_dataset(os.path.join(out, i))["years"].values.max()) for i in all_items)
        entry = {"valid_through": valid, "modules": sorted({i.split("/")[0] for i in all_items})}
        for scale in ("global", "local"):
            site = a.site if scale == "local" else 0
            years, tot = load(out, f"facts-total/{wf}_{scale}_total.nc", site)
            series[(wf, scale)] = (years[years <= valid], np.percentile(tot[:, years <= valid], PCT, axis=0))
            entry[scale] = {}
            for yr in (YA, YB):
                if yr > valid:
                    continue
                e = pct(at(years, tot, yr))
                extra = [f"{m}/{f}" for m in sorted({i.split("/")[0] for i in items[f"{wf}-{scale}"]})
                         for f in UNPATCHED_EXTRA.get(m, {}).get(scale, [])]
                if extra:                                           # what the unpatched registry would have summed
                    gen = at(years, tot, yr) + sum(at(*load(out, x, site), yr) for x in extra)
                    e["as_generated_p50"] = float(np.median(gen))
                entry[scale][str(yr)] = e
        comp = {}
        for yr in (YA, YB):
            if yr > valid:
                continue
            c = {}
            for it in items[f"{wf}-global"]:
                y, v = load(out, it, 0)
                c[part_of(it)] = c.get(part_of(it), 0.0) + float(np.median(at(y, v, yr)))
            comp[str(yr)] = c
        entry["global_component_medians"] = comp
        lcomp = {}
        for yr in (YA, YB):
            if yr > valid:
                continue
            c = {}
            for it in items[f"{wf}-local"]:
                y, v = load(out, it, a.site)
                c[part_of(it)] = c.get(part_of(it), 0.0) + float(np.median(at(y, v, yr)))
            lcomp[str(yr)] = c
        entry["site_component_medians"] = lcomp
        esl = sorted(glob.glob(os.path.join(out, f"extremesealevel-pointsoverthreshold-{wf}", "*_extremesl.nc")))
        if esl:                                                    # extreme sea level module: one file per site and target year
            e = xr.open_dataset(esl[0])
            q = e["quantiles"].values

            def qat(var, qq):
                return float(e[var].values[int(np.argmin(np.abs(q - qq)))])
            entry["extreme_sea_level"] = {
                "file": os.path.basename(esl[0]), "year": int(e["year"].values[0]), "mhhw_m": float(e["mhhw"].values[0]),
                "allowance_m": {k: qat("allowance_quantiles", v) for k, v in (("p05", .05), ("p50", .5), ("p95", .95))},
                "amplification_factor": {k: qat("amplification_factors_quantiles", v) for k, v in (("p05", .05), ("p50", .5), ("p95", .95))}}
        res["workflows"][wf] = entry
    if not done:
        sys.exit("no workflow has both facts-total files yet")
    nsamp = xr.open_dataset(os.path.join(out, "fair-temperature/gsat.nc")).sizes["samples"]
    res["nsamps"] = int(nsamp)

    # How closely does each module's sample j follow climate member j? Rank correlation between the member's 2100 warming and the
    # module's 2100 global contribution over the samples. facts-total adds sample j of every module, so this shows how "paired" the sum is.
    gs = xr.open_dataset(os.path.join(out, "fair-temperature/gsat.nc"))
    temp = gs["surface_temperature"].transpose("samples", "years", ...).values.reshape(gs.sizes["samples"], gs.sizes["years"], -1)[:, :, 0]
    gyears = list(gs["years"].values)
    t2100 = temp[:, gyears.index(YA)]
    rank = lambda v: np.argsort(np.argsort(v))     # noqa: E731  (ties are negligible for continuous model output)
    res["climate_link"] = {}
    for it in sorted({i for wf in done for i in items[f"{wf}-global"]}):
        y, v = load(out, it, 0)
        res["climate_link"][it] = float(np.corrcoef(rank(t2100), rank(at(y, v, YA)))[0, 1])
    res["climate_link_null_sd"] = float(1 / np.sqrt(len(t2100) - 1))
    res["gsat_c"] = {str(yr): pct(temp[:, gyears.index(yr)]) for yr in (2050, YA, YB)}

    # ---- Figure 1: totals over time (to each workflow's last valid year) and the 2100 spread
    fig = plt.figure(figsize=(12.5, 4.6))
    gs_ = fig.add_gridspec(1, 3, width_ratios=[1.5, 1, 1], wspace=0.32)
    ax = fig.add_subplot(gs_[0])
    for wf in done:
        x, p = series[(wf, "global")]
        ax.fill_between(x, p[0], p[4], color=WF_COLOR[wf], alpha=0.07, lw=0)
        ax.plot(x, p[2], color=WF_COLOR[wf], lw=2.0, label=wf + ("" if res["workflows"][wf]["valid_through"] >= YB else " (to 2100)"))
    ax.axvline(YA, color=MUTED, lw=0.8, ls=":")
    ax.set_title("Global mean total, median and 5-95%")
    ax.set_ylabel("sea-level change since 2005 (mm)")
    ax.legend(title="workflow", ncol=2, loc="upper left")
    for k, scale, title in ((1, "global", f"{YA}, global mean"), (2, "local", f"{YA}, one site")):
        a2 = fig.add_subplot(gs_[k])
        for i, wf in enumerate(done):
            e = res["workflows"][wf][scale][str(YA)]
            y = len(done) - 1 - i
            a2.plot([e["p05"], e["p95"]], [y, y], color=WF_COLOR[wf], lw=2.0, solid_capstyle="round")
            a2.plot([e["p17"], e["p83"]], [y, y], color=WF_COLOR[wf], lw=6.0, solid_capstyle="butt")
            a2.plot(e["p50"], y, "o", ms=8, mfc="white", mec=WF_COLOR[wf], mew=2.0, zorder=3)
            a2.text(e["p50"], y + 0.3, f"{e['p50']:.0f}", fontsize=9, color=INK2, ha="center")
        a2.set_yticks(range(len(done)))
        a2.set_yticklabels(done[::-1])
        a2.set_title(title)
        a2.set_xlabel("mm")
        a2.set_ylim(-0.6, len(done) - 0.3)
        a2.grid(axis="y", visible=False)
    fig.text(0.5, -0.04, f"right panels: dot = median, thick bar = 17-83%, thin line = 5-95% over the {nsamp} samples. "
             "Workflows with an emulandice module are valid only through 2100.", ha="center", color=INK2)
    fig.savefig(os.path.join(figs, "coupling_585_totals.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # ---- Figure 2: components of each workflow's 2100 global total
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    for i, wf in enumerate(done):
        y = len(done) - 1 - i
        left = 0.0
        for part in PARTS:
            v = res["workflows"][wf]["global_component_medians"][str(YA)].get(part)
            if v is None:
                continue
            ax.barh(y, v, left=left, height=0.62, color=PART_COLOR[part], edgecolor="white", linewidth=2)
            left += max(v, 0)
        ax.plot(res["workflows"][wf]["global"][str(YA)]["p50"], y, "|", color=INK, ms=22, mew=2.0, zorder=4)
    ax.set_yticks(range(len(done)))
    ax.set_yticklabels(done[::-1])
    ax.set_xlabel(f"{YA} global mean (mm): median of each component; black tick = median of the total")
    ax.set_title("What each workflow's total is made of")
    ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=PART_COLOR[p]) for p in PARTS[:5]]
    ax.legend(handles, PARTS[:5], ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    fig.savefig(os.path.join(figs, "coupling_585_components.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)

    with open(os.path.join(exp, "coupling_summary.json"), "w") as f:
        json.dump(res, f, indent=2)

    # ---- Markdown tables (numbers are copied from the JSON, not retyped)
    short = lambda m: m.replace("-landwaterstorage", "-lws").replace("-verticallandmotion", "-vlm")   # noqa: E731

    def totals_table(yr):
        rows = ["| workflow | modules | global 5% | global median | global 95% | site 5% | site median | site 95% | unpatched registry: global / site median |",
                "|---|---|---|---|---|---|---|---|---|"]
        for wf in done:
            w = res["workflows"][wf]
            if str(yr) not in w["global"]:
                continue
            g, l = w["global"][str(yr)], w["local"][str(yr)]
            gen = (f"{g['as_generated_p50']:.0f} / {l['as_generated_p50']:.0f} (+{100 * (g['as_generated_p50'] / g['p50'] - 1):.0f}% / "
                   f"+{100 * (l['as_generated_p50'] / l['p50'] - 1):.0f}%)") if "as_generated_p50" in g else "same (no overlap)"
            rows.append(f"| {wf} | {', '.join(short(m) for m in w['modules'])} | {g['p05']:.0f} | **{g['p50']:.0f}** | {g['p95']:.0f} | "
                        f"{l['p05']:.0f} | **{l['p50']:.0f}** | {l['p95']:.0f} | {gen} |")
        return "\n".join(rows)

    comp = ["| workflow | " + " | ".join(PARTS[:5]) + " | sum of medians | median of total |", "|---|" + "---|" * 7]
    for wf in done:
        c = res["workflows"][wf]["global_component_medians"][str(YA)]
        comp.append(f"| {wf} | " + " | ".join(f"{c.get(k, 0):.0f}" for k in PARTS[:5]) + f" | {sum(c.values()):.0f} | "
                    f"{res['workflows'][wf]['global'][str(YA)]['p50']:.0f} |")
    comp_site = ["| workflow | " + " | ".join(PARTS) + " | sum of medians | median of total |", "|---|" + "---|" * 8]
    for wf in done:
        c = res["workflows"][wf]["site_component_medians"][str(YA)]
        comp_site.append(f"| {wf} | " + " | ".join(f"{c.get(k, 0):.0f}" for k in PARTS) + f" | {sum(c.values()):.0f} | "
                         f"{res['workflows'][wf]['local'][str(YA)]['p50']:.0f} |")
    diffs = {k: [res["workflows"][wf]["site_component_medians"][str(YA)].get(k, 0) - res["workflows"][wf]["global_component_medians"][str(YA)].get(k, 0)
                 for wf in done] for k in PARTS}
    res["site_minus_global_2100"] = {k: [min(v), max(v)] for k, v in diffs.items()}
    with open(os.path.join(exp, "coupling_summary.json"), "w") as f:      # rewrite with the extra key
        json.dump(res, f, indent=2)
    esl = ["| workflow | allowance 5% (m) | allowance median (m) | allowance 95% (m) | amplification factor median |", "|---|---|---|---|---|"]
    for wf in done:
        e = res["workflows"][wf].get("extreme_sea_level")
        if e:
            esl.append(f"| {wf} | {e['allowance_m']['p05']:.2f} | **{e['allowance_m']['p50']:.2f}** | {e['allowance_m']['p95']:.2f} | "
                       f"{e['amplification_factor']['p50']:.0f} |")
    link = ["| module output | rank correlation with the sample's 2100 warming |", "|---|---|"]
    for it, r in sorted(res["climate_link"].items(), key=lambda kv: -kv[1]):
        link.append(f"| {it} | {r:+.2f} |")
    valid = ", ".join(f"{wf}: {res['workflows'][wf]['valid_through']}" for wf in done)
    gsat = "; ".join(f"{yr}: {v['p50']:.1f} ({v['p05']:.1f}-{v['p95']:.1f})" for yr, v in res["gsat_c"].items())
    with open(os.path.join(exp, "coupling_tables.md"), "w") as f:
        f.write(f"Totals in {YA} (mm, since 2005; {nsamp} samples; all workflows valid)\n\n{totals_table(YA)}\n\n"
                f"Totals in {YB} (only workflows complete through {YB})\n\n{totals_table(YB)}\n\n"
                f"Global components in {YA} (mm)\n\n" + "\n".join(comp) +
                f"\n\nNew York components in {YA} (mm)\n\n" + "\n".join(comp_site) +
                "\n\nExtreme sea level, New York, 2100\n\n" + "\n".join(esl) +
                f"\n\nPer-sample link to the climate member (null: 0 +/- {res['climate_link_null_sd']:.3f})\n\n" + "\n".join(link) +
                f"\n\nValid through year per workflow: {valid}\n\nGlobal mean surface temperature (degC): {gsat}\n")
    write_summary_md(a.summary_md or os.path.join(ws, "SUMMARY_coupling_585.md"), exp, res, done, totals_table, comp, comp_site, esl, link, valid, res["gsat_c"])
    print(open(os.path.join(exp, "coupling_tables.md")).read())
    if res["missing_workflows"]:
        print("not yet available:", ", ".join(res["missing_workflows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
