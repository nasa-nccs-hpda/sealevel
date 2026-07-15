#!/usr/bin/env python
"""
facts_benchmark.py - FACTS Workflow Benchmarking System

Supports external YAML configuration files for flexible benchmark definitions.

Usage:
    python facts_benchmark.py --run --config benchmark_config.yaml
    python facts_benchmark.py --status --results-dir ./benchmark_xxx
    python facts_benchmark.py --analyze --results-dir ./benchmark_xxx
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
from typing import Dict, List, Optional, Tuple, Any
import statistics

# Try to import yaml, provide fallback
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Warning: PyYAML not installed. Install with: pip install pyyaml")


# =============================================================================
# Data Classes
# =============================================================================

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
    phases: List[str] = field(default_factory=lambda: ["modules","modules2","fair","total"])
    constraint: Optional[str] = None
    qos: Optional[str] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class BenchmarkSuite:
    name: str
    output_dir: str
    configs: List[BenchmarkConfig]
    facts_script: str = "./run_facts.py"
    input_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/data/input"
    base_output_dir: str = "/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output"
    container_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/containers"
    description: str = ""
    author: str = ""


# =============================================================================
# Configuration File Parsing
# =============================================================================

def load_config_file(config_path: str) -> Tuple[BenchmarkSuite, List[BenchmarkConfig]]:
    """Load benchmark configuration from YAML file"""
    if not HAS_YAML:
        raise RuntimeError("PyYAML required. Install with: pip install pyyaml")
    
    with open(config_path, 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Global settings
    global_cfg = cfg.get('global', {})
    account = global_cfg.get('account', 'ilab')
    scenario = global_cfg.get('scenario', 'ssp585')
    default_phases = global_cfg.get('phases', ['modules','modules2','fair','total'])
    facts_script = global_cfg.get('facts_script', './run_facts.py')
    input_dir = global_cfg.get('input_dir', '/discover/nobackup/projects/sealevel/facts2.0/data/input')
    container_dir = global_cfg.get('container_dir', '/discover/nobackup/projects/sealevel/facts2.0/containers')
    
    configs = []
    
    # Parse explicit benchmarks
    for bench in cfg.get('benchmarks', []):
        config = BenchmarkConfig(
            name=bench['name'],
            partition=bench['partition'],
            account=bench.get('account', account),
            nodes=bench.get('nodes', 1),
            ntasks=bench.get('ntasks', 1),
            cpus=bench.get('cpus'),
            mem=bench.get('mem'),
            mem_per_cpu=bench.get('mem_per_cpu'),
            mem_per_gpu=bench.get('mem_per_gpu'),
            cpus_per_gpu=bench.get('cpus_per_gpu'),
            time=bench.get('time', '04:00:00'),
            gres=bench.get('gres'),
            nsamps=bench.get('nsamps', 20),
            scenario=bench.get('scenario', scenario),
            phases=bench.get('phases', default_phases),
            constraint=bench.get('constraint'),
            qos=bench.get('qos'),
            description=bench.get('description', ''),
            tags=bench.get('tags', [])
        )
        configs.append(config)
    
    # Parse range-based configurations
    ranges = cfg.get('ranges', {})
    
    # CPU scaling range
    if ranges.get('cpu_scaling', {}).get('enabled', False):
        r = ranges['cpu_scaling']
        for cpus in r.get('cpus', []):
            config = BenchmarkConfig(
                name=r.get('name_template', 'range_cpu_{cpus}').format(cpus=cpus),
                partition=r.get('partition', 'compute'),
                account=r.get('account', account),
                cpus=cpus,
                mem=r.get('mem', '64G'),
                time=r.get('time', '02:00:00'),
                nsamps=r.get('nsamps', 20),
                scenario=r.get('scenario', scenario),
                phases=r.get('phases', default_phases),
                description=r.get('description_template', 'CPU scaling: {cpus} cores').format(cpus=cpus),
                tags=r.get('tags', ['auto', 'cpu'])
            )
            configs.append(config)
    
    # GPU scaling range
    if ranges.get('gpu_scaling', {}).get('enabled', False):
        r = ranges['gpu_scaling']
        for ngpu in r.get('gres_range', []):
            config = BenchmarkConfig(
                name=r.get('name_template', 'range_gpu_{ngpu}').format(ngpu=ngpu),
                partition=r.get('partition', 'gpu_a100'),
                account=r.get('account', account),
                gres=f"gpu:{ngpu}",
                constraint=r.get('constraint', 'rome'),
                time=r.get('time', '02:00:00'),
                nsamps=r.get('nsamps', 20),
                scenario=r.get('scenario', scenario),
                phases=r.get('phases', default_phases),
                description=r.get('description_template', 'GPU scaling: {ngpu} GPUs').format(ngpu=ngpu, nsamps=r.get('nsamps', 20)),
                tags=r.get('tags', ['auto', 'gpu'])
            )
            configs.append(config)
    
    # Sample scaling range
    if ranges.get('sample_scaling', {}).get('enabled', False):
        r = ranges['sample_scaling']
        time_map = r.get('time_map', {})
        for nsamps in r.get('nsamps_range', []):
            time_val = time_map.get(nsamps, r.get('time', '02:00:00'))
            config = BenchmarkConfig(
                name=r.get('name_template', 'range_samps_{nsamps}').format(nsamps=nsamps),
                partition=r.get('partition', 'compute'),
                account=r.get('account', account),
                cpus=r.get('cpus', 16),
                mem=r.get('mem', '64G'),
                time=time_val,
                nsamps=nsamps,
                scenario=r.get('scenario', scenario),
                phases=r.get('phases', default_phases),
                description=r.get('description_template', 'Sample scaling: {nsamps} samples').format(nsamps=nsamps),
                tags=r.get('tags', ['auto', 'samples'])
            )
            configs.append(config)
    
    # Create suite
    suite = BenchmarkSuite(
        name=cfg.get('name', 'benchmark'),
        output_dir="",  # Will be set later
        configs=configs,
        facts_script=facts_script,
        input_dir=input_dir,
        container_dir=container_dir,
        description=cfg.get('description', ''),
        author=cfg.get('author', '')
    )
    
    return suite, configs


def generate_example_config(output_path: str):
    """Generate example configuration file"""
    example = '''# FACTS Benchmark Configuration
# ==============================

name: "My Benchmark Suite"
description: "Example benchmark configuration"
author: "username"

global:
  account: "ilab"
  scenario: "ssp585"
  phases: ["modules"]
  facts_script: "./run_facts.py"
  input_dir: "/discover/nobackup/projects/sealevel/facts2.0/data/input"
  container_dir: "/discover/nobackup/projects/sealevel/facts2.0/containers"

benchmarks:
  # CPU test
  - name: "cpu_test"
    partition: "compute"
    cpus: 16
    mem: "64G"
    time: "02:00:00"
    nsamps: 20
    description: "CPU baseline test"
    tags: ["cpu", "baseline"]

  # GPU test
  - name: "gpu_test"
    partition: "gpu_a100"
    gres: "gpu:1"
    constraint: "rome"
    time: "02:00:00"
    nsamps: 20
    description: "GPU baseline test"
    tags: ["gpu", "baseline"]

# Auto-generate range configurations
ranges:
  cpu_scaling:
    enabled: true
    partition: "compute"
    cpus: [4, 8, 16, 32]
    mem: "64G"
    time: "02:00:00"
    nsamps: 20
    name_template: "cpu_{cpus}"
    description_template: "CPU scaling: {cpus} cores"
    tags: ["cpu", "scaling"]

  gpu_scaling:
    enabled: false
    partition: "gpu_a100"
    gres_range: [1, 2]
    constraint: "rome"
    time: "02:00:00"
    nsamps: 20
    name_template: "gpu_{ngpu}"
    description_template: "GPU scaling: {ngpu} GPUs"
    tags: ["gpu", "scaling"]

  sample_scaling:
    enabled: false
    partition: "compute"
    cpus: 16
    mem: "64G"
    nsamps_range: [10, 20, 50]
    time_map:
      10: "01:00:00"
      20: "02:00:00"
      50: "04:00:00"
    name_template: "samps_{nsamps}"
    description_template: "Sample scaling: {nsamps} samples"
    tags: ["samples"]
'''
    
    with open(output_path, 'w') as f:
        f.write(example)
    
    print(f"Example configuration saved to: {output_path}")


# =============================================================================
# Built-in Configuration Generators
# =============================================================================

def generate_quick_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    return [
        BenchmarkConfig(
            name="quick_cpu",
            partition="compute",
            account=account,
            cpus=4,
            mem="16G",
            time="01:00:00",
            nsamps=5,
            description="Quick CPU test",
            tags=["quick", "cpu"]
        ),
        BenchmarkConfig(
            name="quick_gpu",
            partition="gpu_a100",
            account=account,
            gres="gpu:1",
            constraint="rome",
            time="01:00:00",
            nsamps=5,
            description="Quick GPU test",
            tags=["quick", "gpu"]
        ),
    ]


def generate_scaling_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    configs = []
    for cpus in [4, 8, 16, 32]:
        configs.append(BenchmarkConfig(
            name=f"scale_cpu{cpus}",
            partition="compute",
            account=account,
            cpus=cpus,
            mem="64G",
            time="02:00:00",
            nsamps=20,
            description=f"CPU scaling: {cpus} cores",
            tags=["scaling", "cpu"]
        ))
    return configs


def generate_gpu_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    configs = []
    for ngpu in [1, 2, 4]:
        configs.append(BenchmarkConfig(
            name=f"gpu_{ngpu}x_a100",
            partition="gpu_a100",
            account=account,
            gres=f"gpu:{ngpu}",
            constraint="rome",
            time="02:00:00",
            nsamps=20,
            description=f"{ngpu}x A100 GPU",
            tags=["gpu", "scaling"]
        ))
    return configs


def generate_full_configs(account: str = "ilab") -> List[BenchmarkConfig]:
    configs = []
    
    # CPU scaling
    for cpus in [4, 8, 16, 32]:
        configs.append(BenchmarkConfig(
            name=f"cpu_{cpus}",
            partition="compute",
            account=account,
            cpus=cpus,
            mem="64G",
            time="02:00:00",
            nsamps=20,
            description=f"CPU: {cpus} cores",
            tags=["cpu", "scaling"]
        ))
    
    # GPU scaling
    for ngpu in [1, 2, 4]:
        configs.append(BenchmarkConfig(
            name=f"gpu_{ngpu}",
            partition="gpu_a100",
            account=account,
            gres=f"gpu:{ngpu}",
            constraint="rome",
            time="02:00:00",
            nsamps=20,
            description=f"GPU: {ngpu}x A100",
            tags=["gpu", "scaling"]
        ))
    
    # Sample scaling
    for nsamps in [10, 20, 50]:
        configs.append(BenchmarkConfig(
            name=f"samps_{nsamps}",
            partition="compute",
            account=account,
            cpus=16,
            mem="64G",
            time="04:00:00" if nsamps > 20 else "02:00:00",
            nsamps=nsamps,
            description=f"Samples: {nsamps}",
            tags=["samples"]
        ))
    
    # Comparison
    configs.append(BenchmarkConfig(
        name="compare_cpu32",
        partition="compute",
        account=account,
        cpus=32,
        mem="128G",
        time="02:00:00",
        nsamps=20,
        description="Comparison: 32 CPUs",
        tags=["comparison", "cpu"]
    ))
    configs.append(BenchmarkConfig(
        name="compare_gpu1",
        partition="gpu_a100",
        account=account,
        gres="gpu:1",
        constraint="rome",
        time="02:00:00",
        nsamps=20,
        description="Comparison: 1 GPU",
        tags=["comparison", "gpu"]
    ))
    
    return configs


# =============================================================================
# SLURM Script Generation
# =============================================================================

def generate_slurm_script(config: BenchmarkConfig, suite: BenchmarkSuite, 
                          job_output_dir: str) -> str:
    job_output_dir = os.path.abspath(job_output_dir)
    facts_script = os.path.abspath(suite.facts_script)
    facts_output_dir = os.path.join(job_output_dir, "facts_output")
    log_file = os.path.join(job_output_dir, "facts.log")
    
    phases_str = " ".join(config.phases)
    phases_json = json.dumps(config.phases)
    tags_json = json.dumps(config.tags)
    
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
    is_gpu = config.gres is not None
    
    script = f'''{sbatch_header}

BENCH_DIR="{job_output_dir}"

echo "========================================"
echo "Benchmark: {config.name}"
echo "Description: {config.description}"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_JOB_NODELIST"
echo "Partition: {config.partition}"
'''
    
    if is_gpu:
        script += 'echo "GPUs: $CUDA_VISIBLE_DEVICES"\n'
    else:
        script += f'echo "CPUs: {config.cpus}"\n'
    
    script += f'''echo "Memory: {config.mem or 'default'}"
echo "Samples: {config.nsamps}"
echo "Start: $(date)"
echo "========================================"

BENCH_START=$(date +%s)

module load python/GEOSpyD/24.3.0-0/3.11
module load singularity/4.0.3
'''
    
    if is_gpu:
        script += '''module load cuda/11.8 2>/dev/null || true
nvidia-smi || echo "nvidia-smi not available"
'''
    
    script += f'''
export SINGULARITY_CACHEDIR="$BENCH_DIR/singularity_cache"
export SINGULARITY_TMPDIR="$BENCH_DIR/singularity_tmp"
export TMPDIR="$BENCH_DIR/tmp"
mkdir -p "$SINGULARITY_CACHEDIR" "$SINGULARITY_TMPDIR" "$TMPDIR"

export OMP_NUM_THREADS=${{SLURM_CPUS_PER_TASK:-${{SLURM_CPUS_ON_NODE:-1}}}}

cd "{job_output_dir}"

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
  "tags": {tags_json},
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
# Job Submission
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
    print(f"\n{'='*60}")
    print(f"FACTS Benchmark Suite: {suite.name}")
    if suite.description:
        print(f"Description: {suite.description}")
    print(f"Output: {suite.output_dir}")
    print(f"Total configurations: {len(suite.configs)}")
    print(f"{'='*60}\n")
    
    jobs = {}
    
    for i, config in enumerate(suite.configs, 1):
        tags_str = f" [{', '.join(config.tags)}]" if config.tags else ""
        print(f"[{i}/{len(suite.configs)}] {config.name}: {config.description}{tags_str}")
        
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
    
    # Save suite info
    suite_info = {
        "name": suite.name,
        "description": suite.description,
        "author": suite.author,
        "created": datetime.now().isoformat(),
        "total_configs": len(suite.configs),
        "output_dir": suite.output_dir
    }
    with open(os.path.join(suite.output_dir, "suite_info.json"), 'w') as f:
        json.dump(suite_info, f, indent=2)
    
    print(f"\n{'='*60}")
    submitted = sum(1 for j in jobs.values() if j["job_id"])
    print(f"Submitted: {submitted}/{len(suite.configs)}")
    print(f"{'='*60}")
    
    return jobs


# =============================================================================
# Status Checking
# =============================================================================

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
         '--format=JobID,State,ExitCode,Elapsed,MaxRSS,MaxVMSize,AveCPU'],
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
                    "max_vmsize": parts[5] if len(parts) > 5 else "",
                    "avg_cpu": parts[6] if len(parts) > 6 else ""
                }
    
    return {"state": "UNKNOWN"}


def check_benchmark_status(results_dir: str) -> None:
    jobs_file = os.path.join(results_dir, "jobs.json")
    
    if not os.path.exists(jobs_file):
        print(f"No jobs.json found in {results_dir}")
        return
    
    with open(jobs_file) as f:
        jobs = json.load(f)
    
    # Load suite info if available
    suite_info_file = os.path.join(results_dir, "suite_info.json")
    if os.path.exists(suite_info_file):
        with open(suite_info_file) as f:
            suite_info = json.load(f)
        print(f"\nBenchmark Suite: {suite_info.get('name', 'Unknown')}")
        if suite_info.get('description'):
            print(f"Description: {suite_info['description']}")
    
    print(f"\nResults Directory: {results_dir}")
    print("=" * 90)
    print(f"{'Name':<30} {'Job ID':<12} {'State':<12} {'Time':<12} {'MaxRSS':<12} {'Done'}")
    print("-" * 90)
    
    completed = 0
    running = 0
    pending = 0
    failed = 0
    
    for name, job in jobs.items():
        job_id = job.get("job_id", "N/A")
        
        if job_id and job_id != "N/A":
            status = get_job_status(job_id)
            state = status.get("state", "UNKNOWN")
            elapsed = status.get("elapsed", status.get("time", ""))
            max_rss = status.get("max_rss", "")
        else:
            state = "SUBMIT_FAILED"
            elapsed = ""
            max_rss = ""
        
        result_file = os.path.join(job["output_dir"], "benchmark_result.json")
        has_result = "✓" if os.path.exists(result_file) else ""
        
        # Count states
        if state == "COMPLETED":
            completed += 1
        elif state == "RUNNING":
            running += 1
        elif state in ["PENDING", "CONFIGURING"]:
            pending += 1
        elif state in ["FAILED", "CANCELLED", "TIMEOUT", "SUBMIT_FAILED"]:
            failed += 1

        # Convert None to empty strings to prevent the formatting crash
        safe_name = str(name) if name is not None else "Unknown"
        safe_job_id = str(job_id) if job_id is not None else "N/A"
        safe_state = str(state) if state is not None else "UNKNOWN"
        safe_elapsed = str(elapsed) if elapsed is not None else ""
        safe_max_rss = str(max_rss) if max_rss is not None else ""
        safe_has_result = str(has_result) if has_result is not None else ""

        print(f"{safe_name:<30} {safe_job_id:<12} {safe_state:<12} {safe_elapsed:<12} {safe_max_rss:<12} {safe_has_result}")
        
    print("=" * 90)
    print(f"Summary: {completed} completed, {running} running, {pending} pending, {failed} failed")
    print(f"Total: {len(jobs)} jobs")


# =============================================================================
# Analysis and Reporting
# =============================================================================

def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


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


def collect_results(suite_dir: str) -> List[dict]:
    results = []
    suite_path = Path(suite_dir)
    
    for result_file in suite_path.glob("*/benchmark_result.json"):
        try:
            with open(result_file) as f:
                content = f.read()
                # Handle shell variable substitution in JSON
                content = content.replace("'$SLURM_JOB_ID'", '"$SLURM_JOB_ID"')
                result = json.loads(content)
            
            config_file = result_file.parent / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    result["config"] = json.load(f)
            
            # Get additional SLURM stats
            job_id = str(result.get("job_id", "")).strip("'\"")
            if job_id and job_id != "$SLURM_JOB_ID":
                status = get_job_status(job_id)
                result["slurm_stats"] = status
            
            result["output_dir"] = str(result_file.parent)
            results.append(result)
        except Exception as e:
            print(f"Warning: Failed to load {result_file}: {e}")
    
    return results


def analyze_results(results: List[dict]) -> dict:
    """Comprehensive analysis with statistics and recommendations"""
    if not results:
        return {"error": "No results", "summary": {"total_runs": 0}}
    
    def is_success(r):
        ec = r.get("exit_code")
        if isinstance(ec, str):
            ec = ec.split(':')[0] if ':' in str(ec) else ec
        try:
            return int(ec) == 0
        except:
            return False
    
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
        "by_gpus": {},
        "by_memory": {},
        "by_nsamps": {},
        "by_tags": {},
        "scaling": {
            "cpu": [],
            "gpu": [],
            "samples": []
        },
        "comparison": {
            "cpu_vs_gpu": []
        },
        "failures": [],
        "statistics": {},
        "recommendations": []
    }
    
    # Timing statistics
    if successful:
        times = [r.get("elapsed_seconds", 0) for r in successful if r.get("elapsed_seconds")]
        if times:
            analysis["timing"] = {
                "min": min(times),
                "max": max(times),
                "avg": sum(times) / len(times),
                "median": statistics.median(times),
                "stdev": statistics.stdev(times) if len(times) > 1 else 0,
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
                "max_time": max(times),
                "median_time": statistics.median(times)
            }
    
    # By CPUs (for CPU jobs)
    cpu_results = [r for r in successful if r.get("gres") in [None, "none", ""]]
    cpu_values = set()
    for r in cpu_results:
        cpus = r.get("cpus")
        if cpus and cpus not in ["default", "unknown"]:
            try:
                cpu_values.add(int(cpus))
            except:
                pass
    
    for cpus in sorted(cpu_values):
        cpu_res = [r for r in cpu_results if str(r.get("cpus")) == str(cpus)]
        times = [r.get("elapsed_seconds", 0) for r in cpu_res if r.get("elapsed_seconds")]
        if times:
            analysis["by_cpus"][str(cpus)] = {
                "count": len(cpu_res),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times)
            }
    
    # By GPUs
    gpu_results = [r for r in successful if r.get("gres") and r.get("gres") != "none"]
    for r in gpu_results:
        gres = r.get("gres", "")
        if gres and "gpu:" in gres:
            try:
                ngpu = int(gres.split(":")[1])
                if str(ngpu) not in analysis["by_gpus"]:
                    analysis["by_gpus"][str(ngpu)] = {"count": 0, "times": []}
                analysis["by_gpus"][str(ngpu)]["count"] += 1
                if r.get("elapsed_seconds"):
                    analysis["by_gpus"][str(ngpu)]["times"].append(r["elapsed_seconds"])
            except:
                pass
    
    for ngpu, data in analysis["by_gpus"].items():
        if data["times"]:
            data["avg_time"] = sum(data["times"]) / len(data["times"])
            data["min_time"] = min(data["times"])
            data["max_time"] = max(data["times"])
        del data["times"]
    
    # By sample count
    nsamps_values = set(r.get("nsamps") for r in successful if r.get("nsamps"))
    for nsamps in sorted(nsamps_values):
        nsamp_res = [r for r in successful if r.get("nsamps") == nsamps]
        times = [r.get("elapsed_seconds", 0) for r in nsamp_res if r.get("elapsed_seconds")]
        if times:
            analysis["by_nsamps"][str(nsamps)] = {
                "count": len(nsamp_res),
                "avg_time": sum(times) / len(times),
                "time_per_sample": (sum(times) / len(times)) / nsamps
            }
    
    # By tags
    all_tags = set()
    for r in successful:
        tags = r.get("tags", [])
        if isinstance(tags, list):
            all_tags.update(tags)
    
    for tag in all_tags:
        tag_res = [r for r in successful if tag in r.get("tags", [])]
        times = [r.get("elapsed_seconds", 0) for r in tag_res if r.get("elapsed_seconds")]
        if times:
            analysis["by_tags"][tag] = {
                "count": len(tag_res),
                "avg_time": sum(times) / len(times)
            }
    
    # CPU Scaling analysis
    if len(analysis["by_cpus"]) >= 2:
        cpu_data = [(int(k), v["avg_time"]) for k, v in analysis["by_cpus"].items()]
        cpu_data.sort()
        base_cpus, base_time = cpu_data[0]
        
        for cpus, t in cpu_data:
            speedup = base_time / t if t > 0 else 0
            ideal = cpus / base_cpus
            efficiency = (speedup / ideal * 100) if ideal > 0 else 0
            analysis["scaling"]["cpu"].append({
                "cpus": cpus,
                "time": round(t, 1),
                "speedup": round(speedup, 2),
                "ideal_speedup": round(ideal, 2),
                "efficiency": round(efficiency, 1)
            })
    
    # GPU Scaling analysis
    if len(analysis["by_gpus"]) >= 2:
        gpu_data = [(int(k), v["avg_time"]) for k, v in analysis["by_gpus"].items()]
        gpu_data.sort()
        base_gpu, base_time = gpu_data[0]
        
        for ngpu, t in gpu_data:
            speedup = base_time / t if t > 0 else 0
            ideal = ngpu / base_gpu
            efficiency = (speedup / ideal * 100) if ideal > 0 else 0
            analysis["scaling"]["gpu"].append({
                "gpus": ngpu,
                "time": round(t, 1),
                "speedup": round(speedup, 2),
                "ideal_speedup": round(ideal, 2),
                "efficiency": round(efficiency, 1)
            })
    
    # Sample scaling analysis
    if len(analysis["by_nsamps"]) >= 2:
        samp_data = [(int(k), v["avg_time"], v["time_per_sample"]) for k, v in analysis["by_nsamps"].items()]
        samp_data.sort()
        
        for nsamps, t, tps in samp_data:
            analysis["scaling"]["samples"].append({
                "samples": nsamps,
                "total_time": round(t, 1),
                "time_per_sample": round(tps, 2)
            })
    
    # CPU vs GPU comparison
    cpu_times = {int(k): v["avg_time"] for k, v in analysis["by_cpus"].items()}
    gpu_times = {int(k): v["avg_time"] for k, v in analysis["by_gpus"].items()}
    
    if cpu_times and gpu_times:
        # Find best CPU and GPU times
        best_cpu_cores, best_cpu_time = min(cpu_times.items(), key=lambda x: x[1])
        best_gpu_count, best_gpu_time = min(gpu_times.items(), key=lambda x: x[1])
        
        analysis["comparison"]["cpu_vs_gpu"] = {
            "best_cpu": {
                "cores": best_cpu_cores,
                "time": round(best_cpu_time, 1)
            },
            "best_gpu": {
                "gpus": best_gpu_count,
                "time": round(best_gpu_time, 1)
            },
            "gpu_speedup": round(best_cpu_time / best_gpu_time, 2) if best_gpu_time > 0 else 0
        }
    
    # Failures
    for r in failed:
        analysis["failures"].append({
            "name": r.get("name"),
            "exit_code": r.get("exit_code"),
            "partition": r.get("partition"),
            "gres": r.get("gres"),
            "description": r.get("description", "")
        })
    
    # Generate recommendations
    recommendations = []
    
    # Fastest configuration
    if successful:
        fastest = min(successful, key=lambda r: r.get("elapsed_seconds") or float('inf'))
        if fastest.get("elapsed_seconds"):
            recommendations.append({
                "type": "fastest",
                "priority": "high",
                "message": f"Fastest configuration: {fastest.get('name')} ({format_time(fastest['elapsed_seconds'])})",
                "config": {
                    "partition": fastest.get("partition"),
                    "cpus": fastest.get("cpus"),
                    "gres": fastest.get("gres"),
                    "nsamps": fastest.get("nsamps")
                }
            })
    
    # CPU scaling efficiency
    if analysis["scaling"]["cpu"]:
        last_cpu = analysis["scaling"]["cpu"][-1]
        if last_cpu["efficiency"] < 50:
            recommendations.append({
                "type": "cpu_scaling",
                "priority": "medium",
                "message": f"CPU scaling efficiency drops to {last_cpu['efficiency']:.0f}% at {last_cpu['cpus']} cores. Consider using fewer CPUs for better resource efficiency.",
                "suggestion": f"Optimal CPU count appears to be around {analysis['scaling']['cpu'][len(analysis['scaling']['cpu'])//2]['cpus']} cores"
            })
        elif last_cpu["efficiency"] > 80:
            recommendations.append({
                "type": "cpu_scaling",
                "priority": "low",
                "message": f"Good CPU scaling efficiency ({last_cpu['efficiency']:.0f}%). Workload may benefit from even more CPUs."
            })
    
    # GPU recommendations
    if analysis["comparison"].get("cpu_vs_gpu"):
        comp = analysis["comparison"]["cpu_vs_gpu"]
        if comp["gpu_speedup"] > 1.5:
            recommendations.append({
                "type": "gpu",
                "priority": "high",
                "message": f"GPU provides {comp['gpu_speedup']:.1f}x speedup over best CPU configuration. Recommend using GPU for production runs."
            })
        elif comp["gpu_speedup"] < 1:
            recommendations.append({
                "type": "gpu",
                "priority": "medium",
                "message": f"CPU ({comp['best_cpu']['cores']} cores) is faster than GPU. Consider using CPU partition for this workload."
            })
    
    # Sample scaling
    if analysis["scaling"]["samples"]:
        first_tps = analysis["scaling"]["samples"][0]["time_per_sample"]
        last_tps = analysis["scaling"]["samples"][-1]["time_per_sample"]
        if last_tps < first_tps * 0.8:
            recommendations.append({
                "type": "samples",
                "priority": "medium",
                "message": "Time per sample decreases with larger batch sizes. Consider running larger sample counts for better efficiency."
            })
    
    # Cost efficiency (rough estimate)
    if cpu_times and gpu_times:
        # Assume GPU costs ~3x CPU per hour
        best_cpu_cost = best_cpu_time * best_cpu_cores  # CPU-seconds
        best_gpu_cost = best_gpu_time * best_gpu_count * 3  # GPU-seconds (weighted)
        
        if best_cpu_cost < best_gpu_cost:
            recommendations.append({
                "type": "cost",
                "priority": "low",
                "message": "CPU may be more cost-effective for this workload size."
            })
        else:
            recommendations.append({
                "type": "cost",
                "priority": "low",
                "message": "GPU is likely more cost-effective due to faster completion."
            })
    
    analysis["recommendations"] = recommendations
    
    return analysis


def generate_report(results: List[dict], analysis: dict, output_file: str):
    """Generate comprehensive text report"""
    
    def is_success(r):
        ec = r.get("exit_code")
        if isinstance(ec, str):
            ec = ec.split(':')[0] if ':' in str(ec) else ec
        try:
            return int(ec) == 0
        except:
            return False
    
    lines = [
        "=" * 80,
        "FACTS WORKFLOW BENCHMARK REPORT",
        "=" * 80,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Results Directory: {os.path.dirname(output_file)}",
        "",
    ]
    
    # Executive Summary
    lines.extend([
        "EXECUTIVE SUMMARY",
        "-" * 60,
        f"  Total benchmark runs:     {analysis['summary']['total_runs']}",
        f"  Successful:               {analysis['summary']['successful']}",
        f"  Failed:                   {analysis['summary']['failed']}",
        f"  Success rate:             {analysis['summary']['success_rate']:.1f}%",
    ])
    
    if analysis.get("timing"):
        t = analysis["timing"]
        lines.extend([
            "",
            f"  Fastest run:              {format_time(t['min'])}",
            f"  Slowest run:              {format_time(t['max'])}",
            f"  Average time:             {format_time(t['avg'])}",
            f"  Median time:              {format_time(t['median'])}",
            f"  Std deviation:            {format_time(t['stdev'])}",
            f"  Total compute time:       {format_time(t['total'])}",
        ])
    
    lines.append("")
    
    # Recommendations (high priority first)
    if analysis.get("recommendations"):
        lines.extend([
            "KEY RECOMMENDATIONS",
            "-" * 60,
        ])
        
        sorted_recs = sorted(analysis["recommendations"], 
                            key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 3))
        
        for i, rec in enumerate(sorted_recs, 1):
            priority = rec.get("priority", "").upper()
            lines.append(f"  [{priority}] {rec['message']}")
            if rec.get("suggestion"):
                lines.append(f"         → {rec['suggestion']}")
        
        lines.append("")
    
    # CPU vs GPU Comparison
    if analysis.get("comparison", {}).get("cpu_vs_gpu"):
        comp = analysis["comparison"]["cpu_vs_gpu"]
        lines.extend([
            "CPU VS GPU COMPARISON",
            "-" * 60,
            f"  Best CPU:    {comp['best_cpu']['cores']} cores @ {format_time(comp['best_cpu']['time'])}",
            f"  Best GPU:    {comp['best_gpu']['gpus']} GPU(s) @ {format_time(comp['best_gpu']['time'])}",
            f"  GPU Speedup: {comp['gpu_speedup']:.2f}x",
            ""
        ])
    
    # CPU Scaling
    if analysis.get("scaling", {}).get("cpu"):
        lines.extend([
            "CPU SCALING ANALYSIS",
            "-" * 60,
            f"  {'CPUs':<8} {'Time':<12} {'Speedup':<10} {'Ideal':<10} {'Efficiency'}",
        ])
        for s in analysis["scaling"]["cpu"]:
            lines.append(
                f"  {s['cpus']:<8} {format_time(s['time']):<12} "
                f"{s['speedup']:.2f}x{'':<5} {s['ideal_speedup']:.2f}x{'':<5} "
                f"{s['efficiency']:.1f}%"
            )
        lines.append("")
    
    # GPU Scaling
    if analysis.get("scaling", {}).get("gpu"):
        lines.extend([
            "GPU SCALING ANALYSIS",
            "-" * 60,
            f"  {'GPUs':<8} {'Time':<12} {'Speedup':<10} {'Ideal':<10} {'Efficiency'}",
        ])
        for s in analysis["scaling"]["gpu"]:
            lines.append(
                f"  {s['gpus']:<8} {format_time(s['time']):<12} "
                f"{s['speedup']:.2f}x{'':<5} {s['ideal_speedup']:.2f}x{'':<5} "
                f"{s['efficiency']:.1f}%"
            )
        lines.append("")
    
    # Sample Scaling
    if analysis.get("scaling", {}).get("samples"):
        lines.extend([
            "SAMPLE COUNT SCALING",
            "-" * 60,
            f"  {'Samples':<10} {'Total Time':<15} {'Time/Sample'}",
        ])
        for s in analysis["scaling"]["samples"]:
            lines.append(
                f"  {s['samples']:<10} {format_time(s['total_time']):<15} "
                f"{s['time_per_sample']:.2f}s"
            )
        lines.append("")
    
    # By Partition
    if analysis.get("by_partition"):
        lines.extend([
            "RESULTS BY PARTITION",
            "-" * 60,
        ])
        for part, stats in analysis["by_partition"].items():
            lines.append(
                f"  {part:<15} {stats['count']:>3} runs  "
                f"avg: {format_time(stats['avg_time']):<10} "
                f"range: {format_time(stats['min_time'])}-{format_time(stats['max_time'])}"
            )
        lines.append("")
    
    # By Tags
    if analysis.get("by_tags"):
        lines.extend([
            "RESULTS BY TAG",
            "-" * 60,
        ])
        for tag, stats in sorted(analysis["by_tags"].items()):
            lines.append(f"  {tag:<20} {stats['count']:>3} runs  avg: {format_time(stats['avg_time'])}")
        lines.append("")
    
    # Failures
    if analysis.get("failures"):
        lines.extend([
            "FAILED RUNS",
            "-" * 60,
        ])
        for f in analysis["failures"]:
            gres = f.get("gres", "none")
            lines.append(
                f"  ✗ {f['name']:<25} exit: {f['exit_code']:<8} "
                f"partition: {f['partition']:<12} gres: {gres}"
            )
        lines.append("")
    
    # Detailed Results Table
    lines.extend([
        "DETAILED RESULTS",
        "-" * 60,
        f"  {'Name':<28} {'Part':<10} {'CPUs':<6} {'GPU':<8} {'Samps':<6} {'Time':<10} {'OK'}",
    ])
    
    for r in sorted(results, key=lambda x: x.get("elapsed_seconds") or float('inf')):
        status = "✓" if is_success(r) else "✗"
        elapsed = r.get("elapsed_seconds", 0)
        time_str = format_time(elapsed) if elapsed else "N/A"
        gres = r.get("gres", "") or ""
        cpus = str(r.get("cpus", "")) or "-"
        
        lines.append(
            f"  {r.get('name', '?'):<28} {r.get('partition', '?'):<10} "
            f"{cpus:<6} {gres:<8} {r.get('nsamps', '?'):<6} {time_str:<10} {status}"
        )
    
    lines.extend(["", "=" * 80])
    
    report = "\n".join(lines)
    
    with open(output_file, 'w') as f:
        f.write(report)
    
    print(report)
    return report


def generate_markdown_report(results: List[dict], analysis: dict, output_file: str):
    """Generate markdown report"""
    
    def is_success(r):
        ec = r.get("exit_code")
        if isinstance(ec, str):
            ec = ec.split(':')[0] if ':' in str(ec) else ec
        try:
            return int(ec) == 0
        except:
            return False
    
    lines = [
        "# FACTS Workflow Benchmark Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Runs | {analysis['summary']['total_runs']} |",
        f"| Successful | {analysis['summary']['successful']} |",
        f"| Failed | {analysis['summary']['failed']} |",
        f"| Success Rate | {analysis['summary']['success_rate']:.1f}% |",
    ]
    
    if analysis.get("timing"):
        t = analysis["timing"]
        lines.extend([
            f"| Fastest | {format_time(t['min'])} |",
            f"| Slowest | {format_time(t['max'])} |",
            f"| Average | {format_time(t['avg'])} |",
            f"| Median | {format_time(t['median'])} |",
        ])
    
    lines.append("")
    
    # Recommendations
    if analysis.get("recommendations"):
        lines.extend(["## Recommendations", ""])
        
        for rec in sorted(analysis["recommendations"], 
                         key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 3)):
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.get("priority", ""), "⚪")
            lines.append(f"- {priority_emoji} **{rec.get('priority', '').upper()}**: {rec['message']}")
        
        lines.append("")
    
    # CPU vs GPU
    if analysis.get("comparison", {}).get("cpu_vs_gpu"):
        comp = analysis["comparison"]["cpu_vs_gpu"]
        lines.extend([
            "## CPU vs GPU Comparison",
            "",
            "| Config | Time |",
            "|--------|------|",
            f"| Best CPU ({comp['best_cpu']['cores']} cores) | {format_time(comp['best_cpu']['time'])} |",
            f"| Best GPU ({comp['best_gpu']['gpus']} GPU) | {format_time(comp['best_gpu']['time'])} |",
            f"| **GPU Speedup** | **{comp['gpu_speedup']:.2f}x** |",
            ""
        ])
    
    # Scaling tables
    if analysis.get("scaling", {}).get("cpu"):
        lines.extend([
            "## CPU Scaling",
            "",
            "| CPUs | Time | Speedup | Efficiency |",
            "|------|------|---------|------------|",
        ])
        for s in analysis["scaling"]["cpu"]:
            lines.append(f"| {s['cpus']} | {format_time(s['time'])} | {s['speedup']:.2f}x | {s['efficiency']:.1f}% |")
        lines.append("")
    
    if analysis.get("scaling", {}).get("gpu"):
        lines.extend([
            "## GPU Scaling",
            "",
            "| GPUs | Time | Speedup | Efficiency |",
            "|------|------|---------|------------|",
        ])
        for s in analysis["scaling"]["gpu"]:
            lines.append(f"| {s['gpus']} | {format_time(s['time'])} | {s['speedup']:.2f}x | {s['efficiency']:.1f}% |")
        lines.append("")
    
    # All results
    lines.extend([
        "## All Results",
        "",
        "| Name | Partition | CPUs | GPU | Samples | Time | Status |",
        "|------|-----------|------|-----|---------|------|--------|",
    ])
    
    for r in sorted(results, key=lambda x: x.get("elapsed_seconds") or float('inf')):
        status = "✅" if is_success(r) else "❌"
        elapsed = r.get("elapsed_seconds", 0)
        time_str = format_time(elapsed) if elapsed else "N/A"
        gres = r.get("gres", "-") or "-"
        cpus = r.get("cpus", "-") or "-"
        
        lines.append(
            f"| {r.get('name', '?')} | {r.get('partition', '?')} | "
            f"{cpus} | {gres} | {r.get('nsamps', '?')} | {time_str} | {status} |"
        )
    
    report = "\n".join(lines)
    
    with open(output_file, 'w') as f:
        f.write(report)
    
    return report


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="FACTS Workflow Benchmarking System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run from config file
  python facts_benchmark.py --run --config benchmark_config.yaml

  # Quick test
  python facts_benchmark.py --run --quick

  # CPU scaling
  python facts_benchmark.py --run --scaling

  # GPU benchmarks
  python facts_benchmark.py --run --gpu

  # Full suite
  python facts_benchmark.py --run --full

  # Check status
  python facts_benchmark.py --status --results-dir ./benchmark_xxx

  # Analyze and generate report
  python facts_benchmark.py --analyze --results-dir ./benchmark_xxx

  # Generate example config
  python facts_benchmark.py --generate-config
        """
    )
    
    p.add_argument("--run", action="store_true", help="Run benchmarks")
    p.add_argument("--status", action="store_true", help="Check job status")
    p.add_argument("--analyze", action="store_true", help="Analyze results")
    p.add_argument("--generate-config", action="store_true", help="Generate example config file")
    
    # Config options
    p.add_argument("--config", "-c", help="YAML configuration file")
    p.add_argument("--quick", action="store_true", help="Quick test (CPU + GPU)")
    p.add_argument("--scaling", action="store_true", help="CPU scaling test")
    p.add_argument("--gpu", action="store_true", help="GPU benchmarks")
    p.add_argument("--full", action="store_true", help="Full benchmark suite")
    
    p.add_argument("--account", "-A", default="ilab", help="SLURM account")
    p.add_argument("--output-dir", "-o", help="Output directory")
    p.add_argument("--results-dir", help="Results directory for status/analyze")
    p.add_argument("--facts-script", default="./run_facts.py", help="Path to run_facts.py")
    
    return p.parse_args()


