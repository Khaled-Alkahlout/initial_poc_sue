import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import type { QueryDetail, SystemStatus } from "@/lib/api/contracts";
import { PageHeader } from "@/components/shared/page-header";
import { OutcomeBadge, SourceBadge } from "@/components/shared/status";
import {
  QueryDecision,
  QueryMetrics,
} from "@/components/queries/query-decision";
import { SqlViewer } from "@/components/queries/sql-viewer";
import { ContextViewer } from "@/components/evaluation/attempt-panels";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/states";
import { conditionLabels } from "@/lib/formatters";
import { StartRun } from "@/features/runs/start-run";

export function QueryDetailView({
  query,
  system,
}: {
  query: QueryDetail;
  system: SystemStatus;
}) {
  const context =
    query.attempts.find((attempt) => attempt.condition === "C4_stats") ??
    query.attempts[0];
  return (
    <div className="stack">
      <Link href="/queries" className="text-link">
        <ArrowLeft size={13} />
        Alle query&apos;s
      </Link>
      <PageHeader
        eyebrow="POC / QUERY-INSPECTIE"
        title={query.query_id}
        description="Inspecteer SQL, selectiebeslissingen en beschikbare resultaten. Het openen van deze pagina voert niets uit."
        action={
          <StartRun
            queries={[query]}
            queryId={query.query_id}
            system={system}
          />
        }
      />
      <SqlViewer sql={query.sql} title="Originele SQL · bestaande fixture" />
      <div className="grid-two">
        <QueryMetrics query={query} />
        <QueryDecision query={query} />
      </div>
      {context ? (
        <ContextViewer attempt={context} />
      ) : (
        <EmptyState
          title="Geen opgeslagen context"
          description="Er is geen context opgehaald; queryinspectie voert zelf geen databasequery uit."
        />
      )}
      <Card>
        <CardHeader
          title="Beschikbare voorstellen & tests"
          description="Een poging is geen onafhankelijke querycase. De technische conclusie komt uit de backendadapter."
          action={<SourceBadge source="historical" />}
        />
        {query.attempts.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Kandidaat</th>
                  <th>Context</th>
                  <th>Resultaat</th>
                  <th>Bron</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {query.attempts.map((attempt) => (
                  <tr key={attempt.id}>
                    <td className="mono">{attempt.candidate}</td>
                    <td>
                      {conditionLabels[attempt.condition ?? ""] ??
                        "Niet vastgelegd"}
                    </td>
                    <td>
                      <OutcomeBadge outcome={attempt.outcome} />
                    </td>
                    <td>
                      <SourceBadge source={attempt.origin} />
                    </td>
                    <td>
                      <Link
                        className="text-link"
                        href={`/runs/${attempt.run_id}?attempt=${encodeURIComponent(attempt.id)}`}
                      >
                        Inspecteren <ArrowUpRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="Nog geen voorstellen" />
        )}
      </Card>
    </div>
  );
}
