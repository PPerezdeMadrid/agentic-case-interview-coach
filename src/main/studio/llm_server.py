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


# Local LM Studio model 
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

# Backward-compatible default used by baseline and older call sites.
llm_server = lmstudio_llm_server
