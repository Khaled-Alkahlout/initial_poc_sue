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
  await page.getByRole("button", { name: "Demo starten" }).click();
  await page.getByRole("button", { name: "Replay starten" }).click();
  await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/);
  await expect(page.getByText("Afgerond", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText("Historische replay.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Gelijk, niet sneller", { exact: true }).first(),
  ).toBeVisible();
  await page.getByLabel("Reviewlabel").selectOption("incorrect");
  await page
    .getByLabel("Toelichting · optioneel")
    .fill("E2E review: controleer de semantische aannames.");
  await page.getByRole("button", { name: "Review opslaan" }).click();
  await expect(page.getByRole("status")).toContainText(
    "technische uitslag blijft ongewijzigd",
  );
  await page.reload();
  await expect(
    page.getByText("E2E review: controleer de semantische aannames."),
  ).toBeVisible();
  await expect(
    page.getByText("Gelijk, niet sneller", { exact: true }).first(),
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
