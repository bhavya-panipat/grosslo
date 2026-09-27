"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CalendarRange, Info, Loader2, Plus, Trash2, Users } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { WorkforceForecastCohortInput, WorkforceForecastResponse } from "@/lib/api-types";

// Addition spec 2.1 — WORKFORCE_COST_FORECAST_DESIGN.md. This page formats what
// /api/workforce-forecast returns and computes nothing itself: every figure,
// every refusal and every note comes from workforce_forecast.py.

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

const LOCATIONS: { value: string; label: string }[] = [
  { value: "", label: "Not specified (PT not modelled)" },
  { value: "karnataka", label: "Karnataka" },
  { value: "maharashtra", label: "Maharashtra" },
  { value: "telangana", label: "Telangana" },
  { value: "tamil_nadu", label: "Tamil Nadu" },
  { value: "delhi", label: "Delhi" },
];

type CohortForm = {
  label: string;
  headcount: number | "";
  ctc: number | "";
  city: "metro" | "non_metro";
  npsOpted: boolean;
  joinMonth: string;
  rentPaid: number | "";
  workLocation: string;
  provisionExcluded: number | "";
};

const newCohort = (): CohortForm => ({
  label: "",
  headcount: 1,
  ctc: "",
  city: "metro",
  npsOpted: false,
  joinMonth: "2026-10",
  rentPaid: "",
  workLocation: "",
  provisionExcluded: "",
});

const inputClass =
  "rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none";

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="text-xs text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

const num = (v: string): number | "" => (v === "" ? "" : Number(v));

