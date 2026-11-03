"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { Run, SystemStatus } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";

export function ValidateProposal({ run }: { run: Run }) {
  const router = useRouter();
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .getSystem()
      .then(setSystem)
      .catch((e) => setError(errorMessage(e)));
  }, []);
  const allowed = system?.run_modes.find((m) => m.id === "validate");
  const attempt = run.attempts[0];
  async function validate() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.startRun({
        mode: "validate",
        query_id: run.query_ids[0],
        condition: "C1_query",
        source_id: run.id,
        confirm_sql: consent,
        confirm_external_model: false,
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
        title="Voorstel afzonderlijk valideren"
        description="Geen nieuwe modelcall. Correctheid en performance worden op de bevestigde testdatabase afzonderlijk beoordeeld."
      />
      <div className="panel-body stack">
        <p className="notice notice-amber">
          {allowed?.available
            ? "SQL-uitvoering beschikbaar op het door de operator bevestigde testdoel."
            : "Validatie niet beschikbaar. Beide SQL-veiligheidsinstellingen, een geïsoleerde testdatabase en psycopg zijn vereist. AI-advies blijft bruikbaar voor menselijke review."}
        </p>
        {allowed?.available && (
          <label className="check-field">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              Ik bevestig vergelijking en zeven benchmarkherhalingen op de
              geïsoleerde testdatabase.
            </span>
          </label>
        )}
        <Button
          disabled={
            !allowed?.available ||
            !consent ||
            busy ||
            !attempt?.proposed_sql ||
            attempt.outcome === "safety_rejected"
          }
          onClick={validate}
        >
          {busy ? "Validatie starten…" : "Correctheid & performance testen"}
        </Button>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
      </div>
    </Card>
  );
}
