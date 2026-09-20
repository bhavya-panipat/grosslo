# Running the suite when several sessions share one machine

**Standing procedure.** The test suite writes to one local Postgres, and
`tests/test_review_workflow.TestMissingSchemaFailsLoudly` drops a schema on
purpose mid-run. Two suites at once therefore pull tables out from under each
other: the symptom is dozens of errors across `test_auth`, `test_identity`,
`test_review_workflow` and `test_tenant_isolation`, with wall-clock time roughly
half the usual, plus `UniqueViolation` on `pg_namespace_nspname_index`,
`UndefinedTable`, and occasional `DeadlockDetected`.

**Such a run proves nothing and must be discarded, not interpreted.**

## The rule

```sh
mkdir /tmp/grosslo-suite.lock        # atomic: succeeds for exactly one process
```

- **It succeeded:** write an `owner` file naming your session, **a pid that
  lives for the whole job**, and what you are running. Release when your whole
  block of runs is done, not between runs.
- **It failed:** you do not have the lock. Read `owner`, queue behind whoever is
  named, and start nothing. Read the exit status; do not assume it.

Release, with the check that makes it safe:

```sh
grep -q "pid=$$" /tmp/grosslo-suite.lock/owner && rm -rf /tmp/grosslo-suite.lock
```

Put it on an `EXIT` trap so a crash releases the lock instead of leaving a
genuinely stale one behind. The `grep` must match something that identifies
**you** — a session name is safer than a pid, because a pid can be dead while
the job is alive (below).

### The pid you write is the hard part

**Recording a pid that outlives the job is the whole point, and both sessions
that tried it got it wrong in opposite directions on the same night.**

- A lock named pid 84635, which was **dead**, while that session's suite ran as
  84671 → 84673 → 84675: the recorded pid was an earlier shell in the pipeline.
  Clearing that "stale" lock would have killed a healthy run.
- A lock named pid 84968, also **dead**, held by a session that was genuinely
  mid-job — between a sabotage run and a docs run, editing files in the gap. For
  those minutes there was no suite process either, so the lock satisfied **both
  halves** of the staleness rule while being entirely legitimate. Caught because
  the session queued behind it **asked instead of acting**.

So the staleness rule is necessary but not sufficient: a two-phase job has gaps
in which it looks exactly like an abandoned lock. Options, in order of
preference:

1. **Write a pid that lives for the whole job** — the long-running shell's `$$`,
   never a child's, and never a pid from a command substitution.
2. **Write a phase or heartbeat line** the holder updates between runs, so a gap
   is distinguishable from abandonment by something machine-checkable. A `work=`
   field describing two runs states intent, but nothing reads it.
3. **Ask the named session before clearing anything.** This is what actually
   worked. It is slower than a heuristic and it is right more often.

**Both traps were found by a session checking a lock it wanted to take, never by
the lock's holder** — and that is not a coincidence. From inside a job
everything looks fine: the holder is running, its files are where it left them,
and nothing in its own view says the lock it wrote now reads as abandoned. The
failure is only visible from outside. So the ask-first step earns its place even
after the pid handling is fixed: whoever is about to clear a lock is the only
party who can see the problem, and asking is the only action that puts that
observation in front of the one who can resolve it.

## Why the obvious alternatives do not work

All four were tried on 2026-09-20/21, and all four failed the same way.

| Mechanism | How it failed |
|---|---|
| `pgrep` before starting | It sees only runs that have already begun. Two sessions checking an idle machine both start. Cost: four discarded runs in one night, two of them seconds apart. |
| "Go" / "done" messages alone | Messages cross. One session's *hold* and another's *start* were in flight simultaneously, twice. |
| An idle notice about another session | One arrived claiming a session had finished at 00:57, timestamped before the run it was describing, while the machine was busy. **An automated idle notice is a prompt to check the lock, never permission to start.** |
| "The owner pid is dead, so the lock is stale" | **The most dangerous of the four.** The lock named pid 84635, which was dead, while that session's suite was alive as 84671 → 84673 → 84675: the recorded pid was an earlier shell in the same pipeline. Clearing that "stale" lock would have destroyed a healthy run. |

**A lock is stale only if the owner pid is dead AND no suite process is
running** (`pgrep -f "[-]m unittest"`). If either is alive, it is not stale.

**And even then, ask the named session before clearing it.** Both halves were
true of a live, legitimate lock on 2026-09-21, during an edit gap between two
runs of the same job. A session that applied the rule correctly and acted on it
would have collided with the holder's second run. The rule tells you a lock
*might* be abandoned; only the holder can tell you it is.

**The principle underneath all four**, which is the part worth carrying to other
problems: each mechanism infers a global fact from a local observation taken a
moment ago. A clear `pgrep`, an acknowledgement received, a dead pid, an idle
notice — every one is evidence about the past, and the race lives in the gap
between observing and acting. Only an atomic acquire closes that gap, and only
if nothing is allowed to override it.

## What still has to be true of the run itself

The lock stops collisions. It does not make a run valid.

- **Run from a clean worktree at a commit**, not the shared checkout. A run in
  the shared tree includes whatever anyone has left uncommitted and corresponds
  to no commit; its numbers must not be recorded as a baseline.
- **Run with `python3 -B`**, and clear `~/Library/Caches/com.apple.python` if
  anything looks inconsistent (`LEGAL_CLAIM_INVENTORY_DESIGN.md` §9).
- **Hold sleep off with `caffeinate -dimsu`.** `caffeinate -i` is not enough on
  battery: two runs were lost to sleep, and a third reported a skip count that
  appeared only in the slept run. A run whose test time and wall-clock time
  disagree has slept; check `pmset -g log` and discard it.
- **Report the commit, the window and the count**, so another session can tell a
  real change in the count from an artefact.

## Numbers that describe the suite

From the README session's work on 2026-09-21, and general beyond this file.

**A count in prose rots.** README asserted "150 tests total across five files"
while the suite was 615, and the sentence invited the reader to confirm it —
naming no commit, so there was nothing to confirm it against. It had survived
from 150 to 615 in that state.

**When you find a stale number, first ask whether the sentence needs a number at
all.** Three outcomes, most durable first:

1. **Delete it** if it is rhetorical. "The other 261 tests cannot catch what this
   phase risks" is an argument about the *kind* of coverage the rest of the suite
   provides; the count carries no weight and is strictly more durable gone.
2. **Anchor it to a commit** if it is a verification claim: *615 tests at
   `0277b6a`*. That cannot go stale — it can only become not-yet-re-measured, and
   a reader elsewhere can tell immediately which.
3. **Pin it as historical** if it records what was true then, and say so.

Refreshing it in place is the one option that guarantees you will be back.

**Anchor to a commit a reader can actually fetch.** The point of naming a SHA is
that someone else can check it; an unpublished SHA keeps the form of that and
loses its purpose. When the commit you measured is not yet published, name a
published one whose `tests/` tree object is identical — `git rev-parse <sha>:tests`
on both — and say that is why. Found by the README session on 2026-09-21, which
measured at an unpushed commit and anchored its sentence to the published one
with the same tree.

**Prefer an invariant that fails cheaply over a measurement that must be
repeated.** README's eighteen per-file counts now sum to its stated total, so a
half-updated edit is caught by arithmetic, with no suite run and no lock. That
property — failing loudly and locally — is what the old sentence lacked, and it
is worth reaching for wherever a document states something checkable about the
code.
