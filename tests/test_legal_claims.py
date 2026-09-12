"""
The legal claim inventory (LEGAL_CLAIM_INVENTORY_DESIGN.md, Phase 2.4).

Step 2 builds the mechanism over an EMPTY inventory and proves it with probes,
the same way 2.2 built the candidate gate and proved it in both directions
while zero candidates existed. A mechanism first tested by the thing that
depends on it cannot be shown to have been working beforehand.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compliance_rules
import legal_claims
import provenance
from legal_claims import Claim


def _probe(**kw):
    base = dict(id="C1", module="tax_engine", symbol="CESS_RATE",
                describes="probe", asserted_value=0.04,
                claim_type=provenance.CONVENTION, basis="probe basis",
                threshold_origin="probe: not statutory")
    base.update(kw)
    return Claim(**base)


class TestTheMechanismWorksIndependentlyOfTheInventory(unittest.TestCase):
    """
    REPLACES two step-2 tests that asserted CLAIMS == () and that both reports
    came back empty. They pinned the step ordering — the mechanism exists before
    anything depends on it — and step 3 is that arrival, so the assertions had
    to go. Same shape as 2.2's test_there_are_no_candidates_yet.

    What they protected has not gone: the reports must still behave correctly
    over an empty collection, which is now asserted by patching one in rather
    than by relying on the real inventory being empty. That is the stronger
    version — it keeps holding once the inventory has 25 entries.
    """

    def test_both_reports_run_clean_over_an_empty_inventory(self):
        from unittest.mock import patch
        with patch.object(legal_claims, "CLAIMS", ()):
            self.assertEqual(legal_claims.evidence_findings(), [])
            self.assertEqual(legal_claims.drift_findings(), [])


class TestAClaimHasNoInertState(unittest.TestCase):
    """
    Design §4.4, the phase's central finding. A rule can be inert; a constant
    cannot. If a Claim could ever report itself not-live, the whole premise
    that `unverified` is a live risk rather than a safe holding pen would be
    quietly false.
    """

    def test_a_claim_is_always_live(self):
        self.assertTrue(_probe().is_live)

    def test_no_status_field_exists_to_make_a_claim_inert(self):
        # A candidate gate cannot be bolted on later by accident: there is no
        # field to set. This asserts the absence deliberately, because absences
        # are what this project keeps failing to notice.
        self.assertFalse(hasattr(_probe(), "status"))
        self.assertFalse(hasattr(_probe(), "is_active"))

    def test_an_unverified_claim_is_reported_immediately(self):
        from unittest.mock import patch
        with patch.object(legal_claims, "CLAIMS", (_probe(),)):
            findings = legal_claims.evidence_findings()
        self.assertTrue(any("C1" in f and "reviewed" in f for f in findings), findings)

    def test_the_message_names_what_a_reviewer_would_be_asserting(self):
        # A rule's reviewer asserts the predicate implements the claim; a
        # claim's reviewer asserts the value matches the source. A message
        # naming the wrong one sends a reviewer to the wrong task.
        from unittest.mock import patch
        with patch.object(legal_claims, "CLAIMS", (_probe(),)):
            findings = legal_claims.evidence_findings()
        self.assertTrue(any("verified the value against the cited source" in f
                            for f in findings), findings)
        rule_findings = compliance_rules.protocol_violations()
        self.assertFalse(any("verified the value against the cited source" in f
                             for f in rule_findings),
                         "rule findings picked up claim vocabulary")


class TestTheValueCheckComparesTwoRealCopies(unittest.TestCase):
    """
    Design §4.5. The duplicated value is the mechanism: a claim reading the live
    constant could not drift, and could not check anything either.
    """

    def test_a_matching_value_does_not_drift(self):
        import tax_engine
        self.assertFalse(_probe(asserted_value=tax_engine.CESS_RATE).value_has_drifted)

    def test_a_changed_value_drifts(self):
        self.assertTrue(_probe(asserted_value=0.05).value_has_drifted)

    def test_drift_is_reported_with_both_numbers_and_the_fix(self):
        from unittest.mock import patch
        with patch.object(legal_claims, "CLAIMS", (_probe(asserted_value=0.05),)):
            findings = legal_claims.drift_findings()
        self.assertEqual(len(findings), 1)
        message = findings[0]
        self.assertIn("0.04", message)   # what the code says now
        self.assertIn("0.05", message)   # what was recorded as verified
        self.assertIn("citation_checked_on", message,
                      "the message does not say to re-verify, only to update")

    def test_updating_the_value_alone_is_named_as_the_wrong_fix(self):
        # The realistic mistake: someone silences this by copying the new
        # number across without re-checking the source, reinstating exactly the
        # state the check exists to find.
        from unittest.mock import patch
        with patch.object(legal_claims, "CLAIMS", (_probe(asserted_value=0.05),)):
            message = legal_claims.drift_findings()[0]
        self.assertIn("updating the value", message.lower())

    def test_the_check_reads_the_code_live_not_a_cached_import(self):
        from unittest.mock import patch
        import tax_engine
        claim = _probe(asserted_value=0.04)
        self.assertFalse(claim.value_has_drifted)
        with patch.object(tax_engine, "CESS_RATE", 0.06):
            self.assertTrue(claim.value_has_drifted,
                            "the claim is reading a snapshot, not the live value")

    def test_a_claim_pointing_at_a_deleted_symbol_says_so_by_name(self):
        # Distinct failure from drift: a claim describing code that no longer
        # exists is a claim about nothing, and a bare AttributeError would not
        # say which claim or what to do.
        claim = _probe(symbol="NO_SUCH_CONSTANT")
        with self.assertRaises(legal_claims.SymbolMissingError) as caught:
            claim.live_value()
        message = str(caught.exception)
        self.assertIn("C1", message)
        self.assertIn("tax_engine.NO_SUCH_CONSTANT", message)


class TestTheSharedModelIsNotDuplicatedInLogic(unittest.TestCase):

    def test_rule_and_claim_declare_the_same_provenance_fields(self):
        # Python 3.9 has no dataclass kw_only and cannot inherit a field list
        # onto a class with required fields, so these are declared twice. The
        # duplication is accepted and CHECKED rather than hand-waved — promised
        # when the mixin was extracted, asserted here.
        import dataclasses
        shared = {"source_url", "provision", "citation_checked_on", "instrument",
                  "instrument_status", "basis", "threshold_origin",
                  "reviewed_by", "reviewed_on", "claim_type"}
        rule_fields = {f.name for f in dataclasses.fields(compliance_rules.Rule)}
        claim_fields = {f.name for f in dataclasses.fields(Claim)}
        self.assertEqual(shared - rule_fields, set(), "Rule lost a provenance field")
        self.assertEqual(shared - claim_fields, set(), "Claim lost a provenance field")

    def test_both_carriers_run_through_the_same_checker(self):
        self.assertIs(legal_claims.provenance_violations,
                      provenance.provenance_violations)
        self.assertIs(compliance_rules.provenance_violations,
                      provenance.provenance_violations)

    def test_a_claim_carries_no_rule_concepts(self):
        for absent in ("predicate", "severity", "rationale", "why", "check"):
            with self.subTest(field=absent):
                self.assertFalse(hasattr(_probe(), absent),
                                 f"Claim picked up the rule concept {absent!r}")


if __name__ == "__main__":
    unittest.main()


class TestTheFirstBatchIsTheFourTaxEngineFigures(unittest.TestCase):
    """
    Design §5. Deliberately small — prove the shape on four before committing
    to ~25, the same discipline as 2.2's first candidate batch.
    """

    def _claim(self, cid):
        return next(c for c in legal_claims.CLAIMS if c.id == cid)

    def test_the_batch_is_exactly_the_four_named_figures(self):
        # NARROWED at Stage A: this compared the WHOLE inventory, which also
        # froze its length — a property the first batch never claimed. Third
        # time this exact shape has appeared (the R1-R6 migration test and the
        # empty-inventory tests were the first two): a test written while a
        # collection held one batch silently becomes a test about the whole
        # collection. Its real claim is that the first four came through
        # unaltered and in order, which is still asserted exactly.
        self.assertEqual([(c.id, c.symbol) for c in legal_claims.CLAIMS][:4],
                         [("TE1", "NEW_REGIME_SLABS"),
                          ("TE2", "OLD_REGIME_SLABS"),
                          ("TE3", "STANDARD_DEDUCTION"),
                          ("TE4", "NPS_80CCD2_CAP_PCT")])

    def test_every_recorded_value_matches_the_live_constant(self):
        # The claims must describe the code as it actually is on the day they
        # are written, or the drift check starts life already failing and gets
        # silenced instead of trusted.
        self.assertEqual(legal_claims.drift_findings(), [])

    def test_all_four_are_unverified_and_that_is_the_batch_working(self):
        # Recorded as the expected outcome, not defensively. The visible truth
        # is that four of the most load-bearing numbers in this system rest on
        # nothing recorded, and making that visible IS the deliverable.
        for claim in legal_claims.CLAIMS:
            with self.subTest(claim=claim.id):
                self.assertFalse(claim.citation_is_checked)
                self.assertFalse(claim.implementation_is_reviewed)
                self.assertTrue(claim.is_live, "an unverified claim is a LIVE risk")

    def test_the_evidence_report_names_every_claim(self):
        findings = legal_claims.evidence_findings()
        for claim in legal_claims.CLAIMS:
            with self.subTest(claim=claim.id):
                self.assertTrue(any(claim.id in f for f in findings),
                                "a claim with no verification went unreported")

    def test_the_two_citation_states_are_kept_apart(self):
        # "Nobody tried" and "tried and could not" are different facts, and the
        # second is worse. TE1-TE3's values were never attempted; TE4's were,
        # against secondary sources this project will not treat as verification.
        for cid in ("TE1", "TE2", "TE3"):
            with self.subTest(claim=cid):
                self.assertEqual(self._claim(cid).citation_checked_on, "")
                self.assertFalse(self._claim(cid).citation_attempt_unresolved)
        self.assertTrue(self._claim("TE4").citation_attempt_unresolved)

    def test_no_successor_provision_was_invented(self):
        # Only TE4 carries a provision, and only because the repository already
        # records that mapping in two places. The others carry none, because
        # none is recorded anywhere — and an invented one would read as
        # evidence, which is worse than a visible gap.
        # Scoped to this batch, for the reason above: OP1 legitimately carries
        # a provision, taken from R1's record of the same proposition and
        # recorded as such. Widening this to the whole inventory would make it
        # assert something it was never about.
        with_provision = [c.id for c in legal_claims.CLAIMS
                          if c.id.startswith("TE") and c.provision.strip()]
        self.assertEqual(with_provision, ["TE4"])

    def test_a_missing_citation_message_does_not_claim_a_provision_exists(self):
        # Found by running the report: the message read "cites a provision but
        # records no citation_checked_on" for claims citing no provision at all.
        # Written for rules, false for claims.
        findings = legal_claims.evidence_findings()
        self.assertFalse(any("cites a provision but" in f for f in findings),
                         "the report tells a reader a provision exists when none does")

    def test_every_claim_answers_the_threshold_origin_question(self):
        for claim in legal_claims.CLAIMS:
            with self.subTest(claim=claim.id):
                self.assertTrue(claim.threshold_origin.strip())


class TestTheLegalReviewQueue(unittest.TestCase):
    """
    Phase 2.4 step 5 (design §4.6). One prioritized queue over BOTH provenance
    carriers — the payoff of step 1's extraction. Before it, a rule's staleness
    and a constant's staleness were different kinds of thing in different
    places and could not be ranked against each other.
    """

    def _run(self, *args):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(
            [sys.executable, "-B",
             os.path.join(root, "scripts", "generate_legal_review_queue.py"), *args],
            capture_output=True, text=True, cwd=root)

    def _queue(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "LEGAL_REVIEW_QUEUE.md")) as f:
            return f.read()

    def test_the_committed_queue_matches_the_generator(self):
        result = self._run("--check")
        self.assertEqual(result.returncode, 0,
                         f"queue is stale.\n{result.stdout}{result.stderr}")

    def test_it_covers_both_carriers_in_one_list(self):
        queue = self._queue()
        self.assertIn("### R5", queue, "no compliance rule reached the queue")
        self.assertIn("### TE1", queue, "no legal claim reached the queue")
        self.assertIn("compliance rules and", queue)

    def test_the_worst_item_is_first_not_the_easiest(self):
        # Ranked by how badly a reader could be misled, never by effort. R5
        # cites a repealed Act — it reads as verified while locating nothing,
        # which is worse than a visibly-missing citation.
        queue = self._queue()
        first = queue.index("### R5")
        for other in ("### TE1", "### TE2", "### TE3", "### R1", "### TE4"):
            with self.subTest(item=other):
                self.assertLess(first, queue.index(other),
                                "a lesser item outranked the superseded-law item")

    def test_every_live_rule_and_every_claim_is_accounted_for(self):
        queue = self._queue()
        for claim in legal_claims.CLAIMS:
            with self.subTest(item=claim.id):
                self.assertIn(f"### {claim.id}", queue,
                              "a live legal claim is missing from the queue")
        for rule in compliance_rules.RULES:
            if rule.is_live and not rule.implementation_is_reviewed:
                with self.subTest(item=rule.id):
                    self.assertIn(f"### {rule.id}", queue)

    def test_an_inert_candidate_rule_never_appears(self):
        # A candidate cannot fire, so it cannot mislead anyone, so it does not
        # belong in a queue about what might be wrong in production. R7 and R8
        # are the live check that the is_live filter is doing work.
        queue = self._queue()
        for rule in compliance_rules.RULES:
            if not rule.is_live:
                with self.subTest(item=rule.id):
                    self.assertNotIn(f"### {rule.id}", queue,
                                     "an inert candidate leaked into the queue")

    def test_the_queue_says_plainly_that_it_is_not_evidence(self):
        # §4.6's hard requirement. A list of legal-sounding findings that does
        # not say what it is would be read as research.
        self.assertIn("Nothing in this file is evidence", self._queue())

    def test_the_queue_states_the_never_decide_boundary(self):
        queue = self._queue()
        self.assertIn("may never decide", queue)
        self.assertIn("marking something verified is a human act", queue)

    def test_the_queue_says_why_it_does_not_fetch(self):
        # Narrower than §4.6 first described, and recorded rather than quietly
        # delivered as if it were the whole thing.
        queue = self._queue()
        self.assertIn("does not fetch anything, on purpose", queue)
        self.assertIn("403", queue)

    def test_it_distinguishes_never_attempted_from_attempted_and_unresolved(self):
        queue = self._queue()
        self.assertIn("_never attempted_", queue)
        self.assertIn("unresolved:", queue)


class TestStageAOptimizerClaims(unittest.TestCase):
    """
    INVENTORY_EXPANSION_DESIGN.md §4 Stage A. Two claims, no new mechanism,
    first because OP1 is the claim this whole phase was named after.
    """

    def _claim(self, cid):
        return next(c for c in legal_claims.CLAIMS if c.id == cid)

    def test_stage_a_added_exactly_two_claims_after_the_first_batch(self):
        # FOURTH instance of the recurring shape, and written one message after
        # the pattern was named — see INVENTORY_EXPANSION_DESIGN.md §7. Scoped
        # to this stage's own claims, which is what it was ever about.
        self.assertEqual([c.id for c in legal_claims.CLAIMS if c.id.startswith("OP")],
                         ["OP1", "OP2"])
        self.assertEqual([c.id for c in legal_claims.CLAIMS][:6],
                         ["TE1", "TE2", "TE3", "TE4", "OP1", "OP2"],
                         "the first two batches moved or reordered")

    def test_both_values_match_the_live_constants(self):
        import optimizer
        self.assertEqual(self._claim("OP1").asserted_value, optimizer.BASIC_PCT_MIN)
        self.assertEqual(self._claim("OP2").asserted_value, optimizer.BASIC_PCT_MAX)
        self.assertEqual(legal_claims.drift_findings(), [])

    def test_the_floor_is_statutory_and_the_ceiling_is_not(self):
        # optimizer.py's own docstring makes exactly this distinction — "one of
        # these is statute, not assumption". Recording it is the point of
        # inventorying the pair together rather than only the floor.
        self.assertEqual(self._claim("OP1").claim_type, provenance.STATUTORY)
        self.assertEqual(self._claim("OP2").claim_type, provenance.CONVENTION)

    def test_the_floor_is_not_verified_despite_the_file_saying_verified(self):
        # optimizer.py says "Verified against multiple independent sources on
        # 2026-09-01" and names none of them. Under §5.1 that is evidence a
        # check happened, not a trail anyone can redo.
        op1 = self._claim("OP1")
        self.assertFalse(op1.citation_is_checked)
        self.assertTrue(op1.citation_attempt_unresolved)
        self.assertIn("names NONE of them", op1.citation_checked_on)

    def test_no_citation_trail_was_backdated_onto_an_older_check(self):
        # The easy mistake §5.1 names: find a better source today, credit it to
        # a check made earlier on different evidence, and the claim reads as
        # verified on a basis nobody used.
        op1 = self._claim("OP1")
        self.assertIn("NOT backdated", op1.citation_checked_on)
        self.assertFalse(op1.citation_is_checked,
                         "a 2026-09-01 check was upgraded to verified")

    def test_the_ceiling_records_its_derivation_unlike_R2_and_R4(self):
        # R2's Rs 6L and R4's 10% are recorded as UNKNOWN because nobody wrote
        # down where they came from. BASIC_PCT_MAX is the counter-example: its
        # derivation is stated in the file that defines it, so the inventory
        # can record a real answer rather than an honest blank.
        basis = self._claim("OP2").basis
        self.assertIn("10-point", basis)
        self.assertNotIn("unknown", basis.lower())

    def test_no_claim_is_verified_on_a_date_with_no_trail(self):
        # Mechanical half of §5.1: a date answers WHEN; the trail lives in
        # instrument/provision/source_url. A statutory claim carrying a check
        # date but neither a provision nor a source is verified on nothing.
        #
        # Asserted here as a property of the inventory. Promoting it to a
        # protocol check in provenance.py would also cover the rule set, and is
        # a candidate for Stage B — held back because Stage A adds no mechanism.
        for claim in legal_claims.CLAIMS:
            if claim.claim_type != provenance.STATUTORY:
                continue
            with self.subTest(claim=claim.id):
                if claim.citation_is_checked:
                    self.assertTrue(
                        claim.provision.strip() and claim.source_url.strip(),
                        "claim is marked checked but records no re-findable trail")


class TestStageB1PenaltyExposureClaims(unittest.TestCase):
    """
    INVENTORY_EXPANSION_DESIGN.md §4 Stage B1. Adds exactly one mechanism —
    instrument_kind — because this is the first file whose citations are not all
    Acts. The s. 448 non-applicability claim is held back for B2: it needs a
    value-less claim, which is a second mechanism.
    """

    def _claim(self, cid):
        return next(c for c in legal_claims.CLAIMS if c.id == cid)

    def test_stage_b1_added_exactly_the_four_rate_claims(self):
        # The id prefix was the WRONG batch boundary: B2 added PE5 to the same
        # file and the same prefix. A prefix is a proxy for a batch, and proxies
        # break when a later batch reuses them — see §7's refinement. Pinned on
        # what actually distinguishes this batch: the four rate claims by name.
        rate_claims = [c.id for c in legal_claims.CLAIMS
                       if c.module == "penalty_exposure" and c.asserts_a_value]
        self.assertEqual(rate_claims, ["PE1", "PE2", "PE3", "PE4"])

    def test_every_recorded_value_matches_the_live_constant(self):
        import penalty_exposure as pe
        self.assertEqual(self._claim("PE1").asserted_value, pe.EPF_7Q_MONTHLY_RATE)
        self.assertEqual(self._claim("PE2").asserted_value, pe.EPF_14B_MONTHLY_RATE)
        self.assertEqual(self._claim("PE3").asserted_value, pe.EPF_14B_CAP_FRACTION)
        self.assertEqual(self._claim("PE4").asserted_value, pe.TDS_201_1A_MONTHLY_RATE)
        self.assertEqual(legal_claims.drift_findings(), [])

    def test_the_notification_is_marked_subordinate_not_an_act(self):
        # The whole reason instrument_kind exists. EPF s. 14B's 1%/month is set
        # by a dated Ministry notification, not by the Act — and re-checking a
        # notification is a different task from looking up a section.
        pe2 = self._claim("PE2")
        self.assertEqual(pe2.instrument_kind, provenance.KIND_SUBORDINATE)
        self.assertIn("notification", pe2.instrument.lower())

    def test_the_act_based_rates_are_marked_as_acts(self):
        for cid in ("PE1", "PE3", "PE4"):
            with self.subTest(claim=cid):
                self.assertEqual(self._claim(cid).instrument_kind, provenance.KIND_ACT)

    def test_the_rate_known_to_have_moved_says_so(self):
        # PE2 replaced a tiered 5-25% structure in 2024. A figure that has
        # already changed once, and that lives in a notification rather than an
        # Act, is the most likely in this batch to change again.
        origin = self._claim("PE2").threshold_origin
        self.assertIn("5-25%", origin)
        self.assertIn("notification changes more easily", origin)

    def test_all_four_are_unresolved_on_the_files_own_wording(self):
        # Not a judgement about the file — a reading of it.
        # penalty_exposure.py says "independently verified against current
        # sources"; payroll_breakdown.py says "against a PRIMARY source" and
        # names the document. Only the second is a trail.
        for cid in ("PE1", "PE2", "PE3", "PE4"):
            with self.subTest(claim=cid):
                claim = self._claim(cid)
                self.assertFalse(claim.citation_is_checked)
                self.assertTrue(claim.citation_attempt_unresolved)
                self.assertIn("does not assert a primary source",
                              claim.citation_checked_on)
                self.assertIn("NOT backdated", claim.citation_checked_on)

    def test_the_four_rate_claims_all_assert_a_value(self):
        # REPLACES test_the_448_exclusion_is_not_in_this_stage, which pinned
        # that no value-less claim existed yet. B2 is that arrival, so the
        # assertion had to go — but what it protected has not: these four are
        # rate claims, and a rate claim with no figure would be incoherent.
        for cid in ("PE1", "PE2", "PE3", "PE4"):
            with self.subTest(claim=cid):
                claim = self._claim(cid)
                self.assertTrue(claim.asserts_a_value)
                self.assertIsInstance(claim.asserted_value, float)


class TestInstrumentKind(unittest.TestCase):

    def test_it_defaults_to_act_so_nothing_existing_changed(self):
        for rule in compliance_rules.RULES:
            with self.subTest(rule=rule.id):
                self.assertEqual(rule.instrument_kind, provenance.KIND_ACT)

    def test_an_unknown_kind_is_a_violation(self):
        from unittest.mock import patch
        bad = legal_claims.Claim(
            id="K1", module="tax_engine", symbol="CESS_RATE", describes="d",
            asserted_value=0.04, claim_type=provenance.STATUTORY,
            instrument="Some Act, 1952", instrument_kind="statute-ish",
            instrument_status=provenance.IN_FORCE, provision="P",
            source_url="https://example.invalid/x", citation_checked_on="2026-09-12",
            threshold_origin="t")
        with patch.object(legal_claims, "CLAIMS", (bad,)):
            problems = legal_claims.evidence_findings()
        self.assertTrue(any("K1" in p and "instrument_kind" in p for p in problems),
                        problems)

    def test_the_checker_survives_a_carrier_that_predates_the_field(self):
        # The mixin supplies a class-level fallback so adding a field to the
        # shared evidence model cannot make the checker raise AttributeError on
        # an older carrier. Found by a test stand-in doing exactly that.
        # MUST be STATUTORY. The first version of this test used a CONVENTION
        # carrier and passed even with the fallback deleted, because the
        # instrument_kind check lives inside the statutory branch and was never
        # reached — the test was green for the wrong reason, which a sabotage
        # run caught and an assertion alone would not have.
        class Old(provenance.ProvenanceMixin):
            id = "OLD1"
            claim_type = provenance.STATUTORY
            basis = ""
            threshold_origin = "t"
            reviewed_by = "R"
            reviewed_on = "2026-09-12"
            source_url = "https://example.invalid/x"
            provision = "P"
            citation_checked_on = "2026-09-12"
            instrument = "Some Act, 1952"
            instrument_status = provenance.IN_FORCE
        self.assertEqual(provenance.provenance_violations([Old()]), [])


class TestStageB2ValuelessClaims(unittest.TestCase):
    """
    INVENTORY_EXPANSION_DESIGN.md §2.3, Stage B2. One mechanism: a claim that
    asserts no value, because it asserts a provision does NOT apply.
    """

    def _pe5(self):
        return next(c for c in legal_claims.CLAIMS if c.id == "PE5")

    def test_the_sentinel_is_not_None(self):
        # None is a legitimate value for a constant to hold, so using it would
        # collapse "has no value" into "its value is None" — the same
        # two-states-into-one mistake citation_checked_on avoids.
        self.assertIsNot(legal_claims.NO_VALUE, None)
        self.assertIs(legal_claims.NO_VALUE, legal_claims._NoValue())
        self.assertEqual(repr(legal_claims.NO_VALUE), "NO_VALUE")

    def test_a_claim_with_a_value_of_None_still_counts_as_asserting_one(self):
        probe = _probe(asserted_value=None)
        self.assertTrue(probe.asserts_a_value)

    def test_the_drift_check_refuses_rather_than_returning_false(self):
        # Returning False would mean "has not drifted" for a claim nothing
        # checked — a green result nobody computed.
        with self.assertRaises(legal_claims.ValuelessClaimError):
            self._pe5().value_has_drifted
        with self.assertRaises(legal_claims.ValuelessClaimError):
            self._pe5().live_value()

    def test_what_the_drift_check_cannot_cover_is_named_not_silently_skipped(self):
        # drift_findings() == [] must not quietly also mean "and some claims
        # were never eligible".
        self.assertEqual([c.id for c in legal_claims.drift_is_not_applicable()],
                         ["PE5"])
        self.assertEqual(legal_claims.drift_findings(), [])

    def test_a_non_applicability_claim_still_owes_a_citation(self):
        # "This provision does not apply" is not a softer claim than "this
        # provision requires X". If it shipped without a source, the easiest way
        # to avoid citing a provision would be to assert it does not apply.
        from unittest.mock import patch
        uncited = legal_claims.Claim(
            id="NA1", module="penalty_exposure", symbol="",
            describes="d", asserted_value=legal_claims.NO_VALUE,
            claim_type=provenance.NON_APPLICABILITY, threshold_origin="none")
        with patch.object(legal_claims, "CLAIMS", (uncited,)):
            problems = legal_claims.evidence_findings()
        self.assertTrue(any("NA1" in p and "source_url" in p for p in problems), problems)
        self.assertTrue(any("NA1" in p and "provision" in p for p in problems), problems)

    def test_the_review_message_names_the_right_assertion(self):
        # PE5 has no value; asking someone to "verify the value" sends them to
        # a task that does not exist.
        findings = [f for f in legal_claims.evidence_findings() if f.startswith("PE5")]
        self.assertTrue(findings)
        self.assertIn("the authority still holds", findings[0])
        self.assertNotIn("verified the value", findings[0])
        # And a value-asserting claim keeps its own wording.
        pe1 = [f for f in legal_claims.evidence_findings() if f.startswith("PE1")]
        self.assertIn("verified the value", pe1[0])

    def test_it_carries_the_judgment_as_its_instrument(self):
        pe5 = self._pe5()
        self.assertEqual(pe5.instrument_kind, provenance.KIND_JUDGMENT)
        self.assertIn("149 taxmann.com 144", pe5.instrument)

    def test_where_reads_as_the_module_not_a_truncated_symbol(self):
        self.assertEqual(self._pe5().where, "penalty_exposure")

    def test_the_scope_condition_the_exclusion_depends_on_is_recorded(self):
        # s. 448 is inapplicable BECAUSE this module only models the
        # deducted-but-not-deposited case. If it ever models failure to deduct,
        # the claim becomes wrong without any law having changed, and no
        # automated check can catch that.
        source = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "legal_claims.py")).read()
        self.assertIn("ever models FAILURE TO DEDUCT", source)

    def test_the_citation_is_recorded_as_specific_but_still_unresolved(self):
        # Both halves of §5.1 are required: a re-findable trail AND a recorded
        # check. PE5 has the first and not the second.
        pe5 = self._pe5()
        self.assertFalse(pe5.citation_is_checked)
        self.assertTrue(pe5.citation_attempt_unresolved)
        self.assertIn("most specific", pe5.citation_checked_on)
        self.assertIn("NOT backdated", pe5.citation_checked_on)

    def test_whether_the_judgment_still_stands_is_named_as_unchecked(self):
        # A separate question from the citation, and the one that would make
        # this claim wrong rather than merely unverified.
        self.assertIn("overruled", self._pe5().citation_checked_on)
