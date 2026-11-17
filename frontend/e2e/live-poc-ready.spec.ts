import { expect, test } from "@playwright/test";
import type { SystemStatus } from "../src/lib/api/contracts";

test("POC uitvoeren vraagt toestemming voor de beschikbare stappen", async ({
  page,
}) => {
  const status = await page.request.get("/api/system/status");
  expect(status.ok()).toBe(true);
  const system: SystemStatus = await status.json();
  const live = system.run_modes.find((mode) => mode.id === "live");
  const analysis = system.run_modes.find((mode) => mode.id === "analysis");
  await page.goto("/queries/top_products");
  await page.getByRole("button", { name: "POC starten", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Live POC", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("combobox")).toHaveCount(1);
  await expect(dialog.getByRole("combobox", { name: "Querycase" })).toHaveValue(
    "top_products",
  );
  const start = dialog.getByRole("button", {
    name: live?.available ? "Live POC starten" : "AI-analyse starten",
  });
  const modelConsent = dialog.getByRole("checkbox", { name: /AI-kosten/ });
  const sqlConsent = dialog.getByRole("checkbox", {
    name: /read-only correctheidscontrole/,
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
    if (live?.available) {
      await expect(start).toBeDisabled();
      await sqlConsent.check();
    } else {
      await expect(sqlConsent).toHaveCount(0);
      await expect(
        dialog.getByText(/Correctheid en Benchmark vereisen/),
      ).toBeVisible();
    }
    await expect(start).toBeEnabled();
    await page.screenshot({ path: "test-results/live-poc-ready.png" });
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
