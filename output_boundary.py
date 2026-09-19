"""
output_boundary.py — the second enforcement layer for the numeric guard
(OUTPUT_BOUNDARY_DESIGN.md).

WHAT THE FIRST LAYER IS, AND WHY A SECOND ONE EXISTS. ai_layer's
_numbers_ungrounded() checks an LLM's candidate text against an allow-set
supplied BY THE CALL SITE, at each of six messages.create() sites. It is correct
today. Its three failure modes are all failures of a call site rather than of
the checking function:

  1. an incomplete allowed_numbers set — the guard checks faithfully against
     whatever it was handed;
  2. a skip_below set too high — a real figure below it is exempt by
     construction;
  3. A NEW CALL SITE THAT NEVER CALLS THE GUARD AT ALL. This is the one that
     matters, and it is the exact analogue of the tenancy case RLS covered: a
     query that forgets to filter. Nothing today prevents a seventh
     messages.create() whose output goes straight into a response.

This module trusts no call site to have done anything. It inspects an assembled
response and asks one question: is every number in LLM-authored text traceable
to a deterministic field of that same response?

WHERE THE INDEPENDENCE IS REAL AND WHERE IT IS NOT. This reuses ai_layer's
_extract_numbers. That is PARSING, NOT POLICY, and sharing it is deliberate —
two different extractors would disagree about "Rs 1,20,000" and the disagreement
would be a bug in itself. But it means the layers SHARE FATE on tokenisation: a
figure neither recognises as a number is invisible to both. What the second
layer buys is independence of POLICY and CALL-SITE DISCIPLINE, not independence
of tokenisation. Stated rather than claimed away.

RUNS IN THE TEST SUITE, NOT AT RUNTIME (design §3.1). A runtime assertion would
add a production failure mode — a request dying because a CHECKER was wrong —
for a property the inline guard already enforces in the request path. The
mistake this catches is a development one, and development mistakes are caught
in CI.
"""

from __future__ import annotations

import re

from ai_layer import _extract_numbers

# The structural marker for "this section may contain model-authored text".
#
# DELIBERATELY NOT A HARDCODED LIST OF FIELD PATHS. A list of
# explanation.explanation / negotiation.points / flags[].rationale would be a
# second source of truth for "where can model text appear", and it would drift
# the first time a field was added — the exact failure this project has now
# found in a design doc, a status file, a README and a brief. Every section that
# can carry model text already declares itself with this key, so a new one is
# inspected automatically BECAUSE it declares itself.
#
# The cost of that choice, named: a section that OMITS the flag is invisible
# here. Tracked as its own follow-up rather than absorbed into this module.
AI_MARKER = "ai_backed"

# Matches the inline guard. Rupee figures are rounded for display, and a
# stricter rule would fail on honest formatting rather than on ungrounded
# numbers.
TOLERANCE = 1.0


class Finding:
    """One number in model-authored text that no deterministic field supports."""

    def __init__(self, path: str, number: float, text: str):
        self.path = path
        self.number = number
        self.text = text

    def __str__(self) -> str:
        excerpt = self.text if len(self.text) <= 160 else self.text[:157] + "..."
        return (f"{self.path}: the figure {self.number:g} appears in "
                f"model-authored text but matches no deterministic field of "
                f"this response. Either it was invented, or the value it "
                f"restates is not in the payload for a reader to check against. "
                f"Text: {excerpt!r}")

    __repr__ = __str__


# Tokens like "R1", "IFSC0001", "Section17" — a digit fused to letters. These
# are IDENTIFIERS, not figures, and stripping them before parsing is a
# category correction rather than a policy exemption.
#
# FOUND BY RUNNING THIS AGAINST REAL PIPELINE OUTPUT, not by inspection. A
# compliance flag carries rule_id "R1" inside a section marked ai_backed, and
# the shared extractor pulled "1" out of it. That exposed a wrong assumption in
# the design: a section is NOT uniformly model-authored. flags[].rule_id and
# flags[].severity are set by Python from compliance_rules.py; only the message
# text is ever rephrased.
#
# WHY NOT A LIST OF FIELDS TO SKIP: that would be a second source of truth for
# "which fields are model-authored", the exact thing AI_MARKER exists to avoid.
# Stripping identifier tokens is a statement about what a FIGURE is, true
# everywhere, rather than a per-field exemption that drifts.
#
# The shared extractor is left untouched — changing it would change the inline
# guard's behaviour, which design §6 puts out of scope. This filters its INPUT.
_IDENTIFIER_TOKEN = re.compile(r"\b[A-Za-z]+\d[A-Za-z0-9]*\b")


