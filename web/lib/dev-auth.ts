/** Seed accounts from scripts/seed_db.py — local development only. */
export const DEV_ACCOUNTS = {
  estimator: {
    label: "Estimator",
    name: "Rick Gilbert",
    email: "rgilbert@hamiltonparker.com",
    password: "opshub",
  },
  admin: {
    label: "Admin",
    name: "Kevin Baker",
    email: "kbaker@hamiltonparker.com",
    password: "opshub",
  },
} as const;

export type DevAccountKey = keyof typeof DEV_ACCOUNTS;

export function isDevQuickLoginEnabled(appEnv = process.env.APP_ENV): boolean {
  return !["production", "prod", "staging"].includes((appEnv ?? "development").toLowerCase());
}
