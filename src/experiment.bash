#!/bin/bash
#SBATCH --job-name=langgraph-agents-experiment
#SBATCH --account=compsci
#SBATCH --partition=gpu.A100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err


echo "Starting LangGraph multi-agent system (Mistral-only experiment)"

source /software/conda/$USER/conda/etc/profile.d/conda.sh
conda activate coach

# Prevent ~/.local user site-packages (e.g. a pip install --user'd vllm on
# system Python 3.9) from shadowing the packages installed in this conda env
export PYTHONNOUSERSITE=1

# Model weights are large; keep them off the backed-up home directory
export HF_HOME=/sharedscratch/$USER/huggingface

mkdir -p logs

echo "GPU information:"
nvidia-smi

# Start Candidate model (Mistral) — the only model used in this experiment

echo "Starting Mistral Candidate server..."

CUDA_VISIBLE_DEVICES=0 \
vllm serve mistralai/Mistral-Nemo-Instruct-2407 \
    --host 127.0.0.1 \
    --port 18401 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 32000 \
    > logs/mistral.log 2>&1 &

MISTRAL_PID=$!

echo "Waiting for model server..."

wait_for_server() {
    local name="$1" port="$2" max_wait="${3:-1200}" interval="${4:-10}"
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

wait_for_server "Mistral candidate" 18401 || { kill "$MISTRAL_PID" 2>/dev/null; exit 1; }

echo "Checking model server API connections..."

(cd main/studio && conda run -n coach --no-capture-output python -m unittest tests.test_api_connection -v) \
    > logs/api_connection_check.log 2>&1
if [ $? -ne 0 ]; then
    echo "WARNING: API connection check failed — see logs/api_connection_check.log (continuing anyway)"
fi

# Run all scenarios (baseline + agentic, 1 repeat each)

echo "Running run_all_scenarios.py..."

python run_all_scenarios.py --graph both --repeat 1 \
    > logs/run_all_scenarios_experiment.log 2>&1


# Cleanup

echo "Stopping model server..."

kill $MISTRAL_PID
