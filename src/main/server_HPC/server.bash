#!/bin/bash
#SBATCH --job-name=llm-server
#SBATCH --account=compsci
#SBATCH --partition=gpu.A100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
 
echo "Starting LLM Server (Mistral-Nemo + Llama-70B)"
 
source /software/conda/$USER/conda/etc/profile.d/conda.sh
conda activate coach
 
# Prevenir shadowing de paquetes
export PYTHONNOUSERSITE=1
export HF_HOME=/sharedscratch/$USER/huggingface
 
mkdir -p logs
 
echo "GPU information:"
nvidia-smi
 
echo "Starting dual-model server..."
python server.py