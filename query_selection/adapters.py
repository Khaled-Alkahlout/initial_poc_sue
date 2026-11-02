"""Case-specific boundary; the selection core does not import cases or services."""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from query_selection.models import QueryTelemetry, SelectionResult

if TYPE_CHECKING:
    from cases.classes.case import Case


# Deliberately fictional workload figures: NOT database or benchmark measurements.
# Every metric below belongs to the same simulated observation window.
MOCK_WORKLOAD: dict[str, tuple[int, float]] = {
    "top_products": (100_000, 5.0),
    "top_customers": (1, 2_000.0),
    "audit_log_page": (2_000, 1.5),
    "revenue_orders": (1_000, 10.0),
}
MOCK_SOURCE = "mock:case-workload-v1"
MOCK_WINDOW = "synthetic-window-v1"


def mock_telemetry(cases: Iterable[Case]) -> tuple[QueryTelemetry, ...]:
    """Adapt existing cases without calling parameter functions or a database.

    Unknown cases retain their SQL but have missing metrics, so selection defers
    them instead of inventing workload data.
    """
    records = []
    for case in cases:
        calls, mean = MOCK_WORKLOAD.get(case.name, (None, None))
        total = calls * mean if calls is not None and mean is not None else None
        records.append(QueryTelemetry(case.name, case.original, calls, mean, total,
                                      MOCK_SOURCE, True, MOCK_WINDOW))
    return tuple(records)


def selected_cases(result: SelectionResult, cases: Iterable[Case]) -> list[Case]:
    """Resolve selections to the original objects, preserving params and SQL.

    Fail explicitly on ambiguous, missing or changed cases. No SQL reconstruction
    or parameter inference is performed at this boundary.
    """
    by_id = {}
    for case in cases:
        if case.name in by_id:
            raise ValueError(f"Duplicate case name: {case.name}")
        by_id[case.name] = case
    selected = []
    for decision in result.selected:
        record = decision.telemetry
        case = by_id.get(record.query_id)
        if case is None:
            raise ValueError(f"Selected query has no Case: {record.query_id}")
        if record.sql != case.original:
            raise ValueError(f"Selected SQL differs from Case: {record.query_id}")
        selected.append(case)
    return selected
