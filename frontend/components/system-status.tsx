"use client";

import { useEffect, useState } from "react";
import type { HealthResponse } from "@/lib/demo-data";

type Status = "checking" | "ai_active" | "fallback" | "unreachable";

export default function SystemStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    fetch("/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json: HealthResponse) => {
        if (!cancelled) setStatus(json.ai_layer_active ? "ai_active" : "fallback");
      })
      .catch(() => {
        if (!cancelled) setStatus("unreachable");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const label =
    status === "checking"
      ? "CONNECTING…"
      : status === "ai_active"
        ? "AI LAYER: ACTIVE"
        : status === "fallback"
          ? "AI LAYER: DETERMINISTIC FALLBACK"
          : "SYSTEM OFFLINE";

  const dotColor =
    status === "ai_active"
      ? "bg-gold-bright shadow-glow-gold"
      : status === "fallback"
        ? "bg-neutral-400"
        : status === "unreachable"
          ? "bg-red-500/70"
          : "bg-neutral-600";

  return (
    <div className="flex items-center gap-2 font-mono text-xs text-neutral-500">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      <span>{`> 01 / ${label}`}</span>
    </div>
  );
}
