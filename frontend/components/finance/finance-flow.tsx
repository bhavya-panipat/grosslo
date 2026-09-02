"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, XCircle, ChevronDown, ChevronUp, Download, Upload, Copy, Loader2, TriangleAlert } from "lucide-react";
import CardShell from "@/components/card-shell";
import type {
  Submission,
  SubmissionRow,
  DecideRowResponse,
  ExportApprovedRowResponse,
  OrchestrationRoute,
} from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// A row with no orchestration data (submitted before this feature shipped)
// defaults to "needs_review" — the fail-safe direction. Defaulting to
// auto_pass_candidate instead would be a quiet safety bug: a legacy or
// malformed row silently fast-tracking into the bulk-approve path.
const routeOf = (r: SubmissionRow): OrchestrationRoute => r.orchestration?.route ?? "needs_review";

function RouteBadge({ row }: { row: SubmissionRow }) {
  const route = routeOf(row);
  const severity = row.orchestration?.severity ?? "None";

  if (route === "auto_pass_candidate" && severity === "Low") {
    // Deliberately NOT emerald, unlike the zero-flag "Clean" badge below —
    // found live during a defense pressure-test: identical styling here
    // meant a real (if low-severity) note could get scanned past and
    // bulk-approved without ever being read, defeating the point of
    // surfacing it at all. Same gold "caution" token already used for
    // "Needs review" elsewhere in this file, plus an icon, so this reads
    // as visually distinct even to someone scanning by color/shape, not
    // just to someone who stops to read the text.
    const flags = row.computed.compliance.flags;
    const ruleIds = flags.map((f) => f.rule_id).join(", ");
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-gold/30 bg-gold/[0.08] px-2 py-0.5 text-[11px] font-medium text-gold-bright">
        <TriangleAlert className="h-3 w-3 shrink-0" />
        Fast-tracked · {flags.length} low-severity note{flags.length === 1 ? "" : "s"}, {ruleIds}
      </span>
    );
  }
  if (route === "auto_pass_candidate") {
    return (
      <span className="inline-flex items-center rounded-full border border-emerald-400/30 bg-emerald-400/[0.08] px-2 py-0.5 text-[11px] font-medium text-emerald-300">
        Clean
      </span>
    );
  }
  if (route === "guardrail_not_run") {
    return (
      <span className="inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[11px] font-medium text-neutral-400">
        Guardrail not run
      </span>
    );
  }
  if (route === "escalate") {
    return (
      <span className="inline-flex items-center rounded-full border border-red-400/30 bg-red-400/[0.08] px-2 py-0.5 text-[11px] font-medium text-red-300">
        Escalated
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full border border-gold/30 bg-gold/[0.08] px-2 py-0.5 text-[11px] font-medium text-gold-bright">
      Needs review
    </span>
  );
}

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

