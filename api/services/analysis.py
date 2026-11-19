"""One dashboard workflow for generation, live evaluation and stored proposals."""

import json

from api.config import (
    DASHBOARD_BENCHMARK_TIMEOUTS_MS,
    DASHBOARD_CORRECTNESS_TIMEOUT_MS,
    LIVE_PROFILE_ORDERS,
    SQL_RUN_MODES,
)
from api.schemas import Attempt, Benchmark, ContextSection, RunDetail
from api.services.artifacts import (
    CASE_MAP,
    LIMITATIONS,
    RUN_STAGES,
    adapt_attempt,
    stage,
    summarize,
)
from api.services.database import (
    TestDatabaseError,
    check_case_database,
    connect_test_database,
    require_confirmation,
    validation_blocker,
)
from api.services.privacy import redact, safe_json
from api.services.sql_safety import proposal_check
from cases.classes.candidate import Candidate
from llm.analysis import (
    Analysis,
    AnalysisError,
    analyze,
    model_configuration,
    unchanged_sql,
)
from llm.context import build_context
from llm.client import SYSTEM, build_prompt
from llm.generation import GenerationSettings
from query_selection.adapters import mock_telemetry
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries
from validator.checker import SqlRejected, inspect_sql
from validator.evaluation import evaluate
from validator.timing import BENCHMARK_TIMEOUT_MS

TITLES = {
    "analysis": "SQL-analyse",
    "live": "SQL-analyse met validatie",
    "validate": "Validatie opgeslagen AI-voorstel",
    "mock": "Offline mock",
    "live_mock": "Testdatabase · mockmodel",
}
MOCK_MODES = {"mock", "live_mock"}
CONTEXT_LABELS = {
    "query": "Originele SQL",
    "schema": "Schema en indexen",
    "plan": "Geschat queryplan",
    "stats": "Statistieken",
    "telemetry": "Gesimuleerde workload",
    "context_provenance": "Herkomst van de context",
    "known_bottlenecks": "Eerdere diagnose",
    "previous_candidate": "Eerder voorstel",
    "previous_outcome": "Eerdere uitkomst",
}


def saved_proposal(store, source_id, query_id):
    job = store.job(source_id) if source_id else None
    if (
        not job
        or job["status"] not in {"COMPLETED", "FAILED"}
        or job["config"].get("mode") not in {"analysis", "live"}
        or not job.get("result")
    ):
        raise AnalysisError("Kies een opgeslagen AI-voorstel als validatiebron.")
    run = RunDetail.model_validate(job["result"])
    if (
        run.query_ids != [query_id]
        or not run.attempts
        or not run.attempts[0].proposed_sql
        or run.attempts[0].outcome == "safety_rejected"
    ):
        raise AnalysisError("Geen passend opgeslagen SQL-voorstel voor deze case.")
    source = run.attempts[0]
    if not source.original_sql or not unchanged_sql(
        CASE_MAP[query_id].original, source.original_sql
    ):
        raise AnalysisError(
            "De oorspronkelijke SQL van dit voorstel komt niet overeen met de huidige casus."
        )
    return source


def rewrite_source(store, source_id, query_id):
    job = store.job(source_id) if source_id else None
    if not job or job["status"] not in {"COMPLETED", "FAILED"} or not job.get("result"):
        raise AnalysisError("Kies een opgeslagen analyse of validatie als rewritebron.")
    run = RunDetail.model_validate(job["result"])
    if (
        run.query_ids != [query_id]
        or not run.attempts
        or run.mode not in {"analysis", "live", "validate"}
    ):
        raise AnalysisError("Rewritebron hoort niet bij deze query.")
    return run.attempts[0]


def uses_test_database_context(config):
    return config.get("condition", "C1_query") != "C1_query" and config["mode"] in {
        "analysis",
        "live",
        "live_mock",
    }


