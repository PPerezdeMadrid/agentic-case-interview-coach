sbatch server.bash

Modelos esperados en /sharedscratch/$USER/huggingface/hub/ antes de lanzar el job
(política del servidor: los pesos deben vivir en sharedscratch, no en $HOME):
  - models--mistralai--Mistral-Nemo-Instruct-2407       (candidate, en uso)
  - models--meta-llama--Llama-3.3-70B-Instruct          (judge)
  - models--mistralai--Mistral-Small-24B-Instruct-2501  (candidate, alternativa más fuerte -- añadido, aún no lanzado en server.bash)

Mistral-Small-24B está en MODELS (server.py, puerto 18403) y listo para
`python server.py --model mistral-small`, pero server.bash SOLO lanza mistral
(Nemo) + llama por ahora -- --gres=gpu:3 alcanza para esos dos (1+2 GPUs). Si
quieres levantar Mistral-Small-24B en vez de Nemo, cambia `--model mistral` por
`--model mistral-small` en server.bash (mismo footprint, 1 GPU, no cambia el
--gres). Si quieres tenerlos LOS DOS a la vez (para comparar), hace falta subir
--gres=gpu:4 y añadir una tercera línea de arranque con CUDA_VISIBLE_DEVICES=3.

Si los descargaste en otro sitio (p.ej. $HOME/work/huggingface), muévelos o
vuelve a descargarlos con --local-dir apuntando a sharedscratch antes de lanzar
el job -- server.py resuelve la ruta a partir de HF_HOME, que server.bash fija
a /sharedscratch/$USER/huggingface.

server.py acepta tanto una descarga plana (`hf download <repo> --local-dir ...`)
como el layout de caché estándar de HF (`hf download <repo>` sin --local-dir,
con snapshots/blobs/refs) - detecta cuál es y carga en consecuencia.

Comandos útiles para monitorizar

squeue -u $USER              # ver el estado de tu job (PENDING/RUNNING)
squeue -u $USER --start      # tiempo estimado de inicio si está en cola
scontrol show job 123456     # detalles del job (nodo asignado, razón de espera, etc.)
tail -f logs/langgraph-agents_123456.out   # ver el stdout en vivo
tail -f logs/langgraph-agents_123456.err   # stderr
scancel 123456                # cancelar el job si algo va mal

4329802

tail -f logs/mistral.log
tail -f logs/llama70b.log
tail -f logs/run_all_scenarios.log 

tail -f logs/exp3.1_4494918.out

tail -f logs/hf-llm-server-candidate-exp02HPC_4329802.err 
tail -f logs/langgraph-agents-experiment_4329758.out 
tail -f logs/api_connection_check.log

cd main/studio && conda run -n coach --no-capture-output python -m unittest tests.test_api_connection -v

# equivalente via Makefile (usa el runner ya configurado con setup-hpc, o fuerza RUNNER=hpc)
cd .. && make test-api-connection RUNNER=hpc


---

#  Mistral-Nemo
conda activate coach
hf download mistralai/Mistral-Nemo-Instruct-2407 \
  --local-dir /sharedscratch/$USER/huggingface/hub/models--mistralai--Mistral-Nemo-Instruct-2407

# Llama-70B
conda activate coach
hf download meta-llama/Llama-3.3-70B-Instruct \
  --local-dir /sharedscratch/$USER/huggingface/hub/models--meta-llama--Llama-3.3-70B-Instruct

# Mistral-Small-24B (alternativa al candidate, mismo tamaño que el que usáis en OpenRouter)
conda activate coach
hf download mistralai/Mistral-Small-24B-Instruct-2501 \
  --local-dir /sharedscratch/$USER/huggingface/hub/models--mistralai--Mistral-Small-24B-Instruct-2501