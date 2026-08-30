"use client";

import { Sparkles, Zap } from "lucide-react";
import type { OptimizeResponse } from "@/lib/api-types";

type Capability = { label: string; aiBacked: boolean; note?: string };

export default function CapabilityStrip({
  data,
  extractionRan,
}: {
  data: OptimizeResponse;
  extractionRan: boolean;
}) {
  const capabilities: Capability[] = [
    { label: "Tax calculation", aiBacked: false, note: "always deterministic" },
    { label: "Explanation", aiBacked: data.explanation.ai_backed },
    { label: "Compliance flags", aiBacked: data.compliance.ai_backed, note: "rule-matching always deterministic" },
  ];
  if (extractionRan) {
    capabilities.unshift({ label: "Offer letter extraction", aiBacked: false });
  }

  return (
    <div className="flex flex-wrap gap-2">
      {capabilities.map((c) => (
        <div
          key={c.label}
          className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-neutral-400"
          title={c.note}
        >
          {c.aiBacked ? (
            <Sparkles className="h-3 w-3 text-gold-bright" />
          ) : (
            <Zap className="h-3 w-3 text-neutral-500" />
          )}
          {c.label}
          <span className="text-neutral-600">{c.aiBacked ? "AI-generated" : "rule-based"}</span>
        </div>
      ))}
    </div>
  );
}
