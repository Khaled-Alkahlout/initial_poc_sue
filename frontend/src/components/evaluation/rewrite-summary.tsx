"use client";

import { useEffect } from "react";
import { api } from "@/lib/api/client";
import type { Attempt } from "@/lib/api/contracts";
import { SqlComparison } from "@/components/queries/sql-viewer";

export function RewriteSummary({ attempt }: { attempt: Attempt }) {
  const sql = attempt.proposed_sql;
  useEffect(() => {
    if (attempt.diagnostics?.rewrite_requested) {
      // Acknowledges the rendered stored value, without transmitting SQL.
      void api.recordRewriteDisplay(attempt.run_id, !!sql).catch(() => {});
    }
  }, [attempt.run_id, attempt.diagnostics?.rewrite_requested, sql]);
  const failed = attempt.validation_state === "rewrite_parsing_failed";
  const rejected = attempt.outcome === "safety_rejected";
  const title = failed
    ? "Rewrite parsing failed"
    : rejected
      ? "Rewrite failed static validation"
      : sql
        ? "SQL rewrite generated"
        : attempt.validation_state === "analysis_failed"
          ? "SQL rewrite request failed"
          : "No SQL rewrite proposed";
  const reason = failed
    ? "Het modelantwoord kon niet worden verwerkt. Dit is geen no-rewritebeslissing. Backenddiagnostiek bevat de verwerkingsstatus."
    : rejected
      ? `Statische controle: ${attempt.diagnostics?.candidate_rejection_reason ?? "safety_rejected"}. Het voorstel blijft zichtbaar voor review en wordt niet uitgevoerd.`
      : (attempt.analysis?.rewrite_explanation ??
        (sql
          ? "Ongeteste kandidaat; afzonderlijke correctheids- en performancetests vereist."
          : `Geen specifieke rewritebeslissing vastgelegd in dit oudere artefact. ${attempt.analysis?.uncertainty ?? ""}`));
  return (
    <section className="stack" aria-label="SQL rewrite">
      <div className="notice notice-amber">
        <h3>{title}</h3>
        <p>{reason}</p>
        {sql && attempt.correctness === "skipped" && !rejected && (
          <p>Rewrite awaiting correctness validation · performance ongetest.</p>
        )}
      </div>
      <SqlComparison
        original={attempt.original_sql}
        proposed={sql}
        empty={`${title}. ${reason}`}
      />
    </section>
  );
}
