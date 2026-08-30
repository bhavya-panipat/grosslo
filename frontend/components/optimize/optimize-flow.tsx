"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import OfferLetterCard from "@/components/optimize/offer-letter-card";
import ManualEntryCard, { type FormState } from "@/components/optimize/manual-entry-card";
import ResultsSection from "@/components/optimize/results-section";
import type {
  CurrentStructurePayload,
  ExtractResponse,
  ExportRazorpayXResponse,
  GuardrailResponse,
  OptimizeResponse,
  SensitivityResponse,
  TraceStage,
} from "@/lib/api-types";

const INITIAL_FORM: FormState = {
  ctc: "",
  rentPaid: "",
  city: "metro",
  npsOpted: false,
  bandMin: "",
  bandMax: "",
};

export default function OptimizeFlow() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [extraction, setExtraction] = useState<ExtractResponse | null>(null);
  const [currentStructure, setCurrentStructure] = useState<CurrentStructurePayload | null>(null);
  const [optimizeData, setOptimizeData] = useState<OptimizeResponse | null>(null);
  const [sensitivityData, setSensitivityData] = useState<SensitivityResponse | null>(null);
  const [optimizeStatus, setOptimizeStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [guardrail, setGuardrail] = useState<GuardrailResponse | null>(null);
  const [guardrailTrace, setGuardrailTrace] = useState<TraceStage[]>([]);

  const ctcPrefilled = useRef(false);

  const handleFormChange = (patch: Partial<FormState>) => setForm((prev) => ({ ...prev, ...patch }));

  const handleExtract = (result: ExtractResponse) => {
    setExtraction(result);
    if (result.basic && result.basic > 0) {
      setCurrentStructure({
        basic: result.basic,
        hra: result.hra ?? undefined,
        lta: result.lta ?? undefined,
        employer_pf: result.employer_pf ?? undefined,
      });
    }
    // One-time prefill of CTC — only if the user hasn't already typed one,
    // and never again after this first extraction (manual edits always win).
    if (!ctcPrefilled.current && form.ctc === "" && result.ctc) {
      setForm((prev) => ({ ...prev, ctc: result.ctc as number }));
    }
    ctcPrefilled.current = true;
  };

  const handleStructureChange = (patch: Partial<CurrentStructurePayload>) => {
    setCurrentStructure((prev) => ({ ...(prev ?? { basic: 0 }), ...patch }));
  };

  const handleOptimize = () => {
    if (!form.ctc) return;
    setOptimizeStatus("loading");
    setOptimizeData(null);
    setSensitivityData(null);
    setGuardrail(null);

    const basePayload = {
      ctc: form.ctc,
      rent_paid: form.rentPaid || 0,
      city: form.city,
      nps_opted: form.npsOpted,
    };
    const includeStructure = currentStructure && currentStructure.basic > 0;

    fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...basePayload,
        ...(includeStructure
          ? { current_structure: currentStructure, extraction_ai_backed: extraction?.ai_backed ?? false }
          : {}),
      }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json: OptimizeResponse) => {
        setOptimizeData(json);
        setOptimizeStatus("success");
      })
      .catch(() => setOptimizeStatus("error"));

    fetch("/api/sensitivity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rent_paid: basePayload.rent_paid,
        city: basePayload.city,
        nps_opted: basePayload.nps_opted,
      }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json: SensitivityResponse) => setSensitivityData(json))
      .catch(() => {
        /* chart stays in its skeleton state */
      });
  };

  // Guardrail check runs automatically once results exist and a band has
  // been entered — it doesn't need employee bank details, so it's checkable
  // immediately, well before anyone reaches the RazorpayX export step.
  useEffect(() => {
    const bandReady =
      form.bandMin !== "" && form.bandMax !== "" && Number(form.bandMin) < Number(form.bandMax);
    if (!optimizeData || !bandReady) {
      setGuardrail(null);
      setGuardrailTrace([]);
      return;
    }
    let cancelled = false;
    fetch("/api/export-razorpayx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ctc: form.ctc,
        rent_paid: form.rentPaid || 0,
        city: form.city,
        nps_opted: form.npsOpted,
        band_min: form.bandMin,
        band_max: form.bandMax,
      }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((json: ExportRazorpayXResponse) => {
        if (!cancelled) {
          setGuardrail(json.compliance_metadata);
          setGuardrailTrace(json.execution_trace ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGuardrail(null);
          setGuardrailTrace([]);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optimizeData, form.bandMin, form.bandMax]);

  return (
    <section className="mx-auto max-w-6xl px-6 pb-28 pt-32 md:px-10">
      <div className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-gold-bright">{"> OPTIMIZE"}</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white sm:text-4xl">
          Structure a CTC, check compliance, export to payroll.
        </h1>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <OfferLetterCard
          structure={currentStructure}
          onExtract={handleExtract}
          onStructureChange={handleStructureChange}
        />
        <ManualEntryCard
          form={form}
          onChange={handleFormChange}
          onSubmit={handleOptimize}
          loading={optimizeStatus === "loading"}
        />
      </div>

      <AnimatePresence>
        {optimizeStatus === "error" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-6 rounded-xl border border-red-400/20 bg-red-400/[0.05] p-4 text-sm text-red-300"
          >
            Optimizer unreachable — check that the backend is running and try again.
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {optimizeData && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mt-10"
          >
            <ResultsSection
              data={optimizeData}
              sensitivityData={sensitivityData}
              guardrail={guardrail}
              executionTrace={[...(optimizeData.execution_trace ?? []), ...guardrailTrace]}
              bandMissing={
                form.bandMin === "" ||
                form.bandMax === "" ||
                Number(form.bandMin) >= Number(form.bandMax)
              }
              form={form}
              extractionRan={extraction !== null}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
