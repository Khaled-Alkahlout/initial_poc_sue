"""Separate recommendation from opt-in testing of an immutable stored proposal."""

import os
import json
from time import perf_counter

from api.schemas import Attempt, Benchmark, RunDetail, ContextSection
from api.services.artifacts import (
    CASE_MAP,
    LIMITATIONS,
    Artifacts,
    adapt_attempt,
    stage,
    summarize,
)
from api.services.privacy import redact
from llm.analysis import Analysis, AnalysisError, analyze, configuration, unchanged_sql
from api.services.sql_safety import proposal_check
from query_selection.adapters import mock_telemetry
from query_selection.policy import SelectionPolicy
from query_selection.selection import select_queries


def saved_proposal(store, source_id, query_id):
    job = store.job(source_id) if source_id else None
    if (
        not job
        or job["status"] != "COMPLETED"
        or job["config"].get("mode") != "analysis"
    ):
        raise AnalysisError("Kies een afgeronde AI-analyse als validatiebron.")
    run = RunDetail.model_validate(job["result"])
    if (
        run.query_ids != [query_id]
        or not run.attempts
        or not run.attempts[0].proposed_sql
        or run.attempts[0].outcome == "safety_rejected"
    ):
        raise AnalysisError("Geen passend opgeslagen SQL-voorstel voor deze case.")
    return run.attempts[0]


def rewrite_source(store, source_id, query_id):
    job = store.job(source_id) if source_id else None
    if not job or job["status"] not in {"COMPLETED", "FAILED"} or not job.get("result"):
        raise AnalysisError("Kies een opgeslagen analyse of validatie als rewritebron.")
    run = RunDetail.model_validate(job["result"])
    if (
        run.query_ids != [query_id]
        or not run.attempts
        or run.mode not in {"analysis", "validate"}
    ):
        raise AnalysisError("Rewritebron hoort niet bij deze query.")
    return run.attempts[0]


