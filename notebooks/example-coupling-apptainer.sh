#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# FACTS Sea Level Experiment Runner - Apptainer run on limavm
# =============================================================================

# --- Paths -------------------------------------------------------------------
WORKSPACE="/discover/nobackup/projects/sealevel/shared"
DATA_DIR="${WORKSPACE}/data"
EXPERIMENT_NAME="example_coupling_apptainer"
EXPERIMENT_PARENT_DIR="apptainer_experiments"
OUTPUT_DIR="${WORKSPACE}/${EXPERIMENT_PARENT_DIR}/${EXPERIMENT_NAME}/output"
SHARED_IN="${DATA_DIR}/shared_input_data"
MODULE_IN="${DATA_DIR}/module_specific_input_data"
SIF_DIR="${WORKSPACE}/apptainer_experiments/sif"          # where .sif image files will be stored

# --- GLOBAL PARAMS ----
PYEAR_START=2020
PYEAR_END=2150
PYEAR_STEP=10
BASEYEAR=2005
SCENARIO="ssp585"
NSAMPS=1000
PIPELINE_ID="abc123"
WORKFLOW1_NAME="wf1f"
WORKFLOW2_NAME="wf2f"

# --- Image registry ----------------------------------------------------------
## prefix for all containers used from the FACTS2 container registry
REGISTRY="ghcr.io/fact-sealevel"

# --- Helpers -----------------------------------------------------------------

log() { echo "[$(date '+%H:%M:%S')] $*"; }

pull_image() {
    local name="$1"
    local ref="$2"
    local sif="${SIF_DIR}/${name}.sif"
    if [[ ! -f "$sif" ]]; then
        log "Pulling ${ref} -> ${sif}"
		# apptainer pull --disable-cache "$sif" "docker://${ref}"
		/usr/local/other/singularity/4.0.3/bin/singularity pull --disable-cache "$sif" "docker://${ref}"
    else
        log "Image already exists: ${sif}"
    fi
}
run_service() {
    local name="$1"
    local sif="${SIF_DIR}/${name}.sif"
    shift
    log "Running service: ${name} ${sif}"
    /usr/local/other/singularity/4.0.3/bin/singularity run \
        --no-home \
        --containall \
        "${BINDS[@]}" \
        "$sif" \
        "$@"
    log "Completed: ${name}"
}

_run_service() {
    local name="$1"
    local sif="${SIF_DIR}/${name}.sif"
    shift
    log "Running service: ${name} ${sif}"
    local cmd="/usr/local/other/singularity/4.0.3/bin/singularity run \
        --no-home \
        --containall \
        "${BINDS[@]}" \
        "$sif" \
        "$@""
    log "Completed: ${cmd}"
}

wait_for_output() {
    # Poll until an expected output file exists (used to gate depends_on)
    local file="$1"
    local service="$2"
    log "Waiting for output of ${service}: ${file}"
    local attempts=0
    until [[ -f "$file" ]]; do
        sleep 5
        attempts=$((attempts + 1))
        if (( attempts > 360 )); then   # 30-minute timeout
            echo "ERROR: Timed out waiting for ${file}" >&2
            exit 1
        fi
    done
    log "Output ready: ${file}"
}
# --- Setup -------------------------------------------------------------------
## make directories for output data
mkdir -p \
    "${SIF_DIR}" \
    "${OUTPUT_DIR}/fair-temperature" \
    "${OUTPUT_DIR}/fittedismip-gris" \
    "${OUTPUT_DIR}/deconto21-ais" \
    "${OUTPUT_DIR}/bamber19-icesheets" \
    "${OUTPUT_DIR}/larmip-ais" \
    "${OUTPUT_DIR}/ipccar5-glaciers" \
    "${OUTPUT_DIR}/ipccar5-icesheets" \
    "${OUTPUT_DIR}/tlm-sterodynamics" \
    "${OUTPUT_DIR}/kopp14-verticallandmotion" \
    "${OUTPUT_DIR}/ssp-landwaterstorage" \
    "${OUTPUT_DIR}/facts-total-${WORKFLOW1_NAME}" \
    "${OUTPUT_DIR}/facts-total-${WORKFLOW2_NAME}" \
    "${OUTPUT_DIR}/extremesealevel-pointsoverthreshold-${WORKFLOW1_NAME}" \
    "${OUTPUT_DIR}/extremesealevel-pointsoverthreshold-${WORKFLOW2_NAME}"

