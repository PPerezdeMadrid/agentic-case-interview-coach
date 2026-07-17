#!/bin/bash
#SBATCH --job-name=hf-llm-server
#SBATCH --account=compsci
#SBATCH --partition=gpu.A100
#SBATCH --gres=gpu:3
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

echo "Starting HF/FastAPI LLM servers (Mistral-Nemo + Llama-3.3-70B)"

source /software/conda/$USER/conda/etc/profile.d/conda.sh
conda activate coach

# Prevent shadowing of conda env packages by ~/.local user site-packages
export PYTHONNOUSERSITE=1
export HF_HOME=/sharedscratch/$USER/huggingface

mkdir -p logs

echo "GPU information:"
nvidia-smi

# Mistral-Nemo (12B) fits comfortably on a single A100.
echo "Starting Mistral-Nemo server on GPU 0..."
CUDA_VISIBLE_DEVICES=0 python server.py --model mistral > logs/mistral.log 2>&1 &
MISTRAL_PID=$!

# Llama-3.3-70B needs its weights sharded across two GPUs (fp16 ~140GB).
echo "Starting Llama-3.3-70B server on GPUs 1,2..."
CUDA_VISIBLE_DEVICES=1,2 python server.py --model llama > logs/llama70b.log 2>&1 &
LLAMA_PID=$!

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

wait_for_server "Mistral-Nemo" 18401 || { kill "$MISTRAL_PID" "$LLAMA_PID" 2>/dev/null; exit 1; }
wait_for_server "Llama-3.3-70B" 18402 1800 || { kill "$MISTRAL_PID" "$LLAMA_PID" 2>/dev/null; exit 1; }

echo "Both servers are up:"
echo "  - Mistral-Nemo:   http://127.0.0.1:18401/v1/models"
echo "  - Llama-3.3-70B:  http://127.0.0.1:18402/v1/models"

# Keep the job alive as long as either server is running.
wait $MISTRAL_PID $LLAMA_PID
