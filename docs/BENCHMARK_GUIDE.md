# FACTS Benchmark Suite User Guide

## Overview

The FACTS Benchmark Suite orchestrates sea-level rise workflow benchmarks through Slurm, supporting CPU/GPU scaling, sample size analysis, and performance reporting.

---

## Quick Start

### 1. Run Benchmarks

Execute the benchmark suite with Slurm bindings:

```bash
/usr/local/other/singularity/4.0.3/bin/singularity exec \
  -B /usr/bin/sbatch,/etc/slurm/slurm.conf,/etc/slurm/preempt.conf,/etc/slurm/sched.preempt.conf,/etc/slurm/logacct.conf,/etc/slurm/nodesparts.conf,/usr/lib64/slurm,/usr/lib64/slurm/libslurmfull.so,/usr/slurm/lib64/slurm,/usr/slurm/lib64/slurm/auth_munge.so,/usr/lib64/libmunge.so.2,/run/munge/munge.socket.2,/usr/bin/squeue,/usr/bin/sacct \
  /discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest-sandbox \
  python facts_benchmark.py --run --config fair_config_local.yaml
```

**Output:** Results directory with timestamp (e.g., `benchmark_20260713_175600`)

---

### 2. Check Status

Monitor job progress:

```bash
python facts_benchmark.py --status \
  --results-dir /discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/benchmark_20260713_175600
```

**Output:**
```
Name                           Job ID       State        Time         MaxRSS       Done
------------------------------------------------------------------------------------------
samps_10                       discover     UNKNOWN                                ✓
```

---

### 3. Analyze Results

Generate comprehensive reports:

```bash
python facts_benchmark.py --analyze \
  --results-dir /discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/benchmark_20260713_175600
```

**Generated Files:**
- `benchmark_report.txt` — Text summary
- `benchmark_report.md` — Markdown report
- `analysis.json` — Raw JSON data

---

## Sample Output

### Benchmark Report

```
================================================================================
FACTS WORKFLOW BENCHMARK REPORT
================================================================================

Generated: 2026-07-13 17:57:53
Results Directory: /discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/benchmark_20260713_175600

EXECUTIVE SUMMARY
------------------------------------------------------------
  Total benchmark runs:     1
  Successful:               1
  Failed:                   0
  Success rate:             100.0%
  Fastest run:              23s
  Slowest run:              23s
  Average time:             23s
  Median time:              23s
  Std deviation:            0s
  Total compute time:       23s

KEY RECOMMENDATIONS
------------------------------------------------------------
  [HIGH] Fastest configuration: samps_10 (23s)

RESULTS BY PARTITION
------------------------------------------------------------
  compute           1 runs  avg: 23s        range: 23s-23s

RESULTS BY TAG
------------------------------------------------------------
  samples           1 runs  avg: 23s

DETAILED RESULTS
------------------------------------------------------------
  Name                         Part       CPUs   GPU      Samps  Time       OK
  samps_10                     compute    16     none     10     23s        ✓

================================================================================
```

---

## Configuration

Edit `fair_config_local.yaml` to customize benchmarks:

### Global Settings
```yaml
global:
  account: "ilab"
  scenario: "ssp585"
  phases: ["modules"]
  facts_script: "./run_facts.py"
  input_dir: "/discover/nobackup/projects/sealevel/facts2.0/data/input"
  container_dir: "/discover/nobackup/projects/sealevel/facts2.0/containers"
```

### Single Benchmarks
```yaml
benchmarks:
  - name: "cpu_test"
    partition: "compute"
    cpus: 16
    mem: "64G"
    time: "02:00:00"
    nsamps: 2000
    tags: ["cpu", "baseline"]
```

### Auto-Generated Ranges

#### CPU Scaling
```yaml
ranges:
  cpu_scaling:
    enabled: true
    partition: "compute"
    cpus: [4, 8, 16, 32, 64, 128, 256, 512, 1024]
    mem: "64G"
    nsamps: 2000
    name_template: "cpu_{cpus}"
```

#### Sample Scaling
```yaml
  sample_scaling:
    enabled: true
    partition: "compute"
    cpus: 16
    nsamps_range: [10, 20, 50, 100, 2000, 8000]
    time_map:
      10: "01:00:00"
      20: "02:00:00"
      50: "05:00:00"
      100: "10:00:00"
      2000: "12:00:00"
      8000: "12:00:00"
```

---

## Output Structure

```
benchmark_20260713_175600/
├── benchmark_report.txt
├── benchmark_report.md
├── analysis.json
└── samps_10_20260713_175600/
    ├── facts_output/
    │   └── fair/
    │       ├── climate.nc
    │       ├── gsat.nc
    │       ├── oceantemp.nc
    │       └── ohc.nc
    └── job.slurm
```

---

## Slurm Bindings Required

The container execution requires these bindings for Slurm integration:

| Path | Purpose |
|------|---------|
| `/usr/bin/sbatch` | Job submission |
| `/etc/slurm/slurm.conf` | Cluster configuration |
| `/etc/slurm/*.conf` | Preempt, scheduling, node configs |
| `/usr/lib64/slurm/` | Slurm libraries |
| `/usr/slurm/lib64/` | Slurm plugin directory |
| `/usr/lib64/libmunge.so.2` | Munge authentication |
| `/run/munge/munge.socket.2` | Munge socket |
| `/usr/bin/squeue` | Job status query |
| `/usr/bin/sacct` | Job accounting |

**Note:** Initial warnings about underlay bind mounts (>50 mounts) are normal and do not affect execution.

---

## Key Metrics

### Performance Summary
- **Success Rate:** Percentage of successful runs
- **Execution Time:** Wall-clock time per benchmark
- **Compute Time:** Total CPU hours consumed
- **Speedup:** Relative performance across configurations

### By Partition
- Grouped results for CPU vs. GPU nodes
- Average execution time per partition
- Resource utilization statistics

### By Tag
- Filter results by category (cpu, gpu, baseline, scaling, samples)
- Identify optimal configurations by use case

---

## Troubleshooting

### Job Status Unknown
- Wait for Slurm to update job status
- Check `/etc/slurm/slurm.conf` is readable
- Verify Munge socket is accessible

### Missing Output Files
- Confirm benchmark container path is correct
- Verify input data directory exists
- Check Singularity bindings are complete

### Low Performance
- Review CPU/GPU allocation in config
- Compare against baseline benchmarks
- Analyze scaling plots in report

---

## Example Workflow

1. **Configure** → Edit `fair_config_local.yaml`
2. **Run** → Submit benchmarks with `--run`
3. **Wait** → Monitor with `--status`
4. **Analyze** → Generate reports with `--analyze`
5. **Review** → Inspect `benchmark_report.md` and `analysis.json`

