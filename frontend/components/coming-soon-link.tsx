"use client";

import { useState } from "react";

export default function ComingSoonLink({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-disabled="true"
        onClick={(e) => e.preventDefault()}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className={`cursor-not-allowed opacity-60 ${className}`}
      >
        {children}
      </button>
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 top-full z-20 mt-2 -translate-x-1/2 whitespace-nowrap rounded-full border border-white/10 bg-black/90 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-neutral-400 shadow-lg backdrop-blur-sm transition-opacity duration-150 ${
          open ? "opacity-100" : "opacity-0"
        }`}
      >
        Coming soon
      </span>
    </span>
  );
}
