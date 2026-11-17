"""Offline checks added for the transfer. All provider responses are synthetic."""
import io
import json
import os
import unittest
from importlib.util import find_spec
from unittest.mock import call, patch
from urllib.error import HTTPError

from llm import client


class ClientTests(unittest.TestCase):
    def test_prompt_and_sql_extraction(self):
        prompt = client.build_prompt({"query": "SELECT %(value)s", "schema": "TABLE demo"})
        self.assertIn("SELECT %(value)s", prompt)
        self.assertIn("TABLE demo", prompt)
        self.assertEqual(client.extract_sql("```sql\nSELECT 1;\n```\nTekst"), "SELECT 1")
        self.assertEqual(client.extract_sql("SELECT 1;"), "SELECT 1")
        self.assertEqual(client.extract_sql(" "), "")

    def test_mock_does_not_call_transport(self):
        with patch.object(client.urllib.request, "urlopen") as request:
            response = client.call_llm("prompt", "mock", original_sql="SELECT 1")
        request.assert_not_called()
        self.assertEqual(client.extract_sql(response["text"]), "SELECT 1")
        self.assertEqual(response["output_tokens"], 0)
        self.assertEqual(response["usage_raw"], {})

    def test_openrouter_serializes_model_effort_and_keeps_usage(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 12, "cost": 0.01,
                 "completion_tokens_details": {"reasoning_tokens": 4}}
        body = {"choices": [{"message": {"content": [{"type": "text", "text": "SELECT 1"}]},
                             "finish_reason": "length", "native_finish_reason": "other"}],
                "usage": usage}
        for effort in ("low", "medium", "high", "xhigh", "max", None):
            with self.subTest(effort=effort), patch.dict(os.environ, {
                "OPENROUTER_API_KEY": "offline-test",
                "OPENROUTER_BASE_URL": "https://router.example.invalid/api/v1/",
            }), patch.object(client.urllib.request, "urlopen",
                             return_value=io.BytesIO(json.dumps(body).encode())) as request:
                response = client.call_llm("prompt", "provider/model", 4000,
                                           provider="openrouter", effort=effort)
                sent = request.call_args.args[0]
                payload = json.loads(sent.data)
                self.assertEqual(sent.full_url, "https://router.example.invalid/api/v1/chat/completions")
                self.assertEqual(sent.get_method(), "POST")
                self.assertEqual(sent.get_header("Authorization"), "Bearer offline-test")
                self.assertEqual(request.call_args.kwargs["timeout"], 600)
                self.assertEqual(payload["model"], "provider/model")
                self.assertEqual(payload["max_tokens"], 4000)
                self.assertEqual(payload["messages"], [{"role": "system", "content": client.SYSTEM},
                                                        {"role": "user", "content": "prompt"}])
                self.assertEqual(payload["usage"], {"include": True})
                if effort:
                    self.assertEqual(payload["reasoning"], {"effort": effort, "exclude": True})
                else:
                    self.assertNotIn("reasoning", payload)
                self.assertEqual(response["usage_raw"], usage)
                self.assertEqual((response["text"], response["stop_reason"]), ("SELECT 1", "max_tokens"))
                self.assertEqual((response["input_tokens"], response["output_tokens"]), (10, 12))
                self.assertEqual(response["cost_reported"], 0.01)

    def test_openrouter_retry_and_permanent_error(self):
        url = "https://router.example.invalid"
        transient = HTTPError(url, 429, "fixture", {}, io.BytesIO(b"limited"))
        permanent = HTTPError(url, 401, "fixture", {}, io.BytesIO(b"unauthorized"))
        with patch.object(client.urllib.request, "urlopen",
                          side_effect=[transient, TimeoutError(), io.BytesIO(b"{}")]) as request, \
                patch.object(client.time, "sleep") as sleep:
            self.assertEqual(client._post_json(url, {}, "offline-test"), {})
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_args_list, [call(2), call(4)])
        with patch.object(client.urllib.request, "urlopen", side_effect=permanent) as request:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                client._post_json(url, {}, "offline-test")
            request.assert_called_once()

    def test_invalid_openrouter_response_and_missing_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "offline-test"}):
            with patch.object(client, "_post_json", return_value={"choices": []}):
                with self.assertRaisesRegex(RuntimeError, "onverwacht antwoord"):
                    client.call_llm("prompt", "provider/model", provider="openrouter")
            with patch.object(client.urllib.request, "urlopen", return_value=io.BytesIO(b"invalid")):
                with self.assertRaises(json.JSONDecodeError):
                    client.call_llm("prompt", "provider/model", provider="openrouter")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with self.assertRaisesRegex(SystemExit, "OPENROUTER_API_KEY"):
                client.call_llm("prompt", "provider/model", provider="openrouter")

    @unittest.skipUnless(find_spec("anthropic") and find_spec("httpx2"),
                         "requires the tested Anthropic SDK with httpx2")
    def test_anthropic_sdk_serializes_extra_body(self):
        import anthropic
        import httpx2

        model = "claude-sonnet-5-5"
        requests = []

        def respond(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/v1/messages")
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json={
                "id": "msg_fixture", "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "text", "text": "```sql\nSELECT 1\n```"}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 12, "cache_read_input_tokens": 5},
            })

        for effort in ("high", None):
            with self.subTest(effort=effort), httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
                sdk = anthropic.Anthropic(api_key="offline-test", base_url="https://claude.example.invalid",
                                          http_client=http)
                with patch.object(anthropic, "Anthropic", return_value=sdk), \
                        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "offline-test"}):
                    response = client.call_llm("prompt", model, max_tokens=4000, effort=effort)
                sent = requests[-1]
                self.assertEqual(sent["model"], model)
                self.assertEqual(sent["max_tokens"], 4000)
                self.assertEqual(sent["system"], client.SYSTEM)
                self.assertEqual(sent["messages"], [{"role": "user", "content": "prompt"}])
                self.assertEqual(sent.get("output_config"), {"effort": "high"} if effort else None)
                self.assertNotIn("thinking", sent)
                self.assertEqual(response["usage_raw"], {"input_tokens": 10, "output_tokens": 12})
                self.assertIsNone(response["cost_reported"])
                self.assertEqual(client.extract_sql(response["text"]), "SELECT 1")
