"use client";

import { useState } from "react";
import { AlertTriangle, FileText, Loader2, X } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { CurrentStructurePayload, ExtractResponse } from "@/lib/api-types";

type Props = {
  structure: CurrentStructurePayload | null;
  onExtract: (result: ExtractResponse) => void;
  onStructureChange: (patch: Partial<CurrentStructurePayload>) => void;
  onClear: () => void;
};

const FIELDS: { key: keyof CurrentStructurePayload; label: string }[] = [
  { key: "basic", label: "Basic" },
  { key: "hra", label: "HRA" },
  { key: "lta", label: "LTA" },
  { key: "employer_pf", label: "Employer PF" },
];

export default function OfferLetterCard({ structure, onExtract, onStructureChange, onClear }: Props) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [mismatchWarning, setMismatchWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The pasted text is local to this card, but the extracted structure is
  // owned by the parent (it feeds the optimize request) — clearing the
  // textarea by hand never touched it, so the extracted numbers stayed on
  // screen after the letter they came from was gone. This resets both
  // together, plus this card's own leftover warning/error state.
  const handleClear = () => {
    setText("");
    setMismatchWarning(null);
    setError(null);
    onClear();
  };

  const handleExtract = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const result: ExtractResponse = await res.json();
      setMismatchWarning(result.mismatch_warning ?? null);
      onExtract(result);
    } catch {
      setError("Couldn't reach the extractor — try again, or fill in the details manually below.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <CardShell className="flex flex-col">
      <div className="flex items-center gap-2 text-neutral-300">
        <FileText className="h-4 w-4 text-gold-bright" />
        <h3 className="font-display text-lg font-semibold text-white">Offer letter</h3>
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        Paste the offer letter text and we'll pull out the structure.
      </p>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste offer letter text here…"
        rows={6}
        className="mt-4 w-full resize-none rounded-xl border border-white/10 bg-black/40 p-3 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
      />

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={handleExtract}
          disabled={!text.trim() || loading}
          className="inline-flex items-center justify-center gap-2 self-start rounded-full border border-white/10 px-4 py-2 text-sm font-medium text-neutral-200 transition-colors hover:border-white/20 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Extract fields
        </button>
        {structure && (
          <button
            onClick={handleClear}
            className="inline-flex items-center justify-center gap-1.5 self-start rounded-full px-3 py-2 text-sm text-neutral-500 transition-colors hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-xs text-red-400/80">{error}</p>}
      {mismatchWarning && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] p-3 text-xs text-amber-200/80">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {mismatchWarning}
        </div>
      )}

      {structure && (
        <div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/[0.06] pt-4">
          {FIELDS.map(({ key, label }) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs text-neutral-500">{label}</span>
              <input
                type="number"
                value={structure[key] ?? ""}
                onChange={(e) =>
                  onStructureChange({ [key]: e.target.value === "" ? undefined : Number(e.target.value) })
                }
                className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
              />
            </label>
          ))}
        </div>
      )}
    </CardShell>
  );
}
