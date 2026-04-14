#!/bin/bash

# Default values
DEFAULT_JOB_NAME="fair_facts_v2"
DEFAULT_OUTPUT="fair_facts_%j.out"
DEFAULT_ERROR="fair_facts_%j.err"
DEFAULT_TIME="04:00:00"
DEFAULT_NODES=""
DEFAULT_NTASKS="1"
DEFAULT_CPUS_PER_TASK="16"
DEFAULT_MEM="64GB"
DEFAULT_MEM_PER_CPU=""
DEFAULT_PARTITION="jh"
#DEFAULT_PARTITION="compute"
DEFAULT_ACCOUNT="ilab"
DEFAULT_MAIL_TYPE="END,FAIL"
DEFAULT_MAIL_USER="your.email@nasa.gov"
DEFAULT_PYTHON_SCRIPT="/discover/nobackup/projects/eis_freshwater/gtamkin/facts2.0/notebooks/1_fair_facts_v2_aggregate_full_sbatch.py"
DEFAULT_WORK_DIR="/discover/nobackup/\$USER/facts_work"
DEFAULT_OUTPUT_DIR="/discover/nobackup/projects/sealevel/facts_outputs"

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Submit FACTS workflow job to SLURM with configurable resources.

OPTIONS:
    --job-name NAME          Job name (default: $DEFAULT_JOB_NAME)
    --output FILE            Standard output file (default: $DEFAULT_OUTPUT)
    --error FILE             Standard error file (default: $DEFAULT_ERROR)
    --time TIME              Wall time limit HH:MM:SS (default: $DEFAULT_TIME)
    --nodes N                Number of nodes (default: auto)
    --ntasks N               Number of tasks (default: $DEFAULT_NTASKS)
    --cpus-per-task N        CPUs per task (default: $DEFAULT_CPUS_PER_TASK)
    --mem SIZE               Memory per node (default: $DEFAULT_MEM)
    --mem-per-cpu SIZE       Memory per CPU (alternative to --mem)
    --partition NAME         Partition name (default: $DEFAULT_PARTITION)
    --account NAME           Account to charge (default: $DEFAULT_ACCOUNT)
    --mail-type TYPE         Email notification type (default: $DEFAULT_MAIL_TYPE)
    --mail-user EMAIL        Email address (default: $DEFAULT_MAIL_USER)
    --gres RESOURCE          Generic resources (e.g., gpu:1)
    --constraint CONSTRAINT  Node constraint (e.g., v100)
    --exclusive              Request exclusive node access
    --python-script PATH     Python script to execute (default: $DEFAULT_PYTHON_SCRIPT)
    --work-dir PATH          Working directory base (default: $DEFAULT_WORK_DIR)
    --output-dir PATH        Output directory base (default: $DEFAULT_OUTPUT_DIR)
    --dry-run                Print SBATCH script without submitting
    --help                   Display this help message

EXAMPLES:
    # Use defaults
    $0

    # Custom resources
    $0 --cpus-per-task 32 --mem 128GB --time 48:00:00

    # GPU job
    $0 --partition gpu --gres gpu:2 --cpus-per-task 8

    # Multi-node job
    $0 --nodes 4 --ntasks 4 --mem-per-cpu 4GB

    # Dry run
    $0 --dry-run --nodes 8 --cpus-per-task 32

EOF
    exit 0
}

