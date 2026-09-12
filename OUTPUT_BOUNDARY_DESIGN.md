# Output-boundary numeric assertion — design

Replaces Tier 1 of the consolidated addition spec. **The goal Tier 1 stated is
right — a second, independent enforcement layer for the numeric guard, the same
shape of improvement RLS was over query-layer-only tenant isolation. The
mechanism it proposed is not available, and building it would have been a
regression.** That analysis is in the spec review; this document designs the
thing that achieves the goal.

## 1. What the guard is today, measured

`ai_layer._numbers_ungrounded(text, allowed_numbers, skip_below)`:

- extracts numbers from a candidate LLM string,
- rejects any that is not within tolerance `1` of some member of
  `allowed_numbers`,
- ignores numbers below `skip_below` — `100` for explanation and query text
  (prose filler like "2-4 sentences"), `0` for compliance and guardrail text,
  because a percentage like `50%` is exactly the safety-critical figure there.

It is called **per LLM call site**. There are six `messages.create` sites in
`ai_layer.py`. Each one supplies its own `allowed_numbers` and its own
`skip_below`.

**That is the whole of the enforcement, and it is correct today** — tested,
sabotage-proven, and the reason no LLM figure has ever reached a response.

## 2. Why a boundary check is genuinely a second layer

The existing guard has three failure modes, and they are failures *of a call
site*, not of the checking function:

1. **An incomplete `allowed_numbers` set.** The guard faithfully checks against
   whatever it was handed.
2. **A `skip_below` set too high.** A real figure below the threshold is exempt
   by construction.
3. **A NEW call site that does not call the guard at all.** This is the one that
   matters most, and it is the exact analogue of the tenancy case RLS covered: a
   query that forgets to filter. Today nothing prevents a seventh
   `messages.create` from being added with its output placed straight into a
   response.

**A check at the output boundary trusts no call site to have done anything.** It
inspects the assembled response and asks one question: *is every number in
LLM-authorable text traceable to a deterministic field of this same response?*
That covers all three, including the one the inline guard structurally cannot.

### 2.1 Where the independence is real, and where it is not — stated honestly

The boundary check will reuse `_extract_numbers`. That is **parsing, not
policy**, and sharing it is deliberate: two different number extractors would
disagree about "Rs 1,20,000" and the disagreement would be a bug in itself.

But it means the two layers **share fate on one thing**: a figure neither
extractor recognises as a number is invisible to both. This is a real limit,
not a hedge, and it should be stated rather than claimed away. What the second
layer buys is independence of *policy and call-site discipline*, not
independence of tokenisation.

## 3. Design decisions

### 3.1 It runs in the test suite, not at runtime

**Rejected: a runtime assertion on every response.** It would add a failure mode
to production — a request dying because a *checker* was wrong — for a property
the inline guard already enforces in the request path. The second layer exists
to catch a *development* mistake (a forgotten guard, a wrong allow-set), and
development mistakes are caught in CI.

**Chosen: a test.** Consistent with `LEGAL_CLAIM_INVENTORY_DESIGN.md` §6's
no-scheduler decision, for the same reason: a local, network-free check that
runs on every suite run catches the mistake *in the commit that makes it*.

### 3.2 LLM-authorable text is located STRUCTURALLY, not from a list of fields

**Rejected: a hardcoded list of fields to inspect** (`explanation.explanation`,
`negotiation.points`, each flag's `rationale`, …). That is a second source of
truth for "where can model text appear", and it would drift the first time a
field is added — the exact failure this project has now found in a design doc,
a status file, a README and a brief.

**Chosen: the `ai_backed` flag already in the payload is the marker.** Every
section that can contain model-authored text carries `ai_backed`; the baseline
shows three (`compliance`, `explanation`, `negotiation`). The check walks the
response, and for every object carrying an `ai_backed` key, treats that object's
string fields as LLM-authorable.

This is self-maintaining: a new AI-backed section is inspected automatically
*because* it declares itself, and a section that forgets to declare `ai_backed`
is itself a finding worth a separate check.

### 3.3 The allowed set is every number in the response's deterministic parts

Built from the same payload, by walking every numeric leaf **outside** any
`ai_backed` section — plus the numbers in the request that produced it, since
an explanation may legitimately restate the CTC the caller supplied.

Tolerance stays at `1`, matching the inline guard, because rupee figures are
rounded for display and a stricter rule would fail on honest formatting.

### 3.4 `skip_below` is 0 at the boundary, deliberately stricter than inline

The inline guard skips numbers under 100 in explanation text because prose
filler ("2-4 sentences") would otherwise trip it.

**The boundary check does not skip.** A backstop that exempts a range is not a
backstop over that range, and the inline guard's own comment says the
safety-critical figures — `50%`, `12%`, `14%` — live exactly there. Prose filler
is handled instead by the allow-set: small integers that appear in the
deterministic payload are allowed, and ones that do not are exactly what this is
looking for.

**This will produce findings on day one if any honest prose filler is not
grounded.** That is expected, and each one is a decision — widen the allow-set,
or change the prompt — rather than a reason to reinstate a blanket exemption.

### 3.5 It proves nothing unless it is driven with model text

The characterization baseline has `ai_backed: False` throughout — it is the
deterministic fallback path, because no API key is present when it is generated.
Running the check over the baseline alone would test the fallback and report
success having checked nothing that matters.

**So the corpus is two-part:** the real deterministic responses *and* responses
where the LLM is mocked to return text containing an ungrounded figure. The
second is the sabotage-shaped half, and without it this check cannot be shown to
work.

## 4. Proof requirement

Both directions, per this project's standing pattern:

- a response whose model text restates only grounded figures → no finding;
- the identical response with one digit changed in the model text → a finding
  that **names the number and the field it appeared in**;
- a **new AI-backed section added with no inline guard call at all** → still
  caught. This is the case the whole design exists for, and it is the one to
  sabotage-prove first.

## 5. Decisions needing an explicit call

- **Does a finding fail the build on day one?** §3.4 predicts day-one findings
  from honest prose. Recommendation: yes, fail — the set is small and each
  finding is a real decision. This is the opposite of the
  `LEGAL_CLAIM_INVENTORY_DESIGN.md` §6 call, and deliberately: there, 4 claims
  were unverifiable for reasons outside the repo; here, every finding is fixable
  inside it.
- **Does a section lacking `ai_backed` warrant its own check?** §3.2 makes
  `ai_backed` load-bearing, so a section that omits it becomes invisible.
  Recommendation: yes, but as a separate follow-up, not folded in here.

## 6. What this does NOT ship

Any change to `_numbers_ungrounded` or to any call site's `allowed_numbers` or
`skip_below` — **structural and behavioural changes stay separate**, per the
spec's own Tier 1 constraint, which survives its mechanism being replaced. No
runtime assertion. No new dependency. No agent, no tool loop, no hook.
