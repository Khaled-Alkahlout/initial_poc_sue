"use client";
import Link from "next/link";
import { useCallback, useState, useEffect } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, Info } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Run } from "@/lib/api/contracts";
import { conditionLabels, count, dateTime } from "@/lib/formatters";
import { useApi } from "@/hooks/use-api";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState, LoadingState } from "@/components/shared/states";
import {
  LifecycleBadge,
  OutcomeBadge,
  SourceBadge,
} from "@/components/shared/status";
import { JsonInspector } from "@/components/shared/json-inspector";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/fields";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import { AttemptPanels } from "@/components/evaluation/attempt-panels";
import { FeedbackForm } from "@/components/evaluation/feedback-form";
import { ValidateProposal } from "@/features/runs/validate-proposal";
import { RetryAnalysis } from "./retry-analysis";

const active = (run: Run) => ["PENDING", "RUNNING"].includes(run.lifecycle);
export function RunDetail({
  initial,
  initialAttemptId,
  onUpdate,
  rewriteAction,
}: {
  initial: Run;
  initialAttemptId?: string;
  onUpdate?: (run: Run) => void;
  rewriteAction?: ReactNode;
}) {
  const loader = useCallback(() => api.getRun(initial.id), [initial.id]);
  const { data: run, error, refresh } = useApi(loader, initial, active);
  useEffect(() => {
    if (run && onUpdate) onUpdate(run);
  }, [run, onUpdate]);
  const [index, setIndex] = useState(() =>
    Math.max(
      0,
      initial.attempts.findIndex((attempt) => attempt.id === initialAttemptId),
    ),
  );
  if (!run) return <LoadingState />;
  const attempt = run.attempts[index] ?? run.attempts[0];
  return (
    <div className="stack">
      <Link href="/runs" className="text-link">
        <ArrowLeft size={13} />
        Alle pipeline-runs
      </Link>
      <PageHeader
        eyebrow="POC / PIPELINE-INSPECTIE"
        title={run.query_ids.length === 1 ? run.query_ids[0] : run.title}
        description={`${run.title} · ${dateTime(run.created_at)}`}
        action={
          <div className="badge-row">
            <SourceBadge source={run.mode} />
            <LifecycleBadge status={run.lifecycle} />
          </div>
        }
      />
      {error && <ErrorState message={error} retry={refresh} />}
      {run.error && (
        <div className="error-state" role="alert">
          {run.error}
        </div>
      )}
      {["historical", "replay"].includes(run.mode) && (
        <div className="notice notice-amber">
          <Info size={16} />
          <p>
            <strong>
              {run.mode === "replay"
                ? "Historische replay. "
                : "Historisch experiment. "}
            </strong>
            De onderstaande modelresponse en metingen zijn opgeslagen
            resultaten. Er is bij het openen of herafspelen niets opnieuw
            gemeten.
            {run.source_id && (
              <>
                {" "}
                Bron:{" "}
                <Link className="text-link" href={`/runs/${run.source_id}`}>
                  {run.source_id}
                </Link>
                .
              </>
            )}
          </p>
        </div>
      )}
      <div className="summary-strip">
        <span>
          <strong>{run.attempt_count}</strong> pogingen ·{" "}
          <strong>{run.query_ids.length}</strong> querycases
        </span>
        <span>
          <strong>{count(run.model_requests)}</strong>{" "}
          {run.mode === "historical" ? "historische" : "nieuwe"} externe
          modelrequests
        </span>
        <span>
          <strong>
            {count(run.input_tokens)} / {count(run.output_tokens)}
          </strong>{" "}
          {run.mode === "replay" ? "historische" : "geregistreerde"} input- /
          outputtokens
        </span>
      </div>
      {run.attempts.length > 1 && (
        <label className="field">
          <span>Inspecteer poging</span>
          <Select
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
          >
            {run.attempts.map((value, i) => (
              <option key={value.id} value={i}>
                {value.query_id} ·{" "}
                {conditionLabels[value.condition ?? ""] ?? value.condition} ·
                herhaling {value.repetition ?? "—"} · {value.raw_verdict}
              </option>
            ))}
          </Select>
        </label>
      )}
      <Card>
        <CardHeader
          title="Van selectie naar resultaat"
          description="Open een fase voor de status, herkomst en beschikbare duur."
          action={attempt && <OutcomeBadge outcome={attempt.outcome} />}
        />
        <PipelineVisualizer stages={attempt?.stages ?? run.stages} />
      </Card>
      {attempt && (
        <AttemptPanels attempt={attempt} rewriteAction={rewriteAction} />
      )}
      {run.mode === "analysis" && run.lifecycle === "FAILED" && (
        <RetryAnalysis run={run} />
      )}
      {run.mode === "analysis" && attempt && <ValidateProposal run={run} />}
      {run.selection && (
        <JsonInspector
          value={run.selection}
          title="Selectiesnapshot · gesimuleerde workload"
        />
      )}
      <FeedbackForm targetId={run.id} targetType="run" />
      <Card>
        <CardHeader title="Interpretatie en beperkingen" />
        <div className="panel-body">
          <ul className="list-disc pl-4 space-y-2 text-xs muted">
            {run.limitations.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      </Card>
    </div>
  );
}