def execute_analysis(job, settings, store):
    config, run_id = job["config"], job["id"]
    case = CASE_MAP[config["query_id"]]
    selection = select_queries(mock_telemetry([case]), SelectionPolicy(top_k=1))
    if not selection.selected:
        raise AnalysisError("Query voldoet niet aan de selectieregels.")
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

    def mark(index, status, note):
        stages[index] = stage(stages[index].id, status, note, "current")
        store.update(run_id, "RUNNING", progress=[s.model_dump() for s in stages])

    mark(0, "passed", "Bestaande filtering en impactranking; gesimuleerde workload.")
    run = RunDetail(
        id=run_id,
        title="AI-analyse · ongetest advies",
        mode=config["mode"],
        lifecycle="COMPLETED",
        created_at=job["created_at"],
        selection=selection.to_dict(),
        limitations=LIMITATIONS,
    )
    if config["mode"] == "validate":
        # Enforce again at service boundary; queued inputs never grant SQL rights.
        if not (
            settings.enable_sql
            and settings.test_database_confirmed
            and config.get("confirm_sql")
        ):
            raise AnalysisError(
                "SQL-validatie uitgeschakeld: beide veiligheidsinstellingen en expliciete bevestiging zijn vereist."
            )
        original = saved_proposal(store, config.get("source_id"), case.name)
        ok, reason = proposal_check(original.proposed_sql)
        if not ok:
            raise AnalysisError("Voorstel afgewezen vóór databaseverbinding: " + reason)
        import psycopg
        from cases.cases import make_ctx
        from cases.classes.candidate import Candidate
        from scripts.run_validation import evaluate

        mark(
            4,
            "running",
            "Opgeslagen voorstel afzonderlijk testen op de bevestigde testdatabase.",
        )
        with psycopg.connect(
            os.environ["SUE_DATABASE_URL"],
            autocommit=True,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=120000",
        ) as connection:
            row = evaluate(
                connection,
                case,
                Candidate(
                    "stored_ai_proposal", original.proposed_sql, "unknown", "llm"
                ),
                make_ctx(connection),
                7,
            )
        attempt = adapt_attempt(
            row, run_id, 0, response={"sql": original.proposed_sql}, origin="measured"
        )
        attempt.analysis, attempt.provider = original.analysis, original.provider
        attempt.model = original.model
        # This run tested a stored proposal; it made zero new model requests.
        attempt.stages[2] = stage(
            "generation",
            "skipped",
            "Opgeslagen voorstel; geen nieuw modelrequest.",
            "current",
        )
        attempt.validation_state = {
            "accepted": "validated_improvement",
            "mismatch": "correctness_failed",
            "not_faster": "performance_regression"
            if attempt.benchmark.speedup is not None and attempt.benchmark.speedup < 1
            else "not_faster",
            "error": "validation_error",
            "safety_rejected": "safety_rejected",
        }.get(attempt.outcome, "inconclusive")
        run.title, run.source_id = (
            "Validatie opgeslagen AI-voorstel",
            config["source_id"],
        )
        run.attempts, run.stages = [attempt], attempt.stages
        result = summarize(run)
        result.model_requests = 0
        return result.model_dump()

    if not settings.enable_llm or not config.get("confirm_external_model"):
        raise AnalysisError(
            "AI-analyse vereist SUE_ENABLE_LLM=1 en expliciete bevestiging."
        )
    mark(1, "running", "Opgeslagen context selecteren; geen live SQL uitvoeren.")
    historical = Artifacts(settings.results_dir)
    match = next(
        (
            a
            for r in sorted(
                historical.runs.values(), key=lambda r: r.created_at, reverse=True
            )
            for a in r.attempts
            if a.query_id == case.name
            and a.condition == config["condition"]
            and a.context
        ),
        None,
    )
    context = match.context if match else []
    blocks = {
        s.id: redact(s.text, literals=True)[:8000]
        for s in context
        if s.text and s.id != "query"
    }
    # Fixture SQL retains literals and parameters; there is no arbitrary SQL upload.
    blocks["query"] = redact(case.original)
    blocks["telemetry"] = {
        k: v
        for k, v in selection.selected[0].to_dict().items()
        if k
        in {
            "calls",
            "mean_execution_time_ms",
            "total_execution_time_ms",
            "is_synthetic",
            "window_id",
        }
    }
    blocks["context_provenance"] = (
        "Historische, mogelijk verouderde context"
        if match
        else "Alleen fixture-SQL; schema, indexen en execution plan ontbreken"
    )
    if config.get("rewrite_only"):
        source = rewrite_source(store, config.get("source_id"), case.name)
        # Reuse the exact redacted context and diagnosis selected by the user.
        blocks = {s.id: s.text for s in source.context if s.text}
        blocks["query"] = redact(case.original)
        blocks["known_bottlenecks"] = (
            source.analysis.root_cause
            if source.analysis
            else "Diagnose niet beschikbaar; evalueer de originele SQL."
        )
        blocks["previous_candidate"] = source.proposed_sql
        blocks["previous_outcome"] = source.validation_state or source.outcome
        blocks.setdefault(
            "telemetry",
            {
                k: v
                for k, v in selection.selected[0].to_dict().items()
                if k
                in {
                    "calls",
                    "mean_execution_time_ms",
                    "total_execution_time_ms",
                    "is_synthetic",
                    "window_id",
                }
            },
        )
        run.title, run.source_id = (
            "Gericht SQL-rewritevoorstel · ongetest",
            config["source_id"],
        )
    context = [
        ContextSection(
            id=key,
            label=key,
            state="redacted",
            text=value if isinstance(value, str) else json.dumps(value),
            note="Exact geredigeerd blok voor dit modelrequest; maximaal 8000 tekens per historisch blok.",
        )
        for key, value in blocks.items()
        if isinstance(value, (str, dict))
    ]
    mark(
        1,
        "warning",
        "Context begrensd tot 8000 tekens per blok, geredigeerd en historisch gelabeld. Geen database aangeroepen.",
    )
    mark(
        2, "running", "Eén extern analyseverzoek; geen automatische generatie-retries."
    )
    started = perf_counter()
    from llm.generation import GenerationSettings

    generation = (
        GenerationSettings.model_validate(config["generation_settings"])
        if "generation_settings" in config
        else store.generation_settings()
    )
    try:
        analysis, metadata = analyze(
            blocks,
            generation=generation,
            **({"focused": True} if config.get("rewrite_only") else {}),
        )
    except AnalysisError as exc:
        mark(2, "error", str(exc))
        mark(3, "skipped", "Geen geldig voorstel; geen SQL-controle of uitvoering.")
        mark(4, "skipped", "Geen correctheidscontrole uitgevoerd.")
        mark(5, "skipped", "Geen benchmark uitgevoerd.")
        mark(
            6, "error", "Analyse mislukt; diagnostiek bewaard. Geen automatische retry."
        )
        provider, model, _ = configuration()
        diagnostics = {
            **exc.diagnostics,
            "model": model,
            "configured_max_output_tokens": generation.max_output_tokens,
            "reasoning_effort": generation.reasoning_effort,
            "rewrite_requested": True,
            "structured_parse_success": False,
            "static_validation_accepted": None,
            "sql_stored_success": False,
            "frontend_sql_displayed": None,
            "model_returned_candidate": exc.diagnostics.get("model_returned_candidate"),
        }
        if exc.partial_text:
            from api.services.diagnostics import preserve_output

            diagnostics["secure_output_preserved"] = preserve_output(
                settings.data_dir, run_id, exc.partial_text
            )
        from api.services.privacy import safe_json

        diagnostics = safe_json(diagnostics)
        attempt = Attempt(
            id=f"{run_id}~0",
            run_id=run_id,
            query_id=case.name,
            candidate="failed_ai_analysis",
            condition=config["condition"],
            model=model,
            provider=provider,
            outcome="error",
            correctness="skipped",
            original_sql=case.original,
            detail=str(exc),
            diagnostics=diagnostics,
            input_tokens=diagnostics.get("input_tokens"),
            output_tokens=diagnostics.get("output_tokens"),
            llm_seconds=diagnostics.get("seconds"),
            stages=stages,
            benchmark=Benchmark(origin="current"),
            origin="current",
            context=context,
            validation_state="rewrite_parsing_failed"
            if exc.diagnostics.get("error_code")
            in {"malformed_json", "schema_validation_failed", "legacy_sql_invalid"}
            else "analysis_failed",
        )
        run.attempts, run.stages = [attempt], stages
        run.lifecycle, run.error = "FAILED", str(exc)
        failed = summarize(run).model_dump()
        store.update(run_id, "FAILED", result=failed, error=str(exc))
        return failed
    # Defense in depth: redact before persistence, including untrusted prose.
    if (
        analysis.optimized_sql
        and redact(analysis.optimized_sql) != analysis.optimized_sql
    ):
        raise AnalysisError(
            "SQL-voorstel bevat gevoelige waarden. Voorstel niet opgeslagen; literals worden niet stilzwijgend gewijzigd."
        )
    analysis = Analysis.model_validate_json(redact(analysis.model_dump_json()))
    mark(
        2,
        "passed",
        "Gestructureerd modelantwoord gevalideerd; nog geen correctheidsbewijs.",
    )
    stages[2].duration_ms = (perf_counter() - started) * 1000
    ok, reason = (
        proposal_check(analysis.optimized_sql)
        if analysis.optimized_sql
        else (
            True,
            "Geen SQL-rewrite voorgesteld; tekst- of indexadvies is alleen ter review.",
        )
    )
    unchanged = bool(
        analysis.optimized_sql and unchanged_sql(case.original, analysis.optimized_sql)
    )
    if unchanged:
        ok, reason = (
            False,
            "UNCHANGED_SQL: Alleen opmaak of commentaar gewijzigd; geen structurele rewrite.",
        )
    # Parser errors can contain SQL fragments; only the classification is public.
    safe_reason = reason.split(":", 1)[0] if not ok else None
    mark(
        3,
        ("passed" if ok else "failed") if analysis.optimized_sql else "skipped",
        reason
        if ok
        else safe_reason + ": SQL-voorstel afgewezen; onafhankelijke review vereist.",
    )
    mark(
        4,
        "skipped",
        "Correctheid niet getest. Start afzonderlijke validatie op een bevestigde testdatabase.",
    )
    mark(5, "skipped", "Geen benchmark uitgevoerd; verwachte baten zijn hypotheses.")
    mark(
        6,
        "warning" if ok else "failed",
        "AI-advies beschikbaar, nog niet gevalideerd."
        if ok
        else "SQL-voorstel afgewezen door statische controle; advies blijft inspecteerbaar.",
    )
    provider, model, _ = configuration()
    attempt = Attempt(
        id=f"{run_id}~0",
        run_id=run_id,
        query_id=case.name,
        candidate="structured_ai_analysis",
        condition=config["condition"],
        model=model,
        provider=provider,
        analysis=analysis,
        diagnostics={
            **metadata.get("diagnostics", {}),
            "rewrite_requested": True,
            "model_returned_candidate": bool(analysis.optimized_sql),
            "structured_parse_success": True,
            "static_validation_accepted": ok if analysis.optimized_sql else None,
            "candidate_rejection_reason": safe_reason,
            "sql_stored_success": None,
            "frontend_sql_displayed": None,
        },
        cost_usd=metadata.get("cost_usd"),
        cost_kind=metadata.get("cost_kind"),
        outcome="inconclusive" if ok else "safety_rejected",
        correctness="skipped",
        original_sql=case.original,
        proposed_sql=analysis.optimized_sql,
        unchanged=unchanged if analysis.optimized_sql else None,
        detail="AI-interpretatie; correctheid en performance niet gemeten.",
        explanation=analysis.problem,
        input_tokens=metadata.get("input_tokens"),
        output_tokens=metadata.get("output_tokens"),
        llm_seconds=metadata["seconds"],
        stages=stages,
        benchmark=Benchmark(origin="current"),
        context=context,
        origin="current",
        validation_state=(
            "no_rewrite_proposed"
            if not analysis.optimized_sql
            else "rewrite_static_rejected"
            if not ok
            else "awaiting_validation"
            if settings.enable_sql and settings.test_database_confirmed
            else "validation_unavailable"
        ),
    )
    run.attempts, run.stages = [attempt], stages
    return summarize(run).model_dump()
