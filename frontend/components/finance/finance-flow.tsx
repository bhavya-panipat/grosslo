"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { Submission, SubmissionRow, DecideRowResponse } from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

function DiffPanel({ row }: { row: SubmissionRow }) {
  const diff = row.diff;
  if (!diff) return null;
  if (!diff.has_prior_offer) {
    return <p className="text-sm text-neutral-500">{diff.note}</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {diff.regime_change && (
        <div className="rounded-lg border border-white/[0.06] bg-black/30 p-2.5 text-sm">
          <span className="text-neutral-400">Regime: </span>
          <span className="font-mono capitalize text-neutral-300">{diff.regime_change.before}</span>
          <span className="text-neutral-600"> → </span>
          <span className="font-mono capitalize text-gold-bright">{diff.regime_change.after}</span>
          <span className="ml-2 text-xs text-neutral-500">({diff.regime_change.reason})</span>
        </div>
      )}
      {diff.field_changes.length === 0 && !diff.regime_change && (
        <p className="text-sm text-neutral-500">No meaningful change from the as-offered structure.</p>
      )}
      {diff.field_changes.map((c) => (
        <div key={c.field} className="rounded-lg border border-white/[0.06] bg-black/30 p-2.5 text-sm">
          <span className="capitalize text-neutral-400">{c.field.replace("_", " ")}: </span>
          <span className="font-mono text-neutral-300">
            {typeof c.before === "boolean" ? String(c.before) : inr(c.before)}
          </span>
          <span className="text-neutral-600"> → </span>
          <span className="font-mono text-gold-bright">
            {typeof c.after === "boolean" ? String(c.after) : inr(c.after)}
          </span>
          <span className="ml-2 text-xs text-neutral-500">({c.reason})</span>
        </div>
      ))}
    </div>
  );
}

function RowCard({ row, onDecided }: { row: SubmissionRow; onDecided: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const decide = (decision: "approve" | "reject") => {
    if (decision === "reject" && !reason.trim()) return;
    setDeciding(true);
    fetch(`/api/submissions/${row.submission_id}/rows/${row.row_index}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason: decision === "reject" ? reason.trim() : undefined }),
    })
      .then((r) => r.json())
      .then((json: DecideRowResponse) => {
        setMessage(json.message);
        setDeciding(false);
        setRejecting(false);
        onDecided();
      })
      .catch(() => setDeciding(false));
  };

  const recommendedRegime = row.computed.recommended_regime;
  const recommended = row.computed[`${recommendedRegime}_regime_best`];
  const flags = row.computed.compliance.flags;

  return (
    <CardShell className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-medium text-neutral-200">{row.employee_name || `Row ${row.row_index + 1}`}</p>
          <p className="text-xs text-neutral-500">
            {inr(row.ctc)} · {recommendedRegime} regime · tax {inr(recommended.tax_breakdown.total_tax)}
            {flags.length > 0 && (
              <span className="ml-2 text-gold-bright">
                {flags.length} compliance flag{flags.length === 1 ? "" : "s"}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-xs text-neutral-400 hover:border-white/20 hover:text-white"
        >
          {expanded ? "Hide detail" : "Inspect"}
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 flex flex-col gap-4 overflow-hidden border-t border-white/[0.06] pt-4"
          >
            {flags.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <p className="text-xs uppercase tracking-wide text-neutral-500">Compliance flags</p>
                {flags.map((f) => (
                  <p key={f.rule_id} className="text-sm text-neutral-300">
                    <span className="font-mono text-gold-bright">{f.rule_id}</span> — {f.rationale}
                  </p>
                ))}
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <p className="text-xs uppercase tracking-wide text-neutral-500">Before / after</p>
              <DiffPanel row={row} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {row.status === "pending" ? (
        <div className="mt-4 flex flex-col gap-2 border-t border-white/[0.06] pt-4">
          {!rejecting ? (
            <div className="flex gap-2">
              <button
                onClick={() => decide("approve")}
                disabled={deciding}
                className="inline-flex items-center gap-1.5 rounded-full bg-white px-4 py-2 text-sm font-medium text-black transition-transform hover:scale-[1.02] disabled:opacity-40"
              >
                <CheckCircle2 className="h-4 w-4" /> Approve
              </button>
              <button
                onClick={() => setRejecting(true)}
                disabled={deciding}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm text-neutral-300 hover:border-red-400/40 hover:text-red-300 disabled:opacity-40"
              >
                <XCircle className="h-4 w-4" /> Reject
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for rejection (required)"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-red-400/50 focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => decide("reject")}
                  disabled={!reason.trim() || deciding}
                  className="rounded-full bg-red-400/90 px-4 py-1.5 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Confirm rejection
                </button>
                <button
                  onClick={() => setRejecting(false)}
                  className="rounded-full border border-white/10 px-4 py-1.5 text-sm text-neutral-400 hover:text-white"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 border-t border-white/[0.06] pt-3 text-sm text-neutral-400">
          {row.status === "approved" ? (
            <span className="text-emerald-300">Approved — Payout SIMULATED, no live dispatch.</span>
          ) : (
            <span className="text-red-300">Rejected: {row.reason}</span>
          )}
        </div>
      )}
      {message && <p className="mt-2 text-xs text-neutral-500">{message}</p>}
    </CardShell>
  );
}

export default function FinanceFlow() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetch("/api/submissions?status=pending")
      .then((r) => r.json())
      .then(async (d: { submissions: Submission[] }) => {
        // fetch full detail (with diff) for each pending submission
        const detailed = await Promise.all(
          d.submissions.map((s) => fetch(`/api/submissions/${s.id}`).then((r) => r.json())),
        );
        setSubmissions(detailed);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const pendingRows = submissions.flatMap((s) => s.rows.filter((r) => r.status === "pending"));

  return (
    <section className="mx-auto max-w-4xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> FINANCE"}</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
          Review what HR submitted.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-neutral-500">
          Every approval writes a simulated decision only — nothing here ever calls RazorpayX or
          dispatches a payout.
        </p>
      </div>

      {loading && <p className="text-sm text-neutral-600">Loading queue…</p>}
      {!loading && pendingRows.length === 0 && (
        <p className="text-sm text-neutral-600">Nothing pending review right now.</p>
      )}

      <div className="flex flex-col gap-3">
        {pendingRows.map((row) => (
          <RowCard key={`${row.submission_id}-${row.row_index}`} row={row} onDecided={refresh} />
        ))}
      </div>
    </section>
  );
}
