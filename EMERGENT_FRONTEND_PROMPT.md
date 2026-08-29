# FinOS — Frontend-Only Redesign Prompt

**Feed this whole document to Emergent as the task spec.**

## Hard boundary — read this first

The backend (`tax_engine.py`, `optimizer.py`, `ai_layer.py`, `app.py`) is
already built, tested (23 passing tests), and validated against government
tax examples. **Do not rewrite, regenerate, or "improve" any backend logic.**
Your job is the frontend only: `static/index.html`, `static/styles.css`,
`static/app.js` (or their replacements, if restructuring into a proper
frontend build). If you believe a backend change is needed to support a
frontend feature, stop and ask — don't just make it happen by editing
Python.

If your normal workflow is to scaffold a new project structure, don't.
Build against the existing Flask static-file serving setup unless
explicitly told otherwise, so there is exactly one working version of this
project, not two.

## What to build

A landing page + application flow that looks and feels professionally
designed: a real hero/landing section explaining what FinOS does, smooth
transitions between the offer-letter/input/results states (not hard page
reloads), and a sophisticated but genuinely easy-to-read results dashboard
— not a wall of numbers. Motion should be purposeful (state transitions,
number count-ups, subtle entrance animation on the results appearing) —
not decorative for its own sake. This is a fintech tool; the tone should
read as trustworthy and precise, not flashy.

## Exact API contract — build against this, do not invent your own shape

**`POST /api/extract`**
Request: `{"text": "<pasted offer letter text>"}`
Response:
```json
{
  "ctc": 1800000.0, "basic": 450000.0, "hra": 300000.0, "lta": null,
  "special_allowance": null, "employer_pf": null,
  "currency_note": "string",
  "ai_backed": true,
  "mismatch_warning": null
}
```
Any field can be `null` if not found in the text. Always show the user the
extracted values with editable fields before they proceed — extraction is
not guaranteed accurate, and the UI must make that visible, not hide it.

**`POST /api/optimize`**
Request:
```json
{
  "ctc": 1800000, "rent_paid": 400000, "city": "metro",
  "nps_opted": true,
  "current_structure": {"basic": 450000, "hra": 300000, "lta": null, "employer_pf": null}
}
```
`current_structure` is optional — only include it when the user actually
extracted/confirmed an as-offered breakdown. Omitting it is correct
behavior for a manually-entered CTC-only flow, not a bug to route around.

Response includes: `ctc`, `old_regime_best` and `new_regime_best` (each
with `structure`, `tax_breakdown`, `basic_pct`), `recommended_regime`,
`annual_saving`, `explanation` (`{explanation, ai_backed, guard_triggered}`),
`compliance` (`{flags: [{rule_id, severity, message}], ai_backed}`), and —
only when `current_structure` was sent — `negotiation`
(`{points, total_annual_saving, changed_levers, ai_backed, guard_triggered}`).

**`GET /health`** → `{"status": "ok", "ai_layer_active": bool, "note": "..."}`

## Non-negotiable UX rules (not style preferences — these encode real
architecture decisions, changing them misrepresents what the tool does)

- Every AI-backed piece of text (explanation, negotiation points,
  compliance phrasing) MUST visibly show whether it came from the live AI
  layer or the deterministic fallback (`ai_backed: true/false` in the
  response). Don't design this away as a small badge nobody notices — it's
  core to this project's honesty story. Make it legible, not hidden in a
  tooltip.
- If `guard_triggered: true` appears anywhere, show a visible note that the
  AI output failed verification and a rule-based result is shown instead.
  Never suppress this to keep the UI "clean."
- The negotiation section must only render when the API actually returns a
  `negotiation` object — don't fabricate a placeholder or empty state that
  implies negotiation ran when it didn't.
- Numbers are real government-validated tax figures. Don't let an animation
  library's easing/rounding during a count-up transition display a
  different final number than what the API returned — the animated number
  must land on the exact API value, not an approximation.

## Deliverable

A polished, animated, professional frontend that is a drop-in replacement
for `static/`, calling the exact endpoints above, with zero changes to any
`.py` file. When done, state clearly whether you touched anything outside
`static/` — if you did, list exactly what and why, so it can be reviewed
before merging.
