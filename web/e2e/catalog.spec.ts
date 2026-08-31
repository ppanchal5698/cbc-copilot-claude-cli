import { test, expect } from "@playwright/test";

import { credentials, signIn } from "./helpers";

test.describe("Catalog", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, credentials.estimator.email, credentials.estimator.password);
  });

  test("searches the product catalog", async ({ page }) => {
    await page.goto("/catalog");
    await page.getByPlaceholder(/search/i).fill("door");
    await expect(page.getByText(/results|parts|catalog/i).first()).toBeVisible({
      timeout: 15_000,
    });
  });
});
