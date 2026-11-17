"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Info,
  LoaderCircle,
} from "lucide-react";
import { api } from "@/lib/api/client";
import type { Attempt, Run, SystemStatus } from "@/lib/api/contracts";
import { compareBenchmark } from "@/lib/benchmark";
import { conditionLabels, count, dateTime } from "@/lib/formatters";
import { useApi } from "@/hooks/use-api";
import { PageHeader } from "@/components/shared/page-header";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/shared/states";
import { LifecycleBadge, SourceBadge } from "@/components/shared/status";
import { JsonInspector } from "@/components/shared/json-inspector";
import { TechnicalDetails } from "@/components/shared/technical-details";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/fields";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import { SqlViewer } from "@/components/queries/sql-viewer";
import { AttemptPanels } from "@/components/evaluation/attempt-panels";
import { FeedbackForm } from "@/components/evaluation/feedback-form";
import { ValidateProposal } from "@/features/runs/validate-proposal";
import { RetryAnalysis } from "./retry-analysis";

const active = (run: Run) =>
  run.lifecycle === "PENDING" || run.lifecycle === "RUNNING";

export function RunDetail({
  initial,
  initialAttemptId,
  onUpdate,
  baselineSql,
  inline = false,
  system,
  validation,
}: {
  initial: Run;
  initialAttemptId?: string;
  onUpdate?: (run: Run) => void;
  baselineSql?: string | null;
  inline?: boolean;
  system?: SystemStatus;
  validation?: Attempt;
}) {
  const loader = useCallback(() => api.getRun(initial.id), [initial.id]);
  const { data: run, error, refresh } = useApi(loader, initial, active);
  const [attemptId, setAttemptId] = useState(initialAttemptId);

  useEffect(() => {
    if (run && onUpdate) onUpdate(run);
  }, [run, onUpdate]);

  if (!run) return <LoadingState />;
  const attempt =
    run.attempts.find(({ id }) => id === attemptId) ?? run.attempts[0];
  const measured = validation ?? attempt;
  const historical = run.mode === "historical" || run.mode === "replay";
  const analysisStages = attempt?.stages.length ? attempt.stages : run.stages;
  const stages = analysisStages.map((stage) =>
    ["input_check", "static", "correctness", "benchmark", "result"].includes(
      stage.id,
    )
      ? (validation?.stages.find((check) => check.id === stage.id) ?? stage)
      : stage,
  );
  const validationEligible =
    !active(run) &&
    (run.mode === "analysis" ||
      (run.mode === "live" &&
        (attempt?.outcome === "error" ||
          attempt?.outcome === "inconclusive"))) &&
    !!attempt?.proposed_sql &&
    attempt.outcome !== "safety_rejected";
  const validationAction = validation ? (
    <Link className="text-link" href={"/runs/" + validation.run_id}>
      Open validatierun <ArrowUpRight size={13} />
    </Link>
  ) : validationEligible ? (
    <a className="text-link" href="#validate-proposal">
      Voorstel valideren
    </a>
  ) : null;
  const details = (
    <>
      <Card>
        <CardHeader title="Runmetadata" />
        <div className="panel-body stack">
          <dl className="kv-list">
            <div>
              <dt>Run-ID</dt>
              <dd className="mono">{run.id}</dd>
            </div>
            <div>
              <dt>Gestart</dt>
              <dd>{dateTime(run.created_at)}</dd>
            </div>
            <div>
              <dt>Eindtijd</dt>
              <dd>{dateTime(run.completed_at)}</dd>
            </div>
            <div>
              <dt>Pogingen</dt>
              <dd>{count(run.attempt_count)}</dd>
            </div>
            <div>
              <dt>
                {run.mode === "historical" ? "Historische" : "Nieuwe"} externe
                modelrequests
              </dt>
              <dd>{count(run.model_requests)}</dd>
            </div>
            <div>
              <dt>
                {run.mode === "replay" ? "Historische" : "Run"} input- /
                outputtokens
              </dt>
              <dd>
                {count(run.input_tokens)} / {count(run.output_tokens)}
              </dd>
            </div>
          </dl>
          {run.selection && (
            <JsonInspector
              value={run.selection}
              title="Selectiesnapshot · gesimuleerde workload"
            />
          )}
          {run.limitations.length > 0 && (
            <details className="inspector">
              <summary>Interpretatie en beperkingen</summary>
              <ul className="advice-list">
                {run.limitations.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </Card>
    </>
  );

  return (
    <div className="stack run-detail">
      {!inline && (
        <>
          <Link href="/runs" className="text-link">
            <ArrowLeft size={14} /> Alle pipeline-runs
          </Link>
          <PageHeader
            title={run.query_ids.length === 1 ? run.query_ids[0] : run.title}
            description={run.title + " · " + dateTime(run.created_at)}
            action={
              <div className="badge-row">
                <SourceBadge source={run.mode} />
                <LifecycleBadge status={run.lifecycle} />
              </div>
            }
          />
        </>
      )}
      {error && <ErrorState message={error} retry={refresh} />}
      {run.error && (
        <p role="alert" className="notice notice-error">
          {run.error}
        </p>
      )}
      {historical && (
        <div className="notice notice-blue provenance-notice">
          <Info size={16} />
          <p>
            <strong>
              {run.mode === "replay"
                ? "Historische replay."
                : "Historisch experiment."}
            </strong>{" "}
            Modeluitvoer en metingen komen uit opgeslagen experimenten.
            {run.source_id && (
              <>
                {" "}
                <Link className="text-link" href={"/runs/" + run.source_id}>
                  Open bronrun <ArrowUpRight size={12} />
                </Link>
              </>
            )}
          </p>
        </div>
      )}
      {(run.mode === "mock" || run.mode === "live_mock") && (
        <div className="notice notice-blue provenance-notice">
          <Info size={16} />
          <p>
            <strong>Demo met mockmodel.</strong> Het voorstel is een kopie van
            de oorspronkelijke SQL.
          </p>
        </div>
      )}
      {run.mode === "validate" && run.source_id && (
        <div className="page-actions">
          <Link className="text-link" href={"/runs/" + run.source_id}>
            Modelanalyse, promptcontext en kosten <ArrowUpRight size={13} />
          </Link>
          {run.query_ids[0] && (
            <Link
              className="text-link"
              href={"/queries/" + encodeURIComponent(run.query_ids[0])}
            >
              Terug naar de query <ArrowRight size={13} />
            </Link>
          )}
        </div>
      )}

      <Card>
        <CardHeader
          title="Pipelinevoortgang"
          description={
            active(run)
              ? "Status van de backend. Deze weergave werkt automatisch bij."
              : validation
                ? "De testfases komen uit de gekoppelde validatierun."
                : undefined
          }
          action={
            inline && (
              <div className="badge-row">
                <SourceBadge source={run.mode} />
                <LifecycleBadge status={run.lifecycle} />
              </div>
            )
          }
        />
        {active(run) && (
          <p className="run-live-status" role="status">
            {run.lifecycle === "RUNNING" && (
              <LoaderCircle size={15} className="spin" />
            )}
            {run.lifecycle === "RUNNING"
              ? "Uitvoering bezig…"
              : "Taak staat in de wachtrij."}
          </p>
        )}
        <PipelineVisualizer stages={stages} />
      </Card>
      {run.attempts.length > 1 && (
        <label className="field attempt-picker">
          <span>Inspecteer poging</span>
          <Select
            value={attempt?.id ?? ""}
            onChange={(event) => setAttemptId(event.target.value)}
          >
            {run.attempts.map((value) => (
              <option key={value.id} value={value.id}>
                {value.query_id} ·{" "}
                {conditionLabels[value.condition ?? ""] ??
                  value.condition ??
                  "Geen contextconditie"}{" "}
                · herhaling {value.repetition ?? "—"} ·{" "}
                {value.raw_verdict ?? value.outcome}
              </option>
            ))}
          </Select>
        </label>
      )}
      {attempt ? (
        <AttemptPanels
          key={attempt.id}
          attempt={attempt}
          measured={validation}
          validationAction={validationAction}
          technical={details}
        />
      ) : (
        <>
          <EmptyState
            title={active(run) ? "Resultaten volgen" : "Geen poging opgeslagen"}
            description={
              active(run)
                ? "SQL en uitkomsten verschijnen zodra de run een resultaat opslaat."
                : "Bekijk de pipeline en runmetadata voor de geregistreerde status."
            }
          />
          {baselineSql && (
            <SqlViewer
              sql={baselineSql}
              title="Original SQL Query"
              label="SQL-fixture"
            />
          )}
          <TechnicalDetails description="Runmetadata">
            {details}
          </TechnicalDetails>
        </>
      )}
      <FeedbackForm
        targetId={run.id}
        targetType="run"
        showBenchmarkWarning={!measured || !compareBenchmark(measured)}
      />
      {run.mode === "analysis" && run.lifecycle === "FAILED" && (
        <RetryAnalysis run={run} />
      )}
      {validationEligible && <ValidateProposal run={run} system={system} />}
    </div>
  );
}
