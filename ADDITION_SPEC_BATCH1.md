# Consolidated addition spec, batch 1 — as revised after review

The spec as proposed, with every item's status after being checked against the
code. Recorded here rather than left in a chat log, because five of its six
tiers changed and the reasons are worth keeping.

The hard constraint is unchanged and binds everything below: **no live dispatch,
no automated statutory deposit routing, no direct integration with government
filing systems, no change to the maker-checker gate, no bypass of employee
consent requirements that do not exist yet.**

**Premise correction:** the spec positioned itself against "2.4 first batch
complete (second batch in design/implementation)". Phase 2.4b is complete and
merged (`49b1ddc`) — 17 claims across five files, two with verified citations.

---

## Tier 1 — REPLACED

**As proposed:** move the numeric guard and candidate-rule gate onto Agent SDK
hooks.

**Why it could not be built:** this codebase uses the plain `anthropic` Messages
SDK, has no agent, no tool loop, and no hook point. More fundamentally, **the
numeric guard is not an interception and cannot be expressed as one** — Python
computes every figure before any LLM is invoked, so there is no moment at which
a model proposes a number that a hook could reject. Building one would have
required first *creating* the capability the guard exists to make impossible,
then policing it after the fact: strictly weaker than what exists.

The RLS analogy does not carry either. RLS is a second check on an operation
that happens regardless; this would have been inventing a new operation in order
to guard it.

**Replaced by:** `OUTPUT_BOUNDARY_DESIGN.md`, shipped. A test that walks every
response and fails on any number in model-authored text not traceable to a
deterministic field. Same goal, genuinely independent of call-site discipline,
no new dependency and no new risk surface.

## Tier 2.1 — unchanged, not yet built

Forward-looking workforce cost modelling. Pure computation over the existing
optimizer and treasury math. Nothing found against it.

## Tier 2.2 — REMOVED from this spec

**As proposed:** a compliance obligation calendar driven from the claim
inventory's recorded instrument and effective-date data.

**The spec anticipated a granularity problem. The actual problem is bigger.**
`Claim` has 18 fields and no date field except `citation_checked_on` and
`reviewed_on`, both about *verification activity*. Effective dates appear as
prose in 2 of 17 claims.

The inventory models **what the law says** — a rate, a threshold, a ceiling. A
PT filing date or PF challan due date is **when you must act**: a procedural
obligation, and not a value any constant in this codebase holds. There is
nothing to derive a calendar from.

So this is not a missing field but a **missing claim category**, with its own
evidence model. Pulled out entirely and treated as a future item, same as Tier
6's deferred work.

## Tier 2.3 — REVISED, not yet built

Compensation health score. Two things to state in whatever spec carries it:

- **The claim-inventory verification component is GLOBAL by explicit decision**
  (`LEGAL_CLAIM_INVENTORY_DESIGN.md` §6 — a statutory number is true or false
  independently of which company is asking). It therefore contributes an
  identical term to every tenant's score and can never differentiate two
  companies. That is a correct consequence of a deliberate decision, and it
  should read as a design choice rather than an unexamined artifact.
- **"Over time" must be built from `submissions.created_at`.** There is no
  metrics time series; a trend means replaying stored submissions.

## Tier 3.1 — SPLIT

**Cost tracking: proceed.** `max_tokens` is set at six call sites and no usage
is captured anywhere; the SDK already returns `response.usage`. Recording it is
additive, changes no behaviour, and needs no new dependency — plumbing-only, in
the same sense this project has used throughout.

**Multi-turn conversation: not proceeding, flagged back.** `answer_query` is
stateless and single-turn — it receives an already-computed result as context
and returns one answer. There is no hand-rolled state to migrate, and no tools
to restrict. Adding multi-turn would be **a capability change**, which the tier
explicitly said it was not. If it is wanted it needs its own decision and its
own design doc; it is not being decided silently either way.

## Tier 4.1 — REFRAMED, not yet built

**As proposed:** deliver the CA review packet by email or Slack, described as
serving "the CA-engagement task that's already the longest-pole item".

**That characterisation was wrong, and the correction matters more than the
feature.** The blocker has never been delivery mechanics. **No reviewer has been
identified at all** — `docs/PROJECT_STATUS.md` and the packet's own design both
record that the clock is on *engaging* a reviewer, not on reviewing. Building
delivery produces a pipe to an address nobody has, and *"whichever is realistic
given who the actual reviewer will be"* is unanswerable for the same reason.

Reframed honestly as **useful once a reviewer exists**. It is not progress on
the bottleneck, and a real code deliverable must not create the appearance of
movement on something it does not touch.

## Tier 5.1 — SCOPED DOWN

**As proposed:** an audit-trail dashboard including "how many candidate rules
were reviewed and by whom" and "how fast are unverified claims being resolved".

**Neither is an application event.** The audit log records money-adjacent
decisions — structure computed, compliance/guardrail verdict, payload generated.
Rule review is a *source edit*: `COMPLIANCE_BREADTH_DESIGN.md` §6 resolved that
`reviewed_by` lives in code and **the diff is the audit trail**. Claim
verification is likewise a commit to `legal_claims.py`.

That data is in **git history**. Writing review events into the audit log as
well would create exactly the second source of truth that decision was made to
prevent — the spec's own rule, caught by the spec's own principle.

**Scoped to what the log holds:** compliance and guardrail trend data,
computation activity. If the two review questions are still wanted, answer them
by querying git history directly and say so explicitly. No new write path.

## Tier 6 — unchanged

Cross-tenant benchmarking and the multi-client CA-firm dashboard both stay out,
each needing its own design doc first. Reasoned correctly as proposed, including
the identification of the CA-firm dashboard — a role legitimately spanning
multiple tenants' **raw** data — as the more sensitive of the two.

## Tracked follow-up, so it does not become permanent by never being anyone's task

**A response section that omits `ai_backed` is invisible to the output-boundary
check.** That flag is load-bearing by design (`OUTPUT_BOUNDARY_DESIGN.md` §3.2),
which is exactly why the gap it opens deserves its own attention rather than
being absorbed into a design already doing real work.

## Excluded, carried forward unchanged

Automated statutory deposit routing or payout execution; direct integration with
Income Tax e-filing, TRACES or EPFO portals; `n8n` or any new third-party
orchestration platform; a fabricated confidence-score threshold; Claude Managed
Agents as a fix for the legal-change monitoring problem specifically; and more
statutory candidate rules beyond what is queued, which stay blocked until the
citation-verification loop is proven end-to-end on R5 and the HRA candidate.
