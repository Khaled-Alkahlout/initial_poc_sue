import { expect, test } from "@playwright/test";

test("AI Settings toont actuele instellingen en beschermde SQL-status", async ({
  page,
}) => {
  await page.route("**/api/settings/ai/test", (route) => route.abort());
  const response = await page.request.get("/api/settings/ai");
  expect(response.ok()).toBe(true);
  const current = await response.json();
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "AI Settings", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Maximum output tokens")).toHaveValue(
    current.settings.max_output_tokens === null
      ? "provider"
      : String(current.settings.max_output_tokens),
  );
  await expect(page.getByLabel("Reasoning effort")).toHaveValue(
    current.settings.reasoning_effort,
  );
  await expect(
    page.getByRole("button", { name: "Test AI connection" }),
  ).toBeDisabled();
  await page.locator("form").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/ai-settings.png",
    fullPage: false,
  });
});

test("opgeslagen analyse toont echte usage en een finish reason", async ({
  page,
}) => {
  const runs = await (await page.request.get("/api/runs")).json();
  const run = runs.find(
    (r: { mode: string; lifecycle: string }) =>
      r.mode === "analysis" && r.lifecycle === "COMPLETED",
  );
  test.skip(
    !run,
    "Geen nieuwe analyse beschikbaar; deze test start geen betaald request.",
  );
  await page.goto(`/runs/${run.id}`);
  await expect(
    page.getByRole("heading", { name: "AI Analysis · werkelijk gebruik" }),
  ).toBeVisible();
  await expect(page.getByText("Finish reason", { exact: true })).toBeVisible();
  await page
    .getByRole("heading", { name: "AI Analysis · werkelijk gebruik" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/ai-usage.png", fullPage: false });
});
