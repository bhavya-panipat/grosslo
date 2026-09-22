# Working in this repo

Several Claude sessions share this working tree and this `main` at the same
time. Assume at least one other session is committing while you work: check
`git status` and `git log` before you edit, and do not assume an uncommitted
file is yours. If you need to be sure of a file's ownership, ask the session
editing it rather than inferring from a plausible match.

## Each session pushes its own commits

**Push only commits you wrote. Never push a range containing another session's
work.**

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

If another session's unpublished work sits under yours, **wait for them to push
first**, then push yours on top. Cherry-picking your own commits onto
`origin/main` is the escape hatch; duplicates drop out by patch-id when their
range later lands. Never push a range ending at a commit that is knowingly red —
tests committed failing are a deliberate step here (see below), and publishing
that state is worse than publishing an unverified one.

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

## How changes are made here

The sequence visible throughout the history is **scope → pin → fix → record**:

1. **Scope** the gap in a `*_DESIGN.md`, numbering the decisions (`D-T1`,
   `D-M3`, `D-E1`), and commit that before writing code.
2. **Pin** the bug with a test that fails, committed failing and labelled so
   in the subject — this is deliberate, and proves the test can detect the bug.
3. **Fix** it, citing the decision IDs in the commit subject.
4. **Record** the outcome in `docs/PROJECT_STATUS.md` and, where a user-visible
   claim changed, in the README.

Commit messages here are long and explain *why*, how the bug survived, and what
it would have cost. Match that; a one-line subject is not enough.

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
