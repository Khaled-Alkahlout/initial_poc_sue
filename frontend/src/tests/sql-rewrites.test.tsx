import { test, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { RewriteSummary } from "@/components/evaluation/rewrite-summary";
import { attemptSchema } from "@/lib/api/contracts";
import { api } from "@/lib/api/client";
import { attempt } from "./fixtures";

const analysis = {
  problem: "Sort cost",
  root_cause: "DISTINCT aggregation",
  optimized_sql: null,
  index_recommendations: ["Review order_id index"],
  expected_benefit: "Untested",
  correctness_risks: ["NULL and duplicates"],
  uncertainty: "Historical plan",
  validation_recommendations: ["Compare both tenants"],
  missing_context: [],
  schema_version: 2 as const,
  rewrite_status: "no_safe_rewrite" as const,
  rewrite_explanation:
    "Per-variant order counts cannot be added without double counting.",
};

test("no rewrite has a specific explanation and no proposed SQL copy button", () => {
  render(
    <RewriteSummary
      attempt={attempt({
        analysis,
        proposed_sql: null,
        validation_state: "no_rewrite_proposed",
      })}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "No SQL rewrite proposed" }),
  ).toBeVisible();
  const right = screen.getByRole("region", { name: "Proposed SQL" });
  expect(within(right).getByText(/double counting/)).toBeVisible();
  expect(within(right).queryByRole("button")).toBeNull();
});

test("stored SQL is highlighted, displayed verbatim and acknowledged without SQL payload", async () => {
  const report = vi
    .spyOn(api, "recordRewriteDisplay")
    .mockResolvedValue(new Response(null, { status: 204 }));
  const value = attempt({
    proposed_sql: "SELECT 2 AS quantity",
    correctness: "skipped",
    diagnostics: { rewrite_requested: true },
  });
  render(<RewriteSummary attempt={value} />);
  const right = screen.getByRole("region", { name: "Proposed SQL" });
  expect(right.querySelector("code")?.textContent).toBe(value.proposed_sql);
  expect(right.querySelector(".token.keyword")).not.toBeNull();
  expect(screen.getByText(/awaiting correctness validation/)).toBeVisible();
  await waitFor(() => expect(report).toHaveBeenCalledWith(value.run_id, true));
});

test.each([
  ["rewrite_parsing_failed", "error", "Rewrite parsing failed"],
  [
    "rewrite_static_rejected",
    "safety_rejected",
    "Rewrite failed static validation",
  ],
  ["analysis_failed", "error", "SQL rewrite request failed"],
] as const)("%s remains distinct", (state, outcome, title) => {
  render(
    <RewriteSummary
      attempt={attempt({
        validation_state: state,
        outcome,
        proposed_sql: null,
      })}
    />,
  );
  expect(screen.getByRole("heading", { name: title })).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "No SQL rewrite proposed" }),
  ).toBeNull();
});

test("frontend contract retains new fields and reads legacy analyses", () => {
  const value = attempt({
    analysis,
    diagnostics: {
      rewrite_requested: true,
      structured_parse_success: true,
      model_returned_candidate: false,
      static_validation_accepted: null,
      sql_stored_success: null,
      frontend_sql_displayed: false,
    },
  });
  expect(attemptSchema.parse(value).diagnostics).toEqual(value.diagnostics);
  expect(attemptSchema.parse(value).analysis?.rewrite_explanation).toBe(
    analysis.rewrite_explanation,
  );
  const { schema_version, rewrite_status, rewrite_explanation, ...legacy } =
    analysis;
  void schema_version;
  void rewrite_status;
  void rewrite_explanation;
  expect(
    attemptSchema.parse(attempt({ analysis: legacy })).analysis?.problem,
  ).toBe("Sort cost");
});
