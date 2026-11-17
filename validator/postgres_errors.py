"""Safe PostgreSQL diagnostics for workflow results and server logs."""

import re

PHASES = {"connect", "context", "correctness", "benchmark"}
MESSAGES = {
    "configuration": "De PostgreSQL-configuratie op de server is ongeldig. Controleer de instellingen in .env.",
    "driver": "De PostgreSQL-driver psycopg kan niet worden geladen door de backend.",
    "dns": "De hostnaam van de testdatabase kan niet worden gevonden vanuit de backend.",
    "timeout": "De verbinding met de testdatabase overschreed de connect-time-out.",
    "unreachable": "De backend kan de testdatabase niet bereiken. Controleer host, poort en netwerk.",
    "tls": "De TLS-verbinding met de testdatabase is mislukt. Controleer TLS-instellingen en certificaten.",
    "authentication": "PostgreSQL weigert de verbinding. Controleer de databaserol, authenticatie en toegangsregels.",
    "database": "De ingestelde databasenaam bestaat niet op deze PostgreSQL-server.",
    "permissions": "De databaserol mist rechten om de casus uit te voeren. Controleer USAGE op public en SELECT-rechten.",
    "schema": "Een vereist schema, tabel of kolom ontbreekt. Controleer het testdataschema en de SQL.",
    "connection_lost": "De verbinding met PostgreSQL is tijdens uitvoering verbroken.",
    "statement_cancelled": "PostgreSQL heeft het statement afgebroken. Controleer de statement-time-out en belasting.",
    "lock_timeout": "PostgreSQL kon binnen de lockwachttijd geen toegang tot de tabel krijgen.",
    "query_error": "PostgreSQL kon de query of het parameterprofiel niet uitvoeren.",
}
SQLSTATE_CODES = {
    "3D000": "database",
    "3F000": "schema",
    "42501": "permissions",
    "42703": "schema",
    "42P01": "schema",
    "57014": "statement_cancelled",
    "55P03": "lock_timeout",
}
CONNECT_HINTS = (
    (
        "dns",
        (
            "could not translate host name",
            "getaddrinfo",
            "no such host",
            "name or service not known",
        ),
    ),
    (
        "authentication",
        ("authentication failed", "no password supplied", "no pg_hba.conf entry"),
    ),
    (
        "tls",
        (
            "ssl error",
            "ssl certificate",
            "root certificate",
            "certificate verify",
            "does not match host name",
            "does not support ssl",
        ),
    ),
    ("timeout", ("timeout expired", "connection timed out", "connection timeout")),
)


def safe_sqlstate(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Z0-9]{5}", value)
        else None
    )


def postgres_error(exc, phase):
    state = safe_sqlstate(getattr(exc, "sqlstate", None))
    code = SQLSTATE_CODES.get(state)
    if state and state.startswith("28"):
        code = "authentication"
    if code is None and phase == "connect":
        # libpq connection errors may lack a server SQLSTATE. The original
        # message is used only to classify the failure and is never exported.
        text = str(exc).lower()
        code = next(
            (
                kind
                for kind, markers in CONNECT_HINTS
                if any(marker in text for marker in markers)
            ),
            None,
        )
        if code is None and re.search(r'database "[^"]+" does not exist', text):
            code = "database"
        if code is None:
            code = {
                "ProgrammingError": "configuration",
                "ConnectionTimeout": "timeout",
            }.get(type(exc).__name__, "unreachable")
    if code is None:
        code = "connection_lost" if state and state.startswith("08") else "query_error"
    return {"code": code, "phase": phase, "sqlstate": state}
