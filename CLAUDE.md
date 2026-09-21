# Working in this repo

Several Claude sessions share this working tree and this `main` at the same
time. Assume at least one other session is committing while you work.

## Each session pushes its own commits

**Push only commits you wrote. Never push a range containing another session's
work.**

A branch push publishes *everything reachable*, not the commits you authored.
If another session's commits sit underneath yours, `git push origin HEAD:main`
publishes theirs too — and approval to *commit* is not approval to *publish*,
so that decision is not yours to make on their behalf. This has happened twice:
once with approval, once without. The mechanism was identical both times; only
the approval differed, and it is not visible from outside the other session.

Before any push:

```bash
git log --oneline origin/main..<sha>   # read it; it must contain only your commits
git push origin <sha>:refs/heads/main  # push the SHA you verified, never HEAD
```

`HEAD` can move between your run and your push — it has, by 14 seconds, and the
push published a commit that had never been in a suite run.

If another session's unpublished work sits under yours, **wait for them to push
first**, then push yours on top. Cherry-picking your own commits onto
`origin/main` is the escape hatch; duplicates drop out by patch-id when their
range later lands. Never push a range ending at a commit that is knowingly red —
tests committed failing are a deliberate step, and publishing that state is
worse than publishing an unverified one.

## Before running the full suite

The suite needs Postgres (`brew services start postgresql@16`) and it needs the
shared lock — two suites against the same database destroy each other, because
`test_review_workflow.TestMissingSchemaFailsLoudly` drops schemas deliberately.
A `pgrep` check is not a lock. See `docs/SUITE_LOCK_PROTOCOL.md` for the
acquire/release protocol, the staleness traps, and what must be true of a run
before you quote its number.

## Numbers that describe the suite

Never write a bare test count into a document. Anchor it to the commit it was
measured at, and to a commit a reader can fetch. See "Numbers that describe the
suite" in `docs/SUITE_LOCK_PROTOCOL.md` — a count without a commit goes stale
silently, which is how one README sentence survived from 150 to 615 while still
inviting the reader to re-run and confirm it.
