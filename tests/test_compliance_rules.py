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
        # NARROWED at step 5, deliberately. This asserted the WHOLE rule list
        # equalled PRE_MIGRATION, which also froze the rule set's length — a
        # property the migration never claimed and that step 5 exists to
        # change. Its real claim is that R1-R6 came through the migration
        # unaltered and in order, which is still asserted exactly, against the
        # same hand-written PRE_MIGRATION list. Rules added later must appear
        # AFTER them, so flag order for the original six cannot shift.
        self.assertEqual([(r.id, r.severity) for r in compliance_rules.RULES][:6],
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

    def test_the_first_candidate_batch_is_exactly_R7_and_R8_and_is_inert(self):
        # REPLACES test_there_are_no_candidates_yet, which asserted
        # candidate_rules() == () to pin step ordering: no rule could arrive
        # before the gate that holds it. Step 5 is that arrival, so the old
        # assertion had to go — but what it was protecting has not, and is
        # re-pinned here against the named batch rather than against emptiness.
        self.assertEqual([r.id for r in compliance_rules.candidate_rules()],
                         ["R7", "R8"])
        for rule in compliance_rules.candidate_rules():
            with self.subTest(rule=rule.id):
                self.assertFalse(rule.is_active)
                self.assertFalse(rule.implementation_is_reviewed,
                                 "a candidate shipped already marked reviewed")
                self.assertNotIn(rule.id, [r.id for r in compliance_rules.active_rules()])

    def test_the_first_batch_makes_no_statutory_claim(self):
        # The batch was drafted as CONVENTION rules deliberately: the primary
        # sources needed to back a statutory claim are unreachable from this
        # environment (see R1 and R5). A statutory rule appearing here would
        # mean that constraint was quietly dropped.
        for rule in compliance_rules.candidate_rules():
            with self.subTest(rule=rule.id):
                self.assertEqual(rule.claim_type, compliance_rules.CONVENTION)
                self.assertTrue(rule.basis.strip())
                self.assertFalse(rule.provision.strip())
                self.assertFalse(rule.source_url.strip())


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
            claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/probe",
            provision="Probe provision",
            citation_checked_on="2026-09-09",
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

    def test_the_rule_set_has_exactly_one_known_open_violation(self):
        # See test_the_only_open_violation_is_the_known_R5_citation.
        self.assertEqual(len(compliance_rules.protocol_violations()), 1)

    def test_an_active_rule_without_a_recorded_reviewer_is_a_violation(self):
        from unittest.mock import patch
        unreviewed = compliance_rules.Rule(
            id="R98", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=ACTIVE,
            claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/x", provision="P",
            citation_checked_on="2026-09-09")   # citation checked, nobody reviewed
        with patch.object(compliance_rules, "RULES",
                          compliance_rules.RULES + (unreviewed,)):
            problems = compliance_rules.protocol_violations()
        self.assertTrue(any("R98" in p and "reviewed" in p for p in problems), problems)

    def test_a_rule_without_a_citation_is_a_violation_even_as_a_candidate(self):
        # Citation is required to SHIP, not merely to activate: a candidate
        # exists so a reviewer can check it, and one with no stated source asks
        # them to verify a claim with no origin.
        from unittest.mock import patch
        uncited = compliance_rules.Rule(
            id="R97", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=CANDIDATE,
            claim_type=compliance_rules.STATUTORY)
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
                    if rule.claim_type == compliance_rules.STATUTORY:
                        self.assertTrue(rule.source_url.strip(),
                                        "a statutory rule shipped with no citation")
                    else:
                        self.assertTrue(rule.basis.strip(),
                                        "a convention rule shipped with no stated basis")


class TestTheTwoClaimsAreSeparate(unittest.TestCase):
    """
    "The cited provision exists and says this" and "this predicate correctly
    implements it" are different claims. Only the first is checkable by
    fetching a document; the second needs someone who can interpret regulatory
    intent. Conflating them would let citation-checking masquerade as review,
    which is the one substitution the protocol exists to prevent.
    """

    def test_a_checked_citation_is_not_a_reviewed_implementation(self):
        cited_only = compliance_rules.Rule(
            id="R96", severity="High", check="c", rationale="r", why="w",
            predicate=lambda s, rp: True, status=CANDIDATE,
            claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/x", provision="P",
            citation_checked_on="2026-09-09",
            # An instrument is required for a citation to read as verified —
            # see TestTheGoverningInstrumentCheck. This test is about the
            # citation-vs-review distinction, so it supplies a valid one.
            instrument="Some Act, 2020",
            instrument_status=compliance_rules.IN_FORCE)
        self.assertTrue(cited_only.citation_is_checked)
        self.assertFalse(cited_only.implementation_is_reviewed,
                         "a fetched source must never count as human review")

    def test_a_convention_rule_needs_a_basis_not_a_citation(self):
        # Demanding a statute from a convention rule pressures whoever writes it
        # into attaching a provision that does not say what the rule claims —
        # evidence that looks stronger than it is.
        from unittest.mock import patch
        no_basis = compliance_rules.Rule(
            id="R95", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=CANDIDATE,
            claim_type=compliance_rules.CONVENTION)
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (no_basis,)):
            problems = compliance_rules.protocol_violations()
        self.assertTrue(any("R95" in p and "basis" in p for p in problems), problems)
        self.assertFalse(any("R95" in p and "source_url" in p for p in problems),
                         "a convention rule was asked for a statute")

    def test_a_convention_rule_citing_a_provision_is_flagged(self):
        # Either it is statutory and mislabelled, or it is citing a section that
        # does not require what it claims. Both are worth surfacing.
        from unittest.mock import patch
        mislabelled = compliance_rules.Rule(
            id="R94", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=CANDIDATE,
            claim_type=compliance_rules.CONVENTION,
            basis="industry practice", provision="Section 999")
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (mislabelled,)):
            problems = compliance_rules.protocol_violations()
        self.assertTrue(any("R94" in p for p in problems), problems)

    def test_the_existing_six_are_classified_by_what_their_own_text_claims(self):
        # R1 says "violating the Code on Wages 2025 requirement"; R2 says
        # "unusual ... confirm this isn't an oversight". Only two of six assert
        # that the law requires something.
        by_id = {r.id: r.claim_type for r in compliance_rules.RULES}
        self.assertEqual(by_id["R1"], compliance_rules.STATUTORY)
        self.assertEqual(by_id["R5"], compliance_rules.STATUTORY)
        for rid in ("R2", "R3", "R4", "R6"):
            self.assertEqual(by_id[rid], compliance_rules.CONVENTION)


