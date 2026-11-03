import type { Attempt } from "@/lib/api/contracts";
import { count, milliseconds } from "@/lib/formatters";
import { Card, CardHeader } from "@/components/ui/card";
import {
  Badge,
  OutcomeBadge,
  SourceBadge,
  StatusBadge,
} from "@/components/shared/status";
import { EmptyState } from "@/components/shared/states";
import { JsonInspector } from "@/components/shared/json-inspector";
import { SqlComparison } from "@/components/queries/sql-viewer";

export function PerformanceComparison({ attempt }: { attempt: Attempt }) {
  const result = attempt.benchmark;
  const supported =
    attempt.correctness === "passed" &&
    ["passed", "warning"].includes(result.status);
  return (
    <Card>
      <CardHeader
        title="Performancevergelijking"
        action={<SourceBadge source={result.origin} />}
      />
      {supported ? (
        <div className="panel-body stack">
          <dl className="kv-list">
            <div>
              <dt>Mediaan origineel</dt>
              <dd>{milliseconds(result.original_ms)}</dd>
            </div>
            <div>
              <dt>Mediaan voorstel</dt>
              <dd>{milliseconds(result.proposed_ms)}</dd>
            </div>
            <div>
              <dt>Gemeten speedup</dt>
              <dd>
                <strong>{count(result.speedup)}×</strong>
              </dd>
            </div>
            <div>
              <dt>Verschil in mediane duur</dt>
              <dd>
                {result.reduction_percent == null
                  ? "Niet beschikbaar"
                  : `${count(Math.abs(result.reduction_percent))}% ${result.reduction_percent >= 0 ? "lager" : "hoger"}`}
              </dd>
            </div>
            <div>
              <dt>IQR origineel / voorstel</dt>
              <dd>
                {count(result.original_iqr_ms)} /{" "}
                {count(result.proposed_iqr_ms)} ms
              </dd>
            </div>
            <div>
              <dt>Herhalingen</dt>
              <dd>{count(result.repetitions)}</dd>
            </div>
          </dl>
          <p className="muted text-xs">
            Gemeten op de testdataset. Dit is geen modelvoorspelling of
            productiegoedkeuring. De totale benchmarkduur is niet afzonderlijk
            vastgelegd.
          </p>
        </div>
      ) : (
        <EmptyState
          title="Geen onderbouwde performanceconclusie"
          description="Er is geen bruikbare benchmark, of de correctheid is niet voldoende vastgesteld. Eventuele ruwe meetvelden staan bij de metadata."
        />
      )}
    </Card>
  );
}
export function CorrectnessComparison({ attempt }: { attempt: Attempt }) {
  return (
    <Card>
      <CardHeader
        title="Correctheidscontrole"
        action={<StatusBadge status={attempt.correctness} />}
      />
      <div className="panel-body stack">
        <dl className="kv-list">
          <div>
            <dt>Geteste parametersets</dt>
            <dd>{count(attempt.parameter_sets)}</dd>
          </div>
          <div>
            <dt>Afwijkend / niet afgerond</dt>
            <dd>{count(attempt.failing_parameter_sets)}</dd>
          </div>
          <div>
            <dt>Legacy-oordeel</dt>
            <dd className="mono">
              {attempt.raw_verdict ?? "Niet beschikbaar"}
            </dd>
          </div>
        </dl>
        <p className="muted text-xs">
          {attempt.detail ||
            "Geen afwijkingsdetails geregistreerd. Gelijkheid geldt uitsluitend binnen de geteste voorwaarden."}
        </p>
        <OutcomeBadge outcome={attempt.outcome} />
      </div>
    </Card>
  );
}
export function ContextViewer({ attempt }: { attempt: Attempt }) {
  return (
    <Card>
      <CardHeader
        title="Context voor het model"
        description={attempt.condition ?? "Contextconditie niet vastgelegd"}
      />
      <div className="panel-body context-grid">
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
                <pre className="context-text">{section.text}</pre>
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
export function AttemptPanels({ attempt }: { attempt: Attempt }) {
  return (
    <div className="stack">
      <SqlComparison
        original={attempt.original_sql}
        proposed={attempt.proposed_sql}
      />
      <div className="grid-two">
        <CorrectnessComparison attempt={attempt} />
        <PerformanceComparison attempt={attempt} />
      </div>
      <ContextViewer attempt={attempt} />
      <Card>
        <CardHeader title="Model- en responsegegevens" />
        <div className="panel-body stack">
          <dl className="kv-list">
            <div>
              <dt>Model-ID uit het artefact</dt>
              <dd className="mono">{attempt.model ?? "Niet vastgelegd"}</dd>
            </div>
            <div>
              <dt>Input / outputtokens</dt>
              <dd>
                {count(attempt.input_tokens)} / {count(attempt.output_tokens)}
              </dd>
            </div>
            <div>
              <dt>Vastgelegde requestduur</dt>
              <dd>
                {attempt.llm_seconds == null
                  ? "Niet vastgelegd"
                  : `${count(attempt.llm_seconds)} s`}
              </dd>
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
            <div>
              <dt>API-kosten</dt>
              <dd>Niet betrouwbaar vastgelegd</dd>
            </div>
          </dl>
          {attempt.explanation ? (
            <details className="inspector">
              <summary>Opgeslagen modelantwoord · geredigeerd</summary>
              <pre>{attempt.explanation}</pre>
            </details>
          ) : (
            <p className="muted text-xs">Geen modelantwoord beschikbaar.</p>
          )}
        </div>
      </Card>
      <JsonInspector
        value={attempt.raw_record}
        title="Oorspronkelijke resultaatvelden · geredigeerd"
      />
    </div>
  );
}
