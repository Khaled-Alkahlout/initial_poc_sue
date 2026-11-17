"""Transfer checks for the current POC behavior, including known defects."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from cases.cases import CASES
from cases.classes.candidate import Candidate
from cases.classes.case import Case
from llm.context import tables_and_columns
from scripts import run_experiment, run_validation
from ui import pipeline
from validator import timing
from validator.checker import compare, run_query, static_check
from validator.classes.result import Result


class ValidatorTests(unittest.TestCase):
    def test_static_check_common_cases(self):
        checks = [
            ("SELECT %(marker)s", True, "ok"),
            ("SELECT 1 UNION SELECT 2", True, "ok"),
            ("SELECT 1; SELECT 2", False, "MULTIPLE_STATEMENTS"),
            ("UPDATE fixture SET id = 2", False, "NOT_SELECT"),
            ("WITH gone AS (DELETE FROM fixture RETURNING id) SELECT id FROM gone", False, "FORBIDDEN_NODE"),
            ("SELECT 1 INTERSECT SELECT 1", False, "NOT_SELECT"),
        ]
        for sql, allowed, reason in checks:
            with self.subTest(sql=sql):
                ok, message = static_check(sql)
                self.assertEqual(ok, allowed)
                self.assertTrue(message.startswith(reason), message)

    def test_static_check_gaps_without_executing_sql(self):
        for sql in ("SELECT id INTO new_table FROM fixture", "SELECT id FROM fixture FOR UPDATE",
                    "SELECT pg_advisory_lock(1)", "(VALUES (1))"):
            with self.subTest(sql=sql):
                self.assertEqual(static_check(sql), (True, "ok"))

    def test_query_execution_uses_readonly_and_rollback(self):
        conn = Mock()
        transaction = unittest.mock.MagicMock()
        conn.transaction.return_value = transaction
        cursor = Mock(description=[SimpleNamespace(name="value")])
        cursor.fetchall.return_value = [(None,)]
        conn.execute.return_value = cursor
        result = run_query(conn, "SELECT %(value)s", {"value": None}, timeout_ms=125)
        conn.transaction.assert_called_once_with(force_rollback=True)
        self.assertEqual(conn.execute.call_args_list,
                         [call("SET TRANSACTION READ ONLY"), call("SET LOCAL statement_timeout = 125"),
                          call("SELECT %(value)s", {"value": None})])
        transaction.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual((result.columns, result.rows), (["value"], [(None,)]))

    def test_compare_duplicates_null_order_and_columns(self):
        orig = Result(["n", "label"], [(1, None), (1, None), (2, "x")], 0)
        reordered = Result(orig.columns, [(2, "x"), (1, None), (Decimal("1.0"), None)], 0)
        self.assertEqual(compare(orig, reordered, None).status, "EQUIVALENT")
        self.assertEqual(compare(orig, reordered, ["n"]).status, "ORDER_MISMATCH")
        self.assertEqual(compare(orig, Result(orig.columns, orig.rows[1:], 0), None).status, "ROWCOUNT_MISMATCH")
        self.assertEqual(compare(orig, Result(orig.columns, [(1, "null"), *orig.rows[1:]], 0), None).status,
                         "VALUE_MISMATCH")
        self.assertEqual(compare(orig, Result(["label", "n"], orig.rows, 0), None).status, "COLUMN_MISMATCH")

    def test_compare_false_positives_for_boundary_and_types(self):
        orig = Result(["score", "label"], [(9, "a"), (8, "b"), (7, "c")], 0)
        fewer = Result(orig.columns, orig.rows[:-1], 0)
        out_of_order = Result(orig.columns, [(8, "b"), (9, "a"), (7, "d")], 0)
        self.assertEqual(compare(orig, fewer, ["score"]).status, "TIE_AMBIGUOUS")
        self.assertEqual(compare(orig, out_of_order, ["score"]).status, "TIE_AMBIGUOUS")
        self.assertEqual(compare(Result(["n"], [(1,)], 0), Result(["n"], [("num:1",)], 0), None).status,
                         "EQUIVALENT")
        with self.assertRaises(ValueError):
            compare(orig, fewer, ["missing"])

    def test_timing_sequence_and_threshold(self):
        for candidate_ms, faster in ((10, True), (10.01, False)):
            with self.subTest(candidate_ms=candidate_ms):
                def query(_, sql, params, timeout_ms):
                    return Result([], [], 12 if sql == "original" else candidate_ms)

                params = {"key": 1}
                with patch.object(timing, "run_query", side_effect=query) as run:
                    result = timing.measure(None, "original", "candidate", params, reps=3, warmup=2)
                original = call(None, "original", params, timeout_ms=120000)
                candidate = call(None, "candidate", params, timeout_ms=120000)
                self.assertEqual(run.call_args_list, [original] + [original, candidate] * 5)
                self.assertEqual(result["speedup"], 1.2)
                self.assertEqual(result["faster"], faster)

    def test_slow_baseline_reduces_reps(self):
        with patch.object(timing, "run_query", return_value=Result([], [], 5001)) as run:
            result = timing.measure(None, "original", "candidate", {}, reps=7)
        self.assertEqual(run.call_count, 7)
        self.assertEqual(result["reps"], 3)
        self.assertFalse(result["faster"])

    def test_empty_parameter_sets_can_pass_both_paths(self):
        case = Case("fixture", "SELECT id FROM fixture", None, lambda _: [], lambda _: {})
        candidate = Candidate("rewrite", "SELECT id + 0 AS id FROM fixture", "unknown")
        with patch.object(run_validation, "measure", return_value={"faster": True}):
            self.assertEqual(run_validation.evaluate(None, case, candidate, {}, 3)["verdict"], "ACCEPTED")
        with patch.object(pipeline, "measure", return_value={"faster": True}):
            self.assertEqual(pipeline.run_all(None, case, {}, candidate.sql, 3)["verdict"], "ACCEPTED")
        self.assertEqual(pipeline.decide(True, [{"status": "EXEC_ERROR"}], {"faster": True}),
                         "REJECTED_NOT_EQUIVALENT")
        self.assertEqual(pipeline.decide(True, [{"status": "EQUIVALENT"}], {"faster": False}),
                         "EQUIVALENT_NOT_FASTER")

    def test_batch_baseline_cache_ignores_connection_and_parameters(self):
        case = Case("fixture", "SELECT id FROM fixture", None, lambda ctx: [("same-label", ctx)], lambda _: {})
        candidate = Candidate("rewrite", "SELECT other_id AS id FROM fixture", "unknown")
        first, second = object(), object()

        def query(conn, sql, params, timeout_ms):
            return Result(["id"], [(2 if conn is second and sql == case.original else 1,)], 0)

        with patch.object(run_validation, "CACHE", {}), \
                patch.object(run_validation, "run_query", side_effect=query) as run, \
                patch.object(run_validation, "measure", return_value={"faster": True}):
            run_validation.evaluate(first, case, candidate, {"tenant": 1}, 3)
            result = run_validation.evaluate(second, case, candidate, {"tenant": 2}, 3)
            self.assertEqual(result["verdict"], "ACCEPTED")
            self.assertNotIn(call(second, case.original, {"tenant": 2}, timeout_ms=120000), run.call_args_list)

    def test_context_discards_schema_and_cte_alias(self):
        tables, columns = tables_and_columns(
            "WITH subset AS (SELECT id FROM other_schema.items) SELECT id FROM subset"
        )
        self.assertEqual(tables, ["items"])
        self.assertEqual(columns, {"id"})

    def test_existing_fixtures_and_aliases_load(self):
        self.assertEqual(len(CASES), 4)
        self.assertEqual(sum(len(case.candidates) for case in CASES), 22)
        for case in CASES:
            for candidate in case.candidates:
                self.assertNotEqual(candidate.sql.strip(), case.original.strip(), candidate.name)
        for provider in ("openrouter", "anthropic"):
            with self.subTest(provider=provider):
                model = pipeline.MODELS["Sonnet 5.5"][0 if provider == "openrouter" else 1]
                self.assertEqual(run_experiment.resolve(["sonnet"], provider), {"sonnet": model})
