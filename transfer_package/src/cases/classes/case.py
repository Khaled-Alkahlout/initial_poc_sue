from __future__ import annotations

from dataclasses import dataclass, field

from cases.classes.candidate import Candidate


@dataclass
class Case:
    """
    One original query with its parameter sets and the candidate rewrites to validate against it.

    Attributes
    ----------
    name : str
        Identifier of the case, equal to the file name of the original query.
    original : str
        SQL text of the original query.
    order_cols : list of str or None
        Result columns that define the ORDER BY sequence; None if the original has no ORDER BY.
    params : callable
        Function ``(ctx) -> list[(label, dict)]`` that returns the labelled parameter sets used for the
        equivalence check.
    timing_params : callable
        Function ``(ctx) -> dict`` that returns the single parameter set used for the timing measurement.
    candidates : list of Candidate
        Candidate rewrites for this case.
    """

    name: str
    original: str
    order_cols: list[str] | None
    params: callable  # (ctx) -> list[(label, dict)]
    timing_params: callable  # (ctx) -> dict
    candidates: list[Candidate] = field(default_factory=list)