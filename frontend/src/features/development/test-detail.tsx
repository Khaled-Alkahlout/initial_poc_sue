import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { TestRecord } from "@/lib/api/contracts";
import { dateTime, milliseconds } from "@/lib/formatters";
import { PageHeader } from "@/components/shared/page-header";
import { SourceBadge, StatusBadge } from "@/components/shared/status";
import { JsonInspector } from "@/components/shared/json-inspector";
import { Card, CardHeader } from "@/components/ui/card";
import { AttemptPanels } from "@/components/evaluation/attempt-panels";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import { FeedbackForm } from "@/components/evaluation/feedback-form";

export function TestDetail({ test }: { test: TestRecord }) {
  return (
    <div className="stack">
      <Link href="/development" className="text-link">
        <ArrowLeft size={13} />
        Terug naar testmatrix
      </Link>
      <PageHeader
        eyebrow={`DEVELOPMENT / ${test.component.toUpperCase()}`}
        title={test.name}
        description={test.purpose}
        action={
          <div className="badge-row">
            <SourceBadge source={test.origin} />
            <StatusBadge status={test.status} />
          </div>
        }
      />
      <Card>
        <CardHeader
          title="Verwachting tegenover waarneming"
          description="Technische uitslag en handmatige review zijn afzonderlijke gegevens."
        />
        <div className="panel-body stack">
          <dl className="kv-list">
            <div>
              <dt>Testinput</dt>
              <dd>
                {test.attempt
                  ? "Originele SQL en kandidaat hieronder."
                  : "Niet als runtimeartefact vastgelegd; zie de unittest-ID in de metadata."}
              </dd>
            </div>
            <div>
              <dt>Verwachting</dt>
              <dd>{test.expected ?? "Niet vooraf gedefinieerd"}</dd>
            </div>
            <div>
              <dt>Werkelijke uitkomst</dt>
              <dd className="mono">{test.actual ?? "Niet vastgelegd"}</dd>
            </div>
            <div>
              <dt>Foutclassificatie</dt>
              <dd>
                {test.error_classification ??
                  "Niet van toepassing / niet vastgelegd"}
              </dd>
            </div>
            <div>
              <dt>Duur</dt>
              <dd>{milliseconds(test.duration_ms)}</dd>
            </div>
            <div>
              <dt>Vastgelegd</dt>
              <dd>{dateTime(test.executed_at)}</dd>
            </div>
          </dl>
          {test.detail && <pre className="context-text">{test.detail}</pre>}
          <div className="badge-row">
            {test.query_id && (
              <Link className="text-link" href={`/queries/${test.query_id}`}>
                Query inspecteren
              </Link>
            )}
            {test.run_id && (
              <Link
                className="text-link"
                href={`/runs/${test.run_id}?attempt=${encodeURIComponent(test.id)}`}
              >
                Bijbehorende run
              </Link>
            )}
          </div>
        </div>
      </Card>
      {test.attempt && (
        <>
          <Card>
            <CardHeader title="Geregistreerde pipelinefases" />
            <PipelineVisualizer stages={test.attempt.stages} />
          </Card>
          <AttemptPanels attempt={test.attempt} />
        </>
      )}
      <JsonInspector value={test.metadata} title="Testmetadata" />
      <FeedbackForm targetId={test.id} targetType="test" />
    </div>
  );
}
