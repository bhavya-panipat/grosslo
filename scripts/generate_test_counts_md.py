"""
Generates the test counts in README.md and FINOS_PROJECT_BRIEF.md from the
suite itself.

    python3 scripts/generate_test_counts_md.py [--check]

Why this exists. The count was hand-maintained and drifted badly: the README
said "150 tests total across five files", described itself as "counted directly
from the test methods in the repo, not estimated", and invited the reader to
re-run and confirm. By the time anyone did, the suite was 615. Correcting it
was not enough — it went 615, 625, 633 in a week, and each correction only
reset the clock. The number is downstream of every commit that touches
`tests/`, so nothing hand-written can stay true.

This owns the NUMBERS only. Every per-file description is hand-written prose
about what that file covers, and no count object should be asked to carry it.
So the generator rewrites the figures in place and never touches the words —
the same split as `generate_compliance_rules_md.py`, for the same reason.

It counts with unittest's own loader rather than by parsing `def test_`,
because a static count is wrong here: `TestAnswerQueryRejectsSectionsItNever\
Supplied` subclasses another TestCase and re-runs its parent's tests, so the
source has six fewer test methods than the runner reports. The loader resolves
that the way the runner does, which is the whole point — the documented number
has to be the number you get, not a plausible approximation of it.

Loading imports the test modules, so Postgres must be running
(`brew services start postgresql@16`). It does not execute any test.

--check exits non-zero if the committed figures do not match, which is what
the test asserts. Without it, "generated" would mean "generated at some point"
and the drift would return through the side door.

It also fails when a test file has no entry, or an entry names a file that no
longer exists. That is deliberate: a new test file needs a human to write what
it covers, and silently appending a bare number would recreate the problem
this removes.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

README = os.path.join(ROOT, "README.md")
BRIEF = os.path.join(ROOT, "FINOS_PROJECT_BRIEF.md")


def counts() -> tuple[dict[str, int], int]:
    """Per-file test counts and the total, exactly as the runner reports them."""
    # Mirror `python3 -m unittest discover -s tests` run from the repo root,
    # exactly: tests/ is not a package, so the modules load top-level and the
    # start directory must be relative to ROOT.
    os.chdir(ROOT)
    suite = unittest.TestLoader().discover("tests")
    per_file: dict[str, int] = {}

    def walk(s):
        for item in s:
            if isinstance(item, unittest.TestSuite):
                walk(item)
            elif isinstance(item, unittest.TestCase):
                mod = type(item).__module__.rsplit(".", 1)[-1]
                per_file[f"{mod}.py"] = per_file.get(f"{mod}.py", 0) + 1
            else:                                   # a load error placeholder
                raise SystemExit(f"error: suite failed to load: {item}")

    walk(suite)
    return per_file, sum(per_file.values())


def render(text: str, per_file: dict[str, int], total: int, seen: set[str]) -> str:
    n_files = len(per_file)

    # "633 tests across 19 files"
    text = re.sub(r"^\d+ tests across \d+ files",
                  f"{total} tests across {n_files} files", text, flags=re.M)
    # the Running-it comment
    text = re.sub(r"# \d+ tests, all pass with no API key set",
                  f"# {total} tests, all pass with no API key set", text)

    # per-file figures, in both the README's and the brief's bullet styles
    def one(m: re.Match) -> str:
        fname = m.group("file")
        seen.add(fname)
        if fname not in per_file:
            raise SystemExit(
                f"error: {fname} is listed in the docs but no longer exists in "
                f"tests/. Remove its entry, or restore the file.")
        return f"{m.group('pre')}{per_file[fname]}{m.group('mid')}{fname}"

    text = re.sub(r"(?P<pre>- \*\*)\d+(?P<mid> in `tests/)(?P<file>test_\w+\.py)",
                  one, text)
    text = re.sub(r"(?P<pre>- \*\*)\d+(?P<mid>\*\* in `tests/)(?P<file>test_\w+\.py)",
                  one, text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    per_file, total = counts()
    seen: set[str] = set()
    outputs = {}
    for path in (README, BRIEF):
        with open(path) as f:
            existing = f.read()
        outputs[path] = (existing, render(existing, per_file, total, seen))

    # Every test file must be documented somewhere, or the total describes
    # files the reader was never told about.
    undocumented = sorted(set(per_file) - seen)
    if undocumented:
        print("error: these test files have no entry in README.md or "
              "FINOS_PROJECT_BRIEF.md, so the total would count files the "
              "reader is never shown. Add a line describing what each covers:",
              file=sys.stderr)
        for f in undocumented:
            print(f"  {f}  ({per_file[f]} tests)", file=sys.stderr)
        return 1

    if args.check:
        stale = [p for p, (old, new) in outputs.items() if old != new]
        if stale:
            print("test counts in the docs are OUT OF SYNC with the suite:",
                  file=sys.stderr)
            for p in stale:
                print(f"  {os.path.basename(p)}", file=sys.stderr)
            print("Run: python3 scripts/generate_test_counts_md.py",
                  file=sys.stderr)
            return 1
        print(f"test counts are in sync ({total} tests across {len(per_file)} files)")
        return 0

    for path, (old, new) in outputs.items():
        if old != new:
            with open(path, "w") as f:
                f.write(new)
            print(f"wrote {os.path.basename(path)}")
    print(f"{total} tests across {len(per_file)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
