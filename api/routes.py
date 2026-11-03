"""Thin REST routes. Domain operations live in services and existing modules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.schemas import (
    Feedback,
    FeedbackInput,
    Overview,
    QueryCollection,
    QueryDetail,
    RunDetail,
    RunRequest,
    RunSummary,
    SystemStatus,
    TestCollection,
    TestExecution,
    TestRecord,
    TestRequest,
    AIConnectionTest,
    RewriteDisplay,
)
from api.services.artifacts import CASE_MAP
from api.services.jobs import BusyError
from api.services.privacy import redact
from llm.generation import GenerationSettings
from api.services import ai_settings
from llm.analysis import AnalysisError
from api.services.errors import model_http_error

router = APIRouter(prefix="/api")


def require(value):
    if value is None:
        raise HTTPException(404, "Niet gevonden.")
    return value


def enqueue(request: Request, kind: str, config: dict):
    try:
        return request.app.state.jobs.start(kind, config)
    except BusyError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/overview", response_model=Overview)
def overview(request: Request):
    return request.app.state.catalog.overview()


@router.get("/queries", response_model=QueryCollection)
def queries(
    request: Request,
    top_k: int = Query(2, ge=0, le=4),
    exclude_query: list[str] = Query(default=[]),
):
    return request.app.state.catalog.queries(top_k, exclude_query)


@router.get("/queries/{query_id}", response_model=QueryDetail)
def query(query_id: str, request: Request):
    return require(request.app.state.catalog.query(query_id))


@router.get("/runs", response_model=list[RunSummary])
def runs(request: Request):
    return request.app.state.catalog.runs()


@router.get("/runs/{run_id}", response_model=RunDetail)
def run(run_id: str, request: Request):
    return require(request.app.state.catalog.run(run_id))


@router.post("/runs", response_model=RunDetail, status_code=202)
def start_run(value: RunRequest, request: Request):
    catalog = request.app.state.catalog
    if value.rewrite_only:
        from api.services.analysis import rewrite_source

        if value.mode != "analysis":
            raise HTTPException(422, "Gerichte rewrite vereist analysis-modus.")
        try:
            rewrite_source(request.app.state.store, value.source_id, value.query_id)
        except AnalysisError as exc:
            raise HTTPException(422, str(exc)) from None
    if value.query_id not in CASE_MAP:
        raise HTTPException(422, "Alleen bestaande querycases zijn toegestaan.")
    capability = next(
        item for item in catalog.system().run_modes if item.id == value.mode
    )
    if not capability.available:
        raise HTTPException(409, capability.reason)
    if capability.executes_sql and not value.confirm_sql:
        raise HTTPException(
            422, "Bevestig expliciet de SQL-uitvoering op de testdatabase."
        )
    if capability.external_model and not value.confirm_external_model:
        raise HTTPException(
            422, "Bevestig expliciet het externe modelrequest en mogelijke kosten."
        )
    if value.mode == "mock" and value.condition != "C1_query":
        raise HTTPException(
            422,
            "Offline mock ondersteunt alleen C1_query; overige context vereist een database.",
        )
    if (
        value.mode == "replay"
        and catalog.artifacts.replay(value.query_id, value.condition, value.source_id)
        is None
    ):
        raise HTTPException(422, "Geen opgeslagen replay voor deze combinatie.")
    if value.mode == "validate":
        from api.services.analysis import saved_proposal

        try:
            saved_proposal(request.app.state.store, value.source_id, value.query_id)
        except AnalysisError as exc:
            raise HTTPException(422, str(exc)) from None
    config = value.model_dump()
    if value.mode == "analysis":
        config["generation_settings"] = (
            request.app.state.store.generation_settings().model_dump()
        )
    job = enqueue(request, "run", config)
    return catalog.job_run(job)


@router.post("/runs/{run_id}/rewrite-display", status_code=204)
def rewrite_display(run_id: str, value: RewriteDisplay, request: Request):
    store = request.app.state.store
    job = require(store.job(run_id))
    result = job.get("result")
    if not result or not result.get("attempts"):
        raise HTTPException(422, "Geen opgeslagen voorstel beschikbaar.")
    attempt = result["attempts"][0]
    if value.sql_displayed and not attempt.get("proposed_sql"):
        raise HTTPException(422, "Er is geen opgeslagen SQL om weer te geven.")
    store.record_rewrite_display(run_id, value.sql_displayed)


@router.get("/development/tests", response_model=TestCollection)
def tests(request: Request):
    collection = request.app.state.catalog.tests()
    collection.tests = [
        test.model_copy(update={"attempt": None}) for test in collection.tests
    ]
    return collection


@router.get("/development/tests/{test_id}", response_model=TestRecord)
def test(test_id: str, request: Request):
    return require(request.app.state.catalog.test(test_id))


@router.post("/development/tests/run", response_model=TestExecution, status_code=202)
def run_tests(value: TestRequest, request: Request):
    catalog = request.app.state.catalog
    capability = next(
        item for item in catalog.system().test_suites if item.id == value.suite
    )
    if not capability.available:
        raise HTTPException(409, capability.reason)
    if value.query_id not in CASE_MAP:
        raise HTTPException(422, "Onbekende querycase.")
    if capability.executes_sql and not value.confirm_sql:
        raise HTTPException(
            422, "Bevestig expliciet de SQL-uitvoering op de testdatabase."
        )
    job = enqueue(request, "test", value.model_dump())
    return require(catalog.execution(job["id"]))


@router.get("/development/executions/{job_id}", response_model=TestExecution)
def execution(job_id: str, request: Request):
    return require(request.app.state.catalog.execution(job_id))


@router.get("/development/feedback", response_model=list[Feedback])
def feedback(
    request: Request, target_id: str | None = Query(default=None, max_length=240)
):
    return request.app.state.store.feedback(target_id)


@router.post("/development/feedback", response_model=Feedback, status_code=201)
def add_feedback(value: FeedbackInput, request: Request):
    catalog = request.app.state.catalog
    exists = (
        catalog.run(value.target_id)
        if value.target_type == "run"
        else catalog.test(value.target_id)
    )
    if value.target_type == "attempt":
        exists = next(
            (
                a
                for run in catalog.runs()
                for a in run.attempts
                if a.id == value.target_id
            ),
            None,
        )
    if exists is None:
        raise HTTPException(404, "Reviewdoel bestaat niet.")
    safe = value.model_copy(
        update={"comment": redact(value.comment), "reviewer": redact(value.reviewer)}
    )
    return request.app.state.store.add_feedback(safe)


@router.get("/system/status", response_model=SystemStatus)
def system_status(request: Request):
    return request.app.state.catalog.system()


@router.post("/system/check-model")
def check_model():
    from llm.analysis import AnalysisError, check_connection

    try:
        return check_connection()
    except AnalysisError as exc:
        raise model_http_error(exc) from None


@router.get("/settings/ai")
def get_ai_settings(request: Request):
    try:
        return ai_settings.settings_view(
            request.app.state.store, request.app.state.catalog.settings
        )
    except AnalysisError as exc:
        raise model_http_error(exc) from None


@router.put("/settings/ai", response_model=GenerationSettings)
def put_ai_settings(value: GenerationSettings, request: Request):
    try:
        ai_settings.save_settings(request.app.state.store, value)
        return value
    except AnalysisError as exc:
        raise model_http_error(exc) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/settings/ai/reset", response_model=GenerationSettings)
def reset_ai_settings(request: Request):
    try:
        value = ai_settings.environment_defaults()
        ai_settings.validate_capabilities(value, ai_settings.model_capabilities())
        request.app.state.store.reset_generation_settings()
        return value
    except AnalysisError as exc:
        raise model_http_error(exc) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/settings/ai/test")
def test_ai_generation(value: AIConnectionTest, request: Request):
    try:
        result = ai_settings.test_generation(request.app.state.catalog.settings)
        if not result["success"] and result.get("diagnostics", {}).get(
            "error_code"
        ) in {"network_or_timeout", "provider_error"}:
            raise model_http_error(
                AnalysisError(result["message"], result["diagnostics"])
            )
        return result
    except AnalysisError as exc:
        raise model_http_error(exc, default=409) from None
