"""Provider, contracts, safe workflow and API tests; no external calls or SQL."""

import json
import os
import tempfile
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import httpx
from fastapi.testclient import TestClient
from api.app import create_app
from api.config import Settings, ROOT
from api.schemas import RunDetail
from api.services.analysis import execute_analysis
from api.services.jobs import BusyError
from api.services.storage import Store
from api.services.sql_safety import proposal_check
from llm.analysis import (
    Analysis,
    AnalysisError,
    configuration,
    parse_analysis,
    chat,
    _model_info,
)

ENV = {
    "SUE_ENABLE_LLM": "1",
    "SUE_LLM_PROVIDER": "openrouter",
    "SUE_MODEL": "anthropic/claude-haiku-5.5",
    "OPENROUTER_API_KEY": "sk-or-unit-secret",
    "SUE_ENABLE_SQL_RUNS": "0",
    "SUE_TEST_DATABASE_CONFIRMED": "0",
}
DOCUMENT = dict(
    problem="Veel werk bij aggregatie.",
    root_cause="Mogelijke joinbelasting; niet bewezen.",
    optimized_sql="SELECT 1",
    index_recommendations=["Controleer bestaande indexen; geen DDL uitvoeren."],
    expected_benefit="Mogelijk minder werk.",
    correctness_risks=["NULL en duplicaten vergelijken."],
    uncertainty="Geen live plan beschikbaar.",
    validation_recommendations=["Test dezelfde parameters."],
    missing_context=["Actuele indexen en plan."],
)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        _model_info.cache_clear()

    def tearDown(self):
        self.env.stop()
        _model_info.cache_clear()

    def test_configuration_separates_keys_and_legacy(self):
        self.assertEqual(
            configuration(), ("openrouter", ENV["SUE_MODEL"], ENV["OPENROUTER_API_KEY"])
        )
        with patch.dict(
            os.environ,
            {
                "SUE_LLM_PROVIDER": "anthropic",
                "SUE_MODEL": "claude-legacy",
                "ANTHROPIC_API_KEY": "direct",
            },
        ):
            self.assertEqual(configuration(), ("anthropic", "claude-legacy", "direct"))

    def test_schema_rejects_missing_wrong_types_and_extra_claims(self):
        self.assertEqual(parse_analysis(json.dumps(DOCUMENT)).optimized_sql, "SELECT 1")
        for value in (
            {},
            {**DOCUMENT, "problem": 123},
            {**DOCUMENT, "measured_speedup": 5},
            {**DOCUMENT, "optimized_sql": " "},
        ):
            with self.subTest(value=value), self.assertRaises(AnalysisError):
                parse_analysis(json.dumps(value))

    def test_openrouter_exact_model_schema_metadata(self):
        catalog = {
            "data": [
                {"id": ENV["SUE_MODEL"], "supported_parameters": ["response_format"]}
            ]
        }
        response = {
            "model": ENV["SUE_MODEL"],
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(DOCUMENT)}}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.002},
        }
        client = Mock()
        client.request.side_effect = [
            httpx.Response(200, json=catalog),
            httpx.Response(200, json=response),
        ]
        with patch("llm.analysis.httpx.Client") as constructor:
            constructor.return_value.__enter__.return_value = client
            result = chat(
                [{"role": "system", "content": "test"}],
                ENV["SUE_MODEL"],
                schema=Analysis.model_json_schema(),
            )
        self.assertEqual(
            client.request.call_args.kwargs["json"]["model"], ENV["SUE_MODEL"]
        )
        self.assertEqual(
            client.request.call_args.kwargs["headers"]["Authorization"],
            "Bearer " + ENV["OPENROUTER_API_KEY"],
        )
        self.assertNotIn("models", client.request.call_args.kwargs["json"])
        self.assertEqual(result["cost_usd"], 0.002)
        self.assertEqual(result["provider"], "openrouter")

    def test_misplaced_provider_keys_are_explained_not_reused(self):
        for values, message in (
            (
                {"OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "sk-or-unit-secret"},
                "staat onder ANTHROPIC_API_KEY",
            ),
            (
                {
                    "SUE_LLM_PROVIDER": "anthropic",
                    "ANTHROPIC_API_KEY": "sk-or-unit-secret",
                },
                "niet rechtstreeks naar Anthropic",
            ),
            ({"OPENROUTER_API_KEY": "sk-ant-unit-secret"}, "directe Anthropic-key"),
        ):
            with (
                self.subTest(values=values),
                patch.dict(os.environ, values),
                self.assertRaisesRegex(AnalysisError, message),
            ):
                configuration()

    def test_unavailable_model_never_generates_or_substitutes(self):
        client = Mock()
        client.request.return_value = httpx.Response(200, json={"data": []})
        with patch("llm.analysis.httpx.Client") as constructor:
            constructor.return_value.__enter__.return_value = client
            with self.assertRaisesRegex(AnalysisError, "geen ander model"):
                chat([], ENV["SUE_MODEL"])
        self.assertEqual(client.request.call_count, 1)

    def test_errors_are_safe_and_generation_does_not_retry(self):
        for code in (401, 402, 404, 429, 500):
            with (
                self.subTest(code=code),
                patch("llm.analysis._model_info", return_value={}),
                patch("llm.analysis.httpx.Client") as constructor,
            ):
                client = constructor.return_value.__enter__.return_value
                client.request.return_value = httpx.Response(
                    code, json={"error": ENV["OPENROUTER_API_KEY"]}
                )
                with self.assertRaises(AnalysisError) as error:
                    chat([], ENV["SUE_MODEL"])
                self.assertNotIn(ENV["OPENROUTER_API_KEY"], str(error.exception))
                self.assertEqual(client.request.call_count, 1)

    def test_timeout_no_generation_retry(self):
        with (
            patch("llm.analysis._model_info", return_value={}),
            patch("llm.analysis.httpx.Client") as constructor,
        ):
            client = constructor.return_value.__enter__.return_value
            client.request.side_effect = httpx.ReadTimeout("private detail")
            with self.assertRaisesRegex(AnalysisError, "niet automatisch herhaald"):
                chat([], ENV["SUE_MODEL"])
            self.assertEqual(client.request.call_count, 1)

    def test_truncated_or_wrong_model_response_rejected(self):
        for model, finish in (("other", "stop"), (ENV["SUE_MODEL"], "length")):
            with (
                patch("llm.analysis._model_info", return_value={}),
                patch("llm.analysis.httpx.Client") as constructor,
            ):
                constructor.return_value.__enter__.return_value.request.return_value = (
                    httpx.Response(
                        200,
                        json={
                            "model": model,
                            "choices": [
                                {"finish_reason": finish, "message": {"content": "{}"}}
                            ],
                        },
                    )
                )
                with self.assertRaises(AnalysisError):
                    chat([], ENV["SUE_MODEL"])


class AnalysisWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(
            root=ROOT,
            data_dir=Path(self.directory.name),
            enable_sql=False,
            test_database_confirmed=False,
            enable_llm=True,
        )
        self.store = Store(self.settings.database_path)
        self.env = patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def job(self, **values):
        return self.store.create_job(
            "run",
            {
                "mode": "analysis",
                "query_id": "top_products",
                "condition": "C4_stats",
                "confirm_external_model": True,
                **values,
            },
        )

    def test_no_database_analysis_saved_unvalidated_and_duplicate_prevented(self):
        job = self.job()
        with self.assertRaises(BusyError):
            self.job()
        with patch(
            "api.services.analysis.analyze",
            return_value=(
                Analysis(**DOCUMENT),
                {"seconds": 0.5, "input_tokens": 10, "output_tokens": 20},
            ),
        ) as generate:
            result = execute_analysis(job, self.settings, self.store)
        generate.assert_called_once()
        self.assertIn("is_synthetic", generate.call_args.args[0]["telemetry"])
        attempt = result["attempts"][0]
        self.assertEqual(attempt["correctness"], "skipped")
        self.assertEqual(attempt["benchmark"]["status"], "skipped")
        self.assertEqual(attempt["validation_state"], "validation_unavailable")
        self.assertEqual(result["model_requests"], 1)
        self.store.update(job["id"], "COMPLETED", result=result)
        stored = RunDetail.model_validate(self.store.job(job["id"])["result"])
        self.assertEqual(stored.attempts[0].analysis.problem, DOCUMENT["problem"])

    def test_no_generation_without_confirmation(self):
        with patch("api.services.analysis.analyze") as generate:
            with self.assertRaises(AnalysisError):
                execute_analysis(
                    self.job(confirm_external_model=False), self.settings, self.store
                )
            generate.assert_not_called()

    def test_stored_validation_statuses_and_no_new_model_request(self):
        job = self.job()
        with patch(
            "api.services.analysis.analyze",
            return_value=(Analysis(**DOCUMENT), {"seconds": 0.2}),
        ):
            original = execute_analysis(job, self.settings, self.store)
        self.store.update(job["id"], "COMPLETED", result=original)
        settings = Settings(
            root=ROOT,
            data_dir=Path(self.directory.name),
            enable_sql=True,
            test_database_confirmed=True,
        )
        conn = Mock()
        driver = SimpleNamespace(connect=MagicMock())
        driver.connect.return_value.__enter__.return_value = conn
        for verdict, detail, expected in (
            ("ACCEPTED", "", "validated_improvement"),
            ("REJECTED_NOT_EQUIVALENT", "VALUE_MISMATCH", "correctness_failed"),
            ("REJECTED_NOT_EQUIVALENT", "EXEC_ERROR: unit", "validation_error"),
        ):
            task = self.store.create_job(
                "run",
                {
                    "mode": "validate",
                    "query_id": "top_products",
                    "source_id": job["id"],
                    "confirm_sql": True,
                },
            )
            evaluate = Mock(
                return_value={
                    "case": "top_products",
                    "candidate": "stored",
                    "verdict": verdict,
                    "param_sets": 2,
                    "failing_param_sets": 0 if verdict == "ACCEPTED" else 1,
                    "detail": detail,
                    "orig_median_ms": 100,
                    "cand_median_ms": 20,
                    "speedup": 5,
                    "reps": 7,
                }
            )
            with (
                patch.dict(
                    sys.modules,
                    {
                        "psycopg": driver,
                        "scripts.run_validation": SimpleNamespace(evaluate=evaluate),
                    },
                ),
                patch.dict(os.environ, {"SUE_DATABASE_URL": "postgresql://unit-only"}),
                patch("cases.cases.make_ctx", return_value={}),
                patch("api.services.analysis.analyze") as generation,
            ):
                result = execute_analysis(task, settings, self.store)
            generation.assert_not_called()
            self.assertEqual(result["model_requests"], 0)
            self.assertEqual(result["attempts"][0]["validation_state"], expected)
            self.store.update(task["id"], "COMPLETED", result=result)

    def test_validation_requires_both_flags_before_connecting(self):
        for enable, confirm in ((False, False), (True, False), (False, True)):
            self.settings = Settings(
                root=ROOT,
                data_dir=Path(self.directory.name),
                enable_sql=enable,
                test_database_confirmed=confirm,
                enable_llm=True,
            )
            job = {
                "id": "test",
                "created_at": "now",
                "config": {
                    "mode": "validate",
                    "query_id": "top_products",
                    "confirm_sql": True,
                },
            }
            with self.assertRaisesRegex(AnalysisError, "SQL-validatie uitgeschakeld"):
                execute_analysis(job, self.settings, Mock())

    def test_sql_execution_admission(self):
        self.assertTrue(proposal_check("SELECT 1")[0])
        for sql in (
            "DELETE FROM x",
            "SELECT 1; SELECT 2",
            "SELECT * INTO other FROM x",
            "SELECT pg_sleep(100)",
            "SELECT set_config('x', 'y', false)",
        ):
            with self.subTest(sql=sql):
                self.assertFalse(proposal_check(sql)[0])

    def test_api_analysis_available_without_sql_and_secrets_hidden(self):
        app = create_app(self.settings)
        with (
            TestClient(app) as client,
            patch.object(
                app.state.jobs,
                "start",
                side_effect=lambda kind, config: self.store.create_job(kind, config),
            ),
        ):
            status = client.get("/api/system/status")
            self.assertNotIn(ENV["OPENROUTER_API_KEY"], status.text)
            modes = {m["id"]: m for m in status.json()["run_modes"]}
            self.assertTrue(modes["analysis"]["available"])
            self.assertFalse(modes["validate"]["available"])
            payload = {
                "mode": "analysis",
                "query_id": "top_products",
                "confirm_external_model": True,
            }
            self.assertEqual(
                client.post(
                    "/api/runs", json={**payload, "confirm_external_model": False}
                ).status_code,
                422,
            )
            self.assertEqual(client.post("/api/runs", json=payload).status_code, 202)
            self.assertEqual(
                client.post(
                    "/api/runs", json={**payload, "mode": "validate"}
                ).status_code,
                409,
            )


if __name__ == "__main__":
    unittest.main()
