"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { Query, RunInput, SystemStatus } from "@/lib/api/contracts";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Select } from "@/components/ui/fields";
import { Button } from "@/components/ui/button";
import { AnalysisOptions } from "./analysis-options";

export function StartRun({
  queries,
  system,
  label = "Nieuwe analyse",
  queryId,
}: {
  queries: Query[];
  system: SystemStatus;
  label?: string;
  queryId?: string;
}) {
  const router = useRouter();
  const liveMode = system.run_modes.find((item) => item.id === "live");
  const analysisMode = system.run_modes.find((item) => item.id === "analysis");
  const databaseMode = system.run_modes.find((item) => item.id === "validate");
  const canValidate = databaseMode?.available === true;
  const canAnalyze =
    liveMode?.available === true || analysisMode?.available === true;
  const defaultCase = canValidate
    ? queries.find((query) => query.query_id === "audit_log_page")
    : undefined;
  const [open, setOpen] = useState(false);
  const [selectedQuery, setSelectedQuery] = useState(
    queryId ?? defaultCase?.query_id ?? queries[0]?.query_id ?? "",
  );
  const [confirmModel, setConfirmModel] = useState(false);
  const [confirmSql, setConfirmSql] = useState(false);
  const [condition, setCondition] = useState<RunInput["condition"]>(
    canValidate ? "C4_stats" : "C1_query",
  );
  const [testAfter, setTestAfter] = useState(canValidate);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const statusReason =
    analysisMode?.reason ??
    liveMode?.reason ??
    "AI-analyse is momenteel niet beschikbaar.";
  const needsDatabase = condition !== "C1_query" || testAfter;
  const canStart =
    canAnalyze &&
    selectedQuery !== "" &&
    confirmModel &&
    (!needsDatabase || (canValidate && confirmSql)) &&
    !busy;

  function changeOpen(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) {
      setConfirmModel(false);
      setConfirmSql(false);
      setError(null);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canStart) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.startRun({
        mode: testAfter ? "live" : "analysis",
        query_id: selectedQuery,
        condition,
        confirm_sql: needsDatabase && confirmSql,
        confirm_external_model: confirmModel,
      });
      setOpen(false);
      router.push(`/runs/${run.id}`);
      router.refresh();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Play size={14} />
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent
        title="SQL-analyse starten"
        description="Kies de context voor het model en of je het voorstel daarna wilt testen."
      >
        <form className="form-grid" onSubmit={submit}>
          <label className="field">
            <span>Query</span>
            <Select
              value={selectedQuery}
              onChange={(e) => setSelectedQuery(e.target.value)}
            >
              {queries.map((query) => (
                <option key={query.query_id}>{query.query_id}</option>
              ))}
            </Select>
          </label>
          <AnalysisOptions
            system={system}
            condition={condition}
            onConditionChange={setCondition}
            testAfter={testAfter}
            onTestAfterChange={setTestAfter}
            confirmDatabase={confirmSql}
            onConfirmDatabaseChange={setConfirmSql}
            disabled={busy || !canAnalyze}
          />
          {!canAnalyze && <p className="notice notice-blue">{statusReason}</p>}
          {canAnalyze && (
            <p className="text-xs muted">
              <strong>{system.provider ?? "Ingestelde provider"}</strong> ·{" "}
              <span className="mono">
                {system.configured_model ?? "ingesteld op de server"}
              </span>
              . Eén verzoek na jouw bevestiging.
            </p>
          )}
          <label className="check-field">
            <input
              type="checkbox"
              checked={confirmModel}
              onChange={(e) => setConfirmModel(e.target.checked)}
              disabled={!canAnalyze}
              required
            />
            <span>
              Ik ga akkoord met mogelijke AI-kosten en geef toestemming om de
              gekozen SQL en context naar het AI-model te sturen.
            </span>
          </label>
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Annuleren
            </Button>
            <Button type="submit" disabled={!canStart}>
              {busy ? "In wachtrij zetten…" : "Analyse starten"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
