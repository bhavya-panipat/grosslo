// Full, accurate request/response types for the Flask backend's /api/* routes.
// Verified directly against app.py / ai_layer.py / tax_engine.py rather than
// assumed — see the plan file for the specific line references.

export type StructureDict = {
  ctc: number;
  basic: number;
  hra: number;
  lta: number;
  special_allowance: number;
  employer_pf: number;
  employer_nps: number;
  nps_opted: boolean;
};

export type TaxBreakdown = {
  total_tax: number;
  slab_tax: number;
  tax_after_rebate: number;
  tax_after_marginal_relief: number;
  cess: number;
  taxable_income: number;
};

export type OptResult = {
  regime: "old" | "new";
  structure: StructureDict;
  taxable_income: number;
  tax_breakdown: TaxBreakdown;
  basic_pct: number;
};

export type ComplianceFlag = {
  rule_id: string;
  severity: "Low" | "Medium" | "High";
  message: string;
  rationale: string;
};

export type NegotiationResponse = {
  points: string; // prose, not a list, despite the field name
  total_annual_saving: number;
  changed_levers: string[];
  ai_backed: boolean;
  guard_triggered: boolean;
};

export type OptimizeResponse = {
  ctc: number;
  old_regime_best: OptResult;
  new_regime_best: OptResult;
  recommended_regime: "old" | "new";
  annual_saving: number;
  explanation: { explanation: string; ai_backed: boolean; guard_triggered: boolean };
  compliance: { flags: ComplianceFlag[]; ai_backed: boolean; guard_triggered?: boolean };
  compliance_checked_against: "as_offered" | "recommended";
  negotiation?: NegotiationResponse; // present iff request included current_structure
  metrics: {
    optimization_value_pct: number;
    compliance_pct: number;
    ai_coverage_pct: number;
  };
  execution_trace?: TraceStage[];
  // Present iff the submission carried a band_min/band_max — /api/submissions
  // runs the same evaluate_band_guardrail() the single-candidate flow uses,
  // not a separate check.
  guardrail?: GuardrailResponse;
  // Present on /api/submissions rows only (computed against the RECOMMENDED
  // structure, same call /api/export-razorpayx makes) — absent on plain
  // /api/optimize responses, which have no review-queue row to fund.
  treasury_forecast?: TreasuryForecast;
};

export type SensitivityPoint = {
  ctc: number;
  old_tax: number;
  new_tax: number;
  recommended_regime: "old" | "new";
};

export type SensitivityResponse = {
  points: SensitivityPoint[];
  rent_paid: number;
  city: string;
  nps_opted: boolean;
};

export type HealthResponse = {
  status: string;
  ai_layer_active: boolean;
};

// /api/extract
export type ExtractResponse = {
  ctc: number | null;
  basic: number | null;
  hra: number | null;
  lta: number | null;
  special_allowance: number | null;
  employer_pf: number | null;
  ai_backed: boolean;
  mismatch_warning?: string | null;
  currency_note?: string;
};

// What actually gets sent back to /api/optimize's current_structure field —
// deliberately a subset of ExtractResponse (backend ignores ctc/special_allowance
// on this path; special_allowance is recomputed server-side as a residual, and
// only basic is required — the backend treats basic<=0 the same as "omit this
// field entirely," per _build_current_structure in app.py).
export type CurrentStructurePayload = {
  basic: number;
  hra?: number;
  lta?: number;
  employer_pf?: number;
};

// /api/query
export type QueryResponse = {
  answer: string;
  ai_backed: boolean;
  recalculated?: boolean;
  guard_triggered?: boolean;
  error?: string;
};

export type QueryContext = {
  recommended_regime: "old" | "new";
  recommended_tax: number;
  annual_saving: number;
};

// New for the RazorpayX pivot — /api/export-razorpayx

