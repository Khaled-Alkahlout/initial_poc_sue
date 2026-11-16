import { ArrowDownRight, ArrowUpRight, ShieldCheck, Timer } from "lucide-react";
import type { Attempt } from "@/lib/api/contracts";
import {
  benchmarkTime,
  compareBenchmark,
  percentageChange,
} from "@/lib/benchmark";
import { count } from "@/lib/formatters";
import { Badge, SourceBadge, StatusBadge } from "@/components/shared/status";
import { Card, CardHeader } from "@/components/ui/card";

const correctnessLabels: Partial<Record<Attempt["correctness"], string>> = {
  passed: "Passed",
  failed: "Failed",
  skipped: "Not tested",
  error: "Error",
};

export function PerformanceComparison({ attempt }: { attempt: Attempt }) {
  const measured = compareBenchmark(attempt);
  if (!measured) {
    return (
      <div className="evidence-card">
        <div className="evidence-heading">
          <Timer size={17} />
          <h3>Performancebenchmark</h3>
        </div>
        <p className="evidence-value">
          {attempt.benchmark.original_ms != null &&
          attempt.benchmark.proposed_ms != null
            ? "Metingen onvergelijkbaar"
            : "Not benchmarked"}
        </p>
        <p className="muted text-sm">Geen onderbouwde performanceconclusie</p>
        <p className="muted text-xs mt-2">
          Een vergelijkbare meting vereist twee geldige medianen en een
          geslaagde correctheidscontrole.
        </p>
      </div>
    );
  }
  const { original, proposed, reduction, regression, validated } = measured;
  const maximum = Math.max(original, proposed);
  return (
    <div className="evidence-card">
      <div className="evidence-heading">
        <Timer size={17} />
        <h3>Performancebenchmark</h3>
        <SourceBadge source={attempt.benchmark.origin} />
      </div>
      <div
        className={
          "evidence-value" +
          (regression
            ? " evidence-regression"
            : validated
              ? " evidence-gain"
              : "")
        }
      >
        {regression ? (
          <ArrowUpRight size={22} />
        ) : (
          reduction > 0 && <ArrowDownRight size={22} />
        )}
        {regression
          ? percentageChange(reduction) + " langere duur"
          : reduction > 0
            ? percentageChange(reduction) + " kortere duur"
            : "Geen gemeten verschil"}
      </div>
      {regression ? (
        <Badge tone="red">Performanceregressie</Badge>
      ) : validated ? (
        <Badge tone="green">Gevalideerde verbetering</Badge>
      ) : (
        <Badge tone="neutral">
          {reduction > 0 && attempt.outcome === "not_faster"
            ? "Validatiedrempel niet gehaald"
            : reduction > 0
              ? "Verbetering niet bevestigd"
              : "Geen gemeten verbetering"}
        </Badge>
      )}
      <dl
        className="timing-chart"
        aria-label="Mediane uitvoeringstijd per SQL-versie"
      >
        {[
          { label: "Origineel", value: original },
          { label: "Voorstel", value: proposed },
        ].map(({ label, value }) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{benchmarkTime(value)}</dd>
            <dd className="timing-track" aria-hidden="true">
              <span style={{ width: (value / maximum) * 100 + "%" }} />
            </dd>
          </div>
        ))}
      </dl>
      <p className="muted text-xs">
        {attempt.benchmark.repetitions == null
          ? "Aantal herhalingen niet vastgelegd"
          : count(attempt.benchmark.repetitions) +
            " meetherhalingen per SQL-versie"}
        {" · medianen op de testdataset"}
      </p>
    </div>
  );
}

export function OptimizationResults({
  attempt,
  action,
}: {
  attempt: Attempt;
  action?: React.ReactNode;
}) {
  return (
    <Card aria-label="Optimization Results">
      <CardHeader
        title="Optimization Results"
        description="Correctheidscontrole en gemeten uitvoeringstijd op de testdataset."
        action={action}
      />
      <div className="panel-body evidence-grid">
        <div className="evidence-card">
          <div className="evidence-heading">
            <ShieldCheck size={17} />
            <h3>Correctheid</h3>
            <StatusBadge
              status={attempt.correctness}
              label={correctnessLabels[attempt.correctness]}
            />
          </div>
          <p className="correctness-message">
            {
              {
                passed:
                  "Het voorstel geeft dezelfde resultaten binnen de geteste parametersets.",
                failed: "De validator heeft een resultaatverschil vastgesteld.",
                skipped: "Er is geen resultaatvergelijking uitgevoerd.",
                error: "De resultaatvergelijking kon niet worden afgerond.",
                pending: "De correctheidscontrole staat in de wachtrij.",
                running: "De correctheidscontrole wordt uitgevoerd.",
                warning: "De correctheidscontrole heeft een aandachtspunt.",
                inconclusive:
                  "De beschikbare controle levert geen definitief oordeel op.",
              }[attempt.correctness]
            }
          </p>
          <dl className="kv-list">
            <div>
              <dt>Geteste parametersets</dt>
              <dd>{count(attempt.parameter_sets)}</dd>
            </div>
            <div>
              <dt>Afwijkend / niet afgerond</dt>
              <dd>{count(attempt.failing_parameter_sets)}</dd>
            </div>
          </dl>
          {attempt.correctness !== "passed" && attempt.detail && (
            <p className="muted text-xs mt-3">{attempt.detail}</p>
          )}
        </div>
        <PerformanceComparison attempt={attempt} />
      </div>
    </Card>
  );
}
