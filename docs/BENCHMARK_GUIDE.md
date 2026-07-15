# FACTS Benchmark Suite User Guide

## Overview

The FACTS Benchmark Suite runs benchmark workflows for the FAIR module through Slurm. It supports CPU and GPU scaling, sample-size sweeps, and automated performance reporting.

> Note: The commands below assume execution on Discover. If you run them elsewhere, update the Slurm bindings and paths accordingly.

---

## Testing Goals

1. Allow sealevel users to configure and run the FACTS FAIR experiment on CPUs.
2. Identify the most effective approach for running multiple experiments with different configurations, such as those defined in a benchmark configuration file.

---

## Quick Start

### 1. Install the Repository

Clone the repository from a node on Discover:

```bash
mkdir test
cd test/
git clone https://github.com/nasa-nccs-hpda/sealevel.git
cd sealevel/notebooks/
```

---

### 2. Run a Benchmark

Run the benchmark suite with the Singularity and Slurm bindings shown below:

```bash
time /usr/local/other/singularity/4.0.3/bin/singularity exec \
  -B /usr/bin/sbatch,/etc/slurm/slurm.conf,/etc/slurm/preempt.conf,/etc/slurm/sched.preempt.conf,/etc/slurm/logacct.conf,/etc/slurm/nodesparts.conf,/usr/lib64/slurm,/usr/lib64/slurm/libslurmfull.so,/usr/slurm/lib64/slurm,/usr/slurm/lib64/slurm/auth_munge.so,/usr/lib64/libmunge.so.2,/run/munge/munge.socket.2,/usr/bin/squeue,/usr/bin/sacct,/home/gtamkin/test/sealevel/notebooks \
  /discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest.sif \
  python /home/gtamkin/test/sealevel/notebooks/facts_benchmark.py \
  --run --config /home/gtamkin/test/sealevel/notebooks/fair_config.yaml
```

This submits the benchmark job and creates a results directory such as:

```text
/home/gtamkin/test/sealevel/notebooks/benchmark_20260715_120307
```

Example output will include a summary similar to the following:

```text
FACTS Benchmark Suite: Fair Module Sample
Total configurations: 1
[1/1] samps_10: Sample scaling: 10 samples [samples]
Job ID: 57148204
```

---

### 3. Check Job Status

Monitor job progress with:

```bash
time /usr/local/other/singularity/4.0.3/bin/singularity exec \
  -B /usr/bin/sbatch,/etc/slurm/slurm.conf,/etc/slurm/preempt.conf,/etc/slurm/sched.preempt.conf,/etc/slurm/logacct.conf,/etc/slurm/nodesparts.conf,/usr/lib64/slurm,/usr/lib64/slurm/libslurmfull.so,/usr/slurm/lib64/slurm,/usr/slurm/lib64/slurm/auth_munge.so,/usr/lib64/libmunge.so.2,/run/munge/munge.socket.2,/usr/bin/squeue,/usr/bin/sacct,/home/gtamkin/test/sealevel/notebooks \
  /discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest.sif \
  python /home/gtamkin/test/sealevel/notebooks/facts_benchmark.py \
  --status --results-dir /home/gtamkin/test/sealevel/notebooks/benchmark_20260715_120307
```

This reports the current state of each benchmark job, including whether it is running, pending, completed, or failed.

---

### 4. Analyze the Results

After jobs finish, generate a report with:

```bash
time /usr/local/other/singularity/4.0.3/bin/singularity exec \
  -B /usr/bin/sbatch,/etc/slurm/slurm.conf,/etc/slurm/preempt.conf,/etc/slurm/sched.preempt.conf,/etc/slurm/logacct.conf,/etc/slurm/nodesparts.conf,/usr/lib64/slurm,/usr/lib64/slurm/libslurmfull.so,/usr/slurm/lib64/slurm,/usr/slurm/lib64/slurm/auth_munge.so,/usr/lib64/libmunge.so.2,/run/munge/munge.socket.2,/usr/bin/squeue,/usr/bin/sacct,/home/gtamkin/test/sealevel/notebooks \
  /discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest.sif \
  python /home/gtamkin/test/sealevel/notebooks/facts_benchmark.py \
  --analyze --results-dir /home/gtamkin/test/sealevel/notebooks/benchmark_20260715_120307
```

The analysis step creates:

- `benchmark_report.txt` — a plain-text summary
- `benchmark_report.md` — a Markdown report
- `analysis.json` — structured JSON results

Example summary output includes:

```text
Total benchmark runs: 1
Successful: 1
Failed: 0
Success rate: 100.0%
Fastest run: 23s
Slowest run: 23s
Average time: 23s
Median time: 23s
```

---

### 5. Review the Output Files

Inspect the run directory and generated results:

```bash
module load netcdf4

ls -alt /home/gtamkin/test/sealevel/notebooks/benchmark_20260715_120307/samps_10_20260715_120307/
```

You should see output files such as:

- `facts_results.json`
- `facts.log`
- `benchmark_result.json`
- `job.slurm`
- `facts_output/fair/`

To confirm the sample count, inspect the NetCDF output:

```bash
ncdump -h /home/gtamkin/test/sealevel/notebooks/benchmark_20260715_120307/samps_10_20260715_120307/facts_output/fair/climate.nc | grep samples
```

The reported sample count should match the `nsamps_range` setting in `fair_config.yaml`.

---

## Configuration Notes

Use the configuration file to define the benchmark sweep. A simple example is to set a sample range such as:

```yaml
nsamps_range: [10, 20, 50, 100, 2000, 8000]
```

You can then compare runtime and output characteristics for each setting and record the most efficient configuration.

---

## Recommended Workflow

1. Edit the benchmark configuration.
2. Submit the job with `--run`.
3. Monitor execution with `--status`.
4. Generate a report with `--analyze`.
5. Review the report and NetCDF outputs to compare performance.