def model_context(config, case, original, decision, source):
    blocks = {"query": case.original}
    live_context = uses_test_database_context(config)
    if config["mode"] == "live" or live_context:
        with connect_test_database() as connection:
            check_case_database(connection, original.tables)
            if live_context:
                blocks = build_context(
                    connection,
                    case,
                    None,
                    config["condition"],
                    recent_order_limit=LIVE_PROFILE_ORDERS,
                )
    blocks = {
        key: redact(value, literals=key != "query") for key, value in blocks.items()
    }
    if source:
        blocks["known_bottlenecks"] = redact(
            source.analysis.root_cause
            if source.analysis
            else "Diagnose niet beschikbaar.",
            literals=True,
        )
        if source.proposed_sql:
            blocks["previous_candidate"] = redact(source.proposed_sql, literals=True)
        blocks["previous_outcome"] = source.validation_state or source.outcome
    blocks["telemetry"] = {
        key: value
        for key, value in decision.to_dict().items()
        if key
        in {
            "calls",
            "mean_execution_time_ms",
            "total_execution_time_ms",
            "is_synthetic",
            "window_id",
        }
    }
    blocks["context_provenance"] = (
        "Begrensde metadata uit de bevestigde testdatabase. Het geschatte plan bevat geen uitvoeringsmetingen."
        if live_context
        else "SQL uit het casusregister en gesimuleerde workload."
    )
    return blocks, config["condition"] if live_context else "C1_query"


def generate(attempt, blocks, generation, settings):
    """Populate the existing result contract and keep provider failures inspectable."""
    try:
        attempt.provider, attempt.model, _ = model_configuration(generation)
        if attempt.provider != "openrouter":
            raise AnalysisError("Gestructureerde dashboardanalyse vereist OpenRouter.")
        attempt.system_prompt = SYSTEM
        attempt.user_prompt = build_prompt(blocks)
        analysis, metadata = analyze(blocks, generation=generation)
        if (
            analysis.optimized_sql
            and redact(analysis.optimized_sql) != analysis.optimized_sql
        ):
            raise AnalysisError(
                "SQL-voorstel bevat gevoelige waarden en is niet opgeslagen.",
                {**metadata.get("diagnostics", {}), "error_code": "sensitive_sql"},
            )
        values = analysis.model_dump()
        for key, value in values.items():
            if key == "optimized_sql":
                continue
            if isinstance(value, str):
                values[key] = redact(value)
            elif isinstance(value, list):
                values[key] = [redact(item) for item in value]
        attempt.analysis = Analysis.model_validate(values)
        attempt.explanation = attempt.analysis.problem
        attempt.proposed_sql = attempt.analysis.optimized_sql
        if attempt.proposed_sql:
            attempt.proposal_source = "model"
        attempt.input_tokens = metadata.get("input_tokens")
        attempt.output_tokens = metadata.get("output_tokens")
        attempt.llm_seconds = metadata.get("seconds")
        attempt.cost_usd = metadata.get("cost_usd")
        attempt.cost_kind = metadata.get("cost_kind")
        attempt.diagnostics = {
            **safe_json(metadata.get("diagnostics", {})),
            "rewrite_requested": True,
            "model_returned_candidate": bool(attempt.proposed_sql),
            "structured_parse_success": True,
            "static_validation_accepted": None,
            "sql_stored_success": None,
            "frontend_sql_displayed": None,
        }
    except AnalysisError as exc:
        diagnostics = {
            "configured_max_output_tokens": generation.max_output_tokens,
            "reasoning_effort": generation.reasoning_effort,
            "model": attempt.model,
            "model_returned_candidate": None,
            **exc.diagnostics,
            "rewrite_requested": True,
            "structured_parse_success": exc.diagnostics.get(
                "structured_parse_success", False
            ),
            "static_validation_accepted": None,
            "sql_stored_success": False,
            "frontend_sql_displayed": None,
        }
        if exc.partial_text:
            from api.services.diagnostics import preserve_output

            diagnostics["secure_output_preserved"] = preserve_output(
                settings.data_dir, attempt.run_id, exc.partial_text
            )
        attempt.diagnostics = safe_json(diagnostics)
        attempt.input_tokens = diagnostics.get("input_tokens")
        attempt.output_tokens = diagnostics.get("output_tokens")
        attempt.llm_seconds = diagnostics.get("seconds")
        attempt.outcome, attempt.detail = "error", str(exc)
        attempt.validation_state = (
            "rewrite_parsing_failed"
            if exc.diagnostics.get("error_code")
            in {"malformed_json", "schema_validation_failed", "response_too_large"}
            else "analysis_failed"
        )


