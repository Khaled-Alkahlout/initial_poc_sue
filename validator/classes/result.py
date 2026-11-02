from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Result:
    """
    Output of a single query execution.

    Attributes
    ----------
    columns : list of str
        Column names in the order returned by the query.
    rows : list of tuple
        All returned rows, one tuple of Python values per row.
    ms : float
        Wall-clock duration of the execution in milliseconds, including fetching the rows.
    """

    columns: list[str]
    rows: list[tuple]
    ms: float
