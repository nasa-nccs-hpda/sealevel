#!/usr/bin/env python
"""
facts_benchmark.py - FACTS Workflow Benchmarking System
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class BenchmarkConfig:
    name: str
    partition: str
    account: str
    nodes: int = 1
    ntasks: int = 1
    cpus: Optional[int] = None
    mem: Optional[str] = None
    mem_per_cpu: Optional[str] = None
    mem_per_gpu: Optional[str] = None
    cpus_per_gpu: Optional[int] = None
    time: str = "04:00:00"
    gres: Optional[str] = None
    nsamps: int = 20
    scenario: str = "ssp585"
    phases: List[str] = field(default_factory=lambda: ["modules", "modules2", "total"])
    constraint: Optional[str] = None
    qos: Optional[str] = None
    description: str = ""


@dataclass
class BenchmarkSuite:
    name: str
    output_dir: str
    configs: List[BenchmarkConfig]
    facts_script: str = "./run_facts.py"
    input_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/data/input"
    base_output_dir: str = "/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output"
    container_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/containers"


# =============================================================================
# Configuration Generators
# =============================================================================

def generate_default_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate default CPU benchmark configurations"""
    configs = []
    
    # CPU scaling
    for cpus in [4, 8, 16, 32]:
        configs.append(BenchmarkConfig(
            name=f"compute_cpu{cpus}",
            partition="compute",
            account=account,
            cpus=cpus,
            mem="64G",
            time="04:00:00",
            nsamps=20,
            description=f"Compute partition with {cpus} CPUs"
        ))
    
    # Memory variations
    for mem in ["32G", "64G", "128G"]:
        configs.append(BenchmarkConfig(
            name=f"compute_mem{mem.replace('G', '')}",
            partition="compute",
            account=account,
            cpus=16,
            mem=mem,
            time="04:00:00",
            nsamps=20,
            description=f"Compute partition with {mem} memory"
        ))
    
    # Sample count variations
    for nsamps in [10, 20, 50]:
        configs.append(BenchmarkConfig(
            name=f"compute_samps{nsamps}",
            partition="compute",
            account=account,
            cpus=16,
            mem="64G",
            time="06:00:00",
            nsamps=nsamps,
            description=f"Compute partition with {nsamps} samples"
        ))
    
    return configs


def generate_quick_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate quick test configurations"""
    return [
        BenchmarkConfig(
            name="quick_small",
            partition="compute",
            account=account,
            cpus=4,
            mem="16G",
            time="01:00:00",
            nsamps=5,
            phases=["modules"],
            description="Quick small test"
        ),
        BenchmarkConfig(
            name="quick_medium",
            partition="compute",
            account=account,
            cpus=8,
            mem="32G",
            time="02:00:00",
            nsamps=10,
            phases=["modules"],
            description="Quick medium test"
        ),
    ]


def generate_scaling_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate CPU scaling configurations"""
    configs = []
    for cpus in [1, 2, 4, 8, 16, 32]:
        configs.append(BenchmarkConfig(
            name=f"scale_cpu{cpus}",
            partition="compute",
            account=account,
            cpus=cpus,
            mem="64G",
            time="04:00:00",
            nsamps=20,
            description=f"Scaling test: {cpus} CPUs"
        ))
    return configs