export type CompositeBankAccountPayout = {
  account_number: string; // grosslo's own RazorpayX account number, not the employee's
  amount: number; // paise
  currency: "INR";
  mode: "IMPS" | "NEFT" | "RTGS";
  purpose: "salary";
  fund_account: {
    account_type: "bank_account";
    bank_account: { name: string; ifsc: string; account_number: string };
    contact: {
      name: string;
      email?: string;
      contact?: string;
      type: "employee";
      reference_id: string;
    };
  };
  queue_if_low_balance: boolean;
  reference_id: string;
  narration: string;
};

export type TreasuryForecast = {
  net_take_home_annual: number;
  tds_escrow_annual: number;
  epfo_challan_annual: number;
  // State Professional Tax — 0 with pt_state_recognized:false when
  // work_location wasn't supplied or isn't one of the 5 modeled states
  // (a real "not modeled" gap), vs. Delhi's genuine, checked 0 with
  // pt_state_recognized:true. pt_is_approximation is true only for
  // tamil_nadu (a monthly-equivalent of its real half-yearly assessment).
  professional_tax_annual: number;
  pt_state_recognized: boolean;
  pt_is_approximation: boolean;
  total_capital_outlay: number;
  funding_deadline_hours_before_payroll: number;
};

export type GuardrailCheck = {
  id: string;
  label: string;
  passed: boolean;
  message: string;
};

export type GuardrailResponse = {
  verdict: "pass" | "flag";
  checks: GuardrailCheck[];
  ai_backed: boolean;
  guard_triggered: boolean;
};

// Execution trace — additive, optional on OptimizeResponse/GuardrailResponse.
// Never a hardcoded placeholder: every line is built server-side from a
// field that's already present elsewhere in the same response.
export type TraceStage = {
  stage: string; // e.g. "PARSE_INGESTION", "COMPLIANCE_PASS", "MATH_SOLVER", "POLICY_GATE"
  message: string;
};

export type ExportRazorpayXResponse = {
  // payouts is only present when the request included `employees` — the
  // same endpoint doubles as a guardrail/treasury-only check before anyone
  // has entered payroll bank details.
  payouts?: CompositeBankAccountPayout[];
  treasury_forecast: TreasuryForecast;
  compliance_metadata: GuardrailResponse;
  idempotency_key_hint: string; // a value the client can use to set X-Payout-Idempotency on real dispatch
  execution_trace?: TraceStage[];
};

// Batch mode — /api/batch-audit

export type PenaltyScenarioRow = {
  months_delayed: number;
  section_7q_interest: number;
  section_14b_damages: number;
  section_14b_cap_applied: boolean;
  section_201_1a_interest: number;
  total: number;
};

export type PenaltyScenario = {
  rows: PenaltyScenarioRow[];
  disclaimer: string;
};

export type BatchAuditRow = {
  row_index: number;
  name?: string;
  current_regime?: "old" | "new";
  current_tax?: number;
  unclaimed_savings?: number;
  excess_contribution?: number;
  regime_mismatch?: boolean;
  guardrail?: GuardrailResponse;
  treasury_forecast?: TreasuryForecast;
  // Same classify_row() output the Finance queue uses — never a second,
  // page-specific definition of "is this row clean." See
  // OrchestrationDecision below.
  orchestration?: OrchestrationDecision;
  error?: string;
};

export type BatchAuditResponse = {
  rows: BatchAuditRow[];
  summary: {
    total_rows: number;
    clean_count: number;
    flagged_count: number;
    epfo_cap_exceeded_count: number;
    regime_mismatch_count: number;
    total_excess_contribution: number;
    total_unclaimed_savings: number;
  };
  penalty_scenario: PenaltyScenario;
};

// --- Maker-checker review queue ---

export type SubmissionRowStatus = "pending" | "approved" | "rejected";

