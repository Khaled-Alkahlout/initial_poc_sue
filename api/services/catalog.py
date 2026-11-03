"""Compose source adapters for views; business selection stays in query_selection/."""

from __future__ import annotations

import importlib.util
import os
from pydantic import ValidationError
from collections import Counter

from api.config import CONDITIONS, Settings
from api.schemas import (
    Capability,
    ConditionStats,
    Metric,
    Overview,
    QueryCollection,
    QueryDetail,
    QueryView,
    RunDetail,
    RunSummary,
    SystemStatus,
    TestCollection,
    TestExecution,
    TestRecord,
)
from api.services.artifacts import Artifacts, CASE_MAP, LIMITATIONS, stage
from api.services.storage import Store
from api.services.errors import StoredResultError
from query_selection.adapters import mock_telemetry
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries


class Catalog:
    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.artifacts = Artifacts(settings.results_dir)

    def selection(self, top_k=2, excluded=()):
        return select_queries(
            mock_telemetry(CASE_MAP.values()),
            SelectionPolicy(top_k=top_k, excluded_query_ids=frozenset(excluded)),
        )

    def runs(self) -> list[RunDetail]:
        values = list(self.artifacts.runs.values())
        for job in self.store.jobs("run"):
            values.append(self.job_run(job))
        return sorted(values, key=lambda run: run.created_at, reverse=True)

    @staticmethod
    def job_run(job: dict) -> RunDetail:
        if job["result"]:
            try:
                result = RunDetail.model_validate(job["result"])
            except ValidationError as exc:
                raise StoredResultError(job["id"], exc) from exc
            return result.model_copy(
                update={
                    "lifecycle": job["status"],
                    "completed_at": job["completed_at"],
                    "error": job["error"],
                }
            )
        config = job["config"]
        return RunDetail(
            id=job["id"],
            title={
                "replay": "Historische replay",
                "mock": "Offline mock",
                "live_mock": "Testdatabase / mockmodel",
                "live": "Live POC",
                "analysis": "AI-analyse · ongetest advies",
                "validate": "Validatie opgeslagen AI-voorstel",
            }[config["mode"]],
            mode=config["mode"],
            lifecycle=job["status"],
            created_at=job["created_at"],
            completed_at=job["completed_at"],
            query_ids=[config["query_id"]],
            stages=job["progress"]
            or [
                stage(
                    key,
                    ("error" if key == "result" else "skipped")
                    if job["status"] == "FAILED"
                    else "pending",
                    job["error"]
                    or "Taak staat in de wachtrij; fase nog niet uitgevoerd.",
                    "current",
                )
                for key in (
                    "selection",
                    "context",
                    "generation",
                    "static",
                    "correctness",
                    "benchmark",
                    "result",
                )
            ],
            error=job["error"],
            limitations=LIMITATIONS,
        )

    def run(self, run_id: str) -> RunDetail | None:
        return next((run for run in self.runs() if run.id == run_id), None)

    def queries(self, top_k=2, excluded=()) -> QueryCollection:
        selection = self.selection(top_k, excluded)
        historical = self.runs()
        queries = []
        for decision in sorted(
            selection.decisions, key=lambda d: (d.rank or 999, d.telemetry.query_id)
        ):
            query_id = decision.telemetry.query_id
            runs = sorted(
                [r for r in historical if query_id in r.query_ids],
                key=lambda r: r.created_at,
                reverse=True,
            )
            attempts = [
                a
                for run in runs
                for a in run.attempts
                if a.query_id == query_id
                and a.model not in {None, "mock"}
                and run.mode not in {"replay", "validate", "mock", "live_mock"}
            ]
            queries.append(
                QueryView(
                    **decision.to_dict(),
                    analyzed=bool(attempts),
                    related_run_ids=[r.id for r in runs],
                    analysis_count=len(attempts),
                    latest_outcome=attempts[0].outcome if attempts else None,
                )
            )
        return QueryCollection(queries=queries, policy=selection.policy.to_dict())

    def query(self, query_id: str) -> QueryDetail | None:
        query = next(
            (q for q in self.queries().queries if q.query_id == query_id), None
        )
        if query is None:
            return None
        runs = [run for run in self.runs() if query_id in run.query_ids]
        return QueryDetail(
            **query.model_dump(),
            runs=[RunSummary(**r.model_dump()) for r in runs],
            attempts=[
                a for run in runs for a in run.attempts if a.query_id == query_id
            ],
        )

    def tests(self) -> TestCollection:
        tests = list(self.artifacts.tests.values())
        for run in self.runs():
            for attempt in run.attempts:
                status = attempt.stages[-1].status
                tests.append(
                    TestRecord(
                        id=attempt.id,
                        name=f"{attempt.query_id} / {attempt.candidate}",
                        component="LLM-evaluatie" if attempt.model else "Contextopbouw",
                        purpose="Inspectie van proposal, context en onafhankelijke softwarevalidatie.",
                        actual=attempt.raw_verdict,
                        status=status,
                        run_id=run.id,
                        query_id=attempt.query_id,
                        executed_at=run.created_at,
                        origin=run.mode,
                        detail=attempt.detail,
                        attempt=attempt,
                        error_classification=attempt.outcome
                        if status != "passed"
                        else None,
                    )
                )
        for job in self.store.jobs("test"):
            if job["result"]:
                tests.extend(
                    TestRecord.model_validate(t) for t in job["result"]["tests"]
                )
        return TestCollection(
            tests=tests,
            counts=dict(Counter(t.status for t in tests)),
            warnings=self.artifacts.warnings,
        )

    def test(self, test_id: str) -> TestRecord | None:
        return next((test for test in self.tests().tests if test.id == test_id), None)

    def execution(self, job_id: str) -> TestExecution | None:
        job = self.store.job(job_id)
        if job is None or job["kind"] != "test":
            return None
        return TestExecution(
            id=job_id,
            suite=job["config"]["suite"],
            lifecycle=job["status"],
            created_at=job["created_at"],
            completed_at=job["completed_at"],
            error=job["error"],
            tests=job["result"]["tests"] if job["result"] else [],
        )

    def system(self) -> SystemStatus:
        dependencies = {
            name: importlib.util.find_spec(name) is not None
            for name in ("sqlglot", "psycopg", "anthropic")
        }
        database = bool(os.getenv("SUE_DATABASE_URL"))
        from llm.analysis import configuration, AnalysisError

        provider, model_name, error = None, None, None
        try:
            provider, model_name, key = configuration()
            model = bool(key)
        except AnalysisError as exc:
            model, error = False, str(exc)
        sql_ready = (
            self.settings.enable_sql
            and self.settings.test_database_confirmed
            and database
            and dependencies["psycopg"]
        )
        llm_ready = (
            self.settings.enable_llm
            and model
            and (provider == "openrouter" or dependencies["anthropic"])
        )
        missing = []
        if not self.settings.enable_llm:
            missing.append("SUE_ENABLE_LLM=1")
        if not model:
            missing.append(
                "OPENROUTER_API_KEY" if provider == "openrouter" else "providerkey"
            )
        if provider == "anthropic" and not dependencies["anthropic"]:
            missing.append("Anthropic SDK")
        llm_reason = error or (
            "Echte AI-analyse via "
            + str(provider)
            + "; geen database nodig. SQL-validatie is een afzonderlijke stap."
            if llm_ready
            else "AI-analyse nog niet beschikbaar. Vereist: "
            + ", ".join(missing)
            + ". Werk .env bij en herstart de Python-API."
        )
        sql_reason = (
            "Alleen vooraf gedefinieerde cases op de expliciet bevestigde testdatabase; verbinding niet vooraf getest."
            if sql_ready
            else "Vereist SUE_ENABLE_SQL_RUNS=1, SUE_TEST_DATABASE_CONFIRMED=1, server-side databaseconfiguratie en psycopg."
        )
        return SystemStatus(
            provider=provider,
            configured_model=model_name,
            model_status="not_checked" if model else "not_configured",
            configuration_error=error,
            sql_enabled=self.settings.enable_sql,
            test_database_confirmed=self.settings.test_database_confirmed,
            database_configured=database,
            model_configured=model,
            dependencies=dependencies,
            fixtures=len(CASE_MAP),
            historical_runs=len(self.artifacts.runs),
            historical_evaluations=len(self.artifacts.tests),
            run_modes=[
                Capability(
                    id="analysis",
                    label="Live POC · echt AI-advies (zonder database)",
                    available=llm_ready,
                    reason=llm_reason,
                    external_model=True,
                ),
                Capability(
                    id="validate",
                    label="Opgeslagen AI-voorstel valideren",
                    available=sql_ready,
                    reason=sql_reason,
                    executes_sql=True,
                ),
                Capability(
                    id="replay",
                    label="Historische replay",
                    available=bool(self.artifacts.runs),
                    reason="Hergebruikt opgeslagen resultaten; geen database of modelcall.",
                ),
                Capability(
                    id="mock",
                    label="Offline mock",
                    available=True,
                    reason="Nieuwe selectie, mockresponse en statische controle. Geen correctheids- of performancemeting.",
                ),
                Capability(
                    id="live_mock",
                    label="Testdatabase · mockmodel",
                    available=sql_ready,
                    reason=sql_reason,
                    executes_sql=True,
                ),
                Capability(
                    id="live",
                    label="AI + databasevalidatie · experimenteel",
                    available=llm_ready and sql_ready,
                    reason=sql_reason + " " + llm_reason,
                    executes_sql=True,
                    external_model=True,
                ),
            ],
            test_suites=[
                Capability(
                    id="selection",
                    label="Filtering & ranking",
                    available=True,
                    reason="Bestaande offline unittest-suite; geen database of modelcall.",
                ),
                Capability(
                    id="routing",
                    label="Pipeline-routing",
                    available=True,
                    reason="Bestaande CLI-routingtests met vervangen servicegrenzen.",
                ),
                Capability(
                    id="mutations",
                    label="SQL-mutatietests",
                    available=sql_ready,
                    reason=sql_reason,
                    executes_sql=True,
                ),
            ],
            warnings=self.artifacts.warnings,
            limitations=LIMITATIONS,
        )

    def overview(self) -> Overview:
        queries = self.queries().queries
        historical = [
            a
            for r in self.artifacts.runs.values()
            for a in r.attempts
            if a.model not in {None, "mock"}
        ]

        def total(field):
            values = [getattr(a, field) for a in historical]
            return (
                sum(values) if values and all(v is not None for v in values) else None
            )

        metrics = [
            Metric(
                id="queries",
                label="Querypatronen",
                value=len(queries),
                note="Bestaande SQL-cases",
                origin="fixtures",
            ),
            Metric(
                id="selected",
                label="Geselecteerd",
                value=sum(q.selected for q in queries),
                note="Top 2 op fictieve workloadimpact",
                origin="synthetic",
            ),
            Metric(
                id="accepted",
                label="Geaccepteerde voorstellen",
                value=sum(a.outcome == "accepted" for a in historical)
                if historical
                else None,
                note="Binnen historisch geteste voorwaarden",
                origin="historical",
            ),
            Metric(
                id="requests",
                label="Historische modelrequests",
                value=len(historical) if historical else None,
                note=f"Over {len({a.query_id for a in historical})} onafhankelijke querycases",
                origin="historical",
            ),
            Metric(
                id="tokens",
                label="Historische tokens",
                value=total("input_tokens") + total("output_tokens")
                if total("input_tokens") is not None
                and total("output_tokens") is not None
                else None,
                note="Input en output; geen actuele kostenraming",
                origin="historical",
            ),
            Metric(
                id="issues",
                label="Afgewezen / onbeslist",
                value=sum(
                    a.outcome
                    in {"mismatch", "safety_rejected", "inconclusive", "error"}
                    for a in historical
                )
                if historical
                else None,
                note="Technische uitkomsten, geen ontwikkelaarslabels",
                origin="historical",
            ),
        ]
        metrics.extend(
            [
                Metric(
                    id="workload_calls",
                    label="Demo-uitvoeringen",
                    value=sum(q.calls for q in queries)
                    if queries and all(q.calls is not None for q in queries)
                    else None,
                    note="Gesimuleerde workload, geen databaseobservaties",
                    origin="synthetic",
                ),
                Metric(
                    id="workload_total",
                    label="Demo-workloadtijd · ms",
                    value=sum(q.total_execution_time_ms for q in queries)
                    if queries
                    and all(q.total_execution_time_ms is not None for q in queries)
                    else None,
                    note="Totale belasting uit mocktelemetrie",
                    origin="synthetic",
                ),
                Metric(
                    id="new_analyses",
                    label="Nieuwe AI-analyses",
                    value=sum(
                        r.mode == "analysis" and r.lifecycle == "COMPLETED"
                        for r in self.runs()
                    ),
                    note="Nieuw gegenereerd; geen validatiebewijs",
                    origin="current",
                ),
            ]
        )
        conditions = []
        for condition in CONDITIONS:
            rows = [a for a in historical if a.condition == condition]
            conditions.append(
                ConditionStats(
                    condition=condition,
                    requests=len(rows),
                    independent_queries=len({a.query_id for a in rows}),
                    accepted=sum(a.outcome == "accepted" for a in rows),
                    rejected=sum(
                        a.outcome in {"mismatch", "safety_rejected"} for a in rows
                    ),
                    inconclusive=sum(
                        a.outcome in {"inconclusive", "error"} for a in rows
                    ),
                    unchanged=sum(a.unchanged is True for a in rows),
                    input_tokens=sum(a.input_tokens for a in rows)
                    if rows and all(a.input_tokens is not None for a in rows)
                    else None,
                    output_tokens=sum(a.output_tokens for a in rows)
                    if rows and all(a.output_tokens is not None for a in rows)
                    else None,
                )
            )
        return Overview(
            metrics=metrics,
            queries=queries,
            recent_runs=[RunSummary(**r.model_dump()) for r in self.runs()[:5]],
            conditions=conditions,
            warnings=self.artifacts.warnings,
        )
