"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Copy, Loader2, X } from "lucide-react";
import type { CompositeBankAccountPayout, ExportRazorpayXResponse, TreasuryForecast } from "@/lib/api-types";
import type { FormState } from "@/components/optimize/manual-entry-card";

export type EmployeeForm = { name: string; bank_account_number: string; ifsc: string; email: string };

const EMPTY_EMPLOYEE: EmployeeForm = { name: "", bank_account_number: "", ifsc: "", email: "" };

// One export call's worth of inputs for a single row — batch mode makes one
// /api/export-razorpayx call per row (each row can have its own CTC/rent/
// city/NPS/band, since these are different new hires, not N employees on
// one shared structure) and the modal aggregates the results.
export type BatchExportRow = {
  ctc: number;
  rentPaid: number;
  city: string;
  npsOpted: boolean;
  bandMin: number;
  bandMax: number;
  employee: EmployeeForm;
};

type Props = {
  onClose: () => void;
} & (
  | { form: FormState; batchRows?: undefined }
  | { form?: undefined; batchRows: BatchExportRow[] }
);

function sumForecast(forecasts: TreasuryForecast[]): TreasuryForecast {
  return forecasts.reduce(
    (acc, f) => ({
      net_take_home_annual: acc.net_take_home_annual + f.net_take_home_annual,
      tds_escrow_annual: acc.tds_escrow_annual + f.tds_escrow_annual,
      epfo_challan_annual: acc.epfo_challan_annual + f.epfo_challan_annual,
      total_capital_outlay: acc.total_capital_outlay + f.total_capital_outlay,
      funding_deadline_hours_before_payroll: f.funding_deadline_hours_before_payroll,
    }),
    { net_take_home_annual: 0, tds_escrow_annual: 0, epfo_challan_annual: 0, total_capital_outlay: 0, funding_deadline_hours_before_payroll: 48 },
  );
}