# --- Pull images for all modules included in experiment ---------------------------------------------------------

log "=== Pulling images ==="
pull_image "fair-temperature"                    "${REGISTRY}/fair-temperature:0.2.1"
pull_image "fittedismip-gris"               "${REGISTRY}/fittedismip-gris:0.1.2"
pull_image "bamber19-icesheets"             "${REGISTRY}/bamber19-icesheets:0.1.0"
pull_image "deconto21-ais"                  "${REGISTRY}/deconto21-ais:0.1.3"
pull_image "larmip-ais"                      "${REGISTRY}/larmip-ais:0.1.2"
pull_image "ipccar5-glaciers"                "${REGISTRY}/ipccar5:0.1.2"
pull_image "ipccar5-icesheets"               "${REGISTRY}/ipccar5:0.1.2"
pull_image "emulandice-ais"               "${REGISTRY}/emulandice:0.2.0"
pull_image "emulandice-gris"               "${REGISTRY}/emulandice:0.2.0"
pull_image "emulandice-glaciers"               "${REGISTRY}/emulandice:0.2.0"
pull_image "ssp-landwaterstorage"             "${REGISTRY}/ssp-landwaterstorage:0.2.1"
pull_image "kopp14-verticallandmotion"    "${REGISTRY}/kopp14-verticallandmotion:0.2.0"
pull_image "tlm-sterodynamics"            "${REGISTRY}/tlm-sterodynamics:0.3.2"
pull_image "facts-total"                      "${REGISTRY}/facts-total:0.1.4"
pull_image "extremesealevel-pointsoverthreshold"             "${REGISTRY}/extremesealevel-pointsoverthreshold:0.2.0"


# # =============================================================================
# #  extremesealevel step. 
# # Run for local outputs from each workflow in experiment.
# # =============================================================================

# log "=== Stage 4: extremesealevel2-afs shortcut ==="

# BINDS=(
#     "--bind=${MODULE_IN}/extremesealevel-pointsoverthreshold:/mnt/module_specific_in"
#     "--bind=${SHARED_IN}:/mnt/shared_in"
#     "--bind=${OUTPUT_DIR}:/mnt/out"
# )

# _run_service "extremesealevel-pointsoverthreshold" \
#     --pipeline-id=${PIPELINE_ID} \
#     --nsamps=${NSAMPS} \
#     --min-days=250 \
#     --min-years=20 \
#     --match-lim=0.1 \
#     --center-year=2000 \
#     --pct-pot=95 \
#     --gpd-pot-threshold=99.7 \
#     --cluster-lim=72 \
#     --min-z=0.5 \
#     --max-z=8.0 \
#     --quantile-min=0.01 \
#     --quantile-max=0.99 \
#     --quantile-step=0.01 \
#     --allowance-freq=0.01 \
#     --output-dir=/mnt/out/extremesealevel-pointsoverthreshold-${WORKFLOW1_NAME} \
#     --seed=2413 \
#     --total-localsl-file=/mnt/out/facts-total-${WORKFLOW1_NAME}/local_total.nc \
#     --gesla-dir=/mnt/module_specific_in/gesla_data

# run_service "extremesealevel-pointsoverthreshold" \
#     --pipeline-id=${PIPELINE_ID} \
#     --nsamps=${NSAMPS} \
#     --min-days=250 \
#     --min-years=20 \
#     --match-lim=0.1 \
#     --center-year=2000 \
#     --pct-pot=95 \
#     --gpd-pot-threshold=99.7 \
#     --cluster-lim=72 \
#     --min-z=0.5 \
#     --max-z=8.0 \
#     --quantile-min=0.01 \
#     --quantile-max=0.99 \
#     --quantile-step=0.01 \
#     --allowance-freq=0.01 \
#     --output-dir=/mnt/out/extremesealevel-pointsoverthreshold-${WORKFLOW2_NAME} \
#     --seed=2413 \
#     --total-localsl-file=/mnt/out/facts-total-${WORKFLOW2_NAME}/local_total.nc \
#     --gesla-dir=/mnt/module_specific_in/gesla_data

