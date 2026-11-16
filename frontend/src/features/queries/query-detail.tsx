import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import type { QueryDetail, SystemStatus } from "@/lib/api/contracts";
import { PageHeader } from "@/components/shared/page-header";
import { OutcomeBadge, SourceBadge } from "@/components/shared/status";
import {
  QueryDecision,
  QueryMetrics,
} from "@/components/queries/query-decision";
import { ContextViewer } from "@/components/evaluation/attempt-panels";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/states";
import { TechnicalDetails } from "@/components/shared/technical-details";
import { conditionLabels, count, milliseconds } from "@/lib/formatters";
import { StartRun } from "@/features/runs/start-run";
import { AnalysisWorkspace } from "./analysis-workspace";

export function QueryDetailView({
  query,
  system,
}: {
  query: QueryDetail;
  system: SystemStatus;
}) {
  const context = query.attempts.find(
    (attempt) =>
      attempt.origin === "historical" && attempt.condition === "C4_stats",
  );
  return (
    <div className="stack query-detail">
      <Link href="/queries" className="text-link">
        <ArrowLeft size={14} /> Alle query’s
      </Link>
      <div className="query-heading">
        <PageHeader
          title={query.query_id}
          description="Bekijk de query, het voorstel en het beschikbare validatiebewijs."
          action={
            <StartRun
              queries={[query]}
              queryId={query.query_id}
              system={system}
            />
          }
        />
        <div className="query-facts">
          <SourceBadge source={query.is_synthetic ? "synthetic" : "measured"} />
          <dl>
            <div>
              <dt>Prioriteit</dt>
              <dd>{query.rank ?? "—"}</dd>
            </div>
            <div>
              <dt>Gemiddelde duur</dt>
              <dd>{milliseconds(query.mean_execution_time_ms)}</dd>
            </div>
            <div>
              <dt>Uitvoeringen</dt>
              <dd>{count(query.calls)}</dd>
            </div>
          </dl>
        </div>
      </div>
      <div id="ai-workspace">
        <AnalysisWorkspace key={query.query_id} query={query} system={system} />
      </div>
      <TechnicalDetails
        title="Querygegevens"
        description="Workload, selectie en opgeslagen context"
      >
        <div className="grid-two">
          <QueryMetrics query={query} />
          <QueryDecision query={query} />
        </div>
        {context && <ContextViewer attempt={context} />}
      </TechnicalDetails>
      <TechnicalDetails
        title="Analysehistorie voor deze query"
        description={count(query.attempts.length) + " opgeslagen pogingen"}
      >
        <Card>
          <CardHeader title="Voorstellen en tests" />
          {query.attempts.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Kandidaat</th>
                    <th>Context</th>
                    <th>Resultaat</th>
                    <th>Bron</th>
                    <th aria-label="Openen" />
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
                          href={
                            "/runs/" +
                            attempt.run_id +
                            "?attempt=" +
                            encodeURIComponent(attempt.id)
                          }
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
      </TechnicalDetails>
    </div>
  );
}
