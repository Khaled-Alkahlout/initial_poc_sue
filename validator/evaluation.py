"""One decision for experiment scripts, live runs and stored proposals."""

from cases.cases import make_ctx
from validator.checker import (
    ResultLimitExceeded,
    SqlRejected,
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
    SPEEDUP_THRESHOLD,
    measure,
)


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
    return probes, timing


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

    timing_probe = None
    phase = "context"
    label = None
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
            for label, params in probes:
                baseline = run_query(conn, case.original, params)
                rewrite = run_query(conn, cand.sql, params)
                comparison = compare(baseline, rewrite, case.order_cols)
                checks.append(
                    {
                        "label": label,
                        "status": comparison.status,
                        "detail": comparison.detail,
                        "original_rows": len(baseline.rows),
                        "proposed_rows": len(rewrite.rows),
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
            if max(result.ms for result in timing_probe) >= BENCHMARK_TIMEOUT_MS:
                return finish(
                    "PERFORMANCE_INCONCLUSIVE",
                    "passed",
                    "De vergelijkingsproef overschrijdt het tijdsbudget voor herhaalde metingen.",
                )
            phase = "benchmark"
            if progress:
                progress()
            measured = measure(conn, case.original, cand.sql, timing, reps)
    except (psycopg.Error, ResultLimitExceeded) as exc:
        limited = isinstance(exc, ResultLimitExceeded)
        if limited:
            detail = str(exc)
        else:
            issue = postgres_error(exc, phase)
            row["database_error"] = issue
            detail = MESSAGES[issue["code"]]
            if phase == "context":
                detail = "De parametersets konden niet worden voorbereid. " + detail
        if phase == "benchmark":
            return finish("BENCHMARK_ERROR", "passed", detail, "error")
        if label is not None:
            checks.append(
                {
                    "label": label,
                    "status": "ROW_LIMIT" if limited else "EXEC_ERROR",
                    "detail": detail,
                }
            )
        return finish(
            "VALIDATION_INCONCLUSIVE" if limited else "VALIDATION_ERROR",
            "inconclusive" if limited else "error",
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
            "Gelijke resultaten op alle testsets en minstens 1,2× sneller in de medianen en tussen de kwartielen.",
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
