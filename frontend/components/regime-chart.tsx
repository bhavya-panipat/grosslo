"use client";

import { useId, useMemo, useState } from "react";
import type { SensitivityPoint } from "@/lib/demo-data";
import { scale, smoothPath } from "@/lib/chart-utils";

const WIDTH = 420;
const HEIGHT = 200;
const PAD = 16;
const SPLIT_CTC = 2_500_000;

function ChartSkeleton() {
  return (
    <div className="flex h-full flex-col">
      <div className="h-5 w-48 animate-pulse rounded bg-white/[0.06]" />
      <div className="mt-2 h-4 w-64 animate-pulse rounded bg-white/[0.04]" />
      <div className="mt-6 flex-1 animate-pulse rounded-xl bg-white/[0.03]" />
    </div>
  );
}

export default function RegimeChart({
  points,
}: {
  points: SensitivityPoint[] | null;
}) {
  const [band, setBand] = useState<"low" | "high">("low");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const gradientId = useId();

  const banded = useMemo(() => {
    if (!points) return [];
    return points.filter((p) =>
      band === "low" ? p.ctc <= SPLIT_CTC : p.ctc > SPLIT_CTC,
    );
  }, [points, band]);

  if (!points || banded.length < 2) {
    return <ChartSkeleton />;
  }

  const toL = (v: number) => Math.round((v / 100_000) * 10) / 10;

  const allTax = banded.flatMap((p) => [p.old_tax, p.new_tax]);
  const minY = 0;
  const maxY = Math.max(...allTax) * 1.15;
  const minX = banded[0].ctc;
  const maxX = banded[banded.length - 1].ctc;

  const xs = scale(
    banded.map((p) => p.ctc),
    minX,
    maxX,
    WIDTH,
    PAD,
  );
  const oldYs = scale(
    banded.map((p) => p.old_tax),
    minY,
    maxY,
    HEIGHT,
    PAD,
  ).map((y) => HEIGHT - y);
  const newYs = scale(
    banded.map((p) => p.new_tax),
    minY,
    maxY,
    HEIGHT,
    PAD,
  ).map((y) => HEIGHT - y);

  const oldPath = smoothPath(xs, oldYs);
  const newPath = smoothPath(xs, newYs);
  const areaPath = `${newPath} L ${xs[xs.length - 1]},${HEIGHT} L ${xs[0]},${HEIGHT} Z`;

  const active = hoverIndex !== null ? banded[hoverIndex] : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-lg font-semibold text-white">
            Old regime vs. new regime
          </h3>
          <p className="mt-1 text-sm text-neutral-500">
            Live from the optimizer — ₹4L rent, metro, NPS opted in.
          </p>
        </div>
        <div className="flex shrink-0 gap-1 rounded-full border border-white/10 bg-black/40 p-1">
          {(["low", "high"] as const).map((key) => (
            <button
              key={key}
              onClick={() => {
                setBand(key);
                setHoverIndex(null);
              }}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                band === key
                  ? "bg-white text-black"
                  : "text-neutral-400 hover:text-white"
              }`}
            >
              {key === "low" ? "4L–25L" : "25L–60L"}
            </button>
          ))}
        </div>
      </div>

      <div className="relative mt-4 flex-1">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-full w-full overflow-visible"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#F3BA2F" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#F3BA2F" stopOpacity="0" />
            </linearGradient>
          </defs>

          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1={PAD}
              x2={WIDTH - PAD}
              y1={PAD + f * (HEIGHT - PAD * 2)}
              y2={PAD + f * (HEIGHT - PAD * 2)}
              stroke="rgba(255,255,255,0.06)"
              strokeWidth={1}
            />
          ))}

          <path d={areaPath} fill={`url(#${gradientId})`} />
          <path
            d={oldPath}
            fill="none"
            stroke="rgba(255,255,255,0.35)"
            strokeWidth={2}
            strokeLinecap="round"
          />
          <path
            d={newPath}
            fill="none"
            stroke="#F3BA2F"
            strokeWidth={2.5}
            strokeLinecap="round"
          />

          {xs.map((x, i) => (
            <g key={i}>
              <rect
                x={x - WIDTH / xs.length / 2}
                y={0}
                width={WIDTH / xs.length}
                height={HEIGHT}
                fill="transparent"
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex((cur) => (cur === i ? null : cur))}
              />
              <circle
                cx={x}
                cy={newYs[i]}
                r={hoverIndex === i ? 4.5 : 3}
                fill="#F3BA2F"
                className="transition-all"
                pointerEvents="none"
              />
              <circle
                cx={x}
                cy={oldYs[i]}
                r={hoverIndex === i ? 4.5 : 3}
                fill="rgba(255,255,255,0.6)"
                className="transition-all"
                pointerEvents="none"
              />
            </g>
          ))}
        </svg>

        {active && (
          <div
            className="pointer-events-none absolute -top-1 rounded-lg border border-white/10 bg-black/90 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur-sm"
            style={{
              left: `${(xs[hoverIndex!] / WIDTH) * 100}%`,
              transform: "translate(-50%, -100%)",
            }}
          >
            <div className="font-mono text-neutral-500">
              ₹{toL(active.ctc)}L CTC
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-gold-bright">
              <span className="h-1.5 w-1.5 rounded-full bg-gold-bright" />
              New ₹{toL(active.new_tax)}L
            </div>
            <div className="flex items-center gap-1.5 text-neutral-300">
              <span className="h-1.5 w-1.5 rounded-full bg-white/60" />
              Old ₹{toL(active.old_tax)}L
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center gap-4 text-xs text-neutral-500">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-gold-bright" /> New regime
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-white/60" /> Old regime
        </span>
      </div>
    </div>
  );
}
