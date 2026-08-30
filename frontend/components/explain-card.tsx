"use client";

import { Sparkles } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { OptimizeResponse } from "@/lib/api-types";

export default function ExplainCard({ data }: { data: OptimizeResponse | null }) {
  return (
    <CardShell className="md:col-span-3">
      <div className="flex flex-col gap-6 md:flex-row md:items-center">
        <div className="flex items-center gap-2 md:w-64 md:shrink-0">
          <Sparkles className="h-4 w-4 text-gold-bright" />
          <h3 className="font-display text-lg font-semibold text-white">
            Explained, not just computed
          </h3>
        </div>
        <div className="flex-1 rounded-xl border border-white/[0.06] bg-black/40 p-4 font-mono text-xs leading-relaxed text-neutral-500">
          <div className="mb-2 flex items-center justify-between text-neutral-600">
            <span>{'> grosslo.explain(structure, regime="' + (data?.recommended_regime ?? "…") + '")'}</span>
            {data && (
              <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-neutral-500">
                {data.explanation.ai_backed ? "AI-generated" : "rule-based"}
              </span>
            )}
          </div>
          {!data ? (
            <div className="space-y-2">
              <div className="h-3 w-full animate-pulse rounded bg-white/[0.04]" />
              <div className="h-3 w-4/5 animate-pulse rounded bg-white/[0.04]" />
              <div className="h-3 w-3/5 animate-pulse rounded bg-white/[0.04]" />
            </div>
          ) : (
            <p className="text-neutral-400">{data.explanation.explanation}</p>
          )}
        </div>
      </div>
    </CardShell>
  );
}
