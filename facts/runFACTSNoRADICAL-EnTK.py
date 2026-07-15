#!/usr/bin/env python
"""
runFACTS.py - Rewritten without RADICAL-EnTK
Uses pure asyncio and subprocess for workflow execution
"""

import sys
import os
import time
import datetime
import argparse
import errno
import yaml
import asyncio
import subprocess
from pathlib import Path
from pprint import pprint
import json
import shutil
import FACTS as facts


async def run_task_async(task, pipeline_name, work_dir):
    """
    Execute a single FACTS task asynchronously
    
    Args:
        task: Task object from FACTS pipeline
        pipeline_name: Name of the parent pipeline
        work_dir: Working directory for execution
    
    Returns:
        tuple: (task_name, return_code, stdout, stderr)
    """
    task_dict = task.as_dict()
    task_name = task.name
    
    print(f"  Starting task: {task_name}")
    
    # Create task-specific work directory
    task_dir = Path(work_dir) / pipeline_name / task_name
    task_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Handle input data uploads (copy files to work directory)
        if 'upload_input_data' in task_dict and task_dict['upload_input_data']:
            for input_file in task_dict['upload_input_data']:
                src = Path(input_file)
                if src.exists():
                    dst = task_dir / src.name
                    shutil.copy2(src, dst)
                    print(f"    Copied input: {src.name}")
        
        # Handle copy_input_data (if present)
        if 'copy_input_data' in task_dict and task_dict['copy_input_data']:
            for copy_spec in task_dict['copy_input_data']:
                # copy_spec might be "src > dst" format
                if '>' in copy_spec:
                    src_path, dst_path = copy_spec.split('>')
                    src_path = src_path.strip()
                    dst_path = dst_path.strip()
                    src = Path(src_path)
                    dst = task_dir / dst_path
                    if src.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        print(f"    Copied: {src} -> {dst}")
        
        # Build command list
        commands = []
        
        # Add pre_exec commands
        if 'pre_exec' in task_dict and task_dict['pre_exec']:
            for cmd in task_dict['pre_exec']:
                commands.append(cmd)
        
        # Add main executable and arguments
        if 'executable' in task_dict:
            main_cmd = task_dict['executable']
            if 'arguments' in task_dict and task_dict['arguments']:
                main_cmd += ' ' + ' '.join(map(str, task_dict['arguments']))
            commands.append(main_cmd)
        
        # Add post_exec commands
        if 'post_exec' in task_dict and task_dict['post_exec']:
            for cmd in task_dict['post_exec']:
                commands.append(cmd)
        
        # Execute commands sequentially
        full_stdout = []
        full_stderr = []
        return_code = 0
        
        for cmd in commands:
            if not cmd or cmd.strip() == '':
                continue
                
            print(f"    Executing: {cmd[:100]}...")
            
            # Run command
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=task_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            
            stdout, stderr = await proc.communicate()
            
            full_stdout.append(stdout.decode('utf-8', errors='replace'))
            full_stderr.append(stderr.decode('utf-8', errors='replace'))
            
            if proc.returncode != 0:
                return_code = proc.returncode
                print(f"    ✗ Command failed with return code {return_code}")
                print(f"    Error: {stderr.decode('utf-8', errors='replace')[:200]}")
                break
        
        # Handle output data downloads (copy results to output directory)
        if return_code == 0 and 'download_output_data' in task_dict and task_dict['download_output_data']:
            for output_spec in task_dict['download_output_data']:
                # output_spec might be "src > dst" or just "src"
                if '>' in output_spec:
                    src_name, dst_path = output_spec.split('>')
                    src_name = src_name.strip()
                    dst_path = dst_path.strip()
                else:
                    src_name = output_spec.strip()
                    dst_path = output_spec.strip()
                
                src_file = task_dir / src_name
                if src_file.exists():
                    dst_file = Path(dst_path)
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    print(f"    Downloaded output: {src_name} -> {dst_path}")
                else:
                    print(f"    Warning: Output file not found: {src_name}")
        
        if return_code == 0:
            print(f"  ✓ Completed task: {task_name}")
        
        return (task_name, return_code, '\n'.join(full_stdout), '\n'.join(full_stderr))
        
    except Exception as e:
        print(f"  ✗ Task {task_name} failed with exception: {e}")
        return (task_name, -1, "", str(e))


