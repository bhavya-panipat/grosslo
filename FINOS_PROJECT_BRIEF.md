# FinOS — Project Brief & Build Prompt
**Target: Razorpay AI Buildathon 2026 — Open Track**
**Status as of this doc: tax engine + optimizer core logic built and unit-verified. AI-native layer NOT YET DESIGNED — see Section 5, this is the top blocker.**

---

## 0. Read this first: fit risk

This is an *AI* buildathon. Submissions are judged specifically on the AI-native
component — model/framework choices must be justifiable, and if the project touches
agents, RAG, or LLM orchestration, that's expected to be the centerpiece of the demo.
The Open track does not exempt a submission from this; it only means the *problem*
doesn't have to fit a predefined category.

**As of this doc, FinOS is a deterministic rules engine + grid-search optimizer. It has
no AI/LLM component.** This is a real gap, not a formality — a submission with correct
tax math but no AI layer is not currently competitive for this specific buildathon,
regardless of how good the underlying engineering is. Section 5 below must be resolved
before further build time goes into UI/demo polish.

Separately: the prize is a ₹75,000/month, 6-or-12-month, **in-person Bangalore**
internship starting September. Confirm this is logistically real against your LNMIIT
term schedule before treating "winning" as the actual goal vs. "portfolio artifact."

---

## 1. What FinOS is (current scope)

A CTC (Cost-to-Company) structuring optimizer for Indian salaried employees. Given a
fixed total CTC, it finds the salary component split (basic / HRA / LTA / special
allowance / employer PF / employer NPS) that minimizes the employee's total income tax
liability, and compares the best achievable outcome under the old tax regime vs. the
new tax regime, showing the delta.

**This is NOT:**
- A payroll integration product (no HRMS/API connectivity — out of scope for this
  build entirely, per earlier project pivot)
- A general financial planning tool (no investments, no capital gains, no
  multi-year modeling beyond the regime comparison)
- A compliance auditor (does not check whether an *existing* company payroll setup
  is compliant — only proposes an optimal *new* structure for a given CTC)

**Primary user flow:** user inputs total CTC, rent paid, city tier, and whether
they plan to opt into NPS. Tool outputs: the tax-optimal salary split, under old
regime and under new regime, and the annual rupee saving from picking the better one.

---

## 2. Why this exists / positioning

Originally scoped as a credibility artifact to pitch directly to fintech technical
teams for a hiring/co-founder conversation. Now being adapted as a Razorpay AI
Buildathon Open Track submission — same underlying build, reframed. The core thesis
(good in both contexts): CTC structuring is a well-defined, verifiable, rules-heavy
problem with a real "wow, I didn't know that" moment for non-finance people, and it's
narrow enough to actually get *right* in a short build window — which matters more
for credibility than breadth.

**Known competitive reality:** basic CTC breakup suggestion already exists as a
built-in feature in most Indian payroll SaaS (Zoho Payroll, Keka, greytHR). The
differentiator is NOT "we suggest a breakup" — it's (a) genuine optimization across
the full feasible space rather than a static template, (b) transparent, auditable
logic (documented assumptions, not a black box), and (c) whatever the AI-native layer
ends up being (Section 5).

---

## 3. What's built and verified so far

### 3.1 Tax engine (`tax_engine.py`)
- Progressive slab tax calculation, both regimes, FY 2025-26 / FY 2026-27
  (confirmed via live search: Budget 2026 made no changes to slabs, standard
  deduction, or rebate for either regime — these numbers are stable across both
  FYs as of Aug 2026)
- New regime slabs: nil to ₹4L, then 5/10/15/20/25/30% in ₹4L bands to ₹24L+
- Old regime slabs: nil to ₹2.5L, 5% (2.5-5L), 20% (5-10L), 30% (>10L)
- Standard deduction: ₹75,000 (new) / ₹50,000 (old)
- Section 87A rebate: taxable income ≤ ₹12L → zero tax (new) / ≤ ₹5L (old)
- **Marginal relief logic implemented and validated against the government's own
  worked example** (₹61,500 slab tax → ₹10,000 payable at ~₹12.1L taxable income,
  exact match)
