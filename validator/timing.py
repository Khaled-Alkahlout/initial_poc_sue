"""Paired measurements in the correctness snapshot."""

from statistics import median, quantiles

from validator.checker import run_query

BENCHMARK_TIMEOUT_MS = 500
SPEEDUP_THRESHOLD = 1.2
DEFAULT_REPETITIONS = 6


def measure(conn, orig_sql: str, cand_sql: str, params: dict, reps: int) -> dict:
    """Balance the starting query and measure both with the same binding."""
    conn.execute(f"SET LOCAL statement_timeout = {BENCHMARK_TIMEOUT_MS}")
    baseline, rewrite = [], []
    for index in range(reps):
        if index % 2 == 0:
            baseline.append(run_query(conn, orig_sql, params).ms)
            rewrite.append(run_query(conn, cand_sql, params).ms)
        else:
            rewrite.append(run_query(conn, cand_sql, params).ms)
            baseline.append(run_query(conn, orig_sql, params).ms)
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
            reps >= 4
            and speedup is not None
            and speedup >= SPEEDUP_THRESHOLD
            and original_low >= SPEEDUP_THRESHOLD * candidate_high
        ),
        "reps": reps,
    }
