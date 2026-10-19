# Ice-sheet sea-level contribution under SSP5-8.5 (FACTS2, BAM) — one-page summary

Experiment `bam_ssp585_fixed_gauges`: ssp585, projection years 2020–2150 (step 10), base year 2005, 500 samples, 1,030 PSMSL tide-gauge locations.
Chain: `fair-temperature` 0.2.1 → `bamber19-icesheets` 0.2.0 → `facts-total` 0.2.1, run with Apptainer 1.5.3. Figures are in `facts2/figures/`.

## What this is
The ice-sheet part of sea-level rise only: Greenland (GIS) plus Antarctica (AIS, which is EAIS + WAIS). It leaves out glaciers, thermal expansion,
land water and vertical land motion, so **it is not total sea-level rise**. `bamber19-icesheets` (Bamber et al. 2019, expert-elicitation pools) reads the
FaIR temperature ensemble and returns sea-level change per sample, year and location.

## Headline numbers (2150, median of 500 samples, mm)
| | Global mean | Gauge sites (median of the 1,030 site medians) |
|---|---|---|
| Antarctica (AIS) | 403 | 439 |
| – East Antarctica (EAIS) | 49 | 53 |
| – West Antarctica (WAIS) | 344 | 375 |
| Greenland (GIS) | 420 | 335 |
| **Total (AIS + GIS)** | **914** | **871** |

- AIS = EAIS + WAIS to within 0.0005 mm. Medians of parts need not add up exactly, because the medians come from different samples.
- The total equals AIS + GIS exactly (difference 0 mm, global and local).
- Single-site check: New York, 2150 median 707 mm.
- At a site, local change = global change × a fixed factor per ice sheet and site. The factors differ widely and go **negative near an ice sheet**
  (for example Reykjavik for Greenland, −1.71; Argentine Islands for WAIS, −4.57), so sea level falls there while the global mean rises.
  See the factor map `figures/4b_site_factor_map.png`.
- When quoting a local figure, give a site-specific median. The "871" above is a median across sites, not a pooled median over all samples and locations.

## The Antarctica correction (say this out loud)
With the registry as published (`a085795`), `facts-total` summed AIS, EAIS, WAIS and GIS, which counts Antarctica twice: the 2150 global median came out at 1312 mm
(+44%) and New York at 1181 mm (+67%). The fix is `pass_to_total: false` on the four EAIS/WAIS outputs. It is applied here as a **local patch**
(`facts2/patches/bamber19_pass_to_total.patch`) and proposed upstream as fact-sealevel/facts-module-registry#20 (issue facts-experiment-builder#144), both open
and unreviewed so far. The original experiment `bam_ssp585` appears only as the "before" line in the total chart; never present it as a result.

## Caveats to attach to every plot
1. **Ice-sheet contribution only**, not total sea-level rise.
2. **Samples are not paired trajectories.** BAM uses climate member j only to set the probability of drawing from Bamber's high rather than low scenario pool
   (91% high under ssp585). The ice-sheet realisation is an independent draw (per-sample rank correlation about +0.05; checked by `notebooks/check_bam_pairing.py`).
   Report spreads, medians and totals as ensemble statistics, not as temperature-to-ice-loss paths.
3. Local values apply per-site scaling factors to one global projection; they carry no regional dynamics beyond that.

## Run facts
Exit 0; all outputs finite, units mm, 500 samples × 14 years (× 1,030 locations for local). Wall time 227 s with images already pulled
(fair-temperature 205 s, bamber19 17 s, facts-total 3 s global and 5 s local); cold run with image pulls about 10 min. Peak memory 412 MB.
Reproduce from scratch: `notebooks/README.md`, section "Setup from scratch (verified)". Tests: 25 pass in `notebooks/tests/test_run_bam.py`.

See also `SUMMARY_coupling_585.md`: the same kind of summary for the facts-experiment-catalog experiment (all components, six workflows, extreme sea level).
