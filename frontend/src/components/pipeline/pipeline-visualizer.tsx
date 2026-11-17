import type { Stage } from "@/lib/api/contracts";
import { StatusBadge } from "@/components/shared/status";
import { milliseconds, sourceLabels } from "@/lib/formatters";
import {
  Check,
  ChevronDown,
  Circle,
  Clock3,
  FileCode2,
  Filter,
  Flag,
  Hourglass,
  Layers,
  Minus,
  ShieldCheck,
  Sparkles,
  Timer,
  TriangleAlert,
  X,
} from "lucide-react";

const definition = [
  { id: "selection", label: "Queryselectie", icon: Filter },
  { id: "input_check", label: "Originele SQL", icon: FileCode2 },
  { id: "context", label: "Context", icon: Layers },
  { id: "generation", label: "LLM-generatie", icon: Sparkles },
  { id: "static", label: "SQL-controle", icon: FileCode2 },
  { id: "correctness", label: "Correctheid", icon: ShieldCheck },
  { id: "benchmark", label: "Benchmark", icon: Timer },
  { id: "result", label: "Resultaat", icon: Flag },
];

const stateIcon = {
  pending: Hourglass,
  running: Clock3,
  passed: Check,
  failed: X,
  warning: TriangleAlert,
  inconclusive: Circle,
  skipped: Minus,
  error: X,
};

export function PipelineVisualizer({ stages }: { stages?: Stage[] }) {
  if (!stages) {
    return (
      <ol
        className="pipeline pipeline-compact"
        aria-label="Pipelineonderdelen, geen actuele runstatus"
      >
        {definition.map(({ id, label, icon: Icon }) => (
          <li key={id}>
            <span className="stage-icon">
              <Icon size={18} />
            </span>
            <span>{label}</span>
          </li>
        ))}
      </ol>
    );
  }
  if (!stages.length)
    return <p className="panel-body muted">Geen fasestatus geregistreerd.</p>;
  return (
    <ol
      className="pipeline pipeline-compact pipeline-status"
      aria-label="Pipelinefases"
    >
      {stages.map((stage) => {
        const label =
          definition.find(({ id }) => id === stage.id)?.label ?? stage.label;
        const Icon = stateIcon[stage.status];
        return (
          <li
            key={stage.id}
            data-status={stage.status}
            aria-current={stage.status === "running" ? "step" : undefined}
          >
            <details>
              <summary>
                <span className="stage-icon">
                  <Icon size={17} />
                </span>
                <span className="stage-caption">
                  {label}
                  <ChevronDown size={12} />
                </span>
                <StatusBadge status={stage.status} />
              </summary>
              <div className="stage-note">
                <p>{stage.note}</p>
                <small>
                  {sourceLabels[stage.origin] ?? stage.origin}
                  {" · "}
                  {stage.duration_ms == null
                    ? "Duur niet vastgelegd"
                    : milliseconds(stage.duration_ms)}
                </small>
              </div>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
