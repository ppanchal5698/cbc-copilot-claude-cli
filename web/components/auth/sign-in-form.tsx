"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";

/** Passed in from the server page, which decides whether to offer them at all. */
export interface QuickAccount {
  label: string;
  name: string;
  email: string;
  password: string;
}

export function SignInForm({ quickAccounts = [] }: { quickAccounts?: QuickAccount[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Where the session expired, so signing back in returns to the same screen.
  const from = searchParams.get("from");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitCredentials(nextEmail: string, nextPassword: string) {
    setBusy(true);
    setError(null);

    const result = await signIn("credentials", {
      email: nextEmail,
      password: nextPassword,
      redirect: false,
    }).catch(() => null);

    if (!result || result.error) {
      setError(
        result
          ? "That email and password do not match an account."
          : "Could not reach the sign-in service. Try again in a moment.",
      );
      setBusy(false);
      return;
    }

    // Only follow an in-app path. An open redirect here would let a crafted
    // link bounce someone straight off this host after authenticating.
    const target = from && from.startsWith("/") && !from.startsWith("//") ? from : "/dashboard";
    router.push(target);
    router.refresh();
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    await submitCredentials(email, password);
  }

  async function onQuickSignIn(account: QuickAccount) {
    setEmail(account.email);
    setPassword(account.password);
    await submitCredentials(account.email, account.password);
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto w-full max-w-[360px]">
      <h2 className="text-[20px] font-semibold">Sign in</h2>
      <p className="mt-1.5 text-[13px]" style={{ color: "var(--app-tx-2)" }}>
        Use your Hamilton Parker address.
      </p>

      <label
        htmlFor="signin-email"
        className="mt-8 block text-[11.5px] uppercase tracking-[0.08em]"
        style={{ color: "var(--app-tx-3)" }}
      >
        Email
      </label>
      <input
        id="signin-email"
        type="email"
        required
        autoComplete="username"
        aria-invalid={!!error}
        aria-describedby={error ? "signin-error" : undefined}
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        className="mt-1.5 w-full rounded-md px-3 py-2.5 text-[13.5px] outline-none focus:ring-2"
        style={{
          background: "var(--app-panel-2)",
          border: "1px solid var(--app-line)",
          color: "var(--app-tx)",
        }}
      />

      <label
        htmlFor="signin-password"
        className="mt-5 block text-[11.5px] uppercase tracking-[0.08em]"
        style={{ color: "var(--app-tx-3)" }}
      >
        Password
      </label>
      <input
        id="signin-password"
        type="password"
        required
        autoComplete="current-password"
        aria-invalid={!!error}
        aria-describedby={error ? "signin-error" : undefined}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        className="mt-1.5 w-full rounded-md px-3 py-2.5 text-[13.5px] outline-none focus:ring-2"
        style={{
          background: "var(--app-panel-2)",
          border: "1px solid var(--app-line)",
          color: "var(--app-tx)",
        }}
      />

      {error && (
        <p
          id="signin-error"
          role="alert"
          className="anim-fadein mt-4 rounded-md px-3 py-2 text-[12.5px]"
          style={{
            background: "var(--app-neg-soft)",
            border: "1px solid var(--app-neg-line)",
            color: "var(--app-neg)",
          }}
        >
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        className="mt-7 w-full rounded-md py-2.5 text-[13.5px] font-semibold transition disabled:opacity-60"
        style={{ background: "var(--app-accent)", color: "#fff" }}
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>

      {quickAccounts.length > 0 && (
        <div
          className="mt-6 rounded-md px-3 py-3"
          style={{ background: "var(--app-panel)", border: "1px dashed var(--app-line)" }}
        >
          <p
            className="text-[11.5px] font-medium uppercase tracking-[0.08em]"
            style={{ color: "var(--app-tx-3)" }}
          >
            Local development
          </p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {quickAccounts.map((account) => (
              <button
                key={account.email}
                type="button"
                disabled={busy}
                onClick={() => onQuickSignIn(account)}
                className="rounded-md px-3 py-2.5 text-left transition disabled:opacity-60"
                style={{
                  background: "var(--app-panel-2)",
                  border: "1px solid var(--app-line)",
                  color: "var(--app-tx)",
                }}
              >
                <span className="block text-[13px] font-semibold">{account.label}</span>
                <span className="mt-0.5 block text-[11.5px]" style={{ color: "var(--app-tx-2)" }}>
                  {account.name}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
