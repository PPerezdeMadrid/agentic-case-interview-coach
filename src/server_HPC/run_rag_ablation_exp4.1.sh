#!/bin/bash
#SBATCH --job-name=rag-exp4.1
#SBATCH --account=compsci
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --partition=small-long
#SBATCH --time=30:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

BATCH="${BATCH:-20260801T173045Z_exp4.1}"
RUN_LABEL="${RUN_LABEL:-exp4.1}"
LIMIT="${LIMIT:-}"

echo "Starting RAG ablation for batch '$BATCH'"

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

RAG_LOG="$SRC_DIR/logs/rag_ablation_${RUN_LABEL}_${SLURM_JOB_ID:-local}.log"

echo "Running make rag-ablation (RUNNER=hpc, BATCH=$BATCH${LIMIT:+, LIMIT=$LIMIT})..."
if [ -n "$LIMIT" ]; then
    make rag-ablation RUNNER=hpc BATCH="$BATCH" LIMIT="$LIMIT" 2>&1 | tee "$RAG_LOG"
else
    make rag-ablation RUNNER=hpc BATCH="$BATCH" 2>&1 | tee "$RAG_LOG"
fi

exit ${PIPESTATUS[0]}
