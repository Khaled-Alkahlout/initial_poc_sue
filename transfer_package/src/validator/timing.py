"""Herhaalde tijdmeting, om en om (ABAB) zodat caching en drift beide kanten even raken."""
from __future__ import annotations

import statistics

from validator.checker import run_query

TIMEOUT_MS = 120000
SPEEDUP_THRESHOLD = 1.2  # een voorstel telt pas als 'sneller' vanaf 20% winst op de mediaan


def measure(conn, orig_sql: str, cand_sql: str, params: dict, reps: int = 7, warmup: int = 2) -> dict:
    """
    Measure the speed of a candidate against the original with alternating repetitions.

    The original and the candidate are executed in turn (ABAB), so that caching and
    drift affect both equally. When the original takes longer than 5 seconds the number
    of repetitions is reduced to at most 3 and the warm-up is skipped.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection, in autocommit mode.
    orig_sql : str
        The original query.
    cand_sql : str
        The candidate query.
    params : dict
        Parameter values used for all executions.
    reps : int, default 7
        Number of timed executions per query.
    warmup : int, default 2
        Number of untimed executions per query before measuring.

    Returns
    -------
    dict
        ``orig_median_ms``, ``orig_iqr_ms``, ``cand_median_ms``, ``cand_iqr_ms``,
        ``speedup`` (original median divided by candidate median), ``faster`` (True when
        the speedup reaches ``SPEEDUP_THRESHOLD``) and ``reps`` (the repetitions used).
    """
    # Trage originelen (>5 s): minder herhalingen en geen warm-up, anders duurt de proef uren.
    first = run_query(conn, orig_sql, params, timeout_ms=TIMEOUT_MS).ms
    if first > 5000:
        reps, warmup = min(reps, 3), 0
    for _ in range(warmup):
        run_query(conn, orig_sql, params, timeout_ms=TIMEOUT_MS)
        run_query(conn, cand_sql, params, timeout_ms=TIMEOUT_MS)
    a, b = [], []
    for _ in range(reps):
        a.append(run_query(conn, orig_sql, params, timeout_ms=TIMEOUT_MS).ms)
        b.append(run_query(conn, cand_sql, params, timeout_ms=TIMEOUT_MS).ms)

    def iqr(x):
        """
        Compute the interquartile range of a list of measurements.

        Parameters
        ----------
        x : list of float
            Measured durations in milliseconds.

        Returns
        -------
        float
            Third quartile minus first quartile.
        """
        q = statistics.quantiles(x, n=4)
        return q[2] - q[0]

    ma, mb = statistics.median(a), statistics.median(b)
    return {
        "orig_median_ms": round(ma, 1), "orig_iqr_ms": round(iqr(a), 1),
        "cand_median_ms": round(mb, 1), "cand_iqr_ms": round(iqr(b), 1),
        "speedup": round(ma / mb, 2) if mb else None,
        "faster": (ma / mb) >= SPEEDUP_THRESHOLD if mb else False,
        "reps": reps,
    }
