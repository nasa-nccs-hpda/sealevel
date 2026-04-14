#!/bin/bash
################################################################################
# facts_benchmark.sh - Comprehensive FACTS workflow benchmarking script
################################################################################

set -u

# Configuration
SUBMIT_SCRIPT="./submit_facts.sh"
BENCHMARK_DIR="/discover/nobackup/$USER/facts_benchmarks/$(date +%Y%m%d_%H%M%S)"
RESULTS_FILE="${BENCHMARK_DIR}/benchmark_results.tsv"
REPORT_FILE="${BENCHMARK_DIR}/benchmark_report.txt"
SUMMARY_FILE="${BENCHMARK_DIR}/benchmark_summary.md"
LOG_FILE="${BENCHMARK_DIR}/benchmark.log"
ANALYSIS_SCRIPT="./analyze_benchmark.py"

# Create benchmark directory
mkdir -p "${BENCHMARK_DIR}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log "Starting FACTS Benchmark Suite"
log "Benchmark directory: ${BENCHMARK_DIR}"

# Check if submit script exists
if [ ! -f "${SUBMIT_SCRIPT}" ]; then
    log "ERROR: Submit script not found: ${SUBMIT_SCRIPT}"
    exit 1
fi

# Check if analysis script exists
if [ ! -f "${ANALYSIS_SCRIPT}" ]; then
    log "ERROR: Analysis script not found: ${ANALYSIS_SCRIPT}"
    log "Please create analyze_benchmark.py in the current directory"
    exit 1
fi

################################################################################
# Define Test Configurations
################################################################################
declare -a CONFIGS=(
    # Small configurations
    "small_basic|datamove||1|1|4GB|01:00:00|Basic small test (datamove, 1 CPUs, 4GB)"
    "small_basic|compute||1|1|4GB|01:00:00|Basic small test (compute, 1 CPUs, 4GB)"
    "small_basic|gpu_a100||1|1|4GB|01:00:00|Basic small test (gpu_a100, 1 CPUs, 4GB)"
    #"small_basic|datamove||1|4|16GB|01:00:00|Basic small test (4 CPUs, 16GB)"
#    "small_mid|compute||1|8|32GB|02:00:00|Small with more resources (8 CPUs, 32GB)"
)

declare -a _CONFIGS=(
    # Small configurations
    "small_basic|compute||1|4|16GB|01:00:00|Basic small test (4 CPUs, 16GB)"
    "small_mid|compute||1|8|32GB|02:00:00|Small with more resources (8 CPUs, 32GB)"
    
    # Medium configurations
    "medium_basic|compute||1|16|64GB|04:00:00|Medium baseline (16 CPUs, 64GB)"
    "medium_high|compute||1|24|96GB|06:00:00|Medium with high resources (24 CPUs, 96GB)"
    
    # Large configurations
    "large_basic|compute||1|32|128GB|12:00:00|Large baseline (32 CPUs, 128GB)"
    "large_high|compute||1|48|192GB|12:00:00|Large high resources (48 CPUs, 192GB)"
    
    # Multi-node configurations
    "multinode_2|compute|2|2|16|64GB|08:00:00|2 nodes, 16 CPUs per node"
    "multinode_4|compute|4|4|16|64GB|08:00:00|4 nodes, 16 CPUs per node"
    
    # Memory-focused configurations
    "mem_optimized|bigmem||1|16|256GB|12:00:00|Memory optimized (256GB)"
    
    # Long-running configurations
    "long_basic|long||1|16|64GB|24:00:00|Long partition baseline"
)

################################################################################
# Submit Jobs
################################################################################

log "Submitting ${#CONFIGS[@]} benchmark configurations..."

declare -A JOB_IDS
declare -A JOB_CONFIGS
declare -A JOB_SUBMIT_TIMES

