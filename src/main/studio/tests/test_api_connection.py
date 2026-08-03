import os
import sys
import unittest
from pathlib import Path

import httpx

STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

try:
    import llm_server
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Studio test dependencies are not installed: {exc.name}") from exc

CONNECT_TIMEOUT = 5.0


def _check_endpoint(base_url: str, api_key: str) -> tuple[bool, str]:
    """GETs {base_url}/models as a cheap reachability + auth probe (no generation cost)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(f"{base_url}/models", headers=headers, timeout=CONNECT_TIMEOUT)
    except httpx.ConnectError as exc:
        return False, f"connection refused/unreachable at {base_url} ({exc})"
    except httpx.TimeoutException as exc:
        return False, f"timed out after {CONNECT_TIMEOUT}s contacting {base_url} ({exc})"
    except httpx.HTTPError as exc:
        return False, f"request to {base_url} failed ({exc})"

    if response.status_code in (401, 403):
        return False, f"{base_url} rejected the API key (HTTP {response.status_code})"
    if response.status_code >= 400:
        return False, f"{base_url} returned HTTP {response.status_code}: {response.text[:200]}"
    return True, f"HTTP {response.status_code}"


class APIConnectionTests(unittest.TestCase):
    """Pings every configured LLM endpoint before graph nodes call them; run ahead of `make langgraph`
    to catch a down server or bad API key early. Covers the four active roles plus the two fallback-only clients."""

    def test_lmstudio_connection(self):
        if not os.getenv("LMSTUDIO_RUN_LOCAL_TESTS"):
            self.skipTest(
                "Set LMSTUDIO_RUN_LOCAL_TESTS=1 to check this local, not-wired-to-any-active-role "
                "client; skipped by default since it requires the LM Studio app running locally."
            )
        client = llm_server.lmstudio_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(
            ok,
            f"LM Studio unreachable: {detail}\n"
            "-> Start the LM Studio app and load/serve the model configured in LMSTUDIO_MODEL.",
        )

    def test_openai_connection(self):
        if not os.getenv("OPENAI_API_KEY"):
            self.skipTest("OPENAI_API_KEY is not set in .env")
        client = llm_server.openai_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(ok, f"OpenAI connection failed: {detail}")

    def test_interviewer_openrouter_connection(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            self.skipTest("OPENROUTER_API_KEY is not set in .env")
        client = llm_server.interviewer_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(ok, f"OpenRouter connection (interviewer/Llama-3.3-70B) failed: {detail}")

    def test_candidate_openrouter_connection(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            self.skipTest("OPENROUTER_API_KEY is not set in .env")
        client = llm_server.candidate_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(ok, f"OpenRouter connection (candidate/Gemma-3-27B) failed: {detail}")

    def test_judge_openrouter_connection(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            self.skipTest("OPENROUTER_API_KEY is not set in .env")
        client = llm_server.judge_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(ok, f"OpenRouter connection (judge/Qwen2.5-72B) failed: {detail}")

    def test_feedback_openrouter_connection(self):
        if not os.getenv("OPENROUTER_API_KEY"):
            self.skipTest("OPENROUTER_API_KEY is not set in .env")
        client = llm_server.feedback_llm_server
        ok, detail = _check_endpoint(client.openai_api_base, client.openai_api_key.get_secret_value())
        self.assertTrue(ok, f"OpenRouter connection (feedback/Phi-4) failed: {detail}")


if __name__ == "__main__":
    unittest.main()
