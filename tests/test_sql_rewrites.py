"""Rewrite contract and top_products workflow regression; no provider/DB calls."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.app import create_app
from api.config import ROOT, Settings
from api.services.analysis import execute_analysis
from api.services.artifacts import CASE_MAP, adapt_attempt
from api.services.storage import Store
from llm.analysis import (
    AnalysisError,
    RewriteResponse,
    analyze,
    parse_analysis,
    unchanged_sql,
)
from test_ai_analysis import DOCUMENT, ENV

CASE = CASE_MAP["top_products"]
CANDIDATE = CASE.candidates[0].sql


def document(**changes):
    return {
        **DOCUMENT,
        "schema_version": 2,
        "rewrite_status": "candidate",
        "optimized_sql": CANDIDATE,
        "rewrite_explanation": "Filtered orders CTE; planner may inline it. No measured gain.",
        **changes,
    }


class ResponseContractTests(unittest.TestCase):
    def test_candidate_and_explicit_no_rewrite(self):
        self.assertEqual(
            parse_analysis(json.dumps(document())).optimized_sql, CANDIDATE.strip()
        )
        for status in ("no_safe_rewrite", "insufficient_context"):
            result = parse_analysis(
                json.dumps(
                    document(
                        optimized_sql=None,
                        rewrite_status=status,
                        rewrite_explanation="Cannot remove DISTINCT: multiple variants can occur in one order.",
                    )
                )
            )
            self.assertIsNone(result.optimized_sql)
            self.assertTrue(result.index_recommendations)

    def test_inconsistent_or_unexplained_decisions_fail_visibly(self):
        for changes in (
            {"optimized_sql": None},
            {"optimized_sql": " "},
            {"rewrite_explanation": " "},
            {"rewrite_status": "no_safe_rewrite"},
            {"schema_version": 3},
        ):
            with self.subTest(changes=changes), self.assertRaises(AnalysisError):
                parse_analysis(json.dumps(document(**changes)))
        data = document()
        del data["rewrite_status"]
        with self.assertRaises(AnalysisError):
            parse_analysis(json.dumps(data))

    def test_explicit_legacy_compatibility_and_envelope(self):
        old = parse_analysis(json.dumps({**DOCUMENT, "optimized_sql": None}))
        self.assertEqual(old.schema_version, 1)
        self.assertIsNone(
            old.rewrite_explanation
        )  # Never fabricate the old model's reason.
        self.assertEqual(
            parse_analysis(json.dumps({"analysis": document()})).schema_version, 2
        )
        text = f"```sql\n{CANDIDATE}\n```\nUntested."
        self.assertEqual(
            parse_analysis(text, response_version="legacy_text_v0").optimized_sql,
            CANDIDATE.strip(),
        )
        for response in ({"sql": CANDIDATE}, {"text": text}):
            attempt = adapt_attempt({"case": CASE.name}, "legacy", 0, response=response)
            self.assertEqual(attempt.proposed_sql, CANDIDATE.strip())
        failed = adapt_attempt(
            {"case": CASE.name},
            "legacy",
            0,
            response={"text": "```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```"},
        )
        self.assertEqual(failed.validation_state, "rewrite_parsing_failed")

    def test_new_schema_and_focused_prompt_use_same_model_and_no_retry(self):
        with (
            patch.dict(os.environ, ENV),
            patch(
                "llm.analysis.chat", return_value={"text": json.dumps(document())}
            ) as chat,
        ):
            result, metadata = analyze(
                {"query": CASE.original, "known_bottlenecks": "DISTINCT sorting"},
                focused=True,
            )
        chat.assert_called_once()
        self.assertEqual(chat.call_args.args[1], ENV["SUE_MODEL"])
        schema = chat.call_args.kwargs["schema"]
        self.assertEqual(next(iter(schema["properties"])), "optimized_sql")
        self.assertTrue(
            {"rewrite_status", "rewrite_explanation", "schema_version"}
            <= set(schema["required"])
        )
        self.assertFalse(schema["additionalProperties"])
        prompt = chat.call_args.args[0][0]["content"]
        for instruction in (
            "pre-aggregatie",
            "DISTINCT",
            "NULL",
            "UUID",
            "LIMIT",
            "known_bottlenecks",
        ):
            self.assertIn(instruction, prompt)
        self.assertTrue(metadata["diagnostics"]["structured_parse_success"])
        self.assertEqual(result.rewrite_status, "candidate")

    def test_unchanged_detection_preserves_literals_and_parameters(self):
        self.assertTrue(unchanged_sql(CASE.original, CASE.original + "\n-- cosmetic"))
        self.assertFalse(
            unchanged_sql(CASE.original, CASE.original.replace("%(to)s", "%(from)s"))
        )
        self.assertFalse(unchanged_sql(CASE.original, CASE.candidates[1].sql))


class RewriteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            root=ROOT,
            data_dir=Path(self.temp.name),
            enable_llm=True,
            enable_sql=False,
            test_database_confirmed=False,
        )
        self.store = Store(self.settings.database_path)
        self.env = patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def execute(self, doc=None, **changes):
        job = self.store.create_job(
            "run",
            {
                "mode": "analysis",
                "query_id": CASE.name,
                "condition": "C4_stats",
                "confirm_external_model": True,
                **changes,
            },
        )
        with patch(
            "api.services.analysis.analyze",
            return_value=(RewriteResponse(**(doc or document())), {"seconds": 0.1}),
        ) as call:
            result = execute_analysis(job, self.settings, self.store)
        self.store.update(job["id"], "COMPLETED", result=result)
        return self.store.job(job["id"]), call

    def test_top_products_candidate_survives_static_storage_and_readback(self):
        job, call = self.execute()
        attempt = job["result"]["attempts"][0]
        self.assertEqual(attempt["proposed_sql"], CANDIDATE.strip())
        self.assertTrue(attempt["diagnostics"]["static_validation_accepted"])
        self.assertTrue(attempt["diagnostics"]["sql_stored_success"])
        self.assertEqual(attempt["validation_state"], "validation_unavailable")
        self.assertEqual(attempt["correctness"], "skipped")
        self.assertEqual(attempt["benchmark"]["status"], "skipped")
        self.assertIn("count(DISTINCT o.id)", call.call_args.args[0]["query"])

    def test_no_rewrite_static_rejection_and_unchanged_are_distinct(self):
        for doc, expected in (
            (
                document(optimized_sql=None, rewrite_status="no_safe_rewrite"),
                "no_rewrite_proposed",
            ),
            (document(optimized_sql="DELETE FROM orders"), "rewrite_static_rejected"),
            (document(optimized_sql=CASE.original), "rewrite_static_rejected"),
        ):
            job, _ = self.execute(doc)
            attempt = job["result"]["attempts"][0]
            self.assertEqual(attempt["validation_state"], expected)
            self.assertEqual(
                bool(attempt["proposed_sql"]), doc["optimized_sql"] is not None
            )
            self.assertTrue(attempt["analysis"]["index_recommendations"])

    def test_focused_request_reuses_source_and_retains_previous_result(self):
        original, _ = self.execute(
            document(optimized_sql=None, rewrite_status="no_safe_rewrite")
        )
        focused, call = self.execute(rewrite_only=True, source_id=original["id"])
        self.assertTrue(call.call_args.kwargs["focused"])
        blocks = call.call_args.args[0]
        self.assertEqual(blocks["query"], CASE.original)
        self.assertEqual(blocks["known_bottlenecks"], DOCUMENT["root_cause"])
        self.assertEqual(focused["result"]["source_id"], original["id"])
        self.assertIsNone(
            self.store.job(original["id"])["result"]["attempts"][0]["proposed_sql"]
        )

    def test_parse_failure_keeps_private_output_and_no_public_payload(self):
        job = self.store.create_job(
            "run",
            {
                "mode": "analysis",
                "query_id": CASE.name,
                "condition": "C4_stats",
                "confirm_external_model": True,
            },
        )
        raw = '{"optimized_sql":"SELECT private_schema.secret FROM confidential_table",'
        with patch(
            "api.services.analysis.analyze",
            side_effect=AnalysisError(
                "Invalid response",
                {"error_code": "malformed_json", "structured_parse_success": False},
                raw,
            ),
        ):
            result = execute_analysis(job, self.settings, self.store)
        attempt = result["attempts"][0]
        self.assertEqual(attempt["validation_state"], "rewrite_parsing_failed")
        self.assertTrue(attempt["diagnostics"]["secure_output_preserved"])
        self.assertNotIn(raw, json.dumps(result))
        self.assertIsNone(attempt["proposed_sql"])
        files = list(
            (self.settings.data_dir / "private-model-diagnostics").glob("*.bin")
        )
        self.assertEqual(len(files), 1)
        if os.name == "nt":
            self.assertNotIn(raw.encode(), files[0].read_bytes())

    def test_api_source_checks_and_display_acknowledgement(self):
        job, _ = self.execute()
        app = create_app(self.settings)
        with (
            TestClient(app) as client,
            patch.object(
                app.state.jobs,
                "start",
                side_effect=lambda kind, config: self.store.create_job(kind, config),
            ),
        ):
            self.assertEqual(
                client.post(
                    f"/api/runs/{job['id']}/rewrite-display",
                    json={"sql_displayed": True},
                ).status_code,
                204,
            )
            attempt = client.get(f"/api/runs/{job['id']}").json()["attempts"][0]
            self.assertTrue(attempt["diagnostics"]["frontend_sql_displayed"])
            self.assertEqual(
                self.store.job(job["id"])["completed_at"], job["completed_at"]
            )
            payload = {
                "mode": "analysis",
                "query_id": CASE.name,
                "rewrite_only": True,
                "source_id": job["id"],
                "confirm_external_model": True,
            }
            self.assertEqual(
                client.post(
                    "/api/runs", json={**payload, "source_id": "missing"}
                ).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/runs", json={**payload, "query_id": "top_customers"}
                ).status_code,
                422,
            )
            self.assertEqual(
                client.post(
                    "/api/runs", json={**payload, "confirm_external_model": False}
                ).status_code,
                422,
            )
            self.assertEqual(client.post("/api/runs", json=payload).status_code, 202)


if __name__ == "__main__":
    unittest.main()
