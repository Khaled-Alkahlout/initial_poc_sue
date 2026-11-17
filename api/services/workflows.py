"""Allowlisted orchestration and historical replay."""

from __future__ import annotations

from time import perf_counter

from api.config import LIVE_PROFILE_ORDERS, Settings
from api.schemas import RunDetail
from api.services.analysis import execute_analysis
from api.services.artifacts import (
    Artifacts,
    CASE_MAP,
    LIMITATIONS,
    adapt_attempt,
    stage,
    summarize,
)
from api.services.database import connect_test_database, require_confirmation
from api.services.privacy import redact
from api.services.storage import Store
from query_selection.adapters import mock_telemetry
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries
from validator.evaluation import evaluate


def execute_run(job: dict, settings: Settings, store: Store) -> dict:
    config, job_id = job["config"], job["id"]
    if config["mode"] != "replay":
        return execute_analysis(job, settings, store)

    case = CASE_MAP[config["query_id"]]
    selection = select_queries(mock_telemetry([case]), SelectionPolicy(top_k=1))
    source = Artifacts(settings.results_dir).replay(
        case.name, config["condition"], config.get("source_id")
    )
    if source is None:
        raise ValueError("Geen replay beschikbaar voor deze query en contextconditie.")
    historical_run, recorded = source
    attempt = recorded.model_copy(
        deep=True, update={"id": f"{job_id}~0", "run_id": job_id}
    )
    attempt.stages[0] = stage(
        "selection",
        "passed",
        "Bestaande casus geselecteerd; workloadcijfers zijn gesimuleerd.",
        "current",
    )
    attempt.stages[1] = stage(
        "context",
        "warning" if recorded.stages[1].status == "passed" else "skipped",
        "Historische context uit het opgeslagen artefact.",
    )
    attempt.stages[2] = stage(
        "generation",
        "skipped",
        "Historische modelresponse hergebruikt; nul nieuwe modelrequests.",
    )
    run = RunDetail(
        id=job_id,
        title="Historische replay",
        mode="replay",
        lifecycle="COMPLETED",
        created_at=job["created_at"],
        selection=selection.to_dict(),
        limitations=LIMITATIONS,
        source_id=historical_run.id,
        attempts=[attempt],
        stages=attempt.stages,
    )
    return summarize(run).model_dump()


def execute_tests(job: dict, settings: Settings) -> dict:
    """No user-provided command, module path or shell argument is accepted."""
    import unittest
    from api.schemas import TestRecord

    suite_id, job_id = job["config"]["suite"], job["id"]
    if suite_id == "mutations":
        require_confirmation(settings, job["config"].get("confirm_sql", False))
        case = CASE_MAP[job["config"]["query_id"]]
        records = []
        with connect_test_database() as conn:
            for index, candidate in enumerate(case.candidates):
                started = perf_counter()
                row = evaluate(
                    conn,
                    case,
                    candidate,
                    benchmark=False,
                    recent_order_limit=LIVE_PROFILE_ORDERS,
                )
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
