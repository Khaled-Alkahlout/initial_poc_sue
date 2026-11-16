import Link from "next/link";
import type { Attempt } from "@/lib/api/contracts";
import { Card, CardHeader } from "@/components/ui/card";
import { JsonInspector } from "@/components/shared/json-inspector";
import { count } from "@/lib/formatters";

export function AIUsage({ attempt }: { attempt: Attempt }) {
  const d = attempt.diagnostics;
  const input = d?.input_tokens ?? attempt.input_tokens;
  const output = d?.output_tokens ?? attempt.output_tokens;
  const total =
    d?.total_tokens ??
    (input != null && output != null ? input + output : null);
  const duration = d?.seconds ?? attempt.llm_seconds;
  const cost = d?.cost_usd ?? attempt.cost_usd;
  const costKind = d?.cost_kind ?? attempt.cost_kind;
  const available = (value: number | null | undefined) =>
    value == null ? "Niet beschikbaar" : count(value);
  const price =
    cost == null
      ? "Niet beschikbaar"
      : new Intl.NumberFormat("en-US", {
          minimumFractionDigits: 2,
          maximumSignificantDigits: 8,
          maximumFractionDigits: 8,
          roundingPriority: "morePrecision",
        }).format(cost) + " USD";
  return (
    <Card>
      <CardHeader title="AI-model en gebruik" />
      <div className="panel-body stack">
        {d?.error_code && (
          <p role="alert" className="notice notice-amber">
            {d.error_code === "token_limit"
              ? "Response reached the configured output token limit. The analysis may be incomplete."
              : attempt.detail ||
                "Dit modelrequest heeft een fout opgeleverd."}{" "}
            <Link className="text-link" href="/settings">
              AI Settings
            </Link>
          </p>
        )}
        <dl className="kv-list">
          <div>
            <dt>Provider</dt>
            <dd>{attempt.provider ?? "Niet beschikbaar"}</dd>
          </div>
          <div>
            <dt>Model-ID</dt>
            <dd className="mono">
              {d?.model ?? attempt.model ?? "Niet beschikbaar"}
            </dd>
          </div>
          <div>
            <dt>Inputtokens</dt>
            <dd>{available(input)}</dd>
          </div>
          <div>
            <dt>Outputtokens</dt>
            <dd>{available(output)}</dd>
          </div>
          <div>
            <dt>Reasoningtokens</dt>
            <dd>{available(d?.reasoning_tokens)}</dd>
          </div>
          <div>
            <dt>Totaal tokens</dt>
            <dd>{available(total)}</dd>
          </div>
          <div>
            <dt>Maximum outputtokens</dt>
            <dd>
              {d?.configured_max_output_tokens === null
                ? "Provider-default"
                : available(d?.configured_max_output_tokens)}
            </dd>
          </div>
          <div>
            <dt>Reasoning effort</dt>
            <dd>{d?.reasoning_effort ?? "Niet beschikbaar"}</dd>
          </div>
          <div>
            <dt>Requestduur</dt>
            <dd>
              {duration == null ? "Niet beschikbaar" : count(duration) + " s"}
            </dd>
          </div>
          <div>
            <dt>Finish reason</dt>
            <dd>{d?.finish_reason ?? "Niet beschikbaar"}</dd>
          </div>
          <div>
            <dt>Native stop reason</dt>
            <dd>{d?.native_finish_reason ?? "Niet beschikbaar"}</dd>
          </div>
          <div>
            <dt>HTTP-status / zichtbare tekens</dt>
            <dd>
              {available(d?.http_status)} /{" "}
              {available(d?.visible_content_length)}
            </dd>
          </div>
          <div>
            <dt>AI-kosten voor deze poging</dt>
            <dd>
              {price}
              {cost != null &&
                costKind === "reported" &&
                " · providergerapporteerd"}
              {cost != null && costKind === "estimated" && " · geschat"}
            </dd>
          </div>
        </dl>
        {cost != null && costKind === "estimated" && (
          <p className="muted text-xs">
            Schatting op basis van tokens en modeltarieven bij het request.
            Cachekortingen en bijkomende fees vallen buiten deze schatting.
          </p>
        )}
        {attempt.partial_response && (
          <details className="inspector">
            <summary>Onvolledige zichtbare respons · geredigeerd</summary>
            <pre>{attempt.partial_response}</pre>
          </details>
        )}
        {d && Object.keys(d).length > 0 && (
          <JsonInspector title="Responsdiagnostiek" value={d} />
        )}
      </div>
    </Card>
  );
}