def generate_gpu_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate GPU benchmark configurations"""
    configs = []
    
    # Single GPU - quick test
    configs.append(BenchmarkConfig(
        name="gpu_a100_1gpu_quick",
        partition="gpu_a100",
        account=account,
        gres="gpu:1",
        constraint="rome",
        time="01:00:00",
        nsamps=5,
        phases=["modules"],
        description="Single A100 GPU - quick test"
    ))
    
    # Single GPU - full test
    configs.append(BenchmarkConfig(
        name="gpu_a100_1gpu",
        partition="gpu_a100",
        account=account,
        gres="gpu:1",
        constraint="rome",
        time="02:00:00",
        nsamps=20,
        phases=["modules"],
        description="Single A100 GPU"
    ))
    
    # Multiple GPUs
    for ngpu in [2, 4]:
        configs.append(BenchmarkConfig(
            name=f"gpu_a100_{ngpu}gpu",
            partition="gpu_a100",
            account=account,
            gres=f"gpu:{ngpu}",
            constraint="rome",
            time="02:00:00",
            nsamps=20,
            phases=["modules"],
            description=f"{ngpu} A100 GPUs"
        ))
    
    # GPU with varying samples
    for nsamps in [10, 20, 50]:
        configs.append(BenchmarkConfig(
            name=f"gpu_a100_samps{nsamps}",
            partition="gpu_a100",
            account=account,
            gres="gpu:1",
            constraint="rome",
            time="04:00:00",
            nsamps=nsamps,
            phases=["modules"],
            description=f"Single A100 GPU with {nsamps} samples"
        ))
    
    return configs


def generate_gpu_quick_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate quick GPU test configuration"""
    return [
        BenchmarkConfig(
            name="gpu_quick",
            partition="gpu_a100",
            account=account,
            gres="gpu:1",
            constraint="rome",
            time="01:00:00",
            nsamps=5,
            phases=["modules"],
            description="Quick GPU test"
        ),
    ]


def generate_comparison_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    """Generate CPU vs GPU comparison configurations"""
    return [
        # CPU baseline
        BenchmarkConfig(
            name="compare_cpu16",
            partition="compute",
            account=account,
            cpus=16,
            mem="64G",
            time="02:00:00",
            nsamps=20,
            phases=["modules"],
            description="CPU comparison: 16 CPUs"
        ),
        BenchmarkConfig(
            name="compare_cpu32",
            partition="compute",
            account=account,
            cpus=32,
            mem="128G",
            time="02:00:00",
            nsamps=20,
            phases=["modules"],
            description="CPU comparison: 32 CPUs"
        ),
        # GPU
        BenchmarkConfig(
            name="compare_gpu1",
            partition="gpu_a100",
            account=account,
            gres="gpu:1",
            constraint="rome",
            time="02:00:00",
            nsamps=20,
            phases=["modules"],
            description="GPU comparison: 1 A100"
        ),
        BenchmarkConfig(
            name="compare_gpu2",
            partition="gpu_a100",
            account=account,
            gres="gpu:2",
            constraint="rome",
            time="02:00:00",
            nsamps=20,
            phases=["modules"],
            description="GPU comparison: 2 A100s"
        ),
    ]


# =============================================================================
# SLURM Script Generation
# =============================================================================

