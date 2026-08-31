import type { Metadata } from "next";
import Nav from "@/components/nav";
import HrFlow from "@/components/hr/hr-flow";

export const metadata: Metadata = {
  title: "grosslo — HR",
  description: "Submit a compensation structure for Finance review.",
};

export default function HrPage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <HrFlow />
    </main>
  );
}
