import type { Metadata } from "next";
import Nav from "@/components/nav";
import FinanceFlow from "@/components/finance/finance-flow";
import RoleGate from "@/components/role-gate";

export const metadata: Metadata = {
  title: "grosslo — Finance",
  description: "Review and decide on compensation structures HR has submitted.",
};

export default function FinancePage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <RoleGate role="finance">
        <FinanceFlow />
      </RoleGate>
    </main>
  );
}
