"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, TrendingUp, Scale } from "lucide-react";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

export default function AuditSummaryCard({
  totalRows,
  cleanCount,
  flaggedCount,
  epfoCapExceededCount,
  regimeMismatchCount,
  totalExcessContribution,
  totalUnclaimedSavings,
}: {
  totalRows: number;
  cleanCount: number;
  flaggedCount: number;
  epfoCapExceededCount: number;
  regimeMismatchCount: number;
  totalExcessContribution: number;
  totalUnclaimedSavings: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col gap-4"
    >
      <div className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge">
        <div className="flex items-center gap-2 text-neutral-400">
          <Scale className="h-4 w-4 text-gold-bright" />
          <span className="text-sm">Batch result — {totalRows} employee{totalRows === 1 ? "" : "s"} audited</span>
        </div>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <span className="inline-flex items-center gap-1.5 font-display text-xl font-semibold text-emerald-300">
            <CheckCircle2 className="h-4 w-4" /> {cleanCount} clean
          </span>
          <span className="inline-flex items-center gap-1.5 font-display text-xl font-semibold text-gold-bright">
            <AlertTriangle className="h-4 w-4" /> {flaggedCount} flagged
          </span>
        </div>
        <p className="mt-2 text-xs text-neutral-600">
          Of the flagged rows: {epfoCapExceededCount} over the ₹7.5L aggregate EPFO ceiling,{" "}
          {regimeMismatchCount} filed under the wrong regime for their own structure — these can
          overlap on the same row, so they aren&rsquo;t claimed to sum to {flaggedCount} exactly.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge">
          <div className="flex items-center gap-2 text-neutral-400">
            <AlertTriangle className="h-4 w-4 text-gold-bright" />
            <span className="text-sm">Total excess EPFO contribution</span>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-gold-bright">
            {inr(totalExcessContribution)}
          </p>
          <p className="mt-1 text-xs text-neutral-600">Sum across rows exceeding the ₹7.5L aggregate PF+NPS ceiling</p>
        </div>
        <div className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge">
          <div className="flex items-center gap-2 text-neutral-400">
            <TrendingUp className="h-4 w-4 text-gold-bright" />
            <span className="text-sm">Total unclaimed savings</span>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-gold-bright">
            {inr(totalUnclaimedSavings)}
          </p>
          <p className="mt-1 text-xs text-neutral-600">Gap between current structures and the optimal split, summed</p>
        </div>
      </div>
    </motion.div>
  );
}
