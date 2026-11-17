from __future__ import annotations

from dataclasses import dataclass

@dataclass
class Comparison:
    """
    Outcome of comparing the result of a candidate query with the result of the original query.

    Attributes
    ----------
    status : str
        One of EQUIVALENT, TIE_AMBIGUOUS, COLUMN_MISMATCH, ROWCOUNT_MISMATCH,
        VALUE_MISMATCH or ORDER_MISMATCH.
    detail : str, default ""
        Human-readable explanation of the difference. Empty when the results are equivalent.
    """

    status: str  # EQUIVALENT | TIE_AMBIGUOUS | COLUMN_MISMATCH | ROWCOUNT_MISMATCH | VALUE_MISMATCH | ORDER_MISMATCH
    detail: str = ""
