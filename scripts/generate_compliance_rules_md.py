"""
Generates the rule table inside compliance_rules.md from compliance_rules.py
(COMPLIANCE_BREADTH_DESIGN.md §3.3, §6).

    python3 scripts/generate_compliance_rules_md.py [--check]

The table is DERIVED; the prose around it is hand-written and preserved. That
split is deliberate. §6 resolved to generate this file rather than replace it,
because the human-readable artefact is the property worth keeping — it is what a
reviewer or a CA opens first — and the editorial context around the table
(scope, how the list is used, the standing note about R5's engine gap) is real
writing that no rule object should be asked to carry.

So the generator only owns what is between the markers. Everything else is
someone's prose and stays untouched.

--check exits non-zero if the committed file does not match what would be
generated, which is what the test asserts. Without that, "generated" would mean
"generated at some point", and the drift this whole phase exists to remove would
come back through the side door.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compliance_rules

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "compliance_rules.md")
BEGIN = "<!-- BEGIN GENERATED RULES TABLE — edit compliance_rules.py, not this -->"
END = "<!-- END GENERATED RULES TABLE -->"


def render_table() -> str:
    lines = ["| Rule ID | Check | Rationale | Severity | Status |",
             "|---|---|---|---|---|"]
    for rule in compliance_rules.RULES:
        # A candidate is marked in the table itself, so a reader of the
        # document — not just a reader of the code — can see that it cannot
        # fire. An unmarked candidate in a compliance table is exactly the
        # "looks authoritative, is unreviewed" failure the protocol prevents.
        status = ("active" if rule.is_active
                  else "**CANDIDATE — cannot fire, awaiting review**")
        why = rule.why.replace("|", "\\|")
        lines.append(f"| {rule.id} | {rule.check} | {why} | {rule.severity} | {status} |")
    return "\n".join(lines)


def render_document(existing: str) -> str:
    before, rest = existing.split(BEGIN, 1)
    _old, after = rest.split(END, 1)
    return f"{before}{BEGIN}\n\n{render_table()}\n\n{END}{after}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    with open(DOC) as f:
        existing = f.read()
    if BEGIN not in existing or END not in existing:
        print(f"error: {DOC} has no generated-table markers", file=sys.stderr)
        return 1

    updated = render_document(existing)
    if args.check:
        if updated != existing:
            print("compliance_rules.md is OUT OF SYNC with compliance_rules.py.\n"
                  "Run: python3 scripts/generate_compliance_rules_md.py", file=sys.stderr)
            return 1
        print(f"compliance_rules.md is in sync ({len(compliance_rules.RULES)} rules)")
        return 0

    with open(DOC, "w") as f:
        f.write(updated)
    active = compliance_rules.total_active()
    total = len(compliance_rules.RULES)
    print(f"wrote {DOC}: {total} rules ({active} active, {total - active} candidate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
