import CardShell from "@/components/card-shell";
import type { OptimizeResponse, StructureDict } from "@/lib/api-types";

type NumericStructureKey = Exclude<keyof StructureDict, "ctc" | "nps_opted">;

const ROWS: { key: NumericStructureKey; label: string }[] = [
  { key: "basic", label: "Basic" },
  { key: "hra", label: "HRA" },
  { key: "lta", label: "LTA" },
  { key: "special_allowance", label: "Special allowance" },
  { key: "employer_pf", label: "Employer PF" },
  { key: "employer_nps", label: "Employer NPS" },
];

const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

export default function ComparisonTable({ data }: { data: OptimizeResponse }) {
  const { old_regime_best, new_regime_best } = data;

  return (
    <CardShell>
      <h3 className="font-display text-lg font-semibold text-white">Full comparison</h3>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-white/[0.08] text-left text-xs uppercase tracking-wide text-neutral-500">
              <th className="py-2 pr-4 font-medium">Component</th>
              <th className="py-2 pr-4 font-medium">Old regime</th>
              <th className="py-2 font-medium">New regime</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.key} className="border-b border-white/[0.04] text-neutral-300">
                <td className="py-2.5 pr-4 text-neutral-500">{row.label}</td>
                <td className="py-2.5 pr-4 font-mono">{inr(old_regime_best.structure[row.key])}</td>
                <td className="py-2.5 font-mono">{inr(new_regime_best.structure[row.key])}</td>
              </tr>
            ))}
            <tr className="text-white">
              <td className="py-2.5 pr-4 font-medium">Total tax</td>
              <td className="py-2.5 pr-4 font-mono font-medium">{inr(old_regime_best.tax_breakdown.total_tax)}</td>
              <td className="py-2.5 font-mono font-medium">{inr(new_regime_best.tax_breakdown.total_tax)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </CardShell>
  );
}
