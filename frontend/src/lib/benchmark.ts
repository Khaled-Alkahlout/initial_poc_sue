import type { Attempt } from "@/lib/api/contracts";

export function compareBenchmark(attempt: Attempt) {
  const { original_ms, proposed_ms, status } = attempt.benchmark;
  if (
    !["passed", "warning"].includes(status) ||
    attempt.correctness !== "passed" ||
    original_ms == null ||
    !Number.isFinite(original_ms) ||
    original_ms <= 0 ||
    proposed_ms == null ||
    !Number.isFinite(proposed_ms) ||
    proposed_ms < 0
  )
    return null;

  const reduction = ((original_ms - proposed_ms) / original_ms) * 100;
  if (!Number.isFinite(reduction)) return null;

  return {
    original: original_ms,
    proposed: proposed_ms,
    reduction,
    regression: proposed_ms > original_ms,
    validated:
      attempt.outcome === "accepted" &&
      proposed_ms < original_ms &&
      !!attempt.proposed_sql?.trim(),
  };
}

const decimal = new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 3 });

export function benchmarkTime(ms: number) {
  return ms > 0 && ms < 0.001 ? "< 0,001 ms" : decimal.format(ms) + " ms";
}

export function percentageChange(value: number) {
  const absolute = Math.abs(value);
  return absolute > 0 && absolute < 0.001
    ? "< 0,001%"
    : decimal.format(absolute) + "%";
}
