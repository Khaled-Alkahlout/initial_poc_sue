"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { Run, RunInput, SystemStatus } from "@/lib/api/contracts";
import { condition } from "@/lib/api/contracts";
import { useApi } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { AnalysisOptions } from "./analysis-options";

export function RetryAnalysis({
  run,
  system: initialSystem,
}: {
  run: Run;
  system?: SystemStatus;
}) {
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const previousCondition = condition.safeParse(run.attempts[0]?.condition);
  const [selectedCondition, setCondition] = useState<RunInput["condition"]>(
    previousCondition.success ? previousCondition.data : "C1_query",
  );
  const [testAfter, setTestAfter] = useState(false);
  const [confirmDatabase, setConfirmDatabase] = useState(false);
  const { data: system, error: systemError } = useApi(
    api.getSystem,
    initialSystem,
  );
  const needsDatabase = selectedCondition !== "C1_query" || testAfter;
  const databaseAvailable = system?.run_modes.some(
    (mode) => mode.id === "validate" && mode.available,
  );
  const canStart =
    consent &&
    !busy &&
    system?.run_modes.some(
      (mode) => mode.id === "analysis" && mode.available,
    ) &&
    (!needsDatabase || (databaseAvailable && confirmDatabase));
  async function retry() {
    if (!canStart) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.startRun({
        mode: testAfter ? "live" : "analysis",
        query_id: run.query_ids[0],
        condition: selectedCondition,
        confirm_sql: needsDatabase && confirmDatabase,
        confirm_external_model: consent,
      });
      router.push(`/runs/${next.id}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title="Analyse opnieuw aanvragen"
        description="Een nieuwe analyse gebruikt de gekozen context en de huidige modelinstellingen."
      />
      <div className="panel-body stack">
        <Link className="text-link" href="/settings">
          AI Settings aanpassen →
        </Link>
        {system && (
          <AnalysisOptions
            system={system}
            condition={selectedCondition}
            onConditionChange={setCondition}
            testAfter={testAfter}
            onTestAfterChange={setTestAfter}
            confirmDatabase={confirmDatabase}
            onConfirmDatabaseChange={setConfirmDatabase}
            disabled={busy}
          />
        )}
        <label className="check-field">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            Ik bevestig een nieuw extern modelrequest met de gekozen SQL en
            context en mogelijke kosten.
          </span>
        </label>
        <Button disabled={!canStart} onClick={retry}>
          {busy ? "Aanvragen…" : "Opnieuw analyseren"}
        </Button>
        {systemError && <p role="alert">{systemError}</p>}
        {error && <p role="alert">{error}</p>}
      </div>
    </Card>
  );
}
