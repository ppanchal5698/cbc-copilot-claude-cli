import { test, expect } from "@playwright/test";

export { test, expect };

export const credentials = {
  estimator: {
    email: process.env.E2E_ESTIMATOR_EMAIL ?? "estimator@cbc.com",
    password: process.env.E2E_ESTIMATOR_PASSWORD ?? "opshub",
  },
  admin: {
    email: process.env.E2E_ADMIN_EMAIL ?? "admin@cbc.com",
    password: process.env.E2E_ADMIN_PASSWORD ?? "opshub",
  },
};

export async function signIn(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
) {
  await page.goto("/signin");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/dashboard/);
}