for config in "${CONFIGS[@]}"; do
    IFS='|' read -r name partition nodes ntasks cpus mem time desc <<< "$config"
    
    log "Submitting: $name - $desc"
    
    # Build submit command
    cmd=("${SUBMIT_SCRIPT}")
    cmd+=("--job-name" "bench_${name}")
    cmd+=("--partition" "$partition")
    cmd+=("--ntasks" "$ntasks")
    cmd+=("--cpus-per-task" "$cpus")
    cmd+=("--time" "$time")
    cmd+=("--output" "${BENCHMARK_DIR}/${name}_%j.out")
    cmd+=("--error" "${BENCHMARK_DIR}/${name}_%j.err")
    
    # Add optional parameters
    [ -n "$nodes" ] && cmd+=("--nodes" "$nodes")
    [ -n "$mem" ] && cmd+=("--mem" "$mem")
    
    # Submit job
    submit_output=$("${cmd[@]}" 2>&1)
    submit_status=$?
    
    if [ $submit_status -eq 0 ]; then
        job_id=$(echo "$submit_output" | grep -oP 'Submitted batch job \K\d+')
        if [ -n "$job_id" ]; then
            JOB_IDS[$name]=$job_id
            JOB_CONFIGS[$job_id]=$config
            JOB_SUBMIT_TIMES[$job_id]=$(date +%s)
            log "  Submitted: $name (Job ID: $job_id)"
        else
            log "  ERROR: Could not extract job ID for $name"
        fi
    else
        log "  ERROR: Failed to submit $name"
        log "  Output: $submit_output"
    fi
    
    sleep 2
done

log "Submitted ${#JOB_IDS[@]} jobs successfully"

# Save job mapping
JOB_MAP_FILE="${BENCHMARK_DIR}/job_mapping.txt"
for name in "${!JOB_IDS[@]}"; do
    echo "${name}|${JOB_IDS[$name]}|${JOB_CONFIGS[${JOB_IDS[$name]}]}" >> "${JOB_MAP_FILE}"
done

################################################################################
# Monitor Jobs
################################################################################

log "Monitoring job completion..."

# Write initial results header
cat > "${RESULTS_FILE}" << EOF
Name	JobID	Partition	Nodes	NTasks	CPUsPerTask	Memory	TimeLimit	SubmitTime	StartTime	EndTime	ElapsedSec	State	ExitCode	MaxRSS_MB	AvgCPU	Description
EOF

# Function to get job info from sacct
get_job_info() {
    local job_id=$1
    sacct -j "$job_id" --format=JobID,State,ExitCode,MaxRSS,AveCPU,Submit,Start,End,Elapsed -P -n 2>/dev/null | grep "^${job_id}\\." | head -1
}

# Monitor until all jobs complete
declare -A JOB_COMPLETED
max_wait_time=172800  # 48 hours
start_monitor=$(date +%s)

