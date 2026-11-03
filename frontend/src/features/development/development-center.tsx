"use client";
import { useState } from "react";
import { Info } from "lucide-react";
import type { Overview, SystemStatus, TestRecord } from "@/lib/api/contracts";
import { conditionLabels, count } from "@/lib/formatters";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { SourceBadge } from "@/components/shared/status";
import { TestMatrix } from "@/components/evaluation/test-matrix";
import { ConditionChart } from "@/components/charts/condition-chart";
import { TestLauncher } from "./test-launcher";

export function DevelopmentCenter({
  tests,
  counts,
  overview,
  system,
}: {
  tests: TestRecord[];
  counts: Record<string, number>;
  overview: Overview;
  system: SystemStatus;
}) {
  const [tab, setTab] = useState("matrix");
  const metrics = [
    {
      label: "Evaluatierecords",
      value: tests.length,
      note: "Historisch, replay en nieuw blijven herkenbaar",
    },
    {
      label: "Geslaagde controles",
      value: counts.passed ?? 0,
      note: "Inclusief correct gedetecteerde mutanten",
    },
    {
      label: "Mislukt / technische fout",
      value: (counts.failed ?? 0) + (counts.error ?? 0),
      note: "Zie de afzonderlijke status in de matrix",
    },
    {
      label: "Onbeslist / niet uitgevoerd",
      value: (counts.inconclusive ?? 0) + (counts.skipped ?? 0),
      note: "Ontbrekend bewijs is geen succes",
    },
  ];
  return (
    <div className="stack">
      <PageHeader
        eyebrow="DEVELOPMENT / TESTEN & ONDERZOEK"
        title="Test- & evaluatiecentrum"
        description="Van een technische uitslag naar een verklaarbaar resultaat. Inspecteer testinput, modelgedrag en afwijkingen; leg je eigen review afzonderlijk vast."
      />
      <div className="metric-grid">
        {metrics.map((metric) => (
          <Card className="metric" key={metric.label}>
            <p className="metric-label">{metric.label}</p>
            <p className="metric-value">{count(metric.value)}</p>
            <p className="metric-note">{metric.note}</p>
          </Card>
        ))}
      </div>
      <div className="notice notice-amber">
        <Info size={16} />
        <p>
          <strong>Bekende validatorgrenzen.</strong> Ties kunnen te ruim worden
          toegelaten en normalisatie kan botsingen geven. De API behandelt
          ambigue vergelijkingen als onbeslist. Een handmatig auteurslabel is
          geen onafhankelijk correctheidsbewijs.
        </p>
      </div>
      <div>
        <div
          className="tabs"
          role="tablist"
          aria-label="Development-weergaven"
          onKeyDown={(event) => {
            const tabs = Array.from(
              event.currentTarget.querySelectorAll<HTMLButtonElement>(
                '[role="tab"]',
              ),
            );
            const index = tabs.indexOf(event.target as HTMLButtonElement);
            const next =
              event.key === "ArrowRight"
                ? (index + 1) % tabs.length
                : event.key === "ArrowLeft"
                  ? (index + tabs.length - 1) % tabs.length
                  : event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? tabs.length - 1
                      : -1;
            if (next >= 0) {
              event.preventDefault();
              setTab(["matrix", "llm", "execute"][next]);
              tabs[next].focus();
            }
          }}
        >
          <button
            role="tab"
            tabIndex={tab === "matrix" ? 0 : -1}
            aria-selected={tab === "matrix"}
            aria-controls="matrix-panel"
            onClick={() => setTab("matrix")}
          >
            Testmatrix
          </button>
          <button
            role="tab"
            tabIndex={tab === "llm" ? 0 : -1}
            aria-selected={tab === "llm"}
            aria-controls="llm-panel"
            onClick={() => setTab("llm")}
          >
            LLM & contextcondities
          </button>
          <button
            role="tab"
            tabIndex={tab === "execute" ? 0 : -1}
            aria-selected={tab === "execute"}
            aria-controls="execute-panel"
            onClick={() => setTab("execute")}
          >
            Tests uitvoeren
          </button>
        </div>
        {tab === "matrix" && (
          <div id="matrix-panel" role="tabpanel">
            <Card>
              <CardHeader
                title="Technische evaluaties"
                description={`${system.historical_evaluations} historische mutatietests plus model- en nieuwe evaluaties. Niet alle records hebben een vooraf gedefinieerde verwachting.`}
              />
              <TestMatrix tests={tests} />
            </Card>
          </div>
        )}
        {tab === "llm" && (
          <div id="llm-panel" role="tabpanel" className="stack">
            <Card>
              <CardHeader
                title="Historische modeluitkomsten"
                description="Requests zijn herhaalde pogingen, geen onafhankelijke querycases. Proefruns en volledige runs zijn samen zichtbaar."
                action={<SourceBadge source="historical" />}
              />
              <div className="panel-body">
                <ConditionChart data={overview.conditions} />
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Contextconditie</th>
                      <th>Requests</th>
                      <th>Querycases</th>
                      <th>Geaccepteerd</th>
                      <th>Afgewezen</th>
                      <th>Onbeslist / fout</th>
                      <th>No-op</th>
                      <th>Input / outputtokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.conditions.map((condition) => (
                      <tr key={condition.condition}>
                        <td>{conditionLabels[condition.condition]}</td>
                        <td>{condition.requests}</td>
                        <td>{condition.independent_queries}</td>
                        <td>{condition.accepted}</td>
                        <td>{condition.rejected}</td>
                        <td>{condition.inconclusive}</td>
                        <td>{condition.unchanged}</td>
                        <td>
                          {count(condition.input_tokens)} /{" "}
                          {count(condition.output_tokens)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card>
              <CardHeader
                title="Vier contextcondities"
                description="De actuele inhoud en redactie zijn per poging beschikbaar op de run- en testdetailpagina."
              />
              <div className="architecture-grid">
                {Object.values(conditionLabels).map((label, index) => (
                  <div className="architecture-node" key={label}>
                    <h3>{label}</h3>
                    <p>
                      {
                        [
                          "Originele SQL met parameters.",
                          "Plus kolommen, constraints en indexdefinities.",
                          "Plus het opgeslagen EXPLAIN ANALYZE-plan.",
                          "Plus tabel- en kolomstatistieken; waarden worden beperkt.",
                        ][index]
                      }
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}
        {tab === "execute" && (
          <div id="execute-panel" role="tabpanel">
            <TestLauncher
              system={system}
              queryIds={overview.queries.map((query) => query.query_id)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
