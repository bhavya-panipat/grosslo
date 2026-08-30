"use client";

import { motion } from "framer-motion";
import { AlertTriangle, TrendingUp } from "lucide-react";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

export default function AuditSummaryCard({
  totalExcessContribution,
  totalUnclaimedSavings,
}: {
  totalExcessContribution: number;
  totalUnclaimedSavings: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="grid grid-cols-1 gap-4 sm:grid-cols-2"
    >
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
    </motion.div>
  );
}
