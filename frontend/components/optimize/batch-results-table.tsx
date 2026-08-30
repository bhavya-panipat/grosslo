"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import type { OptimizeBatchRow, BatchAuditRow } from "@/lib/api-types";

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

export function NewHireBatchTable({ rows }: { rows: OptimizeBatchRow[] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/[0.08] bg-surface shadow-inner-edge">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-white/[0.08] text-left text-xs uppercase tracking-wide text-neutral-500">
            <th className="px-4 py-3 font-medium">Row</th>
            <th className="px-4 py-3 font-medium">CTC</th>
            <th className="px-4 py-3 font-medium">Regime</th>
            <th className="px-4 py-3 font-medium">Annual saving</th>
            <th className="px-4 py-3 font-medium">Guardrail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_index} className="border-b border-white/[0.04] text-neutral-300 transition-colors hover:bg-white/[0.02]">
              <td className="px-4 py-3 font-mono text-xs text-neutral-500">{row.row_index + 1}</td>
              {row.error ? (
                <td colSpan={4} className="px-4 py-3 text-xs text-red-400/80">{row.error}</td>
              ) : (
                <>
                  <td className="px-4 py-3 font-mono">{inr(row.ctc)}</td>
                  <td className="px-4 py-3 capitalize">{row.recommended_regime}</td>
                  <td className="px-4 py-3 font-mono text-gold-bright">{inr(row.annual_saving)}</td>
                  <td className="px-4 py-3"><VerdictBadge verdict={row.guardrail?.verdict} /></td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuditBatchTable({ rows }: { rows: BatchAuditRow[] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/[0.08] bg-surface shadow-inner-edge">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-white/[0.08] text-left text-xs uppercase tracking-wide text-neutral-500">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Current tax</th>
            <th className="px-4 py-3 font-medium">Unclaimed savings</th>
            <th className="px-4 py-3 font-medium">Excess contribution</th>
            <th className="px-4 py-3 font-medium">Guardrail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_index} className="border-b border-white/[0.04] text-neutral-300 transition-colors hover:bg-white/[0.02]">
              {row.error ? (
                <>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-500">Row {row.row_index + 1}</td>
                  <td colSpan={4} className="px-4 py-3 text-xs text-red-400/80">{row.error}</td>
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
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
