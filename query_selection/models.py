"""Source-independent contracts. SQL and provenance are never rewritten."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from query_selection.policy import SelectionPolicy


def finite_number(value: object) -> bool:
    """Accept finite Python numeric metrics, excluding booleans and strings."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class QueryTelemetry:
    """One already-aggregated query pattern, not a cumulative snapshot delta.

    All supplied metrics describe the same measurement window. A non-empty
    window_id is required to derive a missing total from calls and mean time.
    IDs must be unique within the source/database scope supplied by the adapter.
    Missing metrics are None, never an implicit zero.
    """

    query_id: str
    sql: str | None
    calls: int | None
    mean_execution_time_ms: float | None
    total_execution_time_ms: float | None
    source: str
    is_synthetic: bool
    window_id: str | None = None
    dialect: str = "postgres"

    def to_dict(self) -> dict:
        # Invalid metrics must still be reportable as strict JSON (no NaN/Inf).
        # Their specific invalidity is recorded in decision reason_codes.
        return {
            "query_id": self.query_id,
            "sql": self.sql,
            "calls": self.calls if finite_number(self.calls) else None,
            "mean_execution_time_ms": self.mean_execution_time_ms if finite_number(self.mean_execution_time_ms) else None,
            "total_execution_time_ms": self.total_execution_time_ms if finite_number(self.total_execution_time_ms) else None,
            "source": self.source,
            "is_synthetic": self.is_synthetic,
            "window_id": self.window_id,
            "dialect": self.dialect,
        }


class SelectionStatus(str, Enum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class QueryDecision:
    telemetry: QueryTelemetry
    status: SelectionStatus
    reason_codes: tuple[str, ...]
    impact_ms: float | None = None
    impact_source: str | None = None
    rank: int | None = None
    selected: bool = False

    def to_dict(self) -> dict:
        return {
            **self.telemetry.to_dict(),
            "status": self.status.value,
            "selected": self.selected,
            "reason_codes": list(self.reason_codes),
            "impact_ms": self.impact_ms,
            "impact_source": self.impact_source,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class SelectionResult:
    """Selected queries in rank order; all input decisions remain auditable."""

    selected: tuple[QueryDecision, ...]
    decisions: tuple[QueryDecision, ...]
    policy: SelectionPolicy

    def to_dict(self) -> dict:
        return {
            "policy": self.policy.to_dict(),
            "selected": [decision.to_dict() for decision in self.selected],
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
