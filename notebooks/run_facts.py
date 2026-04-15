#!/usr/bin/env python
"""
run_facts.py - FACTS Workflow Execution Script
"""

import argparse
import asyncio
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# =============================================================================
# Logging
# =============================================================================

def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode='w'))
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    return logging.getLogger(__name__)


# =============================================================================
# Data Classes (MUST BE DEFINED BEFORE FUNCTIONS THAT USE THEM)
# =============================================================================

class TaskState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TaskResult:
    name: str
    state: TaskState
    exit_code: int
    elapsed: float
    stdout: str = ""
    stderr: str = ""


@dataclass
class Config:
    # Paths
    input_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/data/input"
    output_dir: str = "/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output"
    container_dir: str = "/discover/nobackup/projects/sealevel/facts2.0/containers"
    singularity: str = "/usr/local/other/singularity/4.0.3/bin/singularity"
    
    # Workflow parameters
    nsamps: int = 20
    scenario: str = "ssp585"
    pipeline_id: str = "1234"
    phases: List[str] = field(default_factory=lambda: ["modules", "modules2", "total"])
    dry_run: bool = False
    verbose: bool = False


# =============================================================================
# Directory Setup
# =============================================================================

def create_directories(cfg: Config):
    """Create all required output directories"""
    base = cfg.output_dir
    subdirs = ['fair', 'lws', 'sterodynamics', 'bamber', 
               'ipccar5_glaciers', 'ipccar5_icesheets', 'kopp14verticallandmotion']
    
    os.makedirs(base, exist_ok=True)
    for sub in subdirs:
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    
    # Also create ./data/output structure for total tasks
    os.makedirs('./data/output/lws', exist_ok=True)
    os.makedirs('./data/output/sterodynamics', exist_ok=True)


# =============================================================================
# Task Execution
# =============================================================================

async def run_task(name: str, cmd: List[str], dry_run: bool = False, 
                   logger: logging.Logger = None) -> TaskResult:
    if logger is None:
        logger = logging.getLogger(__name__)
    
    cmd_str = shlex.join(cmd)
    logger.info(f"[{name}] Starting...")
    logger.debug(f"[{name}] {cmd_str}")
    
    if dry_run:
        logger.info(f"[{name}] DRY RUN")
        return TaskResult(name, TaskState.COMPLETED, 0, 0.0)
    
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        elapsed = time.time() - start
        
        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')
        
        if proc.returncode == 0:
            logger.info(f"[{name}] COMPLETED in {elapsed:.1f}s")
            return TaskResult(name, TaskState.COMPLETED, 0, elapsed, stdout_str, stderr_str)
        else:
            logger.error(f"[{name}] FAILED (exit={proc.returncode})")
            if stderr_str:
                logger.error(f"[{name}] STDERR: {stderr_str[:500]}")
            if stdout_str:
                logger.error(f"[{name}] STDOUT: {stdout_str[:500]}")
            return TaskResult(name, TaskState.FAILED, proc.returncode, elapsed, stdout_str, stderr_str)
    except Exception as e:
        logger.error(f"[{name}] EXCEPTION: {e}")
        return TaskResult(name, TaskState.FAILED, -1, time.time() - start, "", str(e))


# =============================================================================
# Command Builders
# =============================================================================

