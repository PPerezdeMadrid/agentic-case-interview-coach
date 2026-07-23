#!/bin/bash
#SBATCH --job-name=hf-llm-server-candidate-exp02HPC
#SBATCH --account=compsci
#SBATCH --partition=gpu.A100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=15:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# Brings up the candidate-only Mistral-Small-24B server (port 18403), then
# drives the full experiment batch against it (LABEL=exp02HPC): every role
# except candidate goes through OpenRouter, candidate is served locally here.
# If enough of the --time budget below is left afterwards, it replays that
# batch through make rag-ablation. Keep JOB_TIME_BUDGET_SECONDS in sync with
# --time above if you change it.

RUN_LABEL="exp02HPC"
REPEAT="${N:-4}"
JOB_TIME_BUDGET_SECONDS=$((20 * 3600))
RAG_ABLATION_MIN_REMAINING_SECONDS=$((30 * 60))

echo "Starting HF/FastAPI LLM server (Mistral-Small-24B, candidate only) + experiment batch '$RUN_LABEL'"

source /software/conda/$USER/conda/etc/profile.d/conda.sh
conda activate coach

# Prevent shadowing of conda env packages by ~/.local user site-packages
export PYTHONNOUSERSITE=1
export HF_HOME=/sharedscratch/$USER/huggingface

# SLURM copies the batch script to a local scratch dir on the compute node
# (e.g. /tmp/slurmd/jobNNNN/...) before running it, so BASH_SOURCE no longer
# points at the real submission directory there. Use SLURM_SUBMIT_DIR (set
# correctly by sbatch) when available, falling back to BASH_SOURCE for local/
# interactive runs outside SLURM.
SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$SCRIPT_DIR/logs" "$SRC_DIR/logs"

echo "GPU information:"
nvidia-smi

echo "Starting Mistral-Small-24B server on GPU 0..."
cd "$SCRIPT_DIR"
CUDA_VISIBLE_DEVICES=0 python server.py --model mistral-small > logs/mistral.log 2>&1 &
MISTRAL_PID=$!

wait_for_server() {
    local name="$1" port="$2" max_wait="${3:-1800}" interval="${4:-10}"
    local elapsed=0
    until curl -sf "http://127.0.0.1:${port}/v1/models" > /dev/null 2>&1; do
        if [ "$elapsed" -ge "$max_wait" ]; then
            echo "ERROR: $name server on port $port did not come up within ${max_wait}s"
            return 1
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        echo "  still waiting for $name on port $port... (${elapsed}s elapsed)"
    done
    echo "$name server on port $port is up (${elapsed}s)"
}

cleanup() {
    echo "Shutting down candidate server (PID $MISTRAL_PID)..."
    kill "$MISTRAL_PID" 2>/dev/null
}
trap cleanup EXIT

wait_for_server "Mistral-Small-24B" 18403 || exit 1
echo "Candidate server is up: http://127.0.0.1:18403/v1/models"

# --- Experiment batch: baseline + agentic across every scenario, N=$REPEAT ---
# RUNNER=hpc is passed explicitly on the make command line so this doesn't
# depend on whatever RUNNER got persisted by a prior 'make setup-hpc' run.
cd "$SRC_DIR"

RUN_ALL_LOG="$SRC_DIR/logs/run_all_scenarios_${RUN_LABEL}_${SLURM_JOB_ID:-local}.log"
echo "Running make run-all (RUNNER=hpc, LABEL=$RUN_LABEL, N=$REPEAT)..."
make run-all RUNNER=hpc LABEL="$RUN_LABEL" N="$REPEAT" 2>&1 | tee "$RUN_ALL_LOG"
RUN_ALL_STATUS=${PIPESTATUS[0]}

if [ "$RUN_ALL_STATUS" -ne 0 ]; then
    echo "ERROR: make run-all exited with status $RUN_ALL_STATUS -- skipping RAG ablation."
    exit "$RUN_ALL_STATUS"
fi

BATCH_ID=$(grep -o 'Batch finished: .*' "$RUN_ALL_LOG" | tail -1 | sed 's/Batch finished: //')
if [ -z "$BATCH_ID" ]; then
    echo "WARNING: could not determine batch_id from run-all output -- skipping RAG ablation."
    exit 0
fi
echo "run-all finished. batch_id=$BATCH_ID"

# --- Optional: RAG ablation on the batch just produced, if time allows ---
# Judge-only replay of stored transcripts (RAG disabled) via OpenRouter --
# it doesn't touch the candidate server, so it's cheap relative to run-all.
ELAPSED_SECONDS=$SECONDS
REMAINING_SECONDS=$((JOB_TIME_BUDGET_SECONDS - ELAPSED_SECONDS))
echo "Elapsed: ${ELAPSED_SECONDS}s, remaining budget: ${REMAINING_SECONDS}s"

if [ "$REMAINING_SECONDS" -lt "$RAG_ABLATION_MIN_REMAINING_SECONDS" ]; then
    echo "Not enough time budget left for RAG ablation (${REMAINING_SECONDS}s < ${RAG_ABLATION_MIN_REMAINING_SECONDS}s) -- skipping."
    exit 0
fi

echo "Running make rag-ablation BATCH=$BATCH_ID (RUNNER=hpc)..."
make rag-ablation BATCH="$BATCH_ID" RUNNER=hpc 2>&1 | tee "$SRC_DIR/logs/rag_ablation_${RUN_LABEL}_${SLURM_JOB_ID:-local}.log"