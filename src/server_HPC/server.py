#!/usr/bin/env python3
"""OpenAI-compatible FastAPI server for a single HF model on the HPC cluster.

Serves one model per process so each can be pinned to its own GPU(s) via
CUDA_VISIBLE_DEVICES (see server.bash) rather than sharing a process/GPU set.

Usage:
    CUDA_VISIBLE_DEVICES=0   python server.py --model mistral
    CUDA_VISIBLE_DEVICES=1,2 python server.py --model llama
"""

import argparse
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HF_HOME = Path(os.environ.get("HF_HOME", f"/sharedscratch/{os.environ.get('USER', '')}/huggingface"))

MODELS = {
    "mistral": {
        "repo_id": "mistralai/Mistral-Nemo-Instruct-2407",
        "port": 18401,
    },
    "llama": {
        "repo_id": "meta-llama/Llama-3.3-70B-Instruct",
        "port": 18402,
    },
}


def local_model_dir(repo_id: str) -> Path:
    """Directory used by `hf download <repo_id> --local-dir ...` (see server.bash).

    This is a flat directory of real files, not the HF hub cache layout
    (models--org--name/snapshots/<rev>/...), so it must be passed directly as
    the model path rather than as `cache_dir` to `from_pretrained`.
    """
    return HF_HOME / "hub" / f"models--{repo_id.replace('/', '--')}"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.0
    top_p: float = 1.0


class CompletionRequest(BaseModel):
    model: Optional[str] = None
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.0
    top_p: float = 1.0


def load_model(repo_id: str):
    model_dir = local_model_dir(repo_id)
    if not model_dir.exists():
        raise FileNotFoundError(
            f"{repo_id} not found at {model_dir}. Download it first with: "
            f"hf download {repo_id} --local-dir {model_dir}"
        )

    logger.info("Loading %s from %s ...", repo_id, model_dir)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir),
        local_files_only=True,
        torch_dtype="auto",
        device_map="auto",
    )
    model.eval()
    logger.info("%s loaded (dtype=%s)", repo_id, model.dtype)
    return tokenizer, model


def build_app(model_key: str) -> FastAPI:
    if model_key not in MODELS:
        raise ValueError(f"Unknown model key {model_key!r}; choose from {sorted(MODELS)}")

    repo_id = MODELS[model_key]["repo_id"]
    tokenizer, model = load_model(repo_id)

    app = FastAPI(title=f"HPC LLM server ({model_key})")

    def run_generate(input_ids: torch.Tensor, max_tokens: int, temperature: float, top_p: float):
        gen_kwargs = dict(
            max_new_tokens=max_tokens,
            pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
        )
        if temperature and temperature > 0:
            gen_kwargs.update(do_sample=True, temperature=temperature, top_p=top_p)
        else:
            gen_kwargs["do_sample"] = False

        with torch.no_grad():
            output_ids = model.generate(input_ids, **gen_kwargs)

        completion_ids = output_ids[0][input_ids.shape[1]:]
        text = tokenizer.decode(completion_ids, skip_special_tokens=True)
        return text, completion_ids.shape[0]

    @app.get("/v1/models")
    def list_models():
        return {
            "object": "list",
            "data": [{"id": repo_id, "object": "model", "owned_by": "local", "permission": []}],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(request: ChatCompletionRequest):
        messages = [m.model_dump() for m in request.messages]
        try:
            input_ids = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt"
            ).to(model.device)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to render chat template: {exc}") from exc

        try:
            text, completion_tokens = run_generate(input_ids, request.max_tokens, request.temperature, request.top_p)
        except Exception as exc:
            logger.exception("Generation failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        prompt_tokens = input_ids.shape[1]
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": repo_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    @app.post("/v1/completions")
    def completions(request: CompletionRequest):
        inputs = tokenizer(request.prompt, return_tensors="pt").to(model.device)
        try:
            text, completion_tokens = run_generate(
                inputs["input_ids"], request.max_tokens, request.temperature, request.top_p
            )
        except Exception as exc:
            logger.exception("Generation failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        prompt_tokens = inputs["input_ids"].shape[1]
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:12]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": repo_id,
            "choices": [{"text": text, "index": 0, "logprobs": None, "finish_reason": "length"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return app


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS), required=True, help="Which model to serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="Overrides the default port for --model")
    return parser.parse_args()


def main():
    args = parse_args()
    port = args.port or MODELS[args.model]["port"]
    app = build_app(args.model)
    logger.info("Starting %s server on %s:%s", args.model, args.host, port)
    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