def build_commands(cfg: Config) -> Dict[str, List[str]]:
    """Build all singularity commands"""
    s = cfg.singularity
    i = cfg.input_dir
    o = cfg.output_dir
    c = cfg.container_dir
    
    cmds = {}
    
    # FAIR
    cmds['fair'] = [
        s, 'exec',
        '--bind', f'{i}:/input',
        '--bind', f'{o}/fair:/output',
        f'{c}/fair-temperature.sif',
        'fair-temperature',
        f'--pipeline-id={cfg.pipeline_id}',
        f'--nsamps={cfg.nsamps}',
        '--output-oceantemp-file=/output/oceantemp.nc',
        '--output-ohc-file=/output/ohc.nc',
        '--output-gsat-file=/output/gsat.nc',
        '--output-climate-file=/output/climate.nc',
        '--rcmip-file=/input/rcmip/rcmip-emissions-annual-means-v5-1-0.csv',
        '--param-file=/input/parameters/fair_ar6_climate_params_v4.0.nc'
    ]
    
    # LWS
    cmds['lws'] = [
        s, 'exec',
        '--bind', f'{i}:/input',
        '--bind', f'{o}/lws:/output',
        f'{c}/ssp-landwaterstorage.sif',
        'ssp-landwaterstorage',
        f'--pipeline-id={cfg.pipeline_id}',
        f'--nsamps={cfg.nsamps}',
        '--output-gslr-file=/output/gslr.nc',
        '--output-lslr-file=/output/lslr.nc',
        '--location-file=/input/location.lst',
        '--pophist-file=/input/UNWPP2012 population historical.csv',
        '--reservoir-file=/input/Chao2008 groundwater impoundment.csv',
        '--popscen-file=/input/ssp_iam_baseline_popscenarios2100.csv',
        '--gwd-file=/input/Konikow2011 GWD.csv',
        '--gwd-file=/input/Wada2012 GWD.csv',
        '--gwd-file=/input/Pokhrel2012 GWD.csv',
        '--fp-file=/input/REL_GROUNDWATER_NOMASK.nc'
    ]
    
    # Sterodynamics
    cmds['sterodynamics'] = [
        s, 'exec',
        '--bind', f'{i}:/input',
        '--bind', f'{o}/fair:/fair',
        '--bind', f'{o}/sterodynamics:/output',
        '--nv',
        f'{c}/tlm-sterodynamics.sif',
        'tlm-sterodynamics',
        f'--pipeline-id={cfg.pipeline_id}',
        f'--scenario={cfg.scenario}',
        f'--nsamps={cfg.nsamps}',
        '--model-dir=/input/cmip6/',
        '--location-file=/input/location.lst',
        '--output-lslr-file=/output/lslr.nc',
        '--output-gslr-file=/output/gslr.nc',
        '--expansion-coefficients-file=/input/scmpy2LM_RCMIP_CMIP6calpm_n18_expcoefs.nc',
        '--gsat-rmses-file=/input/scmpy2LM_RCMIP_CMIP6calpm_n17_gsat_rmse.nc',
        '--climate-data-file=/fair/climate.nc'
    ]
    
    # Kopp14
    cmds['kopp14'] = [
        s, 'exec',
        '--bind', f'{i}:/mnt/data_in:ro',
        '--bind', f'{o}/kopp14verticallandmotion:/mnt/data_out',
        '--nv',
        f'{c}/kopp14-verticallandmotion.sif',
        'kopp14-verticallandmotion',
        '--pipeline-id=5678',
        '--rate-file=/mnt/data_in/bkgdrate-210306.tsv',
        '--location-file=/mnt/data_in/location.lst',
        '--output-lslr-file=/mnt/data_out/localsl.nc'
    ]
    
    # IPCCAR5 Glaciers
    cmds['ipccar5_glaciers'] = [
        s, 'exec',
        '--bind', f'{i}:/mnt/data_in',
        '--bind', f'{o}/ipccar5_glaciers:/mnt/data_out',
        '--bind', f'{o}/fair:/mnt/fair',
        '--nv',
        f'{c}/ipccar5.sif',
        'ipccar5', 'glaciers',
        f'--scenario={cfg.scenario}',
        f'--nsamps={cfg.nsamps}',
        '--climate-fname=/mnt/fair/climate.nc',
        '--glacier-fraction-file=/mnt/data_in/glacier_fraction.txt',
        '--location-file=/mnt/data_in/location.lst',
        '--fingerprint-dir=/mnt/data_in/FPRINT',
        '--global-output-file=/mnt/data_out/glaciers_gslr.nc',
        '--local-output-file=/mnt/data_out/glaciers_lslr.nc'
    ]
    
    # IPCCAR5 Ice Sheets
    cmds['ipccar5_icesheets'] = [
        s, 'exec',
        '--bind', f'{i}:/mnt/data_in:ro',
        '--bind', f'{o}/ipccar5_icesheets:/mnt/data_out',
        '--bind', f'{o}/fair:/mnt/fair',
        '--nv',
        f'{c}/ipccar5.sif',
        'ipccar5', 'icesheets',
        f'--scenario={cfg.scenario}',
        f'--nsamps={cfg.nsamps}',
        '--climate-fname=/mnt/fair/climate.nc',
        '--icesheet-fraction-file=/mnt/data_in/icesheet_fraction.txt',
        '--location-file=/mnt/data_in/location.lst',
        '--fingerprint-dir=/mnt/data_in/FPRINT',
        '--global-gis-output-file=/mnt/data_out/gis_gslr.nc',
        '--global-ais-output-file=/mnt/data_out/ais_gslr.nc',
        '--global-wais-output-file=/mnt/data_out/wais_gslr.nc',
        '--global-eais-output-file=/mnt/data_out/eais_gslr.nc',
        '--local-gis-output-file=/mnt/data_out/gis_lslr.nc',
        '--local-ais-output-file=/mnt/data_out/ais_lslr.nc',
        '--local-wais-output-file=/mnt/data_out/wais_lslr.nc',
        '--local-eais-output-file=/mnt/data_out/eais_lslr.nc'
    ]
    
    # Bamber
    cmds['bamber'] = [
        s, 'exec',
        '--bind', f'{i}:/mnt/data_in:ro',
        '--bind', f'{o}/bamber:/mnt/data_out',
        '--nv',
        f'{c}/bamber19-icesheets.sif',
        'bamber19-icesheets',
        '--pipeline-id=5678',
        '--slr-proj-mat-file=/mnt/data_in/SLRProjections190726core_SEJ_full.mat',
        '--location-file=/mnt/data_in/location.lst',
        '--fingerprint-dir=/mnt/data_in/FPRINT',
        '--output-EAIS-lslr-file=/mnt/data_out/output_eais_lslr.nc',
        '--output-WAIS-lslr-file=/mnt/data_out/output_wais_lslr.nc',
        '--output-GIS-lslr-file=/mnt/data_out/output_gis_lslr.nc',
        '--output-AIS-lslr-file=/mnt/data_out/output_ais_lslr.nc',
        '--output-EAIS-gslr-file=/mnt/data_out/output_eais_gslr.nc',
        '--output-WAIS-gslr-file=/mnt/data_out/output_wais_gslr.nc',
        '--output-GIS-gslr-file=/mnt/data_out/output_gis_gslr.nc',
        '--output-AIS-gslr-file=/mnt/data_out/output_ais_gslr.nc'
    ]
    
    # Total tasks
    tc = f'{c}/sealevel-facts-total_latest-sandbox'
    for comp in ['lws', 'sterodynamics']:
        for typ in ['gslr', 'lslr']:
            cmds[f'total_{comp}_{typ}'] = [
                s, 'exec',
                '--bind', './data/output:/mnt/io',
                tc, 'facts-total',
                f'--item=/mnt/io/{comp}/{typ}.nc',
                '--pyear-start=2020', '--pyear-end=2150', '--pyear-step=10',
                f'--output-path=/mnt/io/totaled_{comp}_{typ}.nc'
            ]
    
    for typ in ['gslr', 'lslr']:
        cmds[f'total_all_{typ}'] = [
            s, 'exec',
            '--bind', './data/output:/mnt/io',
            tc, 'facts-total',
            f'--item=/mnt/io/lws/{typ}.nc',
            f'--item=/mnt/io/sterodynamics/{typ}.nc',
            '--pyear-start=2020', '--pyear-end=2150', '--pyear-step=10',
            f'--output-path=/mnt/io/totaled_all_{typ}.nc'
        ]
    
    return cmds


