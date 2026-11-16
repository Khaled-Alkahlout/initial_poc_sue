import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Query } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/states";
import { Badge, SourceBadge } from "@/components/shared/status";
import { SqlPreview } from "./sql-viewer";

export function PriorityTable({ queries }: { queries: Query[] }) {
  return (
    <Card>
      <CardHeader
        title="Query’s op prioriteit"
        description="Volg de rangschikking op totale uitvoeringstijd in het meetvenster."
        action={
          <Link href="/queries" className="text-link">
            Alle query’s <ArrowRight size={14} />
          </Link>
        }
      />
      {queries.length ? (
        <div className="table-scroll">
          <table className="priority-table">
            <thead>
              <tr>
                <th>Query</th>
                <th>Prioriteit</th>
                <th className="numeric">Gemiddeld</th>
                <th className="numeric">Uitvoeringen</th>
                <th className="numeric">Totale impact</th>
                <th>Analyse</th>
              </tr>
            </thead>
            <tbody>
              {queries.slice(0, 10).map((query) => (
                <tr key={query.query_id}>
                  <td>
                    <Link
                      className="query-link mono"
                      href={"/queries/" + encodeURIComponent(query.query_id)}
                    >
                      {query.query_id} <ArrowRight size={13} />
                    </Link>
                    <SqlPreview sql={query.sql} />
                  </td>
                  <td>
                    <span className="rank">{query.rank ?? "—"}</span>
                  </td>
                  <td className="numeric">
                    {query.mean_execution_time_ms == null
                      ? "—"
                      : count(query.mean_execution_time_ms) + " ms"}
                  </td>
                  <td className="numeric">{count(query.calls)}</td>
                  <td className="numeric">
                    {query.impact_ms == null
                      ? "—"
                      : count(query.impact_ms) + " ms"}
                  </td>
                  <td>
                    <span className="query-analysis">
                      {query.analyzed
                        ? query.analysis_count + " opgeslagen"
                        : "Nog geen analyse"}
                    </span>
                    <div className="badge-row">
                      <SourceBadge
                        source={query.is_synthetic ? "synthetic" : "measured"}
                      />
                      {query.has_proposal && (
                        <Badge tone="brand">SQL-voorstel</Badge>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="Geen querypatronen gevonden" />
      )}
    </Card>
  );
}
