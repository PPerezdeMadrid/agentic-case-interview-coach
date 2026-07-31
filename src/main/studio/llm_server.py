import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

project_env = Path(__file__).resolve().parents[3] / ".env"
if project_env.exists():
    load_dotenv(project_env, override=False)


def _normalize_base_url(raw_base_url: str) -> str:
    """Ensure provider base URLs always point to a `/v1` API root."""
    base_url = raw_base_url.rstrip("/")
    if base_url and not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url

"""
model_mistral7B = "mistralai/Mistral-7B-Instruct-v0.3"
model_mistral12B = "mistralai/Mistral-Nemo-Instruct-2407"
model_llama70B = "meta-llama/Llama-3.3-70B-Instruct"
model_llama8B = "meta-llama/Llama-3.1-8B-Instruct"
"""

_openrouter_base_url = _normalize_base_url(
    os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
)
_openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
_openrouter_temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))

# Local LM Studio model
lmstudio_llm_server = ChatOpenAI(
    model=os.getenv("LMSTUDIO_MODEL", "deepseek-r1-distill-llama-8b"),
    base_url=_normalize_base_url(os.getenv("LMSTUDIO_BASE_URL", "http://localhost:8081")),
    api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio"),
    temperature=float(os.getenv("LMSTUDIO_TEMPERATURE", "0.5")),
    disable_streaming=True,
)


# OpenAI model (direct API, not OpenRouter)
openai_llm_server = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
    base_url=_normalize_base_url(os.getenv("OPENAI_BASE_URL", "https://api.openai.com")),
    api_key=os.getenv("OPENAI_API_KEY", ""),
    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
    disable_streaming=True,
)


# OpenRouter Llama 3.3 70B Interviewer model
interviewer_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_INTERVIEWER", "meta-llama/llama-3.3-70b-instruct"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=os.getenv("INTERVIEWER_TEMPERATURE", 0.6),
)

# OpenRouter Gemma 3 27B Candidate model
# max_tokens is capped explicitly: some OpenRouter providers (e.g. NextBit)
# default an unset max_tokens to the full context length, which then rejects
# the request as soon as prompt tokens are added on top of it.
candidate_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_CANDIDATE", "google/gemma-3-27b-it"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=os.getenv("CANDIDATE_TEMPERATURE", 0.8),
    max_tokens=int(os.getenv("CANDIDATE_MAX_TOKENS", "1024")),
)

# OpenRouter Qwen2.5 72B Judge model
judge_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_JUDGE", "qwen/qwen-2.5-72b-instruct"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=os.getenv("JUDGE_TEMPERATURE", 0.0),
)

# OpenRouter Phi-4 Feedback model
feedback_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_FEEDBACK", "microsoft/phi-4"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=os.getenv("FEEDBACK_TEMPERATURE", 0.3),
)


# Alternative: GPU-hosted models on the university HPC cluster
candidate_llm_server_gpu = ChatOpenAI(
    model="mistralai/mistral-small-24b-instruct-2501",
    base_url="http://localhost:18403/v1",
    api_key="EMPTY",
    temperature=float(os.getenv("CANDIDATE_TEMPERATURE", 0.8)),
)


# judge_llm_server_gpu = ChatOpenAI(
#     model=model_llama70B,
#     base_url="http://localhost:18402/v1",
#     api_key="EMPTY",
#     temperature=float(os.getenv("TEMPERATURE", "0.0")),
# )

# Backward-compatible default used by baseline and older call sites.
llm_server = lmstudio_llm_server
