# Working in this repo

Several Claude sessions share this working tree and this `main` at the same
time. Assume at least one other session is committing while you work: check
`git status` and `git log` before you edit, and do not assume an uncommitted
file is yours. If you need to be sure of a file's ownership, ask the session
editing it rather than inferring from a plausible match.

## Each session pushes its own commits

**Do not commit onto another session's unpushed tip. Wait for it to land, then
stack yours on top.** Then: **push only commits you wrote, never a range
containing another session's work.**

The first rule is the load-bearing one, and it is a *committing* discipline,
not a pushing one. "Each session pushes its own commits" is a property of the
commit order: once commits interleave, no push can honour it. On 2026-09-21 the
stack ran theirs → mine → theirs → mine → theirs, and every cleared commit was
stranded behind an uncleared one belonging to a session whose user had not been
asked yet. Nobody had done anything wrong at push time; the shape was already
unfixable by then, and the only exits were a cherry-pick or publishing someone
else's work.

A branch push publishes *everything reachable*, not the commits you authored.
If another session's commits sit underneath yours, `git push origin HEAD:main`
publishes theirs too — and approval to *commit* is not approval to *publish*,
so that decision is not yours to make on their behalf. This has happened twice:
once with approval, once without. The mechanism was identical both times; only
the approval differed, and that difference is not visible from outside the
other session.

Before any push:

```bash
git log --oneline origin/main..<sha>   # read it; it must contain only your commits
git push origin <sha>:refs/heads/main  # push the SHA you verified, never HEAD
```

Run that check every time, including when the branch looks routine — the
dangerous case is the one that looks ordinary. `HEAD` can move between your run
and your push; it has, by 14 seconds, and the push published a commit that had
never been in a suite run. Another session has committed *on top of* a commit
in the seconds between writing it and pushing it.

If another session's unpublished work already sits under yours, wait for them
to push, then push yours on top. If your commits are interleaved with theirs,
the separable order is gone: cherry-pick your own onto `origin/main` and let
the duplicates drop out by patch-id when their range lands, or get their
commits cleared and publish the range as one. Never push a range ending at a
commit that is knowingly red —
a test committed failing is a deliberate step in this repo's sequence, and
publishing that state is worse than publishing an unverified one.

## Committing in a shared tree

One kind of change per commit: documentation changes do not ride along with
code changes. Commit by explicit path — `git commit -- <path>` — so another
session's staged or modified files cannot enter your commit. Check `git status`
immediately before committing, not only before editing.

## Before running the full suite

The suite needs Postgres (`brew services start postgresql@16`; an import-time
connection error is a stopped service, not a code bug) and it needs the shared
lock. Two suites against the same database destroy each other, because
`test_review_workflow.TestMissingSchemaFailsLoudly` drops schemas deliberately,
so whichever suite is not driving that test loses its tables.

**A `pgrep` check is not a lock**, and neither is an announcement: a pre-flight
check cannot see a run that starts a moment later, and messages cross in
transit. Take the lock. `docs/SUITE_LOCK_PROTOCOL.md` has the acquire/release
protocol, the staleness traps that will cost someone a live run, and what has
to be true of a run before you may quote its number.

Run it in a clean worktree pinned at a named commit, never in the shared tree:

```bash
caffeinate -dimsu python3 -B -m unittest discover -s tests
```

`caffeinate -i` alone does not hold on battery and has silently invalidated
runs. Compare the wall clock against unittest's own reported elapsed time:
`time.perf_counter` does not advance across sleep, so a slept run still prints
a plausible duration and can still print `OK`. Record the skip count, not just
`OK`. The suite passes with no `ANTHROPIC_API_KEY` set — every AI-layer
function has a deterministic fallback.

## The one architecture rule

**No LLM call may compute, restate with different rounding, or invent a
tax/salary/compliance figure.** Every number a user sees traces to
`tax_engine.py`, `optimizer.py`, `payroll_breakdown.py` or
`penalty_exposure.py`. The LLM narrates those numbers and rephrases
already-decided compliance flags; it never decides one.

This is enforced by a numeric guard that rejects any model response containing
a figure not traceable to the data that call site supplied, plus a second
output-boundary layer that trusts no call site to have supplied a correct
allow-set. Before changing anything in `tax_engine.py`, `optimizer.py`,
`ai_layer.py` or `app.py`, read how the guard works, and run the suite after.

## Fixing a stored computed value: decide about pre-fix rows in the same design

`/api/submissions` computes a row once and stores the result; the Finance queue
and the export routes then **read stored values, not fresh ones**. So a
correctness fix ships clean for new rows and leaves historical rows silently on
the old, wrong basis.

This has now happened three times — `tax_basis` (D1-5), `treasury_basis` (D-T3)
and the CTC reconciliation (D-S2) — and the third was found by a *different*
session, while it was typing the response fields as optional. It is a standing
property of the write-once/read-many pattern, not a fresh consequence to
rediscover per fix.

**So: any correctness fix to a value that gets stored must contain an explicit
decision about pre-fix rows, in its own design document, before implementation.**
Not a section added afterwards when someone notices.

**The decision requires the affected population to be measured, and "no flag"
is a legitimate answer.** Do not rank severity by argument and let that set
urgency — this project's practice is that a severity claim is not accepted until
it is measured, and the measurement has changed the answer before. Where to
look, because the obvious store is not the only one:

- the Postgres `submission_rows` table, per tenant;
- **the pre-port SQLite `review_queue.db`** (git-ignored, still on disk), which
  `scripts/migrate_sqlite_to_postgres.py` would copy in verbatim, basis column
  absent;
- whether the affected field is stored at all — a stateless route's figures
  (`/api/batch-audit`) have no history to flag.

D-S2 measured zero affected rows in both stores and the set cannot grow, since
every row written after the fix is on the corrected basis. A flag with an empty
population is a badge that can never fire, and D1-4 §8.2 already rejected
flagging unaffected rows on the grounds that it teaches people to ignore the
flag. D1-5's population was not empty — 2 of the 5 SQLite rows carried employer
NPS — which is why the same question got the opposite answer. **The difference
was measured, not reasoned.**

## Claims in documentation must be checkable

The standing concern in this project is a claim that asserts its own
verification and is wrong. Two have been found: `(Act 30 of 2025)`, recorded as
fact without a Gazette check, and a README sentence reading "counted directly
from the test methods in the repo, not estimated" that had drifted from 150 to
615 while still inviting the reader to re-run and confirm.

So: never write a bare test count, or any measured number, without the commit
it was measured at — and name a commit a reader can actually fetch. When you
find a stale number, do not refresh it in place. Delete it if it is rhetorical,
anchor it to a commit if it is a verification claim, pin it as historical if it
is a record of what was true then. Refreshing in place guarantees a repeat.
Prefer an invariant that fails cheaply: the README's per-file test counts sum
to the stated total, so a half-updated edit is caught without running anything.
