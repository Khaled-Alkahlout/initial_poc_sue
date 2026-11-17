"""Stap 1: statische controle. Stap 2: uitvoeren in een read-only transactie. Stap 3: resultaten vergelijken."""
from __future__ import annotations

import re
import time
from collections import Counter

import sqlglot
from sqlglot import exp

from validator.classes.result import Result
from validator.classes.comparison import Comparison
from validator.normalize import norm_row

PLACEHOLDER = re.compile(r"%\((\w+)\)s")
FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.TruncateTable)


def static_check(sql: str) -> tuple[bool, str]:
    """
    Check statically that a candidate is exactly one allowed SELECT statement.

    The query is parsed with sqlglot (PostgreSQL dialect) after the ``%(name)s``
    placeholders have been replaced by string literals. Data-modifying and DDL
    nodes are rejected, also when they occur inside a CTE.

    Parameters
    ----------
    sql : str
        The candidate query, with ``%(name)s`` placeholders for its parameters.

    Returns
    -------
    tuple of (bool, str)
        ``(True, "ok")`` when the query passes. Otherwise ``(False, reason)``, where
        reason starts with PARSE_FAIL, MULTIPLE_STATEMENTS, NOT_SELECT or FORBIDDEN_NODE.
    """
    try:
        parsed = sqlglot.parse(PLACEHOLDER.sub(lambda m: f"'__p_{m.group(1)}'", sql), read="postgres")
    except sqlglot.errors.SqlglotError as e:
        return False, f"PARSE_FAIL: {str(e)[:80]}"
    parsed = [p for p in parsed if p is not None]
    if len(parsed) != 1:
        return False, f"MULTIPLE_STATEMENTS: {len(parsed)}"
    root = parsed[0]
    if not isinstance(root, (exp.Select, exp.Union, exp.Subquery)):
        return False, f"NOT_SELECT: {type(root).__name__}"
    if any(root.find(t) for t in FORBIDDEN):
        return False, "FORBIDDEN_NODE"
    return True, "ok"


def run_query(conn, sql: str, params: dict, timeout_ms: int = 30000) -> Result:
    """
    Execute a query read-only, with a timeout, and measure how long it takes.

    Every call runs in its own transaction that is always rolled back, so
    nothing can be changed in the database.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection, in autocommit mode.
    sql : str
        The query, with ``%(name)s`` placeholders.
    params : dict
        Parameter values, keyed by placeholder name.
    timeout_ms : int, default 30000
        Statement timeout in milliseconds.

    Returns
    -------
    Result
        Column names, all rows and the duration in milliseconds.
    """
    t0 = time.perf_counter()
    with conn.transaction(force_rollback=True):
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        cur = conn.execute(sql, params)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    return Result(cols, rows, (time.perf_counter() - t0) * 1000)


def compare(orig: Result, cand: Result, order_cols: list[str] | None) -> Comparison:
    """
    Compare the result of a candidate query with the result of the original query.

    Columns must be identical (names and order). Rows are compared as a multiset of
    normalised values. When ``order_cols`` is given, the sequence of sort-key values
    must also be identical. A difference that only involves rows with the same sort
    key as the last original row (the LIMIT boundary) is reported as TIE_AMBIGUOUS.

    Parameters
    ----------
    orig : Result
        Result of the original query.
    cand : Result
        Result of the candidate query, on the same parameters.
    order_cols : list of str or None
        Output columns that define the ORDER BY of the original query, or None when the
        original has no meaningful order.

    Returns
    -------
    Comparison
        Status (EQUIVALENT, TIE_AMBIGUOUS, COLUMN_MISMATCH, ROWCOUNT_MISMATCH,
        VALUE_MISMATCH or ORDER_MISMATCH) with a detail text.
    """
    if orig.columns != cand.columns:
        return Comparison("COLUMN_MISMATCH", f"{orig.columns} != {cand.columns}")
    o = [norm_row(r) for r in orig.rows]
    c = [norm_row(r) for r in cand.rows]
    idx = [orig.columns.index(x) for x in (order_cols or [])]
    key = lambda r: tuple(r[i] for i in idx)
    if Counter(o) == Counter(c):
        if idx and [key(r) for r in o] != [key(r) for r in c]:
            return Comparison("ORDER_MISMATCH", "zelfde rijen, andere volgorde op de sorteersleutel")
        return Comparison("EQUIVALENT")
    only_o, only_c = Counter(o) - Counter(c), Counter(c) - Counter(o)
    if idx and o:
        boundary = key(o[-1])
        if all(key(r) == boundary for r in list(only_o) + list(only_c)):
            return Comparison("TIE_AMBIGUOUS", "verschil alleen bij gelijke sorteersleutel aan de LIMIT-grens")
    if len(o) != len(c):
        return Comparison("ROWCOUNT_MISMATCH", f"{len(o)} tegenover {len(c)} rijen")
    return Comparison("VALUE_MISMATCH", f"{sum(only_o.values())} rijen verschillen")
