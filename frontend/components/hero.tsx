"use client";

import { motion, type Variants } from "framer-motion";
import { ArrowRight, ChevronRight } from "lucide-react";
import HeroCube from "@/components/hero-cube";
import SystemStatus from "@/components/system-status";
import ComingSoonLink from "@/components/coming-soon-link";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

const container: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.09, delayChildren: 0.1 },
  },
};

const item: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: EASE_OUT_EXPO },
  },
};

export default function Hero() {
  return (
    <section
      id="top"
      className="relative mx-auto flex min-h-screen w-full max-w-7xl items-center px-6 pt-32 pb-20 md:px-10"
    >
      <div className="grid w-full grid-cols-1 items-center gap-16 lg:grid-cols-2 lg:gap-8">
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="flex flex-col items-start"
        >
          <motion.div variants={item} className="mb-8">
            <ComingSoonLink className="group inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-neutral-300">
              grosslo 1.0 is now live
              <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </ComingSoonLink>
          </motion.div>

          <motion.h1
            variants={item}
            className="font-display text-5xl font-semibold leading-[1.1] tracking-tight text-white sm:text-6xl lg:text-[4.25rem]"
          >
            Structure payroll.
            <br />
            Enforce every guardrail.
          </motion.h1>

          <motion.p
            variants={item}
            className="mt-6 max-w-xl text-lg leading-relaxed text-neutral-400"
          >
            grosslo is an AI-assisted compensation controller for HR and
            finance teams — it structures CTC into a compliant split, checks
            it against your approved bands and statutory ceilings, forecasts
            the capital you need, and generates a RazorpayX-ready payout
            payload — no live dispatch, by design. No invented figures, ever.
          </motion.p>

          <motion.div variants={item} className="mt-10 flex flex-wrap items-center gap-3">
            <a
              href="/optimize"
              className="group inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98]"
            >
              Get started
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </a>
            <a
              href="/#product"
              className="inline-flex items-center gap-2 rounded-full border border-white/10 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-white/20 hover:bg-white/[0.04]"
            >
              See how it works
            </a>
          </motion.div>

          <motion.div variants={item} className="mt-14">
            <SystemStatus />
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.2 }}
          className="relative h-[380px] sm:h-[460px] lg:h-[600px]"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-radial-warm blur-2xl"
          />
          <HeroCube />
        </motion.div>
      </div>
    </section>
  );
}
