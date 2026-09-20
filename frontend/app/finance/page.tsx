import type { Metadata } from "next";
import Nav from "@/components/nav";
import FinanceFlow from "@/components/finance/finance-flow";
import PermissionGate from "@/components/permission-gate";

export const metadata: Metadata = {
  title: "grosslo — Finance",
  description: "Review and decide on compensation structures HR has submitted.",
};

export default function FinancePage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <PermissionGate permission="decide_row" label="Finance">
        <FinanceFlow />
      </PermissionGate>
    </main>
  );
}