export default function RazorpayXExportModal({ form, batchRows, onClose }: Props) {
  const isBatch = batchRows !== undefined;

  const [employee, setEmployee] = useState<EmployeeForm>(EMPTY_EMPLOYEE);
  const [result, setResult] = useState<{ payouts: CompositeBankAccountPayout[]; treasury_forecast: TreasuryForecast; idempotencyCount: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [dispatched, setDispatched] = useState(false);

  const bandMissing =
    !isBatch &&
    (form.bandMin === "" || form.bandMax === "" || Number(form.bandMin) >= Number(form.bandMax));
  const canGenerate = isBatch
    ? batchRows.length > 0
    : Boolean(employee.name && employee.bank_account_number && employee.ifsc && !bandMissing);

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setLoading(true);
    setError(null);
    try {
      if (isBatch) {
        const responses = await Promise.all(
          batchRows.map(async (row) => {
            const res = await fetch("/api/export-razorpayx", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                ctc: row.ctc,
                rent_paid: row.rentPaid || 0,
                city: row.city,
                nps_opted: row.npsOpted,
                band_min: row.bandMin,
                band_max: row.bandMax,
                employees: [row.employee],
              }),
            });
            const json: ExportRazorpayXResponse = await res.json();
            if (!res.ok) throw new Error((json as unknown as { error?: string }).error ?? `HTTP ${res.status}`);
            return json;
          }),
        );
        setResult({
          payouts: responses.flatMap((r) => r.payouts ?? []),
          treasury_forecast: sumForecast(responses.map((r) => r.treasury_forecast)),
          idempotencyCount: responses.length,
        });
      } else {
        const res = await fetch("/api/export-razorpayx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ctc: form.ctc,
            rent_paid: form.rentPaid || 0,
            city: form.city,
            nps_opted: form.npsOpted,
            band_min: form.bandMin,
            band_max: form.bandMax,
            employees: [employee],
          }),
        });
        const json: ExportRazorpayXResponse = await res.json();
        if (!res.ok) {
          setError((json as unknown as { error?: string }).error ?? `Export failed (HTTP ${res.status}).`);
          setLoading(false);
          return;
        }
        setResult({
          payouts: json.payouts ?? [],
          treasury_forecast: json.treasury_forecast,
          idempotencyCount: 1,
        });
      }
    } catch (e) {
      setError(isBatch ? `One or more rows failed to export: ${(e as Error).message}` : "Couldn't reach the backend at all — confirm the Flask server is running.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result.payouts, null, 2)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 10 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          onClick={(e) => e.stopPropagation()}
          className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-surface-raised p-6 shadow-2xl"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-white">
              {isBatch ? `Export ${batchRows.length} payouts to RazorpayX` : "Export to RazorpayX"}
            </h2>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-neutral-500 transition-colors hover:bg-white/[0.06] hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-1 text-sm text-neutral-500">
            Generates a schema-accurate RazorpayX Composite Payout payload. No live call is made —
            this is a formatted preview, not a real dispatch.
          </p>

          {!result ? (
            <div className="mt-6 space-y-3">
              {isBatch ? (
                <p className="rounded-lg border border-white/[0.06] bg-black/30 p-3 text-sm text-neutral-400">
                  Using bank details already present in the uploaded CSV for all {batchRows.length} rows —
                  no manual entry needed.
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <input
                    value={employee.name}
                    onChange={(e) => setEmployee((p) => ({ ...p, name: e.target.value }))}
                    placeholder="Employee name"
                    className="col-span-2 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
                  />
                  <input
                    value={employee.bank_account_number}
                    onChange={(e) => setEmployee((p) => ({ ...p, bank_account_number: e.target.value }))}
                    placeholder="Bank account number"
                    className="rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
                  />
                  <input
                    value={employee.ifsc}
                    onChange={(e) => setEmployee((p) => ({ ...p, ifsc: e.target.value }))}
                    placeholder="IFSC"
                    className="rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
                  />
                  <input
                    value={employee.email}
                    onChange={(e) => setEmployee((p) => ({ ...p, email: e.target.value }))}
                    placeholder="Email (optional)"
                    className="col-span-2 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
                  />
                </div>
              )}
              {bandMissing && (
                <p className="text-xs text-amber-300/80">
                  Enter a valid approved compensation band (min less than max) in the "Your
                  details" card first — the guardrail check needs it before a payload can be
                  generated.
                </p>
              )}
              {error && <p className="text-xs text-red-400/80">{error}</p>}
              <button
                onClick={handleGenerate}
                disabled={!canGenerate || loading}
                className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel disabled:cursor-not-allowed disabled:opacity-40"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {isBatch ? `Generate ${batchRows.length} payloads` : "Generate payload"}
              </button>
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              <div className="grid grid-cols-3 gap-3 text-center">
                {[
                  ["Net take-home", result.treasury_forecast.net_take_home_annual],
                  ["TDS escrow", result.treasury_forecast.tds_escrow_annual],
                  ["EPFO challan", result.treasury_forecast.epfo_challan_annual],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
                    <p className="text-xs text-neutral-500">{label}</p>
                    <p className="mt-1 font-mono text-sm text-neutral-200">
                      ₹{Math.round(value as number).toLocaleString("en-IN")}
                    </p>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-gold/20 bg-gold/[0.05] p-3 text-center">
                <p className="text-xs text-neutral-500">Capital required for these employees</p>
                <p className="mt-1 font-display text-lg font-semibold text-gold-bright">
                  ₹{Math.round(result.treasury_forecast.total_capital_outlay).toLocaleString("en-IN")}
                </p>
                <p className="mt-0.5 text-xs text-neutral-600">
                  Fund {result.treasury_forecast.funding_deadline_hours_before_payroll}h before payroll runs —
                  this covers only the {result.payouts.length === 1 ? "employee" : `${result.payouts.length} employees`} shown
                  here, not your full existing payroll
                </p>
              </div>

              <div className="relative">
                <div className="mb-1.5 flex items-center justify-between">
                  <p className="text-xs text-neutral-500">
                    Composite Payout payload{result.payouts.length > 1 ? `s (${result.payouts.length})` : ""}
                  </p>
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1 text-xs text-neutral-500 hover:text-white"
                  >
                    {copied ? <CheckCircle2 className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    {copied ? "Copied" : "Copy JSON"}
                  </button>
                </div>
                <pre className="max-h-64 overflow-auto rounded-xl border border-white/[0.06] bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-neutral-400">
                  {JSON.stringify(result.payouts, null, 2)}
                </pre>
              </div>

              <button
                onClick={() => setDispatched(true)}
                disabled={dispatched}
                className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-white/10 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-white/20 hover:bg-white/[0.04] disabled:cursor-not-allowed"
              >
                {dispatched ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" /> Dispatched (simulated)
                  </>
                ) : (
                  `Simulate dispatch${result.payouts.length > 1 ? ` (${result.payouts.length} payouts)` : ""}`
                )}
              </button>
              <p className="text-center text-[11px] text-neutral-600">
                Simulated only — no live call to RazorpayX. A real dispatch would set a unique{" "}
                <code className="text-neutral-500">X-Payout-Idempotency</code> header per payout
                ({result.idempotencyCount} required here).
              </p>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
