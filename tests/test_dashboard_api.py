import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.app import create_app
from api.config import ROOT, Settings
from api.schemas import Overview, QueryCollection, RunDetail, SystemStatus


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(
            root=ROOT,
            data_dir=Path(self.directory.name),
            enable_sql=False,
            test_database_confirmed=False,
            enable_llm=False,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def wait_for(self, url):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = self.client.get(url).json()
            if value["lifecycle"] in {"COMPLETED", "FAILED"}:
                return value
            time.sleep(0.1)
        self.fail("Worker did not finish within test deadline")

    def test_typed_overview_and_existing_selection_are_connected(self):
        overview = Overview.model_validate(self.client.get("/api/overview").json())
        queries = QueryCollection.model_validate(
            self.client.get("/api/queries?top_k=1").json()
        )
        self.assertEqual(queries.queries[0].query_id, "top_products")
        self.assertEqual(queries.queries[0].impact_ms, 500000)
        self.assertEqual(sum(q.selected for q in queries.queries), 1)
        self.assertTrue(all(q.is_synthetic for q in queries.queries))
        self.assertEqual(
            next(m.value for m in overview.metrics if m.id == "requests"), 50
        )

    def test_selection_exclusion_uses_the_domain_module(self):
        data = self.client.get("/api/queries?exclude_query=top_products").json()
        excluded = next(q for q in data["queries"] if q["query_id"] == "top_products")
        self.assertIn("EXCLUDED_QUERY_ID", excluded["reason_codes"])
        self.assertFalse(excluded["selected"])

    def test_historical_run_retains_status_and_missing_durations(self):
        run = RunDetail.model_validate(
            self.client.get("/api/runs/llm-20261027-220802").json()
        )
        self.assertEqual(run.mode, "historical")
        self.assertEqual(run.attempt_count, 12)
        self.assertIsNone(run.attempts[0].stages[4].duration_ms)
        self.assertEqual(run.attempts[0].raw_verdict, "ACCEPTED")

    def test_missing_resources_and_invalid_inputs(self):
        self.assertEqual(self.client.get("/api/queries/not-a-case").status_code, 404)
        self.assertEqual(self.client.get("/api/runs/not-a-run").status_code, 404)
        self.assertEqual(self.client.get("/api/queries?top_k=-1").status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/runs", json={"mode": "mock", "query_id": "unknown"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/api/runs",
                json={
                    "mode": "mock",
                    "query_id": "top_products",
                    "sql": "DROP TABLE x",
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/api/development/tests/run",
                json={"suite": "shell", "command": "anything"},
            ).status_code,
            422,
        )

    def test_live_operations_are_disabled_by_default(self):
        status = SystemStatus.model_validate(
            self.client.get("/api/system/status").json()
        )
        self.assertEqual(status.database_status, "not_checked")
        self.assertFalse(
            next(mode.available for mode in status.run_modes if mode.id == "live")
        )
        response = self.client.post(
            "/api/runs",
            json={
                "mode": "live",
                "query_id": "top_products",
                "confirm_sql": True,
                "confirm_external_model": True,
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_untrusted_origin_and_host_are_rejected(self):
        self.assertEqual(
            self.client.post(
                "/api/runs",
                json={"mode": "mock", "query_id": "top_products"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/system/status", headers={"Host": "untrusted.example"}
            ).status_code,
            400,
        )

    def test_configuration_does_not_leak_credentials(self):
        with patch.dict(
            os.environ,
            {
                "SUE_DATABASE_URL": "postgresql://user:never-expose-this@localhost/test",
                "ANTHROPIC_API_KEY": "sk-ant-do-not-display",
                "SUE_MODEL": "configured-model",
            },
        ):
            response = self.client.get("/api/system/status")
            self.assertNotIn("never-expose-this", response.text)
            self.assertNotIn("sk-ant-do-not-display", response.text)
            self.assertTrue(response.json()["database_configured"])

    def test_feedback_persists_separately_and_does_not_modify_result(self):
        target = "validation-20261027-195356~0"
        before = self.client.get(f"/api/development/tests/{target}").json()
        value = {
            "target_type": "test",
            "target_id": target,
            "label": "incorrect",
            "comment": "Semantische aanname onderzoeken.",
            "reviewer": "IN",
        }
        self.assertEqual(
            self.client.post("/api/development/feedback", json=value).status_code, 201
        )
        self.assertEqual(
            self.client.get(f"/api/development/feedback?target_id={target}").json()[0][
                "label"
            ],
            "incorrect",
        )
        self.assertEqual(
            self.client.get(f"/api/development/tests/{target}").json(), before
        )
        from api.services.storage import Store

        self.assertEqual(len(Store(self.settings.database_path).feedback(target)), 1)
        value["target_id"] = "unknown"
        self.assertEqual(
            self.client.post("/api/development/feedback", json=value).status_code, 404
        )

    def test_real_replay_worker_does_not_remeasure(self):
        response = self.client.post(
            "/api/runs",
            json={
                "mode": "replay",
                "query_id": "top_products",
                "condition": "C2_schema",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["lifecycle"], "PENDING")
        run = self.wait_for("/api/runs/" + response.json()["id"])
        self.assertEqual(run["lifecycle"], "COMPLETED", run.get("error"))
        self.assertEqual(run["model_requests"], 0)
        self.assertEqual(run["attempts"][0]["benchmark"]["origin"], "historical")
        self.assertEqual(run["attempts"][0]["stages"][2]["status"], "skipped")
        self.assertTrue(run["source_id"].startswith("llm-"))

    def test_real_offline_mock_does_not_claim_correctness_or_speedup(self):
        response = self.client.post(
            "/api/runs",
            json={
                "mode": "mock",
                "query_id": "revenue_orders",
                "condition": "C1_query",
            },
        )
        run = self.wait_for("/api/runs/" + response.json()["id"])
        self.assertEqual(run["lifecycle"], "COMPLETED", run.get("error"))
        self.assertEqual(run["model_requests"], 0)
        attempt = run["attempts"][0]
        self.assertEqual(attempt["correctness"], "skipped")
        self.assertEqual(attempt["benchmark"]["status"], "skipped")
        self.assertEqual(attempt["outcome"], "inconclusive")
        self.assertIsNone(attempt["benchmark"]["speedup"])

    def test_allowlisted_unittest_worker_returns_real_tests(self):
        response = self.client.post(
            "/api/development/tests/run", json={"suite": "selection"}
        )
        self.assertEqual(response.status_code, 202)
        result = self.wait_for("/api/development/executions/" + response.json()["id"])
        self.assertEqual(result["lifecycle"], "COMPLETED", result.get("error"))
        self.assertGreater(len(result["tests"]), 10)
        self.assertTrue(all(test["status"] == "passed" for test in result["tests"]))
        self.assertTrue(all(test["origin"] == "current" for test in result["tests"]))
        self.assertEqual(
            self.client.get(
                "/api/development/tests/" + result["tests"][0]["id"]
            ).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
