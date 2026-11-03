"""Generation settings, response diagnostics and persistence without paid calls."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from api.app import create_app
from api.config import ROOT, Settings
from api.services.analysis import execute_analysis
from api.services.storage import Store
from api.services.ai_settings import test_generation as visibility_test
from llm.analysis import AnalysisError, analyze, chat
from llm.generation import (
    GenerationSettings,
    environment_defaults,
    validate_capabilities,
)

MODEL = "anthropic/claude-haiku-5.5"
INFO = {
    "id": MODEL,
    "supported_parameters": ["max_tokens", "response_format", "reasoning"],
    "reasoning": {
        "mandatory": False,
        "supported_efforts": ["none", "low", "medium", "high"],
    },
    "top_provider": {"max_completion_tokens": 16384},
}
ENV = {
    "SUE_MODEL": MODEL,
    "SUE_LLM_PROVIDER": "openrouter",
    "OPENROUTER_API_KEY": "sk-or-unit-only",
    "SUE_MAX_OUTPUT_TOKENS": "4096",
    "SUE_REASONING_EFFORT": "low",
}


def response(text="OK", finish="stop", reasoning=12):
    return {
        "model": MODEL,
        "choices": [{"finish_reason": finish, "message": {"content": text}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 32,
            "completion_tokens_details": {"reasoning_tokens": reasoning},
            "total_tokens": 132,
            "cost": 0.001,
        },
    }


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def call(self, value, options):
        client = Mock()
        client.request.return_value = httpx.Response(200, json=value)
        with (
            patch("llm.analysis._model_info", return_value=INFO),
            patch("llm.analysis.httpx.Client") as constructor,
        ):
            constructor.return_value.__enter__.return_value = client
            result = chat(
                [{"role": "user", "content": "OK"}], MODEL, generation=options
            )
        return result, client.request.call_args.kwargs["json"]

    def test_defaults_and_all_presets_applied_to_requests(self):
        self.assertEqual(environment_defaults().max_output_tokens, 4096)
        for tokens in (512, 1024, 2048, 4096, 8192, 16384):
            with self.subTest(tokens=tokens):
                data, payload = self.call(
                    response(), GenerationSettings(max_output_tokens=tokens)
                )
                self.assertEqual(payload["max_tokens"], tokens)
                self.assertEqual(payload["reasoning"]["effort"], "low")
                self.assertNotIn("temperature", payload)
                self.assertEqual(data["diagnostics"]["reasoning_tokens"], 12)

    def test_provider_default_omits_maximum_and_disabled_reasoning(self):
        _, payload = self.call(
            response(),
            GenerationSettings(max_output_tokens=None, reasoning_effort="disabled"),
        )
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["reasoning"], {"enabled": False, "exclude": True})

    def test_unsupported_controls_and_bad_values_rejected(self):
        for value in (-1, 0, 333, True, "4096", 32768):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                GenerationSettings(max_output_tokens=value)
        with self.assertRaises(ValueError):
            validate_capabilities(GenerationSettings(temperature=0.1), INFO)
        with self.assertRaises(ValueError):
            validate_capabilities(
                GenerationSettings(reasoning_effort="disabled"),
                {
                    **INFO,
                    "reasoning": {"mandatory": True, "supported_efforts": ["low"]},
                },
            )
        with self.assertRaises(ValueError):
            validate_capabilities(
                GenerationSettings(max_output_tokens=8192),
                {**INFO, "top_provider": {"max_completion_tokens": 4096}},
            )

    def test_empty_truncated_reasoning_and_json_errors_distinct(self):
        for value, code in (
            (response("", reasoning=0), "empty_content"),
            (response("", reasoning=32), "reasoning_without_content"),
            (response('{"problem":', "length"), "token_limit"),
        ):
            with self.subTest(code=code), self.assertRaises(AnalysisError) as captured:
                self.call(value, GenerationSettings())
            self.assertEqual(captured.exception.diagnostics["error_code"], code)
            self.assertEqual(captured.exception.diagnostics["http_status"], 200)
            self.assertEqual(captured.exception.diagnostics["cost_usd"], 0.001)
        with patch(
            "llm.analysis.chat",
            return_value={
                "text": "{",
                "diagnostics": {"finish_reason": "stop", "output_tokens": 2},
            },
        ):
            with self.assertRaises(AnalysisError) as captured:
                analyze({"query": "SELECT 1"}, GenerationSettings())
        self.assertEqual(captured.exception.diagnostics["error_code"], "malformed_json")

    def test_schema_and_application_failures_remain_distinct(self):
        with patch(
            "llm.analysis.chat",
            return_value={"text": "{}", "diagnostics": {"finish_reason": "stop"}},
        ):
            with self.assertRaises(AnalysisError) as captured:
                analyze({"query": "SELECT 1"}, GenerationSettings())
            self.assertEqual(
                captured.exception.diagnostics["error_code"], "schema_validation_failed"
            )
            with patch(
                "llm.analysis.parse_analysis", side_effect=RuntimeError("internal")
            ):
                with self.assertRaises(AnalysisError) as captured:
                    analyze({"query": "SELECT 1"}, GenerationSettings())
            self.assertEqual(
                captured.exception.diagnostics["error_code"],
                "application_processing_error",
            )

    def test_invalid_reasoning_metadata_cannot_break_frontend_contract(self):
        with self.assertRaises(AnalysisError) as captured:
            self.call(response(reasoning="invalid"), GenerationSettings())
        self.assertEqual(captured.exception.diagnostics["error_code"], "invalid_usage")
        self.assertIsNone(captured.exception.diagnostics["reasoning_tokens"])

    def test_visibility_test_no_sql_and_no_preferences_mutation(self):
        with (
            patch("api.services.ai_settings.model_capabilities", return_value=INFO),
            patch(
                "api.services.ai_settings.chat",
                return_value={"text": "OK", "diagnostics": {"finish_reason": "stop"}},
            ) as generate,
        ):
            result = visibility_test(Settings(enable_llm=True))
        self.assertTrue(result["success"])
        self.assertNotIn("SELECT", str(generate.call_args.args[0]))
        self.assertEqual(generate.call_args.kwargs["generation"].max_output_tokens, 512)

    def test_failed_analysis_preserves_usage_and_never_becomes_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                root=ROOT,
                data_dir=Path(directory),
                enable_llm=True,
                enable_sql=False,
                test_database_confirmed=False,
            )
            store = Store(settings.database_path)
            job = store.create_job(
                "run",
                {
                    "mode": "analysis",
                    "query_id": "top_products",
                    "condition": "C1_query",
                    "confirm_external_model": True,
                },
            )
            failure = AnalysisError(
                "Token limit",
                {
                    "finish_reason": "length",
                    "output_tokens": 512,
                    "reasoning_tokens": 500,
                    "error_code": "token_limit",
                },
                '{"problem":"partial',
            )
            with patch("api.services.analysis.analyze", side_effect=failure):
                result = execute_analysis(job, settings, store)
            self.assertEqual(store.job(job["id"])["status"], "FAILED")
            self.assertEqual(
                result["attempts"][0]["diagnostics"]["reasoning_tokens"], 500
            )
            self.assertIsNone(result["attempts"][0]["proposed_sql"])
            self.assertEqual(result["accepted_count"], 0)


class PersistenceTests(unittest.TestCase):
    def test_store_restart_precedence_and_reset(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, ENV):
            path = Path(directory) / "test.sqlite3"
            store = Store(path)
            store.save_generation_settings(
                GenerationSettings(max_output_tokens=8192, reasoning_effort="high")
            )
            with patch.dict(os.environ, {"SUE_MAX_OUTPUT_TOKENS": "1024"}):
                restored = Store(path)
                self.assertEqual(restored.generation_settings().max_output_tokens, 8192)
                restored.reset_generation_settings()
                self.assertEqual(restored.generation_settings().max_output_tokens, 1024)

    def test_api_settings_reject_security_fields_and_require_test_consent(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, ENV),
            patch("api.services.ai_settings.model_capabilities", return_value=INFO),
        ):
            app = create_app(
                Settings(
                    root=ROOT,
                    data_dir=Path(directory),
                    enable_llm=False,
                    enable_sql=False,
                    test_database_confirmed=False,
                )
            )
            with TestClient(app) as client:
                current = client.get("/api/settings/ai")
                self.assertEqual(current.status_code, 200)
                self.assertNotIn(ENV["OPENROUTER_API_KEY"], current.text)
                value = {
                    "max_output_tokens": 8192,
                    "reasoning_effort": "medium",
                    "temperature": None,
                }
                self.assertEqual(
                    client.put("/api/settings/ai", json=value).status_code, 200
                )
                self.assertEqual(
                    client.get("/api/settings/ai").json()["settings"], value
                )
                self.assertEqual(
                    client.put(
                        "/api/settings/ai", json={**value, "sql_enabled": True}
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    client.put(
                        "/api/settings/ai",
                        json=value,
                        headers={"Origin": "https://untrusted.invalid"},
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post("/api/settings/ai/test", json={}).status_code, 422
                )
                self.assertEqual(
                    client.post(
                        "/api/settings/ai/test", json={"confirm_external_model": True}
                    ).status_code,
                    409,
                )
                self.assertFalse(client.get("/api/system/status").json()["sql_enabled"])


if __name__ == "__main__":
    unittest.main()
