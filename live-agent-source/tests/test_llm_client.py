import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

from llm_client import LLMClient
from observability import configure_logging


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LLMClientTests(unittest.TestCase):
    def test_missing_api_key_fails_fast(self):
        with patch.dict(os.environ, {"LLM_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                LLMClient()

    def test_v1_url_and_response_parsing(self):
        client = LLMClient(api_key="test-key", base_url="https://example.com/v1")
        response = FakeResponse({
            "choices": [{"message": {"content": "ok"}}],
        })
        with patch("llm_client.request.urlopen", return_value=response) as urlopen:
            self.assertEqual(client.chat("system", "user", max_tokens=10), "ok")
        request_obj = urlopen.call_args.args[0]
        self.assertEqual(request_obj.full_url, "https://example.com/v1/chat/completions")

    def test_retry_is_written_to_json_log(self):
        client_response = FakeResponse({"choices": [{"message": {"content": "ok"}}]})
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        log_path = Path(temporary_directory.name) / "agent.jsonl"
        logger = configure_logging(log_path)
        client = LLMClient(api_key="test-key", base_url="https://example.com/v1", logger=logger)
        transient_error = error.HTTPError(
            "https://example.com/v1/chat/completions",
            503,
            "busy",
            {},
            io.BytesIO(b"busy"),
        )
        with patch("llm_client.request.urlopen", side_effect=[transient_error, client_response]):
            with patch("llm_client.time.sleep"):
                self.assertEqual(client.chat("system", "user", max_tokens=10, run_id="run-1"), "ok")

        events = [json.loads(line)["event"] for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertIn("llm_retry", events)
        self.assertIn("llm_success", events)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
