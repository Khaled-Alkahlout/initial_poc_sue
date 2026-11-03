import Link from "next/link";
import type { Query } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Card, CardHeader } from "@/components/ui/card";

export function PriorityTable({ queries }: { queries: Query[] }) {
  return (
    <Card>
      <CardHeader
        title="Prioriteit voor onderzoek"
        description="Gesimuleerde workload. Totale tijd = workloadimpact; gemiddelde tijd = latency per uitvoering."
      />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Query</th>
              <th>Gemiddeld · ms</th>
              <th>Uitvoeringen</th>
              <th>Totaal · ms</th>
              <th>Prioriteit</th>
              <th>Actie</th>
            </tr>
          </thead>
          <tbody>
            {queries.slice(0, 10).map((q) => (
              <tr key={q.query_id}>
                <td className="mono">{q.query_id}</td>
                <td>{count(q.mean_execution_time_ms)}</td>
                <td>{count(q.calls)}</td>
                <td>{count(q.impact_ms)}</td>
                <td>{q.rank ?? "—"}</td>
                <td>
                  <Link
                    className="text-link"
                    href={`/queries/${q.query_id}#ai-workspace`}
                  >
                    Analyseworkspace →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
