import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Database,
  Filter,
  FlaskConical,
  GitBranch,
  Info,
  Layers,
  Sparkles,
} from "lucide-react";
import type { Overview, SystemStatus } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SourceBadge } from "@/components/shared/status";
import { PageHeader } from "@/components/shared/page-header";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import { RunTable } from "@/components/pipeline/run-table";
import { ImpactChart } from "@/components/charts/impact-chart";
import { StartRun } from "@/features/runs/start-run";

const icons = [Database, Filter, CheckCheck, Sparkles];
export function OverviewDashboard({
  data,
  system,
}: {
  data: Overview;
  system: SystemStatus;
}) {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="POC / DATABASEOPTIMALISATIE"
        title="Overzicht"
        description="Van SQL-query naar een onderbouwd optimalisatievoorstel. Eén genererende agent, gevolgd door onafhankelijke softwarecontroles."
        action={<StartRun queries={data.queries} system={system} />}
      />
      <div className="metric-grid">
        {data.metrics.slice(0, 4).map((metric, index) => {
          const Icon = icons[index];
          return (
            <Card className="metric" key={metric.id}>
              <div className="metric-label">
                <span>{metric.label}</span>
                <Icon size={15} />
              </div>
              <div className="metric-value">{count(metric.value)}</div>
              <p className="metric-note">{metric.note}</p>
              <div className="metric-meta">
                <SourceBadge source={metric.origin} />
              </div>
            </Card>
          );
        })}
      </div>
      <div className="summary-strip">
        {data.metrics.slice(4).map((metric) => (
          <span key={metric.id}>
            <strong>{count(metric.value)}</strong> {metric.label.toLowerCase()}{" "}
            <span>· {metric.note}</span>
          </span>
        ))}
      </div>
      <Card>
        <CardHeader
          title="De optimalisatiepipeline"
          description="Elke fase heeft een eigen verantwoordelijkheid. Schematische weergave; geen actuele uitvoerstatus."
          action={
            <Link className="text-link" href="/development/architecture">
              Architectuur <ArrowUpRight size={13} />
            </Link>
          }
        />
        <PipelineVisualizer />
      </Card>
      <div className="grid-aside">
        <Card>
          <CardHeader
            title="Welke query heeft de meeste impact?"
            description="Gerangschikt op totale uitvoeringstijd, niet alleen op latency."
            action={<SourceBadge source="synthetic" />}
          />
          <div className="panel-body !pb-0 !pl-1">
            <ImpactChart queries={data.queries} />
          </div>
          <p className="chart-footnote">
            Fictieve workloadgegevens. Een snelle query die vaak draait kan meer
            belasting veroorzaken dan één trage uitvoering.
          </p>
          <div className="table-footer">
            <span>
              {data.queries.length} querypatronen · deterministische ranking
            </span>
            <Link href="/queries" className="text-link">
              Query Explorer <ArrowRight size={13} />
            </Link>
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Wat onderzoeken we?"
            description="Een kleine, controleerbare POC."
          />
          <div className="panel-body">
            <ul className="explanation-list">
              <li>
                <Layers size={17} />
                <div>
                  <strong>Context vóór het voorstel</strong>
                  <p>
                    SQL, schema, indexinformatie en beschikbare execution plans
                    helpen de analyse.
                  </p>
                </div>
              </li>
              <li>
                <CheckCheck size={17} />
                <div>
                  <strong>Vertrouwen door controle</strong>
                  <p>
                    Een modelclaim is geen bewijs. Correctheid en performance
                    worden apart beoordeeld.
                  </p>
                </div>
              </li>
              <li>
                <FlaskConical size={17} />
                <div>
                  <strong>Transparante evaluatie</strong>
                  <p>
                    Inspecteer afwijzingen, beperkingen en ontwikkelaarsreviews
                    in Development.
                  </p>
                </div>
              </li>
            </ul>
            <Button className="mt-6 w-full" variant="outline" asChild>
              <Link href="/development">
                Open Development <ArrowUpRight size={13} />
              </Link>
            </Button>
          </div>
        </Card>
      </div>
      <Card>
        <CardHeader
          title="Recente pipeline-runs"
          description="Historische experimenten, replays en nieuwe uitvoeringen blijven herkenbaar gescheiden."
          action={
            <Link className="text-link" href="/runs">
              Alle runs <GitBranch size={13} />
            </Link>
          }
        />
        <RunTable runs={data.recent_runs} />
      </Card>
      <div className="notice">
        <Info size={15} />
        <p>
          <strong>Zo lees je dit dashboard.</strong> Workloadcijfers zijn
          gesimuleerd; experimentele benchmarks zijn historische testmetingen.
          Een geaccepteerd voorstel geldt uitsluitend binnen de geteste
          voorwaarden.
        </p>
      </div>
    </div>
  );
}
