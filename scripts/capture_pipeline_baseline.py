"""
Captures the characterization baseline the Phase 2.1 restructure is proven
against (ORCHESTRATION_DESIGN.md §3.3, §6).

    python3 scripts/capture_pipeline_baseline.py [--check]

Writes tests/fixtures/pipeline_baseline.json — a COMMITTED FIXTURE, not
something regenerated at test time. That distinction is the whole point: a
regenerated baseline only proves the code agrees with itself and cannot catch a
pre-existing regression. This has to be a fixed point that requires a
deliberate change to move, the same property that makes a commit a checkpoint
rather than a description of the present.

So: run this ONCE against the pre-restructure code, commit the result, and
never re-run it to "fix" a failing comparison. A diff here is either a bug or a
change someone must justify in a commit message.

--check re-captures without writing and reports whether the live pipeline still
matches, which is what the test does too.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.pipeline_cases import CASES

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tests", "fixtures", "pipeline_baseline.json")


def capture() -> dict:
    import app as flask_app
    out = {}
    for name, kwargs in CASES:
        response, _result = flask_app._build_optimize_response(
            kwargs["ctc"], kwargs["rent_paid"], kwargs["city"], kwargs["nps_opted"],
            kwargs["current_extracted"], kwargs["extraction_ai_backed"], skip_ai=True,
        )
        out[name] = response
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed fixture without writing")
    args = ap.parse_args()

    captured = capture()

    if args.check:
        if not os.path.exists(FIXTURE):
            print(f"error: no baseline at {FIXTURE} — capture one first", file=sys.stderr)
            return 1
        with open(FIXTURE) as f:
            baseline = json.load(f)
        drift = [name for name in baseline
                 if json.dumps(baseline[name], sort_keys=True)
                 != json.dumps(captured.get(name), sort_keys=True)]
        missing = sorted(set(baseline) - set(captured))
        added = sorted(set(captured) - set(baseline))
        print(f"cases: {len(baseline)} in baseline, {len(captured)} captured")
        print(f"  drifted: {drift or 'none'}")
        print(f"  missing: {missing or 'none'}")
        print(f"  added:   {added or 'none'}")
        return 1 if (drift or missing or added) else 0

    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, "w") as f:
        json.dump(captured, f, indent=2, sort_keys=True)
        f.write("\n")
    size = os.path.getsize(FIXTURE)
    print(f"wrote {FIXTURE} — {len(captured)} cases, {size:,} bytes")
    for name in captured:
        flags = [fl["rule_id"] for fl in captured[name]["compliance"]["flags"]]
        print(f"  {name:<44} flags={flags or '[]'} "
              f"checked_against={captured[name]['compliance_checked_against']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
