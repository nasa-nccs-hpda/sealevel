from pathlib import Path
import numpy as np
import os
import sys
import argparse
import re
from scipy.stats import norm

from emulandice.r_helper import run_emulandice
from emulandice.io import WriteNetCDF


# For glaciers, there are 19 regions
def ExtractProjections(emulandice_file):
    # Initialize
    ice_sources = []
    regions = []
    years = []
    samples = []
    sles = []

    # Open the emulandice_file for reading
    with open(emulandice_file, "r") as f:
        # Skip the header line
        _ = f.readline()

        # Load the rest of the data
        for line in f:
            lp = re.split(",", line)
            ice_sources.append(lp[0])
            regions.append(lp[1])
            years.append(int(lp[2]))
            samples.append(int(lp[3]))
            sles.append(float(lp[7]))

    # Convert to numpy arrays
    ice_sources = np.array(ice_sources)
    regions = np.array(regions)
    years = np.array(years)
    samples = np.array(samples)
    sles = np.array(sles)

    # Extract the unique target years, samples, and regions
    targyears = np.unique(years)
    unique_samples = np.unique(samples)
    unique_regions = np.unique(regions)

    # Initialize the return data structure
    ret_data = np.full(
        (len(unique_regions), len(unique_samples), len(targyears)), np.nan
    )

    # Pre-compile the regular expression that extracts region number
    region_regex = re.compile("^region_(\d+)$")

    # Loop over all the entries
    for i in np.arange(len(sles)):
        # This sample
        this_icesource = ice_sources[i]
        this_region = regions[i]
        this_year = years[i]
        this_sample = samples[i]
        this_sle = sles[i]

        # Skip this entry if it's not for AIS
        if this_icesource != "Glaciers":
            continue

        # Which index will this entry be filling?
        year_idx = np.flatnonzero(targyears == this_year)
        sample_idx = this_sample - 1

        region_rematch = region_regex.match(this_region)
        region_idx = int(region_rematch.group(1)) - 1

        # Put the data into the return data structure
        ret_data[region_idx, sample_idx, year_idx] = this_sle * 10.0  # Convert cm to mm

    # Done
    return (ret_data, targyears)


def emulandice_project_glaciers(
    pipeline_id,
    preprocess_data: dict,
    fit_data: dict,
    output_dir,
    output_gslr_file: str,
    output_glacier_dir: str | None = None,
    icesource="Glaciers",
):
    preprocess_infile = preprocess_data["infile"]
    baseyear = preprocess_data["baseyear"]
    scenario = preprocess_data["scenario"]
    nsamps = preprocess_data["nsamps"]

    trend_mean = fit_data["trend_mean"]
    trend_sd = fit_data["trend_sd"]

    # Run the module using the FACTS forcing data

    emulandice_dataset = preprocess_data["facts_data_file"]
    run_emulandice(
        emulandice_dataset=emulandice_dataset,
        nsamps=nsamps,
        icesource=icesource,
        outdir=output_dir,
    )

    # Get the output from the emulandice run
    emulandice_file = os.path.join(output_dir, "projections_FAIR_FACTS.csv")
    samples, targyears = ExtractProjections(emulandice_file)

    # Make sure we get the number of samples we expected
    if nsamps != samples.shape[1]:
        raise Exception(
            "Number of SLC projections does not match number of temperature trajectories: {} != {}".format(
                samples.shape[1], nsamps
            )
        )

    # Find the ratio of melt over the first decade of projection years
    syear_idx = 0
    eyear_idx = np.max(np.flatnonzero(targyears <= (targyears[syear_idx] + 10)))

    region_melt = []
    total_melt = 0.0
    for x in np.arange(samples.shape[0]):
        this_melt = np.nanmean(samples[x, :, eyear_idx]) - np.nanmean(
            samples[x, :, syear_idx]
        )
        total_melt += this_melt
        region_melt.append(this_melt)
    region_melt = np.array(region_melt)
    melt_ratio = region_melt / total_melt

    # Generate samples for trends correlated among ice sources
    # Note: Keep seed hard-coded and matched with AIS and GrIS module within emulandice module set
    rng = np.random.default_rng(8071)
    trend_q = rng.random(nsamps)
    glac_trend = norm.ppf(trend_q, trend_mean, trend_sd) * (
        targyears[syear_idx] - baseyear
    )

    # Apply the trends for the baseline adjustment
    for x in np.arange(samples.shape[0]):
        this_trend = glac_trend * melt_ratio[x]
        samples[x, :, :] += this_trend[:, np.newaxis]

    # Save the global projections to a pickle
    output = {
        "gic_samps": samples,
        "targyears": targyears,
        "scenario": scenario,
        "baseyear": baseyear,
        "preprocess_infile": preprocess_infile,
    }

    # Write the global projections to netcdf files
    gic_global_slr = np.sum(samples, axis=0)
    WriteNetCDF(
        gic_global_slr,
        targyears,
        baseyear,
        scenario,
        nsamps,
        pipeline_id,
        nc_filename=output_gslr_file,
        nc_description="Global SLR contribution from glaciers using the emulandice module",
    )

    if output_glacier_dir is not None:
        p = Path(output_glacier_dir)
        p.mkdir(exist_ok=True)

        for i, sample in enumerate(samples):
            idx = i + 1
            out_file = p / f"glac{idx}_globalsl.nc"

            WriteNetCDF(
                sample,
                targyears,
                baseyear,
                scenario,
                nsamps,
                pipeline_id,
                nc_filename=str(out_file),
                nc_description=f"Global SLR contribution from glaciers (glac{idx}) using the emulandice module",
            )

    return output


if __name__ == "__main__":
    # Initialize the argument parser
    parser = argparse.ArgumentParser(
        description="Run the projection stage for the emulandice glaciers SLR projection workflow",
        epilog="Note: This is meant to be run as part of the Framework for the Assessment of Changes To Sea-level (FACTS)",
    )

    # Add arguments for the resource and experiment configuration files
    parser.add_argument(
        "--pipeline_id",
        help="Unique identifier for this instance of the module",
        required=True,
    )

    # Parse the arguments
    args = parser.parse_args()

    # Run the preprocessing
    emulandice_project_glaciers(args.pipeline_id)

    # Done
    sys.exit()
