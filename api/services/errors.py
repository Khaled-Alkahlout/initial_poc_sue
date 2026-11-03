"""Public error contracts and useful diagnostics without SQL or provider bodies."""

import json
import logging
import sqlite3
import traceback
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import JSONResponse
from pydantic import ValidationError

from api.services.runtime import RuntimeMismatch

logger = logging.getLogger("sue.api")


def validation_locations(exc):
    return [
        {"location": list(item["loc"]), "type": item["type"]}
        for item in exc.errors(
            include_input=False, include_context=False, include_url=False
        )
    ]


class StoredResultError(Exception):
    def __init__(self, run_id, cause):
        super().__init__(
            "Opgeslagen analyse is niet compatibel met het backendcontract. Controleer de backendversie en de diagnostiek; historie is behouden."
        )
        self.run_id = run_id
        self.validation_errors = validation_locations(cause)


def error_response(request, status, code, message, **extra):
    return JSONResponse(
        status_code=status,
        content={
            "detail": message,
            "error_code": code,
            "request_id": request.state.request_id,
            **extra,
        },
    )


def log_exception(request, exc, code):
    route = request.scope.get("route")
    record = {
        "request_id": request.state.request_id,
        "method": request.method,
        "route": getattr(route, "path", "unmatched"),
        "error_code": code,
        "exception_type": type(exc).__name__,
        "frames": [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(exc.__traceback__)
        ],
    }
    if isinstance(exc, StoredResultError):
        record.update(
            run_id=exc.run_id,
            cause_type=type(exc.__cause__).__name__,
            validation_errors=exc.validation_errors,
        )
    elif isinstance(exc, ValidationError):
        record["validation_errors"] = validation_locations(exc)
    elif isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        record.update(
            {
                k: exc.detail[k]
                for k in ("provider_error_code", "upstream_status")
                if k in exc.detail
            }
        )
    # No str(exc), exception locals, SQL, request body or raw validation input.
    logger.error("api_failure %s", json.dumps(record))


def unexpected_error(request, exc):
    status, code, message = (
        500,
        "internal_error",
        "Interne backendfout. Raadpleeg de serverdiagnostiek met de referentiecode.",
    )
    if isinstance(exc, RuntimeMismatch):
        status, code, message = 503, "runtime_version_mismatch", str(exc)
    elif isinstance(exc, StoredResultError):
        code, message = "stored_result_incompatible", str(exc)
    elif isinstance(exc, sqlite3.OperationalError) and any(
        text in str(exc).lower()
        for text in ("locked", "unable to open", "readonly", "disk i/o")
    ):
        status, code, message = (
            503,
            "storage_unavailable",
            "De lokale opslag is tijdelijk niet beschikbaar. Controleer de backendopslag en probeer opnieuw.",
        )
    log_exception(request, exc, code)
    return error_response(request, status, code, message)


def model_http_error(exc, default=503):
    code = exc.diagnostics.get("error_code")
    status = (
        503
        if code == "network_or_timeout"
        or exc.diagnostics.get("http_status") in {429, 502, 503, 504}
        else 422
        if code == "unsupported_settings"
        else 502
        if code
        else default
    )
    return HTTPException(
        status_code=status,
        detail={
            "message": str(exc),
            "error_code": "invalid_input" if status == 422 else "llm_request_failed",
            "provider_error_code": code,
            "upstream_status": exc.diagnostics.get("http_status"),
        },
    )
