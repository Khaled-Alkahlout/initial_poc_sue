"use client";
import { useState } from "react";
import { StatusBadge } from "@/components/shared/status";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api/client";
import type { DatabaseTest } from "@/lib/api/contracts";

export function DatabaseStatus({ configured }: { configured: boolean }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DatabaseTest | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      setResult(await api.checkDatabase());
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Testdatabase"
        description="Controleer de PostgreSQL-verbinding en de toegang tot de casustabellen vanuit de Python-API."
      />
      <div className="panel-body stack">
        <Button variant="outline" disabled={busy} onClick={check}>
          {busy
            ? "Databaseverbinding controleren…"
            : "Databaseverbinding testen"}
        </Button>
        <div role="status">
          {result ? (
            <dl className="kv-list">
              {[
                { label: "Verbinding (SELECT 1)", ...result.connection },
                { label: "Toegang tot casustabellen", ...result.tables },
              ].map((step) => (
                <div key={step.label}>
                  <dt>{step.label}</dt>
                  <dd>
                    <StatusBadge status={step.status} />
                    <p className="muted text-xs mt-2">{step.message}</p>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            !error && (
              <p className="muted text-xs">
                {busy
                  ? "Bezig met een read-only verbindingstest."
                  : configured
                    ? "Verbinding nog niet getest."
                    : "Database-instellingen onvolledig. Start de test voor details."}
              </p>
            )
          )}
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </Card>
  );
}