# Parse command line arguments
JOB_NAME="$DEFAULT_JOB_NAME"
OUTPUT="$DEFAULT_OUTPUT"
ERROR="$DEFAULT_ERROR"
TIME="$DEFAULT_TIME"
NODES="$DEFAULT_NODES"
NTASKS="$DEFAULT_NTASKS"
CPUS_PER_TASK="$DEFAULT_CPUS_PER_TASK"
MEM="$DEFAULT_MEM"
MEM_PER_CPU="$DEFAULT_MEM_PER_CPU"
PARTITION="$DEFAULT_PARTITION"
ACCOUNT="$DEFAULT_ACCOUNT"
MAIL_TYPE="$DEFAULT_MAIL_TYPE"
MAIL_USER="$DEFAULT_MAIL_USER"
GRES=""
CONSTRAINT=""
EXCLUSIVE=""
PYTHON_SCRIPT="$DEFAULT_PYTHON_SCRIPT"
WORK_DIR="$DEFAULT_WORK_DIR"
OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --job-name)
            JOB_NAME="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        --error)
            ERROR="$2"
            shift 2
            ;;
        --time)
            TIME="$2"
            shift 2
            ;;
        --nodes)
            NODES="$2"
            shift 2
            ;;
        --ntasks)
            NTASKS="$2"
            shift 2
            ;;
        --cpus-per-task)
            CPUS_PER_TASK="$2"
            shift 2
            ;;
        --mem)
            MEM="$2"
            shift 2
            ;;
        --mem-per-cpu)
            MEM_PER_CPU="$2"
            shift 2
            ;;
        --partition)
            PARTITION="$2"
            shift 2
            ;;
        --account)
            ACCOUNT="$2"
            shift 2
            ;;
        --mail-type)
            MAIL_TYPE="$2"
            shift 2
            ;;
        --mail-user)
            MAIL_USER="$2"
            shift 2
            ;;
        --gres)
            GRES="$2"
            shift 2
            ;;
        --constraint)
            CONSTRAINT="$2"
            shift 2
            ;;
        --exclusive)
            EXCLUSIVE="yes"
            shift
            ;;
        --python-script)
            PYTHON_SCRIPT="$2"
            shift 2
            ;;
        --work-dir)
            WORK_DIR="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate mutually exclusive options
if [[ -n "$MEM" && -n "$MEM_PER_CPU" ]]; then
    echo "Error: Cannot specify both --mem and --mem-per-cpu"
    exit 1
fi

# Generate SBATCH script
SBATCH_SCRIPT=$(mktemp /tmp/facts_sbatch.XXXXXX)

cat > "$SBATCH_SCRIPT" << EOF
#!/bin/bash
#SBATCH --job-name=${JOB_NAME}
#SBATCH --output=${OUTPUT}
#SBATCH --error=${ERROR}
#SBATCH --time=${TIME}
#SBATCH --ntasks=${NTASKS}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --partition=${PARTITION}
#SBATCH --account=${ACCOUNT}
EOF

# Add optional SBATCH directives
[[ -n "$NODES" ]] && echo "#SBATCH --nodes=${NODES}" >> "$SBATCH_SCRIPT"
[[ -n "$MEM" ]] && echo "#SBATCH --mem=${MEM}" >> "$SBATCH_SCRIPT"
[[ -n "$MEM_PER_CPU" ]] && echo "#SBATCH --mem-per-cpu=${MEM_PER_CPU}" >> "$SBATCH_SCRIPT"
[[ -n "$GRES" ]] && echo "#SBATCH --gres=${GRES}" >> "$SBATCH_SCRIPT"
[[ -n "$CONSTRAINT" ]] && echo "#SBATCH --constraint=${CONSTRAINT}" >> "$SBATCH_SCRIPT"
[[ -n "$EXCLUSIVE" ]] && echo "#SBATCH --exclusive" >> "$SBATCH_SCRIPT"
[[ -n "$MAIL_TYPE" ]] && echo "#SBATCH --mail-type=${MAIL_TYPE}" >> "$SBATCH_SCRIPT"
[[ -n "$MAIL_USER" ]] && echo "#SBATCH --mail-user=${MAIL_USER}" >> "$SBATCH_SCRIPT"

# Add job execution content
cat >> "$SBATCH_SCRIPT" << 'EOF'

echo "========================================"
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Nodes allocated: $SLURM_JOB_NODELIST"
echo "Number of nodes: $SLURM_NNODES"
echo "CPUs per node: $SLURM_CPUS_ON_NODE"
echo "CPUs per task: $SLURM_CPUS_PER_TASK"
echo "Total tasks: $SLURM_NTASKS"
echo "Memory: $SLURM_MEM_PER_NODE MB per node"
echo "Partition: $SLURM_JOB_PARTITION"
echo "========================================"
scontrol show job $SLURM_JOB_ID

# Load required modules
module load python/GEOSpyD/24.3.0-0/3.11
module load singularity/4.0.3

# Load CUDA if GPU partition
if [[ "$SLURM_JOB_PARTITION" == "gpu" ]]; then
    module load cuda/11.8
    echo "Loaded CUDA module for GPU partition"
fi

# Set up environment
export SINGULARITY_CACHEDIR=/discover/nobackup/projects/sealevel/singularity_cache
export TMPDIR=/discover/nobackup/$USER/tmp
mkdir -p $TMPDIR $SINGULARITY_CACHEDIR

