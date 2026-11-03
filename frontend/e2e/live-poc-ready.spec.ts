import { expect, test } from "@playwright/test";

test("geconfigureerde Live POC is beschikbaar zonder SQL en wacht op bevestiging", async ({
  page,
}) => {
  const system = await (await page.request.get("/api/system/status")).json();
  test.skip(
    !system.run_modes.some(
      (mode: { id: string; available: boolean }) =>
        mode.id === "analysis" && mode.available,
    ),
    "Vereist geconfigureerde AI-provider; geen generatie in deze test.",
  );
  // A readiness test must never accidentally generate a paid proposal.
  await page.route("**/api/runs", (route) =>
    route.request().method() === "POST" ? route.abort() : route.continue(),
  );
  await page.goto("/queries/top_products");
  await page.getByRole("button", { name: "POC starten", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("combobox", { name: "Uitvoermodus" }),
  ).toHaveValue("analysis");
  await expect(
    dialog.getByRole("option", {
      name: "Live POC · echt AI-advies (zonder database)",
    }),
  ).toBeEnabled();
  await expect(
    dialog.getByText(system.configured_model, { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Echte AI-analyse starten" }),
  ).toBeDisabled();
  await expect(dialog.getByText(/geen database nodig/)).toBeVisible();
  await page.screenshot({
    path: "test-results/live-poc-ready.png",
    fullPage: false,
  });
});