def generate_slurm_script(config: BenchmarkConfig, suite: BenchmarkSuite, 
                          job_output_dir: str) -> str:
    """Generate SLURM script with all absolute paths"""
    
    job_output_dir = os.path.abspath(job_output_dir)
    facts_script = os.path.abspath(suite.facts_script)
    facts_output_dir = os.path.join(job_output_dir, "facts_output")
    log_file = os.path.join(job_output_dir, "facts.log")
    
    phases_str = " ".join(config.phases)
    phases_json = json.dumps(config.phases)
    
    # Build SBATCH header
    sbatch_lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name=bench_{config.name}",
        f"#SBATCH --output={job_output_dir}/slurm_%j.out",
        f"#SBATCH --error={job_output_dir}/slurm_%j.err",
        f"#SBATCH --partition={config.partition}",
        f"#SBATCH --account={config.account}",
        f"#SBATCH --time={config.time}",
        f"#SBATCH --nodes={config.nodes}",
        f"#SBATCH --ntasks={config.ntasks}",
    ]
    
    if config.gres:
        sbatch_lines.append(f"#SBATCH --gres={config.gres}")
        if config.cpus_per_gpu:
            sbatch_lines.append(f"#SBATCH --cpus-per-gpu={config.cpus_per_gpu}")
        if config.mem_per_gpu:
            sbatch_lines.append(f"#SBATCH --mem-per-gpu={config.mem_per_gpu}")
    else:
        if config.cpus:
            sbatch_lines.append(f"#SBATCH --cpus-per-task={config.cpus}")
        if config.mem:
            sbatch_lines.append(f"#SBATCH --mem={config.mem}")
    
    if config.constraint:
        sbatch_lines.append(f"#SBATCH --constraint={config.constraint}")
    if config.qos:
        sbatch_lines.append(f"#SBATCH --qos={config.qos}")
    
    sbatch_header = "\n".join(sbatch_lines)
    
    # Determine if GPU job
    is_gpu = config.gres is not None
    
    script = f'''{sbatch_header}

BENCH_DIR="{job_output_dir}"

echo "========================================"
echo "Benchmark: {config.name}"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_JOB_NODELIST"
echo "Partition: {config.partition}"
'''
    
    if is_gpu:
        script += '''echo "GPUs: $CUDA_VISIBLE_DEVICES"
'''
    
    script += f'''echo "Start: $(date)"
echo "========================================"

BENCH_START=$(date +%s)

# Load modules
module load python/GEOSpyD/24.3.0-0/3.11
module load singularity/4.0.3
'''
    
    if is_gpu:
        script += '''module load cuda/11.8 2>/dev/null || true

# Show GPU info
nvidia-smi || echo "nvidia-smi not available"
'''
    
    script += f'''
# Set Singularity cache/temp directories
export SINGULARITY_CACHEDIR="$BENCH_DIR/singularity_cache"
export SINGULARITY_TMPDIR="$BENCH_DIR/singularity_tmp"
export TMPDIR="$BENCH_DIR/tmp"
mkdir -p "$SINGULARITY_CACHEDIR" "$SINGULARITY_TMPDIR" "$TMPDIR"

export OMP_NUM_THREADS=${{SLURM_CPUS_PER_TASK:-${{SLURM_CPUS_ON_NODE:-1}}}}

cd "{job_output_dir}"

echo "Running FACTS workflow..."
echo "Output dir: {facts_output_dir}"

python {facts_script} \\
    --nsamps {config.nsamps} \\
    --scenario {config.scenario} \\
    --input-dir '{suite.input_dir}' \\
    --output-dir '{facts_output_dir}' \\
    --container-dir '{suite.container_dir}' \\
    --phases {phases_str} \\
    --verbose \\
    --log-file '{log_file}'

EXIT_CODE=$?

BENCH_END=$(date +%s)
BENCH_ELAPSED=$((BENCH_END - BENCH_START))

cat > "{job_output_dir}/benchmark_result.json" << RESULT
{{
  "name": "{config.name}",
  "job_id": "$SLURM_JOB_ID",
  "exit_code": $EXIT_CODE,
  "start_time": $BENCH_START,
  "end_time": $BENCH_END,
  "elapsed_seconds": $BENCH_ELAPSED,
  "nsamps": {config.nsamps},
  "scenario": "{config.scenario}",
  "partition": "{config.partition}",
  "cpus": "{config.cpus or 'default'}",
  "mem": "{config.mem or 'default'}",
  "gres": "{config.gres or 'none'}",
  "constraint": "{config.constraint or 'none'}",
  "phases": {phases_json},
  "description": "{config.description}"
}}
RESULT

echo "========================================"
echo "Completed: $(date)"
echo "Elapsed: $BENCH_ELAPSED seconds"
echo "Exit: $EXIT_CODE"
echo "========================================"

exit $EXIT_CODE
'''
    
    return script


# =============================================================================
# Job Submission and Monitoring
# =============================================================================

