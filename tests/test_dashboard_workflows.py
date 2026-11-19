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

from api.config import (
    LIVE_PROFILE_ORDERS,
    Settings,
)
from api.services.artifacts import CASE_MAP
from api.services.database import TestDatabaseError, connect_test_database
from api.services.storage import Store
from api.services.workflows import execute_run
from llm.analysis import AnalysisError
from llm.client import SYSTEM

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
        "rewrite_status": "candidate" if candidate else "no_safe_rewrite",
        "optimized_sql": candidate,
        "rewrite_explanation": "Orders filteren in een CTE."
        if candidate
        else "Geen modelvariant gevonden.",
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

        def rejected(
            conn,
            case,
            proposal,
            *,
            progress,
            recent_order_limit,
            correctness_timeout_ms,
            benchmark_timeout_ms,
        ):
            self.assertIs(conn, connection)
            self.assertIs(case, CASE)
            self.assertEqual(proposal.sql.strip(), candidate.strip())
            self.assertEqual(recent_order_limit, LIVE_PROFILE_ORDERS)
            self.assertEqual(correctness_timeout_ms, 600_000)
            self.assertEqual(benchmark_timeout_ms, 600_000)
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
        self.assertEqual(payload["messages"][0]["content"], SYSTEM)
        self.assertEqual(result["attempts"][0]["system_prompt"], SYSTEM)
        self.assertEqual(
            result["attempts"][0]["user_prompt"], payload["messages"][1]["content"]
        )
        self.assertNotIn("private-value", str(payload))
        context.assert_called_once_with(
            connection, CASE, None, "C4_stats", recent_order_limit=LIVE_PROFILE_ORDERS
        )
        preflight.assert_called_once()
        evaluate.assert_called_once()
        self.assertEqual(result["model_requests"], 1)
        self.assertEqual(result["attempts"][0]["outcome"], "mismatch")
        self.assertEqual(
            result["attempts"][0]["parameter_checks"][0]["status"], "ROWCOUNT_MISMATCH"
        )
        self.assertEqual(result["attempts"][0]["benchmark"]["status"], "skipped")

    def test_model_context_can_be_selected_without_running_validation(self):
        candidate = CASE.candidates[0].sql
        connection = object()
        for condition, keys in (
            ("C2_schema", ("query", "schema")),
            ("C3_plan", ("query", "schema", "plan")),
            ("C4_stats", ("query", "schema", "plan", "stats")),
        ):
            with (
                self.subTest(condition=condition),
                patch(
                    "llm.analysis._request", return_value=completion(candidate)
                ) as transport,
                patch(
                    "api.services.analysis.connect_test_database",
                    return_value=nullcontext(connection),
                ),
                patch("api.services.analysis.check_case_database"),
                patch(
                    "api.services.analysis.build_context",
                    return_value={
                        key: CASE.original if key == "query" else key for key in keys
                    },
                ) as build,
                patch("api.services.analysis.evaluate") as evaluate,
            ):
                job = self.job(mode="analysis", condition=condition)
                result = execute_run(job, self.settings, self.store)
                self.store.update(job["id"], "COMPLETED", result=result)
            build.assert_called_once_with(
                connection,
                CASE,
                None,
                condition,
                recent_order_limit=LIVE_PROFILE_ORDERS,
            )
            messages = transport.call_args.kwargs["json"]["messages"]
            self.assertEqual(messages[0]["content"], SYSTEM)
            user = json.loads(messages[1]["content"])
            self.assertEqual(
                set(user) & {"query", "schema", "plan", "stats"}, set(keys)
            )
            self.assertEqual(result["attempts"][0]["condition"], condition)
            self.assertEqual(result["attempts"][0]["correctness"], "skipped")
            evaluate.assert_not_called()

    def test_database_context_requires_the_existing_database_confirmation(self):
        with patch("api.services.analysis.connect_test_database") as connection:
            with self.assertRaises(AnalysisError):
                execute_run(
                    self.job(mode="analysis", confirm_sql=False),
                    self.settings,
                    self.store,
                )
        connection.assert_not_called()

    def test_live_run_validates_registered_sql_after_a_valid_response_without_rewrite(
        self,
    ):
        case = CASE_MAP["audit_log_page"]
        reference = case.candidates[0]
        connection = object()
        with (
            patch("llm.analysis._request", return_value=completion(None)) as transport,
            patch(
                "api.services.analysis.connect_test_database",
                side_effect=lambda **kwargs: nullcontext(connection),
            ),
            patch("api.services.analysis.check_case_database"),
            patch(
                "api.services.analysis.evaluate",
                return_value={
                    "case": case.name,
                    "candidate": reference.name,
                    "verdict": "EQUIVALENT_NOT_FASTER",
                    "correctness_status": "passed",
                    "benchmark_status": "warning",
                    "param_sets": 3,
                    "failing_param_sets": 0,
                    "orig_median_ms": 20,
                    "cand_median_ms": 20,
                    "reps": 3,
                    "detail": "Gelijke resultaten; snelheidswinst niet aangetoond.",
                },
            ) as evaluate,
        ):
            result = execute_run(
                self.job(query_id=case.name, condition="C1_query"),
                self.settings,
                self.store,
            )
        transport.assert_called_once()
        evaluate.assert_called_once()
        self.assertEqual(evaluate.call_args.args[2].sql, reference.sql.strip())
        attempt = result["attempts"][0]
        self.assertEqual(attempt["proposal_source"], "case")
        self.assertEqual(attempt["analysis"]["rewrite_status"], "no_safe_rewrite")
        self.assertIsNone(attempt["analysis"]["optimized_sql"])
        self.assertEqual(result["model_requests"], 1)
        stages = {stage["id"]: stage["status"] for stage in result["stages"]}
        self.assertEqual(stages["static"], "passed")
        self.assertEqual(stages["correctness"], "passed")
        self.assertEqual(stages["benchmark"], "warning")
        self.assertEqual(stages["result"], "warning")
        self.assertEqual(attempt["benchmark"]["repetitions"], 3)

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
                self.assertEqual(attempt["parameter_sets"], 3)
                if correctness == "failed":
                    self.assertEqual(attempt["outcome"], "mismatch")
                    self.assertEqual(attempt["benchmark"]["status"], "skipped")
                else:
                    self.assertGreater(attempt["benchmark"]["original_ms"], 0)
                    self.assertEqual(attempt["benchmark"]["repetitions"], 3)
                    self.assertEqual(len(attempt["benchmark"]["measurements"]), 3)
                    self.assertGreaterEqual(
                        attempt["parameter_checks"][0]["original_ms"], 0
                    )

    def test_selected_database_context_without_validation_uses_the_same_system_prompt(
        self,
    ):
        keys = []
        for condition, key in (
            ("C1_query", "query"),
            ("C2_schema", "schema"),
            ("C3_plan", "plan"),
            ("C4_stats", "stats"),
        ):
            keys.append(key)
            with self.subTest(condition=condition):
                job = self.store.create_job(
                    "run",
                    {
                        "mode": "analysis",
                        "query_id": CASE.name,
                        "condition": condition,
                        "confirm_sql": condition != "C1_query",
                        "confirm_external_model": True,
                        "generation_settings": SETTINGS,
                    },
                )
                with (
                    patch("llm.analysis._model_info", return_value=MODEL_INFO),
                    patch(
                        "llm.analysis._request",
                        return_value=completion(CASE.candidates[0].sql),
                    ) as transport,
                    patch("api.services.analysis.evaluate") as evaluate,
                ):
                    result = execute_run(job, self.settings, self.store)
                self.store.update(job["id"], result["lifecycle"], result=result)
                messages = transport.call_args.kwargs["json"]["messages"]
                context = json.loads(messages[1]["content"])
                self.assertEqual(messages[0]["content"], SYSTEM)
                self.assertEqual(
                    set(context) & {"query", "schema", "plan", "stats"}, set(keys)
                )
                self.assertEqual(result["attempts"][0]["condition"], condition)
                self.assertEqual(result["attempts"][0]["correctness"], "skipped")
                evaluate.assert_not_called()

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
                        self.assertEqual(benchmark["repetitions"], 3)
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
