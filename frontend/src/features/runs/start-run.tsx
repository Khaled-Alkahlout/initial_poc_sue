"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { Query, RunInput, SystemStatus } from "@/lib/api/contracts";
import { conditionLabels } from "@/lib/formatters";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Select } from "@/components/ui/fields";
import { Button } from "@/components/ui/button";

export function StartRun({
  queries,
  system,
  label = "Demo starten",
  queryId,
  sourceId,
}: {
  queries: Query[];
  system: SystemStatus;
  label?: string;
  queryId?: string;
  sourceId?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState<RunInput>({
    mode: "replay",
    query_id: queryId ?? queries[0]?.query_id ?? "",
    condition: "C2_schema",
    source_id: sourceId,
    confirm_sql: false,
    confirm_external_model: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const capability = system.run_modes.find((item) => item.id === input.mode);
  function changeMode(mode: RunInput["mode"]) {
    setInput({
      ...input,
      mode,
      condition: mode === "mock" ? "C1_query" : "C2_schema",
      confirm_sql: false,
      confirm_external_model: false,
    });
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const run = await api.startRun(input);
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
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Play size={14} />
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Gecontroleerde run starten"
        description="Kies een bestaande querycase. Replay gebruikt historische resultaten en voert geen SQL of modelrequest uit."
      >
        <form className="form-grid" onSubmit={submit}>
          <label className="field">
            <span>Querycase</span>
            <Select
              value={input.query_id}
              onChange={(e) => setInput({ ...input, query_id: e.target.value })}
            >
              {queries.map((query) => (
                <option key={query.query_id}>{query.query_id}</option>
              ))}
            </Select>
          </label>
          <label className="field">
            <span>Uitvoermodus</span>
            <Select
              value={input.mode}
              onChange={(e) => changeMode(e.target.value as RunInput["mode"])}
            >
              {system.run_modes.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                  disabled={!item.available}
                >
                  {item.label}
                  {!item.available ? " · niet geconfigureerd" : ""}
                </option>
              ))}
            </Select>
          </label>
          <p className="notice notice-blue">{capability?.reason}</p>
          <label className="field">
            <span>Contextconditie</span>
            <Select
              value={input.condition}
              onChange={(e) =>
                setInput({
                  ...input,
                  condition: e.target.value as RunInput["condition"],
                })
              }
            >
              {Object.entries(conditionLabels).map(([key, text]) => (
                <option
                  key={key}
                  value={key}
                  disabled={input.mode === "mock" && key !== "C1_query"}
                >
                  {text}
                </option>
              ))}
            </Select>
          </label>
          {capability?.executes_sql && (
            <label className="check-field">
              <input
                type="checkbox"
                checked={input.confirm_sql}
                onChange={(e) =>
                  setInput({ ...input, confirm_sql: e.target.checked })
                }
                required
              />
              <span>
                Ik bevestig SQL-uitvoering op de geïsoleerde testdatabase,
                inclusief eventuele profiling en benchmarks.
              </span>
            </label>
          )}
          {capability?.external_model && (
            <label className="check-field">
              <input
                type="checkbox"
                checked={input.confirm_external_model}
                onChange={(e) =>
                  setInput({
                    ...input,
                    confirm_external_model: e.target.checked,
                  })
                }
                required
              />
              <span>
                Ik bevestig één extern modelrequest met mogelijke kosten.
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
            <Button type="submit" disabled={busy || !capability?.available}>
              {busy
                ? "In wachtrij zetten…"
                : input.mode === "replay"
                  ? "Replay starten"
                  : "Run starten"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