// Approved rows only. Branches on what the row actually was: a correction
// (current_structure present) downloads an XLSX file, then offers a
// "Simulate upload" confirmation step; a new hire gets back a RazorpayX
// payout payload as JSON with a "Simulate dispatch" step. The two aren't
// symmetric underneath, on purpose: RazorpayX's Bulk Salary Revision is a
// dashboard file-upload feature, not a documented JSON API the way
// Composite Payout is, so simulating a fake API call for it would mean
// inventing a schema nothing has verified — the upload-confirmation step
// mirrors new hire's "review, then confirm" UX without pretending an API
// call happened where only a file upload actually would.
function ExportPanel({ row, onCompleted }: { row: SubmissionRow; onCompleted: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ExportApprovedRowResponse | null>(null);
  const [downloaded, setDownloaded] = useState(false);
  const [honestyLabel, setHonestyLabel] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState(false);
  const [dispatched, setDispatched] = useState(false);
  const [copied, setCopied] = useState(false);
  const isCorrection = Boolean(row.input.current_structure);

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/submissions/${row.submission_id}/rows/${row.row_index}/export`, {
        method: "POST",
      });
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("spreadsheet")) {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setHonestyLabel(res.headers.get("X-Template-Honesty-Label"));
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "grosslo_salary_revision.xlsx";
        a.click();
        URL.revokeObjectURL(url);
        setDownloaded(true);
      } else {
        const json = await res.json();
        if (!res.ok) throw new Error(json.error ?? `HTTP ${res.status}`);
        setPayload(json);
      }
    } catch (e) {
      setError((e as Error).message || "Couldn't reach the backend — confirm it's running.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!payload) return;
    navigator.clipboard.writeText(JSON.stringify(payload.payouts, null, 2)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="mt-3 border-t border-white/[0.06] pt-3">
      {!payload && !(isCorrection && downloaded) && (
        <button
          onClick={handleExport}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold/[0.06] px-3.5 py-1.5 text-xs font-medium text-gold-bright transition-colors hover:bg-gold/[0.12] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          {isCorrection ? "Export Salary Revision XLSX" : "Export RazorpayX payout"}
        </button>
      )}
      {error && <p className="mt-1.5 text-xs text-red-400/80">{error}</p>}
      {isCorrection && downloaded && (
        <div className="space-y-2">
          <p className="text-xs text-neutral-500">
            <span className="text-neutral-300">grosslo_salary_revision.xlsx</span> downloaded — the
            real file RazorpayX Payroll's Bulk Salary Revision accepts. That feature is a dashboard
            file upload, not an API grosslo can call, so there's nothing further to send — "simulate"
            here means confirming the decision, the same as new hire's simulated dispatch does.
          </p>
          {honestyLabel && <p className="text-[11px] text-neutral-600">{honestyLabel}</p>}
          <button
            onClick={() => {
              setUploaded(true);
              onCompleted();
            }}
            disabled={uploaded}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-1.5 text-xs font-medium text-neutral-200 transition-colors hover:border-white/20 hover:bg-white/[0.04] disabled:cursor-not-allowed"
          >
            {uploaded ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Uploaded (simulated)
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" /> Simulate upload to RazorpayX Payroll
              </>
            )}
          </button>
        </div>
      )}
      {payload && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-neutral-500">
              Composite Payout payload{payload.payouts.length > 1 ? `s (${payload.payouts.length})` : ""}
            </p>
            <button onClick={handleCopy} className="flex items-center gap-1 text-xs text-neutral-500 hover:text-white">
              {copied ? <CheckCircle2 className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy JSON"}
            </button>
          </div>
          <pre className="max-h-56 overflow-auto rounded-xl border border-white/[0.06] bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-neutral-400">
            {JSON.stringify(payload.payouts, null, 2)}
          </pre>
          <p className="text-[11px] text-neutral-600">
            Simulated only — no live call to RazorpayX. Capital required:{" "}
            ₹{Math.round(payload.treasury_forecast.total_capital_outlay).toLocaleString("en-IN")}
          </p>
          <button
            onClick={() => {
              setDispatched(true);
              onCompleted();
            }}
            disabled={dispatched}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-1.5 text-xs font-medium text-neutral-200 transition-colors hover:border-white/20 hover:bg-white/[0.04] disabled:cursor-not-allowed"
          >
            {dispatched ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Dispatched (simulated)
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" /> Simulate dispatch
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

const SEVERITY_RANK: Record<string, number> = { Low: 1, Medium: 2, High: 3 };

// One-line summary of the actual fix — visible without clicking Inspect.
// Reuses row.diff, already computed server-side by diff_view.py's
// build_diff() and already fetched for every row (finance-flow's own
// refresh() calls GET /api/submissions/<id> per submission specifically
// to get this) — no new data, just surfaced one level higher than
// before. Deliberately returns null (renders nothing) rather than a
// generic "review this" line when there's no real prior-offer diff to
// point to (a plain new-hire submission) — a vague placeholder would be
// worse than showing nothing.
function pickSuggestedFix(row: SubmissionRow): string | null {
  const diff = row.diff;
  if (!diff || !diff.has_prior_offer) return null;

  const severityByRule = new Map(row.computed.compliance.flags.map((f) => [f.rule_id, f.severity]));

  // Among the changed fields, surface the one tied to the highest-
  // severity compliance rule — the change actually driving the
  // escalation, not just whichever field happens to be listed first.
  // Field changes with no rule attribution ("tax optimization") rank
  // lowest and only surface if nothing rule-tied exists.
  let best: { text: string; rank: number } | null = null;
  for (const c of diff.field_changes) {
    const ruleMatch = c.reason.match(/^(R\d)\s/);
    const severity = ruleMatch ? severityByRule.get(ruleMatch[1]) : undefined;
    const rank = severity ? SEVERITY_RANK[severity] : 0;
    if (!best || rank > best.rank) {
      const fieldLabel = c.field.replace(/_/g, " ");
      const beforeStr = typeof c.before === "boolean" ? String(c.before) : inr(c.before);
      const afterStr = typeof c.after === "boolean" ? String(c.after) : inr(c.after);
      best = { text: `${fieldLabel}: ${beforeStr} → ${afterStr} (${c.reason})`, rank };
    }
  }
  if (best) return best.text;

  if (diff.regime_change) {
    return `Regime: ${diff.regime_change.before} → ${diff.regime_change.after} (${diff.regime_change.reason})`;
  }
  return null;
}

function RowCard({
  row,
  onDecided,
  onExportCompleted,
  selected,
  onToggleSelect,
}: {
  row: SubmissionRow;
  onDecided: () => void;
  onExportCompleted?: () => void;
  selected?: boolean;
  onToggleSelect?: () => void;
}) {
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
  const suggestedFix = pickSuggestedFix(row);

  return (
    <CardShell className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {onToggleSelect && (
            <input
              type="checkbox"
              checked={Boolean(selected)}
              onChange={onToggleSelect}
              aria-label={`Select ${row.employee_name || `row ${row.row_index + 1}`}`}
              className="h-4 w-4 shrink-0 rounded border-white/20 bg-black/40 accent-gold-bright"
            />
          )}
          <div>
            <p className="flex items-center gap-2 font-medium text-neutral-200">
              {row.employee_name || `Row ${row.row_index + 1}`}
              <RouteBadge row={row} />
            </p>
            <p className="text-xs text-neutral-500">
              {inr(row.ctc)} · {recommendedRegime} regime · tax {inr(recommended.tax_breakdown.total_tax)}
              {flags.length > 0 && (
                <span className="ml-2 text-gold-bright">
                  {flags.length} compliance flag{flags.length === 1 ? "" : "s"}
                </span>
              )}
            </p>
            {suggestedFix && (
              <p className="mt-1 text-xs text-neutral-400">
                <span className="text-neutral-500">Suggested fix:</span> {suggestedFix}
              </p>
            )}
          </div>
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
            {row.orchestration && (
              <div className="flex flex-col gap-1.5">
                <p className="text-xs uppercase tracking-wide text-neutral-500">Routing decision</p>
                <p className="text-sm text-neutral-300">
                  Severity: <span className="font-mono text-neutral-200">{row.orchestration.severity}</span>
                </p>
                {row.orchestration.reasons.length > 0 ? (
                  row.orchestration.reasons.map((r, i) => (
                    <p key={i} className="text-sm text-neutral-400">{r}</p>
                  ))
                ) : (
                  <p className="text-sm text-neutral-500">Nothing fired — zero compliance flags.</p>
                )}
                {!row.orchestration.checked.guardrail_evaluated && (
                  <p className="text-sm text-neutral-500">
                    Guardrail not evaluated — no compensation band was supplied for this row.
                  </p>
                )}
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
            <>
              <span className="text-emerald-300">Approved — Payout SIMULATED, no live dispatch.</span>
              <ExportPanel row={row} onCompleted={() => onExportCompleted?.()} />
            </>
          ) : (
            <span className="text-red-300">Rejected: {row.reason}</span>
          )}
        </div>
      )}
      {message && <p className="mt-2 text-xs text-neutral-500">{message}</p>}
    </CardShell>
  );
}

// Approve/reject selected pending rows in one click — still one decide
// call per row under the hood (there's no bulk-decide endpoint, and there
// doesn't need to be one: idempotent per-row calls fired in parallel are
// exactly as safe as clicking each button individually, just faster to
// trigger). This batches the ACTION of confirming decisions someone has
// already reviewed — it never decides anything itself.
function BulkActionBar({
  count,
  busy,
  onApproveAll,
  onRejectAll,
}: {
  count: number;
  busy: boolean;
  onApproveAll: () => void;
  onRejectAll: (reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  return (
    <div className="sticky top-20 z-10 flex flex-col gap-2 rounded-xl border border-gold/20 bg-surface-raised/95 p-3 shadow-inner-edge backdrop-blur-md">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-neutral-300">{count} row{count === 1 ? "" : "s"} selected</p>
        {!rejecting ? (
          <div className="flex gap-2">
            <button
              onClick={onApproveAll}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-sm font-medium text-black transition-transform hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              Approve all {count}
            </button>
            <button
              onClick={() => setRejecting(true)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-1.5 text-sm text-neutral-300 hover:border-red-400/40 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <XCircle className="h-4 w-4" /> Reject all {count}
            </button>
          </div>
        ) : (
          <div className="flex flex-1 items-center gap-2">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason applied to all selected rows (required)"
              className="flex-1 rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-red-400/50 focus:outline-none"
              autoFocus
            />
            <button
              onClick={() => onRejectAll(reason.trim())}
              disabled={!reason.trim() || busy}
              className="shrink-0 rounded-full bg-red-400/90 px-4 py-1.5 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-40"
            >
              Confirm
            </button>
            <button
              onClick={() => setRejecting(false)}
              className="shrink-0 rounded-full border border-white/10 px-4 py-1.5 text-sm text-neutral-400 hover:text-white"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
      {rejecting && (
        <p className="text-[11px] text-neutral-500">
          One reason, applied to every selected row — if these rows need different explanations,
          reject them individually instead.
        </p>
      )}
    </div>
  );
}

export default function FinanceFlow() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [bulkDeciding, setBulkDeciding] = useState(false);
  // Rows whose export has been simulated-dispatched/uploaded — hidden from
  // the approved list below so it doesn't fill up with fully-actioned rows.
  // Client-side only, on purpose: there's nowhere in the backend that
  // tracks "dispatched," the same way there's nowhere that tracks a real
  // payout — this mirrors that boundary instead of inventing new backend
  // state just to persist a UI-only completion flag. A page refresh brings
  // a row back, consistent with every other "simulated" state in this app.
  const [completedKeys, setCompletedKeys] = useState<Set<string>>(new Set());

  const refresh = useCallback(() => {
    // Fetches every submission, not just pending ones — approved rows need
    // to stay visible here so their export action has somewhere to live.
    fetch("/api/submissions")
      .then((r) => r.json())
      .then(async (d: { submissions: Submission[] }) => {
        // fetch full detail (with diff) for each submission
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
  const approvedRows = submissions
    .flatMap((s) => s.rows.filter((r) => r.status === "approved"))
    .filter((r) => !completedKeys.has(`${r.submission_id}-${r.row_index}`));

  // Four buckets. Bulk-approve is scoped to cleanRows ONLY — the other three
  // never render a checkbox at all (see below), so there is structurally
  // nothing to select-around, not just a disabled control with a warning.
  const cleanRows = pendingRows.filter((r) => routeOf(r) === "auto_pass_candidate");
  const reviewRows = pendingRows.filter((r) => routeOf(r) === "needs_review");
  const noGuardrailRows = pendingRows.filter((r) => routeOf(r) === "guardrail_not_run");
  const escalatedRows = pendingRows.filter((r) => routeOf(r) === "escalate");

  const keyOf = (r: SubmissionRow) => `${r.submission_id}-${r.row_index}`;
  const toggleSelected = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const allCleanSelected = cleanRows.length > 0 && cleanRows.every((r) => selectedKeys.has(keyOf(r)));
  const toggleSelectAllClean = () => {
    setSelectedKeys(allCleanSelected ? new Set() : new Set(cleanRows.map(keyOf)));
  };

  // "X of Y rows bulk-approved. Z require individual review (breakdown)." —
  // set right after a bulk action completes, from counts captured before
  // the action (refresh() below is async, so these are the pre-action
  // counts, which is what "how many still need attention" should report).
  const [bulkSummary, setBulkSummary] = useState<string | null>(null);

  const bulkDecide = async (decision: "approve" | "reject", reason?: string) => {
    // Filtered through cleanRows explicitly, not just pendingRows — this is
    // the structural guarantee that a bulk action can never touch a
    // needs_review/guardrail_not_run/escalate row, enforced at the data
    // layer, not only by the absence of a checkbox in those sections.
    const targets = cleanRows.filter((r) => selectedKeys.has(keyOf(r)));
    if (targets.length === 0) return;
    setBulkDeciding(true);
    const totalPending = pendingRows.length;
    const remaining = reviewRows.length + noGuardrailRows.length + escalatedRows.length;
    try {
      await Promise.all(
        targets.map((r) =>
          fetch(`/api/submissions/${r.submission_id}/rows/${r.row_index}/decide`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision, reason: decision === "reject" ? reason : undefined }),
          }),
        ),
      );
      const verb = decision === "approve" ? "bulk-approved" : "bulk-rejected";
      setBulkSummary(
        `${targets.length} of ${totalPending} rows ${verb}.` +
          (remaining > 0
            ? ` ${remaining} require individual review (${escalatedRows.length} high-severity/failed-guardrail, ` +
              `${noGuardrailRows.length} guardrail not run, ${reviewRows.length} needs review).`
            : ""),
      );
    } finally {
      setSelectedKeys(new Set());
      setBulkDeciding(false);
      refresh();
    }
  };

  return (
    <section className="mx-auto max-w-4xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> FINANCE"}</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
          Review what HR submitted.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-neutral-500">
          Every approval writes a simulated decision only — nothing here ever calls RazorpayX or
          dispatches a payout. Approved rows can generate a real export payload below, on demand.
        </p>
      </div>

      {loading && <p className="text-sm text-neutral-600">Loading queue…</p>}
      {!loading && pendingRows.length === 0 && (
        <p className="text-sm text-neutral-600">Nothing pending review right now.</p>
      )}

      {bulkSummary && (
        <p className="mb-4 rounded-lg border border-gold/20 bg-gold/[0.04] px-3 py-2 text-sm text-neutral-300">
          {bulkSummary}
        </p>
      )}

      {/* Ordered by urgency, not by how the routing logic happens to
          compute them — most-attention-needed first. A reviewer opening
          this page should see what's escalated before anything else,
          not scroll past three other sections to find it. Clean is last
          on purpose too: it's the one section that's genuinely fine to
          address in a single bulk click, so it doesn't compete for the
          same visual priority as rows that need a human to actually
          read something. */}
      {escalatedRows.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 font-display text-lg font-semibold text-red-300">Escalated</h3>
          <div className="flex flex-col gap-3">
            {escalatedRows.map((row) => (
              <RowCard key={`${row.submission_id}-${row.row_index}`} row={row} onDecided={refresh} />
            ))}
          </div>
        </div>
      )}

      {reviewRows.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 font-display text-lg font-semibold text-gold-bright">Needs review</h3>
          {/* No checkbox rendered on any RowCard here — onToggleSelect is omitted, so there is
              nothing to select. Individual approve/reject only. */}
          <div className="flex flex-col gap-3">
            {reviewRows.map((row) => (
              <RowCard key={`${row.submission_id}-${row.row_index}`} row={row} onDecided={refresh} />
            ))}
          </div>
        </div>
      )}

      {noGuardrailRows.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 font-display text-lg font-semibold text-neutral-300">Guardrail not run</h3>
          <p className="mb-3 text-xs text-neutral-500">
            No approved compensation band was supplied for these rows — review individually.
          </p>
          <div className="flex flex-col gap-3">
            {noGuardrailRows.map((row) => (
              <RowCard key={`${row.submission_id}-${row.row_index}`} row={row} onDecided={refresh} />
            ))}
          </div>
        </div>
      )}

      {cleanRows.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 font-display text-lg font-semibold text-emerald-300">
            Clean — ready to fast-track
          </h3>
          {cleanRows.length > 1 && (
            <label className="mb-3 flex w-fit items-center gap-2 text-xs text-neutral-500 hover:text-neutral-300">
              <input
                type="checkbox"
                checked={allCleanSelected}
                onChange={toggleSelectAllClean}
                className="h-3.5 w-3.5 rounded border-white/20 bg-black/40 accent-gold-bright"
              />
              Select all {cleanRows.length} clean
            </label>
          )}
          {selectedKeys.size > 0 && (
            <div className="mb-3">
              <BulkActionBar
                count={selectedKeys.size}
                busy={bulkDeciding}
                onApproveAll={() => bulkDecide("approve")}
                onRejectAll={(reason) => bulkDecide("reject", reason)}
              />
            </div>
          )}
          <div className="flex flex-col gap-3">
            {cleanRows.map((row) => (
              <RowCard
                key={`${row.submission_id}-${row.row_index}`}
                row={row}
                onDecided={refresh}
                selected={selectedKeys.has(keyOf(row))}
                onToggleSelect={() => toggleSelected(keyOf(row))}
              />
            ))}
          </div>
        </div>
      )}

      {approvedRows.length > 0 && (
        <div className="mt-10">
          <h3 className="font-display text-lg font-semibold text-white">Approved — ready to export</h3>
          <div className="mt-4 flex flex-col gap-3">
            {approvedRows.map((row) => (
              <RowCard
                key={`${row.submission_id}-${row.row_index}`}
                row={row}
                onDecided={refresh}
                onExportCompleted={() =>
                  setCompletedKeys((prev) => new Set(prev).add(`${row.submission_id}-${row.row_index}`))
                }
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
