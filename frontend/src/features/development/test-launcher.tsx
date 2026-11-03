"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Play, RefreshCw } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { SystemStatus, TestInput } from "@/lib/api/contracts";
import { useApi } from "@/hooks/use-api";
import { LifecycleBadge, StatusBadge } from "@/components/shared/status";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/fields";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/shared/states";

export function TestLauncher({
  system,
  queryIds,
}: {
  system: SystemStatus;
  queryIds: string[];
}) {
  const [input, setInput] = useState<TestInput>({
    suite: "selection",
    query_id: queryIds[0] ?? "top_products",
    confirm_sql: false,
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = system.test_suites.find((suite) => suite.id === input.suite);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await api.runTests(input);
      setJobId(job.id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title="Voer een gecontroleerde test uit"
        description="Vaste allowlist. Eén actieve worker en maximaal één wachtende taak; geen vrije shell- of SQL-invoer."
      />
      <div className="panel-body stack">
        <form className="form-grid !mt-0" onSubmit={submit}>
          <div className="grid-two">
            <label className="field">
              <span>Testsuite</span>
              <Select
                value={input.suite}
                onChange={(e) =>
                  setInput({
                    ...input,
                    suite: e.target.value as TestInput["suite"],
                    confirm_sql: false,
                  })
                }
              >
                {system.test_suites.map((suite) => (
                  <option
                    value={suite.id}
                    key={suite.id}
                    disabled={!suite.available}
                  >
                    {suite.label}
                    {!suite.available ? " · configuratie ontbreekt" : ""}
                  </option>
                ))}
              </Select>
            </label>
            {input.suite === "mutations" && (
              <label className="field">
                <span>Querycase</span>
                <Select
                  value={input.query_id}
                  onChange={(e) =>
                    setInput({ ...input, query_id: e.target.value })
                  }
                >
                  {queryIds.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </Select>
              </label>
            )}
          </div>
          <p className="muted text-xs">{selected?.reason}</p>
          {selected?.executes_sql && (
            <label className="check-field">
              <input
                type="checkbox"
                required
                checked={input.confirm_sql}
                onChange={(e) =>
                  setInput({ ...input, confirm_sql: e.target.checked })
                }
              />
              <span>
                Ik bevestig SQL-uitvoering op de geïsoleerde testdatabase.
              </span>
            </label>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button disabled={busy || !selected?.available} type="submit">
              <Play size={13} />
              {busy ? "In wachtrij zetten…" : "Tests uitvoeren"}
            </Button>
          </div>
        </form>
        {jobId && <ExecutionWatch key={jobId} id={jobId} />}
      </div>
    </Card>
  );
}
const active = (value: { lifecycle: string }) =>
  ["PENDING", "RUNNING"].includes(value.lifecycle);
function ExecutionWatch({ id }: { id: string }) {
  const loader = useCallback(() => api.getExecution(id), [id]);
  const { data, error, refresh } = useApi(loader, undefined, active);
  const router = useRouter();
  if (error) return <ErrorState message={error} retry={refresh} />;
  if (!data) return <p role="status">Teststatus ophalen…</p>;
  return (
    <div className="stack">
      <div className="flex items-center justify-between gap-3">
        <LifecycleBadge status={data.lifecycle} />
        <span className="mono muted">{id.slice(0, 8)}</span>
      </div>
      {data.error && (
        <p className="form-error" role="alert">
          {data.error}
        </p>
      )}
      {data.tests.length > 0 && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Nieuwe testresultaten</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.tests.map((test) => (
                  <tr key={test.id}>
                    <td>
                      <Link
                        className="mono"
                        href={`/development/tests/${encodeURIComponent(test.id)}`}
                      >
                        {test.name}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge status={test.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button variant="outline" onClick={() => router.refresh()}>
            <RefreshCw size={13} />
            Testmatrix verversen
          </Button>
        </>
      )}
    </div>
  );
}
