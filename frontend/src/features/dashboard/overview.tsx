import Link from "next/link";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Database,
  Filter,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { Overview, SystemStatus } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { SourceBadge } from "@/components/shared/status";
import { TechnicalDetails } from "@/components/shared/technical-details";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import { RunTable } from "@/components/pipeline/run-table";
import { ImpactChart } from "@/components/charts/impact-chart";
import { StartRun } from "@/features/runs/start-run";
import { PriorityTable } from "@/components/queries/priority-table";

export function OverviewDashboard({
  data,
  system,
}: {
  data: Overview;
  system: SystemStatus;
}) {
  const metrics = new Map(data.metrics.map((metric) => [metric.id, metric]));
  const highlights = [
    {
      label: "Querypatronen",
      value: metrics.get("queries")?.value,
      note: "Beschikbaar voor inspectie",
      icon: Database,
    },
    {
      label: "Geselecteerd",
      value: metrics.get("selected")?.value,
      note: "Op basis van demo-workload",
      icon: Filter,
    },
    {
      label: "Query’s met AI-analyse",
      value: data.queries.filter((query) => query.analyzed).length,
      note: "Met opgeslagen modelpogingen",
      icon: Sparkles,
    },
    {
      label: "Geaccepteerde voorstellen",
      value: metrics.get("accepted")?.value,
      note: "Geaccepteerde historische pogingen",
      icon: CheckCheck,
    },
  ];
  const analysis = system.run_modes.find((mode) => mode.id === "analysis");
  const validation = system.run_modes.find((mode) => mode.id === "validate");
  return (
    <div className="stack dashboard">
      <section className="overview-hero" aria-labelledby="overview-title">
        <div>
          <h1 id="overview-title">Overzicht</h1>
          <p>
            Inspecteer SQL, vergelijk AI-voorstellen en bekijk de resultaten van
            de validator.
          </p>
          <div className="page-actions">
            <Button asChild>
              <Link href="/queries">
                Query Explorer <ArrowRight size={16} />
              </Link>
            </Button>
            <StartRun queries={data.queries} system={system} />
          </div>
        </div>
        <div className="overview-system">
          <h2>
            <Activity size={16} /> Lokale omgeving
          </h2>
          <dl>
            <div>
              <dt>AI-analyse</dt>
              <dd>
                <span data-available={analysis?.available === true} />
                {analysis?.available ? "Beschikbaar" : "Niet beschikbaar"}
              </dd>
            </div>
            <div>
              <dt>
                <ShieldCheck size={13} /> Testdatabasevalidatie
              </dt>
              <dd>
                <span data-available={validation?.available === true} />
                {validation?.available ? "Beschikbaar" : "Niet beschikbaar"}
              </dd>
            </div>
          </dl>
          <Link href="/development/architecture">
            Systeemstatus <ArrowUpRight size={13} />
          </Link>
        </div>
      </section>

      <div className="metric-grid" aria-label="Samenvatting">
        {highlights.map(({ label, value, note, icon: Icon }) => (
          <Card className="metric" key={label}>
            <div className="metric-label">
              <span>{label}</span>
              <span className="section-icon">
                <Icon size={18} />
              </span>
            </div>
            <div className="metric-value">{count(value)}</div>
            <p className="metric-note">
              {value == null ? "Niet beschikbaar" : note}
            </p>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader
          title="Optimalisatiepipeline"
          description="Fasen die het systeem ondersteunt. Open een run voor de geregistreerde status."
        />
        <PipelineVisualizer />
      </Card>
      <PriorityTable queries={data.queries} />
      <Card>
        <CardHeader
          title="Recente analyses en tests"
          action={
            <Link className="text-link" href="/runs">
              Alle runs <ArrowRight size={14} />
            </Link>
          }
        />
        <RunTable runs={data.recent_runs} />
      </Card>
      <TechnicalDetails
        title="Workload- en onderzoeksgegevens"
        description="Totale impact en historische modelactiviteit"
      >
        <Card>
          <CardHeader
            title="Gesimuleerde workloadimpact"
            action={<SourceBadge source="synthetic" />}
          />
          <div className="panel-body">
            <ImpactChart queries={data.queries} />
          </div>
        </Card>
        <div className="dashboard-research">
          {data.metrics
            .filter(
              (metric) =>
                !["queries", "selected", "accepted"].includes(metric.id),
            )
            .map((metric) => (
              <div key={metric.id}>
                <strong>
                  {count(metric.value)} · {metric.label}
                </strong>
                <p className="muted">{metric.note}</p>
              </div>
            ))}
        </div>
      </TechnicalDetails>
    </div>
  );
}
