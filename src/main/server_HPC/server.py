#!/usr/bin/env python3
"""
Dual Server dual OpenAI-compatible that load models from /sharedscratch
Uso: python server.py
"""

import os
import json
import torch
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from transformers import AutoTokenizer, AutoModelForCausalLM
import multiprocessing
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# config
HF_HOME = Path(os.environ.get("HF_HOME", f"/sharedscratch/{os.environ.get('USER', 'ppdm1')}/huggingface"))

MODELS = {
    "mistral": {
        "name": "mistralai/Mistral-Nemo-Instruct-2407",
        "port": 18401,
        "gpu_memory_fraction": 0.85,
    },
    "llama": {
        "name": "meta-llama/Llama-3.3-70B-Instruct",
        "port": 18402,
        "gpu_memory_fraction": 0.90,
    }
}

# Global cache for models
_model_cache = {}
_tokenizer_cache = {}

def load_model(model_id: str, cache_dir: str):
    """Carga modelo desde cache local sin re-descargar"""
    logger.info(f"Loading {model_id} from {cache_dir}...")
    
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        cache_dir=cache_dir,
        local_files_only=True,
        trust_remote_code=True
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        cache_dir=cache_dir,
        local_files_only=True,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    
    logger.info(f"✅ {model_id} loaded successfully")
    return tokenizer, model

def create_app(model_key: str, cache_dir: str):
    """Create app for FastAPI for a model"""
    app = FastAPI(title=f"LLM Server - {model_key.upper()}")
    
    model_config = MODELS[model_key]
    model_name = model_config["name"]
    
    # Load the model and tokenizer
    tokenizer, model = load_model(model_name, str(cache_dir))
    
    @app.get("/v1/models")
    async def list_models():
        """Lista modelos disponibles"""
        return {
            "object": "list",
            "data": [
                {
                    "id": model_name,
                    "object": "model",
                    "owned_by": "local",
                    "permission": []
                }
            ]
        }
    
    @app.post("/v1/completions")
    async def completions(request: Request):
        """Completions endpoint compatible con OpenAI"""
        body = await request.json()
        
        prompt = body.get("prompt", "")
        max_tokens = body.get("max_tokens", 100)
        temperature = body.get("temperature", 0.7)
        top_p = body.get("top_p", 0.9)
        
        try:
            # Tokenizar
            inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
            
            # Generar
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            # Decodifier
            completion_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            
            return {
                "id": f"cmpl-{model_key}",
                "object": "text_completion",
                "created": int(os.times()[4]),
                "model": model_name,
                "choices": [
                    {
                        "text": completion_text,
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": "length"
                    }
                ],
                "usage": {
                    "prompt_tokens": inputs["input_ids"].shape[1],
                    "completion_tokens": outputs[0].shape[0] - inputs["input_ids"].shape[1],
                    "total_tokens": outputs[0].shape[0]
                }
            }
        except Exception as e:
            logger.error(f"Error in completions: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )
    
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """Chat completions endpoint (wrapper around completions)"""
        body = await request.json()
        messages = body.get("messages", [])
        
        # Convertir messages a prompt
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += "assistant: "
        
        # Usar completions
        body["prompt"] = prompt
        return await completions(Request({"type": "http", "method": "POST", "body": json.dumps(body).encode()}))
    
    return app

def run_server(model_key: str, cache_dir: str):
    """Corre un servidor en su propio proceso"""
    model_config = MODELS[model_key]
    port = model_config["port"]
    
    app = create_app(model_key, cache_dir)
    
    logger.info(f"🚀 Starting {model_key.upper()} server on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

def main():
    """Corre ambos servidores en paralelo"""
    
    # Verificar que HF_HOME existe y tiene los modelos
    if not HF_HOME.exists():
        logger.error(f"HF_HOME not found: {HF_HOME}")
        return
    
    for model_key, config in MODELS.items():
        logger.info(f"Checking {model_key} model...")
        model_path = HF_HOME / f"hub/models--{config['name'].replace('/', '--')}"
        if not model_path.exists():
            logger.warning(f"{model_key} model not found at {model_path}")
    
    logger.info(f"HF_HOME: {HF_HOME}")
    logger.info("Starting dual-model server...")
    
    # Crer procesos para cada modelo
    processes = []
    for model_key in MODELS.keys():
        p = multiprocessing.Process(
            target=run_server,
            args=(model_key, HF_HOME),
            name=f"Server-{model_key.upper()}"
        )
        p.daemon = False
        p.start()
        processes.append(p)
        logger.info(f"Started process for {model_key}")
    
    logger.info("Both servers running!")
    logger.info(f"  - Mistral-Nemo: http://127.0.0.1:18401/v1/models")
    logger.info(f"  - Llama-70B:    http://127.0.0.1:18402/v1/models")
    
    # Esperar a que ambos terminen
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join()

if __name__ == "__main__":
    main()