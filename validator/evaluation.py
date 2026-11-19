"""One decision for experiment scripts, live runs and stored proposals."""

from cases.cases import make_ctx
from time import perf_counter
from validator.checker import (
    ResultLimitExceeded,
    SqlRejected,
    STATEMENT_TIMEOUT_MS,
    check_rewrite,
    compare,
    inspect_sql,
    read_snapshot,
    require_tables,
    run_query,
)
from validator.postgres_errors import MESSAGES, postgres_error
from validator.timing import (
    BENCHMARK_TIMEOUT_MS,
    DEFAULT_REPETITIONS,
    MAX_REPETITIONS,
    SPEEDUP_THRESHOLD,
    measure,
)

MAX_CORRECTNESS_CHECKS = 3


def parameter_sets(case, ctx, names):
    probes = list(case.params(ctx))
    timing = case.timing_params(ctx)
    if not probes:
        raise ValueError("Geen parametersets beschikbaar.")
    if not any(params == timing for _, params in probes):
        probes.append(("benchmark", timing))
    if (
        len(probes) > 12
        or len({label for label, _ in probes}) != len(probes)
        or any(set(params) != names for _, params in probes)
    ):
        raise ValueError(
            "Het parameterprofiel vereist maximaal twaalf unieke sets met de juiste bindingsnamen."
        )
    selected = probes[:MAX_CORRECTNESS_CHECKS]
    if not any(params == timing for _, params in selected):
        selected[-1] = next(probe for probe in probes if probe[1] == timing)
    return selected, timing


