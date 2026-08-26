"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("rgilbert@hamiltonparker.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const result = await signIn("credentials", { email, password, redirect: false });

    if (result?.error) {
      setError("That email and password do not match an account.");
      setBusy(false);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className="grid h-screen" style={{ gridTemplateColumns: "1.15fr 0.85fr" }}>
      <div
        className="flex flex-col justify-between border-r"
        style={{ borderColor: "var(--app-line)", padding: "54px 60px 44px" }}
      >
        <div className="flex items-baseline gap-3">
          <span className="text-[19px] font-semibold tracking-[-0.01em]">Hamilton Parker</span>
          <span
            className="text-[11.5px] uppercase tracking-[0.16em]"
            style={{ color: "var(--app-tx-3)" }}
          >
            Commercial Building Components
          </span>
        </div>

        <div className="max-w-[620px]">
          <div className="h-[5px]" style={{ background: "var(--app-tx)" }} />
          <div className="mt-1 h-px" style={{ background: "var(--app-tx)" }} />
          <h1 className="mt-[26px] text-[74px] font-semibold leading-[0.98] tracking-[-0.025em]">
            Ops&#8209;Hub
          </h1>
          <p className="mt-3.5 max-w-[520px] text-[22px] leading-[1.4] text-pretty">
            The estimating and pricing desk for CBC — bid documents in, priced proposal out.
          </p>

          <div className="mt-[46px] grid max-w-[600px] grid-cols-3 gap-[26px]">
            {[
              ["7", "documents read per bid, schedules and elevations reconciled against addenda"],
              ["14", "price books and multiplier programs kept current by purchasing"],
              ["4", "steps from intake to the signed proposal, with every number traceable"],
            ].map(([figure, caption]) => (
              <span
                key={figure}
                className="text-[13px] leading-[1.55]"
                style={{ color: "var(--app-tx-2)" }}
              >
                <span
                  className="tnum block text-[26px] font-semibold"
                  style={{ color: "var(--app-tx)" }}
                >
                  {figure}
                </span>
                {caption}
              </span>
            ))}
          </div>
        </div>

        <div className="text-[11.5px]" style={{ color: "var(--app-tx-3)" }}>
          Internal system · Estimating department · Columbus, Ohio
        </div>
      </div>

      <div
        className="flex flex-col justify-center px-[60px]"
        style={{ background: "var(--app-bg-2)" }}
      >
        <form onSubmit={onSubmit} className="mx-auto w-full max-w-[360px]">
          <h2 className="text-[20px] font-semibold">Sign in</h2>
          <p className="mt-1.5 text-[13px]" style={{ color: "var(--app-tx-2)" }}>
            Use your Hamilton Parker address.
          </p>

          <label className="mt-8 block text-[11.5px] uppercase tracking-[0.08em]" style={{ color: "var(--app-tx-3)" }}>
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

          <label className="mt-5 block text-[11.5px] uppercase tracking-[0.08em]" style={{ color: "var(--app-tx-3)" }}>
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

          <p className="mt-6 text-[11.5px] leading-relaxed" style={{ color: "var(--app-tx-3)" }}>
            Local development seed: <code>rgilbert@hamiltonparker.com</code> / <code>opshub</code>
          </p>
        </form>
      </div>
    </div>
  );
}
