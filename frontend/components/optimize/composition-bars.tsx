"use client";

import { useEffect, useState } from "react";
import CardShell from "@/components/card-shell";
import type { OptResult } from "@/lib/api-types";

const COMPONENTS: { key: keyof OptResult["structure"]; label: string; color: string }[] = [
  { key: "basic", label: "Basic", color: "rgba(255,255,255,0.85)" },
  { key: "hra", label: "HRA", color: "rgba(255,255,255,0.55)" },
  { key: "lta", label: "LTA", color: "rgba(255,255,255,0.35)" },
  { key: "special_allowance", label: "Special allowance", color: "rgba(255,255,255,0.2)" },
  { key: "employer_pf", label: "Employer PF", color: "#D4AF37" },
  { key: "employer_nps", label: "Employer NPS", color: "#F3BA2F" },
];

function RegimeColumn({ label, result, mounted }: { label: string; result: OptResult; mounted: boolean }) {
  const total = result.structure.ctc || 1;
  return (
    <div>
      <p className="mb-3 text-sm font-medium text-neutral-300">{label}</p>
      <div className="space-y-2.5">
        {COMPONENTS.map((c) => {
          const value = result.structure[c.key] as number;
          const pct = (value / total) * 100;
          return (
            <div key={c.key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-neutral-500">{c.label}</span>
                <span className="font-mono text-neutral-400">₹{Math.round(value).toLocaleString("en-IN")}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.04]">
                <div
                  className="h-full rounded-full transition-all duration-700 ease-out"
                  style={{ width: mounted ? `${pct}%` : "0%", backgroundColor: c.color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CompositionBars({
  oldResult,
  newResult,
}: {
  oldResult: OptResult;
  newResult: OptResult;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <CardShell>
      <h3 className="font-display text-lg font-semibold text-white">Structure comparison</h3>
      <p className="mt-1 text-sm text-neutral-500">How the same CTC splits across each regime.</p>
      <div className="mt-6 grid grid-cols-1 gap-8 sm:grid-cols-2">
        <RegimeColumn label="Old regime" result={oldResult} mounted={mounted} />
        <RegimeColumn label="New regime" result={newResult} mounted={mounted} />
      </div>
    </CardShell>
  );
}
