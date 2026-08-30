"use client";

import { useEffect, useState } from "react";

type Metric = {
  label: string;
  value: number;
  color: string;
};

const SIZE = 132;
const STROKE = 8;
const RADIUS = (SIZE - STROKE) / 2;

export default function RingMetrics({
  metrics,
}: {
  metrics: {
    optimization_value_pct: number;
    compliance_pct: number;
    ai_coverage_pct: number;
  } | null;
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const items: Metric[] = [
    { label: "Optimization value", value: metrics?.optimization_value_pct ?? 0, color: "#F3BA2F" },
    { label: "Compliance", value: metrics?.compliance_pct ?? 0, color: "#7DD3A8" },
    { label: "AI coverage", value: metrics?.ai_coverage_pct ?? 0, color: "#9CA3AF" },
  ];

  return (
    <div className="flex h-full flex-col">
      <h3 className="font-display text-lg font-semibold text-white">
        Every recommendation, scored
      </h3>
      <p className="mt-1 text-sm text-neutral-500">
        Live signal on how much of the output is deterministic vs. AI-assisted.
      </p>

      <div className="mt-6 flex flex-1 items-center justify-center">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="h-40 w-40 -rotate-90">
          {items.map((m, i) => {
            const r = RADIUS - i * (STROKE + 4);
            const c = 2 * Math.PI * r;
            const offset = metrics && mounted ? c - (m.value / 100) * c : c;
            return (
              <g key={m.label}>
                <circle
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={r}
                  fill="none"
                  stroke="rgba(255,255,255,0.06)"
                  strokeWidth={STROKE}
                />
                <circle
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={r}
                  fill="none"
                  stroke={m.color}
                  strokeWidth={STROKE}
                  strokeLinecap="round"
                  strokeDasharray={c}
                  strokeDashoffset={offset}
                  style={{
                    transition: `stroke-dashoffset 1.1s cubic-bezier(0.16,1,0.3,1) ${i * 0.15}s`,
                  }}
                />
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-4 space-y-2">
        {items.map((m) => (
          <div key={m.label} className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-neutral-400">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: m.color }}
              />
              {m.label}
            </span>
            <span className="font-mono text-neutral-300">
              {metrics ? `${m.value}%` : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
