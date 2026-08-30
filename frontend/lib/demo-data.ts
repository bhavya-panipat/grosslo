// Fixed demo inputs used to populate the landing page with real optimizer
// output (not fabricated figures) — same parameters the legacy static
// frontend used for its hero HUD: ₹18L CTC, ₹4L rent, metro, NPS opted in.
export const DEMO_PAYLOAD = {
  ctc: 1_800_000,
  rent_paid: 400_000,
  city: "metro",
  nps_opted: true,
};

export type {
  OptimizeResponse,
  SensitivityPoint,
  SensitivityResponse,
  HealthResponse,
} from "./api-types";
