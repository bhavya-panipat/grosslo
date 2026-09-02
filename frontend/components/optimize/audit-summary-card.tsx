"use client";

import { motion } from "framer-motion";
import { AlertTriangle, Scale } from "lucide-react";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// Secondary, exception-type-level detail — deliberately does NOT repeat
// clean/flagged counts or a total-savings figure, since ExecutiveSummaryCard
// above already reports those (Compliance Clean Rate, Discovered Annual Tax
// Inefficiency). Keeping both would risk two numbers answering "how many
// rows are fine" on the same screen; this card exists for the one thing the
// executive card doesn't cover — breakdown BY exception type.
export default function AuditSummaryCard({
  flaggedCount,
  epfoCapExceededCount,
  regimeMismatchCount,
  totalExcessContribution,
}: {
  flaggedCount: number;
  epfoCapExceededCount: number;
  regimeMismatchCount: number;
  totalExcessContribution: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge"
    >
      <div className="flex items-center gap-2 text-neutral-400">
        <Scale className="h-4 w-4 text-gold-bright" />
        <span className="text-sm">Exception breakdown</span>
      </div>
      <p className="mt-2 text-xs text-neutral-600">
        Of the {flaggedCount} flagged row{flaggedCount === 1 ? "" : "s"}: {epfoCapExceededCount} over the
        ₹7.5L aggregate EPFO ceiling, {regimeMismatchCount} filed under the wrong regime for their own
        structure — these can overlap on the same row, so they aren&rsquo;t claimed to sum to{" "}
        {flaggedCount} exactly.
      </p>
      <div className="mt-3 flex items-center gap-2 text-gold-bright">
        <AlertTriangle className="h-4 w-4" />
        <span className="font-display text-lg font-semibold">{inr(totalExcessContribution)}</span>
        <span className="text-xs text-neutral-600">total excess EPFO contribution</span>
      </div>
    </motion.div>
  );
}
