"""Paired measurements in the correctness snapshot."""

from statistics import median, quantiles
from time import perf_counter

from validator.checker import run_query

BENCHMARK_TIMEOUT_MS = 2_000
SPEEDUP_THRESHOLD = 1.2
MAX_REPETITIONS = 3
DEFAULT_REPETITIONS = MAX_REPETITIONS


def measure(
    conn,
    orig_sql: str,
    cand_sql: str,
    params: dict,
    reps: int,
    *,
    timeout_ms: int = BENCHMARK_TIMEOUT_MS,
    measurements: list | None = None,
) -> dict:
    """Balance the starting query and measure both with the same binding."""
    conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
    if measurements is None:
        measurements = []
    baseline, rewrite = [], []
    for index in range(reps):
        queries = [("original", orig_sql), ("proposed", cand_sql)]
        if index % 2:
            queries.reverse()
        started = perf_counter()
        sample = {
            "repetition": index + 1,
            "first_query": queries[0][0],
            "original_ms": None,
            "proposed_ms": None,
            "status": "passed",
        }
        measurements.append(sample)
        try:
            for query_name, sql in queries:
                query_started = perf_counter()
                result = run_query(conn, sql, params)
                sample[f"{query_name}_ms"] = result.ms
        except Exception:
            sample["status"] = "error"
            sample[f"{query_name}_ms"] = (perf_counter() - query_started) * 1000
            raise
        finally:
            sample["duration_ms"] = (perf_counter() - started) * 1000
        baseline.append(sample["original_ms"])
        rewrite.append(sample["proposed_ms"])
    original_ms, candidate_ms = median(baseline), median(rewrite)
    original_low, _, original_high = (
        quantiles(baseline, method="inclusive") if reps > 1 else (original_ms,) * 3
    )
    candidate_low, _, candidate_high = (
        quantiles(rewrite, method="inclusive") if reps > 1 else (candidate_ms,) * 3
    )
    speedup = original_ms / candidate_ms if candidate_ms > 0 else None
    return {
        "orig_median_ms": original_ms,
        "orig_iqr_ms": original_high - original_low,
        "cand_median_ms": candidate_ms,
        "cand_iqr_ms": candidate_high - candidate_low,
        "speedup": speedup,
        "faster": (
            reps >= 3
            and speedup is not None
            and speedup >= SPEEDUP_THRESHOLD
            and original_low >= SPEEDUP_THRESHOLD * candidate_high
        ),
        "reps": reps,
        "benchmark_measurements": measurements,
    }
