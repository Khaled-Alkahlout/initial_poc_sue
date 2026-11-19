import Link from "next/link";
import type { ReactNode } from "react";
import type { Attempt } from "@/lib/api/contracts";
import { count, conditionLabels } from "@/lib/formatters";
import { benchmarkTime } from "@/lib/benchmark";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge, SourceBadge, StatusBadge } from "@/components/shared/status";
import { JsonInspector } from "@/components/shared/json-inspector";
import { TechnicalDetails } from "@/components/shared/technical-details";
import { SqlViewer } from "@/components/queries/sql-viewer";
import { RewriteSummary } from "./rewrite-summary";
import { AIUsage } from "./ai-usage";
import { OptimizationResults } from "./optimization-results";

export function ContextViewer({ attempt }: { attempt: Attempt }) {
  return (
    <Card>
      <CardHeader
        title="Prompts en modelcontext"
        description={
          conditionLabels[attempt.condition ?? ""] ??
          "Modelcontext niet vastgelegd"
        }
      />
      <div className="panel-body context-grid">
        {attempt.system_prompt && (
          <details className="context-item inspector">
            <summary>Verstuurde systeemprompt</summary>
            <pre tabIndex={0}>{attempt.system_prompt}</pre>
          </details>
        )}
        {attempt.user_prompt && (
          <details className="context-item inspector">
            <summary>Verstuurde userprompt</summary>
            <pre tabIndex={0}>{attempt.user_prompt}</pre>
          </details>
        )}
        {attempt.context.length === 0 && (
          <p className="muted text-sm">
            Geen context opgeslagen voor deze poging.
          </p>
        )}
        {attempt.context.map((section) => (
          <details className="context-item" key={section.id}>
            <summary>
              <span>{section.label}</span>
              <Badge
                tone={
                  ["redacted", "truncated"].includes(section.state)
                    ? "amber"
                    : "neutral"
                }
              >
                {
                  {
                    available: "Beschikbaar",
                    unavailable: "Niet beschikbaar",
                    omitted: "Niet opgenomen",
                    redacted: "Geredigeerd",
                    truncated: "Afgekapt",
                  }[section.state]
                }
              </Badge>
            </summary>
            <div>
              <p className="muted text-xs mb-3">{section.note}</p>
              {section.text ? (
                ["query", "previous_candidate"].includes(section.id) ? (
                  <SqlViewer sql={section.text} title={section.label} />
                ) : (
                  <pre
                    className="context-text"
                    tabIndex={0}
                    aria-label={section.label}
                  >
                    {section.text}
                  </pre>
                )
              ) : (
                <p className="muted text-xs">Geen contexttekst beschikbaar.</p>
              )}
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}

function AdviceList({ values }: { values: string[] }) {
  return (
    <ul className="advice-list">
      {values.map((value, index) => (
        <li key={index}>{value}</li>
      ))}
    </ul>
  );
}

function Explanation({ attempt }: { attempt: Attempt }) {
  const title = "Wat is veranderd en waarom?";
  const analysis = attempt.analysis;
  if (!analysis) {
    const explanation = attempt.explanation
      ?.replace(/```[^\r\n]*\r?\n[\s\S]*?```/g, "")
      .split(/\r?\n[ \t]*\r?\n/)
      .map((paragraph) => paragraph.trim())
      .find(
        (paragraph) =>
          paragraph && !/^(?:SELECT|WITH|CREATE|EXPLAIN)\b/i.test(paragraph),
      );
    return (
      <TechnicalDetails title={title}>
        {explanation && (
          <div>
            <Badge tone="brand">Opgeslagen modeluitleg</Badge>
          </div>
        )}
        <p className="muted text-sm legacy-explanation">
          {explanation ??
            "Voor deze poging is geen afzonderlijke modeltoelichting opgeslagen."}
        </p>
      </TechnicalDetails>
    );
  }
  const points = [
    ["Vastgesteld probleem", analysis.problem],
    ["Vermoedelijke oorzaak", analysis.root_cause],
    ...(analysis.rewrite_explanation && attempt.proposed_sql
      ? [["Voorgestelde wijziging", analysis.rewrite_explanation]]
      : []),
    ["Verwachte impact", analysis.expected_benefit],
    ["Onzekerheid", analysis.uncertainty],
  ];
  return (
    <TechnicalDetails title={title}>
      <div>
        <Badge tone="brand">AI-uitleg</Badge>
      </div>
      <div className="explanation-grid">
        {points.map(([title, value]) => (
          <div key={title}>
            <h3>{title}</h3>
            <p>{value}</p>
          </div>
        ))}
        {!!analysis.correctness_risks.length && (
          <div>
            <h3>Risico’s en aannames</h3>
            <AdviceList values={analysis.correctness_risks} />
          </div>
        )}
      </div>
    </TechnicalDetails>
  );
}

export function AttemptPanels({
  attempt,
  measured = attempt,
  validationAction,
  technical,
}: {
  attempt: Attempt;
  measured?: Attempt;
  validationAction?: ReactNode;
  technical?: ReactNode;
}) {
  const { benchmark } = measured;
  const analysis = attempt.analysis;
  return (
    <div className="stack">
      <RewriteSummary attempt={attempt} measured={measured} />
      <Explanation attempt={attempt} />
      <OptimizationResults attempt={measured} action={validationAction} />
      <TechnicalDetails description="Model, tokens, kosten, execution plans en diagnostiek">
        <AIUsage attempt={attempt} />
        {attempt.context.length > 0 && <ContextViewer attempt={attempt} />}
        <Card>
          <CardHeader
            title="Validatie- en benchmarkgegevens"
            action={<SourceBadge source={benchmark.origin} />}
          />
          <div className="panel-body stack">
            <dl className="kv-list">
              <div>
                <dt>Database-dialect</dt>
                <dd>PostgreSQL</dd>
              </div>
              <div>
                <dt>Validatiepoging</dt>
                <dd className="mono">{measured.id}</dd>
              </div>
              <div>
                <dt>Validatoroordeel</dt>
                <dd className="mono">
                  {measured.raw_verdict ?? "Niet beschikbaar"}
                </dd>
              </div>
              <div>
                <dt>Benchmarkstatus</dt>
                <dd>
                  <StatusBadge status={benchmark.status} />
                </dd>
              </div>
              <div>
                <dt>Mediane tijden · origineel / voorstel</dt>
                <dd>
                  {benchmark.original_ms == null
                    ? "—"
                    : benchmarkTime(benchmark.original_ms)}{" "}
                  /{" "}
                  {benchmark.proposed_ms == null
                    ? "—"
                    : benchmarkTime(benchmark.proposed_ms)}
                </dd>
              </div>
              <div>
                <dt>IQR · origineel / voorstel</dt>
                <dd>
                  {count(benchmark.original_iqr_ms)} /{" "}
                  {count(benchmark.proposed_iqr_ms)} ms
                </dd>
              </div>
              <div>
                <dt>Gemeten speedup</dt>
                <dd>
                  {benchmark.speedup == null
                    ? "Niet beschikbaar"
                    : count(benchmark.speedup) + "×"}
                </dd>
              </div>
              <div>
                <dt>Herhalingen</dt>
                <dd>{count(benchmark.repetitions)}</dd>
              </div>
              <div>
                <dt>Ongewijzigde SQL-structuur</dt>
                <dd>
                  {attempt.unchanged == null
                    ? "Niet bepaald"
                    : attempt.unchanged
                      ? "Ja"
                      : "Nee"}
                </dd>
              </div>
            </dl>
            {measured.detail && (
              <p className="muted text-sm">{measured.detail}</p>
            )}
            {analysis && (
              <div className="explanation-grid">
                {!!analysis.validation_recommendations.length && (
                  <div>
                    <h3>Te valideren volgens het model</h3>
                    <AdviceList values={analysis.validation_recommendations} />
                  </div>
                )}
                {!!analysis.missing_context.length && (
                  <div>
                    <h3>Ontbrekende context volgens het model</h3>
                    <AdviceList values={analysis.missing_context} />
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
        {attempt.explanation && (
          <details className="inspector">
            <summary>Opgeslagen modelantwoord · geredigeerd</summary>
            <pre tabIndex={0}>{attempt.explanation}</pre>
          </details>
        )}
        <JsonInspector
          value={attempt.raw_record}
          title="Oorspronkelijke resultaatvelden · geredigeerd"
        />
        {measured.id !== attempt.id && (
          <>
            <JsonInspector
              value={measured.raw_record}
              title="Resultaatvelden van de onafhankelijke validatie"
            />
            <Link className="text-link" href={"/runs/" + measured.run_id}>
              Open validatierun
            </Link>
          </>
        )}
        {technical}
      </TechnicalDetails>
    </div>
  );
}
