"""Regressions for the transferred comparison and benchmark rules."""

import sys
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cases.classes.candidate import Candidate
from cases.cases import make_ctx
from validator.checker import (
    ResultLimitExceeded,
    SqlRejected,
    check_rewrite,
    compare,
    inspect_sql,
)
from validator.classes.result import Result
from validator.evaluation import evaluate
from validator.timing import measure


class DatabaseError(Exception):
    pass


class ParameterProfileTests(unittest.TestCase):
    def test_live_profile_uses_recent_orders_and_their_actual_time_window(self):
        connection = Mock()
        first = datetime(2026, 1, 1)
        last = datetime(2026, 1, 2)
        connection.execute.return_value.fetchall.return_value = [
            ("big", first, last),
            ("small", last, last),
        ]

        profile = make_ctx(connection, recent_order_limit=512)

        statement, parameters = connection.execute.call_args.args
        self.assertIn("ORDER BY created_at DESC LIMIT %s", statement)
        self.assertEqual(parameters, (512,))
        windows = profile["windows"]["big"]
        self.assertEqual(windows["full"], (first, last + timedelta(microseconds=1)))
        self.assertEqual(windows["boundary"], (first, last))
        self.assertGreater(windows["recent"][0], first)


class AdmissionTests(unittest.TestCase):
    def test_query_and_bindings_have_one_consistent_contract(self):
        original = inspect_sql(
            "SELECT id FROM orders WHERE tenant_id = %(Tenant)s ORDER BY id; -- safe"
        )
        self.assertEqual(original.parameters, {"Tenant"})
        candidate = check_rewrite(
            original,
            """
            WITH picked AS (SELECT id FROM public.orders WHERE tenant_id = %(Tenant)s)
            SELECT id FROM picked ORDER BY id
        """,
        )
        self.assertEqual(candidate.tables, {"orders"})
        for candidate in (
            "SELECT 1; SELECT 2",
            "SELECT id INTO copy FROM orders",
            "SELECT id FROM orders FOR UPDATE",
            "SELECT pg_sleep(1)",
            "SELECT id FROM pg_catalog.pg_roles",
            "SELECT id FROM private.orders",
            "SELECT id FROM orders WHERE id OPERATOR(public.=) 1",
            "WITH rows AS (DELETE FROM orders RETURNING id) SELECT id FROM rows",
            "SELECT id FROM orders WHERE id::public.unsafe = 1",
            "SELECT id FROM orders WHERE id = %(Tenant)s -- bind %(Tenant)s",
            "SELECT '%(Tenant)s'",
            "SELECT id FROM orders ORDER BY id",
            "SELECT id FROM customers WHERE tenant_id = %(Tenant)s ORDER BY id",
            "SELECT id FROM orders WHERE tenant_id = %(Tenant)s",
        ):
            with self.subTest(sql=candidate), self.assertRaises(SqlRejected):
                check_rewrite(original, candidate)

    def test_type_duplicate_count_and_limit_ties(self):
        source = Result(["id", "score"], [(1, 5), (2, 5)], 0, [23, 23])
        for candidate, status in (
            (Result(source.columns, [(2, 5)], 0, source.types), "ROWCOUNT_MISMATCH"),
            (
                Result(source.columns, [(1, 5), (1, 5)], 0, source.types),
                "VALUE_MISMATCH",
            ),
            (Result(source.columns, [(1, 5), (2, 5)], 0, [20, 23]), "COLUMN_MISMATCH"),
            (
                Result(source.columns, [("num:1", 5), (2, 5)], 0, source.types),
                "VALUE_MISMATCH",
            ),
            (Result(source.columns, [(2, 5), (1, 5)], 0, source.types), "EQUIVALENT"),
        ):
            with self.subTest(status=status):
                self.assertEqual(compare(source, candidate, ["score"]).status, status)
        identical = Result(source.columns, source.rows, 0, source.types)
        self.assertEqual(
            compare(source, identical, ["absent"]).status, "ORDER_UNVERIFIABLE"
        )


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.dict(sys.modules, {"psycopg": SimpleNamespace(Error=DatabaseError)})
        )
        self.enterContext(
            patch("validator.evaluation.read_snapshot", return_value=nullcontext())
        )
        self.enterContext(patch("validator.evaluation.require_tables"))
        self.read = self.enterContext(patch("validator.evaluation.run_query"))
        self.time = self.enterContext(patch("validator.evaluation.measure"))
        self.case = SimpleNamespace(
            name="sample",
            original="SELECT %(n)s::int AS n",
            order_cols=None,
            params=lambda ctx: [("small", {"n": 1})],
            timing_params=lambda ctx: {"n": 2},
        )
        self.candidate = Candidate(
            "rewrite", "SELECT %(n)s::int + 0 AS n", "unknown", "llm"
        )

    def test_benchmark_binding_must_pass_correctness(self):
        self.read.side_effect = [
            Result(["n"], [(1,)], 1, [23]),
            Result(["n"], [(1,)], 1, [23]),
            Result(["n"], [(2,)], 1, [23]),
            Result(["n"], [(4,)], 1, [23]),
        ]
        row = evaluate(Mock(), self.case, self.candidate, {})
        self.assertEqual(row["verdict"], "REJECTED_NOT_EQUIVALENT")
        self.assertEqual(row["parameter_checks"][-1]["label"], "benchmark")
        self.time.assert_not_called()

    def test_correctness_and_benchmark_are_capped_at_three_and_keep_timing_binding(
        self,
    ):
        self.case.params = lambda ctx: [(str(n), {"n": n}) for n in range(1, 9)]
        self.case.timing_params = lambda ctx: {"n": 8}
        self.read.return_value = Result(["n"], [(1,)], 5, [23])
        self.time.return_value = {"faster": True, "speedup": 2}
        row = evaluate(Mock(), self.case, self.candidate, {}, reps=8)
        self.assertEqual(row["param_sets"], 3)
        self.assertEqual(
            [check["label"] for check in row["parameter_checks"]], ["1", "2", "8"]
        )
        self.assertEqual(self.read.call_count, 6)
        self.assertEqual(self.time.call_args.args[4], 3)
        self.assertEqual(self.read.call_args.args[2], {"n": 8})
        self.assertEqual(row["parameter_checks"][0]["original_ms"], 5)
        self.assertEqual(row["parameter_checks"][0]["proposed_ms"], 5)
        self.assertGreaterEqual(row["parameter_checks"][0]["duration_ms"], 0)

    def test_failed_candidate_preserves_original_time_and_rows(self):
        self.read.side_effect = [
            Result(["n"], [(1,)], 14, [23]),
            DatabaseError("private"),
        ]
        row = evaluate(Mock(), self.case, self.candidate, {})
        check = row["parameter_checks"][0]
        self.assertEqual(check["status"], "EXEC_ERROR")
        self.assertEqual(check["original_ms"], 14)
        self.assertEqual(check["original_rows"], 1)
        self.assertGreaterEqual(check["proposed_ms"], 0)
        self.assertGreaterEqual(check["duration_ms"], 0)

    def test_missing_or_over_limit_evidence_never_passes(self):
        self.case.params = lambda ctx: []
        row = evaluate(Mock(), self.case, self.candidate, {})
        self.assertEqual(row["correctness_status"], "inconclusive")
        self.read.assert_not_called()
        self.case.params = lambda ctx: [("small", {"n": 1})]
        self.read.side_effect = ResultLimitExceeded("Rijlimiet overschreden.")
        row = evaluate(Mock(), self.case, self.candidate, {})
        self.assertEqual(row["correctness_status"], "inconclusive")
        self.assertEqual(row["parameter_checks"][0]["status"], "ROW_LIMIT")
        self.time.assert_not_called()

    def test_comparison_timeout_identifies_the_query_and_parameter_set(self):
        connection = Mock()
        timeout = DatabaseError("driver diagnostic with private data")
        timeout.sqlstate = "57014"
        timeout.diag = SimpleNamespace(
            message_primary="canceling statement due to statement timeout"
        )
        self.read.side_effect = timeout

        row = evaluate(
            connection, self.case, self.candidate, {}, correctness_timeout_ms=600_000
        )

        connection.execute.assert_called_once_with(
            "SET LOCAL statement_timeout = 600000"
        )
        self.assertEqual(row["verdict"], "VALIDATION_INCONCLUSIVE")
        self.assertEqual(row["parameter_checks"][0]["status"], "STATEMENT_TIMEOUT")
        self.assertIn("oorspronkelijke query", row["detail"])
        self.assertIn("bij small", row["detail"])
        self.assertIn("600 s", row["detail"])
        self.assertNotIn("private data", str(row))
        self.time.assert_not_called()

    def test_equivalent_queries_under_two_seconds_reach_benchmark(self):
        self.read.return_value = Result(["n"], [(1,)], 1_500, [23])
        self.time.return_value = {"faster": False, "speedup": 1}

        row = evaluate(Mock(), self.case, self.candidate, {})

        self.assertEqual(row["correctness_status"], "passed")
        self.assertEqual(row["benchmark_status"], "warning")
        self.time.assert_called_once()

    def test_equivalent_queries_at_the_benchmark_limit_skip_benchmark(self):
        self.read.return_value = Result(["n"], [(1,)], 2_000, [23])

        row = evaluate(
            Mock(), self.case, self.candidate, {}, correctness_timeout_ms=30_000
        )

        self.assertEqual(row["correctness_status"], "passed")
        self.assertEqual(row["benchmark_status"], "skipped")
        self.assertEqual(row["param_sets"], 2)
        self.time.assert_not_called()

    def test_long_benchmark_timeout_admits_and_measures_slow_equivalent_queries(self):
        connection = Mock()
        self.read.return_value = Result(["n"], [(1,)], 120_000, [23])
        self.time.side_effect = measure
        with patch("validator.timing.run_query", return_value=self.read.return_value):
            row = evaluate(
                connection, self.case, self.candidate, {}, benchmark_timeout_ms=600_000
            )

        self.assertEqual(row["correctness_status"], "passed")
        self.assertEqual(row["orig_median_ms"], 120_000)
        self.assertEqual(row["reps"], 3)
        self.assertEqual(len(row["benchmark_measurements"]), 3)
        connection.execute.assert_called_once_with(
            "SET LOCAL statement_timeout = 600000"
        )

    def test_benchmark_error_preserves_correctness_without_approval(self):
        self.read.return_value = Result(["n"], [(1,)], 1, [23])
        self.time.side_effect = DatabaseError("secret connection detail")
        row = evaluate(Mock(), self.case, self.candidate, {})
        self.assertEqual(row["verdict"], "BENCHMARK_ERROR")
        self.assertEqual(row["correctness_status"], "passed")
        self.assertEqual(row["benchmark_status"], "error")
        self.assertNotIn("secret", str(row))

    def test_identical_sql_cannot_be_accepted_even_when_measurements_favor_it(self):
        self.read.return_value = Result(["n"], [(1,)], 1, [23])
        self.time.return_value = {"faster": True, "speedup": 5}
        candidate = Candidate(
            "echo", self.case.original + "\n-- changed formatting", "unknown", "llm"
        )
        row = evaluate(Mock(), self.case, candidate, {})
        self.assertEqual(row["verdict"], "EQUIVALENT_NOT_FASTER")

    def test_measurement_starts_with_each_query_and_rejects_overlapping_timings(self):
        connection = Mock()
        with patch("validator.timing.run_query") as fetch:
            fetch.side_effect = [
                SimpleNamespace(ms=ms) for ms in (20, 7, 3, 5, 20, 7, 3, 5)
            ]
            row = measure(connection, "orig", "cand", {}, 4)
        connection.execute.assert_called_once_with("SET LOCAL statement_timeout = 2000")
        self.assertEqual(
            [call.args[1] for call in fetch.call_args_list],
            ["orig", "cand", "cand", "orig"] * 2,
        )
        self.assertGreater(row["speedup"], 1.2)
        self.assertFalse(row["faster"])

    def test_three_stable_benchmark_pairs_can_pass_and_record_individual_times(self):
        with patch(
            "validator.timing.run_query",
            side_effect=[SimpleNamespace(ms=ms) for ms in (20, 7, 7, 20, 20, 7)],
        ):
            row = measure(Mock(), "orig", "cand", {}, 3)
        self.assertTrue(row["faster"])
        self.assertEqual(
            [entry["first_query"] for entry in row["benchmark_measurements"]],
            ["original", "proposed", "original"],
        )
        self.assertEqual(
            [entry["original_ms"] for entry in row["benchmark_measurements"]],
            [20, 20, 20],
        )
        self.assertEqual(
            [entry["proposed_ms"] for entry in row["benchmark_measurements"]], [7, 7, 7]
        )

    def test_failed_benchmark_retains_completed_and_interrupted_pairs(self):
        measurements = []
        with patch(
            "validator.timing.run_query",
            side_effect=[
                SimpleNamespace(ms=20),
                SimpleNamespace(ms=7),
                DatabaseError("private"),
            ],
        ):
            with self.assertRaises(DatabaseError):
                measure(Mock(), "orig", "cand", {}, 3, measurements=measurements)
        self.assertEqual(
            [entry["status"] for entry in measurements], ["passed", "error"]
        )
        self.assertIsNone(measurements[1]["original_ms"])
        self.assertGreaterEqual(measurements[1]["proposed_ms"], 0)
