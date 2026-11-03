import Link from "next/link";
import type { Attempt } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Card, CardHeader } from "@/components/ui/card";
import { JsonInspector } from "@/components/shared/json-inspector";

export function AIUsage({ attempt }: { attempt: Attempt }) {
  const d = attempt.diagnostics;
  const reported = (value: number | null | undefined) =>
    value == null ? "Niet gerapporteerd" : count(value);
  return (
    <Card>
      <CardHeader
        title="AI Analysis · werkelijk gebruik"
        description={attempt.model ?? "Model niet vastgelegd"}
      />
      <div className="panel-body stack">
        {d?.error_code && (
          <p role="alert" className="notice notice-amber">
            {d.error_code === "token_limit"
              ? "Response reached the configured output token limit. The analysis may be incomplete. Increase the limit in Settings and retry."
              : attempt.detail}{" "}
            <Link className="text-link" href="/settings">
              AI Settings →
            </Link>
          </p>
        )}
        <dl className="kv-list">
          <div>
            <dt>Inputtokens</dt>
            <dd>{reported(d?.input_tokens ?? attempt.input_tokens)}</dd>
          </div>
          <div>
            <dt>Outputtokens · inclusief reasoning waar van toepassing</dt>
            <dd>{reported(d?.output_tokens ?? attempt.output_tokens)}</dd>
          </div>
          <div>
            <dt>Reasoningtokens</dt>
            <dd>{reported(d?.reasoning_tokens)}</dd>
          </div>
          <div>
            <dt>Totaal tokens</dt>
            <dd>{reported(d?.total_tokens)}</dd>
          </div>
          <div>
            <dt>Maximum output</dt>
            <dd>
              {d?.configured_max_output_tokens === null
                ? "Provider-default · niet onbeperkt"
                : reported(d?.configured_max_output_tokens)}
            </dd>
          </div>
          <div>
            <dt>Reasoning effort</dt>
            <dd>{d?.reasoning_effort ?? "Niet gerapporteerd"}</dd>
          </div>
          <div>
            <dt>Duur</dt>
            <dd>
              {d?.seconds == null && attempt.llm_seconds == null
                ? "Niet gerapporteerd"
                : `${count(d?.seconds ?? attempt.llm_seconds)} s`}
            </dd>
          </div>
          <div>
            <dt>Finish reason</dt>
            <dd>{d?.finish_reason ?? "Niet gerapporteerd"}</dd>
          </div>
          <div>
            <dt>Native stop reason</dt>
            <dd>{d?.native_finish_reason ?? "Niet gerapporteerd"}</dd>
          </div>
          <div>
            <dt>HTTP-status / zichtbare tekens</dt>
            <dd>
              {reported(d?.http_status)} / {reported(d?.visible_content_length)}
            </dd>
          </div>
          <div>
            <dt>Kosten</dt>
            <dd>
              {(d?.cost_usd ?? attempt.cost_usd) == null
                ? "Niet gerapporteerd"
                : `$${(d?.cost_usd ?? attempt.cost_usd)!.toFixed(6)} USD · ${(d?.cost_kind ?? attempt.cost_kind) === "reported" ? "gerapporteerd" : "geschat"}`}
            </dd>
          </div>
        </dl>
        {attempt.partial_response && (
          <details className="inspector">
            <summary>
              Onvolledige zichtbare respons · eerste 12.000 tekens · geredigeerd
              · niet uitvoerbaar
            </summary>
            <pre>{attempt.partial_response}</pre>
          </details>
        )}
        {d && (
          <JsonInspector
            title="Responsdiagnostiek · geen SQL of reasoningtekst"
            value={d}
          />
        )}
      </div>
    </Card>
  );
}