class TestTheFourProtocolChecks(unittest.TestCase):
    """
    Each check proven in BOTH directions — a rule that satisfies it must not
    flag, and one that misses it must. A one-sided assertion cannot tell a
    working check from a check that never fires.
    """

    def _rule(self, rid, **kw):
        base = dict(id=rid, severity="Low", check="c", rationale="r", why="w",
                    predicate=lambda s, rp: False, status=CANDIDATE,
                    claim_type=compliance_rules.CONVENTION,
                    # Satisfies CHECK 6 so each test below isolates its own
                    # check rather than also tripping the threshold-origin one.
                    threshold_origin="probe: no numeric threshold")
        base.update(kw)
        return compliance_rules.Rule(**base)

    def _violations_with(self, rule):
        from unittest.mock import patch
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (rule,)):
            return compliance_rules.protocol_violations()

    # --- CHECK 2: statutory rule with no citation attempt recorded ----------

    def test_statutory_rule_with_no_citation_attempt_flags(self):
        r = self._rule("R90", claim_type=compliance_rules.STATUTORY,
                       source_url="https://example.invalid/x", provision="P",
                       citation_checked_on="")
        problems = self._violations_with(r)
        self.assertTrue(any("R90" in p and "citation_checked_on" in p for p in problems),
                        problems)

    def test_statutory_rule_with_a_check_date_does_not_flag(self):
        r = self._rule("R90", claim_type=compliance_rules.STATUTORY,
                       source_url="https://example.invalid/x", provision="P",
                       citation_checked_on="2026-09-09")
        self.assertFalse(any("R90" in p and "citation_checked_on" in p
                             for p in self._violations_with(r)))

    def test_an_unresolved_attempt_satisfies_the_check_but_is_not_a_check(self):
        # "Tried and could not reach a primary source" is a recorded outcome and
        # satisfies the protocol. It must NOT read as a verified citation — the
        # two are different facts and the schema distinguishes them.
        r = self._rule("R90", claim_type=compliance_rules.STATUTORY,
                       source_url="https://example.invalid/x", provision="P",
                       citation_checked_on=compliance_rules.UNRESOLVED + "403 from source")
        self.assertFalse(any("R90" in p and "citation_checked_on" in p
                             for p in self._violations_with(r)))
        self.assertFalse(r.citation_is_checked, "an unresolved attempt read as verified")
        self.assertTrue(r.citation_attempt_unresolved)

    # --- CHECK 3: convention rule with no stated basis ----------------------

    def test_convention_rule_with_empty_basis_flags(self):
        problems = self._violations_with(self._rule("R91", basis=""))
        self.assertTrue(any("R91" in p and "basis" in p for p in problems), problems)

    def test_convention_rule_with_a_basis_does_not_flag(self):
        problems = self._violations_with(self._rule("R91", basis="industry practice"))
        self.assertFalse(any("R91" in p and "basis" in p for p in problems), problems)

    # --- CHECKS 1 and 4 still fire after the restructure --------------------

    def test_statutory_rule_missing_provision_still_flags(self):
        r = self._rule("R92", claim_type=compliance_rules.STATUTORY,
                       source_url="https://example.invalid/x",
                       citation_checked_on="2026-09-09")
        self.assertTrue(any("R92" in p and "provision" in p
                            for p in self._violations_with(r)))

    def test_convention_rule_carrying_a_provision_still_flags(self):
        r = self._rule("R93", basis="industry practice", provision="Section 999")
        self.assertTrue(any("R93" in p for p in self._violations_with(r)))

    # --- the shipped rule set satisfies all four ----------------------------

    def test_the_only_open_violation_is_the_known_R5_citation(self):
        """
        R5 is KNOWINGLY in violation, and that is pinned rather than silenced.

        Its citation points at the Income-tax Act, 1961, which the 2025 Act
        replaced from 1 April 2026. The rule stays ACTIVE on purpose: the
        underlying Rs 7.5L composite ceiling is very likely still law, and
        removing a real compliance check because its citation went stale would
        trade a documentation problem for a coverage gap.

        Pinned as EXACTLY one violation so the known gap stays visible AND any
        additional violation still fails the build. An assertEqual([]) here
        would have required either suppressing this or pretending it is fixed.
        """
        violations = compliance_rules.protocol_violations()
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("R5", violations[0])
        self.assertIn("superseded", violations[0])

    def test_both_statutory_rules_record_a_citation_attempt(self):
        # R1 and R5 are grandfathered on having a backdated REVIEWER, not on
        # being citable. Each must record an outcome — a date or an unresolved
        # attempt — never silence.
        for rule in compliance_rules.RULES:
            if rule.claim_type == compliance_rules.STATUTORY:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.citation_checked_on.strip(),
                                    f"{rule.id} asserts the law requires something "
                                    f"and records no attempt to verify it")
                    self.assertTrue(rule.provision.strip())
                    self.assertTrue(rule.source_url.strip())

    def test_every_convention_rule_states_its_basis(self):
        for rule in compliance_rules.RULES:
            if rule.claim_type == compliance_rules.CONVENTION:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.basis.strip())


