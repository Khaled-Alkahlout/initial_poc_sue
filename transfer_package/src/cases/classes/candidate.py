from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    """
    A candidate rewrite of an original query, together with the expected verdict.

    Attributes
    ----------
    name : str
        Short identifier, e.g. "M1_count_zonder_distinct".
    sql : str
        The candidate SELECT statement, with %(name)s placeholders for the parameters.
    expected : str
        Ground truth according to the author: "equivalent" or "not_equivalent".
    fault : str, default ""
        Fault type (taxonomy) used in the analysis; "-" or empty for equivalent candidates.
    """

    name: str
    sql: str
    expected: str  # 'equivalent' | 'not_equivalent'
    fault: str = ""  # type fout (taxonomie) voor de analyse