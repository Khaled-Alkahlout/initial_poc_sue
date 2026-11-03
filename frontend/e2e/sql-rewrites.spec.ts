import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { attempt, run } from "../src/tests/fixtures";

test("top_products: no rewrite, focused candidate and SQL display", async ({
  page,
}) => {
  // Provider requests are intercepted: this browser regression never bills or executes SQL.
  const original = readFileSync("../cases/original/top_products.sql", "utf8");
  const proposed = `WITH filtered_orders AS (
    SELECT id FROM orders WHERE tenant_id = %(tenant_id)s
      AND created_at >= %(from)s AND created_at < %(to)s
      AND status IN ('paid', 'processing', 'shipped', 'delivered')
  )\n${original.replace("JOIN orders o", "JOIN filtered_orders o")}`;
  // Use the known fixture's CTE form with only id references in the outer query.
  const candidate = proposed.replace(
    / WHERE o\.tenant_id[\s\S]*?(?= GROUP BY)/,
    "",
  );
  const analysis = {
    schema_version: 2 as const,
    optimized_sql: null,
    rewrite_status: "no_safe_rewrite" as const,
    rewrite_explanation: "DISTINCT order counts cannot be summed per variant.",
    problem: "Large aggregate",
    root_cause: "Intermediate rows and DISTINCT sorting",
    index_recommendations: ["Review order_lines(order_id)"],
    expected_benefit: "Untested hypothesis",
    correctness_risks: [
      "Preserve tenant isolation, DISTINCT and NULL semantics",
    ],
    uncertainty: "Historical context",
    missing_context: [],
    validation_recommendations: ["Compare all fixture parameters"],
  };
  const makeRun = (sql: string | null) => ({
    ...run(),
    id: sql ? "rewrite-candidate" : "rewrite-none",
    mode: "analysis",
    accepted_count: 0,
    attempts: [
      attempt({
        original_sql: original,
        proposed_sql: sql,
        outcome: "inconclusive",
        correctness: "skipped",
        run_id: sql ? "rewrite-candidate" : "rewrite-none",
        analysis: {
          ...analysis,
          optimized_sql: sql,
          rewrite_status: sql ? "candidate" : "no_safe_rewrite",
          rewrite_explanation: sql
            ? "Filter orders in a CTE; PostgreSQL may inline it. No measured gain."
            : analysis.rewrite_explanation,
        },
        validation_state: sql
          ? "validation_unavailable"
          : "no_rewrite_proposed",
        diagnostics: {
          rewrite_requested: true,
          structured_parse_success: true,
          model_returned_candidate: !!sql,
          static_validation_accepted: sql ? true : null,
          sql_stored_success: sql ? true : null,
        },
        benchmark: { ...attempt().benchmark, status: "skipped", speedup: null },
      }),
    ],
  });
  let requests = 0;
  const displays: boolean[] = [];
  await page.route("**/api/runs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    requests++;
    const body = route.request().postDataJSON();
    expect(body.confirm_sql).toBe(false);
    if (requests === 2) {
      expect(body.rewrite_only).toBe(true);
      expect(body.source_id).toBe("rewrite-none");
    }
    await route.fulfill({
      status: 202,
      json: makeRun(requests === 1 ? null : candidate),
    });
  });
  await page.route("**/api/runs/*", (route) =>
    route.fulfill({
      json: makeRun(
        route.request().url().endsWith("rewrite-candidate") ? candidate : null,
      ),
    }),
  );
  await page.route("**/api/runs/*/rewrite-display", async (route) => {
    displays.push(route.request().postDataJSON().sql_displayed);
    await route.fulfill({ status: 204 });
  });
  await page.goto("/queries/top_products");
  const workspace = page.getByRole("region", { name: "AI Analysis Workspace" });
  await workspace.getByRole("checkbox").first().check();
  await workspace
    .getByRole("button", { name: "Analyze with AI", exact: true })
    .click();
  await expect(
    workspace.getByRole("heading", {
      name: "No SQL rewrite proposed",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    workspace.getByText("Review order_lines(order_id)", { exact: true }),
  ).toBeVisible();
  await workspace
    .getByRole("button", { name: "Generate SQL Rewrite", exact: true })
    .click();
  await expect(
    workspace.getByRole("heading", {
      name: "SQL rewrite generated",
      exact: true,
    }),
  ).toBeVisible();
  const right = workspace.getByRole("region", {
    name: "Proposed SQL",
    exact: true,
  });
  await expect(right.locator("code")).toHaveText(candidate);
  await expect(
    right.getByRole("button", { name: "Kopieer SQL: Proposed SQL" }),
  ).toBeVisible();
  await expect.poll(() => displays.includes(true)).toBe(true);
  expect(requests).toBe(2);
  await workspace
    .getByRole("region", { name: "SQL rewrite", exact: true })
    .screenshot({ path: "test-results/sql-rewrite-comparison.png" });
});
