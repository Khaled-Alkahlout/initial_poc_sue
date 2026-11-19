import { expect, test } from "@playwright/test";
import type { SystemStatus } from "../src/lib/api/contracts";

test("analyse maakt modelcontext en aansluitende tests zichtbaar", async ({
  page,
}) => {
  const status = await page.request.get("/api/system/status");
  expect(status.ok()).toBe(true);
  const system: SystemStatus = await status.json();
  const live = system.run_modes.find((mode) => mode.id === "live");
  const analysis = system.run_modes.find((mode) => mode.id === "analysis");
  const database = system.run_modes.find((mode) => mode.id === "validate");
  await page.goto("/queries/top_products");
  await page
    .getByRole("button", { name: "Nieuwe analyse", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("combobox")).toHaveCount(3);
  await expect(dialog.getByRole("combobox", { name: "Query" })).toHaveValue(
    "top_products",
  );
  const start = dialog.getByRole("button", {
    name: "Analyse starten",
  });
  const modelConsent = dialog.getByRole("checkbox", { name: /AI-kosten/ });
  const sqlConsent = dialog.getByRole("checkbox", {
    name: /correctheidscontrole en benchmark/,
  });
  await expect(start).toBeDisabled();
  await expect(modelConsent).toBeVisible();
  await expect(modelConsent).not.toBeChecked();
  if (live?.available || analysis?.available) {
    if (system.configured_model) {
      await expect(
        dialog.getByText(system.configured_model, { exact: true }),
      ).toBeVisible();
    }
    await modelConsent.check();
    if (database?.available) {
      await expect(start).toBeDisabled();
      await sqlConsent.check();
    } else {
      await expect(sqlConsent).toHaveCount(0);
      await expect(
        dialog.getByText(/Databasemetadata en testen vereisen/),
      ).toBeVisible();
    }
    await expect(start).toBeEnabled();
    if (database?.available) {
      await dialog
        .getByRole("combobox", { name: "Na de analyse" })
        .selectOption("save");
      await dialog
        .getByRole("combobox", { name: "Context voor het model" })
        .selectOption("C1_query");
      await expect(dialog.getByRole("checkbox")).toHaveCount(1);
      await expect(start).toBeEnabled();
    }
    await dialog.getByText("Vaste systeemprompt bekijken").click();
    await expect(dialog.locator("details pre")).toContainText(
      "PostgreSQL 16-expert",
    );
    await page.screenshot({ path: "test-results/live-poc-ready.png" });
    await dialog.getByText("Vaste systeemprompt bekijken").click();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      dialog.getByRole("combobox", { name: "Context voor het model" }),
    ).toBeVisible();
    await start.scrollIntoViewIfNeeded();
    await expect(start).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({ path: "test-results/analysis-options-mobile.png" });
  } else {
    await expect(modelConsent).toBeDisabled();
    await expect(
      dialog.getByText(
        analysis?.reason ??
          live?.reason ??
          "AI-analyse is momenteel niet beschikbaar.",
        { exact: true },
      ),
    ).toBeVisible();
  }
});
