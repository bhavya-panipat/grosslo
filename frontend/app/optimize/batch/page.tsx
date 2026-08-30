import type { Metadata } from "next";
import Nav from "@/components/nav";
import BatchFlow from "@/components/optimize/batch-flow";

export const metadata: Metadata = {
  title: "grosslo — Batch",
  description: "Process new hire offers and audit existing payroll structures in batch.",
};

export default function BatchPage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <BatchFlow />
    </main>
  );
}
