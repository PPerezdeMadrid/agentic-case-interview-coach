sbatch server.bash 

Comandos útiles para monitorizar

squeue -u $USER              # ver el estado de tu job (PENDING/RUNNING)
squeue -u $USER --start      # tiempo estimado de inicio si está en cola
scontrol show job 123456     # detalles del job (nodo asignado, razón de espera, etc.)
tail -f logs/langgraph-agents_123456.out   # ver el stdout en vivo
tail -f logs/langgraph-agents_123456.err   # stderr
scancel 123456                # cancelar el job si algo va mal

4106660

tail -f logs/mistral.log
tail -f logs/llama70b.log
tail -f logs/run_all_scenarios.log 

tail -f logs/langgraph-agents_4106648.out 
tail -f logs/langgraph-agents-experiment_4106660.out 
tail -f logs/api_connection_check.log

cd main/studio && conda run -n coach --no-capture-output python -m unittest tests.test_api_connection -v

cd main/studio && conda run -n coach --no-capture-output python -m unittest tests.test_api_connection -v


---

#  Mistral-Nemo
conda activate coach
hf download mistralai/Mistral-Nemo-Instruct-2407 \
  --local-dir /sharedscratch/$USER/huggingface/hub/models--mistralai--Mistral-Nemo-Instruct-2407

# Llama-70B
conda activate coach
hf download meta-llama/Llama-3.3-70B-Instruct \
  --local-dir /sharedscratch/$USER/huggingface/hub/models--meta-llama--Llama-3.3-70B-Instruct