"""Allowlisted operations composed from the existing Python pipeline."""

from __future__ import annotations

import os
from time import perf_counter

from api.config import Settings
from api.schemas import RunDetail
from api.services.artifacts import (
    Artifacts,
    CASE_MAP,
    LIMITATIONS,
    adapt_attempt,
    stage,
    summarize,
)
from api.services.privacy import redact
from api.services.storage import Store
from llm.client import build_prompt, call_llm, extract_sql
from query_selection.adapters import mock_telemetry, selected_cases
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries


def execute_run(job: dict, settings: Settings, store: Store) -> dict:
    if job["config"]["mode"] in {"analysis", "validate"}:
        from api.services.analysis import execute_analysis

        return execute_analysis(job, settings, store)
    if job["config"]["mode"] in {"live", "live_mock"} and not (
        settings.enable_sql
        and settings.test_database_confirmed
        and job["config"].get("confirm_sql")
    ):
        raise ValueError(
            "SQL-uitvoering vereist beide veiligheidsinstellingen en expliciete bevestiging."
        )
    config, job_id = job["config"], job["id"]
    case = CASE_MAP[config["query_id"]]
    selection = select_queries(mock_telemetry([case]), SelectionPolicy(top_k=1))
    case = selected_cases(selection, [case])[0]
    stages = [
        stage(key, "pending", "Nog niet uitgevoerd.", "current")
        for key in (
            "selection",
            "context",
            "generation",
            "static",
            "correctness",
            "benchmark",
            "result",
        )
    ]

    def mark(key, status, note, duration_ms=None):
        index = next(i for i, value in enumerate(stages) if value.id == key)
        stages[index] = stage(key, status, note, "current", duration_ms)
        store.update(job_id, "RUNNING", progress=[s.model_dump() for s in stages])

    mark(
        "selection",
        "passed",
        "Bestaande query_selection toegepast op expliciet gesimuleerde workloadgegevens.",
    )
    mode, condition = config["mode"], config["condition"]
    run = RunDetail(
        id=job_id,
        title={
            "replay": "Historische replay",
            "mock": "Offline mock",
            "live_mock": "Testdatabase / mockmodel",
            "live": "Live POC",
        }[mode],
        mode=mode,
        lifecycle="COMPLETED",
        created_at=job["created_at"],
        selection=selection.to_dict(),
        limitations=LIMITATIONS,
    )
    if mode == "replay":
        source = Artifacts(settings.results_dir).replay(
            case.name, condition, config.get("source_id")
        )
        if source is None:
            raise ValueError(
                "Geen replay beschikbaar voor deze query en contextconditie."
            )
        historical_run, recorded = source
        attempt = recorded.model_copy(deep=True)
        attempt.id = f"{job_id}~0"
        attempt.run_id = job_id
        attempt.stages[0] = stages[0]
        attempt.stages[1] = stage(
            "context",
            "warning" if recorded.stages[1].status == "passed" else "skipped",
            "Opgeslagen context hergebruikt; niet opnieuw uit de database verzameld."
            if recorded.stages[1].status == "passed"
            else "Geen contextartefact beschikbaar; niet opnieuw opgehaald.",
        )
        attempt.stages[2] = stage(
            "generation",
            "skipped",
            "Historische modelresponse hergebruikt; nul nieuwe modelrequests.",
        )
        run.source_id, run.attempts, run.stages = (
            historical_run.id,
            [attempt],
            attempt.stages,
        )
        return summarize(run).model_dump()

    mark("context", "running", "Context voor de gekozen uitvoering voorbereiden.")
    started = perf_counter()
    connection = None
    try:
        if mode == "mock":
            blocks = {"query": case.original}
        else:
            import psycopg
            from cases.cases import make_ctx
            from llm.context import build_context

            connection = psycopg.connect(
                os.environ["SUE_DATABASE_URL"],
                autocommit=True,
                connect_timeout=5,
                options="-c default_transaction_read_only=on -c statement_timeout=120000",
            )
            ctx = make_ctx(connection)
            blocks = build_context(connection, case, ctx, condition)
        # Only curated fixture SQL is sent as the original; context values are redacted.
        blocks = {
            key: value if key == "query" else redact(value, literals=True)
            for key, value in blocks.items()
        }
        prompt = build_prompt(blocks)
        mark(
            "context",
            "passed",
            "C1 fixturecontext; geen database benaderd."
            if mode == "mock"
            else "Context uit de bevestigde testdatabase; waarden beperkt.",
            (perf_counter() - started) * 1000,
        )
        mark(
            "generation",
            "running",
            "Originele SQL via mockmodel."
            if mode != "live"
            else "Eén expliciet toegestaan extern modelrequest.",
        )
        model = os.environ["SUE_MODEL"] if mode == "live" else "mock"
        response = call_llm(prompt, model, original_sql=case.original)
        sql = extract_sql(response["text"])
        mark(
            "generation",
            "passed",
            "Mockresponse; geen extern request."
            if model == "mock"
            else "Modelresponse ontvangen; geen correctheidsbewijs.",
            response["seconds"] * 1000,
        )
        from api.services.sql_safety import proposal_check

        started = perf_counter()
        ok, reason = proposal_check(sql)
        mark(
            "static",
            "passed" if ok else "failed",
            reason,
            (perf_counter() - started) * 1000,
        )
        if mode == "mock" or not ok:
            row = {
                "case": case.name,
                "candidate": "offline_mock",
                "verdict": "STATIC_ONLY" if ok else "REJECTED_STATIC",
                "param_sets": 0,
                "detail": "Geen SQL uitgevoerd: correctheid en performance zijn niet onderzocht."
                if ok
                else reason,
            }
        else:
            from cases.classes.candidate import Candidate
            from scripts.run_validation import evaluate

            mark(
                "correctness",
                "running",
                "Bestaande evaluate() voert parametercontroles en eventueel benchmarking uit.",
            )
            row = evaluate(
                connection, case, Candidate("dashboard", sql, "unknown", "llm"), ctx, 7
            )
        row.update(
            {
                "model": model,
                "condition": condition,
                "rep": 1,
                "input_tokens": response["input_tokens"],
                "output_tokens": response["output_tokens"],
                "llm_seconds": response["seconds"],
            }
        )
        attempt = adapt_attempt(
            row,
            job_id,
            0,
            response={**response, "sql": sql},
            prompt=prompt,
            origin="current" if mode == "mock" else "measured",
        )
        attempt.stages[:4] = stages[:4]
        if mode == "mock":
            attempt.correctness = "skipped"
            attempt.stages[4] = stage(
                "correctness",
                "skipped",
                "Offline mock: geen database-uitvoering.",
                "current",
            )
            attempt.stages[5] = stage(
                "benchmark", "skipped", "Geen nieuwe performancemeting.", "current"
            )
            attempt.stages[6] = stage(
                "result",
                "inconclusive",
                "Alleen selectie, mockresponse en statische controle uitgevoerd; geen correctheids- of performanceconclusie.",
                "current",
            )
        run.attempts, run.stages = [attempt], attempt.stages
        return summarize(run).model_dump()
    finally:
        if connection is not None:
            connection.close()