export default function ForecastFlow() {
  const [start, setStart] = useState("2026-10");
  const [end, setEnd] = useState("2026-12");
  const [cohorts, setCohorts] = useState<CohortForm[]>([newCohort()]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WorkforceForecastResponse | null>(null);

  const update = (i: number, patch: Partial<CohortForm>) =>
    setCohorts((prev) => prev.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const canSubmit = cohorts.every((c) => c.ctc !== "" && c.headcount !== "" && c.joinMonth);

  const handleSubmit = async () => {
    setStatus("loading");
    setError(null);
    const body = {
      period: { start, end },
      cohorts: cohorts.map<WorkforceForecastCohortInput>((c) => ({
        label: c.label || undefined,
        headcount: Number(c.headcount),
        ctc: Number(c.ctc),
        city: c.city,
        nps_opted: c.npsOpted,
        join_month: c.joinMonth,
        rent_paid: c.rentPaid === "" ? null : Number(c.rentPaid),
        work_location: c.workLocation || null,
        provision_excluded: c.provisionExcluded === "" ? 0 : Number(c.provisionExcluded),
      })),
    };
    try {
      const res = await fetch("/api/workforce-forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        // A 400 carries the backend's reason (rent required, period past the
        // rate year, bad input) — show it verbatim, it says what to fix.
        setError(data?.error ?? `Forecast failed (${res.status}).`);
        setStatus("error");
        setResult(null);
        return;
      }
      setResult(data as WorkforceForecastResponse);
      setStatus("idle");
    } catch {
      setError("Forecast service unreachable — check that the backend is running and try again.");
      setStatus("error");
      setResult(null);
    }
  };

  return (
    <section className="mx-auto max-w-6xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> FORECAST"}</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
          What planned hires will cost, month by month.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-neutral-500">
          The total cash need is the CTC, prorated. What this adds is where that cash goes — take-home, TDS, EPFO,
          NPS and professional tax — for each month of the period.
        </p>
      </div>

      <CardShell>
        <div className="flex items-center gap-2 text-neutral-300">
          <CalendarRange className="h-4 w-4 text-gold-bright" />
          <h3 className="font-display text-lg font-semibold text-white">Period</h3>
        </div>
        <div className="mt-4 grid max-w-md grid-cols-2 gap-3">
          <Field label="From">
            <input type="month" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
          </Field>
          <Field label="To">
            <input type="month" value={end} onChange={(e) => setEnd(e.target.value)} className={inputClass} />
          </Field>
        </div>
        <p className="mt-2 text-xs text-neutral-600">April 2026 to March 2027 only — the year whose tax rates are enacted.</p>
      </CardShell>

      <div className="mt-4 flex flex-col gap-4">
        {cohorts.map((c, i) => (
          <CardShell key={i}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-neutral-300">
                <Users className="h-4 w-4 text-gold-bright" />
                <h3 className="font-display text-lg font-semibold text-white">Hiring group {i + 1}</h3>
              </div>
              {cohorts.length > 1 && (
                <button
                  onClick={() => setCohorts((prev) => prev.filter((_, j) => j !== i))}
                  className="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-red-300"
                  aria-label={`Remove hiring group ${i + 1}`}
                >
                  <Trash2 className="h-3.5 w-3.5" /> Remove
                </button>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Name (optional)" className="col-span-2">
                <input value={c.label} onChange={(e) => update(i, { label: e.target.value })} placeholder="Backend engineers" className={inputClass} />
              </Field>
              <Field label="Hires">
                <input type="number" min={1} value={c.headcount} onChange={(e) => update(i, { headcount: num(e.target.value) })} className={inputClass} />
              </Field>
              <Field label="Joining month">
                <input type="month" value={c.joinMonth} onChange={(e) => update(i, { joinMonth: e.target.value })} className={inputClass} />
              </Field>
              <Field label="CTC per hire (annual, ₹)" className="col-span-2">
                <input type="number" value={c.ctc} onChange={(e) => update(i, { ctc: num(e.target.value) })} placeholder="1800000" className={inputClass} />
              </Field>
              <Field label="City">
                <select value={c.city} onChange={(e) => update(i, { city: e.target.value as CohortForm["city"] })} className={inputClass}>
                  <option value="metro">Metro</option>
                  <option value="non_metro">Non-metro</option>
                </select>
              </Field>
              <Field label="Work location (for PT)">
                <select value={c.workLocation} onChange={(e) => update(i, { workLocation: e.target.value })} className={inputClass}>
                  {LOCATIONS.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Rent paid (annual, ₹) — asked for when it changes the tax" className="col-span-2">
                <input type="number" value={c.rentPaid} onChange={(e) => update(i, { rentPaid: num(e.target.value) })} placeholder="Leave blank if unknown" className={inputClass} />
              </Field>
              <Field label="Gratuity/insurance inside the CTC (₹, optional)" className="col-span-2">
                <input type="number" value={c.provisionExcluded} onChange={(e) => update(i, { provisionExcluded: num(e.target.value) })} placeholder="0" className={inputClass} />
              </Field>
              <label className="col-span-2 flex items-center gap-2 text-sm text-neutral-300 md:col-span-4">
                <input type="checkbox" checked={c.npsOpted} onChange={(e) => update(i, { npsOpted: e.target.checked })} className="h-4 w-4 accent-gold-bright" />
                Employer NPS contribution
              </label>
            </div>
          </CardShell>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => setCohorts((prev) => [...prev, newCohort()])}
          className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm text-neutral-300 transition-colors hover:border-white/20 hover:text-white"
        >
          <Plus className="h-4 w-4" /> Add a hiring group
        </button>
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || status === "loading"}
          className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel disabled:cursor-not-allowed disabled:opacity-40"
        >
          {status === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
          Forecast
        </button>
      </div>

      <AnimatePresence>
        {status === "error" && error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            role="alert"
            className="mt-6 flex items-start gap-2 rounded-xl border border-red-400/20 bg-red-400/[0.05] p-4 text-sm text-red-300"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {result && <ForecastResults result={result} />}
    </section>
  );
}

function ForecastResults({ result }: { result: WorkforceForecastResponse }) {
  const t = result.totals;
  const zeroRentGroups = result.cohorts
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => c.rent_assumed_zero);
  const unmodelledPt = result.cohorts.map((c, i) => ({ c, i })).filter(({ c }) => !c.pt_state_recognized);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="mt-10 flex flex-col gap-4"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-gold/25 bg-gold/[0.05] p-5">
          <p className="text-xs uppercase tracking-wide text-neutral-400">Total cash need, {result.period.start} to {result.period.end}</p>
          <p className="mt-2 font-display text-3xl font-semibold text-gold-bright">{inr(t.total)}</p>
          <p className="mt-1 text-[11px] text-neutral-500">The same whichever TDS case applies — TDS and take-home are two slices of it.</p>
        </div>
        <div className="rounded-2xl border border-white/[0.08] bg-surface p-5">
          <p className="text-xs uppercase tracking-wide text-neutral-400">TDS to remit</p>
          <p className="mt-2 font-display text-3xl font-semibold text-white">{inr(t.tds)}</p>
          <p className="mt-1 text-[11px] text-neutral-500">
            If earlier salary is declared at the same rate: <span className="font-mono text-neutral-300">{inr(t.tds_if_declared)}</span>
          </p>
        </div>
      </div>

      <CardShell className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-white/[0.06] text-xs uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-4 py-3 font-medium">Month</th>
                <th className="px-4 py-3 font-medium text-right">Take-home</th>
                <th className="px-4 py-3 font-medium text-right">TDS</th>
                <th className="px-4 py-3 font-medium text-right">EPFO</th>
                <th className="px-4 py-3 font-medium text-right">NPS</th>
                <th className="px-4 py-3 font-medium text-right">Prof. tax</th>
                <th className="px-4 py-3 font-medium text-right">Total</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums text-neutral-300">
              {result.months.map((m) => (
                <tr key={m.month} className="border-b border-white/[0.04]">
                  <td className="px-4 py-2.5 font-sans text-neutral-200">{m.month}</td>
                  <td className="px-4 py-2.5 text-right">{inr(m.net_take_home)}</td>
                  <td className="px-4 py-2.5 text-right">{inr(m.tds)}</td>
                  <td className="px-4 py-2.5 text-right">{inr(m.epfo_challan)}</td>
                  <td className="px-4 py-2.5 text-right">{inr(m.nps_remittance)}</td>
                  <td className="px-4 py-2.5 text-right">{inr(m.professional_tax)}</td>
                  <td className="px-4 py-2.5 text-right text-white">{inr(m.total)}</td>
                </tr>
              ))}
              <tr className="text-white">
                <td className="px-4 py-3 font-sans font-medium">Total</td>
                <td className="px-4 py-3 text-right">{inr(t.net_take_home)}</td>
                <td className="px-4 py-3 text-right">{inr(t.tds)}</td>
                <td className="px-4 py-3 text-right">{inr(t.epfo_challan)}</td>
                <td className="px-4 py-3 text-right">{inr(t.nps_remittance)}</td>
                <td className="px-4 py-3 text-right">{inr(t.professional_tax)}</td>
                <td className="px-4 py-3 text-right text-gold-bright">{inr(t.total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardShell>

      <CardShell>
        <div className="flex items-center gap-2 text-neutral-300">
          <Info className="h-4 w-4 text-gold-bright" />
          <h3 className="font-display text-base font-semibold text-white">What these figures assume</h3>
        </div>
        <ul className="mt-3 flex flex-col gap-2 text-sm text-neutral-400">
          <li>{result.notes.tds_basis}</li>
          <li>{result.notes.ctc_basis}</li>
          <li>{result.notes.rates}</li>
          {result.cohorts.map((c, i) => (
            <li key={i}>
              Hiring group {i + 1}{c.label ? ` (${c.label})` : ""}: {c.regime_assumed} tax regime assumed (the recommended one; each
              hire chooses), {c.months_employed_in_fy} month{c.months_employed_in_fy === 1 ? "" : "s"} employed this year.
            </li>
          ))}
          {zeroRentGroups.length > 0 && (
            <li>
              Hiring group{zeroRentGroups.length === 1 ? "" : "s"} {zeroRentGroups.map(({ i }) => i + 1).join(", ")}:{" "}
              {result.notes.rent_assumed_zero}
            </li>
          )}
          {unmodelledPt.length > 0 && (
            <li>
              Hiring group{unmodelledPt.length === 1 ? "" : "s"} {unmodelledPt.map(({ i }) => i + 1).join(", ")}: professional tax not
              modelled for this location — shown as ₹0, which is not a claim that none is due.
            </li>
          )}
        </ul>
        <p className="mt-4 text-xs uppercase tracking-wide text-neutral-500">Not modelled</p>
        <ul className="mt-2 list-disc pl-5 text-xs text-neutral-500">
          {result.notes.not_modelled.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </CardShell>
    </motion.div>
  );
}
