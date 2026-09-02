"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { UserPlus, ShieldCheck, Route, Landmark, Send } from "lucide-react";

const TABS = [
  {
    key: "onboarding",
    label: "New hire onboarding",
    icon: UserPlus,
    stat: "5 min",
    statLabel: "from offer letter to structure",
    headline: "Turn an offer letter into a compliant structure in minutes.",
    body: "Extraction pulls basic, HRA, LTA and PF straight out of messy offer-letter text and structures it optimally — checked against your approved compensation bands before the offer ever goes out.",
    gradient: "from-[#1a1f2a] via-[#0a0a0a] to-black",
  },
  {
    key: "compliance",
    label: "Payroll compliance",
    icon: ShieldCheck,
    stat: "3 guardrails",
    statLabel: "checked before every disbursement",
    headline: "Every structure checked against your bands and statutory caps.",
    body: "Band cost-neutrality, the EPFO aggregate contribution ceiling, and the Section 124 employer-NPS cap (formerly 80CCD(2)) — enforced automatically, deterministically, before anything reaches payroll.",
    gradient: "from-[#0f241a] via-[#0a0a0a] to-black",
  },
  {
    key: "audit",
    label: "Audit at scale",
    icon: Route,
    stat: "60 rows",
    statLabel: "audited end-to-end in one sweep",
    headline: "Audit a whole payroll, not one hire at a time.",
    body: "Upload a CSV of existing structures — every row gets a real compliance check and guardrail verdict, then routes itself by severity (clean, needs review, guardrail not run, escalated) before Finance opens a single one. Bulk-approve only ever touches the clean rows.",
    gradient: "from-[#2a1414] via-[#0a0a0a] to-black",
  },
  {
    key: "treasury",
    label: "Treasury & funding",
    icon: Landmark,
    stat: "48h",
    statLabel: "funding lead time forecasted",
    headline: "Know your capital outlay before payroll runs.",
    body: "Net take-home, TDS escrow, and the EPFO challan — forecasted and summed into a single capital number, so treasury always knows what to fund and by when.",
    gradient: "from-[#2a2210] via-[#0a0a0a] to-black",
  },
  {
    key: "export",
    label: "RazorpayX export",
    icon: Send,
    stat: "1 click",
    statLabel: "schema-accurate payout export",
    headline: "Export straight to a RazorpayX-ready payout.",
    body: "A real Composite Payout payload — nested contact and bank account details, amount in paise — generated automatically. No manual re-entry, no format guesswork.",
    gradient: "from-[#241a2a] via-[#0a0a0a] to-black",
  },
];

export default function IndustryTabs() {
  const [active, setActive] = useState(0);
  const current = TABS[active];

  return (
    <section className="mx-auto max-w-7xl px-6 py-28 md:px-10">
      <div className="mb-10 max-w-2xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">
          {"> 03 / BUILT FOR"}
        </p>
        <h2 className="mt-3 font-display text-3xl font-semibold leading-tight text-white sm:text-4xl">
          One engine, every stage of payroll.
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[280px_1fr]">
        <div className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
          {TABS.map((tab, i) => {
            const Icon = tab.icon;
            const isActive = i === active;
            return (
              <button
                key={tab.key}
                onClick={() => setActive(i)}
                className={`group relative flex shrink-0 items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-colors lg:w-full ${
                  isActive
                    ? "border-white/15 bg-white/[0.05] text-white"
                    : "border-transparent text-neutral-500 hover:border-white/[0.08] hover:text-neutral-300"
                }`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 ${isActive ? "text-gold-bright" : "text-neutral-600 group-hover:text-neutral-400"}`}
                />
                <span className="whitespace-nowrap font-medium lg:whitespace-normal">
                  {tab.label}
                </span>
                {isActive && (
                  <motion.span
                    layoutId="tab-indicator"
                    className="absolute inset-y-0 left-0 hidden w-0.5 rounded-full bg-gold-bright lg:block"
                    transition={{ type: "spring", stiffness: 400, damping: 35 }}
                  />
                )}
              </button>
            );
          })}
        </div>

        <div className="relative min-h-[320px] overflow-hidden rounded-2xl border border-white/[0.08]">
          <AnimatePresence mode="wait">
            <motion.div
              key={current.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className={`flex h-full flex-col justify-between bg-gradient-to-br p-8 sm:p-10 ${current.gradient}`}
            >
              <div className="flex items-start justify-between gap-6">
                <h3 className="max-w-md font-display text-2xl font-semibold leading-snug text-white sm:text-3xl">
                  {current.headline}
                </h3>
                <div className="shrink-0 rounded-xl border border-white/10 bg-black/40 px-4 py-3 text-right backdrop-blur-sm">
                  <div className="font-display text-2xl font-semibold text-gold-bright">
                    {current.stat}
                  </div>
                  <div className="mt-0.5 text-xs text-neutral-500">
                    {current.statLabel}
                  </div>
                </div>
              </div>
              <p className="mt-6 max-w-lg text-sm leading-relaxed text-neutral-400">
                {current.body}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