def submit_benchmark(config: BenchmarkConfig, suite: BenchmarkSuite) -> Tuple[Optional[str], str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_output_dir = os.path.abspath(os.path.join(suite.output_dir, f"{config.name}_{timestamp}"))
    os.makedirs(job_output_dir, exist_ok=True)
    os.makedirs(os.path.join(job_output_dir, "facts_output"), exist_ok=True)
    
    for subdir in ["fair", "lws", "sterodynamics", "bamber", "ipccar5_glaciers", 
                   "ipccar5_icesheets", "kopp14verticallandmotion"]:
        os.makedirs(os.path.join(job_output_dir, "facts_output", subdir), exist_ok=True)
    
    with open(os.path.join(job_output_dir, "config.json"), 'w') as f:
        json.dump(asdict(config), f, indent=2)
    
    slurm_script = generate_slurm_script(config, suite, job_output_dir)
    slurm_file = os.path.join(job_output_dir, "job.slurm")
    with open(slurm_file, 'w') as f:
        f.write(slurm_script)
    
    result = subprocess.run(['sbatch', slurm_file], capture_output=True, text=True)
    
    if result.returncode == 0:
        job_id = result.stdout.strip().split()[-1]
        with open(os.path.join(job_output_dir, "job_id.txt"), 'w') as f:
            f.write(job_id)
        return job_id, job_output_dir
    else:
        with open(os.path.join(job_output_dir, "submit_error.txt"), 'w') as f:
            f.write(f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}")
        return None, job_output_dir


def submit_all_benchmarks(suite: BenchmarkSuite, delay: float = 2.0) -> Dict[str, dict]:
    print(f"\nSubmitting {len(suite.configs)} benchmarks to: {suite.output_dir}")
    print("=" * 60)
    
    jobs = {}
    
    for i, config in enumerate(suite.configs, 1):
        print(f"[{i}/{len(suite.configs)}] {config.name}: {config.description}")
        
        job_id, output_dir = submit_benchmark(config, suite)
        
        jobs[config.name] = {
            "job_id": job_id,
            "output_dir": output_dir,
            "config": asdict(config),
            "submit_time": datetime.now().isoformat(),
            "status": "SUBMITTED" if job_id else "SUBMIT_FAILED"
        }
        
        print(f"    {'✓' if job_id else '✗'} Job ID: {job_id or 'FAILED'}")
        
        if i < len(suite.configs):
            time.sleep(delay)
    
    jobs_file = os.path.join(suite.output_dir, "jobs.json")
    with open(jobs_file, 'w') as f:
        json.dump(jobs, f, indent=2)
    
    print("=" * 60)
    submitted = sum(1 for j in jobs.values() if j["job_id"])
    print(f"Submitted: {submitted}/{len(suite.configs)}")
    
    return jobs


def get_job_status(job_id: str) -> dict:
    result = subprocess.run(
        ['squeue', '-j', job_id, '-h', '-o', '%T|%M|%R'],
        capture_output=True, text=True
    )
    
    if result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split('|')
        return {"state": parts[0], "time": parts[1] if len(parts) > 1 else ""}
    
    result = subprocess.run(
        ['sacct', '-j', job_id, '-n', '-P', 
         '--format=JobID,State,ExitCode,Elapsed,MaxRSS,MaxVMSize'],
        capture_output=True, text=True
    )
    
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split('\n'):
            parts = line.split('|')
            if parts[0] == job_id:
                return {
                    "state": parts[1],
                    "exit_code": parts[2] if len(parts) > 2 else "",
                    "elapsed": parts[3] if len(parts) > 3 else "",
                    "max_rss": parts[4] if len(parts) > 4 else "",
                    "max_vmsize": parts[5] if len(parts) > 5 else ""
                }
    
    return {"state": "UNKNOWN"}


def check_benchmark_status(results_dir: str) -> None:
    jobs_file = os.path.join(results_dir, "jobs.json")
    
    if not os.path.exists(jobs_file):
        print(f"No jobs.json found in {results_dir}")
        return
    
    with open(jobs_file) as f:
        jobs = json.load(f)
    
    print(f"\nBenchmark Status: {results_dir}")
    print("=" * 80)
    print(f"{'Name':<30} {'Job ID':<12} {'State':<12} {'Time':<12} {'Result'}")
    print("-" * 80)
    
    for name, job in jobs.items():
        job_id = job.get("job_id", "N/A")
        
        if job_id and job_id != "N/A":
            status = get_job_status(job_id)
            state = status.get("state", "UNKNOWN")
            elapsed = status.get("elapsed", status.get("time", ""))
        else:
            state = "SUBMIT_FAILED"
            elapsed = ""
        
        result_file = os.path.join(job["output_dir"], "benchmark_result.json")
        has_result = "✓" if os.path.exists(result_file) else ""
        
        print(f"{name:<30} {job_id:<12} {state:<12} {elapsed:<12} {has_result}")
    
    print("=" * 80)


# =============================================================================
# Analysis and Reporting
# =============================================================================

def parse_elapsed(elapsed_str: str) -> int:
    try:
        if '-' in elapsed_str:
            days, rest = elapsed_str.split('-')
            days = int(days)
        else:
            days = 0
            rest = elapsed_str
        
        parts = rest.split(':')
        if len(parts) == 3:
            h, m, s = map(int, parts)
        elif len(parts) == 2:
            h, m, s = 0, int(parts[0]), int(parts[1])
        else:
            return 0
        
        return days * 86400 + h * 3600 + m * 60 + s
    except:
        return 0


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def collect_results(suite_dir: str) -> List[dict]:
    results = []
    suite_path = Path(suite_dir)
    
    for result_file in suite_path.glob("*/benchmark_result.json"):
        try:
            with open(result_file) as f:
                result = json.load(f)
            
            config_file = result_file.parent / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    result["config"] = json.load(f)
            
            result["output_dir"] = str(result_file.parent)
            results.append(result)
        except Exception as e:
            print(f"Warning: {e}")
    
    return results


def analyze_results(results: List[dict]) -> dict:
    if not results:
        return {"summary": {"total_runs": 0}}
    
    def is_success(r):
        ec = r.get("exit_code")
        return ec == 0 or ec == "0:0"
    
    successful = [r for r in results if is_success(r)]
    failed = [r for r in results if not is_success(r)]
    
    analysis = {
        "summary": {
            "total_runs": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100 if results else 0
        },
        "timing": {},
        "by_partition": {},
        "by_cpus": {},
        "by_gres": {},
        "by_nsamps": {},
        "scaling": {},
        "failures": [],
        "recommendations": []
    }
    
    if successful:
        times = [r.get("elapsed_seconds", 0) for r in successful if r.get("elapsed_seconds")]
        if times:
            analysis["timing"] = {
                "min": min(times),
                "max": max(times),
                "avg": sum(times) / len(times),
                "total": sum(times)
            }
    
    # By partition
    partitions = set(r.get("partition") for r in successful if r.get("partition"))
    for partition in partitions:
        part_results = [r for r in successful if r.get("partition") == partition]
        times = [r.get("elapsed_seconds", 0) for r in part_results if r.get("elapsed_seconds")]
        if times:
            analysis["by_partition"][partition] = {
                "count": len(part_results),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times)
            }
    
    # By GRES (GPU)
    gres_values = set(r.get("gres") for r in successful if r.get("gres") and r.get("gres") != "none")
    for gres in gres_values:
        gres_results = [r for r in successful if r.get("gres") == gres]
        times = [r.get("elapsed_seconds", 0) for r in gres_results if r.get("elapsed_seconds")]
        if times:
            analysis["by_gres"][gres] = {
                "count": len(gres_results),
                "avg_time": sum(times) / len(times)
            }
    
    # By CPUs
    cpu_values = set()
    for r in successful:
        cpus = r.get("cpus")
        if cpus and cpus not in [None, "default", "unknown"]:
            try:
                cpu_values.add(int(cpus))
            except:
                pass
    
    for cpus in sorted(cpu_values):
        cpu_results = [r for r in successful if str(r.get("cpus")) == str(cpus)]
        times = [r.get("elapsed_seconds", 0) for r in cpu_results if r.get("elapsed_seconds")]
        if times:
            analysis["by_cpus"][str(cpus)] = {
                "count": len(cpu_results),
                "avg_time": sum(times) / len(times)
            }
    
    # CPU Scaling
    if len(analysis["by_cpus"]) >= 2:
        cpu_data = [(int(k), v["avg_time"]) for k, v in analysis["by_cpus"].items()]
        cpu_data.sort()
        base_cpus, base_time = cpu_data[0]
        
        scaling = []
        for cpus, t in cpu_data:
            speedup = base_time / t if t > 0 else 0
            ideal = cpus / base_cpus
            efficiency = (speedup / ideal * 100) if ideal > 0 else 0
            scaling.append({
                "cpus": cpus,
                "time": round(t, 1),
                "speedup": round(speedup, 2),
                "efficiency": round(efficiency, 1)
            })
        analysis["scaling"]["cpu"] = scaling
    
    # Failures
    for r in failed:
        analysis["failures"].append({
            "name": r.get("name"),
            "exit_code": r.get("exit_code"),
            "partition": r.get("partition"),
            "gres": r.get("gres")
        })
    
    # Recommendations
    if successful:
        fastest = min(successful, key=lambda r: r.get("elapsed_seconds") or float('inf'))
        if fastest.get("elapsed_seconds"):
            analysis["recommendations"].append(
                f"Fastest: {fastest.get('name')} ({format_time(fastest['elapsed_seconds'])})"
            )
    
    return analysis