- HRA exemption: min(HRA received, rent − 10% of basic, 50%/40% of basic for
  metro/non-metro)
- Employer NPS (80CCD(2)): 10% of basic cap (old regime) / 14% of basic cap (new
  regime) — the 14% figure is the post-Budget-2024 raised limit, confirmed correct
  via search (not the older 10% figure that appears in stale sources)
- Employer PF: 12% of basic
- Cess: flat 4% on tax after rebate/relief, both regimes
- Verified: gross salary up to ₹12.75L → zero tax for salaried individual under
  new regime (matches public guidance), confirmed via engine test after
  correcting a test-setup error (see 3.3 below — worth reusing in "what broke"
  narrative)

### 3.2 Optimizer (`optimizer.py`)
- Exhaustive grid search, not a general-purpose solver (scipy etc. rejected —
  reasoning: the tax function has kinks at slab boundaries and a discrete
  old-vs-new regime branch, making it piecewise/non-convex; grid search is
  provably exhaustive over the discretized space at this scale, sub-second
  runtime, and fully auditable by a reviewer — a defensible engineering choice
  to be able to explain if asked)
- New regime: search space collapses to basic_pct only, since HRA/LTA get zero
  exemption under new regime and are tax-identical to special allowance — a
  proven simplification, not a shortcut (worth stating explicitly if probed)
- Old regime: full grid over (basic_pct, LTA amount, HRA-vs-special-allowance
  split within remaining CTC)
- Output: best structure under old regime, best under new regime, recommended
  winner, and the rupee delta

### 3.3 Testing notes (raw material for the "what broke" submission requirement)
- Caught and removed a broken/duplicate draft function (`_apply_87a_rebate`
  early version) left over from an editing false-start before it reached
  production logic — a real example of catching your own mistake via
  code review, not an invented anecdote
- Caught a test-design error (fed the engine *taxable* income where the
  ₹12.75L "salaried tax-free" claim actually refers to *gross* salary before
  standard deduction) — engine was correct, test was wrong; a good concrete
  example of "verify your own verification," which is a stronger story than
  "I found a bug" for a judged demo
- Optimizer initially had an unbounded upper end on basic_pct; caught before
  building further that a pure tax-minimizing search with no ceiling would
  push basic toward unrealistic levels (since employer PF/NPS shelter more tax
  as basic grows) — added a 50% ceiling as an explicit, documented assumption
  rather than letting the "optimal" output be something no real company would
  implement

---

## 4. Full list of assumptions made (consolidate for docs/demo — state these
explicitly, don't let a judge/reviewer discover them by probing)

| # | Assumption | Why | Risk if wrong |
|---|---|---|---|
| 1 | Basic salary floor = 40% of CTC | Market convention, not statutory | Low — widely used norm |
| 2 | Basic salary ceiling = 50% of CTC | Added to stop unconstrained tax-minimization from producing unrealistic structures (more basic → more tax-sheltered PF/NPS space) | Medium — arbitrary number, should be stated as a design tradeoff, not fact |
| 3 | LTA exemption = 70% of claimed LTA amount (not 100%) | Real LTA exemption depends on actual travel, valid bills, economy-airfare cap, and a twice-per-4-year block limit that a structuring tool can't know in advance | Medium — still an estimate, not certain |
| 4 | LTA search ceiling = 10% of CTC | Realistic company policy convention | Low-medium |
| 5 | Employer PF computed on full basic (not capped at ₹15,000/month statutory minimum wage ceiling) | Matches common private-sector practice (voluntary higher PF) | Medium — some companies do cap at statutory minimum; toggle exists in code but defaults to uncapped |
| 6 | Surcharge (income > ₹50L) NOT modeled | Out of scope for target demo audience (early-to-mid career hires) | Low for target users, but must be stated as a hard scope limit, not silently absent |
| 7 | **Aggregate employer PF + NPS + superannuation contribution exceeding ₹7.5L/year is a taxable perquisite u/s 17(2)(vii) — NOT currently modeled** | Missed in build so far | **Medium-high at higher CTC bands where this could actually bind — needs a decision: model it, or explicitly scope out with a stated CTC ceiling for tool validity** |
| 8 | Resident individual, age < 60, no other income sources, no capital gains, single tax filer | Keeps scope tractable | Low for target demo, must be stated |
| 9 | Grid search step sizes (basic: 2.5%, LTA: 2% of CTC, HRA fraction: 5%) | Balance between exhaustiveness and runtime; runtime is sub-second at this resolution so finer steps are cheap if precision matters more | Low — easy to tighten, no design risk |

