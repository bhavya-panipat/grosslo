"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import CsvUploadCard from "@/components/optimize/csv-upload-card";
import { NewHireBatchTable, AuditBatchTable } from "@/components/optimize/batch-results-table";
import AuditSummaryCard from "@/components/optimize/audit-summary-card";
import PenaltyScenarioTable from "@/components/optimize/penalty-scenario-table";
import RazorpayXExportModal, { type BatchExportRow } from "@/components/optimize/razorpayx-export-modal";
import type { OptimizeBatchResponse, BatchAuditResponse } from "@/lib/api-types";

type Mode = "new-hire" | "audit";

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
  const [mode, setMode] = useState<Mode>("new-hire");
  const [rawRows, setRawRows] = useState<Record<string, string>[] | null>(null);
  const [newHireResult, setNewHireResult] = useState<OptimizeBatchResponse | null>(null);
  const [auditResult, setAuditResult] = useState<BatchAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);

  const switchMode = (next: Mode) => {
    setMode(next);
    setRawRows(null);
    setNewHireResult(null);
    setAuditResult(null);
    setError(null);
  };

  const handleRowsParsed = async (rows: Record<string, string>[]) => {
    setRawRows(rows);
    setNewHireResult(null);
    setAuditResult(null);
    setError(null);
    setLoading(true);
    try {
      if (mode === "new-hire") {
        const payload = {
          rows: rows.map((r) => ({
            ctc: toNum(r.ctc),
            rent_paid: toNum(r.rent_paid) ?? 0,
            city: r.city || "metro",
            nps_opted: toBool(r.nps_opted),
            band_min: toNum(r.band_min),
            band_max: toNum(r.band_max),
          })),
        };
        const res = await fetch("/api/optimize-batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setNewHireResult(await res.json());
      } else {
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
      }
    } catch {
      setError("Couldn't reach the backend — confirm the Flask server is running.");
    } finally {
      setLoading(false);
    }
  };

  const exportableRows: BatchExportRow[] = (rawRows ?? [])
    .filter((r) => r.bank_account_number && r.ifsc && r.name)
    .map((r) => ({
      ctc: toNum(r.ctc) ?? 0,
      rentPaid: toNum(r.rent_paid) ?? 0,
      city: r.city || "metro",
      npsOpted: toBool(r.nps_opted),
      bandMin: toNum(r.band_min) ?? 0,
      bandMax: toNum(r.band_max) ?? 0,
      employee: { name: r.name, bank_account_number: r.bank_account_number, ifsc: r.ifsc, email: r.email ?? "" },
    }));

  return (
    <section className="mx-auto max-w-6xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> BATCH"}</p>
          <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
            Process many at once.
          </h1>
        </div>
        <a
          href="/optimize"
          className="mt-1 hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-white/10 px-4 py-2 text-sm text-neutral-300 transition-colors hover:border-white/20 hover:bg-white/[0.04] hover:text-white sm:inline-flex"
        >
          ← Single candidate
        </a>
      </div>

      <div className="mb-6 flex gap-1 rounded-full border border-white/10 bg-black/40 p-1 w-fit">
        {(["new-hire", "audit"] as const).map((m) => (
          <button
            key={m}
            onClick={() => switchMode(m)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              mode === m ? "bg-white text-black" : "text-neutral-400 hover:text-white"
            }`}
          >
            {m === "new-hire" ? "New Hire Batch" : "Compliance & Savings Audit"}
          </button>
        ))}
      </div>

      <CsvUploadCard key={mode} mode={mode} onRowsParsed={handleRowsParsed} />

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
        {mode === "new-hire" && newHireResult && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-col gap-4"
          >
            <NewHireBatchTable rows={newHireResult.rows} />
            <div className="flex justify-end">
              <button
                onClick={() => setExportOpen(true)}
                disabled={exportableRows.length === 0}
                className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
              >
                Export {exportableRows.length} to RazorpayX
              </button>
            </div>
          </motion.div>
        )}

        {mode === "audit" && auditResult && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-col gap-6"
          >
            <AuditSummaryCard
              totalExcessContribution={auditResult.summary.total_excess_contribution}
              totalUnclaimedSavings={auditResult.summary.total_unclaimed_savings}
            />
            <AuditBatchTable rows={auditResult.rows} />
            <PenaltyScenarioTable scenario={auditResult.penalty_scenario} />
          </motion.div>
        )}
      </AnimatePresence>

      {exportOpen && exportableRows.length > 0 && (
        <RazorpayXExportModal batchRows={exportableRows} onClose={() => setExportOpen(false)} />
      )}
    </section>
  );
}
