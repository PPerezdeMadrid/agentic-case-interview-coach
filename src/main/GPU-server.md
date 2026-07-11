sbatch server.bash 

Comandos útiles para monitorizar

squeue -u $USER              # ver el estado de tu job (PENDING/RUNNING)
squeue -u $USER --start      # tiempo estimado de inicio si está en cola
scontrol show job 123456     # detalles del job (nodo asignado, razón de espera, etc.)
tail -f logs/langgraph-agents_123456.out   # ver el stdout en vivo
tail -f logs/langgraph-agents_123456.err   # stderr
scancel 123456                # cancelar el job si algo va mal

4101165

tail -f logs/mistral.log
tail -f logs/llama70b.log
tail -f logs/run_all_scenarios.log 

tail -f logs/langgraph-agents_4101083.out 