# =============================================================================
# Workflow
# =============================================================================

async def run_workflow(cfg: Config, logger: logging.Logger) -> Dict[str, TaskResult]:
    """Run the FACTS workflow"""
    
    # Create directories first
    create_directories(cfg)
    
    cmds = build_commands(cfg)
    results = {}
    
    if "modules" in cfg.phases:
        logger.info("=" * 50)
        logger.info("PHASE: modules")
        logger.info("=" * 50)
        
        fair_t = asyncio.create_task(run_task('fair', cmds['fair'], cfg.dry_run, logger))
        lws_t = asyncio.create_task(run_task('lws', cmds['lws'], cfg.dry_run, logger))
        
        results['fair'] = await fair_t
        results['lws'] = await lws_t
        
        if results['fair'].state == TaskState.COMPLETED:
            results['sterodynamics'] = await run_task('sterodynamics', cmds['sterodynamics'], cfg.dry_run, logger)
        else:
            logger.warning("Skipping sterodynamics - FAIR failed")
            results['sterodynamics'] = TaskResult('sterodynamics', TaskState.SKIPPED, -1, 0)
    
    if "modules2" in cfg.phases:
        logger.info("=" * 50)
        logger.info("PHASE: modules2")
        logger.info("=" * 50)
        
        tasks = {n: asyncio.create_task(run_task(n, cmds[n], cfg.dry_run, logger))
                 for n in ['kopp14', 'ipccar5_glaciers', 'ipccar5_icesheets', 'bamber']}
        for n, t in tasks.items():
            results[n] = await t
    
    if "total" in cfg.phases:
        logger.info("=" * 50)
        logger.info("PHASE: total")
        logger.info("=" * 50)
        
        total_names = [k for k in cmds if k.startswith('total_')]
        tasks = {n: asyncio.create_task(run_task(n, cmds[n], cfg.dry_run, logger)) for n in total_names}
        for n, t in tasks.items():
            results[n] = await t
    
    return results