def validate(attempt, case, mark):
    mark(
        "correctness",
        "running",
        "Dezelfde parameters en PostgreSQL-snapshot voor origineel en voorstel.",
    )

    def benchmark_started():
        mark("correctness", "passed", "Alle geselecteerde parametersets komen overeen.")
        mark(
            "benchmark",
            "running",
            "Uitvoeringstijden per paar meten met afwisselende startvolgorde.",
        )

    try:
        with connect_test_database(phase="correctness") as connection:
            row = evaluate(
                connection,
                case,
                Candidate(attempt.candidate, attempt.proposed_sql, "unknown", "llm"),
                progress=benchmark_started,
                recent_order_limit=LIVE_PROFILE_ORDERS,
                correctness_timeout_ms=DASHBOARD_CORRECTNESS_TIMEOUT_MS,
                benchmark_timeout_ms=DASHBOARD_BENCHMARK_TIMEOUTS_MS.get(
                    case.name, BENCHMARK_TIMEOUT_MS
                ),
            )
    except TestDatabaseError as exc:
        attempt.outcome, attempt.correctness = "error", "error"
        attempt.validation_state, attempt.detail = "validation_error", str(exc)
        if exc.issue:
            attempt.raw_record["database_error"] = exc.issue
        mark("correctness", "error", attempt.detail)
        return

    evidence = adapt_attempt(row, attempt.run_id, 0, origin="measured")
    if "database_error" in row:
        attempt.raw_record["database_error"] = row["database_error"]
    attempt.raw_verdict = evidence.raw_verdict
    attempt.outcome, attempt.correctness = evidence.outcome, evidence.correctness
    attempt.benchmark = evidence.benchmark
    attempt.detail = evidence.detail
    attempt.parameter_sets = evidence.parameter_sets
    attempt.failing_parameter_sets = evidence.failing_parameter_sets
    attempt.parameter_checks = evidence.parameter_checks
    if attempt.parameter_sets:
        attempt.origin = "measured"
    attempt.validation_state = {
        "accepted": "validated_improvement",
        "mismatch": "correctness_failed",
        "not_faster": "performance_regression"
        if evidence.benchmark.speedup is not None and evidence.benchmark.speedup < 1
        else "not_faster",
        "error": "validation_error",
        "safety_rejected": "safety_rejected",
    }.get(attempt.outcome, "inconclusive")
    mark(
        "correctness",
        attempt.correctness,
        "Gelijke resultaatkolommen, waarden en vereiste volgorde op de geteste parametersets."
        if attempt.correctness == "passed"
        else attempt.detail,
    )
    mark("benchmark", attempt.benchmark.status, attempt.detail)


