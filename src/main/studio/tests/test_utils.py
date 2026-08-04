import sys
import unittest
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

try:
    import utils
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Studio test dependencies are not installed: {exc.name}") from exc


class IsTransientProviderErrorTests(unittest.TestCase):
    def test_status_code_429_is_transient(self) -> None:
        exc = Exception("rate limited")
        exc.status_code = 429
        self.assertTrue(utils._is_transient_provider_error(exc))

    def test_429_in_message_is_transient(self) -> None:
        exc = Exception("Error code: 429 - {'error': {'message': 'rate limited'}}")
        self.assertTrue(utils._is_transient_provider_error(exc))

    def test_400_with_provider_name_is_transient(self) -> None:
        exc = Exception(
            "Error code: 400 - {'error': {'code': 400, 'metadata': {'provider_name': 'Novita'}}}"
        )
        self.assertTrue(utils._is_transient_provider_error(exc))

    def test_400_provider_endpoint_mismatch_without_provider_name_is_transient(self) -> None:
        # Reproduces the crash from 2026-08: langchain_openai re-raises OpenRouter's routed
        # provider error as a bare ValueError with no 'provider_name' key, e.g.
        # ValueError({'message': 'model: qwen/qwen-2.5-72b-instruct does not support endpoint:
        # completions', 'code': 400}).
        exc = ValueError(
            {"message": "model: qwen/qwen-2.5-72b-instruct does not support endpoint: completions", "code": 400}
        )
        self.assertTrue(utils._is_transient_provider_error(exc))

    def test_our_own_malformed_request_is_not_transient(self) -> None:
        exc = Exception("Error code: 400 - {'error': {'message': 'invalid schema', 'code': 400}}")
        self.assertFalse(utils._is_transient_provider_error(exc))


if __name__ == "__main__":
    unittest.main()