def print_summary(results: Dict[str, TaskResult], elapsed: float, logger: logging.Logger) -> bool:
    logger.info("")
    logger.info("=" * 50)
    logger.info("SUMMARY")
    logger.info("=" * 50)
    
    completed = failed = skipped = 0
    for name, r in results.items():
        icon = {"COMPLETED": "✓", "FAILED": "✗", "SKIPPED": "○"}.get(r.state.value, "?")
        if r.state == TaskState.COMPLETED:
            completed += 1
        elif r.state == TaskState.FAILED:
            failed += 1
        else:
            skipped += 1
        logger.info(f"  {icon} {name}: {r.state.value} ({r.elapsed:.1f}s)")
    
    logger.info(f"\nTotal: {len(results)} | ✓ {completed} | ✗ {failed} | ○ {skipped}")
    logger.info(f"Time: {elapsed:.1f}s ({elapsed/60:.1f}m)")
    
    return failed == 0


# =============================================================================
# SLURM
# =============================================================================

def generate_slurm_script(args, script_path: str) -> str:
    """Generate SLURM submission script"""
    
    # Normalize memory format
    mem = args.mem
    if mem:
        mem = mem.upper().replace('GB', 'G').replace('MB', 'M')
    
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={args.job_name}",
        f"#SBATCH --output=facts_%j.out",
        f"#SBATCH --error=facts_%j.err",
        f"#SBATCH --partition={args.partition}",
        f"#SBATCH --account={args.account}",
        f"#SBATCH --time={args.time}",
        f"#SBATCH --nodes={args.nodes}",
        f"#SBATCH --ntasks={args.ntasks}",
    ]
    
    if args.gres:
        lines.append(f"#SBATCH --gres={args.gres}")
    else:
        if args.cpus:
            lines.append(f"#SBATCH --cpus-per-task={args.cpus}")
        if mem:
            lines.append(f"#SBATCH --mem={mem}")
    
    lines.extend([
        "",
        'echo "Job: $SLURM_JOB_ID on $SLURM_NODELIST"',
        'echo "Start: $(date)"',
        "",
        "module load python/GEOSpyD/24.3.0-0/3.11",
        "module load singularity/4.0.3",
        "",
        "export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}",
        "",
    ])
    
    # Build python command
    py_cmd = f"python {script_path}"
    py_cmd += f" --nsamps {args.nsamps}"
    py_cmd += f" --scenario {args.scenario}"
    py_cmd += f" --input-dir '{args.input_dir}'"
    py_cmd += f" --output-dir '{args.output_dir}'"
    py_cmd += f" --container-dir '{args.container_dir}'"
    py_cmd += f" --phases {' '.join(args.phases)}"
    if args.verbose:
        py_cmd += " --verbose"
    
    lines.extend([py_cmd, "", 'echo "End: $(date), Exit: $?"'])
    
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(description="FACTS Workflow")
    
    # Workflow
    w = p.add_argument_group("Workflow")
    w.add_argument("--nsamps", type=int, default=20)
    w.add_argument("--scenario", default="ssp585")
    w.add_argument("--phases", nargs="+", default=["modules", "modules2", "total"],
                   choices=["modules", "modules2", "total"])
    
    # Paths
    pa = p.add_argument_group("Paths")
    pa.add_argument("--input-dir", default="/discover/nobackup/projects/sealevel/facts2.0/data/input")
    pa.add_argument("--output-dir", default="/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output")
    pa.add_argument("--container-dir", default="/discover/nobackup/projects/sealevel/facts2.0/containers")
    pa.add_argument("--singularity", default="/usr/local/other/singularity/4.0.3/bin/singularity")
    
    # Execution
    e = p.add_argument_group("Execution")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--verbose", "-v", action="store_true")
    e.add_argument("--log-file")
    
    # SLURM
    s = p.add_argument_group("SLURM")
    s.add_argument("--slurm", action="store_true", help="Print SLURM script")
    s.add_argument("--submit", action="store_true", help="Submit to SLURM")
    s.add_argument("--job-name", default="facts_workflow")
    s.add_argument("--partition", "-p", default="compute")
    s.add_argument("--account", "-A", default="ilab")
    s.add_argument("--nodes", "-N", type=int, default=1)
    s.add_argument("--ntasks", "-n", type=int, default=1)
    s.add_argument("--cpus", "-c", type=int, default=16)
    s.add_argument("--mem", default="64G")
    s.add_argument("--time", "-t", default="04:00:00")
    s.add_argument("--gres")
    
    return p.parse_args()


def main():
    args = parse_args()
    
    # SLURM modes
    if args.slurm or args.submit:
        script = generate_slurm_script(args, os.path.abspath(__file__))
        
        if args.slurm:
            print(script)
            return 0
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script)
            slurm_file = f.name
        
        print(f"Submitting: {slurm_file}")
        result = subprocess.run(['sbatch', slurm_file], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode
    
    # Setup logging
    logger = setup_logging(args.verbose, args.log_file)
    
    # Build config
    cfg = Config(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        container_dir=args.container_dir,
        singularity=args.singularity,
        nsamps=args.nsamps,
        scenario=args.scenario,
        phases=args.phases,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    
    logger.info(f"FACTS: nsamps={cfg.nsamps}, scenario={cfg.scenario}, phases={cfg.phases}")
    
    start = time.time()
    results = asyncio.run(run_workflow(cfg, logger))
    elapsed = time.time() - start
    
    success = print_summary(results, elapsed, logger)
    
    # Save results
    with open('facts_results.json', 'w') as f:
        json.dump({n: {'state': r.state.value, 'exit': r.exit_code, 'time': r.elapsed}
                   for n, r in results.items()}, f, indent=2)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
