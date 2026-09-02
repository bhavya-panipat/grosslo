"use client";

import { motion } from "framer-motion";
import { AlertTriangle, Clock } from "lucide-react";
import type { PenaltyScenario } from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

export default function PenaltyScenarioTable({ scenario }: { scenario: PenaltyScenario }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge"
    >
      <div className="flex items-center gap-2 text-neutral-300">
        <Clock className="h-4 w-4 text-gold-bright" />
        <h3 className="font-display text-lg font-semibold text-white">Delayed-remittance scenario</h3>
      </div>

      {/* Non-dismissible disclaimer — always rendered, no close/hide control */}
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] p-3 text-xs text-amber-200/80">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {scenario.disclaimer}
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-white/[0.08] text-left text-xs uppercase tracking-wide text-neutral-500">
              <th className="py-2 pr-4 font-medium">Delay</th>
              <th className="py-2 pr-4 font-medium">Sec 7Q interest</th>
              <th className="py-2 pr-4 font-medium">Sec 14B damages</th>
              <th className="py-2 pr-4 font-medium" title="Section 398(3), formerly Section 201(1A) under the 1961 Act">
                Sec 398(3) interest
              </th>
              <th className="py-2 font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {scenario.rows.map((row) => (
              <tr key={row.months_delayed} className="border-b border-white/[0.04] text-neutral-300">
                <td className="py-2.5 pr-4 text-neutral-400">{row.months_delayed} mo</td>
                <td className="py-2.5 pr-4 font-mono">{inr(row.section_7q_interest)}</td>
                <td className="py-2.5 pr-4 font-mono">
                  {inr(row.section_14b_damages)}
                  {row.section_14b_cap_applied && (
                    <span className="ml-1.5 text-[10px] text-gold-bright">capped</span>
                  )}
                </td>
                <td className="py-2.5 pr-4 font-mono">{inr(row.section_201_1a_interest)}</td>
                <td className="py-2.5 font-mono font-medium text-white">{inr(row.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
