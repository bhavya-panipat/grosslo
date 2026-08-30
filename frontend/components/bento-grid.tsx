"use client";

import { useEffect, useState } from "react";
import RegimeChart from "@/components/regime-chart";
import RingMetrics from "@/components/ring-metric";
import CardShell from "@/components/card-shell";
import ComplianceCard from "@/components/compliance-card";
import ExplainCard from "@/components/explain-card";
import {
  DEMO_PAYLOAD,
  type OptimizeResponse,
  type SensitivityResponse,
} from "@/lib/demo-data";

export default function BentoGrid() {
  const [optimizeData, setOptimizeData] = useState<OptimizeResponse | null>(null);
  const [sensitivityData, setSensitivityData] = useState<SensitivityResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(DEMO_PAYLOAD),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json) => {
        if (!cancelled) setOptimizeData(json);
      })
      .catch(() => {
        /* backend not reachable — cards stay in their skeleton/empty state */
      });

    fetch("/api/sensitivity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rent_paid: DEMO_PAYLOAD.rent_paid,
        city: DEMO_PAYLOAD.city,
        nps_opted: DEMO_PAYLOAD.nps_opted,
      }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json) => {
        if (!cancelled) setSensitivityData(json);
      })
      .catch(() => {
        /* backend not reachable — chart stays in its skeleton state */
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section id="product" className="mx-auto max-w-7xl px-6 py-28 md:px-10">
      <div className="mb-12 max-w-2xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">
          {"> 02 / HOW IT WORKS"}
        </p>
        <h2 className="mt-3 font-display text-3xl font-semibold leading-tight text-white sm:text-4xl">
          A deterministic engine, with AI where it actually helps.
        </h2>
        <p className="mt-4 text-neutral-400">
          No LLM ever touches a tax figure. The math is a validated optimizer;
          the AI layer only explains it, extracts it, and phrases it clearly.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <CardShell className="md:col-span-2 md:row-span-2">
          <RegimeChart points={sensitivityData?.points ?? null} />
        </CardShell>
        <CardShell>
          <RingMetrics metrics={optimizeData?.metrics ?? null} />
        </CardShell>
        <ComplianceCard data={optimizeData} />
        <ExplainCard data={optimizeData} />
      </div>
    </section>
  );
}
