/**
 * Seed accounts from scripts/seed_db.py - local development only.
 *
 * SERVER ONLY. This module holds plaintext seed passwords, and it used to be
 * imported directly by the sign-in form, which put them in the client bundle of
 * every deployment - production included, where the quick-login buttons are not
 * even rendered. The page now reads the accounts on the server and passes only
 * what it decides to show.
 */
import "server-only";

export interface DevAccount {
  label: string;
  name: string;
  email: string;
  password: string;
}

const DEV_ACCOUNTS: DevAccount[] = [
  {
    label: "Estimator",
    name: "Rick Gilbert",
    email: "rgilbert@hamiltonparker.com",
    password: "opshub",
  },
  {
    label: "Admin",
    name: "Kevin Baker",
    email: "kbaker@hamiltonparker.com",
    password: "opshub",
  },
];

export function isDevQuickLoginEnabled(appEnv = process.env.APP_ENV): boolean {
  return !["production", "prod", "staging"].includes((appEnv ?? "development").toLowerCase());
}

/** The accounts to offer, or none at all outside local development. */
export function devAccounts(): DevAccount[] {
  return isDevQuickLoginEnabled() ? DEV_ACCOUNTS : [];
}
