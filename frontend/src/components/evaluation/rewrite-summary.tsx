"use client";

import { useEffect } from "react";
import { api } from "@/lib/api/client";
import type { Attempt } from "@/lib/api/contracts";
import { SqlComparison } from "@/components/queries/sql-viewer";
import { Badge } from "@/components/shared/status";
import { benchmarkTime, compareBenchmark } from "@/lib/benchmark";

export function RewriteSummary({
  attempt,
  measured = attempt,
}: {
  attempt: Attempt;
  measured?: Attempt;
}) {
  const sql = attempt.proposed_sql;
  const fromCase = attempt.proposal_source === "case";
  useEffect(() => {
    if (attempt.diagnostics?.rewrite_requested) {
      // Acknowledge the stored value without sending SQL or its display formatting.
      void api
        .recordRewriteDisplay(attempt.run_id, !!sql && !fromCase)
        .catch(() => {});
    }
  }, [attempt.run_id, attempt.diagnostics?.rewrite_requested, sql, fromCase]);

  const failed = attempt.validation_state === "rewrite_parsing_failed";
  const rejected = attempt.outcome === "safety_rejected";
  const error = attempt.outcome === "error" && !sql;
  const measuredPair = compareBenchmark(measured);
  const aiCandidate =
    !!attempt.analysis || (!!attempt.model && attempt.model !== "mock");
  const untested = !!sql && measured.correctness === "skipped" && !rejected;
  const title = failed
    ? "Rewrite parsing failed"
    : rejected
      ? "Rewrite failed static validation"
      : fromCase
        ? "Variant uit het casusregister"
        : error
          ? "SQL rewrite request failed"
          : sql
            ? aiCandidate
              ? "SQL rewrite generated"
              : "SQL-kandidaat opgeslagen"
            : "No SQL rewrite proposed";
  const empty =
    failed || error
      ? "Er is geen bruikbaar SQL-voorstel opgeslagen. Open Technical Details voor responsdiagnostiek."
      : (attempt.analysis?.rewrite_explanation ??
        "Deze poging bevat geen opgeslagen SQL-voorstel.");
  const status =
    !sql || rejected || failed || untested || fromCase ? (
      <div className="rewrite-state">
        <h3>{title}</h3>
        {rejected && (
          <Badge tone="red">
            {attempt.diagnostics?.candidate_rejection_reason ??
              "Statisch afgewezen"}
          </Badge>
        )}
        {untested && <Badge tone="amber">Wacht op correctheidsvalidatie</Badge>}
        {!sql &&
          attempt.analysis?.rewrite_status === "insufficient_context" && (
            <Badge tone="amber">Onvoldoende context</Badge>
          )}
        {fromCase && (
          <p className="muted text-xs">
            Het model gaf geen SQL-voorstel. De pipeline test de bestaande
            variant <code>{attempt.candidate}</code>.
          </p>
        )}
      </div>
    ) : null;

  return (
    <section aria-label="SQL rewrite">
      <SqlComparison
        status={status}
        original={attempt.original_sql}
        proposed={sql}
        empty={empty}
        proposedTitle={fromCase ? "Casusvariant" : undefined}
        proposedLabel={
          sql && !fromCase
            ? aiCandidate
              ? "AI-voorstel"
              : "Testkandidaat"
            : undefined
        }
        timing={
          measuredPair && sql
            ? {
                original: benchmarkTime(measuredPair.original),
                proposed: benchmarkTime(measuredPair.proposed),
              }
            : undefined
        }
      />
    </section>
  );
}
