"""Server-side PostgreSQL settings, connections and read-only checks."""

import logging
import os
import re
from contextlib import contextmanager
from importlib.util import find_spec
from pathlib import Path

from api.config import ROOT
from api.schemas import DatabaseCheckStep, DatabaseConnectionTest
from cases.cases import CASES
from validator.checker import (
    STATEMENT_TIMEOUT_MS,
    inspect_sql,
    read_snapshot,
    require_tables,
)
from validator.postgres_errors import MESSAGES, postgres_error

logger = logging.getLogger("sue.api")

RDS_FIELDS = {
    "ENDPOINT": "host",
    "PORT": "port",
    "DB_NAME": "dbname",
    "DB_USER": "user",
    "DB_PASS": "password",
}


class TestDatabaseError(ValueError):
    def __init__(self, message, issue=None):
        super().__init__(message)
        self.issue = issue


def _configuration_error(message):
    return TestDatabaseError(
        message, {"code": "configuration", "phase": "connect", "sqlstate": None}
    )


def _connection_parameters():
    dsn = os.getenv("SUE_DATABASE_URL", "").strip()
    if dsn:
        return {"conninfo": dsn}

    values = {key: os.getenv(key, "") for key in RDS_FIELDS}
    if not any(value.strip() for key, value in values.items() if key != "PORT"):
        raise _configuration_error("SUE_DATABASE_URL ontbreekt op de server.")
    missing = [key for key, value in values.items() if not value.strip()]
    if missing:
        raise _configuration_error(
            f"Vul de RDS-instellingen in .env aan ({', '.join(missing)})."
        )
    port = values["PORT"].strip()
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise _configuration_error("PORT moet een poortnummer tussen 1 en 65535 zijn.")

    parameters = {target: values[key].strip() for key, target in RDS_FIELDS.items()}
    parameters["password"] = values["DB_PASS"]
    parameters["sslmode"] = "verify-full"
    if root_cert := os.getenv("PGSSLROOTCERT", "").strip():
        parameters["sslrootcert"] = (
            root_cert
            if root_cert == "system"
            else str(ROOT / Path(root_cert).expanduser())
        )
    return parameters


def database_configuration_error():
    try:
        _connection_parameters()
    except TestDatabaseError as exc:
        return str(exc)
    return None


def validation_blocker(settings):
    missing = []
    if error := database_configuration_error():
        missing.append(error)
    if not settings.enable_sql:
        missing.append("SUE_ENABLE_SQL_RUNS=1 is vereist.")
    if not settings.test_database_confirmed:
        missing.append("SUE_TEST_DATABASE_CONFIRMED=1 is vereist.")
    if find_spec("psycopg") is None:
        missing.append("Installeer psycopg in de Python-omgeving van de API.")
    return " ".join(missing)


def require_confirmation(settings, confirmed: bool):
    if not (settings.enable_sql and settings.test_database_confirmed and confirmed):
        raise TestDatabaseError(
            "SQL-validatie uitgeschakeld: beide veiligheidsinstellingen en expliciete bevestiging zijn vereist."
        )


@contextmanager
def connect_test_database(*, phase="context"):
    parameters = _connection_parameters()
    try:
        import psycopg
    except ImportError:
        raise TestDatabaseError(
            MESSAGES["driver"], {"code": "driver", "phase": "connect", "sqlstate": None}
        ) from None
    try:
        connection = psycopg.connect(
            **parameters,
            autocommit=True,
            connect_timeout=5,
            prepare_threshold=None,
            options=f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}",
        )
    except psycopg.Error as exc:
        issue = postgres_error(exc, "connect")
        raise TestDatabaseError(MESSAGES[issue["code"]], issue) from None
    try:
        with connection as opened:
            yield opened
    except psycopg.Error as exc:
        issue = postgres_error(exc, phase)
        raise TestDatabaseError(MESSAGES[issue["code"]], issue) from None


def check_case_database(connection, tables):
    """Check the session and case sources before sending a live model request."""
    connection.execute("SELECT 1").fetchone()
    _check_case_tables(connection, tables)


def _check_case_tables(connection, tables):
    from psycopg import sql

    required = tables | {"orders"}  # Case parameter profiles also read orders.
    with read_snapshot(connection):
        try:
            require_tables(connection, required)
        except ValueError as exc:
            raise TestDatabaseError(
                str(exc), {"code": "schema", "phase": "context", "sqlstate": None}
            ) from None
        for table in sorted(required):
            statement = sql.SQL("SELECT 1 FROM {} LIMIT 0").format(
                sql.Identifier("public", table)
            )
            connection.execute(statement)


def check_database():
    """Exercise the configured connection and the validator's table admission checks."""
    tables = set().union(*(inspect_sql(case.original).tables for case in CASES))
    connected = False
    try:
        with connect_test_database() as connection:
            connection.execute("SELECT 1").fetchone()
            connected = True
            _check_case_tables(connection, tables)
    except TestDatabaseError as exc:
        if exc.issue:
            logger.warning(
                "postgres_check_failed phase=%s code=%s sqlstate=%s",
                exc.issue["phase"],
                exc.issue["code"],
                exc.issue["sqlstate"] or "-",
            )
        if not connected:
            return DatabaseConnectionTest(
                connection=DatabaseCheckStep(status="failed", message=str(exc)),
                tables=DatabaseCheckStep(
                    status="skipped",
                    message="Toegang controleren vereist een werkende verbinding.",
                ),
            )
        table_check = DatabaseCheckStep(status="failed", message=str(exc))
    else:
        table_check = DatabaseCheckStep(
            status="passed",
            message="De vereiste casustabellen in public zijn leesbaar.",
        )
    return DatabaseConnectionTest(
        connection=DatabaseCheckStep(
            status="passed", message="PostgreSQL heeft SELECT 1 uitgevoerd."
        ),
        tables=table_check,
    )