// Routing/presentation recommendation only — never an approval. A human
// still clicks Approve on every row via the existing /decide endpoint,
// regardless of route. See orchestration.py for the full routing rule.
export type OrchestrationRoute = "auto_pass_candidate" | "needs_review" | "guardrail_not_run" | "escalate";
export type OrchestrationSeverity = "None" | "Low" | "Medium" | "High";

export type OrchestrationDecision = {
  route: OrchestrationRoute;
  severity: OrchestrationSeverity;
  reasons: string[];
  checked: {
    compliance_rules_evaluated: number;
    compliance_flags_triggered: number;
    guardrail_evaluated: boolean;
    guardrail_checks_failed: number | null;
  };
};

export type FieldChange = {
  field: string;
  before: number | boolean;
  after: number | boolean;
  reason: string;
};

export type RegimeChange = { before: string; after: string; reason: string } | null;

export type SubmissionDiff = {
  has_prior_offer: boolean;
  note: string | null;
  regime_change: RegimeChange;
  field_changes: FieldChange[];
};

export type SubmissionRow = {
  id: number;
  submission_id: number;
  row_index: number;
  employee_name: string | null;
  ctc: number;
  status: SubmissionRowStatus;
  reason: string | null;
  decided_at: string | null;
  decided_by: string | null;
  input: {
    ctc: number; rent_paid: number; city: string; nps_opted: boolean;
    current_structure: StructureDict | null; employee_name: string | null;
    band_min?: number | null; band_max?: number | null;
    bank_account_number?: string | null; ifsc?: string | null; email?: string | null;
    work_location?: string | null;
  };
  computed: OptimizeResponse;
  diff?: SubmissionDiff;
  // null for rows submitted before this feature shipped — every consumer
  // must treat that as "needs_review" (fail-safe direction), never as clean.
  orchestration?: OrchestrationDecision | null;
};

export type Submission = {
  id: number;
  created_at: string;
  source: "single" | "batch";
  submitted_by: string;
  rows: SubmissionRow[];
};

export type CreateSubmissionResponse = {
  submission_id: number;
  inserted_row_ids: number[];
  duplicates: { row_index: number; matches_existing_row_id: number }[];
  row_errors: { row_index: number; error: string }[];
};

export type DecideRowResponse = {
  already_decided: boolean;
  status?: SubmissionRowStatus;
  current_status?: SubmissionRowStatus;
  message: string;
};

// POST /api/submissions/<id>/rows/<row_index>/export — only reachable once a
// row is approved. Two shapes depending on what the row actually was:
// a new hire (current_structure absent) gets a RazorpayX payout payload
// back as JSON; a correction (current_structure present) gets an XLSX file
// back instead, so this type only describes the JSON branch — the XLSX
// branch is handled as a blob download, not parsed against this type.
export type ExportApprovedRowResponse = {
  guardrail?: GuardrailResponse | null;
  idempotency_key_hint: string;
  payouts: CompositeBankAccountPayout[];
  treasury_forecast: TreasuryForecast;
};

// GET /api/razorpayx/balance — the real, live RazorpayX call. Shape mirrors
// RazorpayX's actual GET /v1/banking_balances response (verified live
// against real test-mode credentials on 2026-09-02, not assumed from docs
// alone): amount/available_amount are in PAISE, not rupees — every
// consumer of this type must divide by 100 before displaying or comparing
// against a rupee figure. available_amount (net withdrawable) is the
// figure the treasury gate compares against required funding, not amount
// (gross), since a fund-availability question should use what's actually
// withdrawable right now.
export type RazorpayXBankingBalance = {
  entity: "banking_balance";
  currency: string;
  account_number: string;
  account_type: string;
  bank_name: string | null;
  bank_code: string | null;
  amount: number; // paise
  available_amount: number; // paise
  refreshed_at: number;
};

export type RazorpayXBalanceResponse = {
  configured: boolean;
  live: boolean;
  balance?: { entity: "collection"; count: number; items: RazorpayXBankingBalance[] };
  error?: string;
};