async def run_stage_async(stage, pipeline_name, work_dir):
    """
    Execute a stage (all tasks in parallel)
    
    Args:
        stage: Stage object from FACTS pipeline
        pipeline_name: Name of the parent pipeline
        work_dir: Working directory for execution
    
    Returns:
        list: Results from all tasks
    """
    stage_name = stage.name
    print(f"\n--- Stage: {stage_name} ---")
    
    # Run all tasks in this stage concurrently
    tasks = [run_task_async(task, pipeline_name, work_dir) for task in stage.tasks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check for failures
    failures = []
    for result in results:
        if isinstance(result, Exception):
            failures.append(str(result))
        elif result[1] != 0:  # return_code != 0
            failures.append(f"{result[0]} failed with code {result[1]}")
    
    if failures:
        print(f"✗ Stage {stage_name} completed with failures:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print(f"✓ Stage {stage_name} completed successfully")
    
    return results


async def run_pipeline_async(pipeline, work_dir):
    """
    Execute a pipeline (all stages sequentially)
    
    Args:
        pipeline: Pipeline object from FACTS
        work_dir: Working directory for execution
    
    Returns:
        list: Results from all stages
    """
    pipeline_name = pipeline.name
    print(f"\n=== Pipeline: {pipeline_name} ===")
    
    # Run stages sequentially (they may have dependencies)
    all_results = []
    for stage in pipeline.stages:
        stage_results = await run_stage_async(stage, pipeline_name, work_dir)
        all_results.extend(stage_results)
        
        # Check if stage failed - if so, stop pipeline
        failures = [r for r in stage_results if isinstance(r, tuple) and r[1] != 0]
        if failures:
            print(f"✗ Pipeline {pipeline_name} stopped due to stage failure")
            return all_results
    
    print(f"✓ Pipeline {pipeline_name} completed successfully")
    return all_results


async def run_pipelines_async(pipelines, work_dir):
    """
    Execute multiple pipelines in parallel
    
    Args:
        pipelines: List of Pipeline objects
        work_dir: Working directory for execution
    
    Returns:
        list: Results from all pipelines
    """
    print(f"\n{'=' * 60}")
    print(f"Executing {len(pipelines)} pipeline(s)")
    print(f"{'=' * 60}")
    
    # Run all pipelines concurrently
    tasks = [run_pipeline_async(p, work_dir) for p in pipelines]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


def run_experiment(exp_dir, debug_mode=False, alt_id=False, resourcedir=None, 
                   makeshellscript=False, globalopts=None, work_dir=None):
    """
    Main function to run FACTS experiment without RADICAL-EnTK
    
    Args:
        exp_dir: Experiment directory path
        debug_mode: If True, print config and exit
        alt_id: Alternative session ID format (unused in async version)
        resourcedir: Resource directory (unused in async version)
        makeshellscript: Generate shell script instead of running
        globalopts: Global options to override
        work_dir: Working directory for execution (default: exp_dir/work)
    """
    
    if not resourcedir:
        resourcedir = exp_dir
    
    # Parse experiment configuration
    expconfig = facts.ParseExperimentConfig(exp_dir, globalopts=globalopts)
    experimentsteps = expconfig['experimentsteps']
    workflows = expconfig['workflows']
    climate_data_files = expconfig['climate_data_files']
    
    # Write workflows to yml file
    workflows_file = os.path.join(exp_dir, 'workflows.yml')
    with open(workflows_file, 'w') as f:
        f.write("# automatically generated by runFACTS.py\n")
        f.write("#\n")
        yaml.dump(workflows, f)
    print(f"Written workflows to: {workflows_file}")
    
    # Write location file if none exists
    location_file = os.path.join(exp_dir, "location.lst")
    if not os.path.isfile(location_file):
        with open(location_file, 'w') as f:
            f.write("New_York\t12\t40.70\t-74.01")
        print(f"Created default location file: {location_file}")
    
    # Print debug info if requested
    if debug_mode:
        print_experimentsteps(experimentsteps)
        print('')
        print('CLIMATE DATA')
        print('------------')
        pprint(climate_data_files)
        print('')
        print_workflows(workflows)
        sys.exit(0)
    
    # Generate shell script if requested
    if makeshellscript:
        print_experimentsteps_script(experimentsteps, exp_dir=exp_dir)
        sys.exit(0)
    
    # Create output directory
    output_dir = os.path.join(exp_dir, "output")
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Output directory: {output_dir}")
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    
    # Create work directory
    if work_dir is None:
        work_dir = os.path.join(exp_dir, "work")
    try:
        os.makedirs(work_dir, exist_ok=True)
        print(f"Work directory: {work_dir}")
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    
    # Copy location file to work directory
    shutil.copy2(location_file, work_dir)
    
    # Run experiment steps
    print(f"\n{'=' * 60}")
    print(f"Starting FACTS Experiment")
    print(f"Experiment: {exp_dir}")
    print(f"Steps: {len(experimentsteps)}")
    print(f"{'=' * 60}\n")
    
    start_time = time.time()
    
    for step_num, (step, pipelines) in enumerate(experimentsteps.items(), 1):
        step_start = time.time()
        print(f"\n{'#' * 60}")
        print(f"# STEP {step_num}/{len(experimentsteps)}: {step}")
        print(f"# Pipelines: {len(pipelines)}")
        print(f"{'#' * 60}")
        
        # Run pipelines for this step
        try:
            results = asyncio.run(run_pipelines_async(pipelines, work_dir))
            
            # Check for failures
            all_failures = []
            for pipeline_results in results:
                if isinstance(pipeline_results, Exception):
                    all_failures.append(str(pipeline_results))
                elif isinstance(pipeline_results, list):
                    for task_result in pipeline_results:
                        if isinstance(task_result, tuple) and task_result[1] != 0:
                            all_failures.append(f"{task_result[0]}: code {task_result[1]}")
            
            if all_failures:
                print(f"\n✗ Step {step} completed with {len(all_failures)} failure(s)")
                for failure in all_failures:
                    print(f"  - {failure}")
            else:
                print(f"\n✓ Step {step} completed successfully")
            
        except Exception as e:
            print(f"\n✗ Step {step} failed with exception: {e}")
            import traceback
            traceback.print_exc()
        
        step_elapsed = time.time() - step_start
        print(f"\nStep elapsed time: {step_elapsed:.2f} seconds")
    
    total_elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Experiment Complete")
    print(f"Total elapsed time: {total_elapsed:.2f} seconds ({total_elapsed/60:.2f} minutes)")
    print(f"{'=' * 60}\n")


def print_workflows(workflows):
    """Print workflow information"""
    for this_workflow in workflows:
        print('WORKFLOW: ', this_workflow)
        print('-----------------')
        pprint(workflows[this_workflow])
        print('')


def print_pipeline(pipelines):
    """Print pipeline information"""
    for p in pipelines:
        print("Pipeline {}:".format(p.name))
        print("################################")
        print(p.as_dict())
        for s in p.stages:
            print("Stage {}:".format(s.name))
            print("============================")
            pprint(s.as_dict())
            for t in s.tasks:
                print("Task {}:".format(t.name))
                print("----------------------------")
                pprint(t.as_dict())


def print_experimentsteps(experimentsteps):
    """Print experiment steps information"""
    for this_step, pipelines in experimentsteps.items():
        print('EXPERIMENT STEP: ', this_step)
        print('-----------------')
        print_pipeline(pipelines)
        print('')


def print_experimentsteps_script(experimentsteps, exp_dir=None):
    """Generate bash script from experiment configuration"""
    print('#!/bin/bash\n')
    
    print('if [ -z "$WORKDIR" ]; then  ')
    print('   WORKDIR=/scratch/`whoami`/test.`date +%s`')
    print('fi')
    print('mkdir -p $WORKDIR\n')
    print('if [ -z "$OUTPUTDIR" ]; then  ')
    print('   OUTPUTDIR=/scratch/`whoami`/test.`date +%s`/output')
    print('fi')
    print('mkdir -p $OUTPUTDIR')
    print('BASEDIR=`pwd`')
    
    for this_step, pipelines in experimentsteps.items():
        print('\n#EXPERIMENT STEP: ', this_step, '\n')
        for p in pipelines:
            print("\n# - Pipeline {}:\n\n".format(p.name))
            print("PIPELINEDIR=$WORKDIR/{}".format(p.name))
            print('mkdir -p $PIPELINEDIR\n')
            print('cd $BASEDIR')
            if exp_dir and len(exp_dir) > 0:
                print("cp {}/location.lst $PIPELINEDIR".format(exp_dir))
            for s in p.stages:
                print("\n# ---- Stage {}:\n".format(s.name))
                for t in s.tasks:
                    tdict = t.as_dict()
                    print('cd $BASEDIR')
                    if 'upload_input_data' in tdict.keys():
                        if len(tdict['upload_input_data']) > 0:
                            print('cp ' + ' '.join(map(str, t['upload_input_data'])) + ' $PIPELINEDIR')
                    
                    print('cd $PIPELINEDIR')
                    
                    if 'pre_exec' in tdict.keys():
                        print('\n'.join(map(str, t['pre_exec'])))
                    if 'arguments' in tdict.keys():
                        print(tdict['executable'] + ' ' + ' '.join(map(str, t['arguments'])))
                    if 'post_exec' in tdict.keys():
                        print('\n'.join(map(str, t['post_exec'])))
                    if 'download_output_data' in tdict.keys():
                        for df in tdict['download_output_data']:
                            ddf = df.split(' ')
                            print('cp ' + ddf[0] + ' $OUTPUTDIR')


if __name__ == "__main__":
    # Initialize the argument parser
    parser = argparse.ArgumentParser(
        description="The Framework for Assessing Changes To Sea-level (FACTS) - Async Version"
    )
    
    # Add arguments
    parser.add_argument('edir', nargs='?', 
                       help="Experiment Directory",
                       default="/home/gtamkin/_sealevel/facts/experiments/dummy.input")
    parser.add_argument('--shellscript', 
                       help="Turn experiment config into a shell script", 
                       action="store_true")
    parser.add_argument('--debug', 
                       help="Enable debug mode (check configuration, do not execute)", 
                       action="store_true")
    parser.add_argument('--resourcedir', 
                       help="Directory containing resource files (unused in async version)", 
                       type=str, default='./resources')
    parser.add_argument('--alt_id', 
                       help='Alternative session ID format (unused in async version)', 
                       action='store_true')
    parser.add_argument('--global_options', 
                       help='Dictionary of global options to overwrite those in config.yml', 
                       type=json.loads)
    parser.add_argument('--workdir',
                       help='Working directory for task execution (default: exp_dir/work)',
                       type=str, default=None)
    
    # Parse the arguments
    args = parser.parse_args()
    
    # Does the experiment directory exist?
    if not os.path.isdir(args.edir):
        print(f'{args.edir} does not exist')
        sys.exit(1)
    
    # Run the experiment
    try:
        run_experiment(
            args.edir, 
            args.debug, 
            args.alt_id, 
            resourcedir=args.resourcedir,
            makeshellscript=args.shellscript, 
            globalopts=args.global_options,
            work_dir=args.workdir
        )
    except KeyboardInterrupt:
        print("\n\nExperiment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nExperiment failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    sys.exit(0)