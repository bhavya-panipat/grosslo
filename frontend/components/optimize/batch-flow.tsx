"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import CsvUploadCard from "@/components/optimize/csv-upload-card";
import { Send } from "lucide-react";
import { AuditBatchTable, type CorrectionStatus } from "@/components/optimize/batch-results-table";
import AuditSummaryCard from "@/components/optimize/audit-summary-card";
import PenaltyScenarioTable from "@/components/optimize/penalty-scenario-table";
import type { BatchAuditResponse, CreateSubmissionResponse } from "@/lib/api-types";

function toNum(v: string | undefined): number | undefined {
  if (v === undefined || v.trim() === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function toBool(v: string | undefined): boolean {
  if (!v) return false;
  return ["true", "1", "yes"].includes(v.trim().toLowerCase());
}

export default function BatchFlow() {
  const [rawRows, setRawRows] = useState<Record<string, string>[] | null>(null);
  const [auditResult, setAuditResult] = useState<BatchAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correctionStatus, setCorrectionStatus] = useState<Record<number, CorrectionStatus>>({});

  const handleRowsParsed = async (rows: Record<string, string>[]) => {
    setRawRows(rows);
    setCorrectionStatus({});
    setAuditResult(null);
    setError(null);
    setLoading(true);
    try {
      const payload = {
        rows: rows.map((r) => ({
          name: r.name,
          ctc: toNum(r.ctc),
          basic: toNum(r.basic),
          hra: toNum(r.hra) ?? 0,
          lta: toNum(r.lta) ?? 0,
          special_allowance: toNum(r.special_allowance) ?? 0,
          employer_pf: toNum(r.employer_pf) ?? 0,
          employer_nps: toNum(r.employer_nps) ?? 0,
          nps_opted: toBool(r.nps_opted),
          rent_paid: toNum(r.rent_paid) ?? 0,
          city: r.city || "metro",
          band_min: toNum(r.band_min),
          band_max: toNum(r.band_max),
        })),
      };
      const res = await fetch("/api/batch-audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setAuditResult(await res.json());
    } catch {
      setError("Couldn't reach the backend — confirm the Flask server is running.");
    } finally {
      setLoading(false);
    }
  };

  // Shared by both the single-row and bulk submit paths below, so a batch
  // submission isn't a second, divergent way of building the same payload.
  const buildCorrectionRow = (raw: Record<string, string>) => ({
    employee_name: raw.name,
    ctc: toNum(raw.ctc),
    rent_paid: toNum(raw.rent_paid) ?? 0,
    city: raw.city || "metro",
    nps_opted: toBool(raw.nps_opted),
    current_structure: {
      basic: toNum(raw.basic) ?? 0,
      hra: toNum(raw.hra) ?? 0,
      lta: toNum(raw.lta) ?? 0,
      special_allowance: toNum(raw.special_allowance) ?? 0,
      employer_pf: toNum(raw.employer_pf) ?? 0,
      employer_nps: toNum(raw.employer_nps) ?? 0,
      nps_opted: toBool(raw.nps_opted),
    },
  });

  // Closes the audit loop: a flagged row (excess EPFO contribution,
  // unclaimed regime-switch savings) is submitted for Finance review the
  // same way HR's own submissions are — same endpoint, same diff-with-
  // attribution, same approve/reject. current_structure is the row's AS-IS
  // structure from the uploaded CSV, not the corrected one: the server
  // recomputes the correction itself (same principle as everywhere else in
  // this app — never trust a client-supplied tax figure), and Finance's
  // diff view shows exactly what changed and why.
  const handleSubmitCorrection = async (rowIndex: number) => {
    const raw = (rawRows ?? [])[rowIndex];
    if (!raw) return;
    setCorrectionStatus((prev) => ({ ...prev, [rowIndex]: "submitting" }));
    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: "single", row: buildCorrectionRow(raw) }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCorrectionStatus((prev) => ({ ...prev, [rowIndex]: "submitted" }));
    } catch {
      setCorrectionStatus((prev) => ({ ...prev, [rowIndex]: "error" }));
    }
  };

  // One click, one batch submission — reuses the exact same
  // buildCorrectionRow() + /api/submissions endpoint as a single click
  // does, just with N rows in one request instead of N separate ones.
  // This only batches the ACTION of sending already-flagged rows to
  // Finance; every row still gets its own individual approve/reject
  // decision once it lands in the queue — nothing here skips review.
  const flaggedIndices = (auditResult?.rows ?? [])
    .filter((r) => !r.error && ((r.unclaimed_savings ?? 0) > 0 || (r.excess_contribution ?? 0) > 0))
    .map((r) => r.row_index)
    .filter((i) => (correctionStatus[i] ?? "idle") === "idle" || correctionStatus[i] === "error");

  const [bulkSubmitting, setBulkSubmitting] = useState(false);

  const handleSubmitAllFlagged = async () => {
    const indices = flaggedIndices;
    if (indices.length === 0 || !rawRows) return;
    setBulkSubmitting(true);
    setCorrectionStatus((prev) => {
      const next = { ...prev };
      indices.forEach((i) => { next[i] = "submitting"; });
      return next;
    });
    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "batch",
          rows: indices.map((i) => buildCorrectionRow(rawRows[i])),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result: CreateSubmissionResponse = await res.json();
      // row_errors/duplicates from the response are indexed within THIS
      // batch request (0..N-1), not by the original audit row_index — map
      // back through `indices` to know which real row each one was.
      const erroredBatchPositions = new Set(result.row_errors.map((e) => e.row_index));
      setCorrectionStatus((prev) => {
        const next = { ...prev };
        indices.forEach((originalIndex, batchPosition) => {
          next[originalIndex] = erroredBatchPositions.has(batchPosition) ? "error" : "submitted";
        });
        return next;
      });
    } catch {
      setCorrectionStatus((prev) => {
        const next = { ...prev };
        indices.forEach((i) => { next[i] = "error"; });
        return next;
      });
    } finally {
      setBulkSubmitting(false);
    }
  };

  return (
    <section className="mx-auto max-w-6xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> AUDIT"}</p>
          <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
            Audit existing payroll, in bulk.
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-neutral-500">
            Upload the structures already in place today. Flagged rows (excess EPFO contribution,
            unclaimed regime-switch savings) can be sent straight to Finance for review — the same
            path new hires go through on the <a href="/hr" className="text-gold-bright hover:underline">HR</a> page.
          </p>
        </div>
        <a
          href="/hr"
          className="mt-1 hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-white/10 px-4 py-2 text-sm text-neutral-300 transition-colors hover:border-white/20 hover:bg-white/[0.04] hover:text-white sm:inline-flex"
        >
          Structure a new hire →
        </a>
      </div>

      <CsvUploadCard mode="audit" onRowsParsed={handleRowsParsed} />

      {loading && (
        <div className="mt-6 flex items-center gap-2 text-sm text-neutral-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Processing batch…
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-xl border border-red-400/20 bg-red-400/[0.05] p-4 text-sm text-red-300">
          {error}
        </div>
      )}

      <AnimatePresence>
        {auditResult && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-col gap-6"
          >
            <AuditSummaryCard
              totalRows={auditResult.summary.total_rows}
              cleanCount={auditResult.summary.clean_count}
              flaggedCount={auditResult.summary.flagged_count}
              epfoCapExceededCount={auditResult.summary.epfo_cap_exceeded_count}
              regimeMismatchCount={auditResult.summary.regime_mismatch_count}
              totalExcessContribution={auditResult.summary.total_excess_contribution}
              totalUnclaimedSavings={auditResult.summary.total_unclaimed_savings}
            />
            {flaggedIndices.length > 0 && (
              <div className="flex items-center justify-between rounded-xl border border-gold/20 bg-gold/[0.04] px-5 py-3">
                <p className="text-sm text-neutral-300">
                  {flaggedIndices.length} flagged row{flaggedIndices.length === 1 ? "" : "s"} not yet sent to Finance.
                </p>
                <button
                  onClick={handleSubmitAllFlagged}
                  disabled={bulkSubmitting}
                  className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {bulkSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Submit all {flaggedIndices.length} for review
                </button>
              </div>
            )}
            <AuditBatchTable
              rows={auditResult.rows}
              correctionStatus={correctionStatus}
              onSubmitCorrection={handleSubmitCorrection}
            />
            <PenaltyScenarioTable scenario={auditResult.penalty_scenario} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
