"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";
import type { OptimizeResponse } from "@/lib/api-types";

function useCountUp(target: number, durationMs = 900) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);
  return value;
}

export default function RecommendationBanner({ data }: { data: OptimizeResponse }) {
  const saving = useCountUp(data.annual_saving);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col gap-4 rounded-2xl border border-white/[0.08] bg-gradient-to-br from-surface-raised to-surface p-6 shadow-inner-edge sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold/10">
          <TrendingUp className="h-5 w-5 text-gold-bright" />
        </div>
        <div>
          <p className="text-sm text-neutral-500">Recommended</p>
          <p className="font-display text-xl font-semibold text-white">
            {data.recommended_regime === "new" ? "New regime" : "Old regime"}
          </p>
        </div>
      </div>
      <div className="text-left sm:text-right">
        <p className="text-sm text-neutral-500">Annual saving</p>
        <p className="font-display text-3xl font-semibold text-gold-bright">
          ₹{saving.toLocaleString("en-IN")}
        </p>
      </div>
    </motion.div>
  );
}
