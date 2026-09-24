import { AlertTriangle } from "lucide-react";
import type { OptimizeResponse } from "@/lib/api-types";

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

// D-S2 §6.3: the components read from the offer letter add up to MORE than
// its stated CTC. A positive reconciliation_gap is ordinary (gratuity,
// insurance) and gets no banner; a negative one means the extraction or a
// person misread the letter, and nothing derived from the row is trustworthy
// until it's resolved. Before this, the backend's max(0, ...) clamp on
// special allowance absorbed it silently and the page showed a confident
// result. Only reachable with an extracted current structure — a CTC-only
// run has nothing to disagree with.
export default function ComponentsExceedCtcBanner({ data }: { data: OptimizeResponse }) {
  if (!data.components_exceed_stated_ctc || data.reconciliation_gap === undefined) return null;
  const excess = -data.reconciliation_gap;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-2xl border border-red-400/25 bg-red-400/[0.06] p-5"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" />
      <div>
        <p className="font-medium text-red-200">
          The offer letter&apos;s components add up to more than its CTC
        </p>
        <p className="mt-1 text-sm text-red-300/80">
          They total {inr(data.ctc + excess)}, which is {inr(excess)} more than the stated CTC of {inr(data.ctc)}.
          That usually means a figure was misread. Check the extracted figures and the CTC against the letter before
          relying on anything below.
        </p>
      </div>
    </div>
  );
}