def execute_tests(job: dict, settings: Settings) -> dict:
    """No user-provided command, module path or shell argument is accepted."""
    import unittest
    from api.schemas import TestRecord

    suite_id, job_id = job["config"]["suite"], job["id"]
    if suite_id == "mutations":
        import psycopg
        from cases.cases import make_ctx
        from scripts.run_validation import evaluate

        case = CASE_MAP[job["config"]["query_id"]]
        records = []
        with psycopg.connect(
            os.environ["SUE_DATABASE_URL"],
            autocommit=True,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=120000",
        ) as conn:
            ctx = make_ctx(conn)
            for index, candidate in enumerate(case.candidates):
                started = perf_counter()
                row = evaluate(conn, case, candidate, ctx, 7)
                attempt = adapt_attempt(
                    row, job_id, index, handwritten=True, origin="measured"
                )
                if attempt.correctness in {"error", "inconclusive"}:
                    status = attempt.correctness
                else:
                    rejected = attempt.outcome in {"mismatch", "safety_rejected"}
                    status = (
                        "passed"
                        if rejected == (candidate.expected == "not_equivalent")
                        else "failed"
                    )
                records.append(
                    TestRecord(
                        id=f"{job_id}~{index}",
                        name=f"{case.name} / {candidate.name}",
                        component="SQL-validator",
                        purpose="Nieuwe mutatietest op de bevestigde testdatabase.",
                        expected=candidate.expected,
                        actual=row["verdict"],
                        status=status,
                        duration_ms=(perf_counter() - started) * 1000,
                        executed_at=job["created_at"],
                        query_id=case.name,
                        origin="measured",
                        detail=attempt.detail,
                        attempt=attempt,
                    )
                )
        return {"tests": [r.model_dump() for r in records]}

    patterns = {
        "selection": "test_query_selection.py",
        "routing": "test_run_llm_selection.py",
    }
    suite = unittest.defaultTestLoader.discover(
        str(settings.root / "tests"), pattern=patterns[suite_id]
    )
    if suite.countTestCases() == 0:
        raise ValueError(
            "Geen tests gevonden voor deze vaste suite; niet als geslaagd behandeld."
        )

    class Recorder(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.records = []
            self.started = {}

        def startTest(self, test):
            super().startTest(test)
            self.started[test.id()] = perf_counter()

        def record(self, test, status, detail=""):
            self.records.append(
                TestRecord(
                    id=f"{job_id}~{len(self.records)}",
                    name=test.id().split(".")[-1],
                    component="Queryselectie"
                    if suite_id == "selection"
                    else "Pipeline-routing",
                    purpose=test.shortDescription()
                    or "Bestaande offline unittest-asserties uitvoeren.",
                    expected="unittest-asserties slagen",
                    actual=status,
                    status=status,
                    duration_ms=(perf_counter() - self.started[test.id()]) * 1000
                    if test.id() in self.started
                    else None,
                    executed_at=job["created_at"],
                    origin="current",
                    detail=redact(detail)[:6000],
                    metadata={"unittest_id": test.id(), "suite": suite_id},
                )
            )

        def addSuccess(self, test):
            super().addSuccess(test)
            self.record(test, "passed")

        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.record(test, "failed", self._exc_info_to_string(err, test))

        def addError(self, test, err):
            super().addError(test, err)
            self.record(test, "error", self._exc_info_to_string(err, test))

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            self.record(test, "skipped", reason)

        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err is not None:
                self.record(subtest, "failed", self._exc_info_to_string(err, test))

    recorder = Recorder()
    suite.run(recorder)
    return {"tests": [record.model_dump() for record in recorder.records]}
