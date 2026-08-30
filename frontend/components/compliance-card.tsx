"use client";

import { CheckCircle2, ShieldAlert } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { OptimizeResponse } from "@/lib/api-types";

const SEVERITY_COLOR: Record<string, string> = {
  High: "text-gold-bright",
  Medium: "text-amber-300/80",
  Low: "text-neutral-400",
};

const CHECKED_AGAINST_LABEL: Record<string, string> = {
  as_offered: "Checked against: as offered",
  recommended: "Checked against: recommended structure",
};

export default function ComplianceCard({ data }: { data: OptimizeResponse | null }) {
  const flags = data?.compliance.flags ?? [];

  return (
    <CardShell className="flex flex-col">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gold/10 blur-2xl transition-opacity group-hover:opacity-100"
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-neutral-300">
          <ShieldAlert className="h-4 w-4 text-gold-bright" />
          <h3 className="font-display text-lg font-semibold text-white">
            Compliance, checked
          </h3>
        </div>
        {data && (
          <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-neutral-500">
            {CHECKED_AGAINST_LABEL[data.compliance_checked_against] ?? data.compliance_checked_against}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        Every structure runs against a fixed rule set before it ever reaches you.
      </p>

      {!data ? (
        <div className="mt-5 space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-white/[0.04]" />
          ))}
        </div>
      ) : flags.length === 0 ? (
        <div className="mt-5 flex items-center gap-2.5 text-sm text-neutral-400">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400/80" />
          No compliance flags on this structure.
        </div>
      ) : (
        <ul className="mt-5 space-y-3">
          {flags.map((flag) => (
            <li key={flag.rule_id} className="flex items-start gap-2.5 text-sm">
              <ShieldAlert
                className={`mt-0.5 h-4 w-4 shrink-0 ${SEVERITY_COLOR[flag.severity] ?? "text-neutral-400"}`}
              />
              <span className="text-neutral-300">{flag.message}</span>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}