# =============================================================================
# =============================================================================
                    # Running the experiment modules
# =============================================================================
# Modules with no dependencies (Climate step and sea-level modules that don't use output from climate step)
# =============================================================================
# =============================================================================

log "=== Stage 1: independent services ==="

# --- fair-temperature --- 
BINDS=(
    "--bind=${MODULE_IN}/fair-temperature:/mnt/module_specific_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "fair-temperature" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --scenario=${SCENARIO} \
    --cyear-start=1850 \
    --cyear-end=1900 \
    --smooth-win=19 \
    --seed=2314 \
    --rcmip-file=/mnt/module_specific_in/rcmip/rcmip-emissions-annual-means-v5-1-0.csv \
    --param-file=/mnt/module_specific_in/parameters/fair_ar6_climate_params_v4.0.nc \
    --output-oceantemp-file=/mnt/out/fair-temperature/oceantemp.nc \
    --output-climate-file=/mnt/out/fair-temperature/climate.nc \
    --output-ohc-file=/mnt/out/fair-temperature/ohc.nc \
    --output-gsat-file=/mnt/out/fair-temperature/gsat.nc 


# --- ssp-lws ---
BINDS=(
    "--bind=${MODULE_IN}/ssp-landwaterstorage:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "ssp-landwaterstorage" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --scenario="ssp2" \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --location-file=/mnt/shared_in/location.lst \
    --fp-file=/mnt/module_specific_in/REL_GROUNDWATER_NOMASK.nc \
    --dcyear-start=2020 \
    --dcyear-end=2040 \
    --chunksize=50 \
    --seed=1243 \
    "--pophist-file=/mnt/module_specific_in/UNWPP2012 population historical.csv" \
    "--reservoir-file=/mnt/module_specific_in/Chao2008 groundwater impoundment.csv" \
    "--popscen-file=/mnt/module_specific_in/ssp_iam_baseline_popscenarios2100.csv" \
    "--gwd-file=/mnt/module_specific_in/Konikow2011 GWD.csv" \
    "--gwd-file=/mnt/module_specific_in/Wada2012 GWD.csv" \
    --output-gslr-file=/mnt/out/ssp-landwaterstorage/gslr.nc \
    --output-lslr-file=/mnt/out/ssp-landwaterstorage/lslr.nc

# --- kopp14-verticallandmotion (no depends_on) ---------------------------
BINDS=(
     "--bind=${MODULE_IN}/kopp14-verticallandmotion:/mnt/module_specific_in"
     "--bind=${SHARED_IN}:/mnt/shared_in"
     "--bind=${OUTPUT_DIR}:/mnt/out"
 )
run_service "kopp14-verticallandmotion" \
     --pipeline-id=${PIPELINE_ID} \
     --nsamps=${NSAMPS} \
     --baseyear=${BASEYEAR} \
     --pyear-start=${PYEAR_START} \
     --pyear-end=${PYEAR_END} \
     --pyear-step=${PYEAR_STEP} \
     --location-file=/mnt/shared_in/location.lst \
     --chunk-size=50 \
     --rng-seed=5678 \
     --rate-file=/mnt/module_specific_in/bkgdrate-210306.tsv \
     --output-lslr-file=/mnt/out/kopp14-verticallandmotion/lslr.nc




# Stage 2 - sealevel modules using climate output
log "=== Stage 2: services depending on climate step ==="
wait_for_output "${OUTPUT_DIR}/fair-temperature/climate.nc" "fair-temperature"
wait_for_output "${OUTPUT_DIR}/fair-temperature/gsat.nc" "fair-temperature"

# =============================================================================
# Modules with dependencies (sea-level modules that don't use output from climate step)
# =============================================================================

# -- fittedismip gris ---
BINDS=(
    "--bind=${MODULE_IN}/fittedismip-gris:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "fittedismip-gris" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --baseyear=${BASEYEAR} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --scenario=${SCENARIO} \
    --location-file=/mnt/shared_in/location.lst \
    --fingerprint-dir=/mnt/shared_in/FPRINT \
    --tlm-flag=1 \
    --cyear-end=2100 \
    --chunksize=50 \
    --rngseed=1432 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --gris-parm-file=/mnt/module_specific_in/FittedParms_GrIS_ALL.csv \
    --wais-parm-file=/mnt/module_specific_in/FittedParms_AIS_WAIS.csv \
    --eais-parm-file=/mnt/module_specific_in/FittedParms_AIS_EAIS.csv \
    --pen-parm-file=/mnt/module_specific_in/FittedParms_AIS_PEN.csv \
    --gris-global-out-file=/mnt/out/fittedismip-gris/gris-global-out.nc \
    --gris-local-out-file=/mnt/out/fittedismip-gris/gris-local-out.nc

# --- deconto21-ais ---
BINDS=(
    "--bind=${MODULE_IN}/deconto21-ais:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "deconto21-ais" \
    --pipeline-id=${PIPELINE_ID} \
    --scenario=${SCENARIO} \
    --nsamps=${NSAMPS} \
    --rngseed=1234 \
    --baseyear=${BASEYEAR} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --fingerprint-dir=/mnt/shared_in/FPRINT \
    --location-file=/mnt/shared_in/location.lst \
    --replace=True \
    --chunksize=50 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --input-eais-rcp26-file=/mnt/module_specific_in/dp21_eais_rcp26.nc \
    --input-eais-rcp45-file=/mnt/module_specific_in/dp21_eais_rcp45.nc \
    --input-eais-rcp85-file=/mnt/module_specific_in/dp21_eais_rcp85.nc \
    --input-wais-rcp26-file=/mnt/module_specific_in/dp21_wais_rcp26.nc \
    --input-wais-rcp45-file=/mnt/module_specific_in/dp21_wais_rcp45.nc \
    --input-wais-rcp85-file=/mnt/module_specific_in/dp21_wais_rcp85.nc \
    --output-ais-gslr-file=/mnt/out/deconto21-ais/ais-gslr.nc \
    --output-eais-gslr-file=/mnt/out/deconto21-ais/eais-gslr.nc \
    --output-wais-gslr-file=/mnt/out/deconto21-ais/wais-gslr.nc \
    --output-ais-lslr-file=/mnt/out/deconto21-ais/ais-lslr.nc \
    --output-eais-lslr-file=/mnt/out/deconto21-ais/eais-lslr.nc \
    --output-wais-lslr-file=/mnt/out/deconto21-ais/wais-lslr.nc

# --- larmip-ais ---
BINDS=(
    "--bind=${MODULE_IN}/larmip-ais:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "larmip-ais" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --baseyear=${BASEYEAR} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --scenario=${SCENARIO} \
    --location-file=/mnt/shared_in/location.lst \
    --fingerprint-dir=/mnt/shared_in/FPRINT \
    --refyear-start=1850 \
    --refyear-end=1900 \
    --year-start=1900 \
    --year-end=2300 \
    --seed=1342 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --scaling-coefficients-dir=/mnt/module_specific_in/ScalingCoefficients \
    --r-functions-dir=/mnt/module_specific_in/RFunctions \
    --ais-global-output-file=/mnt/out/larmip-ais/ais_global_output.nc \
    --eais-global-output-file=/mnt/out/larmip-ais/eais_global_output.nc \
    --wais-global-output-file=/mnt/out/larmip-ais/wais_global_output.nc \
    --pen-global-output-file=/mnt/out/larmip-ais/pen_global_output.nc \
    --smb-global-output-file=/mnt/out/larmip-ais/smb_global_output.nc \
    --wais-local-output-file=/mnt/out/larmip-ais/wais_local_output.nc \
    --eais-local-output-file=/mnt/out/larmip-ais/eais_local_output.nc \
    --ais-local-output-file=/mnt/out/larmip-ais/ais_local_output.nc

# --- ipccar5-glaciers ---
BINDS=(
    "--bind=${MODULE_IN}/ipccar5:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "ipccar5-glaciers" \
    glaciers \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --scenario=${SCENARIO} \
    --location-file=/mnt/shared_in/location.lst \
    --fingerprint-dir=/mnt/shared_in/FPRINT \
    --refyear-start=1986 \
    --refyear-end=2005 \
    --end-year=2301 \
    --tlm-flag=1 \
    --rng-seed=2143 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --glacier-fraction-file=/mnt/module_specific_in/glacier_fraction.txt \
    --global-output-file=/mnt/out/ipccar5-glaciers/global-output.nc \
    --local-output-file=/mnt/out/ipccar5-glaciers/local-output.nc

# --- ipccar5 - icesheets --- 
run_service "ipccar5-icesheets" \
    icesheets \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --scenario=${SCENARIO} \
    --location-file=/mnt/shared_in/location.lst \
    --fingerprint-dir=/mnt/shared_in/FPRINT \
    --refyear-start=1986 \
    --refyear-end=2005 \
    --tlm-flag=1 \
    --rng-seed=1423 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --icesheet-fraction-file=/mnt/module_specific_in/icesheet_fraction.txt \
    --global-gis-output-file=/mnt/out/ipccar5-icesheets/global-gis-output.nc \
    --global-ais-output-file=/mnt/out/ipccar5-icesheets/global-ais-output.nc \
    --global-wais-output-file=/mnt/out/ipccar5-icesheets/global-wais-output.nc \
    --global-eais-output-file=/mnt/out/ipccar5-icesheets/global-eais-output.nc \
    --local-gis-output-file=/mnt/out/ipccar5-icesheets/local-gis-output.nc \
    --local-ais-output-file=/mnt/out/ipccar5-icesheets/local-ais-output.nc \
    --local-wais-output-file=/mnt/out/ipccar5-icesheets/local-wais-output.nc \
    --local-eais-output-file=/mnt/out/ipccar5-icesheets/local-eais-output.nc 

# --- tlm-sterodynamics ---
BINDS=(
    "--bind=${MODULE_IN}/tlm-sterodynamics:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)
run_service "tlm-sterodynamics" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --scenario=${SCENARIO} \
    --baseyear=${BASEYEAR} \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --location-file=/mnt/shared_in/location.lst \
    --seed=4321 \
    --climate-data-file=/mnt/out/fair-temperature/climate.nc \
    --model-dir=/mnt/module_specific_in/cmip6/ \
    --expansion-coefficients-file=/mnt/module_specific_in/scmpy2LM_RCMIP_CMIP6calpm_n18_expcoefs.nc \
    --gsat-rmses-file=/mnt/module_specific_in/scmpy2LM_RCMIP_CMIP6calpm_n17_gsat_rmse.nc \
    --output-gslr-file=/mnt/out/tlm-sterodynamics/gslr.nc \
    --output-lslr-file=/mnt/out/tlm-sterodynamics/lslr.nc

# =============================================================================
#                          Totaling step
# Runs totaling step on local and global outputs for each workflow 
# defined in the experiment.
# =============================================================================

log "=== Stage 3: facts-total ==="

BINDS=(
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/total_out"
)
#run totaling service for workflow1 (global)
run_service "facts-total" \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --item=/mnt/total_out/fittedismip-gris/gris-global-out.nc \
    --item=/mnt/total_out/larmip-ais/ais_global_output.nc \
    --item=/mnt/total_out/ipccar5-glaciers/global-output.nc \
    --item=/mnt/total_out/ipccar5-icesheets/global-ais-output.nc \
    --item=/mnt/total_out/ipccar5-icesheets/global-gis-output.nc \
    --item=/mnt/total_out/tlm-sterodynamics/gslr.nc \
    --item=/mnt/total_out/ssp-landwaterstorage/gslr.nc \
    --output-path=/mnt/total_out/facts-total-${WORKFLOW1_NAME}/global_total.nc &
PID_TOTAL_GLOBAL_1=$!

# run totaling service for workflow2 (global)
run_service "facts-total" \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --item=/mnt/total_out/fittedismip-gris/gris-global-out.nc \
    --item=/mnt/total_out/larmip-ais/ais_global_output.nc \
    --item=/mnt/total_out/ipccar5-glaciers/global-output.nc \
    --item=/mnt/total_out/tlm-sterodynamics/gslr.nc \
    --item=/mnt/total_out/ssp-landwaterstorage/gslr.nc \
    --output-path=/mnt/total_out/facts-total-${WORKFLOW2_NAME}/global_total.nc &
PID_TOTAL_GLOBAL_2=$!

# run totaling service for workflow1 (local)
run_service "facts-total" \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --item=/mnt/total_out/fittedismip-gris/gris-local-out.nc \
    --item=/mnt/total_out/larmip-ais/ais_local_output.nc \
    --item=/mnt/total_out/ipccar5-glaciers/local-output.nc \
    --item=/mnt/total_out/ipccar5-icesheets/local-ais-output.nc \
    --item=/mnt/total_out/ipccar5-icesheets/local-gis-output.nc \
    --item=/mnt/total_out/tlm-sterodynamics/lslr.nc \
    --item=/mnt/total_out/kopp14-verticallandmotion/lslr.nc \
    --item=/mnt/total_out/ssp-landwaterstorage/lslr.nc \
    --output-path=/mnt/total_out/facts-total-${WORKFLOW1_NAME}/local_total.nc &
 PID_TOTAL_LOCAL_1=$!

# run totaling service for workflow2 (local)
run_service "facts-total" \
    --pyear-start=${PYEAR_START} \
    --pyear-end=${PYEAR_END} \
    --pyear-step=${PYEAR_STEP} \
    --item=/mnt/total_out/fittedismip-gris/gris-local-out.nc \
    --item=/mnt/total_out/larmip-ais/ais_local_output.nc \
    --item=/mnt/total_out/ipccar5-glaciers/local-output.nc \
    --item=/mnt/total_out/tlm-sterodynamics/lslr.nc \
    --item=/mnt/total_out/kopp14-verticallandmotion/lslr.nc \
    --item=/mnt/total_out/ssp-landwaterstorage/lslr.nc \
    --output-path=/mnt/total_out/facts-total-${WORKFLOW2_NAME}/local_total.nc &
 PID_TOTAL_LOCAL_2=$!

wait $PID_TOTAL_GLOBAL_1 || { echo "ERROR: wf1f facts-total global failed" >&2; exit 1; }
wait $PID_TOTAL_LOCAL_1  || { echo "ERROR: wf1f facts-total local failed" >&2; exit 1; }
wait $PID_TOTAL_GLOBAL_2 || { echo "ERROR: wf2f facts-total global failed" >&2; exit 1; }
wait $PID_TOTAL_LOCAL_2  || { echo "ERROR: wf2f facts-total local failed" >&2; exit 1; }

# =============================================================================
#  extremesealevel step. 
# Run for local outputs from each workflow in experiment.
# =============================================================================

log "=== Stage 4: extremesealevel2-afs ==="

BINDS=(
    "--bind=${MODULE_IN}/extremesealevel-pointsoverthreshold:/mnt/module_specific_in"
    "--bind=${SHARED_IN}:/mnt/shared_in"
    "--bind=${OUTPUT_DIR}:/mnt/out"
)

run_service "extremesealevel-pointsoverthreshold" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --min-days=250 \
    --min-years=20 \
    --match-lim=0.1 \
    --center-year=2000 \
    --pct-pot=95 \
    --gpd-pot-threshold=99.7 \
    --cluster-lim=72 \
    --min-z=0.5 \
    --max-z=8.0 \
    --quantile-min=0.01 \
    --quantile-max=0.99 \
    --quantile-step=0.01 \
    --allowance-freq=0.01 \
    --output-dir=/mnt/out/extremesealevel-pointsoverthreshold-${WORKFLOW1_NAME} \
    --seed=2413 \
    --total-localsl-file=/mnt/out/facts-total-${WORKFLOW1_NAME}/local_total.nc \
    --gesla-dir=/mnt/module_specific_in/gesla_data

run_service "extremesealevel-pointsoverthreshold" \
    --pipeline-id=${PIPELINE_ID} \
    --nsamps=${NSAMPS} \
    --min-days=250 \
    --min-years=20 \
    --match-lim=0.1 \
    --center-year=2000 \
    --pct-pot=95 \
    --gpd-pot-threshold=99.7 \
    --cluster-lim=72 \
    --min-z=0.5 \
    --max-z=8.0 \
    --quantile-min=0.01 \
    --quantile-max=0.99 \
    --quantile-step=0.01 \
    --allowance-freq=0.01 \
    --output-dir=/mnt/out/extremesealevel-pointsoverthreshold-${WORKFLOW2_NAME} \
    --seed=2413 \
    --total-localsl-file=/mnt/out/facts-total-${WORKFLOW2_NAME}/local_total.nc \
    --gesla-dir=/mnt/module_specific_in/gesla_data

log "=== All services completed successfully ==="
