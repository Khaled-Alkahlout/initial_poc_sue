"""Configuration for query selection; independent of telemetry sources."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectionPolicy:
    """Select all eligible queries by default, excluding explicit system schemas.

    Object exclusions use PostgreSQL identifier spelling: unquoted identifiers
    are lower-case; quoted identifiers retain their case. No latency threshold
    is applied, so frequent, fast queries remain eligible.
    """

    top_k: int | None = None
    excluded_query_ids: frozenset[str] = frozenset()
    excluded_schemas: frozenset[str] = frozenset({"pg_catalog", "information_schema"})
    excluded_tables: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.top_k is not None and (type(self.top_k) is not int or self.top_k < 0):
            raise ValueError("top_k must be a non-negative integer or None")
        for name in ("excluded_query_ids", "excluded_schemas", "excluded_tables"):
            values = getattr(self, name)
            if isinstance(values, str):
                raise ValueError(f"{name} must be a collection of names, not a string")
            values = frozenset(values)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, values)

    def to_dict(self) -> dict:
        return {
            "top_k": self.top_k,
            "excluded_query_ids": sorted(self.excluded_query_ids),
            "excluded_schemas": sorted(self.excluded_schemas),
            "excluded_tables": sorted(self.excluded_tables),
        }
