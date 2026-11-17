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
        with patch("validator.timing.run_query") as fetch:
            fetch.side_effect = [
                SimpleNamespace(ms=ms) for ms in (20, 7, 3, 5, 20, 7, 3, 5)
            ]
            row = measure(Mock(), "orig", "cand", {}, 4)
        self.assertEqual(
            [call.args[1] for call in fetch.call_args_list],
            ["orig", "cand", "cand", "orig"] * 2,
        )
        self.assertGreater(row["speedup"], 1.2)
        self.assertFalse(row["faster"])
