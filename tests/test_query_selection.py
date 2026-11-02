"""Offline contract tests: no database, model provider or benchmark dependency."""
import json
import unittest
from dataclasses import replace

from cases.cases import CASES
from cases.classes.case import Case
from query_selection.adapters import mock_telemetry, selected_cases
from query_selection.models import QueryTelemetry, SelectionStatus
from query_selection.policy import SelectionPolicy
from query_selection.selection import filter_queries, prioritize_queries, select_queries


def record(query_id="q", **changes):
    base = QueryTelemetry(query_id, "SELECT 1", 10, 5.0, 50.0,
                          "unit-test", True, "same-window")
    return replace(base, **changes)


class EligibilityTests(unittest.TestCase):
    def decision(self, value, policy=None):
        result = select_queries([value], policy)
        self.assertEqual(len(result.decisions), 1)
        return result.decisions[0]

    def test_select_and_postgres_parameters_preserve_original_sql(self):
        sql = "-- keep this\nSELECT '--literal', %(tenant_id)s::uuid, 42"
        decision = self.decision(record(sql=sql))
        self.assertEqual(decision.status, SelectionStatus.ELIGIBLE)
        self.assertTrue(decision.selected)
        self.assertEqual(decision.telemetry.sql, sql)

    def test_select_cte_and_set_operations(self):
        for sql in ("WITH q AS (SELECT 1) SELECT * FROM q", "SELECT 1 UNION ALL SELECT 2",
                    "SELECT 1 INTERSECT SELECT 1", "(SELECT 1)"):
            with self.subTest(sql=sql):
                self.assertTrue(self.decision(record(sql=sql)).selected)

    def test_missing_sql_and_id(self):
        for sql in (None, "", "  ", "-- only a comment"):
            with self.subTest(sql=sql):
                self.assertIn("MISSING_SQL", self.decision(record(sql=sql)).reason_codes)
        self.assertIn("MISSING_QUERY_ID", self.decision(record(query_id="")).reason_codes)

    def test_invalid_sql(self):
        decision = self.decision(record(sql="SELECT * FROM"))
        self.assertEqual(decision.status, SelectionStatus.EXCLUDED)
        self.assertIn("INVALID_SQL", decision.reason_codes)

    def test_non_select_and_write_cte_are_excluded(self):
        for sql in ("DELETE FROM orders", "UPDATE orders SET id = 1", "CREATE TABLE x (id int)",
                    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
                    "SELECT * INTO copy FROM orders"):
            with self.subTest(sql=sql):
                self.assertIn("UNSUPPORTED_STATEMENT", self.decision(record(sql=sql)).reason_codes)

    def test_multiple_statements_are_excluded(self):
        self.assertIn("MULTIPLE_STATEMENTS", self.decision(record(sql="SELECT 1; SELECT 2")).reason_codes)

    def test_unsupported_dialect_is_explicit(self):
        self.assertIn("UNSUPPORTED_DIALECT", self.decision(record(dialect="unknown")).reason_codes)

    def test_configured_exclusions_and_default_system_schemas(self):
        policy = SelectionPolicy(excluded_query_ids=frozenset({"skip"}),
                                 excluded_tables=frozenset({"private.secrets", "orders"}))
        for value, reason in ((record("skip"), "EXCLUDED_QUERY_ID"),
                              (record(sql="SELECT * FROM private.secrets"), "EXCLUDED_TABLE"),
                              (record(sql="SELECT * FROM orders"), "EXCLUDED_TABLE"),
                              (record(sql="SELECT * FROM PG_CATALOG.pg_class"), "EXCLUDED_SCHEMA"),
                              (record(sql="SELECT * FROM information_schema.tables"), "EXCLUDED_SCHEMA")):
            with self.subTest(value=value):
                self.assertIn(reason, self.decision(value, policy).reason_codes)

    def test_cte_alias_is_not_a_physical_table_exclusion(self):
        policy = SelectionPolicy(excluded_tables=frozenset({"orders"}))
        self.assertTrue(self.decision(record(sql="WITH orders AS (SELECT 1) SELECT * FROM orders"), policy).selected)
        self.assertFalse(self.decision(record(sql="WITH q AS (SELECT * FROM orders) SELECT * FROM q"), policy).selected)

    def test_literals_are_not_removed_and_selection_is_not_safety(self):
        # A SELECT function can pass eligibility; execution permission is NOT granted here.
        for sql in ("SELECT 'DELETE FROM orders'", "SELECT pg_sleep(1)"):
            self.assertTrue(self.decision(record(sql=sql)).selected)

    def test_missing_metrics_defer_instead_of_becoming_zero(self):
        decision = self.decision(record(calls=None, mean_execution_time_ms=None, total_execution_time_ms=None))
        self.assertEqual(decision.status, SelectionStatus.DEFERRED)
        self.assertIsNone(decision.impact_ms)
        self.assertIn("MISSING_CALLS", decision.reason_codes)
        self.assertIn("MISSING_MEAN_EXECUTION_TIME_MS", decision.reason_codes)

    def test_valid_total_can_rank_without_secondary_metrics(self):
        decision = self.decision(record(calls=None, mean_execution_time_ms=None))
        self.assertTrue(decision.selected)
        self.assertEqual(decision.impact_ms, 50)
        self.assertIn("MISSING_CALLS", decision.reason_codes)

    def test_total_is_derived_only_with_explicit_shared_window(self):
        value = record(total_execution_time_ms=None)
        derived = self.decision(value)
        self.assertEqual(derived.impact_ms, 50)
        self.assertEqual(derived.impact_source, "calls_times_mean")
        self.assertIsNone(derived.telemetry.total_execution_time_ms)
        for window in (None, "", " "):
            with self.subTest(window=window):
                deferred = self.decision(replace(value, window_id=window))
                self.assertEqual(deferred.status, SelectionStatus.DEFERRED)
                self.assertIn("MISSING_MEASUREMENT_WINDOW", deferred.reason_codes)

    def test_invalid_metrics_are_excluded_and_strict_json_serializable(self):
        invalid = {"calls": [-1, 1.5, True, "10", float("nan")],
                   "mean_execution_time_ms": [-1.0, float("nan"), float("inf"), True, "5"],
                   "total_execution_time_ms": [-1, float("-inf"), True, "50"]}
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    result = select_queries([record(**{field: value})])
                    self.assertEqual(result.decisions[0].status, SelectionStatus.EXCLUDED)
                    self.assertIn(f"INVALID_{field.upper()}", result.decisions[0].reason_codes)
                    json.dumps(result.to_dict(), allow_nan=False)

    def test_zero_calls_and_zero_duration_are_different(self):
        self.assertIn("NO_EXECUTIONS", self.decision(record(calls=0, total_execution_time_ms=0)).reason_codes)
        self.assertTrue(self.decision(record(mean_execution_time_ms=0, total_execution_time_ms=0)).selected)

    def test_derived_total_overflow_is_excluded(self):
        decision = self.decision(record(calls=10**100, mean_execution_time_ms=1e300,
                                        total_execution_time_ms=None))
        self.assertIn("INVALID_DERIVED_TOTAL", decision.reason_codes)


