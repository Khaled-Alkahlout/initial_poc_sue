import { expect, test } from "@playwright/test";

test("overview, queries and stored analysis history load together", async ({
  page,
}) => {
  // Inspect data only; never generate a paid response or execute SQL.
  await page.route("**/api/runs", (route) =>
    route.request().method() === "POST" ? route.abort() : route.continue(),
  );
  for (const path of [
    "/api/overview",
    "/api/queries?top_k=2",
    "/api/queries/top_products",
    "/api/runs",
    "/api/development/tests",
    "/api/system/status",
  ]) {
    const response = await page.request.get(path);
    expect(response.status(), path).toBe(200);
    expect(response.headers()["x-request-id"], path).toBeTruthy();
  }
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Overzicht", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Gegevens niet beschikbaar", { exact: true }),
  ).toHaveCount(0);
  await page.goto("/queries/top_products");
  await expect(
    page.getByRole("heading", { name: "top_products", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Gegevens niet beschikbaar", { exact: true }),
  ).toHaveCount(0);
  const workspace = page.getByRole("region", { name: "AI Analysis Workspace" });
  await expect(
    workspace.getByRole("region", { name: "Proposed SQL", exact: true }),
  ).toBeVisible();
  await expect(
    workspace.getByRole("button", {
      name: "Generate SQL Rewrite",
      exact: true,
    }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/api-history-recovered.png",
    fullPage: false,
  });
});
