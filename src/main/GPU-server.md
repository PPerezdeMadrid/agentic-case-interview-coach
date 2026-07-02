# GPU Setup - vLLM on Hypatia

## 1. Environment (one-time setup)

```bash
python3 -m venv ~/.venv
source ~/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install vllm openai
```

## 2. Check GPU availability

```bash
sinfo -s
squeue -p gpu.A100    # check if any jobs are about to finish
```

## 3. Production script (sbatch)

`serverQwen.slurm`:

```bash
#!/bin/bash
#SBATCH --job-name=vllm-server
#SBATCH --partition=gpu.L40S
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=4-00:00:00
#SBATCH --output=vllm_%j.log

source ~/.venv/bin/activate

vllm serve Qwen/Qwen2.5-32B-Instruct \
    --host 0.0.0.0 \
    --port 8081 \
    --api-key sk-Dissertation2026 \
    --served-model-name QwenDissertation
```

> Once `gpu.A100` frees up, swap `--partition=gpu.L40S` for `--partition=gpu.A100` and resubmit the job.

Submit the job:

```bash
sbatch serverQwen.slurm
```

Check which node it's running on and confirm it started correctly:

```bash
squeue -u $USER
tail -f vllm_<jobid>.log
```

## 4. (Optional) Quick interactive session for testing

Only for checking that a model loads correctly before running it in production — don't leave this session running for long:

```bash
srun --pty -p gpu.L40S --gres=gpu:1 --cpus-per-task=4 --mem=32G --time=02:00:00 bash
hostname
nvidia-smi
source ~/.venv/bin/activate

vllm serve Qwen/Qwen2.5-32B-Instruct \
    --host 0.0.0.0 \
    --port 8081 \
    --api-key sk-Dissertation2026 \
    --served-model-name QwenDissertation
```

Note down the `hostname` it prints (e.g. `gpu02`) — you'll need it for the tunnel.

## 5. SSH tunnel from your Mac

```bash
ssh -N -L 8081:NODE_HOSTNAME:8081 ppdm1@hypatia.st-andrews.ac.uk
```

Replace `NODE_HOSTNAME` with the actual node (e.g. `gpu02`), obtained via `squeue -u $USER` or the `hostname` output from step 4.

## 6. Environment variables in your LangGraph project

```
HPC_BASE_URL=http://localhost:8081/v1
HPC_MODEL=QwenDissertation
HPC_KEY=sk-Dissertation2026
```

> `HPC_MODEL` must match `--served-model-name` on the server exactly.

## 7. Cleanup

```bash
squeue -u $USER          # find the jobid
scancel <jobid>          # free up the GPU
```