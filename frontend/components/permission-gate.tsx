"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, LogOut, Loader2, KeyRound } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { Permission, SessionResponse, LoginResponse, BootstrapRequiredResponse, BootstrapResponse } from "@/lib/api-types";

// Replaces role-gate.tsx (LOGIN_FIX_DESIGN.md). The old gate checked
// session.role === role against a session shape that no longer exists —
// GET /api/auth/session now reports {user_id, tenant_id, roles, permissions,
// display_name}, with no `role` field at all, so that check could never pass
// for a real, current login. This gates on `permission` membership in the
// server-derived `permissions` list instead — the server remains the only
// enforcement (every route keeps its own @require_permission); this only
// decides what the page shows.
//
// `permission` is typed as the real Permission union, not string: a typo
// like "decide-row" then fails at build instead of compiling into a check
// that silently denies everyone.
type Props = { permission: Permission; label: string; children: React.ReactNode };

type Session = SessionResponse | null;

// §3.4: bootstrap is a secondary path under the login form, not a second
// login. It only ever advances past step 1 on a real bootstrap_required
// response from the server — the page cannot know in advance whether a
// tenant is still unset-up (an endpoint that told it so would disclose
// tenant state to anonymous callers), so the backend's own answer is the
// only source of truth for whether step 2 is reachable at all.
type BootstrapStage = "closed" | "code" | "owner";

