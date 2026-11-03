"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api/client";
import type { Run } from "@/lib/api/contracts";
import { condition } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";

export function RetryAnalysis({ run }: { run: Run }) {
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const previousCondition = condition.safeParse(run.attempts[0]?.condition);
  async function retry() {
    setBusy(true);
    setError(null);
    try {
      const next = await api.startRun({
        mode: "analysis",
        query_id: run.query_ids[0],
        condition: previousCondition.success
          ? previousCondition.data
          : "C4_stats",
        confirm_sql: false,
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
        description="Pas eerst je budget of reasoning aan. De mislukte poging en diagnostiek blijven bewaard; een retry is een nieuw betaald request."
      />
      <div className="panel-body stack">
        <Link className="text-link" href="/settings">
          AI Settings aanpassen →
        </Link>
        <label className="check-field">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            Ik bevestig een nieuw extern modelrequest met mogelijke kosten.
          </span>
        </label>
        <Button disabled={!consent || busy} onClick={retry}>
          {busy
            ? "Aanvragen…"
            : "Opnieuw analyseren met opgeslagen instellingen"}
        </Button>
        {error && <p role="alert">{error}</p>}
      </div>
    </Card>
  );
}