def figures(text: str) -> list:
    """Numbers in `text` that are figures rather than identifier tokens."""
    return _extract_numbers(_IDENTIFIER_TOKEN.sub(" ", text))


def _is_number(value) -> bool:
    """
    Numeric leaf, excluding bools.

    bool is a subclass of int in Python, so `ai_backed: True` would otherwise
    enter the allow-set as the number 1 and silently ground every stray "1" in
    model text.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk(node, path=""):
    """Every (path, value) leaf, with dict/list structure flattened into path."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def _ai_section_paths(payload) -> list:
    """
    Paths of every section that declares itself as CARRYING model text.

    ai_backed must be TRUE, not merely present. A section whose ai_backed is
    False contains the deterministic fallback text by definition — the
    Python-authored rationale from compliance_rules.py, for instance, whose
    figures are grounded in the rule rather than in the response. Checking those
    would report findings against text no model ever touched.
    """
    found = []

    def visit(node, path=""):
        if isinstance(node, dict):
            if node.get(AI_MARKER) is True:
                found.append(path)
            for key, value in node.items():
                visit(value, f"{path}.{key}" if path else key)
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(payload)
    return found


def declared_ai_fields(section: dict, base: str = "") -> list:
    """
    (path, value) for every field `section` declares as model-authored in its
    "ai_fields" list (OUTPUT_BOUNDARY_GROUNDING_DESIGN.md §3.1 (b)).

    Paths are relative to the section: "points" is a key; "flags[].message" is
    `message` in every element of `flags`; "checks[2].message" is one element.
    A declared path that resolves to nothing raises, rather than silently
    declaring nothing. That would be the same quiet gap this exists to close.
    """
    out = []
    for declared in section.get("ai_fields", []):
        found = []

        def walk(node, parts, path):
            if not parts:
                found.append((path, node))
                return
            m = re.fullmatch(r"(\w+)(?:\[(\d*)\])?", parts[0])
            if not m or not isinstance(node, dict) or m.group(1) not in node:
                return
            key, index = m.group(1), m.group(2)
            child, child_path = node[key], f"{path}.{key}" if path else key
            if index is None:
                walk(child, parts[1:], child_path)
            elif isinstance(child, list):
                picks = range(len(child)) if index == "" else [int(index)]
                for i in picks:
                    if i < len(child):
                        walk(child[i], parts[1:], f"{child_path}[{i}]")

        walk(section, declared.split("."), base)
        if not found:
            raise ValueError(f"ai_fields declares {declared!r}, which resolves to nothing "
                             f"in {base or 'the section'}")
        out.extend(found)
    return out


def _in_any_section(path: str, sections: list) -> bool:
    return any(path == s or path.startswith(s + ".") or path.startswith(s + "[")
               for s in sections)


def grounded_numbers(payload, extra=()) -> set:
    """
    Every number a model may legitimately restate: the deterministic leaves of
    this response, plus anything the caller supplied.

    `extra` carries the REQUEST's numbers — an explanation may legitimately
    restate the CTC that was asked about even when the response does not echo it
    back as its own field.
    """
    sections = _ai_section_paths(payload)
    allowed = {float(v) for path, v in _walk(payload)
               if _is_number(v) and not _in_any_section(path, sections)}
    allowed |= {float(n) for n in extra}
    return allowed


def ungrounded_findings(payload, extra=()) -> list:
    """
    Numbers in model-authored text with nothing in the response to support them.

    NO skip_below, deliberately, and stricter than the inline guard's 100 for
    explanation text (design §3.4). A backstop that exempts a range is not a
    backstop over that range — and the inline guard's own comment says the
    safety-critical figures live exactly there: R1's 50% floor, the 12% PF rate,
    the 14% NPS cap. Prose filler is handled by the allow-set instead: a small
    integer that appears in the deterministic payload is allowed, and one that
    does not is precisely what this is looking for.
    """
    allowed = grounded_numbers(payload, extra)
    sections = _ai_section_paths(payload)
    findings = []
    for path, value in _walk(payload):
        if not isinstance(value, str) or not _in_any_section(path, sections):
            continue
        for number in figures(value):
            if not any(abs(number - a) < TOLERANCE for a in allowed):
                findings.append(Finding(path, number, value))
    return findings
