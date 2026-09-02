// Shared by the batch Executive Summary card (/optimize/batch) and the
// live Treasury Gate (/finance) — same underlying question ("what does
// this row-set cost to fund"), asked over two different row-sets (every
// processed row vs. pending-only). One implementation, two call sites, so
// the two banners can never silently disagree about what the same
// treasury_forecast.total_capital_outlay figure means.
import type { TreasuryForecast } from "@/lib/api-types";

export function totalCapitalOutlay(rows: { treasury_forecast?: TreasuryForecast }[]): number {
  return rows.reduce((sum, r) => sum + (r.treasury_forecast?.total_capital_outlay ?? 0), 0);
}
