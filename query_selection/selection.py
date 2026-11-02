"""Pure query eligibility and impact ranking. This is NOT SQL safety validation."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from query_selection.models import (
    QueryDecision, QueryTelemetry, SelectionResult, SelectionStatus, finite_number,
)
from query_selection.policy import SelectionPolicy


def _identifier(identifier: exp.Expression | None) -> str:
    if not isinstance(identifier, exp.Identifier):
        return ""
    return identifier.name if identifier.args.get("quoted") else identifier.name.lower()


def _sql_reasons(record: QueryTelemetry, policy: SelectionPolicy) -> tuple[str, ...]:
    if not isinstance(record.sql, str) or not record.sql.strip():
        return ("MISSING_SQL",)
    if record.dialect != "postgres":
        return ("UNSUPPORTED_DIALECT",)
    try:
        statements = [tree for tree in sqlglot.parse(record.sql, read=record.dialect) if tree is not None]
    except sqlglot.errors.SqlglotError:
        return ("INVALID_SQL",)
    if not statements:
        return ("MISSING_SQL",)
    if len(statements) != 1:
        return ("MULTIPLE_STATEMENTS",)
    tree = statements[0]
    while isinstance(tree, exp.Subquery):
        tree = tree.this
    # SELECT-based set operations are supported; write CTEs/SELECT INTO are not.
    # Function permissions, resource use and generated SQL safety remain outside
    # this module, even when the outer statement is a SELECT.
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return ("UNSUPPORTED_STATEMENT",)
    if tree.find(exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                 exp.Alter, exp.Command, exp.TruncateTable, exp.Into):
        return ("UNSUPPORTED_STATEMENT",)
    # Scope resolution avoids mistaking a CTE alias for a physical table.
    for scope in traverse_scope(tree):
        for table in scope.sources.values():
            if not isinstance(table, exp.Table):
                continue
            name = _identifier(table.this)
            schema = _identifier(table.args.get("db"))
            qualified = f"{schema}.{name}" if schema else name
            if schema in policy.excluded_schemas:
                return ("EXCLUDED_SCHEMA",)
            if name in policy.excluded_tables or qualified in policy.excluded_tables:
                return ("EXCLUDED_TABLE",)
    return ()


def _assess(record: QueryTelemetry, policy: SelectionPolicy) -> QueryDecision:
    def decision(status: SelectionStatus, *reasons: str) -> QueryDecision:
        return QueryDecision(record, status, tuple(reasons))

    if not isinstance(record.query_id, str) or not record.query_id.strip():
        return decision(SelectionStatus.EXCLUDED, "MISSING_QUERY_ID")
    if record.query_id in policy.excluded_query_ids:
        return decision(SelectionStatus.EXCLUDED, "EXCLUDED_QUERY_ID")
    sql_reasons = _sql_reasons(record, policy)
    if sql_reasons:
        return decision(SelectionStatus.EXCLUDED, *sql_reasons)

    invalid = []
    if record.calls is not None and (type(record.calls) is not int or record.calls < 0 or not finite_number(record.calls)):
        invalid.append("INVALID_CALLS")
    for name in ("mean_execution_time_ms", "total_execution_time_ms"):
        value = getattr(record, name)
        if value is not None and (not finite_number(value) or value < 0):
            invalid.append(f"INVALID_{name.upper()}")
    if invalid:
        return decision(SelectionStatus.EXCLUDED, *invalid)
    if record.calls == 0:
        return decision(SelectionStatus.EXCLUDED, "NO_EXECUTIONS")

    missing = []
    if record.calls is None:
        missing.append("MISSING_CALLS")
    if record.mean_execution_time_ms is None:
        missing.append("MISSING_MEAN_EXECUTION_TIME_MS")
    if record.total_execution_time_ms is not None:
        return QueryDecision(record, SelectionStatus.ELIGIBLE,
                             ("PROVIDED_TOTAL", *missing),
                             float(record.total_execution_time_ms), "provided_total")
    if missing:
        return decision(SelectionStatus.DEFERRED, "MISSING_TOTAL_EXECUTION_TIME_MS", *missing)
    if not isinstance(record.window_id, str) or not record.window_id.strip():
        return decision(SelectionStatus.DEFERRED, "MISSING_MEASUREMENT_WINDOW")
    assert record.calls is not None and record.mean_execution_time_ms is not None
    try:
        impact = record.calls * record.mean_execution_time_ms
    except OverflowError:
        impact = float("inf")
    if not finite_number(impact):
        return decision(SelectionStatus.EXCLUDED, "INVALID_DERIVED_TOTAL")
    return QueryDecision(record, SelectionStatus.ELIGIBLE, ("DERIVED_TOTAL",),
                         float(impact), "calls_times_mean")


def filter_queries(records: Iterable[QueryTelemetry], policy: SelectionPolicy) -> tuple[QueryDecision, ...]:
    """Assess each aggregate without I/O or metric aggregation.

    For repeated IDs with identical SQL, the first record is retained and later
    ones excluded (never summed). Conflicting SQL under one ID excludes all of
    those records rather than silently selecting a different query.
    """
    records = tuple(records)
    sql_by_id: dict[str, set[str | None]] = {}
    for record in records:
        if isinstance(record.query_id, str) and record.query_id.strip():
            sql = record.sql.strip() if isinstance(record.sql, str) else None
            sql_by_id.setdefault(record.query_id, set()).add(sql)
    seen: set[str] = set()
    decisions = []
    for record in records:
        if isinstance(record.query_id, str) and record.query_id.strip():
            if len(sql_by_id[record.query_id]) > 1:
                decisions.append(QueryDecision(record, SelectionStatus.EXCLUDED, ("CONFLICTING_QUERY_ID",)))
                continue
            if record.query_id in seen:
                decisions.append(QueryDecision(record, SelectionStatus.EXCLUDED, ("DUPLICATE_QUERY_ID",)))
                continue
            seen.add(record.query_id)
        decisions.append(_assess(record, policy))
    return tuple(decisions)


def prioritize_queries(decisions: Iterable[QueryDecision], policy: SelectionPolicy) -> SelectionResult:
    """Rank eligible decisions by total, mean, calls, then stable ID.

    Missing secondary metrics sort after known non-negative metrics. top_k only
    limits selection: eligible records outside the budget retain their rank.
    """
    decisions = tuple(decisions)
    eligible = sorted(
        (i for i, d in enumerate(decisions) if d.status == SelectionStatus.ELIGIBLE),
        key=lambda i: (
            -decisions[i].impact_ms,
            -(decisions[i].telemetry.mean_execution_time_ms if decisions[i].telemetry.mean_execution_time_ms is not None else -1),
            -(decisions[i].telemetry.calls if decisions[i].telemetry.calls is not None else -1),
            decisions[i].telemetry.query_id,
        ),
    )
    ranked = list(decisions)
    for rank, index in enumerate(eligible, 1):
        chosen = policy.top_k is None or rank <= policy.top_k
        reasons = tuple(reason for reason in decisions[index].reason_codes if reason != "OUTSIDE_TOP_K")
        if not chosen:
            reasons += ("OUTSIDE_TOP_K",)
        ranked[index] = replace(decisions[index], rank=rank, selected=chosen, reason_codes=reasons)
    return SelectionResult(tuple(ranked[i] for i in eligible if ranked[i].selected), tuple(ranked), policy)


def select_queries(records: Iterable[QueryTelemetry], policy: SelectionPolicy | None = None) -> SelectionResult:
    """Compose independent eligibility and ranking stages for one input batch."""
    policy = policy if policy is not None else SelectionPolicy()
    return prioritize_queries(filter_queries(records, policy), policy)
