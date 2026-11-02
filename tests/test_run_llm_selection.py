"""CLI routing and orchestration tests with services replaced at their boundaries."""
import builtins
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cases.cases import CASES
from scripts import run_llm


class SelectionCliTests(unittest.TestCase):
    def offline(self, args):
        real_import = builtins.__import__

        def guarded_import(name, *rest, **kwargs):
            if name in {"psycopg", "anthropic", "scripts.run_validation"} or name.startswith("validator"):
                raise AssertionError(f"Offline path imported service dependency: {name}")
            return real_import(name, *rest, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch.object(run_llm, "ROOT", Path(directory)), \
                    patch("builtins.__import__", side_effect=guarded_import), \
                    patch.object(run_llm, "build_context") as context, \
                    patch.object(run_llm, "call_llm") as model, \
                    patch.object(run_llm, "make_ctx") as parameters, \
                    contextlib.redirect_stdout(output):
                run_llm.main(args)
            context.assert_not_called()
            model.assert_not_called()
            parameters.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
            return output.getvalue()

    def test_selection_only_is_offline_without_uri_and_deterministic(self):
        first = self.offline(["--selection-only", "--top-k", "1"])
        self.assertEqual(first, self.offline(["--selection-only", "--top-k", "1"]))
        payload = json.loads(first)
        self.assertEqual(payload["selected"][0]["query_id"], "top_products")
        self.assertEqual(payload["selected"][0]["impact_ms"], 500_000)

    def test_selection_flags_limit_input_and_apply_exclusions(self):
        payload = json.loads(self.offline(["--selection-only", "--cases", "top_products", "top_customers",
                                          "--exclude-query", "top_products"]))
        self.assertEqual([d["query_id"] for d in payload["selected"]], ["top_customers"])
        self.assertIn("EXCLUDED_QUERY_ID", payload["decisions"][0]["reason_codes"])

    def test_empty_selection_does_not_connect_even_with_uri(self):
        payload = json.loads(self.offline(["unused-uri", "--select-mock", "--top-k", "0"]))
        self.assertEqual(payload["selected"], [])

    def test_invalid_cli_is_rejected_before_runtime_dependencies(self):
        for args in ([], ["--selection-only", "--top-k", "-1"],
                     ["--selection-only", "--cases", "typo"], ["unused-uri", "--top-k", "1"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                run_llm.main(args)
            self.assertEqual(exc.exception.code, 2)


class PipelineRoutingTests(unittest.TestCase):
    def run_pipeline(self, extra_args):
        connection = Mock()
        driver = SimpleNamespace(connect=Mock(return_value=connection))
        evaluate = Mock(side_effect=lambda conn, case, cand, ctx, reps: {
            "case": case.name, "candidate": cand.name, "verdict": "EQUIVALENT_NOT_FASTER",
            "orig_median_ms": 123.0,
        })
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(sys.modules, {"psycopg": driver, "scripts.run_validation": SimpleNamespace(evaluate=evaluate)}), \
                    patch.object(run_llm, "ROOT", Path(directory)), \
                    patch.object(run_llm, "make_ctx", return_value={}), \
                    patch.object(run_llm, "build_context", side_effect=lambda conn, case, ctx, cond: {"query": case.original}) as context, \
                    patch.object(run_llm, "call_llm", wraps=run_llm.call_llm) as model, \
                    contextlib.redirect_stdout(io.StringIO()):
                run_llm.main(["fake-uri", "--model", "mock", "--conditions", "C1_query", "--reps", "1", *extra_args])
            folders = list((Path(directory) / "results").glob("llm-*"))
            self.assertEqual(len(folders), 1)
            folder = folders[0]
            rows = json.loads((folder / "llm-results.json").read_text()) if (folder / "llm-results.json").exists() else []
            selection = json.loads((folder / "selection.json").read_text()) if (folder / "selection.json").exists() else None
            driver.connect.assert_called_once_with("fake-uri", autocommit=True)
            return context.call_args_list, evaluate.call_args_list, model.call_count, rows, selection

    def test_selected_cases_reach_existing_context_and_validator_in_rank_order(self):
        contexts, evaluations, calls, rows, selection = self.run_pipeline(["--select-mock", "--top-k", "2"])
        expected = [CASES[0], CASES[3]]
        self.assertEqual([call.args[1] for call in contexts], expected)
        self.assertEqual([call.args[1] for call in evaluations], expected)
        for call, case in zip(contexts, expected):
            self.assertIs(call.args[1], case)
        self.assertEqual(calls, 2)
        self.assertEqual([row["selection_rank"] for row in rows], [1, 2])
        self.assertTrue(all(row["telemetry_is_synthetic"] for row in rows))
        self.assertEqual(rows[0]["workload_impact_ms"], 500_000)
        self.assertEqual(rows[0]["orig_median_ms"], 123.0)
        self.assertEqual(selection["selected"][0]["query_id"], "top_products")

    def test_legacy_workflow_preserves_case_order_without_selection_fields(self):
        contexts, evaluations, calls, rows, selection = self.run_pipeline([])
        self.assertEqual([call.args[1] for call in contexts], CASES)
        self.assertEqual(len(evaluations), 4)
        self.assertEqual(calls, 4)
        self.assertIsNone(selection)
        self.assertTrue(all("workload_impact_ms" not in row for row in rows))

    def test_dry_run_still_prepares_context_but_does_not_call_model(self):
        contexts, evaluations, calls, rows, selection = self.run_pipeline(["--select-mock", "--top-k", "1", "--dry-run"])
        self.assertEqual(len(contexts), 1)
        self.assertEqual(evaluations, [])
        self.assertEqual(calls, 0)
        self.assertEqual(rows, [])
        self.assertIsNotNone(selection)


if __name__ == "__main__":
    unittest.main()
