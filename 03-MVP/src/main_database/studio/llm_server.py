import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()

project_env = Path(__file__).resolve().parents[3] / ".env"
if project_env.exists():
    load_dotenv(project_env, override=False)

base_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:8081").rstrip("/")
if not base_url.endswith("/v1"):
    base_url = f"{base_url}/v1"


llm_server = ChatOpenAI(
    model=os.getenv("LMSTUDIO_MODEL", "deepseek-r1-distill-llama-8b"),
    base_url=base_url,
    api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio"),
    temperature=float(os.getenv("LMSTUDIO_TEMPERATURE", "0.14")),
    disable_streaming=True,
)
