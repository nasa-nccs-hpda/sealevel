#!/usr/bin/env python
"""
fair_facts_v2.py - FACTS workflow execution script
Converted from Jupyter notebook for SLURM execution on Discover
"""

import asyncio
import logging
import time
import os
import shlex
import random
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from radical.asyncflow import WorkflowEngine
from radical.asyncflow import ConcurrentExecutionBackend
from radical.asyncflow.logging import init_default_logger

logger = logging.getLogger(__name__)


def file_exists_and_has_content(filepath):
    """Check if file exists and has content"""
    path = Path(filepath)
    return path.is_file() and path.stat().st_size > 0


async def modules():
    """Run FAIR, LWS, and Sterodynamics modules"""
    init_default_logger(logging.DEBUG)

    # Create backend and workflow
    engine = await ConcurrentExecutionBackend(ThreadPoolExecutor())
    flow = await WorkflowEngine.create(engine)
    
    # Ensure output directories exist
    def setup_directories():
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/lws', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/sterodynamics', exist_ok=True)
        os.makedirs('/lscratch/tdirs/gt-scratch/.cache', exist_ok=True)

    @flow.executable_task
    async def fair_task():
        """FAIR temperature model task"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/input',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair:/output',
            '/discover/nobackup/projects/sealevel/facts2.0//containers/fair-temperature.sif',
            'fair-temperature',
            '--pipeline-id=1234',
            '--output-oceantemp-file=/output/oceantemp.nc',
            '--nsamps=20',
            '--output-ohc-file=/output/ohc.nc',
            '--output-gsat-file=/output/gsat.nc',
            '--output-climate-file=/output/climate.nc',
            '--rcmip-file=/input/rcmip/rcmip-emissions-annual-means-v5-1-0.csv',
            '--param-file=/input/parameters/fair_ar6_climate_params_v4.0.nc'
        ]
        return shlex.join(cmd)

    @flow.executable_task
    async def lws_task():
        """Land Water Storage task - can run independently of FAIR"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/input',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/lws:/output',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/ssp-landwaterstorage.sif',
            'ssp-landwaterstorage',
            '--pipeline-id=1234',
            '--nsamps=20',
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
        return shlex.join(cmd)

    @flow.executable_task
    async def sterodynamics_task(fair_task):
        """Sterodynamics task - depends on FAIR output"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/input',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair:/fair',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/sterodynamics:/output',
            '--nv',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/tlm-sterodynamics.sif',
            'tlm-sterodynamics',
            '--pipeline-id=1234',
            '--scenario=ssp585',
            '--nsamps=20',
            '--model-dir=/input/cmip6/',
            '--location-file=/input/location.lst',
            '--output-lslr-file=/output/lslr.nc',
            '--output-gslr-file=/output/gslr.nc',
            '--expansion-coefficients-file=/input/scmpy2LM_RCMIP_CMIP6calpm_n18_expcoefs.nc',
            '--gsat-rmses-file=/input/scmpy2LM_RCMIP_CMIP6calpm_n17_gsat_rmse.nc',
            '--climate-data-file=/fair/climate.nc'
        ]
        return shlex.join(cmd)

    async def run_climate_workflow(pipeline_id):
        """Run the complete climate workflow"""
        logger.info(f'Starting climate workflow {pipeline_id} at {time.time()}')

        # Setup directories
        setup_directories()

        # Start FAIR and LWS tasks (they can run in parallel)
        fair_future = fair_task()
        lws_future = lws_task()

        # Wait for FAIR to complete (sterodynamics depends on it)
        fair_result = await fair_future
        logger.info(f'FAIR task completed for pipeline {pipeline_id}')

        # Start sterodynamics task (depends on FAIR output)
        sterodynamics_future = sterodynamics_task(fair_future)

        # Wait for all tasks to complete
        lws_result = await lws_future
        sterodynamics_result = await sterodynamics_future

        logger.info(f'Climate workflow {pipeline_id} finished at {time.time()}')

        return {
            'fair': fair_result,
            'lws': lws_result,
            'sterodynamics': sterodynamics_result
        }

    # Run workflow(s)
    transaction_id = random.randint(1, 1000)
    logger.info("Launching asynchronous workflow: " + str(transaction_id))
    results = await run_climate_workflow(transaction_id)
    logger.info("All modules completed successfully: " + str(transaction_id))
    
    await flow.shutdown()
    logger.info(results)
    logger.info("All workflows completed successfully")
    
    return results


async def total():
    """Run facts-total tasks"""
    init_default_logger(logging.DEBUG)

    # Create backend and workflow
    engine = await ConcurrentExecutionBackend(ThreadPoolExecutor())
    flow = await WorkflowEngine.create(engine)
    
    # Ensure output directories exist
    def setup_total_directories():
        os.makedirs('./data/output', exist_ok=True)

    @flow.executable_task
    async def total_task(component, name):
        """Facts total task - returns singularity command string"""
        if component == 'all':
            filename = '/mnt/total_out/totaled_output_all_' + name + '.nc'
            cmd = [
                '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
                '--bind', './data/output:/mnt/total_in',
                '--bind', './data/output:/mnt/total_out',
                '/discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest-sandbox',
                'facts-total',
                '--item=/mnt/total_out/lws/' + name + '.nc',
                '--item=/mnt/total_out/sterodynamics/' + name + '.nc',
                '--pyear-start=2020',
                '--pyear-end=2150',
                '--pyear-step=10',
                '--output-path=' + filename
            ]
        else:
            filename = '/mnt/total_out/totaled_output_' + component + '_' + name + '.nc'
            cmd = [
                '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
                '--bind', './data/output:/mnt/total_in',
                '--bind', './data/output:/mnt/total_out',
                '/discover/nobackup/projects/sealevel/facts2.0/containers/sealevel-facts-total_latest-sandbox',
                'facts-total',
                '--item=/mnt/total_out/' + component + '/' + name + '.nc',
                '--pyear-start=2020',
                '--pyear-end=2150',
                '--pyear-step=10',
                '--output-path=' + filename
            ]
        
        # Log the command
        cmd_str = shlex.join(cmd)
        logger.info(f"Preparing command: {cmd_str}")
        
        # RETURN THE COMMAND STRING - let radical.asyncflow execute it
        return cmd_str

    async def run_total_workflow(pipeline_id):
        """Run the total climate workflow"""
        logger.info(f'Starting total climate workflow {pipeline_id} at {time.time()}')

        # Setup directories
        setup_total_directories()
        
        # Start ALL tasks in parallel
        total_future_lws_lslr = total_task('lws', 'lslr')
        total_future_lws_gslr = total_task('lws', 'gslr')
        total_future_sterodynamics_lslr = total_task('sterodynamics', 'lslr')
        total_future_sterodynamics_gslr = total_task('sterodynamics', 'gslr')
        total_future_all_lslr = total_task('all', 'lslr')
        total_future_all_gslr = total_task('all', 'gslr')

        # Wait for all tasks to complete
        results = await asyncio.gather(
            total_future_lws_lslr,
            total_future_lws_gslr,
            total_future_sterodynamics_lslr,
            total_future_sterodynamics_gslr,
            total_future_all_lslr,
            total_future_all_gslr,
            return_exceptions=True
        )
            
        logger.info(f'ALL TOTAL tasks completed for pipeline {pipeline_id}')
        logger.info(f'Climate workflow {pipeline_id} finished at {time.time()}')
        return results
        
    # Run workflow(s)
    transaction_id = random.randint(1, 1000)
    results = await run_total_workflow(transaction_id)
    logger.info(results)
    logger.info("=========Total completed successfully=========: " + str(transaction_id))
    await flow.shutdown()
    
    return results


async def modules2():
    """Run kopp14, ipccar5, and bamber modules"""
    init_default_logger(logging.DEBUG)

    # Create backend and workflow
    engine = await ConcurrentExecutionBackend(ThreadPoolExecutor())
    flow = await WorkflowEngine.create(engine)
    
    # Ensure output directories exist
    def setup_directories():
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/lws', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/sterodynamics', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/bamber', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/ipccar5_glaciers', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/ipccar5_icesheets', exist_ok=True)
        os.makedirs('/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/kopp14verticallandmotion', exist_ok=True)

    @flow.executable_task
    async def kopp14_verticallandmotion_task():
        """kopp14_verticallandmotion temperature model task"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/mnt/kopp14verticallandmotion_data_in:ro',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/kopp14verticallandmotion:/mnt/kopp14verticallandmotion_data_out',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair:/mnt/fair_data_out',
            '--nv',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/kopp14-verticallandmotion.sif',
            'kopp14-verticallandmotion',
            '--pipeline-id=5678',
            '--rate-file=/mnt/kopp14verticallandmotion_data_in/bkgdrate-210306.tsv', 
            '--location-file=/mnt/kopp14verticallandmotion_data_in/location.lst',
            '--output-lslr-file=/mnt/kopp14verticallandmotion_data_out/localsl.nc'
        ]
        return shlex.join(cmd)
        
    @flow.executable_task
    async def ipccar5_glaciers_task():
        """ipccar5_glaciers temperature model task"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/mnt/ipccar5_data_in',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/ipccar5_glaciers:/mnt/ipccar5_data_out',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair:/mnt/fair_data_out',
            '--nv',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/ipccar5.sif',
            'ipccar5',
            'glaciers',
            '--scenario=ssp585', 
            '--nsamps=20',
            '--climate-fname=/mnt/fair_data_out/climate.nc',
            '--glacier-fraction-file=/mnt/ipccar5_data_in/glacier_fraction.txt',
            '--location-file=/mnt/ipccar5_data_in/location.lst',
            '--fingerprint-dir=/mnt/ipccar5_data_in/FPRINT',
            '--global-output-file=/mnt/ipccar5_data_out/glaciers_gslr.nc',
            '--local-output-file=/mnt/ipccar5_data_out/glaciers_lslr.nc'
        ]
        return shlex.join(cmd)
   
    @flow.executable_task
    async def ipccar5_icesheets_task():
        """ipccar5_icesheets temperature model task"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/mnt/ipccar5_data_in:ro',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/ipccar5_icesheets:/mnt/ipccar5_data_out',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/fair:/mnt/fair_data_out',
            '--nv',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/ipccar5.sif',
            'ipccar5',
            'icesheets',
            '--scenario=ssp585', 
            '--nsamps=20',
            '--climate-fname=/mnt/fair_data_out/climate.nc',
            '--icesheet-fraction-file=/mnt/ipccar5_data_in/icesheet_fraction.txt',
            '--global-gis-output-file=/mnt/ipccar5_data_out/gis_gslr.nc',
            '--global-ais-output-file=/mnt/ipccar5_data_out/ais_gslr.nc',
            '--global-wais-output-file=/mnt/ipccar5_data_out/wais_gslr.nc',
            '--global-eais-output-file=/mnt/ipccar5_data_out/eais_gslr.nc',
            '--location-file=/mnt/ipccar5_data_in/location.lst',
            '--fingerprint-dir=/mnt/ipccar5_data_in/FPRINT',
            '--local-gis-output-file=/mnt/ipccar5_data_out/gis_lslr.nc',
            '--local-ais-output-file=/mnt/ipccar5_data_out/ais_lslr.nc',
            '--local-wais-output-file=/mnt/ipccar5_data_out/wais_lslr.nc',
            '--local-eais-output-file=/mnt/ipccar5_data_out/eais_lslr.nc' 
        ]
        return shlex.join(cmd)
   
    @flow.executable_task
    async def bamber_task():
        """BAMBER temperature model task"""
        cmd = [
            '/usr/local/other/singularity/4.0.3/bin/singularity', 'exec',
            '--bind', '/discover/nobackup/projects/sealevel/facts2.0/data/input:/mnt/bamber_data_in:ro',
            '--bind', '/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/data/output/bamber:/mnt/bamber_data_out',
            '--nv',
            '/discover/nobackup/projects/sealevel/facts2.0/containers/bamber19-icesheets.sif',
            'bamber19-icesheets',
            '--pipeline-id=5678',
            '--slr-proj-mat-file=/mnt/bamber_data_in/SLRProjections190726core_SEJ_full.mat',
            '--location-file=/mnt/bamber_data_in/location.lst',
            '--fingerprint-dir=/mnt/bamber_data_in/FPRINT',
            '--output-EAIS-lslr-file=/mnt/bamber_data_out/output_eais_lslr.nc',
            '--output-WAIS-lslr-file=/mnt/bamber_data_out/output_wais_lslr.nc',
            '--output-GIS-lslr-file=/mnt/bamber_data_out/output_gis_lslr.nc',
            '--output-AIS-lslr-file=/mnt/bamber_data_out/output_ais_lslr.nc',
            '--output-EAIS-gslr-file=/mnt/bamber_data_out/output_eais_gslr.nc',
            '--output-WAIS-gslr-file=/mnt/bamber_data_out/output_wais_gslr.nc',
            '--output-GIS-gslr-file=/mnt/bamber_data_out/output_gis_gslr.nc',
            '--output-AIS-gslr-file=/mnt/bamber_data_out/output_ais_gslr.nc' 
        ]
        return shlex.join(cmd)

    async def run_climate_workflow2(pipeline_id):
        """Run the complete climate workflow"""
        logger.info(f'Starting climate workflow2 {pipeline_id} at {time.time()}')

        # Setup directories
        setup_directories()

        # Start tasks 
        kopp14_verticallandmotion_future = kopp14_verticallandmotion_task()
        kopp14_verticallandmotion_result = await kopp14_verticallandmotion_future
        logger.info(f'kopp14-verticallandmotion_task completed for pipeline {pipeline_id}')

        ipccar5_icesheets_future = ipccar5_icesheets_task()
        ipccar5_icesheets_result = await ipccar5_icesheets_future
        logger.info(f'ipccar5_icesheets task completed for pipeline {pipeline_id}')

        bamber_future = bamber_task()
        bamber_result = await bamber_future
        logger.info(f'BAMBER task completed for pipeline {pipeline_id}')

        logger.info(f'Climate workflow2 {pipeline_id} finished at {time.time()}')

        return {
            'bamber': bamber_result,
            'ipccar5_icesheets': ipccar5_icesheets_result,
            'kopp14_verticallandmotion': kopp14_verticallandmotion_result
        }

    # Run workflow(s)
    transaction_id = random.randint(1, 1000)
    logger.info("Launching asynchronous workflow2: " + str(transaction_id))
    results = await run_climate_workflow2(transaction_id)
    logger.info("All modules2 completed successfully: " + str(transaction_id))
    
    await flow.shutdown()
    logger.info(results)
    logger.info("All workflows2 completed successfully")
    
    return results


async def main():
    """Main execution function - ALL ASYNC CALLS MUST BE INSIDE THIS FUNCTION"""
    logger.info("=" * 60)
    logger.info("Starting FACTS Workflow Execution")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    try:
        # Run modules and total
        logger.info("\n" + "=" * 60)
        logger.info("Running modules...")
        logger.info("=" * 60)
        modules2_results = await modules()

        # Run modules2 and total
        logger.info("\n" + "=" * 60)
        logger.info("Running modules2...")
        logger.info("=" * 60)
        modules2_results = await modules2()
        
        logger.info("\n" + "=" * 60)
        logger.info("Running total...")
        logger.info("=" * 60)
        total_results = await total()
        
        elapsed = time.time() - start_time
        
        logger.info("\n" + "=" * 60)
        logger.info("ALL WORKFLOWS COMPLETED SUCCESSFULLY")
        logger.info(f"Total elapsed time: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n" + "=" * 60)
        logger.error(f"WORKFLOW FAILED WITH ERROR: {e}")
        logger.error("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Set up basic logging before running
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the main workflow - NO AWAIT HERE, use asyncio.run()
    exit_code = asyncio.run(main())
    sys.exit(exit_code)