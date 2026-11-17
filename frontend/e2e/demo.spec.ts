import { test, expect } from "@playwright/test";

test("POC demo: query inspecteren, replay starten en review bewaren", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Overzicht", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Query Explorer", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Query uitsluiten van selectie")
    .selectOption("top_products");
  const topProducts = page.getByRole("row").filter({ hasText: "top_products" });
  await expect(
    topProducts.getByText("Uitgesloten", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Query uitsluiten van selectie").selectOption("");
  await expect(
    topProducts.getByText("Geselecteerd", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "top_products", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "top_products", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "POC starten" }).click();
  await page
    .getByRole("combobox", { name: "Uitvoermodus" })
    .selectOption("replay");
  await page.getByRole("button", { name: "Replay starten" }).click();
  await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/);
  await expect(page.getByText("Afgerond", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText("Historische replay.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Optimization Results" }),
  ).toBeVisible();
  await page.getByLabel("Reviewlabel").selectOption("incorrect");
  await page
    .getByLabel("Toelichting · optioneel")
    .fill("E2E review: controleer de semantische aannames.");
  await page.getByRole("button", { name: "Review opslaan" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Review opgeslagen" }),
  ).toContainText("technische uitslag blijft ongewijzigd");
  await page.reload();
  await expect(
    page.getByText("E2E review: controleer de semantische aannames."),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Optimization Results" }),
  ).toBeVisible();
});

test("een offline request krijgt een opgeslagen beoordeling zonder prestatiemeting", async ({
  page,
}) => {
  await page.goto("/queries/top_products");
  await page.getByRole("button", { name: "POC starten" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("combobox", { name: "Uitvoermodus" })
    .selectOption("mock");
  await dialog.getByRole("button", { name: "Run starten" }).click();
  await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/);
  await expect(page.getByText("Afgerond", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText("Not benchmarked", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Request beoordelen" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Geen vergelijkbare prestatiemeting beschikbaar/),
  ).toBeVisible();

  const comment = "Handmatige beoordeling zonder benchmark.";
  await page.getByLabel("Toelichting · optioneel").fill(comment);
  await page.getByRole("button", { name: "Review opslaan" }).click();
  await expect(page.getByText(comment, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(comment, { exact: true })).toBeVisible();
  await expect(
    page.getByText("Not benchmarked", { exact: true }),
  ).toBeVisible();
});

test("Development inspecteert een gemiste mutant en voert offline tests uit", async ({
  page,
}) => {
  await page.goto("/development");
  await page.screenshot({
    path: "test-results/development-desktop.png",
    fullPage: false,
  });
  await page
    .getByRole("link", { name: /audit_log_page \/ M3_geen_id_tiebreak/ })
    .first()
    .click();
  await expect(
    page.getByText("Mislukt", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/development");
  await page.getByRole("tab", { name: "LLM & contextcondities" }).click();
  await expect(
    page.getByRole("heading", { name: "Historische modeluitkomsten" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Tests uitvoeren" }).click();
  await page
    .getByRole("button", { name: "Tests uitvoeren", exact: true })
    .click();
  await expect(page.getByText("Afgerond", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByRole("link", {
      name: "test_frequency_can_outweigh_individual_latency",
    }),
  ).toBeVisible();
});

test("klein scherm: navigatie werkt en inhoud veroorzaakt geen body-overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Navigatie openen" }).click();
  await page
    .getByRole("link", { name: "Query Explorer", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Query Explorer", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
});

test("client toont een API-fout zonder vervangende successen", async ({
  page,
}) => {
  await page.route("**/api/queries?*", (route) => route.abort());
  await page.goto("/queries");
  await expect(
    page.getByRole("alert").filter({ hasText: "niet bereikbaar" }),
  ).toBeVisible();
});

test("AI-workspace toont configuratie en vraagt expliciete bevestiging", async ({
  page,
}) => {
  await page.goto("/queries/top_products");
  await expect(
    page.getByRole("heading", { name: "Analyze with AI", exact: true }),
  ).toBeVisible();
  await page.locator("#ai-workspace").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/analysis-workspace.png",
    fullPage: false,
  });
  await expect(
    page.getByText("Gesimuleerd", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Analyze with AI", exact: true }),
  ).toBeDisabled();
  const system = await (await page.request.get("/api/system/status")).json();
  if (
    system.run_modes.some(
      (mode: { id: string; available: boolean }) =>
        mode.id === "analysis" && mode.available,
    )
  ) {
    await expect(
      page
        .getByRole("region", { name: "AI Analysis Workspace" })
        .getByRole("checkbox"),
    ).not.toBeChecked();
  }
});
