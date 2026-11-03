"""Real mixed-version history regression and safe API failure contracts."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ConfigDict, create_model

from api.app import create_app
from api.config import ROOT, Settings
from api.schemas import Attempt, RunDetail
from api.services.runtime import LOADED_REVISION, RuntimeMismatch, ensure_current
from llm.analysis import Analysis, AnalysisError
from test_ai_analysis import DOCUMENT, ENV
from test_generation_settings import INFO


class APIErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            root=ROOT,
            data_dir=Path(self.temp.name),
            enable_llm=True,
            enable_sql=False,
            test_database_confirmed=False,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.store = self.app.state.store
        self.env = patch.dict("os.environ", ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.app.state.jobs.close()
        self.temp.cleanup()

    def save_run(self, analysis):
        job = self.store.create_job(
            "run", {"mode": "analysis", "query_id": "top_products"}
        )
        result = RunDetail(
            id=job["id"],
            title="Stored analysis",
            mode="analysis",
            lifecycle="COMPLETED",
            created_at=job["created_at"],
            query_ids=["top_products"],
            attempts=[
                Attempt(
                    id=job["id"] + "~0",
                    run_id=job["id"],
                    query_id="top_products",
                    candidate="structured_ai_analysis",
                    outcome="inconclusive",
                    correctness="skipped",
                    detail="Untested",
                    stages=[],
                    benchmark={},
                    analysis=analysis,
                )
            ],
        )
        self.store.update(job["id"], "COMPLETED", result=result.model_dump())
        return job["id"]

    def test_mixed_v1_v2_history_loads_in_all_affected_endpoints_without_loss(self):
        # Simulate legacy rows without any of the newly added metadata fields.
        legacy_id = self.save_run(Analysis(**DOCUMENT))
        legacy = self.store.job(legacy_id)["result"]
        for key in ("schema_version", "rewrite_status", "rewrite_explanation"):
            legacy["attempts"][0]["analysis"].pop(key)
        self.store.update(legacy_id, "COMPLETED", result=legacy)
        modern_id = self.save_run(
            Analysis(
                **DOCUMENT,
                schema_version=2,
                rewrite_status="candidate",
                rewrite_explanation="Untested candidate",
            )
        )
        # Catalog.tests expects a recorded result stage, as real analyses have.
        for job_id in (legacy_id, modern_id):
            result = self.store.job(job_id)["result"]
            result["attempts"][0]["stages"] = [
                {
                    "id": "result",
                    "label": "Result",
                    "status": "warning",
                    "note": "Untested",
                }
            ]
            self.store.update(job_id, "COMPLETED", result=result)
        before = {j: self.store.job(j)["result"] for j in (legacy_id, modern_id)}
        for path in (
            "/api/overview",
            "/api/queries?top_k=2",
            "/api/queries/top_products",
            "/api/runs",
            "/api/development/tests",
            f"/api/runs/{modern_id}",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
        history = self.client.get("/api/runs").json()
        self.assertTrue({legacy_id, modern_id} <= {r["id"] for r in history})
        self.assertEqual(before, {j: self.store.job(j)["result"] for j in before})

    def test_exact_old_reader_failure_is_diagnosed_without_exposing_the_payload(self):
        run_id = self.save_run(
            Analysis(
                **DOCUMENT,
                schema_version=2,
                rewrite_status="candidate",
                rewrite_explanation="private_schema.secret",
            )
        )
        old = create_model(
            "PreRewriteAnalysis",
            __config__=ConfigDict(extra="forbid", strict=True),
            **{
                k: (v.annotation, v)
                for k, v in Analysis.model_fields.items()
                if k not in {"schema_version", "rewrite_status", "rewrite_explanation"}
            },
        )
        old_attempt = create_model(
            "PreRewriteAttempt", __base__=Attempt, analysis=(old | None, None)
        )
        old_run = create_model(
            "PreRewriteRun", __base__=RunDetail, attempts=(list[old_attempt], [])
        )
        with (
            patch("api.services.catalog.RunDetail", old_run),
            self.assertLogs("sue.api", level="ERROR") as logs,
        ):
            response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "stored_result_incompatible")
        self.assertEqual(
            response.headers["X-Request-ID"], response.json()["request_id"]
        )
        logged = "\n".join(logs.output)
        for field in (
            "schema_version",
            "rewrite_status",
            "rewrite_explanation",
            "extra_forbidden",
            run_id,
            "job_run",
        ):
            self.assertIn(field, logged)
        self.assertNotIn("private_schema.secret", logged + response.text)
        self.assertIsNotNone(self.store.job(run_id)["result"])

    def test_unexpected_errors_are_500_with_safe_traceback_and_request_reference(self):
        with (
            patch.object(
                self.app.state.catalog,
                "overview",
                side_effect=RuntimeError("SELECT secret FROM private_schema"),
            ),
            self.assertLogs("sue.api", level="ERROR") as logs,
        ):
            response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "internal_error")
        self.assertIn("RuntimeError", "\n".join(logs.output))
        self.assertIn("/api/overview", "\n".join(logs.output))
        self.assertNotIn("SELECT secret", response.text + "\n".join(logs.output))

    def test_invalid_input_and_temporary_storage_outage_have_distinct_statuses(self):
        response = self.client.get("/api/queries?top_k=-1")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error_code"], "invalid_input")
        with (
            patch.object(
                self.store,
                "jobs",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
            self.assertLogs("sue.api", level="ERROR"),
        ):
            response = self.client.get("/api/runs")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "storage_unavailable")

    def test_changed_runtime_blocks_api_and_new_workers_before_dispatch(self):
        with (
            patch("api.services.runtime.source_revision", return_value="new-version"),
            patch.object(self.app.state.jobs.pool, "submit") as submit,
            self.assertLogs("sue.api", level="ERROR"),
        ):
            response = self.client.post(
                "/api/runs",
                json={
                    "mode": "analysis",
                    "query_id": "top_products",
                    "confirm_external_model": True,
                },
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error_code"], "runtime_version_mismatch")
            self.assertIn("Herstart", response.json()["detail"])
            with self.assertRaises(RuntimeMismatch):
                self.app.state.jobs.start("test", {"suite": "selection"})
            submit.assert_not_called()
        with self.assertRaises(RuntimeMismatch):
            ensure_current("different-parent-version")
        with patch.object(self.app.state.jobs.pool, "submit"):
            job = self.app.state.jobs.start("test", {"suite": "selection"})
        self.assertEqual(job["config"]["runtime_revision"], LOADED_REVISION)

    def test_model_dependency_failures_are_not_reported_as_invalid_settings(self):
        failure = AnalysisError(
            "Provider tijdelijk niet bereikbaar", {"error_code": "network_or_timeout"}
        )
        with (
            patch("api.services.ai_settings.model_capabilities", side_effect=failure),
            self.assertLogs("sue.api", level="ERROR"),
        ):
            response = self.client.put(
                "/api/settings/ai",
                json={
                    "max_output_tokens": 4096,
                    "reasoning_effort": "low",
                    "temperature": None,
                },
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "llm_request_failed")
        with patch("api.services.ai_settings.model_capabilities", return_value=INFO):
            response = self.client.put(
                "/api/settings/ai", json={"max_output_tokens": 123}
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
