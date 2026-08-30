"use client";

import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import RazorpayXExportModal from "@/components/optimize/razorpayx-export-modal";
import type { FormState } from "@/components/optimize/manual-entry-card";

export default function RazorpayXExportTrigger({ form }: { form: FormState }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 self-start rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98]"
      >
        Export to RazorpayX
        <ArrowUpRight className="h-4 w-4" />
      </button>
      {open && <RazorpayXExportModal form={form} onClose={() => setOpen(false)} />}
    </>
  );
}
