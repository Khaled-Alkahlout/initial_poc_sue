"""Verify live-path composition with fake service boundaries, never real SQL/LLM."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api.config import ROOT, Settings
from api.services.artifacts import CASE_MAP
from api.services.storage import Store
from api.services.workflows import execute_run


class WorkflowCompositionTests(unittest.TestCase):
    def test_single_generation_preserves_case_and_uses_existing_evaluate(self):
        case = CASE_MAP["top_products"]
        conn = Mock()
        driver = SimpleNamespace(connect=Mock(return_value=conn))
        evaluate = Mock(
            return_value={
                "case": case.name,
                "candidate": "dashboard",
                "verdict": "ACCEPTED",
                "param_sets": 8,
                "failing_param_sets": 0,
                "detail": "",
                "orig_median_ms": 100,
                "cand_median_ms": 20,
                "speedup": 5,
                "reps": 7,
            }
        )
        response = {
            "text": f"```sql\n{case.original}\n```",
            "input_tokens": 111,
            "output_tokens": 22,
            "seconds": 0.1,
        }
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                root=ROOT,
                data_dir=Path(directory),
                enable_sql=True,
                test_database_confirmed=True,
            )
            store = Store(settings.database_path)
            job = store.create_job(
                "run",
                {
                    "mode": "live",
                    "query_id": case.name,
                    "condition": "C2_schema",
                    "confirm_sql": True,
                },
            )
            with (
                patch.dict(
                    sys.modules,
                    {
                        "psycopg": driver,
                        "scripts.run_validation": SimpleNamespace(evaluate=evaluate),
                    },
                ),
                patch.dict(
                    os.environ,
                    {
                        "SUE_DATABASE_URL": "postgresql://unit-test",
                        "SUE_MODEL": "unit-provider",
                    },
                ),
                patch("cases.cases.make_ctx", return_value={}),
                patch(
                    "llm.context.build_context",
                    return_value={
                        "query": case.original,
                        "schema": "CHECK (name <> 'private-value')",
                    },
                ) as context,
                patch(
                    "api.services.workflows.call_llm", return_value=response
                ) as generation,
            ):
                result = execute_run(job, settings, store)
            generation.assert_called_once()
            self.assertNotIn("private-value", generation.call_args.args[0])
            self.assertIs(context.call_args.args[1], case)
            self.assertIs(evaluate.call_args.args[1], case)
            self.assertEqual(
                evaluate.call_args.args[2].sql.strip(), case.original.strip()
            )
            self.assertIn(
                "default_transaction_read_only=on",
                driver.connect.call_args.kwargs["options"],
            )
            conn.close.assert_called_once()
            self.assertEqual(result["model_requests"], 1)
            self.assertTrue(result["selection"]["selected"][0]["is_synthetic"])
            self.assertEqual(result["attempts"][0]["benchmark"]["origin"], "measured")
            evaluate.reset_mock()
            unsafe = {**response, "text": "```sql\nSELECT pg_sleep(100)\n```"}
            with (
                patch.dict(
                    sys.modules,
                    {
                        "psycopg": driver,
                        "scripts.run_validation": SimpleNamespace(evaluate=evaluate),
                    },
                ),
                patch.dict(
                    os.environ,
                    {
                        "SUE_DATABASE_URL": "postgresql://unit-test",
                        "SUE_MODEL": "unit-provider",
                    },
                ),
                patch("cases.cases.make_ctx", return_value={}),
                patch(
                    "llm.context.build_context", return_value={"query": case.original}
                ),
                patch("api.services.workflows.call_llm", return_value=unsafe),
            ):
                rejected = execute_run(job, settings, store)
            evaluate.assert_not_called()
            self.assertEqual(rejected["attempts"][0]["outcome"], "safety_rejected")


if __name__ == "__main__":
    unittest.main()
