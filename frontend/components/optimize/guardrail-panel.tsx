"use client";

import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import type { GuardrailResponse } from "@/lib/api-types";

export default function GuardrailPanel({
  guardrail,
  bandMissing,
}: {
  guardrail: GuardrailResponse | null;
  bandMissing: boolean;
}) {
  if (bandMissing) {
    return (
      <div className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge">
        <div className="flex items-center gap-2 text-neutral-300">
          <ShieldCheck className="h-4 w-4 text-neutral-500" />
          <h3 className="font-display text-lg font-semibold text-white">Payroll guardrail</h3>
        </div>
        <p className="mt-2 text-sm text-neutral-500">
          Enter a valid approved compensation band above (min less than max) to run band, EPFO
          ceiling, and Section 80CCD(2) checks before export.
        </p>
      </div>
    );
  }

  const passed = guardrail?.verdict === "pass";

  return (
    <div
      className={`rounded-2xl border p-6 shadow-inner-edge ${
        passed ? "border-white/[0.08] bg-surface" : "border-gold/30 bg-gold/[0.04]"
      }`}
    >
      <div className="flex items-center gap-2">
        <ShieldCheck className={`h-4 w-4 ${passed ? "text-emerald-400/80" : "text-gold-bright"}`} />
        <h3 className="font-display text-lg font-semibold text-white">Payroll guardrail</h3>
        {guardrail && (
          <span
            className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium ${
              passed ? "bg-emerald-400/10 text-emerald-300" : "bg-gold/10 text-gold-bright"
            }`}
          >
            {passed ? "Clear to export" : "Needs review"}
          </span>
        )}
      </div>

      {!guardrail ? (
        <div className="mt-4 space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-white/[0.04]" />
          ))}
        </div>
      ) : (
        <ul className="mt-4 space-y-2.5">
          {guardrail.checks.map((c) => (
            <li key={c.id} className="flex items-start gap-2.5 text-sm">
              {c.passed ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400/80" />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-gold-bright" />
              )}
              <div>
                <p className="text-neutral-300">{c.label}</p>
                <p className="text-xs text-neutral-500">{c.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
