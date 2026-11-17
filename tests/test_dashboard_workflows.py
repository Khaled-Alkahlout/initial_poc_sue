"""Test dashboard orchestration at the provider and PostgreSQL boundaries."""

import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api.config import LIVE_PROFILE_ORDERS, Settings
from api.services.artifacts import CASE_MAP
from api.services.database import TestDatabaseError, connect_test_database
from api.services.storage import Store
from api.services.workflows import execute_run
from llm.analysis import AnalysisError

MODEL = "fixture/model"
SETTINGS = {
    "model": MODEL,
    "max_output_tokens": 2048,
    "reasoning_effort": "xhigh",
}
MODEL_INFO = {
    "id": MODEL,
    "supported_parameters": ["max_tokens", "reasoning", "response_format"],
    "reasoning": {"supported_efforts": ["xhigh"]},
}
CASE = CASE_MAP["top_products"]


def completion(candidate):
    analysis = {
        "schema_version": 2,
        "rewrite_status": "candidate",
        "optimized_sql": candidate,
        "rewrite_explanation": "Orders filteren in een CTE.",
        "problem": "Aggregatie op joins.",
        "root_cause": "Mogelijk veel tussenrijen.",
        "expected_benefit": "Minder tussenrijen.",
        "uncertainty": "Te meten.",
        "correctness_risks": [],
        "index_recommendations": [],
        "validation_recommendations": [],
        "missing_context": [],
    }
    return {
        "model": MODEL,
        "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(analysis)}}
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 200},
    }


class WorkflowCompositionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.settings = Settings(
            data_dir=Path(directory),
            enable_sql=True,
            test_database_confirmed=True,
            enable_llm=True,
        )
        self.store = Store(self.settings.database_path)
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "SUE_LLM_PROVIDER": "openrouter",
                    "SUE_MODEL": "fixture/default",
                    "SUE_ALLOWED_MODELS": MODEL,
                    "OPENROUTER_API_KEY": "unit-key",
                },
            )
        )
        self.enterContext(patch("llm.analysis._model_info", return_value=MODEL_INFO))

    def job(self, **changes):
        return self.store.create_job(
            "run",
            {
                "mode": "live",
                "query_id": CASE.name,
                "condition": "C4_stats",
                "confirm_sql": True,
                "confirm_external_model": True,
                "generation_settings": SETTINGS,
                **changes,
            },
        )

    def test_http_transport_and_validation_use_one_model_response(self):
        candidate = CASE.candidates[0].sql
        connection = object()

        def rejected(conn, case, proposal, *, progress, recent_order_limit):
            self.assertIs(conn, connection)
            self.assertIs(case, CASE)
            self.assertEqual(proposal.sql.strip(), candidate.strip())
            self.assertEqual(recent_order_limit, LIVE_PROFILE_ORDERS)
            return {
                "case": case.name,
                "candidate": proposal.name,
                "verdict": "REJECTED_NOT_EQUIVALENT",
                "correctness_status": "failed",
                "benchmark_status": "skipped",
                "param_sets": 1,
                "failing_param_sets": 1,
                "detail": "Verschillende rijen.",
                "parameter_checks": [
                    {
                        "label": "big/full",
                        "status": "ROWCOUNT_MISMATCH",
                        "detail": "Verschillende rijen.",
                    },
                ],
            }

        with (
            patch(
                "llm.analysis._request", return_value=completion(candidate)
            ) as transport,
            patch(
                "api.services.analysis.connect_test_database",
                side_effect=lambda **kwargs: nullcontext(connection),
            ),
            patch("api.services.analysis.check_case_database") as preflight,
            patch(
                "api.services.analysis.build_context",
                return_value={
                    "query": CASE.original,
                    "schema": "CHECK (name <> 'private-value')",
                },
            ) as context,
            patch("api.services.analysis.evaluate", side_effect=rejected) as evaluate,
        ):
            result = execute_run(self.job(), self.settings, self.store)
        transport.assert_called_once()
        payload = transport.call_args.kwargs["json"]
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["reasoning"], {"effort": "xhigh", "exclude": True})
        self.assertEqual(payload["provider"], {"require_parameters": True})
        self.assertNotIn("private-value", str(payload))
        context.assert_called_once_with(connection, CASE, None, "C4_stats")
        preflight.assert_called_once()
        evaluate.assert_called_once()
        self.assertEqual(result["model_requests"], 1)
        self.assertEqual(result["attempts"][0]["outcome"], "mismatch")
        self.assertEqual(
            result["attempts"][0]["parameter_checks"][0]["status"], "ROWCOUNT_MISMATCH"
        )
        self.assertEqual(result["attempts"][0]["benchmark"]["status"], "skipped")

    def test_rejected_or_failed_generation_does_not_start_query_comparison(self):
        for response, expected in (
            (completion("SELECT pg_sleep(100)"), "safety_rejected"),
            (completion(CASE.original), "safety_rejected"),
            (None, "error"),
        ):
            with self.subTest(expected=expected):
                job = self.job(condition="C1_query")
                with (
                    patch(
                        "llm.analysis._request",
                        return_value=response,
                        side_effect=AnalysisError("Provider timeout")
                        if response is None
                        else None,
                    ) as transport,
                    patch("api.services.analysis.connect_test_database") as connect,
                    patch("api.services.analysis.check_case_database"),
                    patch("api.services.analysis.evaluate") as evaluate,
                ):
                    result = execute_run(job, self.settings, self.store)
                transport.assert_called_once()
                connect.assert_called_once()  # Read-only preflight before generation.
                evaluate.assert_not_called()
                self.assertEqual(result["attempts"][0]["outcome"], expected)
                self.assertEqual(result["attempts"][0]["correctness"], "skipped")
                self.store.update(job["id"], result["lifecycle"], result=result)

    def test_original_rejected_before_context_or_provider(self):
        from dataclasses import replace

        with (
            patch.dict(
                CASE_MAP, {CASE.name: replace(CASE, original="SELECT pg_sleep(100)")}
            ),
            patch("llm.analysis._request") as transport,
            patch("api.services.analysis.connect_test_database") as connect,
        ):
            result = execute_run(self.job(), self.settings, self.store)
        connect.assert_not_called()
        transport.assert_not_called()
        self.assertEqual(result["model_requests"], 0)
        self.assertEqual(result["attempts"][0]["outcome"], "safety_rejected")
        self.assertEqual(result["stages"][1]["status"], "failed")

    def test_postgres_error_classification_does_not_expose_the_driver_message(self):
        class DriverError(Exception):
            pass

        driver = SimpleNamespace(Error=DriverError)
        with (
            patch.dict(sys.modules, {"psycopg": driver}),
            patch.dict(os.environ, {"SUE_DATABASE_URL": "fixture connection data"}),
        ):
            for text, expected in (
                ("could not translate host name", "dns"),
                ("SSL error: certificate verify failed", "tls"),
                ("password authentication failed", "authentication"),
                ("timeout expired", "timeout"),
            ):
                with self.subTest(expected=expected):
                    driver.connect = Mock(
                        side_effect=DriverError(text + " test-secret")
                    )
                    with self.assertRaises(TestDatabaseError) as captured:
                        with connect_test_database():
                            self.fail("failed connection was yielded")
                    self.assertEqual(captured.exception.issue["code"], expected)
                    self.assertNotIn("test-secret", str(captured.exception))