def execute_analysis(job, settings, store):
    config, run_id = job["config"], job["id"]
    mode = config["mode"]
    if mode in SQL_RUN_MODES or uses_test_database_context(config):
        try:
            require_confirmation(settings, config.get("confirm_sql", False))
        except TestDatabaseError as exc:
            raise AnalysisError(str(exc)) from None
    if (
        mode != "validate"
        and mode not in MOCK_MODES
        and not (settings.enable_llm and config.get("confirm_external_model"))
    ):
        raise AnalysisError(
            "AI-analyse vereist SUE_ENABLE_LLM=1 en expliciete bevestiging."
        )
    case = CASE_MAP[config["query_id"]]
    selection = select_queries(mock_telemetry([case]), SelectionPolicy(top_k=1))
    stages = {
        key: stage(key, "pending", "Nog niet uitgevoerd.", "current")
        for key in RUN_STAGES
    }

    def mark(key, status, note, duration_ms=None):
        stages[key] = stage(key, status, note, "current", duration_ms)
        store.update(
            run_id, "RUNNING", progress=[item.model_dump() for item in stages.values()]
        )

    attempt = Attempt(
        id=f"{run_id}~0",
        run_id=run_id,
        query_id=case.name,
        condition=config.get("condition", "C1_query"),
        candidate="offline_mock" if mode in MOCK_MODES else "structured_ai_analysis",
        outcome="inconclusive",
        correctness="skipped",
        detail="",
        original_sql=case.original,
        origin="current",
        stages=[],
        benchmark=Benchmark(origin="current"),
    )
    run = RunDetail(
        id=run_id,
        title=TITLES[mode],
        mode=mode,
        lifecycle="COMPLETED",
        created_at=job["created_at"],
        selection=selection.to_dict(),
        limitations=LIMITATIONS,
        source_id=config.get("source_id"),
    )

    def finish():
        status = {
            "accepted": "passed",
            "not_faster": "warning",
            "mismatch": "failed",
            "safety_rejected": "failed",
            "error": "error",
        }.get(attempt.outcome, "inconclusive")
        for key, item in stages.items():
            if item.status == "pending":
                note = (
                    attempt.detail
                    if key in {"static", "correctness", "benchmark"}
                    else "Fase niet uitgevoerd."
                )
                stages[key] = stage(key, "skipped", note, "current")
        stages["result"] = stage("result", status, attempt.detail, "current")
        attempt.stages = list(stages.values())
        run.attempts, run.stages = [attempt], attempt.stages
        if attempt.outcome == "error":
            run.lifecycle, run.error = "FAILED", attempt.detail
        summarize(run)
        if mode == "validate":
            run.model_requests = 0
        result = run.model_dump()
        if run.lifecycle == "FAILED":
            store.update(run_id, "FAILED", result=result, error=run.error)
        return result

    mark(
        "selection",
        "passed",
        "Casus uit het queryregister; workloadimpact is gesimuleerd.",
    )
    try:
        original = inspect_sql(case.original)
    except SqlRejected as exc:
        mark("input_check", "failed", str(exc))
        attempt.outcome, attempt.detail = "safety_rejected", str(exc)
        attempt.validation_state = "safety_rejected"
        return finish()
    mark(
        "input_check",
        "passed",
        "Originele SELECT, tabellen, functies en bindingsvorm gecontroleerd.",
    )

    if mode == "validate":
        source = saved_proposal(store, config.get("source_id"), case.name)
        attempt.candidate = (
            source.candidate
            if source.proposal_source == "case"
            else "stored_ai_proposal"
        )
        attempt.proposed_sql, attempt.analysis = source.proposed_sql, source.analysis
        attempt.proposal_source = source.proposal_source
        attempt.condition, attempt.model, attempt.provider = (
            source.condition,
            source.model,
            source.provider,
        )
        mark("generation", "skipped", "Opgeslagen voorstel hergebruikt.")
    else:
        source = (
            rewrite_source(store, config.get("source_id"), case.name)
            if config.get("rewrite_only", False)
            else None
        )
        mark(
            "context",
            "running",
            "Verbinding en toegang tot de casustabellen controleren."
            if mode == "live" or uses_test_database_context(config)
            else "Context voor de gekozen casus voorbereiden.",
        )
        try:
            blocks, attempt.condition = model_context(
                config, case, original, selection.decisions[0], source
            )
        except (TestDatabaseError, ValueError) as exc:
            attempt.outcome, attempt.detail = "error", str(exc)
            if isinstance(exc, TestDatabaseError) and exc.issue:
                attempt.raw_record["database_error"] = exc.issue
            mark("context", "error", attempt.detail)
            return finish()
        attempt.context = [
            ContextSection(
                id=key,
                label=CONTEXT_LABELS.get(key, key),
                state="truncated"
                if isinstance(value, str) and value.endswith("(afgekapt)")
                else "redacted",
                text=value if isinstance(value, str) else json.dumps(value),
                note="Blok dat voor generatie is voorbereid.",
            )
            for key, value in blocks.items()
        ]
        note = blocks["context_provenance"]
        if mode == "live":
            note = "Verbinding en toegang tot de casustabellen gecontroleerd. " + note
        mark("context", "passed", note)

        if mode in MOCK_MODES:
            attempt.model, attempt.proposed_sql = "mock", case.original
            mark(
                "generation",
                "skipped",
                "Expliciete demo met een kopie van de oorspronkelijke SQL.",
            )
        else:
            generation = (
                GenerationSettings.model_validate(config["generation_settings"])
                if "generation_settings" in config
                else store.generation_settings()
            )
            mark(
                "generation",
                "running",
                "Gestructureerde analyse en één rewriteverzoek via OpenRouter.",
            )
            generate(attempt, blocks, generation, settings)
            if attempt.outcome == "error":
                mark("generation", "error", attempt.detail)
                return finish()
            mark(
                "generation",
                "passed",
                "Gestructureerd antwoord, met uitleg over de rewritebeslissing."
                if attempt.proposed_sql
                else "AI-analyse ontvangen. Het model gaf geen SQL-voorstel.",
                attempt.llm_seconds * 1000 if attempt.llm_seconds is not None else None,
            )

    if mode == "live" and attempt.analysis is not None and not attempt.proposed_sql:
        # The completed AI analysis remains unchanged. A registered candidate
        # goes through the same admission and database evaluation as model SQL.
        reference = next(
            (
                candidate
                for candidate in case.candidates
                if candidate.expected == "equivalent"
            ),
            None,
        )
        if reference is not None:
            attempt.candidate = reference.name
            attempt.proposed_sql = reference.sql.strip()
            attempt.proposal_source = "case"

    if not attempt.proposed_sql:
        attempt.validation_state = "no_rewrite_proposed"
        attempt.detail = "De analyse heeft geen SQL-voorstel opgeleverd."
        return finish()

    ok, reason = proposal_check(attempt.proposed_sql, original)
    attempt.unchanged = ok and unchanged_sql(case.original, attempt.proposed_sql)
    if attempt.unchanged and mode not in MOCK_MODES:
        ok, reason = (
            False,
            "UNCHANGED_SQL: De oorspronkelijke SQL is inhoudelijk ongewijzigd.",
        )
    if attempt.diagnostics and attempt.proposal_source != "case":
        attempt.diagnostics["static_validation_accepted"] = ok
        attempt.diagnostics["candidate_rejection_reason"] = (
            None if ok else reason.split(":", 1)[0]
        )
    static_note = (
        f"Variant {attempt.candidate} uit het casusregister. {reason}"
        if attempt.proposal_source == "case"
        else reason
    )
    mark("static", "passed" if ok else "failed", static_note)
    if not ok:
        attempt.outcome, attempt.detail = "safety_rejected", reason
        attempt.raw_verdict = "REJECTED_STATIC"
        attempt.validation_state = "rewrite_static_rejected"
    elif mode in SQL_RUN_MODES:
        validate(attempt, case, mark)
    elif mode == "mock":
        attempt.detail = "Offline demo. Alleen softwarechecks uitgevoerd."
        attempt.raw_verdict = "STATIC_ONLY"
    else:
        blocker = validation_blocker(settings)
        attempt.detail = "Deze run geeft AI-advies. " + (
            blocker
            or "Start Correctheid & performance testen om dit voorstel te valideren."
        )
        attempt.validation_state = (
            "validation_unavailable" if blocker else "awaiting_validation"
        )
    return finish()