class RankingTests(unittest.TestCase):
    def test_frequency_can_outweigh_individual_latency(self):
        fast = record("fast", calls=100_000, mean_execution_time_ms=5, total_execution_time_ms=None)
        slow = record("slow", calls=1, mean_execution_time_ms=2000, total_execution_time_ms=2000)
        result = select_queries([slow, fast])
        self.assertEqual([d.telemetry.query_id for d in result.selected], ["fast", "slow"])
        self.assertEqual([d.impact_ms for d in result.selected], [500_000, 2000])

    def test_provided_total_is_the_primary_metric(self):
        result = select_queries([record("high_mean", mean_execution_time_ms=100, total_execution_time_ms=10),
                                 record("high_total", mean_execution_time_ms=1, total_execution_time_ms=100)])
        self.assertEqual(result.selected[0].telemetry.query_id, "high_total")
        self.assertEqual(result.selected[0].impact_source, "provided_total")

    def test_secondary_sort_mean_then_calls_then_id(self):
        values = [record("z", mean_execution_time_ms=5, calls=10),
                  record("a", mean_execution_time_ms=5, calls=10),
                  record("more_calls", mean_execution_time_ms=5, calls=20),
                  record("higher_mean", mean_execution_time_ms=6, calls=1),
                  record("unknown_secondary", mean_execution_time_ms=None, calls=None)]
        expected = ["higher_mean", "more_calls", "a", "z", "unknown_secondary"]
        for inputs in (values, list(reversed(values))):
            self.assertEqual([d.telemetry.query_id for d in select_queries(inputs).selected], expected)

    def test_top_k_retains_eligible_but_unselected_decisions(self):
        result = select_queries([record("b"), record("a")], SelectionPolicy(top_k=1))
        self.assertEqual([d.telemetry.query_id for d in result.selected], ["a"])
        other = result.decisions[0]
        self.assertEqual(other.status, SelectionStatus.ELIGIBLE)
        self.assertEqual(other.rank, 2)
        self.assertFalse(other.selected)
        self.assertIn("OUTSIDE_TOP_K", other.reason_codes)

    def test_top_k_zero_and_empty_input(self):
        self.assertEqual(select_queries([record()], SelectionPolicy(top_k=0)).selected, ())
        self.assertEqual(select_queries([]).to_dict()["decisions"], [])

    def test_reranking_with_a_larger_budget_clears_old_budget_reason(self):
        limited = select_queries([record("b"), record("a")], SelectionPolicy(top_k=1))
        expanded = prioritize_queries(limited.decisions, SelectionPolicy(top_k=2))
        self.assertEqual(len(expanded.selected), 2)
        self.assertTrue(all("OUTSIDE_TOP_K" not in d.reason_codes for d in expanded.selected))

    def test_duplicates_do_not_add_workload_or_select_twice(self):
        values = [record(), record(total_execution_time_ms=999)]
        result = select_queries(values)
        self.assertEqual(len(result.selected), 1)
        self.assertEqual(result.selected[0].impact_ms, 50)
        self.assertIn("DUPLICATE_QUERY_ID", result.decisions[1].reason_codes)
        self.assertEqual(result.decisions[1].telemetry.total_execution_time_ms, 999)

    def test_conflicting_sql_under_same_id_is_never_silently_resolved(self):
        result = select_queries([record(), record(sql="SELECT 2")])
        self.assertFalse(result.selected)
        self.assertTrue(all("CONFLICTING_QUERY_ID" in d.reason_codes for d in result.decisions))

    def test_public_stages_compose_and_input_is_unchanged(self):
        values = [record("b"), record("a")]
        before = list(values)
        policy = SelectionPolicy(top_k=1)
        self.assertEqual(prioritize_queries(filter_queries(iter(values), policy), policy), select_queries(values, policy))
        self.assertEqual(values, before)
        self.assertEqual(select_queries(values, policy), select_queries(values, policy))

    def test_policy_rejects_invalid_budget(self):
        for budget in (-1, True, 1.5, "1"):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                SelectionPolicy(top_k=budget)
        with self.assertRaises(ValueError):
            SelectionPolicy(excluded_tables="orders")