class TestTheGoverningInstrumentCheck(unittest.TestCase):
    """
    A citation can match its source perfectly and still point at a repealed
    Act. That combination is the worst case: it reads as verified while citing
    dead law, which is strictly worse than an unresolved citation because an
    unresolved one is visibly a gap.
    """

    def _rule(self, rid, **kw):
        base = dict(id=rid, severity="Low", check="c", rationale="r", why="w",
                    predicate=lambda s, rp: False, status=CANDIDATE,
                    claim_type=compliance_rules.STATUTORY,
                    source_url="https://example.invalid/x", provision="P",
                    citation_checked_on="2026-09-09",
                    instrument="Some Act, 1961",
                    instrument_status=compliance_rules.IN_FORCE,
                    threshold_origin="probe: no numeric threshold")
        base.update(kw)
        return compliance_rules.Rule(**base)

    def _violations_with(self, rule):
        from unittest.mock import patch
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (rule,)):
            return compliance_rules.protocol_violations()

    def test_a_checked_citation_on_a_superseded_act_does_not_read_as_verified(self):
        # THE CORE OF THIS FIX. Text matched, date recorded — and still not
        # verified, because the Act it matched no longer governs.
        superseded = self._rule("R80", instrument_status=compliance_rules.SUPERSEDED)
        self.assertFalse(superseded.citation_is_checked,
                         "a citation into a repealed Act reported as verified")
        self.assertTrue(superseded.cites_superseded_law)

    def test_the_same_citation_on_an_in_force_act_does_read_as_verified(self):
        # The other side: without this, the assertion above would also pass if
        # citation_is_checked simply always returned False.
        self.assertTrue(self._rule("R80").citation_is_checked)

    def test_an_active_rule_citing_a_superseded_act_is_a_violation(self):
        active_superseded = self._rule("R81", status=ACTIVE,
                                       instrument_status=compliance_rules.SUPERSEDED,
                                       reviewed_by="R", reviewed_on="2026-09-09")
        problems = self._violations_with(active_superseded)
        self.assertTrue(any("R81" in p and "superseded" in p for p in problems), problems)

    def test_a_statutory_rule_with_no_named_instrument_is_a_violation(self):
        # A section number without an Act is not a citation. "17(2)(vii)" means
        # different things in different statutes, which is exactly how a
        # citation survives a repeal while silently changing meaning.
        problems = self._violations_with(self._rule("R82", instrument=""))
        self.assertTrue(any("R82" in p and "instrument" in p for p in problems), problems)

    def test_a_named_in_force_instrument_does_not_flag(self):
        problems = self._violations_with(self._rule("R83"))
        self.assertFalse(any("R83" in p for p in problems), problems)

    def test_both_statutory_rules_name_their_instrument(self):
        for rule in compliance_rules.RULES:
            if rule.claim_type == compliance_rules.STATUTORY:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.instrument.strip())

    def test_R5_is_recorded_as_citing_superseded_law(self):
        r5 = next(r for r in compliance_rules.RULES if r.id == "R5")
        self.assertTrue(r5.cites_superseded_law)
        self.assertFalse(r5.citation_is_checked)
        self.assertIn("1961", r5.instrument)
        # The successor provision must NOT have been guessed.
        self.assertNotIn("2025", r5.provision,
                         "a successor section number appears to have been invented")


