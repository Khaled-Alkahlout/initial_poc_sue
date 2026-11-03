"use client";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/client";
import type { AISettings, GenerationSettings } from "@/lib/api/contracts";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, Input } from "@/components/ui/fields";
import { PageHeader } from "@/components/shared/page-header";
import { JsonInspector } from "@/components/shared/json-inspector";
import { count } from "@/lib/formatters";

export function AISettingsPage({ initial }: { initial: AISettings }) {
  const [value, setValue] = useState<GenerationSettings>(initial.settings);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const usageNumber = (value: number | null | undefined) =>
    value == null ? "Niet gerapporteerd" : count(value);
  const [testResult, setTestResult] = useState<Awaited<
    ReturnType<typeof api.testAIGeneration>
  > | null>(null);
  async function save(reset = false) {
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      setValue(
        await (reset ? api.resetAISettings() : api.saveAISettings(value)),
      );
      setFeedback(
        reset
          ? "Omgevingsstandaarden hersteld; volgende aanvragen gebruiken deze waarden."
          : "Instellingen opgeslagen. Ze gelden voor nieuwe analyses; opnieuw starten is niet nodig.",
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function test() {
    setBusy(true);
    setError(null);
    setTestResult(null);
    try {
      setTestResult(await api.testAIGeneration());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const labels: Record<string, string> = {
    disabled: "Uitgeschakeld",
    low: "Low",
    medium: "Medium",
    high: "High",
  };
  return (
    <div className="stack">
      <PageHeader
        title="AI Settings"
        eyebrow="INSTELLINGEN / GENERATIE"
        description="Beheer het outputbudget en reasoning. Instellingen veranderen geen databasebevoegdheden of API-credentials."
      />
      <Card>
        <CardHeader
          title="AI Provider"
          description="Credentials blijven uitsluitend op de server."
        />
        <div className="panel-body stack">
          <dl className="kv-list">
            <div>
              <dt>Provider</dt>
              <dd>{initial.provider}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd className="mono">{initial.model}</dd>
            </div>
            <div>
              <dt>API-key geconfigureerd</dt>
              <dd>{initial.key_configured ? "Ja" : "Nee"}</dd>
            </div>
            <div>
              <dt>AI-generatie</dt>
              <dd>{initial.llm_enabled ? "Ingeschakeld" : "Uitgeschakeld"}</dd>
            </div>
            <div>
              <dt>Verbindingsstatus</dt>
              <dd>
                {testResult
                  ? testResult.success
                    ? "Geslaagd · zichtbare modeloutput ontvangen"
                    : "Test mislukt"
                  : "Nog niet getest"}
              </dd>
            </div>
          </dl>
          <label className="check-field">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              Ik bevestig een kleine betaalde AI-verbindingstest. Geen SQL;
              maximaal 512 outputtokens, reasoning uit waar ondersteund.
            </span>
          </label>
          <Button
            variant="outline"
            onClick={test}
            disabled={
              busy ||
              !consent ||
              !initial.key_configured ||
              !initial.llm_enabled
            }
          >
            {busy ? "Bezig…" : "Test AI connection"}
          </Button>
          {testResult && (
            <>
              <dl className="kv-list">
                <div>
                  <dt>Input / output / reasoning</dt>
                  <dd>
                    {usageNumber(testResult.diagnostics?.input_tokens)} /{" "}
                    {usageNumber(testResult.diagnostics?.output_tokens)} /{" "}
                    {usageNumber(testResult.diagnostics?.reasoning_tokens)}
                  </dd>
                </div>
                <div>
                  <dt>Duur / finish reason</dt>
                  <dd>
                    {usageNumber(testResult.diagnostics?.seconds)} s /{" "}
                    {testResult.diagnostics?.finish_reason ??
                      "Niet gerapporteerd"}
                  </dd>
                </div>
              </dl>
              <p
                role={testResult.success ? "status" : "alert"}
                className={
                  testResult.success ? "notice notice-blue" : "form-error"
                }
              >
                {testResult.message}
              </p>
              <JsonInspector
                title="Werkelijke testmetadata · geen reasoningtekst"
                value={testResult.diagnostics}
              />
            </>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Generation Settings"
          description="Outputbudget wordt gedeeld met reasoningtokens. Meer tokens garanderen geen correct of volledig antwoord."
        />
        <form
          className="panel-body form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="field">
            <span>Maximum output tokens</span>
            <Select
              value={value.max_output_tokens ?? "provider"}
              onChange={(e) =>
                setValue({
                  ...value,
                  max_output_tokens:
                    e.target.value === "provider"
                      ? null
                      : Number(e.target.value),
                })
              }
            >
              {[512, 1024, 2048, 4096, 8192, 16384].map((n) => (
                <option
                  key={n}
                  value={n}
                  disabled={
                    !!initial.capabilities?.max_output_tokens &&
                    n > initial.capabilities.max_output_tokens
                  }
                >
                  {n.toLocaleString("nl-NL")}
                </option>
              ))}
              <option value="provider">
                Provider-default · maximum weglaten
              </option>
            </Select>
          </label>
          <p className="muted text-xs">
            Provider-default laat max_tokens weg; het is geen onbeperkt budget.
            Modellimiet:{" "}
            {initial.capabilities?.max_output_tokens?.toLocaleString("nl-NL") ??
              "niet gerapporteerd"}
            .
          </p>
          <label className="field">
            <span>Reasoning effort</span>
            <Select
              value={value.reasoning_effort}
              onChange={(e) =>
                setValue({
                  ...value,
                  reasoning_effort: e.target
                    .value as GenerationSettings["reasoning_effort"],
                })
              }
            >
              {Object.entries(labels).map(([key, label]) => (
                <option
                  key={key}
                  value={key}
                  disabled={
                    !initial.capabilities?.reasoning_efforts.includes(key)
                  }
                >
                  {label}
                  {!initial.capabilities?.reasoning_efforts.includes(key)
                    ? " · niet ondersteund/bevestigd"
                    : ""}
                </option>
              ))}
            </Select>
          </label>
          <p className="muted text-xs">
            Low is de standaard voor SQL-analyse. Hogere effort kan meer
            outputbudget gebruiken voordat zichtbare JSON verschijnt.
          </p>
          {initial.capabilities?.temperature_supported ? (
            <label className="field">
              <span>Temperature · leeg = provider-default</span>
              <Input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={value.temperature ?? ""}
                onChange={(e) =>
                  setValue({
                    ...value,
                    temperature:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          ) : (
            <p className="muted text-xs">
              Temperature wordt door dit model niet ondersteund; de applicatie
              stuurt deze parameter niet mee.
            </p>
          )}
          {initial.capabilities_error && (
            <p role="alert" className="notice notice-amber">
              Modelmogelijkheden konden niet worden bevestigd:{" "}
              {initial.capabilities_error}
            </p>
          )}
          <p className="muted text-xs">{initial.precedence}</p>
          <div className="form-actions">
            <Button
              type="button"
              variant="outline"
              onClick={() => save(true)}
              disabled={busy}
            >
              Standaarden herstellen
            </Button>
            <Button type="submit" disabled={busy || !initial.capabilities}>
              Instellingen opslaan
            </Button>
          </div>
        </form>
      </Card>
      {feedback && (
        <p role="status" className="notice notice-blue">
          {feedback}
        </p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <Card>
        <CardHeader title="Beveiligde databaseconfiguratie" />
        <div className="panel-body stack">
          <p>
            SQL-uitvoering:{" "}
            <strong>
              {initial.sql_enabled ? "Ingeschakeld" : "Uitgeschakeld"}
            </strong>{" "}
            · Testdoel bevestigd:{" "}
            <strong>{initial.test_database_confirmed ? "Ja" : "Nee"}</strong>.
          </p>
          <p className="text-xs muted">
            Deze instellingen zijn hier alleen leesbaar. Generatie-instellingen
            kunnen SQL nooit inschakelen.
          </p>
          <Link className="text-link" href="/development/architecture">
            Systeemstatus en veiligheidsgrenzen →
          </Link>
        </div>
      </Card>
    </div>
  );
}
