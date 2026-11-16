import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AttemptPanels } from "@/components/evaluation/attempt-panels";
import { OptimizationResults } from "@/components/evaluation/optimization-results";
import { compareBenchmark } from "@/lib/benchmark";
import { attempt } from "./fixtures";

test("an accepted and equivalent SQL pair uses measured median reduction", () => {
  const row = attempt({ proposed_sql: "SELECT 2" });
  expect(compareBenchmark(row)).toMatchObject({
    reduction: 80,
    validated: true,
    regression: false,
  });
  render(<OptimizationResults attempt={row} />);
  expect(screen.getByText("Passed")).toBeVisible();
  expect(screen.getByText("80% kortere duur")).toBeVisible();
  expect(screen.getByText("Gevalideerde verbetering")).toBeVisible();
  expect(
    screen.getByText("7 meetherhalingen per SQL-versie", { exact: false }),
  ).toBeVisible();
});

test.each([
  [95, "5% kortere duur", "Validatiedrempel niet gehaald"],
  [100, "Geen gemeten verschil", "Geen gemeten verbetering"],
  [125, "25% langere duur", "Performanceregressie"],
] as const)(
  "100 → %s ms preserves the backend acceptance rule",
  (time, reduction, outcome) => {
    const row = attempt({
      outcome: "not_faster",
      benchmark: {
        ...attempt().benchmark,
        status: "warning",
        proposed_ms: time,
      },
    });
    expect(compareBenchmark(row)?.validated).toBe(false);
    render(<OptimizationResults attempt={row} />);
    expect(screen.getByText(reduction)).toBeVisible();
    expect(screen.getByText(outcome)).toBeVisible();
    expect(screen.queryByText("Gevalideerde verbetering")).toBeNull();
  },
);

test.each([
  ["failed", "Failed"],
  ["error", "Error"],
  ["skipped", "Not tested"],
] as const)(
  "correctness %s blocks comparative claims",
  (correctness, label) => {
    const row = attempt({
      correctness,
      benchmark: {
        ...attempt().benchmark,
        original_ms: null,
        status: "skipped",
      },
    });
    expect(compareBenchmark(row)).toBeNull();
    render(<OptimizationResults attempt={row} />);
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.getByText("Not benchmarked")).toBeVisible();
    expect(screen.queryByText("Gevalideerde verbetering")).toBeNull();
  },
);

test("zero or invalid baseline cannot produce a percentage", () => {
  for (const value of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
    expect(
      compareBenchmark(
        attempt({ benchmark: { ...attempt().benchmark, original_ms: value } }),
      ),
    ).toBeNull();
  }
  expect(
    compareBenchmark(
      attempt({ benchmark: { ...attempt().benchmark, proposed_ms: -1 } }),
    ),
  ).toBeNull();
});

test("technical disclosure retains recorded usage, cost basis and long redacted plans", async () => {
  const explain = "Seq Scan with Filter ".repeat(600);
  const row = attempt({
    provider: "openrouter",
    diagnostics: {
      model: "vendor/exact-model-id",
      input_tokens: 1234,
      output_tokens: 50,
      total_tokens: 1284,
      cost_usd: 0.001234,
      cost_kind: "reported",
    },
    context: [
      {
        id: "plan",
        label: "Execution plan",
        state: "available",
        text: explain,
        note: "Historische context.",
      },
    ],
  });
  render(<AttemptPanels attempt={row} />);
  expect(screen.getByText("vendor/exact-model-id")).not.toBeVisible();
  await userEvent.click(screen.getByText("Technical Details", { exact: true }));
  expect(screen.getByText("vendor/exact-model-id")).toBeVisible();
  expect(screen.getByText("1.234")).toBeVisible();
  expect(screen.getByText("1.284")).toBeVisible();
  expect(
    screen.getByText("0.001234 USD · providergerapporteerd"),
  ).toBeVisible();
  await userEvent.click(screen.getByText("Execution plan", { exact: true }));
  expect(screen.getByLabelText("Execution plan").textContent).toBe(explain);
});

test("historical model prose is shown beside the comparison and full SQL stays in the raw response", async () => {
  const original = "SELECT first";
  const proposed = "SELECT second";
  const explanation = "The model proposed eliminating the repeated scan.";
  const raw = ["```sql", proposed, "```", "", explanation].join("\n");
  render(
    <AttemptPanels
      attempt={attempt({
        original_sql: original,
        proposed_sql: proposed,
        explanation: raw,
      })}
    />,
  );
  expect(screen.getByText(explanation, { exact: true })).toBeVisible();
  const source = screen.getByText("Opgeslagen modelantwoord · geredigeerd");
  const rawResponse = source.closest("details")?.querySelector("pre");
  expect(rawResponse?.textContent).toBe(raw);
  expect(rawResponse).not.toBeVisible();
  await userEvent.click(screen.getByText("Technical Details", { exact: true }));
  await userEvent.click(source);
  expect(rawResponse).toBeVisible();
});

test("unknown costs and partial token usage stay unavailable", async () => {
  render(
    <AttemptPanels
      attempt={attempt({
        input_tokens: null,
        output_tokens: 15,
        cost_usd: null,
      })}
    />,
  );
  await userEvent.click(screen.getByText("Technical Details", { exact: true }));
  const usage = screen
    .getByRole("heading", { name: "AI-model en gebruik" })
    .closest("section");
  expect(usage?.textContent).toMatch(
    /InputtokensNiet beschikbaar.*Totaal tokensNiet beschikbaar.*AI-kosten voor deze pogingNiet beschikbaar/,
  );
});

test("index statements get a copyable SQL block and recorded warnings stay visible", () => {
  render(
    <AttemptPanels
      attempt={attempt({
        analysis: {
          problem: "Sortering",
          root_cause: "Extra sortering",
          expected_benefit: "Minder werk",
          uncertainty: "Historische data",
          optimized_sql: null,
          index_recommendations: [
            "Controleer schrijfoverhead. `CREATE INDEX ix_orders ON orders (tenant_id, created_at);`",
          ],
          correctness_risks: [],
          validation_recommendations: [],
          missing_context: [],
        },
      })}
    />,
  );
  const code = screen.getByRole("region", { name: "Indexvoorstel · SQL" });
  expect(code).toHaveTextContent("CREATE INDEX");
  expect(code.querySelectorAll(".sql-line").length).toBeGreaterThan(1);
  expect(screen.getByText(/schrijfoverhead/)).toBeVisible();
});