def evaluate(
    conn,
    case,
    cand,
    ctx=None,
    reps=DEFAULT_REPETITIONS,
    *,
    progress=None,
    benchmark=True,
    recent_order_limit=None,
    correctness_timeout_ms=STATEMENT_TIMEOUT_MS,
    benchmark_timeout_ms=BENCHMARK_TIMEOUT_MS,
):
    """Use one read-only snapshot and benchmark only after complete comparison."""
    import psycopg

    checks = []
    row = {
        "case": case.name,
        "candidate": cand.name,
        "expected": cand.expected,
        "fault": cand.fault,
    }

    def finish(verdict, correctness, detail, benchmark_status="skipped", **timing):
        if "recent_order_limit" in row:
            detail += f" De tijdvensters zijn afgeleid uit maximaal {recent_order_limit} recente orders."
        return {
            **row,
            **timing,
            "verdict": verdict,
            "correctness_status": correctness,
            "benchmark_status": benchmark_status,
            "param_sets": len(checks),
            "failing_param_sets": sum(
                check["status"] != "EQUIVALENT" for check in checks
            ),
            "flagged_not_equivalent": verdict
            in {"REJECTED_STATIC", "REJECTED_NOT_EQUIVALENT"},
            "detail": detail,
            "parameter_checks": checks,
        }

    try:
        original = inspect_sql(case.original)
        candidate = check_rewrite(original, cand.sql)
    except SqlRejected as exc:
        return finish("REJECTED_STATIC", "skipped", str(exc))

    if not 1 <= reps <= 12:
        raise ValueError("Kies één tot twaalf benchmarkparen.")
    reps = min(reps, MAX_REPETITIONS)

    timing_probe = None
    phase = "context"
    label = None
    query_label = None
    check_started = None
    query_started = None
    baseline = None
    rewrite = None
    try:
        with read_snapshot(conn):
            try:
                require_tables(
                    conn, original.tables | ({"orders"} if ctx is None else set())
                )
                if ctx is None:
                    ctx = make_ctx(conn, recent_order_limit=recent_order_limit)
                    if recent_order_limit is not None:
                        row["recent_order_limit"] = recent_order_limit
                probes, timing = parameter_sets(case, ctx, original.parameters)
            except ValueError as exc:
                return finish("VALIDATION_INCONCLUSIVE", "inconclusive", str(exc))
            phase = "correctness"
            if correctness_timeout_ms != STATEMENT_TIMEOUT_MS:
                conn.execute(
                    f"SET LOCAL statement_timeout = {int(correctness_timeout_ms)}"
                )
            for label, params in probes:
                check_started = query_started = perf_counter()
                baseline = rewrite = None
                query_label = "oorspronkelijke query"
                baseline = run_query(conn, case.original, params)
                query_label = "kandidaatquery"
                query_started = perf_counter()
                rewrite = run_query(conn, cand.sql, params)
                comparison = compare(baseline, rewrite, case.order_cols)
                checks.append(
                    {
                        "label": label,
                        "status": comparison.status,
                        "detail": comparison.detail,
                        "original_rows": len(baseline.rows),
                        "proposed_rows": len(rewrite.rows),
                        "original_ms": baseline.ms,
                        "proposed_ms": rewrite.ms,
                        "duration_ms": (perf_counter() - check_started) * 1000,
                    }
                )
                if params == timing:
                    timing_probe = baseline, rewrite
            if any(
                check["status"]
                in {
                    "COLUMN_MISMATCH",
                    "ROWCOUNT_MISMATCH",
                    "VALUE_MISMATCH",
                    "ORDER_MISMATCH",
                }
                for check in checks
            ):
                return finish(
                    "REJECTED_NOT_EQUIVALENT",
                    "failed",
                    "Minstens één parameterset geeft een resultaatverschil.",
                )
            if not all(check["status"] == "EQUIVALENT" for check in checks):
                return finish(
                    "VALIDATION_INCONCLUSIVE",
                    "inconclusive",
                    "De vereiste sorteervolgorde kon niet worden gecontroleerd.",
                )
            if not any(check["original_rows"] for check in checks):
                return finish(
                    "VALIDATION_INCONCLUSIVE",
                    "inconclusive",
                    "Alle parametersets leverden lege resultaten op.",
                )
            if not benchmark:
                return finish(
                    "CORRECTNESS_ONLY",
                    "passed",
                    "Resultaten komen overeen op de geteste parametersets.",
                )
            if timing_probe is None or not timing_probe[0].rows:
                return finish(
                    "PERFORMANCE_INCONCLUSIVE",
                    "passed",
                    "De benchmarkparameters leveren geen resultaatrijen op.",
                )
            if max(result.ms for result in timing_probe) >= benchmark_timeout_ms:
                return finish(
                    "PERFORMANCE_INCONCLUSIVE",
                    "passed",
                    "De vergelijkingsproef op de benchmarkparameters bereikte de "
                    f"grens van {benchmark_timeout_ms} ms voor herhaalde metingen.",
                )
            phase = "benchmark"
            if progress:
                progress()
            row["benchmark_measurements"] = []
            measured = measure(
                conn,
                case.original,
                cand.sql,
                timing,
                reps,
                timeout_ms=benchmark_timeout_ms,
                measurements=row["benchmark_measurements"],
            )
    except (psycopg.Error, ResultLimitExceeded) as exc:
        limited = isinstance(exc, ResultLimitExceeded)
        timed_out = False
        if limited:
            detail = str(exc)
            status = "ROW_LIMIT"
        else:
            issue = postgres_error(exc, phase)
            row["database_error"] = issue
            detail = MESSAGES[issue["code"]]
            timed_out = phase == "correctness" and issue["code"] == "statement_timeout"
            status = "STATEMENT_TIMEOUT" if timed_out else "EXEC_ERROR"
            if phase == "context":
                detail = "De parametersets konden niet worden voorbereid. " + detail
        if phase == "benchmark":
            return finish("BENCHMARK_ERROR", "passed", detail, "error")
        if label is not None:
            if timed_out:
                detail = (
                    f"De {query_label} bereikte bij {label} de statement-time-out "
                    f"van {correctness_timeout_ms / 1000:g} s."
                )
            else:
                detail = f"De {query_label} stopte bij {label}. {detail}"
            checks.append(
                {
                    "label": label,
                    "status": status,
                    "detail": detail,
                    "original_rows": len(baseline.rows)
                    if baseline is not None
                    else None,
                    "proposed_rows": len(rewrite.rows) if rewrite is not None else None,
                    "original_ms": baseline.ms
                    if baseline is not None
                    else (perf_counter() - query_started) * 1000,
                    "proposed_ms": (perf_counter() - query_started) * 1000
                    if baseline is not None
                    else None,
                    "duration_ms": (perf_counter() - check_started) * 1000,
                }
            )
        return finish(
            "VALIDATION_INCONCLUSIVE" if limited or timed_out else "VALIDATION_ERROR",
            "inconclusive" if limited or timed_out else "error",
            detail,
        )

    if candidate.canonical == original.canonical:
        return finish(
            "EQUIVALENT_NOT_FASTER",
            "passed",
            "A/A-meting op dezelfde SQL; geen herschrijving om te accepteren.",
            "warning",
            **measured,
        )
    if measured["faster"]:
        return finish(
            "ACCEPTED",
            "passed",
            "Gelijke resultaten op de geselecteerde parametersets en minstens 1,2× sneller in de medianen en tussen de kwartielen.",
            "passed",
            **measured,
        )
    if measured["speedup"] is None or measured["speedup"] >= SPEEDUP_THRESHOLD:
        return finish(
            "PERFORMANCE_INCONCLUSIVE",
            "passed",
            "De metingen geven onvoldoende stabiel bewijs voor de snelheidsdrempel.",
            "warning",
            **measured,
        )
    return finish(
        "EQUIVALENT_NOT_FASTER",
        "passed",
        "De vereiste snelheidsdrempel van 1,2× is niet gehaald.",
        "warning",
        **measured,
    )
