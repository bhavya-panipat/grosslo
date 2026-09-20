import type { Metadata } from "next";
import Nav from "@/components/nav";
import HrFlow from "@/components/hr/hr-flow";
import PermissionGate from "@/components/permission-gate";

export const metadata: Metadata = {
  title: "grosslo — HR",
  description: "Submit a compensation structure for Finance review.",
};

export default function HrPage() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <PermissionGate permission="view_queue" label="HR">
        <HrFlow />
      </PermissionGate>
    </main>
  );
}
