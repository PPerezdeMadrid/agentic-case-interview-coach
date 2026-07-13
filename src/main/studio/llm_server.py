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

# Local LM Studio model - used for final candidate feedback
lmstudio_llm_server = ChatOpenAI(
    model=os.getenv("LMSTUDIO_MODEL", "deepseek-r1-distill-llama-8b"),
    base_url=_normalize_base_url(os.getenv("LMSTUDIO_BASE_URL", "http://localhost:8081")),
    api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio"),
    temperature=float(os.getenv("LMSTUDIO_TEMPERATURE", "0.14")),
    disable_streaming=True,
)


# OpenAI model
openai_llm_server = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
    base_url=_normalize_base_url(os.getenv("OPENAI_BASE_URL", "https://api.openai.com")),
    api_key=os.getenv("OPENAI_API_KEY", ""),
    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
    disable_streaming=True,
    model_kwargs={"response_format": {"type": "json_object"}},
)


# OpenRouter Qwen Interviewer model
interviewer_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_INTERVIEWER", "qwen/qwen-2.5-7b-instruct"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=_openrouter_temperature,
)

# OpenRouter Mistral Candidate model
candidate_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_CANDIDATE", "mistralai/mistral-nemo"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=_openrouter_temperature,
)

# OpenRouter Llama 70B Judge model
judge_llm_server = ChatOpenAI(
    model=os.getenv("OPENROUTER_MODEL_JUDGE", "meta-llama/llama-3.1-70b-instruct"),
    base_url=_openrouter_base_url,
    api_key=_openrouter_api_key,
    temperature=_openrouter_temperature,
)

feedback_llm_server = lmstudio_llm_server


# Alternative: GPU-hosted models on the university HPC cluster. 
#
# candidate_llm_server_gpu = ChatOpenAI(
#     model=model_mistral12B,
#     base_url="http://localhost:18401/v1",
#     api_key="EMPTY",
#     temperature=float(os.getenv("TEMPERATURE", "0.0")),
# )
#
# judge_llm_server_gpu = ChatOpenAI(
#     model=model_llama70B,
#     base_url="http://localhost:18402/v1",
#     api_key="EMPTY",
#     temperature=float(os.getenv("TEMPERATURE", "0.0")),
# )

# Backward-compatible default used by baseline and older call sites.
llm_server = lmstudio_llm_server
