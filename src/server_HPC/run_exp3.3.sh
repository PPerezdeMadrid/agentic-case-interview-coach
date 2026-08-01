#!/bin/bash
#SBATCH --job-name=exp3.1
#SBATCH --account=compsci
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --partition=small-long
#SBATCH --time=30:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

RUN_LABEL="exp3.3"
REPEAT="${N:-4}"

echo "Starting experiment batch '$RUN_LABEL'"

source /software/conda/$USER/conda/etc/profile.d/conda.sh
conda activate coach

# Prevent shadowing of conda env packages by ~/.local user site-packages
export PYTHONNOUSERSITE=1

# SLURM copies the batch script to a local scratch dir, so use the original
# submission directory when available.
SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$SCRIPT_DIR/logs" "$SRC_DIR/logs"

cd "$SRC_DIR"

RUN_ALL_LOG="$SRC_DIR/logs/run_all_scenarios_${RUN_LABEL}_${SLURM_JOB_ID:-local}.log"

echo "Running make run-all (RUNNER=hpc, LABEL=$RUN_LABEL, N=$REPEAT)..."

make run-all RUNNER=hpc LABEL="$RUN_LABEL" N="$REPEAT" 2>&1 | tee "$RUN_ALL_LOG"
