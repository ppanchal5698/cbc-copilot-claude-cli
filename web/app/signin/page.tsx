import { Suspense } from "react";

import { SignInForm } from "@/components/auth/sign-in-form";
import { devAccounts } from "@/lib/dev-auth";

export default function SignInPage() {
  // Resolved on the server. Outside local development this is an empty list, so
  // the seed credentials never reach the browser at all.
  const quickAccounts = devAccounts();

  return (
    <div className="grid min-h-screen lg:h-screen lg:grid-cols-[1.15fr_0.85fr]">
      <div
        className="hidden flex-col justify-between border-r p-10 lg:flex lg:p-[54px_60px_44px]"
        style={{ borderColor: "var(--app-line)" }}
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
          <h1 className="mt-[26px] text-[54px] font-semibold leading-[0.98] tracking-[-0.025em] xl:text-[74px]">
            Ops&#8209;Hub
          </h1>
          <p className="mt-3.5 max-w-[520px] text-[18px] leading-[1.4] text-pretty xl:text-[22px]">
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
        className="flex flex-col justify-center px-8 py-10 lg:px-[60px]"
        style={{ background: "var(--app-bg-2)" }}
      >
        {/* useSearchParams needs a boundary; the form is the only dynamic part. */}
        <Suspense fallback={null}>
          <SignInForm quickAccounts={quickAccounts} />
        </Suspense>
      </div>
    </div>
  );
}