export default function PermissionGate({ permission, label, children }: Props) {
  const [session, setSession] = useState<Session>(null);
  const [checked, setChecked] = useState(false);
  // Distinct from loginError: this is "the session check itself failed"
  // (backend down, proxy misconfigured, network blip), not "a login
  // attempt was rejected". Without it, a failed /api/auth/session fetch
  // rendered a permanently blank page — worse than the old gate, which
  // failed closed to a visible form. Set alongside the signed-out session
  // shape, not instead of it, so the page still shows the sign-in form
  // underneath the notice rather than nothing at all.
  const [sessionFetchError, setSessionFetchError] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);

  const [bootstrapStage, setBootstrapStage] = useState<BootstrapStage>("closed");
  const [role, setRole] = useState<"hr" | "finance">("hr");
  const [code, setCode] = useState("");
  const [bootstrapTenant, setBootstrapTenant] = useState<{ display_name: string } | null>(null);
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [bootstrapBusy, setBootstrapBusy] = useState(false);

  const refreshSession = () =>
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((d: SessionResponse) => {
        setSession(d);
        setSessionFetchError(false);
      })
      .catch(() => {
        // Signed-out shape, not null: null is reserved for "haven't checked
        // yet" below, so the page still renders the sign-in form rather
        // than staying blank while the notice explains why it's there.
        setSession({ user_id: null, tenant_id: null, roles: [], permissions: [], display_name: null });
        setSessionFetchError(true);
      })
      .finally(() => setChecked(true));

  useEffect(() => {
    refreshSession();
  }, []);

  const handleLogin = () => {
    setLoginBusy(true);
    setLoginError(null);
    fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.error || "Sign-in failed.");
        return body as LoginResponse;
      })
      // Re-reads the session rather than trusting the login response to
      // decide the gate — the response confirms who logged in, but
      // `permissions` is this component's only source of truth for what
      // they may see.
      .then(() => refreshSession())
      .then(() => {
        setPassword("");
      })
      .catch((e: Error) => setLoginError(e.message))
      .finally(() => setLoginBusy(false));
  };

  const handleLogout = () => {
    // Re-reads the session rather than assuming success locally — the same
    // reason handleLogin does — so a logout that failed server-side doesn't
    // leave the UI claiming signed-out while the cookie is still live.
    fetch("/api/auth/logout", { method: "POST" })
      .then(() => refreshSession())
      .finally(() => {
        setEmail("");
        setPassword("");
      });
  };

  const handleBootstrapCode = () => {
    setBootstrapBusy(true);
    setBootstrapError(null);
    fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, code: code.trim() }),
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.error || "That code doesn't match — try again.");
        return body as BootstrapRequiredResponse;
      })
      .then((body) => {
        setBootstrapTenant(body.tenant);
        setBootstrapStage("owner");
      })
      .catch((e: Error) => setBootstrapError(e.message))
      .finally(() => setBootstrapBusy(false));
  };

  const handleBootstrapOwner = () => {
    setBootstrapBusy(true);
    setBootstrapError(null);
    fetch("/api/auth/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ownerEmail.trim(), display_name: ownerName.trim(), password: ownerPassword }),
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.error || "Couldn't create the account.");
        return body as BootstrapResponse;
      })
      .then(() => refreshSession())
      .then(() => setBootstrapStage("closed"))
      .catch((e: Error) => setBootstrapError(e.message))
      .finally(() => setBootstrapBusy(false));
  };

  // Avoids a flash of the login form before the first /api/auth/session
  // answer — matches the old gate's behaviour for this state exactly.
  if (!checked || session === null) return null;

  const signedIn = session.user_id !== null;
  const permitted = session.permissions.includes(permission);

  if (signedIn && permitted) {
    return (
      <div className="relative">
        {children}
        <button
          onClick={handleLogout}
          className="fixed bottom-5 right-5 z-50 flex items-center gap-1.5 rounded-full border border-white/10 bg-black/70 px-3.5 py-2 text-xs text-neutral-400 backdrop-blur-md transition-colors hover:border-white/20 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" /> Signed in as {session.display_name} · Sign out
        </button>
      </div>
    );
  }

  // Signed in but lacking the permission this page needs. Never the login
  // form here — showing a form to someone already signed in reads as "your
  // password was wrong," which isn't what happened.
  if (signedIn && !permitted) {
    return (
      <section className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border border-gold/30 bg-gold/[0.08]">
          <Lock className="h-5 w-5 text-gold-bright" />
        </div>
        <h1 className="mt-4 font-display text-xl font-semibold text-white">Not available for this account</h1>
        <p className="mt-2 text-sm text-neutral-500">
          Signed in as {session.display_name}. This account can&apos;t use {label}.
        </p>
        <button
          onClick={handleLogout}
          className="mt-6 flex items-center gap-1.5 rounded-full border border-white/10 px-3.5 py-2 text-xs text-neutral-400 transition-colors hover:border-white/20 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </section>
    );
  }

  return (
    <section className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6">
      <AnimatePresence mode="wait">
        {bootstrapStage === "closed" ? (
          <motion.div
            key="login"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="w-full"
          >
            <CardShell className="p-8 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border border-gold/30 bg-gold/[0.08]">
                <Lock className="h-5 w-5 text-gold-bright" />
              </div>
              <h1 className="mt-4 font-display text-xl font-semibold text-white">Sign in</h1>
              <p className="mt-2 text-sm text-neutral-500">Sign in to continue to {label}.</p>
              {sessionFetchError && (
                <p className="mt-3 text-xs text-red-400/80">
                  Couldn&apos;t reach the server to check your session — you can still try signing in.
                </p>
              )}

              <div className="mt-6 flex flex-col gap-3">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setLoginError(null);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  placeholder="Email"
                  className="rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
                  autoFocus
                />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setLoginError(null);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  placeholder="Password"
                  className={`rounded-lg border bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:outline-none ${
                    loginError ? "border-red-400/50" : "border-white/10 focus:border-gold-bright/50"
                  }`}
                />
                {/* Shown verbatim — the server's messages are already generic
                    by design (enumeration-safe), so the page must not add
                    detail the server withheld. */}
                {loginError && <p className="text-xs text-red-400/80">{loginError}</p>}
                <button
                  onClick={handleLogin}
                  disabled={!email.trim() || !password || loginBusy}
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {loginBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Sign in
                </button>
              </div>

              <button
                onClick={() => setBootstrapStage("code")}
                className="mt-6 flex w-full items-center justify-center gap-1.5 text-xs text-neutral-500 transition-colors hover:text-neutral-300"
              >
                <KeyRound className="h-3 w-3" /> Setting up this workspace for the first time?
              </button>
            </CardShell>
          </motion.div>
        ) : (
          <motion.div
            key="bootstrap"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="w-full"
          >
            <CardShell className="p-8 text-center">
              {bootstrapStage === "code" ? (
                <>
                  <h1 className="font-display text-xl font-semibold text-white">Workspace setup</h1>
                  <p className="mt-2 text-sm text-neutral-500">
                    Enter the access code your workspace was set up with.
                  </p>
                  <div className="mt-6 flex flex-col gap-3">
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value as "hr" | "finance")}
                      className="rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
                    >
                      <option value="hr">HR</option>
                      <option value="finance">Finance</option>
                    </select>
                    <input
                      type="password"
                      value={code}
                      onChange={(e) => {
                        setCode(e.target.value);
                        setBootstrapError(null);
                      }}
                      onKeyDown={(e) => e.key === "Enter" && handleBootstrapCode()}
                      placeholder="Access code"
                      className={`rounded-lg border bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:outline-none ${
                        bootstrapError ? "border-red-400/50" : "border-white/10 focus:border-gold-bright/50"
                      }`}
                      autoFocus
                    />
                    {bootstrapError && <p className="text-xs text-red-400/80">{bootstrapError}</p>}
                    <button
                      onClick={handleBootstrapCode}
                      disabled={!code.trim() || bootstrapBusy}
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {bootstrapBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Continue
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <h1 className="font-display text-xl font-semibold text-white">
                    Create the owner account
                  </h1>
                  <p className="mt-2 text-sm text-neutral-500">
                    {bootstrapTenant?.display_name}&apos;s first account. The access code stops working
                    once this is created.
                  </p>
                  <div className="mt-6 flex flex-col gap-3">
                    <input
                      type="email"
                      value={ownerEmail}
                      onChange={(e) => {
                        setOwnerEmail(e.target.value);
                        setBootstrapError(null);
                      }}
                      placeholder="Email"
                      className="rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
                      autoFocus
                    />
                    <input
                      type="text"
                      value={ownerName}
                      onChange={(e) => {
                        setOwnerName(e.target.value);
                        setBootstrapError(null);
                      }}
                      placeholder="Your name"
                      className="rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:border-gold-bright/50 focus:outline-none"
                    />
                    <input
                      type="password"
                      value={ownerPassword}
                      onChange={(e) => {
                        setOwnerPassword(e.target.value);
                        setBootstrapError(null);
                      }}
                      onKeyDown={(e) => e.key === "Enter" && handleBootstrapOwner()}
                      placeholder="Password (at least 8 characters)"
                      className={`rounded-lg border bg-black/40 px-3 py-2.5 text-center text-sm text-neutral-200 focus:outline-none ${
                        bootstrapError ? "border-red-400/50" : "border-white/10 focus:border-gold-bright/50"
                      }`}
                    />
                    {/* Client-side check for a friendlier message — the
                        server's own check (>= 8 chars) is the real one and
                        is what the request above is actually gated on. */}
                    {ownerPassword.length > 0 && ownerPassword.length < 8 && (
                      <p className="text-xs text-red-400/80">Password must be at least 8 characters.</p>
                    )}
                    {bootstrapError && <p className="text-xs text-red-400/80">{bootstrapError}</p>}
                    <button
                      onClick={handleBootstrapOwner}
                      disabled={
                        !ownerEmail.trim() || !ownerName.trim() || ownerPassword.length < 8 || bootstrapBusy
                      }
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-black shadow-bevel transition-transform duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {bootstrapBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Create account
                    </button>
                  </div>
                </>
              )}

              <button
                onClick={() => {
                  setBootstrapStage("closed");
                  setBootstrapError(null);
                }}
                className="mt-6 text-xs text-neutral-500 transition-colors hover:text-neutral-300"
              >
                Back to sign in
              </button>
            </CardShell>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
