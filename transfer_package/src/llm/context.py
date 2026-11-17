"""Contextinformatie voor de LLM, opgebouwd uit de database zelf.

Vier condities, cumulatief (elke conditie bevat alles van de vorige):
  C1_query   alleen de originele query
  C2_schema  + kolommen, indexen en constraints van de gebruikte tabellen
  C3_plan    + EXPLAIN (ANALYZE, BUFFERS) van het origineel op de timing-parameters
  C4_stats   + tabelgroottes en kolomstatistieken (pg_class, pg_stats)

Alles wordt read-only gelezen; EXPLAIN ANALYZE draait in een transactie die altijd wordt teruggedraaid.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

CONDITIONS = ["C1_query", "C2_schema", "C3_plan", "C4_stats"]
PLACEHOLDER = re.compile(r"%\((\w+)\)s")
MAX_PLAN_CHARS = 8000


def tables_and_columns(sql: str) -> tuple[list[str], set[str]]:
    """
    Find the real table names (not CTE names) and the column names used in a query.

    Parameters
    ----------
    sql : str
        Query text with %(name)s placeholders.

    Returns
    -------
    tuple of (list of str, set of str)
        Sorted table names and the set of column names that occur in the query.
    """
    tree = sqlglot.parse_one(PLACEHOLDER.sub(lambda m: f"'__p_{m.group(1)}'", sql), read="postgres")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    tables = sorted({t.name for t in tree.find_all(exp.Table) if t.name not in ctes})
    cols = {c.name for c in tree.find_all(exp.Column)}
    return tables, cols


def schema_text(conn, tables: list[str]) -> str:
    """
    Describe the schema of the given tables: columns, constraints and indexes.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database.
    tables : list of str
        Table names in schema "public".

    Returns
    -------
    str
        Text with a TABLE block per table followed by its constraints and index definitions.
    """
    out = []
    for t in tables:
        cols = conn.execute(
            """SELECT column_name, data_type, is_nullable FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""", (t,)).fetchall()
        if not cols:
            out.append(f"-- {t}: niet gevonden in schema public")
            continue
        lines = [f"  {c} {d}{'' if n == 'YES' else ' NOT NULL'}" for c, d, n in cols]
        out.append(f"TABLE {t} (\n" + ",\n".join(lines) + "\n)")
        for (cdef,) in conn.execute(
                """SELECT pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = %s::regclass ORDER BY contype, conname""", (t,)).fetchall():
            out.append(f"  CONSTRAINT {cdef}")
        for (idef,) in conn.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s ORDER BY indexname",
                (t,)).fetchall():
            out.append(f"  {idef}")
    return "\n".join(out)


def plan_text(conn, sql: str, params: dict, timeout_ms: int = 120000) -> str:
    """
    Run EXPLAIN (ANALYZE, BUFFERS) on a query in a read-only transaction that is always rolled back.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database.
    sql : str
        Query text with %(name)s placeholders.
    params : dict
        Parameter values for the placeholders.
    timeout_ms : int, default 120000
        Statement timeout in milliseconds.

    Returns
    -------
    str
        The execution plan as text, truncated to MAX_PLAN_CHARS characters.
    """
    with conn.transaction(force_rollback=True):
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql, params).fetchall()
    text = "\n".join(r[0] for r in rows)
    return text if len(text) <= MAX_PLAN_CHARS else text[:MAX_PLAN_CHARS] + "\n... (afgekapt)"


def _short(v, n=120):
    """
    Shorten the text form of a value for use in a statistics line.

    Parameters
    ----------
    v : object
        Value to convert with ``str``.
    n : int, default 120
        Maximum number of characters before the text is cut off with an ellipsis.

    Returns
    -------
    str
        The text, or its first ``n`` characters followed by an ellipsis.
    """
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def stats_text(conn, tables: list[str], cols: set[str]) -> str:
    """
    Describe table sizes and column statistics (pg_class, pg_stats) for the columns used in the query.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database.
    tables : list of str
        Table names in schema "public".
    cols : set of str
        Column names that occur in the query; statistics of other columns are skipped.

    Returns
    -------
    str
        One line per table (estimated rows and pages) and one line per used column
        (null fraction, n_distinct, correlation and most common values).
    """
    out = []
    for t in tables:
        r = conn.execute("SELECT reltuples::bigint, relpages FROM pg_class WHERE oid = %s::regclass", (t,)).fetchone()
        if r:
            out.append(f"{t}: ~{r[0]} rijen, {r[1]} pagina's")
        for row in conn.execute(
                """SELECT attname, null_frac, n_distinct, correlation, most_common_vals::text, most_common_freqs::text
                     FROM pg_stats WHERE schemaname = 'public' AND tablename = %s ORDER BY attname""", (t,)).fetchall():
            name, nf, nd, corr, mcv, mcf = row
            if name not in cols:
                continue
            out.append(f"  {t}.{name}: null_frac={nf:.3f} n_distinct={nd} correlation={corr if corr is None else round(corr, 3)}"
                       + (f" mcv={_short(mcv)} freqs={_short(mcf)}" if mcv else ""))
    return "\n".join(out)


def build_context(conn, case, ctx, condition: str) -> dict:
    """
    Build the context blocks that belong to a condition, as separate texts (for logging).

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database.
    case : Case
        Case whose original query is described.
    ctx : dict
        Context as returned by ``make_ctx``; used for the timing parameters of the execution plan.
    condition : str
        One of CONDITIONS; each condition includes everything of the previous one.

    Returns
    -------
    dict
        Blocks with the keys "query", and depending on the condition "schema", "plan" and "stats".
    """
    level = CONDITIONS.index(condition)
    tables, cols = tables_and_columns(case.original)
    blocks = {"query": case.original.strip()}
    if level >= 1:
        blocks["schema"] = schema_text(conn, tables)
    if level >= 2:
        blocks["plan"] = plan_text(conn, case.original, case.timing_params(ctx))
    if level >= 3:
        blocks["stats"] = stats_text(conn, tables, cols)
    return blocks
