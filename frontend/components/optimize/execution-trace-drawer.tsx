"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Terminal } from "lucide-react";
import type { TraceStage } from "@/lib/api-types";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = () => setReduced(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

export default function ExecutionTraceDrawer({ trace }: { trace: TraceStage[] }) {
  const [open, setOpen] = useState(true);
  const reducedMotion = useReducedMotion();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: reducedMotion ? "auto" : "smooth" });
    }
  }, [trace.length, open, reducedMotion]);

  if (trace.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-surface shadow-inner-edge">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-6 py-4 text-left"
      >
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-gold-bright" />
          <span className="font-display text-sm font-semibold text-white">Execution trace</span>
          <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[10px] text-neutral-500">
            {trace.length} stage{trace.length === 1 ? "" : "s"}
          </span>
        </div>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown className="h-4 w-4 text-neutral-500" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            <div
              ref={scrollRef}
              className="max-h-64 space-y-2 overflow-y-auto border-t border-white/[0.06] bg-black/40 px-6 py-4 font-mono text-xs leading-relaxed"
            >
              <AnimatePresence initial={!reducedMotion}>
                {trace.map((line, i) => (
                  <motion.div
                    key={line.stage}
                    initial={reducedMotion ? false : { opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: reducedMotion ? 0 : i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                    className="flex gap-2"
                  >
                    <span className="shrink-0 text-gold-bright">
                      [<span className="drop-shadow-[0_0_4px_rgba(243,186,47,0.5)]">{line.stage}</span>]
                    </span>
                    <span className="text-neutral-400">{line.message}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