**Action needed:** Assumption #7 is the one gap in this list that isn't just a
documented scope limit — it's a real correctness edge case that could matter at
higher CTC bands your own optimizer might recommend (since it favors pushing basic
toward the 50% ceiling). Decide: model it properly, or add a hard CTC ceiling to the
tool's stated valid range (e.g., "not validated above ₹40L CTC") so the gap can't be
triggered in a demo.

---

## 5. Open questions — must be answered before continuing the build

### 5.1 AI-native layer (BLOCKING — highest priority, unresolved)
This is a rules engine right now, and the buildathon is an *AI* buildathon judged
specifically on this dimension. Candidate directions, none yet chosen:
- **Document extraction agent**: user uploads a messy offer letter / existing CTC
  breakup (PDF/image), an LLM extracts structured salary components, feeds into
  the existing deterministic engine. Real, defensible AI use — LLM does what it's
  good at (unstructured → structured), deterministic engine does what it's good
  at (tax math), avoids the "LLM doing arithmetic" anti-pattern.
- **Explainer/reasoning agent**: after the optimizer produces a result, an LLM
  generates a plain-language explanation of *why* this split is optimal, tailored
  to the user's specific numbers — turns a table of numbers into something a
  non-technical founder actually understands.
- **Conversational structuring assistant**: chat interface where the user
  describes their situation in natural language ("I make 18L, pay 40k rent in
  Bangalore, my company is flexible on structure") and an agent extracts the
  structured inputs, calls the engine, and responds conversationally — heavier
  build, more clearly "agentic," higher risk of scope overrun before deadline.
- **Anomaly/compliance flagging agent**: given an *existing* company payroll
  structure (not just building a new one), an LLM-assisted agent flags likely
  compliance gaps or inefficiencies — this reintroduces some of the "auditor"
  scope explicitly cut earlier; reconsider only if it strengthens the AI-native
  story enough to be worth the scope creep.

**This needs to be picked, not deferred, before further build time goes into
anything else** — it determines the architecture, not just a feature bolted on
at the end.

### 5.2 Logistics reality check
Is in-person Bangalore, starting September, for 6-12 months, actually compatible
with your LNMIIT term schedule (graduating 2028)? If not, is this still worth
building for (portfolio/credibility value) even if you wouldn't take the internship
if offered? Answer honestly before optimizing further decisions around "winning."

### 5.3 Assumption #7 (aggregate employer contribution perquisite tax)
Model it, or add a hard stated CTC ceiling to keep it out of scope? See Section 4.

### 5.4 Demo format
5-minute pitch video + public repo + architecture doc are required. What's the
actual interface — a deployed web app, a CLI, a notebook walkthrough? This decides
build priority for the remaining time: if it's a web app, real time needs to go to
UI; if it's a notebook/CLI demo, that time goes to the AI layer and edge-case
coverage instead. Don't default to "make it a polished web app" without deciding
this deliberately — polish that isn't being judged is wasted build time.

### 5.5 Test coverage
Core tax logic is spot-checked, not exhaustively tested. Before demo: build an
actual test suite covering — HRA metro vs non-metro, PF statutory-ceiling toggle
on vs off, the old-vs-new crossover point across a range of CTC/rent combinations
(useful for the demo narrative — show *where* the crossover happens, not just one
static example), and NPS opted vs not-opted.

### 5.6 "What broke" narrative
Buildathon explicitly asks what broke and how it was solved. Section 3.3 has three
real candidates already. Decide which becomes the headline story for the pitch
video — the marginal relief validation catch is probably the strongest (shows
rigor: caught your own test being wrong, not just a code bug).

---

## 6. Immediate next step
Resolve 5.1 (AI-native layer choice) before writing another line of engine code.
Everything else in this doc can proceed in parallel once that's picked.
