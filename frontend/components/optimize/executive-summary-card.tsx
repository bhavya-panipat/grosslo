"use client";

import { motion } from "framer-motion";
import { ClipboardCheck, ShieldCheck, Landmark, TrendingUp } from "lucide-react";
import type { BatchAuditRow } from "@/lib/api-types";
import { totalCapitalOutlay } from "@/lib/treasury";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// The four metrics here are deliberately the ONLY four in this card, each
// pinned to an exact, already-computed source — no new backend logic, no
// new classification. See app.py's api_batch_audit() docstring for the
// orchestration.route reuse this Clean Rate metric depends on.
export default function ExecutiveSummaryCard({
  processedCount,
  submittedCount,
  rows,
}: {
  processedCount: number;
  submittedCount: number;
  rows: BatchAuditRow[];
}) {
  const validRows = rows.filter((r) => !r.error);
  const cleanCount = validRows.filter((r) => r.orchestration?.route === "auto_pass_candidate").length;
  const cleanRatePct = validRows.length > 0 ? (cleanCount / validRows.length) * 100 : 0;
  const totalLiability = totalCapitalOutlay(validRows);
  const totalTaxInefficiency = validRows.reduce((sum, r) => sum + (r.unclaimed_savings ?? 0), 0);
  const throughputPct = submittedCount > 0 ? (processedCount / submittedCount) * 100 : 0;

  const metrics = [
    {
      icon: ClipboardCheck,
      label: "Processed Records",
      value: `${processedCount} / ${submittedCount}`,
      detail: `${throughputPct.toFixed(0)}% throughput`,
    },
    {
      icon: ShieldCheck,
      label: "Compliance Clean Rate",
      value: `${cleanRatePct.toFixed(0)}%`,
      detail: `${cleanCount} of ${validRows.length} auto-pass candidates`,
    },
    {
      icon: Landmark,
      label: "Total Monthly Payroll Liability",
      value: inr(totalLiability),
      detail: "Net take-home + TDS escrow + EPFO challan, summed across all processed rows",
    },
    {
      icon: TrendingUp,
      label: "Discovered Annual Tax Inefficiency",
      value: inr(totalTaxInefficiency),
      detail: "Gap between current structures and the optimal split, summed",
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
    >
      {metrics.map((m) => (
        <div key={m.label} className="rounded-2xl border border-white/[0.08] bg-surface p-5 shadow-inner-edge">
          <div className="flex items-center gap-2 text-neutral-400">
            <m.icon className="h-4 w-4 text-gold-bright" />
            <span className="text-xs uppercase tracking-wide">{m.label}</span>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-white">{m.value}</p>
          <p className="mt-1 text-[11px] text-neutral-600">{m.detail}</p>
        </div>
      ))}
    </motion.div>
  );
}
