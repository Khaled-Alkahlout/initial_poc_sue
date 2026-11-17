import { expect, test } from "@playwright/test";

test("historische demo toont echte benchmark, SQL-diff en clipboard op desktop en mobiel", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 940 });
  await page.goto("/");
  await expect(
    page.getByRole("img", { name: "SUE", exact: true }),
  ).toBeVisible();
  expect(
    await page
      .getByRole("img", { name: "SUE", exact: true })
      .evaluate((logo) => (logo as HTMLImageElement).naturalWidth),
  ).toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/redesign-overview-1440.png" });

  await page.locator('a[href="/queries/top_customers"]').click();
  const comparison = page.getByRole("region", {
    name: "Query Optimization Comparison",
  });
  const original = comparison.getByRole("region", {
    name: "Original SQL Query",
  });
  const optimized = comparison.getByRole("region", {
    name: "Optimized SQL Query",
  });
  const outcome = page.getByRole("region", { name: "Optimization Results" });
  await expect(original).toBeVisible({ timeout: 15000 });
  await expect(optimized).toBeVisible();
  await expect(outcome.getByText("Passed", { exact: true })).toBeVisible();
  await expect(outcome.getByText("Gevalideerde verbetering")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Request beoordelen" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Geen vergelijkbare prestatiemeting beschikbaar/),
  ).toHaveCount(0);

  const originalBox = await original.boundingBox();
  const optimizedBox = await optimized.boundingBox();
  expect(optimizedBox!.y).toBeGreaterThan(originalBox!.y + originalBox!.height);
  await original
    .getByRole("button", { name: "Kopieer SQL: Original SQL Query" })
    .click();
  await expect(original.getByText("Gekopieerd", { exact: true })).toBeVisible();
  const catalog = await (
    await page.request.get("/api/queries/top_customers")
  ).json();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied.replace(/\r\n/g, "\n")).toBe(
    catalog.sql.replace(/\r\n/g, "\n"),
  );

  const expand = original.getByRole("button", { name: /^Toon alle/ });
  await expand.click();
  await expect(
    original.getByRole("button", { name: "Toon minder regels" }),
  ).toBeVisible();
  expect(await original.locator(".sql-line").count()).toBeGreaterThan(18);
  await original.getByRole("button", { name: "Toon minder regels" }).click();
  await comparison.scrollIntoViewIfNeeded();
  await comparison.screenshot({
    path: "test-results/redesign-sql-comparison.png",
  });
  await comparison.getByRole("button", { name: "SQL-diff" }).click();
  await expect(
    comparison.locator(".diff-line.diff-added").first(),
  ).toBeVisible();
  await expect(
    comparison.locator(".diff-line.diff-removed").first(),
  ).toBeVisible();
  const tracks = outcome.locator(".timing-track");
  expect(
    await tracks
      .first()
      .evaluate((track) => track.getBoundingClientRect().width),
  ).toBeGreaterThan(100);
  await outcome.screenshot({
    path: "test-results/redesign-optimization-results.png",
  });
  await page.getByText("Technical Details", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "AI-model en gebruik" }),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await comparison.getByRole("button", { name: "SQL", exact: true }).click();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  await original.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/redesign-query-mobile.png" });
  expect(errors).toEqual([]);
});
