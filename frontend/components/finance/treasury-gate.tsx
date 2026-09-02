"use client";

import { Landmark, TriangleAlert, Loader2 } from "lucide-react";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// The one gate in this maker-checker flow based on something 100% real —
// an actual live RazorpayX account balance, not a demo approximation.
// Every other gate here is necessarily simulated, since there's no live
// dispatch anywhere in this product by design (see review_queue.py's own
// docstring). Fails closed on purpose: an unreachable/unconfigured/stale
// balance blocks bulk-approve exactly like a confirmed deficit does — "we
// couldn't verify there's enough money" is not a safe default to treat as
// "there's enough money."
export default function TreasuryGate({
  loading,
  live,
  error,
  availableRupees,
  requiredFunding,
  deficit,
}: {
  loading: boolean;
  live: boolean;
  error: string | null;
  availableRupees: number | null;
  requiredFunding: number;
  deficit: boolean;
}) {
  if (loading) {
    return (
      <div className="mb-6 flex items-center gap-2 rounded-xl border border-white/[0.08] bg-surface px-4 py-3 text-sm text-neutral-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Checking live RazorpayX account balance…
      </div>
    );
  }

  if (!live || availableRupees === null) {
    return (
      <div className="mb-6 flex items-start gap-2 rounded-xl border border-red-400/20 bg-red-400/[0.05] px-4 py-3 text-sm text-red-300">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Live RazorpayX balance unavailable{error ? ` (${error})` : ""} — bulk-approve is blocked until
          the balance can be confirmed. Individual row approval is unaffected.
        </span>
      </div>
    );
  }

  return (
    <div
      className={`mb-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border px-4 py-3 text-sm ${
        deficit ? "border-red-400/30 bg-red-400/[0.06]" : "border-white/[0.08] bg-surface"
      }`}
    >
      <div className="flex items-center gap-2 text-neutral-400">
        <Landmark className="h-4 w-4 text-gold-bright" />
        <span className="text-xs uppercase tracking-wide">Live treasury check</span>
      </div>
      <span className="text-neutral-300">
        Current RazorpayX Account Balance: <span className="font-mono text-white">{inr(availableRupees)}</span>
      </span>
      <span className="text-neutral-300">
        Required Treasury Funding (pending rows):{" "}
        <span className="font-mono text-white">{inr(requiredFunding)}</span>
      </span>
      {deficit && (
        <span className="inline-flex items-center gap-1.5 font-medium text-red-300">
          <TriangleAlert className="h-3.5 w-3.5" />
          Deficit — short by {inr(requiredFunding - availableRupees)}. Bulk-approve blocked; approve
          rows individually as funds allow.
        </span>
      )}
    </div>
  );
}
