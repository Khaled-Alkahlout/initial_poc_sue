"""SQL admission, bounded read-only execution and result comparison."""

from __future__ import annotations

import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import traverse_scope

from validator.classes.comparison import Comparison
from validator.classes.result import Result
from validator.normalize import norm_row

STATEMENT_TIMEOUT_MS = 2000
MAX_ROWS = 2000
PERCENT = re.compile(r"%%|%\(([a-zA-Z_][a-zA-Z_0-9]*)\)s|%")
FORBIDDEN = (
    exp.DDL,
    exp.DML,
    exp.Command,
    exp.Into,
    exp.Lock,
    exp.Operator,
    exp.TableSample,
)
# PostgreSQL built-ins and parser nodes that represent syntax such as CASE.
SAFE_FUNCTIONS = {
    "ABS",
    "AND",
    "ARRAY",
    "AVG",
    "CASE",
    "CAST",
    "CEIL",
    "COALESCE",
    "COUNT",
    "DATE_TRUNC",
    "DENSE_RANK",
    "EXISTS",
    "EXTRACT",
    "FLOOR",
    "GREATEST",
    "IF",
    "LEAST",
    "LENGTH",
    "LOWER",
    "MAX",
    "MIN",
    "NULLIF",
    "OR",
    "RANK",
    "ROUND",
    "ROW_NUMBER",
    "SUM",
    "UPPER",
}
SAFE_TYPES = {
    "BIGINT",
    "BOOLEAN",
    "DATE",
    "DECIMAL",
    "DOUBLE",
    "FLOAT",
    "INT",
    "INTERVAL",
    "SMALLINT",
    "TEXT",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "UUID",
    "VARCHAR",
}


class SqlRejected(ValueError):
    """Public, SQL-free admission error."""


class ResultLimitExceeded(Exception):
    pass


@dataclass(frozen=True)
class CheckedQuery:
    tree: exp.Expression
    tables: frozenset[str]
    parameters: frozenset[str]

    @property
    def canonical(self):
        return self.tree.sql(dialect="postgres", comments=False)


def inspect_sql(sql: str) -> CheckedQuery:
    """Admit a single PostgreSQL SELECT with named psycopg bindings."""
    if len(sql) > 20000:
        raise SqlRejected("SQL_TOO_LARGE: SQL overschrijdt 20.000 tekens.")
    try:
        parsed = sqlglot.parse(sql.replace("%%", "%"), read="postgres")
        # sqlglot emits Semicolon nodes for comments after a delimiter.
        statements = [
            node
            for node in parsed
            if node is not None and not isinstance(node, exp.Semicolon)
        ]
        if len(statements) != 1:
            raise SqlRejected("MULTIPLE_STATEMENTS: Geef precies één query op.")
        root = statements[0]
        while isinstance(root, exp.Subquery):
            root = root.this
        if not isinstance(root, (exp.Select, exp.SetOperation)) or root.find(
            *FORBIDDEN
        ):
            raise SqlRejected(
                "NOT_SELECT: Alleen leesbare SELECT-query's zijn toegestaan."
            )
        if any(node.args.get("recursive") for node in root.find_all(exp.With)):
            raise SqlRejected("RECURSIVE_QUERY: Recursieve CTE's zijn niet toegestaan.")
        for function in root.find_all(exp.Func):
            if function.sql_name() not in SAFE_FUNCTIONS or isinstance(
                function.parent, exp.Dot
            ):
                raise SqlRejected(
                    "UNSAFE_FUNCTION: Alleen toegestane ingebouwde functies zijn toegestaan."
                )
        if any(
            data_type.this.name not in SAFE_TYPES
            for data_type in root.find_all(exp.DataType)
        ):
            raise SqlRejected(
                "UNSAFE_TYPE: Alleen toegestane ingebouwde typen zijn toegestaan."
            )
        # Scope resolution distinguishes a CTE alias from a physical relation.
        tables = set()
        for scope in traverse_scope(
            normalize_identifiers(root.copy(), dialect="postgres")
        ):
            for node, source in scope.selected_sources.values():
                if isinstance(node, exp.Table) and isinstance(source, exp.Table):
                    if (
                        not isinstance(node.this, exp.Identifier)
                        or node.catalog
                        or node.db not in {"", "public"}
                        or node.name.startswith("pg_")
                    ):
                        raise SqlRejected(
                            "UNSAFE_RELATION: Alleen casustabellen in public zijn toegestaan."
                        )
                    tables.add(node.name)
    except (sqlglot.errors.SqlglotError, RecursionError):
        raise SqlRejected(
            "PARSE_FAIL: SQL kon niet veilig worden geanalyseerd."
        ) from None
    names = [placeholder.name for placeholder in root.find_all(exp.Placeholder)]
    bindings = [match[1] for match in PERCENT.finditer(sql) if match[0] != "%%"]
    # Psycopg interprets % markers even inside strings/comments. Require each
    # marker to correspond to a real SQL placeholder and every other % escaped.
    if None in bindings or Counter(bindings) != Counter(names):
        raise SqlRejected(
            "INVALID_PARAMETERS: Gebruik %(naam)s voor parameters en %% voor een letterlijk procentteken."
        )
    return CheckedQuery(root, frozenset(tables), frozenset(names))


