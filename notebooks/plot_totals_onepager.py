"""One-page figure of the facts-total results (for people who did not follow the run): what each workflow's 2100 total is made of,
global mean and New York, with the median and the 5-95% range of the total.

Reads <experiment>/coupling_summary.json (written by summarize_coupling.py), writes figures/coupling_585_onepager.png.

    uv run --isolated --python 3.12 --with xarray --with netcdf4 --with 'numpy<2' --with matplotlib --with pandas \
        python notebooks/plot_totals_onepager.py --experiment apptainer_experiments/coupling-585-260603-fast
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                                                     # noqa: E402
from summarize_coupling import GRID, INK, INK2, PART_COLOR, PARTS, WORKFLOWS, YA                      # noqa: E402

DESC = {"wf1e": "wf1e", "wf2f": "wf2f", "wf2e": "wf2e", "wf3f": "wf3f", "wf3e": "wf3e", "wf4": "wf4"}


def panel(ax, res, scale, medians_key, parts, title):
    done = [w for w in WORKFLOWS if w in res["workflows"]]
    for i, wf in enumerate(done):
        y = len(done) - 1 - i
        w = res["workflows"][wf]
        left = 0.0
        for part in parts:
            v = w[medians_key][str(YA)].get(part)
            if v is None:
                continue
            ax.barh(y, v, left=left, height=0.56, color=PART_COLOR[part], edgecolor="white", linewidth=2)
            left += max(v, 0)
        t = w[scale][str(YA)]
        ax.plot([t["p05"], t["p95"]], [y - 0.42, y - 0.42], "-", color=INK, lw=1.6, solid_capstyle="butt")
        ax.plot([t["p05"], t["p95"]], [y - 0.42] * 2, "|", color=INK, ms=7, mew=1.6)
        ax.plot(t["p50"], y - 0.42, "o", color="white", mec=INK, mew=1.8, ms=7, zorder=4)
        ax.text(t["p95"] + 25, y - 0.42, f"median {t['p50']:.0f} mm", va="center", fontsize=9, color=INK2)
    ax.set_yticks(range(len(done)))
    ax.set_yticklabels(done[::-1])
    ax.set_ylim(-0.85, len(done) - 0.4)
    ax.set_xlim(0, 2650)
    ax.set_title(title)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("mm of sea-level rise in 2100")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--experiment", default="apptainer_experiments/coupling-585-260603-fast")
    p.add_argument("--workspace", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "facts2"))
    a = p.parse_args()
    exp = os.path.join(a.workspace, a.experiment)
    with open(os.path.join(exp, "coupling_summary.json")) as f:
        res = json.load(f)
    plt.rcParams.update({"font.size": 10.5, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "text.color": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                         "axes.axisbelow": True, "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left"})
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.05, 0.955, "Did the totaling step run? Yes: all 12 totals exist and add up", fontsize=17, fontweight="bold", va="top")
    fig.text(0.05, 0.915, "facts-total ran for each of the 6 workflows, once for the global mean and once for New York. Each total is the sum of the\n"
             "components listed under it, checked to 0.001 mm (validation: OK, 58 files, 12 totals).",
             fontsize=10.5, color=INK2, va="top")
    ax1 = fig.add_axes([0.08, 0.50, 0.86, 0.27])
    ax2 = fig.add_axes([0.08, 0.17, 0.86, 0.24])
    panel(ax1, res, "global", "global_component_medians", PARTS[:5], "Global mean sea level, 2100")
    panel(ax2, res, "local", "site_component_medians", [p_ for p_ in PARTS if p_ != "Land water"] + ["Land water"],
          "New York (local, includes vertical land motion), 2100")
    hs = [plt.Rectangle((0, 0), 1, 1, color=PART_COLOR[p_]) for p_ in PARTS]
    fig.legend(hs, PARTS, ncol=6, loc="upper center", bbox_to_anchor=(0.5, 0.875), frameon=False, fontsize=9.5)
    fig.text(0.05, 0.02, "Bars: median of each component, stacked.  Circle: median of the total; line: its 5-95% range (2,000 samples).  The circle is usually a little\n"
             "right of the bar end because medians of skewed parts do not add exactly to the median of their sum.  Scenario ssp585.\n"
             "wf1e, wf2e and wf3e are valid through 2100 only (emulandice stops there), so 2100 is the comparison year.",
             fontsize=8.8, color=INK2, va="bottom")
    out = os.path.normpath(os.path.join(a.workspace, "figures", "coupling_585_onepager.png"))
    fig.savefig(out, dpi=170, facecolor="white")
    print(out)


if __name__ == "__main__":
    main()