def generate_report(results: List[dict], analysis: dict, output_file: str):
    def is_success(r):
        ec = r.get("exit_code")
        return ec == 0 or ec == "0:0"
    
    lines = [
        "=" * 80,
        "FACTS WORKFLOW BENCHMARK REPORT",
        "=" * 80,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "SUMMARY",
        "-" * 60,
        f"  Total runs:     {analysis['summary']['total_runs']}",
        f"  Successful:     {analysis['summary']['successful']}",
        f"  Failed:         {analysis['summary']['failed']}",
        f"  Success rate:   {analysis['summary']['success_rate']:.1f}%",
    ]
    
    if analysis.get("timing"):
        t = analysis["timing"]
        lines.extend([
            "",
            f"  Fastest:        {format_time(t['min'])}",
            f"  Slowest:        {format_time(t['max'])}",
            f"  Average:        {format_time(t['avg'])}",
        ])
    
    lines.append("")
    
    # By partition
    if analysis.get("by_partition"):
        lines.extend(["BY PARTITION", "-" * 60])
        for part, stats in analysis["by_partition"].items():
            lines.append(f"  {part:<15} {stats['count']} runs, avg {format_time(stats['avg_time'])}")
        lines.append("")
    
    # By GPU
    if analysis.get("by_gres"):
        lines.extend(["BY GPU CONFIG", "-" * 60])
        for gres, stats in analysis["by_gres"].items():
            lines.append(f"  {gres:<15} {stats['count']} runs, avg {format_time(stats['avg_time'])}")
        lines.append("")
    
    # CPU Scaling
    if analysis.get("scaling", {}).get("cpu"):
        lines.extend([
            "CPU SCALING",
            "-" * 60,
            f"  {'CPUs':<8} {'Time':<12} {'Speedup':<10} {'Efficiency'}"
        ])
        for s in analysis["scaling"]["cpu"]:
            lines.append(f"  {s['cpus']:<8} {format_time(s['time']):<12} {s['speedup']:.2f}x{'':<5} {s['efficiency']:.1f}%")
        lines.append("")
    
    # Failures
    if analysis.get("failures"):
        lines.extend(["FAILURES", "-" * 60])
        for f in analysis["failures"]:
            lines.append(f"  ✗ {f['name']}: exit {f['exit_code']} ({f['partition']}, {f['gres']})")
        lines.append("")
    
    # Recommendations
    if analysis.get("recommendations"):
        lines.extend(["RECOMMENDATIONS", "-" * 60])
        for rec in analysis["recommendations"]:
            lines.append(f"  • {rec}")
        lines.append("")
    
    # All results
    lines.extend([
        "ALL RESULTS",
        "-" * 60,
        f"  {'Name':<30} {'Part':<12} {'GPU':<10} {'Time':<10} {'Status'}"
    ])
    
    for r in sorted(results, key=lambda x: x.get("elapsed_seconds") or float('inf')):
        status = "✓" if is_success(r) else "✗"
        elapsed = r.get("elapsed_seconds", 0)
        time_str = format_time(elapsed) if elapsed else "N/A"
        gres = r.get("gres", "none") or "none"
        lines.append(f"  {r.get('name', '?'):<30} {r.get('partition', '?'):<12} {gres:<10} {time_str:<10} {status}")
    
    lines.append("=" * 80)
    
    report = "\n".join(lines)
    with open(output_file, 'w') as f:
        f.write(report)
    print(report)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="FACTS Workflow Benchmarking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick CPU test
  python facts_benchmark.py --run --quick

  # CPU scaling test
  python facts_benchmark.py --run --scaling

  # GPU benchmark
  python facts_benchmark.py --run --gpu

  # Quick GPU test
  python facts_benchmark.py --run --gpu-quick

  # CPU vs GPU comparison
  python facts_benchmark.py --run --compare

  # Check status
  python facts_benchmark.py --status --results-dir ./benchmark_xxx

  # Analyze results
  python facts_benchmark.py --analyze --results-dir ./benchmark_xxx
        """
    )
    
    p.add_argument("--run", action="store_true", help="Run benchmarks")
    p.add_argument("--status", action="store_true", help="Check job status")
    p.add_argument("--analyze", action="store_true", help="Analyze results")
    
    p.add_argument("--quick", action="store_true", help="Quick CPU test")
    p.add_argument("--scaling", action="store_true", help="CPU scaling test")
    p.add_argument("--gpu", action="store_true", help="GPU benchmarks")
    p.add_argument("--gpu-quick", action="store_true", help="Quick GPU test")
    p.add_argument("--compare", action="store_true", help="CPU vs GPU comparison")
    
    p.add_argument("--account", "-A", default="ilab", help="SLURM account")
    p.add_argument("--output-dir", "-o", help="Output directory")
    p.add_argument("--results-dir", help="Results directory for status/analyze")
    p.add_argument("--facts-script", default="./run_facts.py", help="Path to run_facts.py")
    
    return p.parse_args()


def main():
    args = parse_args()
    
    if args.status:
        if not args.results_dir:
            print("Need --results-dir")
            return 1
        check_benchmark_status(args.results_dir)
        return 0
    
    if args.analyze:
        if not args.results_dir:
            print("Need --results-dir")
            return 1
        
        print(f"Analyzing: {args.results_dir}")
        results = collect_results(args.results_dir)
        
        if not results:
            print("No results. Checking status...")
            check_benchmark_status(args.results_dir)
            return 1
        
        print(f"Found {len(results)} results\n")
        analysis = analyze_results(results)
        
        report_file = os.path.join(args.results_dir, "benchmark_report.txt")
        generate_report(results, analysis, report_file)
        
        with open(os.path.join(args.results_dir, "analysis.json"), 'w') as f:
            json.dump(analysis, f, indent=2)
        
        return 0
    
    if args.run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.abspath(args.output_dir or f"./benchmark_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)
        
        if args.quick:
            configs = generate_quick_configs(args.account)
        elif args.scaling:
            configs = generate_scaling_configs(args.account)
        elif args.gpu:
            configs = generate_gpu_configs(args.account)
        elif args.gpu_quick:
            configs = generate_gpu_quick_configs(args.account)
        elif args.compare:
            configs = generate_comparison_configs(args.account)
        else:
            configs = generate_default_configs(args.account)
        
        suite = BenchmarkSuite(
            name="benchmark",
            output_dir=output_dir,
            configs=configs,
            facts_script=os.path.abspath(args.facts_script)
        )
        
        submit_all_benchmarks(suite)
        print(f"\nCheck: python facts_benchmark.py --status --results-dir {output_dir}")
        print(f"Analyze: python facts_benchmark.py --analyze --results-dir {output_dir}")
        return 0
    
    print("Use --run, --status, or --analyze. See --help for options.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