def check_rewrite(original: CheckedQuery, sql: str) -> CheckedQuery:
    candidate = inspect_sql(sql)
    if candidate.parameters != original.parameters:
        raise SqlRejected(
            "PARAMETER_MISMATCH: Het voorstel moet dezelfde benoemde parameters gebruiken."
        )
    if candidate.tables - original.tables:
        raise SqlRejected(
            "RELATION_MISMATCH: Het voorstel verwijst naar tabellen buiten de originele query."
        )
    original_order = original.tree.args.get("order")
    candidate_order = candidate.tree.args.get("order")
    if original_order and (
        not candidate_order
        or len(candidate_order.expressions) < len(original_order.expressions)
    ):
        raise SqlRejected(
            "MISSING_ORDER: Het voorstel laat sorteersleutels van de originele query weg."
        )
    return candidate


def require_tables(conn, tables):
    """Only ordinary tables in the trusted test schema may be queried."""
    if not tables:
        return
    rows = conn.execute(
        """SELECT c.relname::text
             FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relhassubclass
              AND c.relname::text = ANY(%s)""",
        (sorted(tables),),
    ).fetchall()
    if {name for (name,) in rows} != tables:
        raise ValueError(
            "Het testdoel mist gewone casustabellen in public of bevat views, partities of foreign tables."
        )


def static_check(sql: str) -> tuple[bool, str]:
    try:
        inspect_sql(sql)
    except SqlRejected as exc:
        return False, str(exc)
    return True, "Eén toegestane SELECT; statische controle afgerond."


@contextmanager
def read_snapshot(conn):
    """Use an idle, task-owned autocommit connection for one read-only snapshot."""
    with conn.transaction(force_rollback=True):
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
        conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
        conn.execute("SET LOCAL lock_timeout = 500")
        conn.execute("SET LOCAL idle_in_transaction_session_timeout = 10000")
        yield


def run_query(conn, sql: str, params: dict) -> Result:
    """Read at most MAX_ROWS + 1 rows in the active snapshot."""
    started = perf_counter()
    with conn.cursor(name="sue_comparison") as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchmany(MAX_ROWS + 1)
        columns = [column.name for column in cursor.description]
        types = [column.type_code for column in cursor.description]
    if len(rows) > MAX_ROWS:
        raise ResultLimitExceeded(
            f"Meer dan {MAX_ROWS} rijen; vergelijking afgebroken."
        )
    return Result(columns, rows, (perf_counter() - started) * 1000, types)


def compare(orig: Result, cand: Result, order_cols: list[str] | None) -> Comparison:
    """Compare column metadata, row multiplicity and the required sort order."""
    if orig.columns != cand.columns or orig.types != cand.types:
        return Comparison(
            "COLUMN_MISMATCH", "Kolomnamen, volgorde of PostgreSQL-typen verschillen."
        )
    if len(orig.rows) != len(cand.rows):
        return Comparison("ROWCOUNT_MISMATCH", "Het aantal resultaatrijen verschilt.")
    if any(orig.columns.count(column) != 1 for column in (order_cols or [])):
        return Comparison(
            "ORDER_UNVERIFIABLE",
            "Een sorteerkolom ontbreekt of komt meerdere keren in de uitvoer voor.",
        )
    original_rows = [norm_row(row) for row in orig.rows]
    candidate_rows = [norm_row(row) for row in cand.rows]
    if Counter(original_rows) != Counter(candidate_rows):
        return Comparison(
            "VALUE_MISMATCH",
            "De waarden of multipliciteit van resultaatrijen verschillen.",
        )
    indices = [orig.columns.index(column) for column in (order_cols or [])]
    if indices:
        original_keys = [
            tuple(row[index] for index in indices) for row in original_rows
        ]
        candidate_keys = [
            tuple(row[index] for index in indices) for row in candidate_rows
        ]
        if original_keys != candidate_keys:
            return Comparison(
                "ORDER_MISMATCH", "De volgorde op de sorteersleutel verschilt."
            )
    return Comparison(
        "EQUIVALENT", "Kolommen, rijen en vereiste volgorde komen overeen."
    )
