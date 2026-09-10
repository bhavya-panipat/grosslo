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
        self.assertEqual([(c.id, c.symbol) for c in legal_claims.CLAIMS],
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
        with_provision = [c.id for c in legal_claims.CLAIMS if c.provision.strip()]
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