class CaseAdapterTests(unittest.TestCase):
    def test_mock_provenance_serialization_and_case_identity(self):
        records = mock_telemetry(CASES)
        result = select_queries(records, SelectionPolicy(top_k=2))
        payload = json.loads(json.dumps(result.to_dict(), allow_nan=False))
        self.assertEqual([d["query_id"] for d in payload["selected"]], ["top_products", "revenue_orders"])
        self.assertTrue(all(d["is_synthetic"] for d in payload["decisions"]))
        self.assertTrue(all(d["source"].startswith("mock:") for d in payload["decisions"]))
        resolved = selected_cases(result, CASES)
        for case, decision in zip(resolved, result.selected):
            original = next(c for c in CASES if c.name == decision.telemetry.query_id)
            self.assertIs(case, original)
            self.assertIs(case.params, original.params)
            self.assertIs(case.timing_params, original.timing_params)
            self.assertEqual(case.original, decision.telemetry.sql)

    def test_adapter_never_calls_parameter_functions(self):
        def forbidden(_):
            raise AssertionError("Parameter/database work is forbidden during selection")
        case = Case("new_case", "SELECT 1", None, forbidden, forbidden)
        result = select_queries(mock_telemetry([case]))
        self.assertEqual(result.decisions[0].status, SelectionStatus.DEFERRED)

    def test_resolver_rejects_missing_ambiguous_or_changed_cases(self):
        result = select_queries(mock_telemetry(CASES), SelectionPolicy(top_k=1))
        with self.assertRaises(ValueError):
            selected_cases(result, [])
        with self.assertRaises(ValueError):
            selected_cases(result, [CASES[0], CASES[0]])
        changed = replace(CASES[0], original="SELECT 999")
        with self.assertRaises(ValueError):
            selected_cases(result, [changed])


if __name__ == "__main__":
    unittest.main()
