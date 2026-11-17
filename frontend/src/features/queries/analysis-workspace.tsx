"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Sparkles } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { QueryDetail, Run, SystemStatus } from "@/lib/api/contracts";
import { compareBenchmark } from "@/lib/benchmark";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/shared/states";
import { SqlViewer } from "@/components/queries/sql-viewer";
import { RunDetail } from "@/features/runs/run-detail";

export function AnalysisWorkspace({
  query,
  system,
}: {
  query: QueryDetail;
  system: SystemStatus;
}) {
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [confirmSql, setConfirmSql] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const capability = system.run_modes.find((mode) => mode.id === "analysis");
  const fullRun = system.run_modes.find(
    (mode) => mode.id === "live" && mode.available,
  );
  const storedAnalysisId = query.runs.find(
    (item) => item.mode === "analysis" || item.mode === "live",
  )?.id;
  const previous = query.attempts.find(
    (attempt) => attempt.analysis || attempt.diagnostics?.error_code,
  );
  const experiment =
    query.attempts.find(
      (attempt) =>
        attempt.origin === "historical" &&
        !!compareBenchmark(attempt)?.validated,
    ) ??
    query.attempts.find(
      (attempt) => attempt.origin === "historical" && !!attempt.proposed_sql,
    );
  const previousRunId =
    storedAnalysisId ?? previous?.run_id ?? experiment?.run_id;
  const validationId =
    run?.mode === "analysis" || run?.mode === "live"
      ? query.runs.find(
          (item) =>
            item.mode === "validate" &&
            item.source_id === run.id &&
            (item.lifecycle === "COMPLETED" || item.lifecycle === "FAILED") &&
            item.attempt_count > 0,
        )?.id
      : undefined;
  const validation = validationId
    ? query.attempts.find((attempt) => attempt.run_id === validationId)
    : undefined;
  const pending = run?.lifecycle === "PENDING" || run?.lifecycle === "RUNNING";
  const latestAttempt = run?.attempts[0];

  useEffect(() => {
    if (!previousRunId) return;
    let disposed = false;
    api
      .getRun(previousRunId)
      .then((value) => {
        if (!disposed) setRun((current) => current ?? value);
      })
      .catch((reason) => {
        if (!disposed) setLoadError(errorMessage(reason));
      });
    return () => {
      disposed = true;
    };
  }, [previousRunId, reload]);

  async function start(rewriteOnly = false) {
    if (busy || pending || !consent || !capability?.available) return;
    const validate = !rewriteOnly && !!fullRun && confirmSql;
    setBusy(true);
    setRequestError(null);
    try {
      setRun(
        await api.startRun({
          mode: validate ? "live" : "analysis",
          ...(rewriteOnly ? { rewrite_only: true, source_id: run?.id } : {}),
          query_id: query.query_id,
          condition: validate ? "C4_stats" : "C1_query",
          confirm_sql: validate,
          confirm_external_model: consent,
        }),
      );
    } catch (reason) {
      setRequestError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  const canRewrite =
    (run?.mode === "analysis" || run?.mode === "live") &&
    !!latestAttempt &&
    !pending;
  return (
    <section className="stack" aria-label="AI Analysis Workspace">
      <Card className="analysis-controls">
        <CardHeader
          title="Analyze with AI"
          description="Analyseer de query en genereer een onderbouwd SQL-voorstel."
          action={
            system.configured_model && (
              <Link
                className="model-pill mono"
                href="/settings"
                title="Model en reasoning instellen"
              >
                {system.configured_model}
              </Link>
            )
          }
        />
        <div className="panel-body">
          {capability?.available ? (
            <>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                <span>
                  Ik bevestig één extern AI-request met de casus-SQL en
                  mogelijke kosten. Bij een volledige run gaat ook beperkte
                  testdatabasemetadata mee.
                </span>
              </label>
              {fullRun && (
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={confirmSql}
                    onChange={(event) => setConfirmSql(event.target.checked)}
                  />
                  <span>
                    Ik bevestig ook correctheidscontrole en een begrensde
                    benchmark op de geïsoleerde testdatabase.
                  </span>
                </label>
              )}
              <div className="page-actions">
                <Button
                  onClick={() => start()}
                  disabled={busy || pending || !consent}
                >
                  <Sparkles size={16} />{" "}
                  {busy
                    ? "Analyse starten…"
                    : fullRun && confirmSql
                      ? "Analyseer en valideer"
                      : "Analyze with AI"}
                </Button>
                {canRewrite && (
                  <Button
                    variant="outline"
                    onClick={() => start(true)}
                    disabled={busy || !consent}
                  >
                    Generate SQL Rewrite
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div className="analysis-unavailable">
              <Button disabled>
                <Sparkles size={16} /> Analyze with AI
              </Button>
              <p className="muted text-sm">
                {system.configuration_error ??
                  capability?.reason ??
                  "OpenRouter nog niet geconfigureerd."}{" "}
                <Link className="text-link" href="/settings">
                  AI Settings <ArrowUpRight size={12} />
                </Link>
              </p>
            </div>
          )}
          {requestError && (
            <p className="notice notice-error" role="alert">
              {requestError}
            </p>
          )}
          {(run?.mode === "analysis" || run?.mode === "live") &&
            latestAttempt && (
              <Link className="text-link" href={"/runs/" + run.id}>
                Open deze analyse <ArrowUpRight size={12} />
              </Link>
            )}
        </div>
      </Card>
      {!run && loadError && (
        <ErrorState
          message={loadError}
          retry={() => {
            setLoadError(null);
            setReload((value) => value + 1);
          }}
        />
      )}
      {run ? (
        <RunDetail
          key={run.id}
          initial={run}
          initialAttemptId={
            run.id === experiment?.run_id ? experiment.id : undefined
          }
          onUpdate={setRun}
          inline
          system={system}
          baselineSql={query.sql}
          validation={validation}
        />
      ) : (
        <>
          {previousRunId && !loadError && (
            <p className="run-live-status" role="status">
              Opgeslagen analyse laden…
            </p>
          )}
          <SqlViewer
            sql={query.sql}
            title="Original SQL Query"
            label="SQL-fixture"
          />
        </>
      )}
    </section>
  );
}
