"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { Query, SystemStatus } from "@/lib/api/contracts";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Select } from "@/components/ui/fields";
import { Button } from "@/components/ui/button";

export function StartRun({
  queries,
  system,
  label = "POC starten",
  queryId,
}: {
  queries: Query[];
  system: SystemStatus;
  label?: string;
  queryId?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [selectedQuery, setSelectedQuery] = useState(
    queryId ?? queries[0]?.query_id ?? "",
  );
  const [confirmModel, setConfirmModel] = useState(false);
  const [confirmSql, setConfirmSql] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const liveMode = system.run_modes.find((item) => item.id === "live");
  const analysisMode = system.run_modes.find((item) => item.id === "analysis");
  const canValidate = liveMode?.available === true;
  const canAnalyze = canValidate || analysisMode?.available === true;
  const statusReason = canAnalyze
    ? liveMode?.reason
    : (analysisMode?.reason ??
      liveMode?.reason ??
      "AI-analyse is momenteel niet beschikbaar.");
  const canStart =
    canAnalyze &&
    selectedQuery !== "" &&
    confirmModel &&
    (!canValidate || confirmSql) &&
    !busy;
  const startLabel = canValidate ? "Live POC starten" : "AI-analyse starten";

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
        mode: canValidate ? "live" : "analysis",
        query_id: selectedQuery,
        condition: "C1_query",
        confirm_sql: canValidate && confirmSql,
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
        title="POC uitvoeren"
        description="Laat het ingestelde AI-model een SQL-voorstel voor de gekozen query maken."
      >
        <form className="form-grid" onSubmit={submit}>
          <label className="field">
            <span>Querycase</span>
            <Select
              value={selectedQuery}
              onChange={(e) => setSelectedQuery(e.target.value)}
            >
              {queries.map((query) => (
                <option key={query.query_id}>{query.query_id}</option>
              ))}
            </Select>
          </label>
          <div className="field">
            <span>Uitvoermodus</span>
            <strong className="text-sm">Live POC</strong>
          </div>
          <p className="notice notice-blue">
            {canAnalyze && !canValidate && (
              <>
                Je kunt de AI-analyse starten. Correctheid en Benchmark vereisen
                een geconfigureerde testdatabase.{" "}
              </>
            )}
            {statusReason}
          </p>
          {canAnalyze && (
            <p className="text-xs muted">
              Provider:{" "}
              <strong>{system.provider ?? "ingesteld op de server"}</strong> ·
              Model:{" "}
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
              Ik geef toestemming om de gekozen query naar het AI-model te
              sturen en ga akkoord met mogelijke AI-kosten.
            </span>
          </label>
          {canValidate && (
            <label className="check-field">
              <input
                type="checkbox"
                checked={confirmSql}
                onChange={(e) => setConfirmSql(e.target.checked)}
                required
              />
              <span>
                Ik bevestig de read-only correctheidscontrole en benchmark op de
                geïsoleerde testdatabase.
              </span>
            </label>
          )}
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
              {busy ? "In wachtrij zetten…" : startLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
