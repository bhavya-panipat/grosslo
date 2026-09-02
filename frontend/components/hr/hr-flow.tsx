"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Papa from "papaparse";
import { Send, Upload, Loader2, RotateCcw } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { CreateSubmissionResponse, Submission } from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-white/10 text-neutral-300",
    approved: "bg-emerald-400/10 text-emerald-300",
    rejected: "bg-red-400/10 text-red-300",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? ""}`}>
      {status}
    </span>
  );
}

export default function HrFlow() {
  const [name, setName] = useState("");
  const [ctc, setCtc] = useState("");
  const [rentPaid, setRentPaid] = useState("");
  const [city, setCity] = useState<"metro" | "non_metro">("metro");
  const [npsOpted, setNpsOpted] = useState(false);
  const [bandMin, setBandMin] = useState("");
  const [bandMax, setBandMax] = useState("");
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [email, setEmail] = useState("");
  const [workLocation, setWorkLocation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<CreateSubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mySubmissions, setMySubmissions] = useState<Submission[]>([]);
  const [csvName, setCsvName] = useState<string | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  // Remounts the file <input> on clear/success — re-selecting the exact
  // same filename otherwise fires no onChange at all (a real HTML file-
  // input quirk, not a React one), so a "try that file again" fix has to
  // be more than just resetting the displayed name.
  const [csvInputKey, setCsvInputKey] = useState(0);

  const refreshQueue = useCallback(() => {
    fetch("/api/submissions")
      .then((r) => r.json())
      .then((d) => setMySubmissions(d.submissions ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshQueue();
  }, [refreshQueue]);

  // Shared by the post-submit auto-clear and the explicit "Clear form"
  // button, so there's exactly one definition of "empty form" — not two
  // that could drift (e.g. one resetting city to "metro", the other
  // forgetting to).
  const clearSingleForm = () => {
    setName("");
    setCtc("");
    setRentPaid("");
    setCity("metro");
    setNpsOpted(false);
    setBandMin("");
    setBandMax("");
    setBankAccountNumber("");
    setIfsc("");
    setEmail("");
    setWorkLocation("");
  };

  const handleSubmitSingle = () => {
    if (!ctc) return;
    setSubmitting(true);
    setError(null);
    setLastResult(null);
    fetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "single",
        row: {
          employee_name: name || undefined,
          ctc: Number(ctc),
          rent_paid: rentPaid ? Number(rentPaid) : 0,
          city,
          nps_opted: npsOpted,
          band_min: bandMin ? Number(bandMin) : undefined,
          band_max: bandMax ? Number(bandMax) : undefined,
          bank_account_number: bankAccountNumber || undefined,
          ifsc: ifsc || undefined,
          email: email || undefined,
          work_location: workLocation || undefined,
        },
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((json: CreateSubmissionResponse) => {
        setLastResult(json);
        setSubmitting(false);
        // Real product behavior, not just a testing convenience: an HR
        // user submitting one offer after another wants a fresh form each
        // time, not the previous candidate's numbers still sitting there
        // to accidentally resubmit. Only clears on success — a failed
        // submission leaves the form as-is so nothing typed is lost.
        clearSingleForm();
        refreshQueue();
      })
      .catch(() => {
        setError("Couldn't submit — confirm the backend is running.");
        setSubmitting(false);
      });
  };

  const handleCsvUpload = (file: File) => {
    setCsvName(file.name);
    setCsvError(null);
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          setCsvError(results.errors[0].message);
          return;
        }
        const rows = results.data
          .filter((r) => r.ctc)
          .map((r) => ({
            // Accepts both employee_name and name — the New Hire Batch
            // CSVs used elsewhere in this project (e.g. /optimize/batch)
            // use `name`, and requiring a different column here just for
            // this page would be an inconsistency nobody asked for.
            employee_name: r.employee_name || r.name || undefined,
            ctc: Number(r.ctc),
            rent_paid: r.rent_paid ? Number(r.rent_paid) : 0,
            city: r.city === "non_metro" ? "non_metro" : "metro",
            nps_opted: ["true", "1", "yes"].includes((r.nps_opted || "").toLowerCase()),
            // Optional — only needed for new hires that should be exportable
            // straight to RazorpayX after Finance approves them. A row missing
            // these still submits fine; it just won't have an export path later.
            band_min: r.band_min ? Number(r.band_min) : undefined,
            band_max: r.band_max ? Number(r.band_max) : undefined,
            bank_account_number: r.bank_account_number || undefined,
            ifsc: r.ifsc || undefined,
            email: r.email || undefined,
            work_location: r.work_location || undefined,
          }));
        if (rows.length === 0) {
          setCsvError("No valid rows found — a ctc column is required.");
          return;
        }
        setSubmitting(true);
        fetch("/api/submissions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: "batch", rows }),
        })
          .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
          .then((json: CreateSubmissionResponse) => {
            setLastResult(json);
            setSubmitting(false);
            // Same reasoning as the single-offer form: a submitted batch
            // is done, and leaving the old filename displayed would read
            // as "this file is still active" when it's actually already
            // queued.
            setCsvName(null);
            setCsvInputKey((k) => k + 1);
            refreshQueue();
          })
          .catch(() => {
            setCsvError("Couldn't submit — confirm the backend is running.");
            setSubmitting(false);
          });
      },
    });
  };

  return (
    <section className="mx-auto max-w-5xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> HR"}</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
          Submit a structure for Finance review.
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-neutral-500">
          Structures a compensation offer, then queues it for Finance to inspect and approve or
          reject — nothing is dispatched anywhere on submit, and approving later only marks the
          decision, it never calls RazorpayX.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardShell>
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg font-semibold text-white">Single offer</h3>
            {(name || ctc || rentPaid || bandMin || bandMax || bankAccountNumber || ifsc || email || workLocation) && (
              <button
                onClick={clearSingleForm}
                className="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300"
              >
                <RotateCcw className="h-3 w-3" />
                Clear form
              </button>
            )}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Employee name (optional)</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ananya Rao"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-xs text-neutral-500">CTC (annual, ₹)</span>
              <input
                type="number"
                value={ctc}
                onChange={(e) => setCtc(e.target.value)}
                placeholder="1800000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Rent paid (annual, ₹)</span>
              <input
                type="number"
                value={rentPaid}
                onChange={(e) => setRentPaid(e.target.value)}
                placeholder="400000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">City</span>
              <select
                value={city}
                onChange={(e) => setCity(e.target.value as "metro" | "non_metro")}
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              >
                <option value="metro">Metro</option>
                <option value="non_metro">Non-metro</option>
              </select>
            </label>
            <label className="col-span-2 flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                checked={npsOpted}
                onChange={(e) => setNpsOpted(e.target.checked)}
                className="h-4 w-4 rounded border-white/20 bg-black/40 accent-gold-bright"
              />
              <span className="text-sm text-neutral-300">Opted into NPS</span>
            </label>
          </div>

          <p className="col-span-2 mt-4 text-xs uppercase tracking-wide text-neutral-600">
            Optional — needed only to export this offer to RazorpayX after approval
          </p>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Approved band min (₹)</span>
              <input
                type="number"
                value={bandMin}
                onChange={(e) => setBandMin(e.target.value)}
                placeholder="1500000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Approved band max (₹)</span>
              <input
                type="number"
                value={bandMax}
                onChange={(e) => setBandMax(e.target.value)}
                placeholder="2000000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Bank account number</span>
              <input
                value={bankAccountNumber}
                onChange={(e) => setBankAccountNumber(e.target.value)}
                placeholder="0000000000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">IFSC</span>
              <input
                value={ifsc}
                onChange={(e) => setIfsc(e.target.value)}
                placeholder="TEST0000000"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-xs text-neutral-500">Email (optional)</span>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ananya@company.com"
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-xs text-neutral-500">
                Work location (optional — state Professional Tax)
              </span>
              <select
                value={workLocation}
                onChange={(e) => setWorkLocation(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              >
                <option value="">Not specified — PT not modeled</option>
                <option value="karnataka">Karnataka</option>
                <option value="maharashtra">Maharashtra</option>
                <option value="telangana">Telangana</option>
                <option value="tamil_nadu">Tamil Nadu (monthly-equivalent approximation)</option>
                <option value="delhi">Delhi (no PT levied)</option>
              </select>
            </label>
          </div>

          <button
            onClick={handleSubmitSingle}
            disabled={!ctc || submitting}
            className="mt-5 inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Submit to Finance for Review
          </button>
          {error && <p className="mt-2 text-xs text-red-400/80">{error}</p>}
        </CardShell>

        <CardShell>
          <h3 className="font-display text-lg font-semibold text-white">Batch CSV</h3>
          <p className="mt-1 text-sm text-neutral-500">
            Columns:{" "}
            <span className="font-mono text-xs text-neutral-400">
              name (or employee_name), ctc, rent_paid, city, nps_opted
            </span>
          </p>
          <p className="mt-1 text-sm text-neutral-500">
            Optional (needed for RazorpayX export after approval):{" "}
            <span className="font-mono text-xs text-neutral-400">
              band_min, band_max, bank_account_number, ifsc, email
            </span>
          </p>
          <p className="mt-1 text-sm text-neutral-500">
            Optional (state Professional Tax):{" "}
            <span className="font-mono text-xs text-neutral-400">work_location</span> — karnataka,
            maharashtra, telangana, tamil_nadu, or delhi.
          </p>
          <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 bg-black/30 px-6 py-8 text-center transition-colors hover:border-gold-bright/40 hover:bg-white/[0.02]">
            <Upload className="h-5 w-5 text-neutral-500" />
            <span className="text-sm text-neutral-400">{csvName || "Click to choose a CSV file"}</span>
            <input
              key={csvInputKey}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleCsvUpload(file);
              }}
            />
          </label>
          {csvError && (
            <p className="mt-3 rounded-lg border border-red-400/20 bg-red-400/[0.05] p-3 text-xs text-red-300">
              {csvError}
            </p>
          )}
        </CardShell>
      </div>

      <AnimatePresence>
        {lastResult && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-6 rounded-xl border border-gold/20 bg-gold/[0.05] p-4 text-sm text-neutral-300"
          >
            Submitted (ID {lastResult.submission_id}) — {lastResult.inserted_row_ids.length} row
            {lastResult.inserted_row_ids.length === 1 ? "" : "s"} queued for Finance review.
            {lastResult.duplicates.length > 0 && (
              <span className="mt-1 block text-gold-bright">
                {lastResult.duplicates.length} row{lastResult.duplicates.length === 1 ? "" : "s"} flagged as a likely
                duplicate (same employee + CTC submitted earlier today) and skipped, not reprocessed.
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-10">
        <h3 className="font-display text-lg font-semibold text-white">My submissions</h3>
        <div className="mt-4 flex flex-col gap-3">
          {mySubmissions.length === 0 && (
            <p className="text-sm text-neutral-600">Nothing submitted yet.</p>
          )}
          {mySubmissions.map((s) => (
            <CardShell key={s.id} className="p-4">
              <p className="mb-2 text-xs text-neutral-500">
                Submission {s.id} · {s.source} · {new Date(s.created_at).toLocaleString()}
              </p>
              <div className="flex flex-col gap-2">
                {s.rows.map((row) => (
                  <div key={row.id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-neutral-300">
                      {row.employee_name || `Row ${row.row_index + 1}`} — {inr(row.ctc)}
                    </span>
                    <div className="flex items-center gap-2">
                      {row.reason && <span className="text-xs text-neutral-500">{row.reason}</span>}
                      <StatusPill status={row.status} />
                    </div>
                  </div>
                ))}
              </div>
            </CardShell>
          ))}
        </div>
      </div>
    </section>
  );
}
