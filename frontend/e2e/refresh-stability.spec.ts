import { expect, test } from "@playwright/test";

test("Query Explorer behoudt invoer zonder spontane paginaherlading", async ({
  page,
}) => {
  let navigations = 0;
  const errors: string[] = [];
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations += 1;
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/queries");
  const search = page.getByLabel("Zoek query of SQL", { exact: true });
  await search.fill("top_products");
  await expect(
    page.getByRole("link", { name: "top_products", exact: true }),
  ).toBeVisible();
  const settledNavigations = navigations;

  // The reported dev-server loop reloaded multiple times per second. Observe
  // several cycles, asserting continuously rather than only at the end.
  for (let second = 0; second < 10; second += 1) {
    await page.waitForTimeout(1000);
    await expect(search).toHaveValue("top_products");
    expect(navigations).toBe(settledNavigations);
  }
  expect(errors).toEqual([]);
  await search.fill("");
  await expect(
    page.getByRole("link", { name: "top_customers", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/refresh-fix.png",
    fullPage: false,
  });
});