while true; do
    all_done=true
    pending_count=0
    running_count=0
    completed_count=0
    failed_count=0
    
    for name in "${!JOB_IDS[@]}"; do
        job_id=${JOB_IDS[$name]}
        
        if [ "${JOB_COMPLETED[$job_id]:-0}" -eq 1 ]; then
            ((completed_count++))
            continue
        fi
        
        # Check job status
        job_state=$(squeue -j "$job_id" -h -o "%T" 2>/dev/null)
        
        if [ -z "$job_state" ]; then
            # Job not in queue - check if completed
            job_info=$(get_job_info "$job_id")
            
            if [ -n "$job_info" ]; then
                IFS='|' read -r job_id_full state exit_code max_rss avg_cpu submit_time start_time end_time elapsed <<< "$job_info"
                
                # Parse configuration
                IFS='|' read -r cfg_name cfg_partition cfg_nodes cfg_ntasks cfg_cpus cfg_mem cfg_time cfg_desc <<< "${JOB_CONFIGS[$job_id]}"
                
                # Convert MaxRSS to MB
                max_rss_mb="0"
                if [[ "$max_rss" =~ ^([0-9.]+)([KMG]?)$ ]]; then
                    rss_value="${BASH_REMATCH[1]}"
                    rss_unit="${BASH_REMATCH[2]}"
                    case "$rss_unit" in
                        K) max_rss_mb=$(echo "scale=2; $rss_value / 1024" | bc 2>/dev/null || echo "0") ;;
                        M) max_rss_mb=$rss_value ;;
                        G) max_rss_mb=$(echo "scale=2; $rss_value * 1024" | bc 2>/dev/null || echo "0") ;;
                        *) max_rss_mb=$rss_value ;;
                    esac
                fi
                
                # Convert elapsed time to seconds
                elapsed_sec=$(echo "$elapsed" | awk -F: '{ if (NF==3) print ($1 * 3600) + ($2 * 60) + $3; else if (NF==2) print ($1 * 60) + $2; else print $1 }')
                
                # Write to results file
                echo -e "${cfg_name}\t${job_id}\t${cfg_partition}\t${cfg_nodes}\t${cfg_ntasks}\t${cfg_cpus}\t${cfg_mem}\t${cfg_time}\t${submit_time}\t${start_time}\t${end_time}\t${elapsed_sec}\t${state}\t${exit_code}\t${max_rss_mb}\t${avg_cpu}\t${cfg_desc}" >> "${RESULTS_FILE}"
                
                JOB_COMPLETED[$job_id]=1
                
                if [[ "$state" == "COMPLETED" ]]; then
                    log "  ✓ Completed: $cfg_name (Job $job_id) - ${elapsed}"
                    ((completed_count++))
                else
                    log "  ✗ Failed: $cfg_name (Job $job_id) - State: $state"
                    ((failed_count++))
                fi
            else
                all_done=false
                ((pending_count++))
            fi
        else
            all_done=false
            if [[ "$job_state" == "RUNNING" ]]; then
                ((running_count++))
            else
                ((pending_count++))
            fi
        fi
    done
    
    if [ $all_done = false ]; then
        log "Status: Pending=$pending_count, Running=$running_count, Completed=$completed_count, Failed=$failed_count"
    fi
    
    if [ $all_done = true ]; then
        log "All jobs completed!"
        break
    fi
    
    # Check timeout
    current_time=$(date +%s)
    elapsed=$((current_time - start_monitor))
    if [ $elapsed -gt $max_wait_time ]; then
        log "WARNING: Maximum wait time exceeded."
        break
    fi
    
    sleep 60
done

################################################################################
# Analyze Results
################################################################################

log "Analyzing benchmark results..."

# Create initial report header
cat > "${REPORT_FILE}" << 'REPORT_HEADER'
================================================================================
                    FACTS Workflow Benchmark Report
================================================================================

REPORT_HEADER

echo "Generated: $(date)" >> "${REPORT_FILE}"
echo "Benchmark Directory: ${BENCHMARK_DIR}" >> "${REPORT_FILE}"
echo "" >> "${REPORT_FILE}"

# Run Python analysis script
log "Running analysis script..."
python3 "${ANALYSIS_SCRIPT}" "${RESULTS_FILE}" "${REPORT_FILE}" "${SUMMARY_FILE}" 2>&1 | tee -a "${LOG_FILE}"

if [ $? -eq 0 ]; then
    log "Analysis completed successfully"
else
    log "ERROR: Analysis script failed"
fi

################################################################################
# Final Summary
################################################################################

log ""
log "=" * 80
log "Benchmark Complete!"
log "=" * 80
log ""
log "Results saved to:"
log "  Data: ${RESULTS_FILE}"
log "  Report: ${REPORT_FILE}"
log "  Summary: ${SUMMARY_FILE}"
log "  Log: ${LOG_FILE}"
log ""

# Display summary if available
if [ -f "${SUMMARY_FILE}" ]; then
    log "Summary generated successfully. Displaying first 100 lines:"
    head -100 "${SUMMARY_FILE}"
else
    log "WARNING: Summary file was not created"
fi

exit 0
