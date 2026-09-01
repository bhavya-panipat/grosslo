"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, LogOut, ShieldAlert } from "lucide-react";
import CardShell from "@/components/card-shell";

// A simulated access gate — deliberately NOT real authentication. There's
// no server-side session, no hashed credential, no user record anywhere;
// the "password" ships in this same client bundle and is shown on screen
// as a hint. This exists so a demo can show what role-gated access would
// *feel* like from the Finance/HR side, not to actually restrict who can
// reach these pages — anyone who opens devtools or reads this file has
// the real access this gate provides. Matches this codebase's standing
// rule: real security infrastructure was deliberately not built for this
// submission (see README.md's security-posture section) — this is a UX
// simulation of that gap, not a fix for it.
const ROLE_CONFIG = {
  hr: { label: "HR", code: "HR2026", storageKey: "grosslo_access_hr" },
  finance: { label: "Finance", code: "FINANCE2026", storageKey: "grosslo_access_finance" },
} as const;

type Role = keyof typeof ROLE_CONFIG;

export default function RoleGate({ role, children }: { role: Role; children: React.ReactNode }) {
  const config = ROLE_CONFIG[role];
  const [unlocked, setUnlocked] = useState(false);
  const [checked, setChecked] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState(false);

  useEffect(() => {
    setUnlocked(sessionStorage.getItem(config.storageKey) === "true");
    setChecked(true);
  }, [config.storageKey]);

  const handleSubmit = () => {
    if (input.trim().toUpperCase() === config.code) {
      sessionStorage.setItem(config.storageKey, "true");
      setUnlocked(true);
      setError(false);
    } else {
      setError(true);
    }
  };

  const handleLock = () => {
    sessionStorage.removeItem(config.storageKey);
    setUnlocked(false);
    setInput("");
  };

  // Avoids a flash of the gate before sessionStorage has been read once.
  if (!checked) return null;

  if (unlocked) {
    return (
      <div className="relative">
        {children}
        <button
          onClick={handleLock}
          className="fixed bottom-5 right-5 z-50 flex items-center gap-1.5 rounded-full border border-white/10 bg-black/70 px-3.5 py-2 text-xs text-neutral-400 backdrop-blur-md transition-colors hover:border-white/20 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" /> Lock {config.label} access
        </button>
      </div>
    );
  }

  return (
    <section className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6">
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="w-full"
        >
          <CardShell className="p-8 text-center">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border border-gold/30 bg-gold/[0.08]">
              <Lock className="h-5 w-5 text-gold-bright" />
            </div>
            <h1 className="mt-4 font-display text-xl font-semibold text-white">
              {config.label} access
            </h1>
            <p className="mt-2 text-sm text-neutral-500">
              Enter the {config.label} access code to continue.
            </p>

            <div className="mt-6 flex flex-col gap-3">
              <input
                type="password"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  setError(false);
                }}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="Access code"
                className={`rounded-lg border bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:outline-none ${
                  error ? "border-red-400/50" : "border-white/10 focus:border-gold-bright/50"
                }`}
                autoFocus
              />
              {error && (
                <p className="text-xs text-red-400/80">That code doesn&apos;t match — try again.</p>
              )}
              <button
                onClick={handleSubmit}
                disabled={!input.trim()}
                className="rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
              >
                Enter
              </button>
            </div>

            <div className="mt-6 flex items-start gap-2 rounded-lg border border-white/[0.06] bg-black/30 p-3 text-left">
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-500" />
              <p className="text-[11px] leading-relaxed text-neutral-500">
                Simulated access only — not real authentication. There&apos;s no server-side session or
                account behind this, the code lives in this page&apos;s own client code, and it&apos;s
                shown below on purpose rather than hidden, the same way this app&apos;s demo bank
                details are always obviously fake. Demo code:{" "}
                <span className="font-mono text-neutral-400">{config.code}</span>
              </p>
            </div>
          </CardShell>
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