@unittest.skipUnless(
    os.getenv("SUE_SYNTHETIC_TEST_DSN"),
    "Requires a disposable PostgreSQL with the transfer fixture.",
)
class PostgresWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "SUE_DATABASE_URL": os.environ["SUE_SYNTHETIC_TEST_DSN"],
                    "SUE_ENABLE_SQL_RUNS": "1",
                    "SUE_TEST_DATABASE_CONFIRMED": "1",
                    "SUE_ENABLE_LLM": "1",
                    "SUE_LLM_PROVIDER": "openrouter",
                    "SUE_MODEL": MODEL,
                    "OPENROUTER_API_KEY": "unit-key",
                },
            )
        )
        self.settings = Settings(data_dir=Path(directory))
        self.store = Store(self.settings.database_path)

    def test_database_context_rewrite_and_mutation_with_stubbed_transport(self):
        for candidate, correctness, condition in (
            (CASE.candidates[0], "passed", "C1_query"),
            (CASE.candidates[0], "passed", "C4_stats"),
            (CASE.candidates[1], "failed", "C1_query"),
        ):
            with self.subTest(candidate=candidate.name):
                job = self.store.create_job(
                    "run",
                    {
                        "mode": "live",
                        "query_id": CASE.name,
                        "condition": condition,
                        "confirm_sql": True,
                        "confirm_external_model": True,
                        "generation_settings": SETTINGS,
                    },
                )
                with (
                    patch("llm.analysis._model_info", return_value=MODEL_INFO),
                    patch(
                        "llm.analysis._request", return_value=completion(candidate.sql)
                    ) as transport,
                ):
                    result = execute_run(job, self.settings, self.store)
                self.store.update(job["id"], result["lifecycle"], result=result)
                payload = json.loads(
                    transport.call_args.kwargs["json"]["messages"][1]["content"]
                )
                if condition == "C4_stats":
                    self.assertIn("TABLE public.orders", payload["schema"])
                    self.assertIn("Plan Rows", payload["plan"])
                    self.assertNotIn("Filter", payload["plan"])
                    self.assertIn("n_distinct", payload["stats"])
                    self.assertNotIn("mcv", payload["stats"])
                else:
                    self.assertNotIn("schema", payload)
                    self.assertNotIn("plan", payload)
                attempt = result["attempts"][0]
                self.assertEqual(attempt["correctness"], correctness)
                self.assertEqual(attempt["parameter_sets"], 8)
                if correctness == "failed":
                    self.assertEqual(attempt["outcome"], "mismatch")
                    self.assertEqual(attempt["benchmark"]["status"], "skipped")
                else:
                    self.assertGreater(attempt["benchmark"]["original_ms"], 0)
                    self.assertEqual(attempt["benchmark"]["repetitions"], 6)

    def test_unreachable_live_database_stops_before_model_request(self):
        with socket.socket() as endpoint:
            endpoint.bind(("127.0.0.1", 0))
            port = endpoint.getsockname()[1]
            with (
                patch.dict(
                    os.environ,
                    {"SUE_DATABASE_URL": f"host=127.0.0.1 port={port} dbname=fixture"},
                ),
                patch("llm.analysis._request") as transport,
            ):
                job = self.store.create_job(
                    "run",
                    {
                        "mode": "live",
                        "query_id": CASE.name,
                        "condition": "C1_query",
                        "confirm_sql": True,
                        "confirm_external_model": True,
                    },
                )
                result = execute_run(job, self.settings, self.store)
        transport.assert_not_called()
        self.assertEqual(result["lifecycle"], "FAILED")
        self.assertEqual(result["model_requests"], 0)
        attempt = result["attempts"][0]
        issue = attempt["raw_record"]["database_error"]
        self.assertIn(issue["code"], {"unreachable", "timeout"})
        self.assertEqual(issue["phase"], "connect")
        self.assertIsNone(issue["sqlstate"])
        self.assertEqual(attempt["correctness"], "skipped")
        self.assertEqual(attempt["benchmark"]["status"], "skipped")
        self.assertRegex(
            result["error"], "kan de testdatabase niet bereiken|connect-time-out"
        )

    def test_api_validates_saved_proposals_on_the_test_database(self):
        from fastapi.testclient import TestClient

        from api.app import create_app

        with TestClient(create_app(self.settings)) as client:
            for candidate, correctness in (
                (CASE.candidates[0], "passed"),
                (CASE.candidates[1], "failed"),
            ):
                with self.subTest(candidate=candidate.name):
                    source = self.store.create_job(
                        "run",
                        {
                            "mode": "analysis",
                            "query_id": CASE.name,
                            "condition": "C1_query",
                            "confirm_external_model": True,
                            "generation_settings": SETTINGS,
                        },
                    )
                    with (
                        patch("llm.analysis._model_info", return_value=MODEL_INFO),
                        patch(
                            "llm.analysis._request",
                            return_value=completion(candidate.sql),
                        ),
                    ):
                        analysis = execute_run(source, self.settings, self.store)
                    self.store.update(
                        source["id"], analysis["lifecycle"], result=analysis
                    )
                    response = client.post(
                        "/api/runs",
                        json={
                            "mode": "validate",
                            "query_id": CASE.name,
                            "source_id": source["id"],
                            "confirm_sql": True,
                        },
                    )
                    self.assertEqual(response.status_code, 202, response.text)
                    url = "/api/runs/" + response.json()["id"]
                    run = wait_for_run(client, url)
                    self.assertEqual(run["lifecycle"], "COMPLETED", run["error"])
                    self.assertEqual(run["model_requests"], 0)
                    attempt = run["attempts"][0]
                    self.assertEqual(attempt["correctness"], correctness)
                    benchmark = attempt["benchmark"]
                    if correctness == "passed":
                        self.assertEqual(benchmark["repetitions"], 6)
                        self.assertGreater(benchmark["original_ms"], 0)
                        self.assertGreater(benchmark["proposed_ms"], 0)
                    else:
                        self.assertEqual(benchmark["status"], "skipped")
                        self.assertEqual(attempt["outcome"], "mismatch")

    def test_api_worker_keeps_database_mock_as_aa_control(self):
        from fastapi.testclient import TestClient

        from api.app import create_app

        with TestClient(create_app(self.settings)) as client:
            response = client.post(
                "/api/runs",
                json={
                    "mode": "live_mock",
                    "query_id": "top_customers",
                    "condition": "C1_query",
                    "confirm_sql": True,
                },
            )
            self.assertEqual(response.status_code, 202, response.text)
            url = "/api/runs/" + response.json()["id"]
            run = wait_for_run(client, url)
        self.assertEqual(run["lifecycle"], "COMPLETED", run["error"])
        attempt = run["attempts"][0]
        self.assertEqual(run["model_requests"], 0)
        self.assertEqual(attempt["correctness"], "passed")
        self.assertEqual(attempt["outcome"], "not_faster")
        self.assertEqual(attempt["parameter_checks"][-1]["label"], "benchmark")


def wait_for_run(client, url):
    deadline = monotonic() + 35
    while monotonic() < deadline:
        run = client.get(url).json()
        if run["lifecycle"] in {"COMPLETED", "FAILED"}:
            return run
        sleep(0.1)
    raise AssertionError("De worker heeft de run niet binnen 35 seconden afgerond.")
