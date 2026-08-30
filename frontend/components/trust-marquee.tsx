"use client";

import { motion } from "framer-motion";
import {
  Hexagon,
  Diamond,
  Triangle,
  Square,
  Circle,
  Component,
  Orbit,
  Aperture,
  Layers,
  Compass,
  Shapes,
  Gem,
  Blend,
  Boxes,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const ROW_1: { name: string; icon: LucideIcon }[] = [
  { name: "Northwind", icon: Hexagon },
  { name: "Fenwick & Rao", icon: Diamond },
  { name: "Meridian", icon: Triangle },
  { name: "Solace Labs", icon: Component },
  { name: "Kavaan", icon: Orbit },
  { name: "Ridgeline", icon: Square },
  { name: "Attar & Co", icon: Aperture },
];

const ROW_2: { name: string; icon: LucideIcon }[] = [
  { name: "Vantage Point", icon: Circle },
  { name: "Harrow & Vale", icon: Layers },
  { name: "Ilio Systems", icon: Compass },
  { name: "Cascade Union", icon: Shapes },
  { name: "Bellwether", icon: Gem },
  { name: "Torrent Labs", icon: Blend },
  { name: "Ferro & Kane", icon: Boxes },
];

function Mark({ name, icon: Icon }: { name: string; icon: LucideIcon }) {
  return (
    <span className="group mx-6 flex shrink-0 items-center gap-2.5 rounded-full px-3 py-1.5 transition-colors duration-300 hover:bg-white/[0.03]">
      <Icon
        className="h-4 w-4 text-neutral-700 transition-all duration-300 group-hover:text-gold-bright group-hover:drop-shadow-[0_0_6px_rgba(243,186,47,0.5)]"
        strokeWidth={1.5}
      />
      <span className="font-display text-lg font-medium tracking-tight text-neutral-600 transition-colors duration-300 group-hover:text-neutral-200">
        {name}
      </span>
    </span>
  );
}

function MarqueeRow({
  items,
  direction,
}: {
  items: { name: string; icon: LucideIcon }[];
  direction: "forward" | "reverse";
}) {
  const loop = [...items, ...items];
  return (
    <div
      className="marquee-row relative overflow-hidden"
      style={{
        maskImage:
          "linear-gradient(to right, transparent, black 12%, black 88%, transparent)",
        WebkitMaskImage:
          "linear-gradient(to right, transparent, black 12%, black 88%, transparent)",
      }}
    >
      <div
        className={`flex w-max items-center ${
          direction === "forward" ? "animate-marquee" : "animate-marquee-reverse"
        }`}
      >
        {loop.map((item, i) => (
          <Mark key={`${item.name}-${i}`} name={item.name} icon={item.icon} />
        ))}
      </div>
    </div>
  );
}

export default function TrustMarquee() {
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="relative overflow-hidden border-y border-white/[0.06] bg-surface/40 py-12 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04),inset_0_-1px_0_0_rgba(255,255,255,0.02)]"
    >
      {/* Recessed-strip depth: faint centered vignette + top/bottom fades */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 100% at 50% 50%, rgba(212,175,55,0.05), transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent"
      />

      <div className="relative mx-auto max-w-7xl px-6 md:px-10">
        <p className="mb-8 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-neutral-600">
          Built to structure payroll for companies like
        </p>
      </div>

      <div className="relative flex flex-col gap-5">
        <MarqueeRow items={ROW_1} direction="forward" />
        <MarqueeRow items={ROW_2} direction="reverse" />
      </div>
    </motion.section>
  );
}
