import RegimeChart from "@/components/regime-chart";
import RingMetrics from "@/components/ring-metric";
import ComplianceCard from "@/components/compliance-card";
import ExplainCard from "@/components/explain-card";
import CardShell from "@/components/card-shell";
import RecommendationBanner from "@/components/optimize/recommendation-banner";
import CapabilityStrip from "@/components/optimize/capability-strip";
import CompositionBars from "@/components/optimize/composition-bars";
import GuardrailPanel from "@/components/optimize/guardrail-panel";
import RazorpayXExportTrigger from "@/components/optimize/razorpayx-export-trigger";
import ComparisonTable from "@/components/optimize/comparison-table";
import QueryPanel from "@/components/optimize/query-panel";
import ExecutionTraceDrawer from "@/components/optimize/execution-trace-drawer";
import type { GuardrailResponse, OptimizeResponse, SensitivityResponse, TraceStage } from "@/lib/api-types";
import type { FormState } from "@/components/optimize/manual-entry-card";

export default function ResultsSection({
  data,
  sensitivityData,
  guardrail,
  executionTrace,
  bandMissing,
  form,
  extractionRan,
}: {
  data: OptimizeResponse;
  sensitivityData: SensitivityResponse | null;
  guardrail: GuardrailResponse | null;
  executionTrace: TraceStage[];
  bandMissing: boolean;
  form: FormState;
  extractionRan: boolean;
}) {
  const recommendedResult = data.recommended_regime === "new" ? data.new_regime_best : data.old_regime_best;

  return (
    <div className="flex flex-col gap-6">
      <RecommendationBanner data={data} />
      <CapabilityStrip data={data} extractionRan={extractionRan} />
      <ExecutionTraceDrawer trace={executionTrace} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <CardShell className="md:col-span-2 md:row-span-2">
          <RegimeChart points={sensitivityData?.points ?? null} />
        </CardShell>
        <CardShell>
          <RingMetrics metrics={data.metrics} />
        </CardShell>
        <ComplianceCard data={data} />
        <ExplainCard data={data} />
      </div>

      <CompositionBars oldResult={data.old_regime_best} newResult={data.new_regime_best} />

      <GuardrailPanel guardrail={guardrail} bandMissing={bandMissing} />

      <div className="flex justify-end">
        <RazorpayXExportTrigger form={form} />
      </div>

      <ComparisonTable data={data} />

      <QueryPanel
        form={form}
        context={{
          recommended_regime: data.recommended_regime,
          recommended_tax: recommendedResult.tax_breakdown.total_tax,
          annual_saving: data.annual_saving,
        }}
      />
    </div>
  );
}
