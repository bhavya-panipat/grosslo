import type { Metadata } from "next";
import Nav from "@/components/nav";
import ForecastFlow from "@/components/forecast/forecast-flow";

export const metadata: Metadata = {
  title: "grosslo — Forecast",
  description: "Forecast what planned hires will cost, month by month: take-home, TDS, EPFO, NPS and professional tax.",
};

export default function ForecastPage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <ForecastFlow />
    </main>
  );
}
