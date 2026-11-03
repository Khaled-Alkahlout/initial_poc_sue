import { Info } from "lucide-react";
import type { SystemStatus } from "@/lib/api/contracts";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/shared/status";
import { Card, CardHeader } from "@/components/ui/card";
import { ArchitectureDiagram } from "@/components/pipeline/architecture-diagram";
import { ProviderStatus } from "./provider-status";

export function ArchitectureView({ system }: { system: SystemStatus }) {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="DEVELOPMENT / ARCHITECTUUR"
        title="Architectuur & diagnostiek"
        description="Expliciete componentgrenzen maken de POC uitlegbaar en uitbreidbaar. Configuratie is geen bewijs dat een databaseverbinding of modelrequest zal slagen."
      />
      <ProviderStatus system={system} />
      <div className="metric-grid">
        {[
          {
            label: "Python-API",
            value: "Bereikbaar",
            note: "Deze status komt uit de API-response",
          },
          {
            label: "Testdatabase",
            value: "Niet getest",
            note: system.database_configured
              ? "Configuratie aanwezig; geen verbinding geopend"
              : "Geen databaseconfiguratie aanwezig",
          },
          {
            label: "Modelprovider",
            value: "Niet getest",
            note: system.model_configured
              ? "Configuratie aanwezig; geen request verstuurd"
              : "Geen complete modelconfiguratie aanwezig",
          },
          {
            label: "SQL-fixtures",
            value: String(system.fixtures),
            note: `${system.historical_runs} opgeslagen modelruns`,
          },
        ].map((item) => (
          <Card className="metric" key={item.label}>
            <p className="metric-label">{item.label}</p>
            <p className="metric-value !text-xl">{item.value}</p>
            <p className="metric-note">{item.note}</p>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader
          title="Aangesloten componenten"
          description="Frontend → API → Python-domein → opslag. De worker voert uitsluitend expliciet gestarte operaties uit."
        />
        <ArchitectureDiagram />
      </Card>
      <div className="grid-two">
        <Card>
          <CardHeader title="Ondersteunde uitvoermodi" />
          <div className="panel-body stack">
            {system.run_modes.map((mode) => (
              <div key={mode.id}>
                <div className="flex justify-between gap-3">
                  <h3>{mode.label}</h3>
                  <Badge tone={mode.available ? "blue" : "neutral"}>
                    {mode.available ? "Beschikbaar" : "Niet ingeschakeld"}
                  </Badge>
                </div>
                <p className="muted text-xs mt-2">{mode.reason}</p>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Modules & dependencies" />
          <div className="panel-body stack">
            <dl className="kv-list">
              <div>
                <dt>Queryselectie</dt>
                <dd>
                  {system.filter_available
                    ? "Bestaande module aangesloten"
                    : "Niet beschikbaar"}
                </dd>
              </div>
              {Object.entries(system.dependencies).map(([name, installed]) => (
                <div key={name}>
                  <dt className="mono">{name}</dt>
                  <dd>{installed ? "Geïnstalleerd" : "Niet geïnstalleerd"}</dd>
                </div>
              ))}
              <div>
                <dt>Historische mutatietests</dt>
                <dd>{system.historical_evaluations}</dd>
              </div>
            </dl>
            <p className="muted text-xs">
              Credentials en connection strings worden niet teruggestuurd. Een
              beschikbare dependency betekent niet dat de externe service
              operationeel is.
            </p>
          </div>
        </Card>
      </div>
      <Card>
        <CardHeader title="Systeemgrenzen" />
        <div className="panel-body">
          <ul className="list-disc pl-4 space-y-3 text-xs muted">
            <li>
              Queryselectie bepaalt wat analyse verdient. SQL-safety beoordeelt
              een voorstel vóór testuitvoering.
            </li>
            <li>
              De generator doet één voorstel. Deterministische software
              controleert; er is geen controle-agent of feedbacklus.
            </li>
            <li>
              Mockworkload is fictief. Historische benchmarks zijn opgeslagen
              metingen; replay meet niet opnieuw.
            </li>
            <li>
              Live SQL is beperkt tot bestaande cases op een expliciet
              bevestigde testdatabase. Geen productie- of schemawijzigingen.
            </li>
            <li>
              POC-pagina&apos;s demonstreren; Development toont bewijs, fouten,
              context en afzonderlijke reviews.
            </li>
            {system.limitations.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      </Card>
      {system.warnings.length > 0 && (
        <div className="notice notice-amber">{system.warnings.join(" ")}</div>
      )}
      <div className="notice notice-blue">
        <Info size={16} />
        <p>
          Lokale ontwikkelgrens: start API en frontend op <code>127.0.0.1</code>
          , met één API-worker. Er is geen authenticatie voor publiek gebruik.
          De live workloadcollector en automatisch indexbeheer zijn niet
          geïmplementeerd.
        </p>
      </div>
    </div>
  );
}
