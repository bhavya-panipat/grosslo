import type { Metadata } from "next";
import Nav from "@/components/nav";
import BatchFlow from "@/components/optimize/batch-flow";

export const metadata: Metadata = {
  title: "grosslo — Audit",
  description: "Audit existing payroll structures in bulk for compliance and unclaimed savings.",
};

export default function BatchPage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <BatchFlow />
    </main>
  );
}
