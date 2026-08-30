import type { Metadata } from "next";
import Nav from "@/components/nav";
import OptimizeFlow from "@/components/optimize/optimize-flow";

export const metadata: Metadata = {
  title: "grosslo — Optimize",
  description: "Structure CTC, check compliance, and export payroll to RazorpayX.",
};

export default function OptimizePage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <OptimizeFlow />
    </main>
  );
}
