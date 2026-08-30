"use client";

import { useRef } from "react";
import { Loader2, Sliders } from "lucide-react";
import CardShell from "@/components/card-shell";

export type FormState = {
  ctc: number | "";
  rentPaid: number | "";
  city: "metro" | "non_metro";
  npsOpted: boolean;
  bandMin: number | "";
  bandMax: number | "";
};

type Props = {
  form: FormState;
  onChange: (patch: Partial<FormState>) => void;
  onSubmit: () => void;
  loading: boolean;
};

// ±15% of CTC, rounded to the nearest ₹50,000 for a clean default band.
function suggestBand(ctc: number): { bandMin: number; bandMax: number } {
  const round50k = (v: number) => Math.round(v / 50_000) * 50_000;
  return { bandMin: round50k(ctc * 0.85), bandMax: round50k(ctc * 1.15) };
}

export default function ManualEntryCard({ form, onChange, onSubmit, loading }: Props) {
  // Tracks whether the user has directly edited a band field — once they
  // have, CTC changes stop overwriting their choice (same "manual edits
  // always win" precedent as the offer-letter CTC prefill).
  const bandTouched = useRef(false);

  const handleCtcChange = (value: string) => {
    const ctc = value === "" ? "" : Number(value);
    if (ctc !== "" && !bandTouched.current) {
      onChange({ ctc, ...suggestBand(ctc) });
    } else {
      onChange({ ctc });
    }
  };

  const handleBandChange = (patch: Partial<Pick<FormState, "bandMin" | "bandMax">>) => {
    bandTouched.current = true;
    onChange(patch);
  };

  const bandInvalid =
    form.bandMin !== "" && form.bandMax !== "" && Number(form.bandMin) >= Number(form.bandMax);

  return (
    <CardShell className="flex flex-col">
      <div className="flex items-center gap-2 text-neutral-300">
        <Sliders className="h-4 w-4 text-gold-bright" />
        <h3 className="font-display text-lg font-semibold text-white">Your details</h3>
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        CTC is the only required field — everything else defaults sensibly.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-xs text-neutral-500">CTC (annual, ₹)</span>
          <input
            type="number"
            value={form.ctc}
            onChange={(e) => handleCtcChange(e.target.value)}
            placeholder="1800000"
            className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-neutral-500">Rent paid (annual, ₹)</span>
          <input
            type="number"
            value={form.rentPaid}
            onChange={(e) => onChange({ rentPaid: e.target.value === "" ? "" : Number(e.target.value) })}
            placeholder="400000"
            className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-neutral-500">City</span>
          <select
            value={form.city}
            onChange={(e) => onChange({ city: e.target.value as FormState["city"] })}
            className="rounded-lg border border-white/10 bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
          >
            <option value="metro">Metro</option>
            <option value="non_metro">Non-metro</option>
          </select>
        </label>

        <label className="col-span-2 flex items-center gap-2 pt-1">
          <input
            type="checkbox"
            checked={form.npsOpted}
            onChange={(e) => onChange({ npsOpted: e.target.checked })}
            className="h-4 w-4 rounded border-white/20 bg-black/40 accent-gold-bright"
          />
          <span className="text-sm text-neutral-300">Opted into NPS</span>
        </label>

        <div className="col-span-2 mt-1 border-t border-white/[0.06] pt-3">
          <p className="mb-2 text-xs text-neutral-500">
            Approved compensation band (for guardrail checks)
            {!bandTouched.current && form.bandMin !== "" && (
              <span className="ml-1.5 text-neutral-600">— suggested from CTC, edit freely</span>
            )}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="number"
              value={form.bandMin}
              onChange={(e) =>
                handleBandChange({ bandMin: e.target.value === "" ? "" : Number(e.target.value) })
              }
              placeholder="Band min (₹)"
              className={`rounded-lg border bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:outline-none ${
                bandInvalid ? "border-red-400/40 focus:border-red-400/60" : "border-white/10 focus:border-gold-bright/50"
              }`}
            />
            <input
              type="number"
              value={form.bandMax}
              onChange={(e) =>
                handleBandChange({ bandMax: e.target.value === "" ? "" : Number(e.target.value) })
              }
              placeholder="Band max (₹)"
              className={`rounded-lg border bg-black/40 px-2.5 py-1.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:outline-none ${
                bandInvalid ? "border-red-400/40 focus:border-red-400/60" : "border-white/10 focus:border-gold-bright/50"
              }`}
            />
          </div>
          {bandInvalid && (
            <p className="mt-1.5 text-xs text-red-400/80">Band min must be less than band max.</p>
          )}
        </div>
      </div>

      <button
        onClick={onSubmit}
        disabled={!form.ctc || loading}
        className="mt-5 inline-flex items-center justify-center gap-2 self-start rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        Optimize
      </button>
    </CardShell>
  );
}
