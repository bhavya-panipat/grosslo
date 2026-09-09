"""
The compliance rule set as data (COMPLIANCE_BREADTH_DESIGN.md, Phase 2.2).

Step 1 is a migration: R1-R6 move from a hand-written if-chain into
compliance_rules.RULES with no behaviour change. The characterization baseline
proves the OUTPUT is unchanged; these assert the invariants the new structure
has to hold so that later steps — and later rules — cannot quietly break it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_layer
import compliance_rules
from compliance_rules import ACTIVE, CANDIDATE
from tax_engine import SalaryStructure

# What R1-R6 were before the migration. Written out rather than derived from
# the module under test, which would make this assert only that the code agrees
# with itself.
PRE_MIGRATION = [
    ("R1", "High"), ("R2", "Medium"), ("R3", "Low"),
    ("R4", "Low"), ("R5", "High"), ("R6", "Low"),
]


class TestMigrationPreservedTheRuleSet(unittest.TestCase):

    def test_the_same_six_rules_exist_with_the_same_severities_in_order(self):
        self.assertEqual([(r.id, r.severity) for r in compliance_rules.RULES],
                         PRE_MIGRATION)

    def test_flag_order_is_the_declaration_order(self):
        # The if-chain produced R1..R6 order implicitly; a dict-backed or
        # set-backed rule set could reorder flags without changing which fired,
        # which the baseline WOULD catch but only as an opaque diff.
        structure = SalaryStructure(
            ctc=2_000_000, basic=100_000, hra=400_000, lta=900_000,
            special_allowance=0, employer_pf=800_000, employer_nps=0,
            nps_opted=False)
        fired = [f["rule_id"] for f in ai_layer._check_rules(structure, rent_paid=0)]
        self.assertEqual(fired, sorted(fired, key=lambda rid: int(rid[1:])),
                         f"flags came back out of declaration order: {fired}")
        self.assertGreater(len(fired), 1, "this fixture must trip several rules")

    def test_every_rule_id_is_unique(self):
        ids = [r.id for r in compliance_rules.RULES]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate rule id in {ids}")

    def test_every_rule_has_text_a_user_could_read(self):
        for rule in compliance_rules.RULES:
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.rationale.strip(), "empty rationale")
                self.assertTrue(rule.check.strip(), "empty check description")
                self.assertIn(rule.severity, ("High", "Medium", "Low"))

    def test_rules_are_immutable(self):
        # Activating a candidate must be a source change that shows in a diff
        # (design §6), not something application code can do at runtime.
        with self.assertRaises(Exception):
            compliance_rules.RULES[0].status = CANDIDATE


class TestTheCountIsDerivedNotDeclared(unittest.TestCase):

    def test_no_module_level_snapshot_of_the_count_survives(self):
        # A derived-once constant is the same staleness class as a hardcoded
        # one, just harder to spot: it agrees with the rule set at import and
        # can disagree afterwards. Consumers must read it live.
        self.assertFalse(hasattr(ai_layer, "TOTAL_COMPLIANCE_RULES"),
                         "a cached rule count reappeared in ai_layer")

    def test_the_count_is_still_six_after_the_migration(self):
        # The migration's own claim: nothing changed.
        self.assertEqual(compliance_rules.total_active(), 6)

    def test_the_denominator_counts_only_rules_that_can_fire(self):
        # A candidate must not make a compliance score look better by inflating
        # the total (design §3.4). Asserted structurally now, before any
        # candidate exists, so the property is in place before it is depended on.
        self.assertEqual(compliance_rules.total_active(),
                         len([r for r in compliance_rules.RULES if r.status == ACTIVE]))
        self.assertNotIn(CANDIDATE,
                         [r.status for r in compliance_rules.active_rules()])


class TestActiveAndCandidatePartitionTheRuleSet(unittest.TestCase):

    def test_every_rule_is_in_exactly_one_partition(self):
        active = set(r.id for r in compliance_rules.active_rules())
        candidate = set(r.id for r in compliance_rules.candidate_rules())
        every = set(r.id for r in compliance_rules.RULES)
        self.assertEqual(active | candidate, every)
        self.assertEqual(active & candidate, set(), "a rule is both active and candidate")

    def test_status_is_one_of_the_two_known_values(self):
        for rule in compliance_rules.RULES:
            with self.subTest(rule=rule.id):
                self.assertIn(rule.status, (ACTIVE, CANDIDATE))

    def test_there_are_no_candidates_yet(self):
        # Step 1 is the migration only. The gate mechanism and its both-states
        # proof are step 4, and the first candidates are step 5 — this pins that
        # ordering so a rule cannot arrive before the gate that holds it.
        self.assertEqual(compliance_rules.candidate_rules(), ())


class TestTheDocumentIsGeneratedNotMaintained(unittest.TestCase):
    """
    compliance_rules.md's table is derived from compliance_rules.py. Without a
    test, "generated" would mean "generated at some point", and the drift this
    phase exists to remove would return through the side door — someone edits
    the table because it is right there and readable, and nothing notices.
    """

    def test_the_committed_table_matches_what_the_generator_produces(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "generate_compliance_rules_md.py"),
             "--check"],
            capture_output=True, text=True, cwd=root)
        self.assertEqual(result.returncode, 0,
                         f"compliance_rules.md is out of sync with compliance_rules.py.\n"
                         f"{result.stdout}{result.stderr}")

    def test_the_hand_written_prose_survives_generation(self):
        # §6 resolved to GENERATE this file rather than replace it, because the
        # readable artefact is the property worth preserving. If generation ever
        # started clobbering the editorial context, the file would still be
        # "in sync" and would have lost the thing it was kept for.
        doc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "compliance_rules.md")).read()
        for passage in ("not legal advice", "How this list is used",
                        "Known gap this table surfaces"):
            with self.subTest(passage=passage):
                self.assertIn(passage, doc)

    def test_both_registers_are_carried_and_are_actually_different(self):
        # The correction step 2 made to step 1's description: `rationale` and
        # `why` are two registers, not one field that drifted. If they were ever
        # collapsed, the generated table would start showing users' flag text
        # instead of the reviewer-facing justification, which is precisely the
        # readability the generated document exists to present.
        for rule in compliance_rules.RULES:
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.why.strip(), "missing documentation register")
                self.assertNotEqual(rule.rationale, rule.why,
                                    "the two registers have been collapsed into one")

    def test_a_candidate_would_be_marked_as_such_in_the_table(self):
        # Asserted on the renderer directly, since no candidate exists yet. An
        # unmarked candidate in a compliance table is the "looks authoritative,
        # is unreviewed" failure the whole protocol prevents — so the marking is
        # verified before the first candidate depends on it.
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts"))
        import generate_compliance_rules_md as gen
        from unittest.mock import patch
        fake = compliance_rules.Rule(
            id="R99", severity="High", check="test", rationale="r", why="w",
            predicate=lambda s, rp: True, status=CANDIDATE)
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (fake,)):
            table = gen.render_table()
        self.assertIn("R99", table)
        self.assertIn("CANDIDATE", table)
        self.assertIn("cannot fire", table)


class TestTheCandidateGate(unittest.TestCase):
    """
    The gate, proven in BOTH directions (design §3.2). A gate asserted only in
    its closed state might be closed for the wrong reason — because the fixture
    never tripped the rule at all, because the predicate is broken, because the
    rule was silently dropped. The same structure must fire once the status
    flips, or "it did not fire" proves nothing.

    Built while zero candidates exist, so the mechanism is testable before any
    rule depends on it.
    """

    def _probe_rule(self, status):
        # Fires on any structure at all, so "it did not fire" can only be the
        # gate — never the predicate failing to match.
        return compliance_rules.Rule(
            id="R99", severity="High",
            check="always true — gate probe",
            rationale="probe rationale", why="probe why",
            predicate=lambda s, rent_paid: True,
            status=status,
            source_url="https://example.invalid/probe",
            provision="Probe provision",
            verified_on="2026-09-09",
            reviewed_by="Test Reviewer" if status == ACTIVE else "",
            reviewed_on="2026-09-09" if status == ACTIVE else "",
        )

    def _structure(self):
        return SalaryStructure(
            ctc=1_800_000, basic=1_080_000, hra=0, lta=0,
            special_allowance=590_400, employer_pf=129_600,
            employer_nps=0, nps_opted=False)

    def test_a_candidate_cannot_fire_and_the_identical_structure_fires_once_reviewed(self):
        from unittest.mock import patch
        structure = self._structure()

        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (self._probe_rule(CANDIDATE),)):
            while_candidate = [f["rule_id"] for f in ai_layer._check_rules(structure, 0)]

        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (self._probe_rule(ACTIVE),)):
            while_reviewed = [f["rule_id"] for f in ai_layer._check_rules(structure, 0)]

        self.assertNotIn("R99", while_candidate,
                         "an unreviewed rule fired — the gate is open")
        self.assertIn("R99", while_reviewed,
                      "the SAME structure did not fire once reviewed, so the "
                      "candidate case proved nothing about the gate")

    def test_a_candidate_does_not_inflate_the_denominator(self):
        from unittest.mock import patch
        before = compliance_rules.total_active()
        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (self._probe_rule(CANDIDATE),)):
            self.assertEqual(compliance_rules.total_active(), before,
                             "a rule that cannot fire changed the denominator")
            # And the score must not improve just because an inert rule exists.
            self.assertEqual(ai_layer.compliance_pct([]), 100.0)
            self.assertEqual(ai_layer.compliance_ratio([])["rules_total"], before)

    def test_activating_a_candidate_does_move_the_denominator(self):
        # The counterpart. Without this, the test above would also pass if
        # total_active() were hardcoded.
        from unittest.mock import patch
        before = compliance_rules.total_active()
        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (self._probe_rule(ACTIVE),)):
            self.assertEqual(compliance_rules.total_active(), before + 1)


class TestTheProtocolIsEnforcedNotJustDocumented(unittest.TestCase):

    def test_the_rule_set_currently_satisfies_the_protocol(self):
        self.assertEqual(compliance_rules.protocol_violations(), [])

    def test_an_active_rule_without_a_recorded_reviewer_is_a_violation(self):
        from unittest.mock import patch
        unreviewed = compliance_rules.Rule(
            id="R98", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=ACTIVE,
            source_url="https://example.invalid/x", provision="P",
            verified_on="2026-09-09")   # no reviewed_by / reviewed_on
        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (unreviewed,)):
            problems = compliance_rules.protocol_violations()
        self.assertTrue(any("R98" in p and "reviewed_by" in p for p in problems), problems)

    def test_a_rule_without_a_citation_is_a_violation_even_as_a_candidate(self):
        # Citation is required to SHIP, not merely to activate: a candidate
        # exists so a reviewer can check it, and one with no stated source asks
        # them to verify a claim with no origin.
        from unittest.mock import patch
        uncited = compliance_rules.Rule(
            id="R97", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=CANDIDATE)
        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (uncited,)):
            problems = compliance_rules.protocol_violations()
        self.assertTrue(any("R97" in p and "source_url" in p for p in problems), problems)

    def test_the_pre_protocol_exemption_is_a_closed_named_set(self):
        # Grandfathering R1-R6 by naming them, rather than by making provenance
        # optional — an optional field would exempt every future rule too.
        self.assertEqual(compliance_rules.PRE_PROTOCOL_RULE_IDS,
                         frozenset({"R1", "R2", "R3", "R4", "R5", "R6"}))
        for rule in compliance_rules.RULES:
            if rule.id not in compliance_rules.PRE_PROTOCOL_RULE_IDS:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.source_url.strip(),
                                    "a post-protocol rule shipped with no citation")
