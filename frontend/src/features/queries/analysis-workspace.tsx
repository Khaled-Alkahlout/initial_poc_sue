"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api/client";
import type { QueryDetail, Run, SystemStatus } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/shared/states";
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
  const [error, setError] = useState<string | null>(null);
  const capability = system.run_modes.find((m) => m.id === "analysis");
  const previousRunId = query.attempts.find(
    (attempt) => attempt.analysis || attempt.diagnostics?.error_code,
  )?.run_id;
  useEffect(() => {
    if (!previousRunId) return;
    let disposed = false;
    api
      .getRun(previousRunId)
      .then((value) => {
        if (!disposed) setRun((current) => current ?? value);
      })
      .catch((reason) => {
        if (!disposed) setError(errorMessage(reason));
      });
    return () => {
      disposed = true;
    };
  }, [previousRunId]);
  async function start(rewriteOnly = false) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setRun(
        await api.startRun({
          mode: "analysis",
          ...(rewriteOnly ? { rewrite_only: true, source_id: run?.id } : {}),
          query_id: query.query_id,
          condition: "C4_stats",
          confirm_sql: false,
          confirm_external_model: consent,
        }),
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="stack" aria-label="AI Analysis Workspace">
      <Card>
        <CardHeader
          title="Analyze with AI"
          description="Van originele query naar een verklaarbaar advies. Generatie voert geen SQL uit en bewijst geen correctheid."
        />
        <div className="panel-body stack">
          <p className="text-xs muted">
            {system.provider ?? "Provider"} ·{" "}
            <span className="mono">
              {system.configured_model ?? "Geen model ingesteld"}
            </span>
            . Beschikbare context is historisch en kan verouderd zijn.
            Ontbrekende informatie wordt als beperking meegestuurd.
          </p>
          <label className="check-field">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              Ik bevestig één extern AI-request met geredigeerde fixturecontext
              en mogelijke kosten.
            </span>
          </label>
          <Button
            onClick={() => start()}
            disabled={
              busy ||
              !consent ||
              !capability?.available ||
              (!!run && ["PENDING", "RUNNING"].includes(run.lifecycle))
            }
          >
            {busy ? "Analyse starten…" : "Analyze with AI"}
          </Button>
          {!capability?.available && (
            <p className="notice notice-amber">
              {system.configuration_error ??
                capability?.reason ??
                "OpenRouter nog niet geconfigureerd."}{" "}
              <Link className="text-link" href="/development/architecture">
                Systeemstatus
              </Link>
            </p>
          )}
          {capability?.available && (
            <p className="notice notice-blue">
              Klaar voor echte AI-analyse via {system.provider}. De knop stuurt
              één verzoek naar het ingestelde model. Er wordt geen SQL
              uitgevoerd; correctheid en performance blijven ongetest.
            </p>
          )}
          {error && <ErrorState message={error} />}
          {query.attempts
            .filter((a) => a.analysis)
            .slice(0, 1)
            .map((a) => (
              <Link key={a.id} className="text-link" href={`/runs/${a.run_id}`}>
                Vorige AI-analyse openen →
              </Link>
            ))}
        </div>
      </Card>
      {run && (
        <RunDetail
          key={run.id}
          initial={run}
          onUpdate={setRun}
          rewriteAction={
            ["COMPLETED", "FAILED"].includes(run.lifecycle) ? (
              <Card>
                <CardHeader
                  title="Generate SQL Rewrite"
                  description="Vraag één alternatief voorstel aan met dezelfde context en bekende bottlenecks. Een voorstel is een ongeteste hypothese."
                />
                <div className="panel-body stack">
                  <Button
                    onClick={() => start(true)}
                    disabled={busy || !consent || !capability?.available}
                  >
                    Generate SQL Rewrite
                  </Button>
                  <p className="muted text-xs">
                    Gebruik de bevestiging hierboven voor één extern
                    modelrequest. Elke aanvraag blijft apart in de
                    analysehistorie bewaard.
                  </p>
                </div>
              </Card>
            ) : null
          }
        />
      )}
    </section>
  );
}
