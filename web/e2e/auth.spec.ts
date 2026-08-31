import { test, expect } from "@playwright/test";

import { credentials, signIn } from "./helpers";

test.describe("Authentication", () => {
  test("redirects unauthenticated users to sign-in", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/signin/);
  });

  test("rejects invalid credentials", async ({ page }) => {
    await page.goto("/signin");
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/do not match/i);
  });

  test("signs in and reaches dashboard", async ({ page }) => {
    await signIn(page, credentials.estimator.email, credentials.estimator.password);
    await expect(page.getByRole("heading", { name: /estimator home|dashboard/i })).toBeVisible({
      timeout: 15_000,
    });
  });
});