class TestTheFirstBatchesBasesAreTrueNotJustStated(unittest.TestCase):
    """
    A convention rule's `basis` is the whole of its evidence — there is no
    citation behind it to fall back on. Prose alone makes it unfalsifiable:
    a plausible-sounding basis and a true one read identically.

    R7 and R8 were drafted with bases consisting only of claims about THIS
    repository, precisely so they could be checked rather than believed. These
    tests check them. If a refactor makes one of these claims false, the rule's
    justification has evaporated and a reviewer must be told — silently keeping
    the rule would leave it resting on a reason that no longer holds.
    """

    def _rule(self, rule_id):
        return next(r for r in compliance_rules.RULES if r.id == rule_id)

    # ---- R7's basis --------------------------------------------------------

    def test_R7_claim_1_tax_ignores_nps_opted_entirely(self):
        # "compute_tax() subtracts employer_nps in both regimes without ever
        # reading nps_opted." If this became false, R7 would be pointing at a
        # contradiction that no longer has any consequence.
        import tax_engine
        for regime in ("old", "new"):
            opted = SalaryStructure(
                ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
                special_allowance=500_000, employer_pf=120_000,
                employer_nps=80_000, nps_opted=True)
            not_opted = SalaryStructure(
                ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
                special_allowance=500_000, employer_pf=120_000,
                employer_nps=80_000, nps_opted=False)
            with self.subTest(regime=regime):
                self.assertEqual(
                    tax_engine.taxable_income_for_structure(opted, regime, 300_000, "metro"),
                    tax_engine.taxable_income_for_structure(not_opted, regime, 300_000, "metro"),
                    "nps_opted now changes taxable income — R7's basis claim 1 "
                    "is false and the rule needs redrafting")

    def test_R7_claim_2_the_builder_cannot_produce_the_flagged_pair(self):
        # "derive_nps() returns 0.0 when opted_in is false, so build_structure()
        # can never produce employer_nps > 0 with nps_opted false."
        import tax_engine
        for regime in ("old", "new"):
            built = tax_engine.build_structure(
                ctc=2_000_000, basic_pct=0.50, hra_pct_of_remaining=0.40,
                lta=0.0, regime=regime, nps_opted=False)
            with self.subTest(regime=regime):
                self.assertEqual(built.employer_nps, 0.0)
                self.assertFalse(self._rule("R7").predicate(built, 0),
                                 "a structure from this tool's own builder trips "
                                 "R7 — the rule would flag ordinary output")

    def test_R7_fires_on_the_externally_reachable_pair(self):
        # The counterpart: the rule must actually match the case it describes,
        # or claims 1 and 2 would be true of a predicate that catches nothing.
        inconsistent = SalaryStructure(
            ctc=2_000_000, basic=1_000_000, hra=300_000, lta=0,
            special_allowance=500_000, employer_pf=120_000,
            employer_nps=80_000, nps_opted=False)
        self.assertTrue(self._rule("R7").predicate(inconsistent, 0))

    # ---- R8's basis --------------------------------------------------------

    def test_R8_claim_the_share_of_ctc_rules_still_fire_on_an_unreconciled_row(self):
        # "R1 (basic/ctc) and R4 (lta/ctc) still compute and still flag against
        # a denominator that does not describe the structure." That consequence
        # is the entire reason R8 is worth having.
        unreconciled = SalaryStructure(
            ctc=5_000_000, basic=400_000, hra=200_000, lta=600_000,
            special_allowance=100_000, employer_pf=48_000,
            employer_nps=0, nps_opted=False)     # components sum to ~1.35L, not 50L
        self.assertTrue(self._rule("R8").predicate(unreconciled, 0),
                        "R8 does not flag a structure that plainly does not reconcile")
        fired = [f["rule_id"] for f in ai_layer._check_rules(unreconciled, rent_paid=0)]
        self.assertIn("R1", fired)
        self.assertIn("R4", fired)

    def test_R8_does_not_fire_on_a_structure_this_tool_built(self):
        # build_structure() derives special_allowance as the residual, so its
        # output reconciles by construction. A meta-rule that flags the tool's
        # own output would be noise on every well-formed row.
        import tax_engine
        for ctc in (600_000, 2_000_000, 5_000_000):
            built = tax_engine.build_structure(
                ctc=ctc, basic_pct=0.50, hra_pct_of_remaining=0.40,
                lta=50_000, regime="old", nps_opted=True)
            with self.subTest(ctc=ctc):
                self.assertFalse(self._rule("R8").predicate(built, 0),
                                 "R8 flags a structure built by this tool")

    def test_R8_tolerance_absorbs_rounding_but_not_a_missing_component(self):
        # The tolerance is a judgement, and its two edges are what a reviewer
        # would want to move. Pinning both makes any change to it visible.
        base = dict(ctc=1_000_000, basic=500_000, hra=200_000, lta=0,
                    employer_pf=60_000, employer_nps=0, nps_opted=False)
        # Off by Rs 2 — rounding scale, must not flag (tolerance = Rs 5,000).
        near = SalaryStructure(special_allowance=240_000 - 2, **base)
        self.assertFalse(self._rule("R8").predicate(near, 0))
        # Off by Rs 20,000 — a missing component's scale, must flag.
        far = SalaryStructure(special_allowance=240_000 - 20_000, **base)
        self.assertTrue(self._rule("R8").predicate(far, 0))

    def test_R8_ignores_a_zero_ctc_rather_than_dividing_by_it(self):
        empty = SalaryStructure(
            ctc=0, basic=0, hra=0, lta=0, special_allowance=0,
            employer_pf=0, employer_nps=0, nps_opted=False)
        self.assertFalse(self._rule("R8").predicate(empty, 0))