def main():
    args = parse_args()
    
    # Generate example config
    if args.generate_config:
        generate_example_config("benchmark_config.yaml")
        return 0
    
    # Check status
    if args.status:
        if not args.results_dir:
            print("Error: --results-dir required")
            return 1
        check_benchmark_status(args.results_dir)
        return 0
    
    # Analyze results
    if args.analyze:
        if not args.results_dir:
            print("Error: --results-dir required")
            return 1
        
        print(f"Analyzing: {args.results_dir}")
        results = collect_results(args.results_dir)
        
        if not results:
            print("\nNo completed results found. Checking status...")
            check_benchmark_status(args.results_dir)
            return 1
        
        print(f"Found {len(results)} results\n")
        
        analysis = analyze_results(results)
        
        # Generate reports
        report_txt = os.path.join(args.results_dir, "benchmark_report.txt")
        report_md = os.path.join(args.results_dir, "benchmark_report.md")
        analysis_json = os.path.join(args.results_dir, "analysis.json")
        
        generate_report(results, analysis, report_txt)
        generate_markdown_report(results, analysis, report_md)
        
        with open(analysis_json, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"\nReports saved:")
        print(f"  Text:     {report_txt}")
        print(f"  Markdown: {report_md}")
        print(f"  JSON:     {analysis_json}")
        
        return 0
    
    # Run benchmarks
    if args.run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.abspath(args.output_dir or f"./benchmark_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)
        
        # Load configuration
        if args.config:
            if not HAS_YAML:
                print("Error: PyYAML required for config files. Install with: pip install pyyaml")
                return 1
            suite, configs = load_config_file(args.config)
            suite.output_dir = output_dir
        elif args.quick:
            configs = generate_quick_configs(args.account)
            suite = BenchmarkSuite(name="quick", output_dir=output_dir, configs=configs,
                                  facts_script=os.path.abspath(args.facts_script))
        elif args.scaling:
            configs = generate_scaling_configs(args.account)
            suite = BenchmarkSuite(name="scaling", output_dir=output_dir, configs=configs,
                                  facts_script=os.path.abspath(args.facts_script))
        elif args.gpu:
            configs = generate_gpu_configs(args.account)
            suite = BenchmarkSuite(name="gpu", output_dir=output_dir, configs=configs,
                                  facts_script=os.path.abspath(args.facts_script))
        elif args.full:
            configs = generate_full_configs(args.account)
            suite = BenchmarkSuite(name="full", output_dir=output_dir, configs=configs,
                                  facts_script=os.path.abspath(args.facts_script))
        else:
            configs = generate_quick_configs(args.account)
            suite = BenchmarkSuite(name="default", output_dir=output_dir, configs=configs,
                                  facts_script=os.path.abspath(args.facts_script))
        
        submit_all_benchmarks(suite)
        
        print(f"\nCommands:")
        print(f"  Check status:  python facts_benchmark.py --status --results-dir {output_dir}")
        print(f"  Analyze:       python facts_benchmark.py --analyze --results-dir {output_dir}")
        
        return 0
    
    print("Use --run, --status, --analyze, or --generate-config")
    print("Run with --help for more options")
    return 1


if __name__ == "__main__":
    sys.exit(main())
