"use client";
import { useCallback, useState } from "react";
import type { z } from "zod";
import { api } from "@/lib/api/client";
import type { queriesSchema } from "@/lib/api/contracts";
import { useApi } from "@/hooks/use-api";
import { QueryTable } from "@/components/queries/query-table";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/fields";
import { ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/shared/status";

export function QueryExplorer({
  initial,
}: {
  initial: z.infer<typeof queriesSchema>;
}) {
  const [topK, setTopK] = useState(2);
  const [excluded, setExcluded] = useState("");
  const loader = useCallback(
    () => api.getQueries(topK, excluded ? [excluded] : []),
    [topK, excluded],
  );
  const { data, error, refresh } = useApi(loader, initial);
  return (
    <div className="stack">
      <div className="notice notice-amber">
        Alle workloadcijfers zijn gesimuleerd. Het querybudget wordt door de
        bestaande Python-module toegepast; tabelsortering verandert de
        backendrang niet.
      </div>
      {error && <ErrorState message={error} retry={refresh} />}
      <Card>
        <CardHeader
          title="Queryselectie & impact"
          description="Bekijk dezelfde beslissingen die vóór contextopbouw en modelcalls worden toegepast."
          action={
            <div className="flex items-center gap-3">
              <Badge tone="amber">Mocktelemetrie</Badge>
              <label className="flex items-center gap-2 text-xs muted">
                Budget
                <Select
                  aria-label="Maximum geselecteerde queries"
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                >
                  {[0, 1, 2, 3, 4].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </Select>
              </label>
            </div>
          }
        />
        <div className="toolbar">
          <label className="flex items-center gap-3 text-xs muted">
            Query uitsluiten voor deze weergave
            <Select
              aria-label="Query uitsluiten van selectie"
              value={excluded}
              onChange={(e) => setExcluded(e.target.value)}
            >
              <option value="">Geen uitsluiting</option>
              {initial.queries.map((query) => (
                <option key={query.query_id} value={query.query_id}>
                  {query.query_id}
                </option>
              ))}
            </Select>
          </label>
        </div>
        <QueryTable queries={data?.queries ?? initial.queries} />
      </Card>
    </div>
  );
}