if __name__ == "__main__":
    unittest.main()


class TestTheThresholdOriginQuestionIsAsked(unittest.TestCase):
    """
    CHECK 6, added after the first candidate batch. The CONVENTION/STATUTORY
    split was meant to route around the primary-source access problem; drafting
    R7 and R8 showed it RELOCATED the risk — a convention rule whose threshold
    is really a statutory figure ships a statutory number with no citation, and
    nothing automated can detect that, because detection needs to know which
    numbers are statutory.

    So this check asserts something deliberately weaker than correctness: that
    the question was ANSWERED, not that the answer is right. Both directions
    are proven, because a check asserted only in its failing state might be
    failing for an unrelated reason.
    """

    def _rule(self, rid, **kw):
        base = dict(id=rid, severity="Low", check="c", rationale="r", why="w",
                    predicate=lambda s, rp: False, status=CANDIDATE,
                    claim_type=compliance_rules.CONVENTION, basis="b")
        base.update(kw)
        return compliance_rules.Rule(**base)

    def _violations_with(self, rule):
        from unittest.mock import patch
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (rule,)):
            return compliance_rules.protocol_violations()

    def test_a_rule_that_does_not_say_where_its_number_came_from_is_a_violation(self):
        problems = self._violations_with(self._rule("R90", threshold_origin=""))
        self.assertTrue(any("R90" in p and "threshold_origin" in p for p in problems),
                        problems)

    def test_a_rule_that_answers_the_question_does_not_flag(self):
        problems = self._violations_with(
            self._rule("R91", threshold_origin="not statutory; an engineering judgement"))
        self.assertFalse(any("R91" in p for p in problems), problems)

    def test_the_question_is_asked_of_statutory_rules_too(self):
        # Not restricted to convention rules even though that is where the gap
        # was found: a statutory rule can carry a number its provision does not
        # actually specify, and the same question catches it.
        problems = self._violations_with(self._rule(
            "R92", claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/x", provision="P",
            citation_checked_on="2026-09-09", instrument="Some Act, 1961",
            instrument_status=compliance_rules.IN_FORCE, threshold_origin=""))
        self.assertTrue(any("R92" in p and "threshold_origin" in p for p in problems),
                        problems)

    def test_whitespace_is_not_an_answer(self):
        problems = self._violations_with(self._rule("R93", threshold_origin="   \n  "))
        self.assertTrue(any("R93" in p and "threshold_origin" in p for p in problems),
                        problems)

    def test_the_grandfathered_six_are_not_retroactively_flagged(self):
        # Adding step 0 does not reopen R1-R6. The pre-protocol set is closed
        # and named; this check applies to everything drafted after it.
        problems = compliance_rules.protocol_violations()
        for rid in compliance_rules.PRE_PROTOCOL_RULE_IDS:
            with self.subTest(rule=rid):
                self.assertFalse(any(rid in p and "threshold_origin" in p
                                     for p in problems), problems)

    def test_every_post_protocol_rule_has_actually_answered_it(self):
        # The live assertion, not a probe: R7 and R8 must carry real answers.
        for rule in compliance_rules.RULES:
            if rule.id not in compliance_rules.PRE_PROTOCOL_RULE_IDS:
                with self.subTest(rule=rule.id):
                    self.assertTrue(rule.threshold_origin.strip(),
                                    "a post-protocol rule advanced without "
                                    "answering the threshold-origin question")
