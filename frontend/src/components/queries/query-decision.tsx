import type { Query } from "@/lib/api/contracts";
import { count, milliseconds, reasonLabels } from "@/lib/formatters";
import { Badge, SourceBadge } from "@/components/shared/status";
import { Card, CardHeader } from "@/components/ui/card";

export function QueryMetrics({ query }: { query: Query }) {
  return (
    <Card>
      <CardHeader
        title="Workloadgegevens"
        action={
          <SourceBadge source={query.is_synthetic ? "synthetic" : "measured"} />
        }
      />
      <dl className="panel-body kv-list">
        <div>
          <dt>Uitvoeringen</dt>
          <dd>{count(query.calls)}</dd>
        </div>
        <div>
          <dt>Gemiddelde duur</dt>
          <dd>{milliseconds(query.mean_execution_time_ms)}</dd>
        </div>
        <div>
          <dt>Totale workloadimpact</dt>
          <dd>{milliseconds(query.impact_ms)}</dd>
        </div>
        <div>
          <dt>Prioriteitsrang</dt>
          <dd>{query.rank ? `#${query.rank}` : "Niet gerangschikt"}</dd>
        </div>
        <div>
          <dt>Bron</dt>
          <dd className="mono">{query.source}</dd>
        </div>
        <div>
          <dt>Meetvenster</dt>
          <dd className="mono">{query.window_id ?? "Niet vastgelegd"}</dd>
        </div>
      </dl>
    </Card>
  );
}
export function QueryDecision({ query }: { query: Query }) {
  return (
    <Card>
      <CardHeader
        title="Selectiebeslissing"
        action={
          <Badge
            tone={
              query.selected
                ? "green"
                : query.status === "deferred"
                  ? "amber"
                  : "neutral"
            }
          >
            {query.selected
              ? "Geselecteerd"
              : query.status === "eligible"
                ? "Geschikt · buiten budget"
                : query.status === "excluded"
                  ? "Uitgesloten"
                  : "Uitgesteld"}
          </Badge>
        }
      />
      <div className="panel-body stack">
        <p className="muted text-xs">
          De backend bepaalt geschiktheid en volgorde. Totale uitvoeringstijd
          weegt zwaarder dan de duur van één uitvoering.
        </p>
        <ul className="explanation-list">
          {query.reason_codes.map((code) => (
            <li key={code}>
              <div>
                <span className="mono">{code}</span>
                <p>
                  {reasonLabels[code] ??
                    "Redencode ontvangen van de backend; nog geen vertaling beschikbaar."}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
