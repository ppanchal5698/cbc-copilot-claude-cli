"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";

import { DEV_ACCOUNTS, type DevAccountKey } from "@/lib/dev-auth";

export function SignInForm({ showDevLogin = false }: { showDevLogin?: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState<string>(DEV_ACCOUNTS.estimator.email);
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
    });

    if (result?.error) {
      setError("That email and password do not match an account.");
      setBusy(false);
      return;
    }

    router.push("/dashboard");
    router.refresh();
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    await submitCredentials(email, password);
  }

  async function onQuickSignIn(key: DevAccountKey) {
    const account = DEV_ACCOUNTS[key];
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
        className="mt-8 block text-[11.5px] uppercase tracking-[0.08em]"
        style={{ color: "var(--app-tx-3)" }}
      >
        Email
      </label>
      <input
        type="email"
        required
        autoComplete="username"
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
        className="mt-5 block text-[11.5px] uppercase tracking-[0.08em]"
        style={{ color: "var(--app-tx-3)" }}
      >
        Password
      </label>
      <input
        type="password"
        required
        autoComplete="current-password"
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

      {showDevLogin && (
        <div
          className="mt-6 rounded-md px-3 py-3"
          style={{
            background: "var(--app-panel)",
            border: "1px dashed var(--app-line)",
          }}
        >
          <p className="text-[11.5px] font-medium uppercase tracking-[0.08em]" style={{ color: "var(--app-tx-3)" }}>
            Local development
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {(Object.entries(DEV_ACCOUNTS) as [DevAccountKey, (typeof DEV_ACCOUNTS)[DevAccountKey]][]).map(
              ([key, account]) => (
                <button
                  key={key}
                  type="button"
                  disabled={busy}
                  onClick={() => onQuickSignIn(key)}
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
              ),
            )}
          </div>
          <p className="mt-2.5 text-[11px] leading-relaxed" style={{ color: "var(--app-tx-3)" }}>
            Seed password for both: <code>opshub</code>
          </p>
        </div>
      )}
    </form>
  );
}