# Set threading based on allocated CPUs
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=$SLURM_CPUS_PER_TASK

EOF

# Add work directory setup with variable expansion
cat >> "$SBATCH_SCRIPT" << EOF
# Change to working directory
WORK_DIR="${WORK_DIR}/\${SLURM_JOB_ID}"
mkdir -p \${WORK_DIR}
cd \${WORK_DIR}

# Create data/output directory structure
mkdir -p ./data/output/fair
mkdir -p ./data/output/lws
mkdir -p ./data/output/sterodynamics
mkdir -p ./data/output/bamber
mkdir -p ./data/output/ipccar5_glaciers
mkdir -p ./data/output/ipccar5_icesheets
mkdir -p ./data/output/kopp14verticallandmotion

# Log job info
echo ""
echo "Working directory: \${WORK_DIR}"
echo "Python script: ${PYTHON_SCRIPT}"
echo "Start time: \$(date)"
echo ""

# Run the workflow
START_TIME=\$(date +%s)

python ${PYTHON_SCRIPT}

EXIT_CODE=\$?

END_TIME=\$(date +%s)
ELAPSED=\$((END_TIME - START_TIME))

echo ""
echo "========================================"
echo "End time: \$(date)"
echo "Exit code: \${EXIT_CODE}"
echo "Elapsed time: \${ELAPSED} seconds (\$((ELAPSED / 60)) minutes)"
echo "========================================"

# Copy outputs to permanent location if successful
if [ \$EXIT_CODE -eq 0 ]; then
    OUTPUT_DIR="${OUTPUT_DIR}/\${SLURM_JOB_ID}"
    mkdir -p \${OUTPUT_DIR}
    echo "Copying outputs to: \${OUTPUT_DIR}"
    cp -r ./data/output/* \${OUTPUT_DIR}/
    echo "Outputs copied successfully"
    echo "Output location: \${OUTPUT_DIR}"
else
    echo "Job failed with exit code \${EXIT_CODE}"
    echo "Check error log: ${ERROR}"
fi

exit \${EXIT_CODE}
EOF

# Handle dry-run or submit
if [ "$DRY_RUN" = true ]; then
    echo "========================================"
    echo "DRY RUN MODE - Generated SBATCH script:"
    echo "========================================"
    cat "$SBATCH_SCRIPT"
    echo "========================================"
    echo "Script not submitted (--dry-run specified)"
    rm "$SBATCH_SCRIPT"
    exit 0
fi

# Submit the job
echo "Submitting job with the following configuration:"
echo "  Job name: $JOB_NAME"
echo "  Partition: $PARTITION"
echo "  Nodes: ${NODES:-auto}"
echo "  Tasks: $NTASKS"
echo "  CPUs per task: $CPUS_PER_TASK"
if [[ -n "$MEM" ]]; then
    echo "  Memory: $MEM"
elif [[ -n "$MEM_PER_CPU" ]]; then
    echo "  Memory per CPU: $MEM_PER_CPU"
fi
echo "  Time limit: $TIME"
[[ -n "$GRES" ]] && echo "  GRES: $GRES"
[[ -n "$CONSTRAINT" ]] && echo "  Constraint: $CONSTRAINT"
echo ""

SUBMIT_OUTPUT=$(sbatch "$SBATCH_SCRIPT" 2>&1)
SUBMIT_STATUS=$?

if [ $SUBMIT_STATUS -eq 0 ]; then
    echo "$SUBMIT_OUTPUT"
    JOB_ID=$(echo "$SUBMIT_OUTPUT" | grep -oP 'Submitted batch job \K\d+')
    
    if [[ -n "$JOB_ID" ]]; then
        echo ""
        echo "Job submitted successfully!"
        echo "Job ID: $JOB_ID"
        echo ""
        echo "Monitor with:"
        echo "  squeue -j $JOB_ID"
        echo "  scontrol show job $JOB_ID"
        echo "  tail -f ${OUTPUT//%j/$JOB_ID}"
        echo ""
        echo "Cancel with:"
        echo "  scancel $JOB_ID"
    fi
else
    echo "Error submitting job:"
    echo "$SUBMIT_OUTPUT"
    rm "$SBATCH_SCRIPT"
    exit 1
fi

# Clean up temporary script
rm "$SBATCH_SCRIPT"

exit 0