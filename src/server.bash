#!/bin/bash
#SBATCH --job-name=langgraph-agents
#SBATCH --account=compsci
#SBATCH --partition=gpu.A100
#SBATCH --gres=gpu:3
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err


echo "Starting LangGraph multi-agent system"

source ~/miniconda3/etc/profile.d/conda.sh
conda activate coach

# Prevent ~/.local user site-packages (e.g. a pip install --user'd vllm on
# system Python 3.9) from shadowing the packages installed in this conda env
export PYTHONNOUSERSITE=1

# Model weights are large; keep them off the backed-up home directory
export HF_HOME=/sharedscratch/$USER/huggingface

mkdir -p logs

echo "GPU information:"
nvidia-smi

# Start Candidate model (Mistral)

echo "Starting Mistral Candidate server..."

CUDA_VISIBLE_DEVICES=0 \
vllm serve mistralai/Mistral-Nemo-Instruct-2407 \
    --host 127.0.0.1 \
    --port 18401 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 32000 \
    > logs/mistral.log 2>&1 &

MISTRAL_PID=$!

# Start Judge model (Llama)

echo "Starting Llama Judge server..."

CUDA_VISIBLE_DEVICES=1,2 \
vllm serve meta-llama/Llama-3.3-70B-Instruct \
    --host 127.0.0.1 \
    --port 18402 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 32000 \
    > logs/llama70b.log 2>&1 &

LLAMA_PID=$!

echo "Waiting for model servers..."

sleep 90

# Run all scenarios (baseline + agentic, 3 repeats each)

echo "Running run_all_scenarios.py..."

python run_all_scenarios.py --graph both --repeat 3 \
    > logs/run_all_scenarios.log 2>&1


# Cleanup

echo "Stopping model servers..."

kill $LLAMA_PID
kill $MISTRAL_PID