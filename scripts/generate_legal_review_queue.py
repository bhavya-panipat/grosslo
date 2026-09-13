"""
Generates docs/LEGAL_REVIEW_QUEUE.md — everything in this codebase that asserts
law and cannot currently be shown to be right (LEGAL_CLAIM_INVENTORY_DESIGN.md
§4.6, Phase 2.4 step 5).

    python3 -B scripts/generate_legal_review_queue.py [--check]

WHAT THIS IS. One prioritized queue over BOTH provenance carriers — the
compliance rule set and the legal claim inventory. That single queue is the
payoff of step 1's extraction: before it, a rule's staleness and a constant's
staleness were different kinds of thing living in different places, and nothing
could rank them against each other.

WHAT THIS IS NOT, and the boundary is not negotiable (design §3):

  This tool may NOTICE and FLAG. It may never DECIDE.

It does not deactivate a rule, reactivate one, edit a citation, mark anything
verified, or judge that a value is correct. Every line it emits is a task for a
person. Marking something verified is a human act, in the same class as
reviewed_by, and no automated path writes it.

WHY IT DOES NOT FETCH ANYTHING, deliberately and against the design's own first
sketch. §4.6 described a monitor that checks reachable secondary sources. That
half is not built, because it would add nothing: AUTOMATED requests to the
primary sources are refused with HTTP 403, and a secondary source is explicitly
NOT verification under COMPLIANCE_BREADTH_DESIGN.md §3.1 step 2. So an automated
fetch would produce, at best, a finding that says "go read it in a browser" —
which this queue already says, with no network, no flakiness, and no risk of a
fetched snippet being mistaken for evidence. A content-hash watch on the primary
URLs would report 403 in perpetuity.

CORRECTED 2026-09-14 — THE PREMISE WAS OVERSTATED, THE DECISION STANDS. This
paragraph used to say "primary sources return 403 from this environment", as a
fact about the SOURCES. It was a fact about the REQUESTS. The same pages load
normally for a person in a browser, and that is how both outstanding lookups were
resolved on 2026-09-13 (docs/PRIMARY_SOURCE_LOOKUP_TASK.md).

The correction was checked against the decision rather than assumed to leave it
intact. Re-tested 2026-09-14, three scripted GETs to incometaxindia.gov.in:
default headers, a browser User-Agent, and browser Accept headers — all HTTP 403.
The refusal is not header-based, so a monitor built the ordinary way would still
be refused, and working around bot detection is not something this tool does.
The not-fetching decision is therefore still right; only its stated reason was
wrong.

That is narrower than the design promised. It is recorded here rather than
quietly delivered as if it were the whole thing.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compliance_rules
import legal_claims
import provenance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "LEGAL_REVIEW_QUEUE.md")

# Priority tiers. Ordered by how badly a reader could be misled, NOT by how
# hard each is to fix — the queue exists to say what matters most, and sorting
# by effort would quietly bury the worst item under the easiest ones.
CITES_DEAD_LAW = (
    1, "Cites law that has been superseded",
    "Worst of the four. The citation may match its source text perfectly and "
    "still point at a repealed Act, so it reads as verified while locating "
    "nothing. Strictly worse than an unresolved citation, which is at least "
    "visibly a gap.")
NO_CITATION_AT_ALL = (
    2, "Asserts law with no citation recorded anywhere",
    "A statutory claim nobody can check, because there is nothing to check "
    "against. Unverifiable by anyone, not merely unverified.")
ATTEMPTED_UNRESOLVED = (
    3, "Citation attempted, no primary source reached",
    "Someone tried and could not. Distinct from never having tried, and worse: "
    "it means the claim is uncheckable from here rather than merely unchecked.")
UNREVIEWED = (
    4, "No human has signed off",
    "The one assertion no automated check can produce. Everything else in this "
    "queue can be narrowed by fetching a document; this cannot.")


# Every tier, in rank order. render_document() walks THIS, not the rows, so a
# tier with nothing in it is still rendered rather than silently skipped.
TIERS = (CITES_DEAD_LAW, NO_CITATION_AT_ALL, ATTEMPTED_UNRESOLVED, UNREVIEWED)

# The exact marker an empty tier renders. Named so a test can bind to it rather
# than to prose that might be reworded (INVENTORY_EXPANSION_DESIGN.md §8).
#
# A whole distinctive sentence, deliberately NOT just "None.". A two-word marker
# can occur by coincidence inside an item's own provision or description text,
# which would make "an occupied tier does not carry the marker" fail for a
# reason unrelated to rendering — passing or failing on coincidence is the
# failure §8 names.
EMPTY_TIER = "No live item is currently in this tier."


def _render_item(item) -> list:
    out = [
        f"### {item.id} — {_describes(item)}",
        "",
        f"- **Where:** {_where(item)}",
        f"- **Instrument:** {item.instrument or '_none recorded_'} "
        f"({item.instrument_status})",
        f"- **Provision:** {item.provision or '_none recorded_'}",
    ]
    state = item.citation_checked_on.strip()
    if not state:
        shown = "_never attempted_"
    elif item.citation_attempt_unresolved:
        shown = state
    else:
        shown = f"checked {state}"
    out += [f"- **Citation state:** {shown}", ""]
    return out


def _tier(item):
    if item.is_live and item.cites_superseded_law:
        return CITES_DEAD_LAW
    if item.claim_type == provenance.STATUTORY and not item.provision.strip():
        return NO_CITATION_AT_ALL
    if item.citation_attempt_unresolved:
        return ATTEMPTED_UNRESOLVED
    if not item.implementation_is_reviewed:
        return UNREVIEWED
    return None


def _where(item):
    """Where the thing lives, for someone who has to go and look at it."""
    if hasattr(item, "where"):
        return f"`{item.where}`"
    return "`compliance_rules.py`"


def _describes(item):
    return getattr(item, "describes", None) or getattr(item, "check", "")


def collect() -> list:
    """
    Everything with provenance, from both carriers, tiered.

    Only LIVE items. An inert candidate rule cannot mislead anyone, so it does
    not belong in a queue about what might be wrong in production — while every
    Claim is live by construction (design §4.4), which is why the inventory
    dominates this list.
    """
    rows = []
    for item in tuple(compliance_rules.RULES) + tuple(legal_claims.CLAIMS):
        if not item.is_live:
            continue
        tier = _tier(item)
        if tier is not None:
            rows.append((tier, item))
    rows.sort(key=lambda row: (row[0][0], row[1].id))
    return rows


def render_document() -> str:
    rows = collect()
    live_rules = [r for r in compliance_rules.RULES if r.is_live]
    out = [
        "<!-- GENERATED by scripts/generate_legal_review_queue.py — do not edit. -->",
        "",
        "# Legal review queue",
        "",
        f"**{len(rows)} items** across {len(live_rules)} live compliance rules and "
        f"{len(legal_claims.CLAIMS)} legal claims.",
        "",
        "## Read this first",
        "",
        "**Nothing in this file is evidence.** It is a list of things this "
        "codebase asserts about the law that cannot currently be shown to be "
        "right. It was produced by reading the codebase's own records, not by "
        "consulting any legal source, and it resolves nothing.",
        "",
        "The tool that generates it may notice and flag. It may never decide. "
        "It does not deactivate a rule, edit a citation, mark anything "
        "verified, or judge that a value is correct — every line below is a "
        "task for a person, and marking something verified is a human act.",
        "",
        "**It does not fetch anything, on purpose.** Automated requests to the "
        "official legal sources are refused — HTTP 403, re-tested on 2026-09-14 "
        "with default and with browser headers — while the same pages load for "
        "a person in an ordinary browser. So the sources *are* readable, just "
        "not by the kind of request an automated monitor makes, and this tool "
        "does not try to get around that. A secondary source is not "
        "verification under this project's own standard either. So an "
        "automated fetch would at best tell you to go and read the source in a "
        "browser — which this file already says, without the risk of a fetched "
        "snippet being mistaken for proof. See "
        "`docs/PRIMARY_SOURCE_LOOKUP_TASK.md`.",
        "",
        "(An earlier version of this paragraph said the sources themselves "
        "returned 403. That over-read two automated failures as a fact about "
        "the source rather than about the request, and it stood for four days.)",
        "",
        "---",
        "",
    ]

    # EVERY TIER IS RENDERED, INCLUDING AN EMPTY ONE, AND AN EMPTY ONE SAYS SO.
    #
    # This loop used to emit a tier's header only when a row in that tier
    # arrived. That was invisible while every tier was occupied. On 2026-09-13
    # R5 — the only tier-1 item — had its citation fixed, tier 1 emptied, and
    # the queue silently began at "## 2." (R5_CITATION_PROPAGATION_DESIGN.md
    # §4.5.3). A numbered list that starts at 2 reads as a deletion, and
    # silence cannot distinguish "checked, and nothing cites dead law" from
    # "that check never ran". Zero is a finding (§2.1), so it is written down —
    # the same thing the CA packet already does with "0 rule(s) … none".
    by_tier = {tier: [] for tier in TIERS}
    for tier, item in rows:
        by_tier[tier].append(item)
    for tier in TIERS:
        rank, title, why = tier
        out += [f"## {rank}. {title}", "", why, ""]
        if not by_tier[tier]:
            out += [f"**None.** {EMPTY_TIER}", ""]
        for item in by_tier[tier]:
            out += _render_item(item)

    out += [
        "---",
        "",
        "## What would take an item off this list",
        "",
        "Reaching a primary source and reading it removes tiers 1-3. It does "
        "**not** remove tier 4: confirming that a provision exists and says "
        "what is quoted is a different act from judging that a value or a "
        "threshold correctly implements it. Only a qualified person clears "
        "that, by recording `reviewed_by` and `reviewed_on`.",
        "",
        "For a legal claim, a reviewer is asserting **the value matches the "
        "cited source**. For a compliance rule, that **the predicate correctly "
        "implements the claim**. Different assertions; do not treat one as the "
        "other.",
        "",
    ]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    updated = render_document()
    existing = ""
    if os.path.exists(DOC):
        with open(DOC) as f:
            existing = f.read()

    if args.check:
        if updated != existing:
            print("docs/LEGAL_REVIEW_QUEUE.md is OUT OF SYNC.\n"
                  "Run: python3 -B scripts/generate_legal_review_queue.py",
                  file=sys.stderr)
            return 1
        print(f"legal review queue is in sync ({len(collect())} items)")
        return 0

    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with open(DOC, "w") as f:
        f.write(updated)
    print(f"wrote {DOC}: {len(collect())} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
