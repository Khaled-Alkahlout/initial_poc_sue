import type { Stage } from "@/lib/api/contracts";
import { StatusBadge } from "@/components/shared/status";
import { milliseconds } from "@/lib/formatters";
import { ChevronDown } from "lucide-react";

const definition = [
  "Queryselectie",
  "Context",
  "LLM-generatie",
  "SQL-controle",
  "Correctheid",
  "Benchmark",
  "Resultaat",
];
export function PipelineVisualizer({
  stages,
  compact = false,
}: {
  stages?: Stage[];
  compact?: boolean;
}) {
  if (!stages)
    return (
      <ol
        className="pipeline pipeline-compact"
        aria-label="Pipelineonderdelen, geen actuele runstatus"
      >
        {definition.map((label, index) => (
          <li key={label}>
            <span className="stage-number">{index + 1}</span>
            <h3>{label}</h3>
          </li>
        ))}
      </ol>
    );
  return (
    <ol
      className={
        compact ? "pipeline pipeline-compact" : "pipeline pipeline-detail"
      }
      aria-label="Pipelinefases"
    >
      {stages.map((stage, index) => (
        <li key={stage.id}>
          {compact ? (
            <>
              <span className="stage-number">{index + 1}</span>
              <h3>{stage.label}</h3>
              <StatusBadge status={stage.status} />
            </>
          ) : (
            <details>
              <summary>
                <span className="stage-number">{index + 1}</span>
                <h3>{stage.label}</h3>
                <span className="stage-duration">
                  {stage.duration_ms == null
                    ? "Duur niet vastgelegd"
                    : milliseconds(stage.duration_ms)}
                </span>
                <StatusBadge status={stage.status} />
                <ChevronDown size={13} />
              </summary>
              <p className="stage-note">
                {stage.note}
                <br />
                <span>
                  Bron:{" "}
                  {stage.origin === "historical"
                    ? "historisch artefact"
                    : stage.origin === "measured"
                      ? "testmeting"
                      : "huidige uitvoering"}
                  .
                </span>
              </p>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}
