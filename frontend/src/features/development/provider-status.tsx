"use client";
import { useState } from "react";
import { z } from "zod";
import { request, errorMessage } from "@/lib/api/client";
import type { SystemStatus } from "@/lib/api/contracts";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";

export function ProviderStatus({ system }: { system: SystemStatus }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  async function check() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await request(
        "/system/check-model",
        z.object({
          status: z.literal("connected"),
          provider: z.string(),
          model: z.string(),
          note: z.string(),
        }),
        { method: "POST", signal: AbortSignal.timeout(50000) },
      );
      setMessage(result.note);
      setFailed(false);
    } catch (e) {
      setMessage(errorMessage(e));
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title="AI-provider & veiligheidsinstellingen"
        description="De verbindingstest controleert key en modelcatalogus. Geen betaalde generatie of databasequery."
      />
      <div className="panel-body stack">
        <dl className="kv-list">
          <div>
            <dt>Provider / model</dt>
            <dd className="mono">
              {system.provider ?? "Onbekend"} /{" "}
              {system.configured_model ?? "Niet ingesteld"}
            </dd>
          </div>
          <div>
            <dt>API-configuratie</dt>
            <dd>
              {message
                ? failed
                  ? "Verbindingscontrole mislukt"
                  : "Verbonden · key en model gecontroleerd"
                : system.model_configured
                  ? "Aanwezig · verbinding niet getest"
                  : "Niet geconfigureerd"}
            </dd>
          </div>
          <div>
            <dt>POC met echt model</dt>
            <dd>
              {system.run_modes.find((mode) => mode.id === "analysis")
                ?.available
                ? "Beschikbaar · zonder database"
                : "Nog niet beschikbaar"}
            </dd>
          </div>
          <div>
            <dt>SQL-uitvoering</dt>
            <dd>{system.sql_enabled ? "Ingeschakeld" : "Uitgeschakeld"}</dd>
          </div>
          <div>
            <dt>Geïsoleerd testdoel bevestigd</dt>
            <dd>{system.test_database_confirmed ? "Ja" : "Nee"}</dd>
          </div>
          <div>
            <dt>Databron</dt>
            <dd>Demo / historische context</dd>
          </div>
        </dl>
        {system.configuration_error && (
          <p role="alert">{system.configuration_error}</p>
        )}
        <Button
          variant="outline"
          disabled={
            busy || !system.model_configured || system.provider !== "openrouter"
          }
          onClick={check}
        >
          {busy ? "Verbinding controleren…" : "OpenRouter-verbinding testen"}
        </Button>
        {message && (
          <p
            role={failed ? "alert" : "status"}
            className={failed ? "form-error" : "notice notice-blue"}
          >
            {message}
          </p>
        )}
      </div>
    </Card>
  );
}
