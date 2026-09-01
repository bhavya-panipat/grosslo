"use client";

import { CheckCircle2, XCircle, Send, Loader2 } from "lucide-react";
import type { BatchAuditRow } from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

function VerdictBadge({ verdict }: { verdict?: "pass" | "flag" }) {
  if (!verdict) return <span className="text-neutral-600">—</span>;
  const passed = verdict === "pass";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
        passed ? "bg-emerald-400/10 text-emerald-300" : "bg-gold/10 text-gold-bright"
      }`}
    >
      {passed ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {passed ? "Pass" : "Flag"}
    </span>
  );
}

export type CorrectionStatus = "idle" | "submitting" | "submitted" | "error";

export function AuditBatchTable({
  rows,
  correctionStatus,
  onSubmitCorrection,
}: {
  rows: BatchAuditRow[];
  correctionStatus?: Record<number, CorrectionStatus>;
  onSubmitCorrection?: (rowIndex: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/[0.08] bg-surface shadow-inner-edge">
      <table className="w-full min-w-[840px] text-sm">
        <thead>
          <tr className="border-b border-white/[0.08] text-left text-xs uppercase tracking-wide text-neutral-500">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Current tax</th>
            <th className="px-4 py-3 font-medium">Unclaimed savings</th>
            <th className="px-4 py-3 font-medium">Excess contribution</th>
            <th className="px-4 py-3 font-medium">Guardrail</th>
            <th className="px-4 py-3 font-medium">Correction</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const flagged = (row.unclaimed_savings ?? 0) > 0 || (row.excess_contribution ?? 0) > 0;
            const status = correctionStatus?.[row.row_index] ?? "idle";
            return (
              <tr key={row.row_index} className="border-b border-white/[0.04] text-neutral-300 transition-colors hover:bg-white/[0.02]">
                {row.error ? (
                  <>
                    <td className="px-4 py-3 font-mono text-xs text-neutral-500">Row {row.row_index + 1}</td>
                    <td colSpan={5} className="px-4 py-3 text-xs text-red-400/80">{row.error}</td>
                  </>
                ) : (
                  <>
                    <td className="px-4 py-3">{row.name}</td>
                    <td className="px-4 py-3 font-mono">{inr(row.current_tax ?? 0)}</td>
                    <td className="px-4 py-3 font-mono text-gold-bright">{inr(row.unclaimed_savings ?? 0)}</td>
                    <td className="px-4 py-3 font-mono">
                      {(row.excess_contribution ?? 0) > 0 ? inr(row.excess_contribution!) : "—"}
                    </td>
                    <td className="px-4 py-3"><VerdictBadge verdict={row.guardrail?.verdict} /></td>
                    <td className="px-4 py-3">
                      {!flagged ? (
                        <span className="text-xs text-neutral-600">Nothing to correct</span>
                      ) : status === "submitted" ? (
                        <span className="inline-flex items-center gap-1 text-xs text-emerald-300">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Sent to Finance
                        </span>
                      ) : (
                        <button
                          onClick={() => onSubmitCorrection?.(row.row_index)}
                          disabled={status === "submitting"}
                          className="inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold/[0.06] px-3 py-1 text-xs font-medium text-gold-bright transition-colors hover:bg-gold/[0.12] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {status === "submitting" ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Send className="h-3 w-3" />
                          )}
                          Submit correction
                        </button>
                      )}
                      {status === "error" && (
                        <p className="mt-1 text-xs text-red-400/80">Couldn&apos;t submit — try again.</p>
                      )}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
