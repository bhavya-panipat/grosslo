"use client";

import { useState } from "react";
import { motion, useMotionValueEvent, useScroll } from "framer-motion";
import ComingSoonLink from "@/components/coming-soon-link";

const NAV_LINKS = [
  { label: "Product", href: "/#product" },
  { label: "Audit", href: "/optimize/batch" },
  { label: "HR", href: "/hr" },
  { label: "Finance", href: "/finance" },
  { label: "Pricing", href: null },
  { label: "Docs", href: null },
];

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const { scrollY } = useScroll();

  useMotionValueEvent(scrollY, "change", (latest) => {
    setScrolled(latest > 24);
  });

  return (
    <div className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-4">
      <motion.nav
        initial={{ maxWidth: 880, paddingLeft: 14, paddingRight: 14 }}
        animate={{
          // 640 was tuned before Audit/HR/Finance existed as nav links —
          // with all 6 links + logo + actions, content needs ~727px at
          // the compact padding below; 640 forced "Get started" to
          // overflow the pill's right edge by ~69px. 760 actually fits.
          maxWidth: scrolled ? 760 : 880,
          paddingLeft: scrolled ? 10 : 14,
          paddingRight: scrolled ? 10 : 14,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 40 }}
        className="flex w-full items-center justify-between gap-6 rounded-full border border-white/10 bg-black/60 py-2 shadow-[0_1px_0_0_rgba(255,255,255,0.06)_inset] backdrop-blur-xl"
      >
        <a
          href="/"
          className="flex shrink-0 items-center gap-2 rounded-full px-2 py-1 text-[15px] font-semibold tracking-tight text-white"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-gold shadow-glow-gold" />
          grosslo
        </a>

        <div className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) =>
            link.href ? (
              <a
                key={link.label}
                href={link.href}
                className="rounded-full px-3 py-1.5 text-sm text-neutral-400 transition-colors hover:bg-white/[0.04] hover:text-white"
              >
                {link.label}
              </a>
            ) : (
              <ComingSoonLink
                key={link.label}
                className="rounded-full px-3 py-1.5 text-sm text-neutral-400"
              >
                {link.label}
              </ComingSoonLink>
            ),
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <ComingSoonLink className="hidden rounded-full px-3 py-1.5 text-sm text-neutral-300 sm:inline-block">
            Sign in
          </ComingSoonLink>
          <a
            href="/optimize"
            className="rounded-full bg-white px-4 py-1.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.03] active:scale-[0.98]"
          >
            Get started
          </a>
        </div>
      </motion.nav>
    </div>
  );
}
