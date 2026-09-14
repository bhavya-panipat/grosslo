"""
The legal claim inventory (LEGAL_CLAIM_INVENTORY_DESIGN.md, Phase 2.4).

Step 2 builds the mechanism over an EMPTY inventory and proves it with probes,
the same way 2.2 built the candidate gate and proved it in both directions
while zero candidates existed. A mechanism first tested by the thing that
depends on it cannot be shown to have been working beforehand.
"""

import os
import sys
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
        #
        # FIFTH instance of §7's shape, and it failed for the best possible
        # reason: it iterated the WHOLE inventory, and Stage C1 produced the
        # first genuinely VERIFIED claims. A test asserting "everything here is
        # unverified" was always going to break the moment something was
        # verified — which is the outcome the project wants.
        for claim in [c for c in legal_claims.CLAIMS if c.module == "tax_engine"]:
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

    def _generator(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(root, "scripts"))
        import generate_legal_review_queue as gen
        return gen

    def _tier_section(self, doc, rank):
        """The rendered text of one tier: from its header to the next '## '."""
        # An explicit assertion, not doc.index(). Sabotage D (restoring the old
        # silent skip of empty tiers) first showed this helper raising a bare
        # "ValueError: substring not found" — red, but as an ERROR that named
        # nothing. A failure should say what broke.
        start = doc.find(f"\n## {rank}. ")
        self.assertNotEqual(start, -1, f"tier {rank} has no header in the rendered queue")
        nxt = doc.find("\n## ", start + 1)
        return doc[start: nxt if nxt != -1 else len(doc)]

    def test_every_tier_is_rendered_in_order_even_when_empty(self):
        # R5_CITATION_PROPAGATION_DESIGN.md §4.5.3. The renderer used to emit a
        # tier header only when a row in that tier arrived, so emptying tier 1
        # made the queue silently open at "## 2.". Rendering is this test's
        # subject, so it reads rendered output — but binds each header to the
        # generator's own TIERS tuple, not to a hand-typed copy of the titles.
        gen = self._generator()
        doc = gen.render_document()
        positions = []
        for rank, title, _why in gen.TIERS:
            header = f"## {rank}. {title}"
            with self.subTest(tier=rank):
                self.assertIn(header, doc, f"tier {rank} was not rendered")
            positions.append(doc.find(header))
        self.assertEqual(positions, sorted(positions), "tiers rendered out of order")
        self.assertEqual([t[0] for t in gen.TIERS], [1, 2, 3, 4])

    def test_an_empty_tier_says_so_and_an_occupied_tier_does_not(self):
        # BOTH STATES, in one test. A marker that appeared under every tier
        # would satisfy "an empty tier says so" while meaning nothing, so the
        # occupied case must be shown NOT to carry it — including tier 1 itself
        # once something is put in it.
        from unittest.mock import patch
        gen = self._generator()

        doc = gen.render_document()
        self.assertIn(gen.EMPTY_TIER, self._tier_section(doc, 1),
                      "tier 1 is empty but does not say so")
        self.assertNotIn(gen.EMPTY_TIER, self._tier_section(doc, 4),
                         "an occupied tier claims to be empty")

        stale = compliance_rules.Rule(
            id="R74", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=compliance_rules.ACTIVE,
            claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/x", provision="P",
            citation_checked_on="2026-09-09", instrument="Some Act, 1961",
            instrument_status=compliance_rules.SUPERSEDED,
            threshold_origin="probe: no numeric threshold")
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (stale,)):
            occupied = self._tier_section(gen.render_document(), 1)
        self.assertIn("### R74", occupied, "the superseded item did not land in tier 1")
        self.assertNotIn(gen.EMPTY_TIER, occupied,
                         "tier 1 still claims to be empty with an item in it")

    def test_the_worst_tier_is_empty_and_would_still_rank_first(self):
        # WAS test_the_worst_item_is_first_not_the_easiest, which hardcoded
        # queue.index("### R5") as the worst item. R5 cited a repealed Act; since
        # 2026-09-13 it cites the in-force one and correctly ranks 21st of 23
        # (R5_CITATION_PROPAGATION_DESIGN.md §4.5.2). The PRINCIPLE the test
        # protected is unchanged — ranked by how badly a reader could be misled,
        # never by effort — so it is retargeted, not deleted.
        #
        # TWO CHANGES OF METHOD, both deliberate:
        #
        # 1. Structured rows, not rendered markdown. The old test indexed "### R5"
        #    in the committed file, and read a STALE file green for the wrong
        #    reason while R5's data had already changed underneath it. collect()
        #    returns the tier tuple and the item, so the assertion binds to the
        #    ranking decision itself (§8), not to how a header happens to render.
        #
        # 2. Both states. An empty tier alone is also what a broken _tier()
        #    produces, so a synthetic live superseded item must be shown to rank
        #    first in the same test that shows no real item does.
        from unittest.mock import patch
        gen = self._generator()

        real = [item.id for tier, item in gen.collect() if tier is gen.CITES_DEAD_LAW]
        self.assertEqual(real, [], f"live items citing superseded law: {real}")

        stale = compliance_rules.Rule(
            id="R73", severity="Low", check="c", rationale="r", why="w",
            predicate=lambda s, rp: False, status=compliance_rules.ACTIVE,
            claim_type=compliance_rules.STATUTORY,
            source_url="https://example.invalid/x", provision="P",
            citation_checked_on="2026-09-09", instrument="Some Act, 1961",
            instrument_status=compliance_rules.SUPERSEDED,
            threshold_origin="probe: no numeric threshold")
        with patch.object(compliance_rules, "RULES", compliance_rules.RULES + (stale,)):
            rows = gen.collect()
        order = [item.id for _, item in rows]
        self.assertIs(rows[0][0], gen.CITES_DEAD_LAW,
                      "the superseded-law tier is no longer ranked first")
        first = order.index("R73")
        for other in ("TE1", "TE2", "TE3", "R1", "TE4"):
            with self.subTest(item=other):
                self.assertLess(first, order.index(other),
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

        # WHY THE OLD assertIn("403", queue) WAS REMOVED rather than kept
        # (R5_CITATION_PROPAGATION_DESIGN.md step 7). It pinned the queue's
        # justification: "Primary legal sources return HTTP 403 from the
        # environment this was built in". That sentence was false about the
        # sources — they load in an ordinary browser, which is how both
        # lookups were resolved on 2026-09-13. The corrected text STILL
        # contains "403", because automated requests are still refused. So
        # "403" is in the false version and the true version alike, and an
        # assertion that passes on both guards nothing (§8).
        #
        # What is actually worth guarding is the distinction the correction
        # draws — automated requests are refused, a person in a browser is
        # not — and that the old claim does not come back.
        self.assertIn("Automated requests to the official legal sources are refused", queue)
        self.assertIn("load for a person in an ordinary browser", queue)
        self.assertNotIn("Primary legal sources return HTTP 403 from the environment this "
                         "was built in", queue,
                         "the false claim that the SOURCES are unreachable is back")

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
                    # ALIGNED WITH §5.1, which my first version of this test was
                    # stricter than: the rule says a NAMED INSTRUMENT a reader
                    # can look up is itself the trail — "its specificity is the
                    # trail" — not that a URL is required. PT1 cites an amending
                    # Act by name, amendment and year and captures no URL, which
                    # satisfies §5.1 and failed this test as first written.
                    #
                    # The separate question of whether provenance.py's 2.2-era
                    # check should still demand source_url is NOT settled here;
                    # see the flag raised with this stage.
                    self.assertTrue(
                        claim.instrument.strip() and claim.provision.strip(),
                        "claim is marked checked but names no re-findable instrument")


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


class TestStageC1ProfessionalTaxClaims(unittest.TestCase):
    """
    INVENTORY_EXPANSION_DESIGN.md §2.1, Stage C1. One mechanism: key paths,
    because PT_MONTHLY_TABLE is one Python name holding five separate STATE
    statutes. known_divergence is C2.
    """

    def _claim(self, cid):
        return next(c for c in legal_claims.CLAIMS if c.id == cid)

    def test_five_states_share_one_symbol_through_key_paths(self):
        pt = [c for c in legal_claims.CLAIMS if c.symbol == "PT_MONTHLY_TABLE"]
        self.assertEqual([c.id for c in pt], ["PT1", "PT2", "PT3", "PT4", "PT5"])
        self.assertEqual([c.key_path[0] for c in pt],
                         ["karnataka", "maharashtra", "telangana", "tamil_nadu",
                          "delhi"])

    def test_each_state_reads_only_its_own_table(self):
        import payroll_breakdown as pb
        for cid, state in (("PT1", "karnataka"), ("PT2", "maharashtra"),
                           ("PT3", "telangana"), ("PT4", "tamil_nadu"),
                           ("PT5", "delhi")):
            with self.subTest(claim=cid):
                self.assertEqual(self._claim(cid).live_value(),
                                 pb.PT_MONTHLY_TABLE[state])
        self.assertEqual(legal_claims.drift_findings(), [])

    def test_drift_in_one_state_names_that_state_alone(self):
        # The whole reason key paths exist. One claim per symbol would report
        # "PT_MONTHLY_TABLE changed" and leave a reader to work out which of
        # five independently-amendable statutes moved.
        from unittest.mock import patch
        import payroll_breakdown as pb
        table = dict(pb.PT_MONTHLY_TABLE)
        table["karnataka"] = [(0, 29_999, 0), (30_000, None, 200)]
        with patch.object(pb, "PT_MONTHLY_TABLE", table):
            findings = legal_claims.drift_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("PT1", findings[0])
        self.assertIn("karnataka", findings[0])
        # MUST assert on the other STATE NAMES, not just the other claim ids.
        # The first version of this test checked ids only and passed when the
        # key path was deleted — because the message then contained the WHOLE
        # dict, whose repr happens to include "karnataka". Sabotage caught it;
        # the assertion could not have. Second time in this phase a test of
        # mine was green for the wrong reason.
        for other_state in ("maharashtra", "telangana", "tamil_nadu", "delhi"):
            self.assertNotIn(other_state, findings[0],
                             "the finding names states this claim is not about")
        for other in ("PT2", "PT3", "PT4", "PT5"):
            self.assertNotIn(other, findings[0])

    def test_a_state_dropped_from_coverage_is_its_own_named_failure(self):
        # Distinct from a stale number and from a missing symbol: the constant
        # is still there and one entry inside it is gone, which is a scope
        # change rather than a wrong figure.
        from unittest.mock import patch
        import payroll_breakdown as pb
        table = {k: v for k, v in pb.PT_MONTHLY_TABLE.items() if k != "telangana"}
        with patch.object(pb, "PT_MONTHLY_TABLE", table):
            with self.assertRaises(legal_claims.KeyPathMissingError) as caught:
                self._claim("PT3").live_value()
        message = str(caught.exception)
        self.assertIn("PT3", message)
        self.assertIn("telangana", message)
        self.assertIn("dropped from coverage", message)
        # §8: assert on what must be ABSENT too. This message does not embed the
        # table's value today, but the drift message did, and that is exactly
        # how the karnataka substring check passed for the wrong reason.
        for other_state in ("karnataka", "maharashtra", "tamil_nadu", "delhi"):
            self.assertNotIn(other_state, message,
                             "the error names states it is not about")
        # And it is still catchable as the broader failure it belongs to.
        self.assertTrue(issubclass(legal_claims.KeyPathMissingError,
                                   legal_claims.SymbolMissingError))

    def test_where_shows_the_key_so_a_reader_knows_what_to_open(self):
        self.assertEqual(self._claim("PT1").where,
                         "payroll_breakdown.PT_MONTHLY_TABLE['karnataka']")

    # ---- the first verified claims in this inventory ----------------------

    def test_karnataka_and_tamil_nadu_are_the_first_verified_citations(self):
        verified = [c.id for c in legal_claims.CLAIMS if c.citation_is_checked]
        self.assertEqual(verified, ["PT1", "PT4"])

    def test_they_are_verified_on_a_named_instrument_not_a_captured_url(self):
        # §5.1: a named instrument a reader can look up IS the trail. PT1
        # captures no URL and is verified; PT4 names the government's own PDF.
        pt1 = self._claim("PT1")
        self.assertTrue(pt1.citation_is_checked)
        self.assertEqual(pt1.source_url, "")
        self.assertIn("(Amendment) Act, 2025", pt1.instrument)
        self.assertIn("tnswp.com", self._claim("PT4").instrument)

    def test_the_three_unnamed_states_stay_unresolved(self):
        # The file's blanket "every slab re-verified against a primary source"
        # records that a check happened without naming what was read. Evidence
        # of a check is not a trail.
        for cid in ("PT2", "PT3", "PT5"):
            with self.subTest(claim=cid):
                claim = self._claim(cid)
                self.assertFalse(claim.citation_is_checked)
                self.assertTrue(claim.citation_attempt_unresolved)
                self.assertIn("NOT backdated", claim.citation_checked_on)

    def test_maharashtras_act_was_not_named_from_outside_the_repo(self):
        # The file refers to "Maharashtra's Act" without naming it. Supplying
        # the title today and recording it against a 2026-09-03 check is
        # exactly the backdating §5.1 forbids.
        self.assertEqual(self._claim("PT2").instrument, "")

    def test_delhis_zero_cites_the_permissive_provision_not_an_absence(self):
        # An absence cannot be cited. Article 276 is what makes the absence
        # lawful rather than an oversight, so it is the nearest citable
        # authority — and recording an empty instrument instead would be
        # indistinguishable from nobody having looked.
        pt5 = self._claim("PT5")
        self.assertEqual(pt5.instrument_kind, provenance.KIND_CONSTITUTION)
        self.assertIn("Article 276", pt5.instrument)
        self.assertIn("PERMITS", pt5.provision)
        self.assertIn("verifying a NEGATIVE", pt5.citation_checked_on)

    def test_the_february_bump_separates_the_ceiling_from_the_arithmetic(self):
        # Rs 2,500 is constitutional; Rs 300 is this tool's arithmetic to land
        # on it. Recording them as one claim would attribute an implementation
        # detail to the Constitution.
        origin = self._claim("PT6").threshold_origin
        self.assertIn("CONSTITUTIONAL", origin)
        self.assertIn("is NOT", origin)


class TestStageC2KnownDivergence(unittest.TestCase):
    """
    INVENTORY_EXPANSION_DESIGN.md §2.4. The subtle gap: a citation can be
    verified AND the implementation correct as designed, while the code still
    knowingly differs from the statute. Left unrecorded, `verified` reads as
    "matches the law exactly".
    """

    def _claim(self, cid):
        return next(c for c in legal_claims.CLAIMS if c.id == cid)

    def test_exactly_the_documented_divergences_are_recorded(self):
        # WAS test_exactly_the_two_documented_divergences_are_recorded. TE4 was
        # added on 2026-09-14 (R1_TE4_RECORD_UPDATE_DESIGN.md SS3.4). This pin is
        # ABOUT the inventory's contents, so moving it deliberately is its job:
        # a divergence added or dropped without anyone meaning to still fails.
        recorded = [c.id for c in legal_claims.CLAIMS if c.known_divergence.strip()]
        self.assertEqual(recorded, ["TE4", "PT2", "PT4"])

    def _divergent(self):
        found = [c for c in legal_claims.CLAIMS if c.known_divergence.strip()]
        # A convention test over an empty collection passes vacuously.
        self.assertTrue(found, "no recorded divergence to check the convention against")
        return found

    def test_empty_means_intended_to_match_not_unexamined(self):
        # Asserted structurally: every other claim declares the field and
        # leaves it empty, which is an assertion rather than an absence of one.
        for claim in legal_claims.CLAIMS:
            with self.subTest(claim=claim.id):
                self.assertIsInstance(claim.known_divergence, str)

    def test_a_divergence_does_not_block_verification(self):
        # The citation claim and the fidelity claim are different, exactly as
        # citation_checked_on and reviewed_by are. PT4 is both verified and
        # knowingly divergent, and that combination is coherent.
        pt4 = self._claim("PT4")
        self.assertTrue(pt4.citation_is_checked)
        self.assertTrue(pt4.known_divergence.strip())

    def test_each_divergence_says_what_a_reviewer_would_be_accepting(self):
        # The point of recording it. A reviewer is not being asked whether the
        # table matches the Act — it does — but whether the departure is
        # acceptable for this tool's purpose, which is a different question.
        # D6: EVERY recorded divergence, not a hardcoded PT2/PT4. As hardcoded, this
        # stayed green while a newly added divergence ignored the convention --
        # INVENTORY_EXPANSION_DESIGN.md SS7, a batch test standing in for a
        # collection rule.
        for claim in self._divergent():
            with self.subTest(claim=claim.id):
                self.assertIn("WHAT A REVIEWER IS ACCEPTING",
                              claim.known_divergence.upper())

    def test_maharashtras_divergence_records_its_direction(self):
        # Which way it errs is the part that decides whether it is safe. This
        # one over-states tax, never under-states it, so a forecast built on it
        # is conservative rather than short.
        divergence = self._claim("PT2").known_divergence
        self.assertIn("OVER-states", divergence)
        self.assertIn("never under-states", divergence)

    def test_an_unreviewed_divergence_is_its_own_finding(self):
        # CHECK 7. The existing reviewer check does not express this: a claim
        # could satisfy that while the divergence itself was never put to anyone.
        # D6: every UNREVIEWED divergence, not a hardcoded PT2/PT4.
        findings = legal_claims.evidence_findings()
        for claim in self._divergent():
            if claim.implementation_is_reviewed:
                continue
            with self.subTest(claim=claim.id):
                self.assertTrue(
                    any(f.startswith(claim.id) and "diverges" in f for f in findings),
                    "a deliberate departure from the law went unreported")

    def test_TE4s_tax_direction_is_marked_pending_not_guessed(self):
        # PT2 records "OVER-states, never under-states" -- the direction is what
        # decides whether a divergence is safe. TE4's cannot be stated while the
        # engine double-counts employer NPS (TAX_ENGINE_EMPLOYER_NPS_DESIGN.md).
        # This pins that it says so, so a direction cannot be written in quietly
        # before D1 is implemented and the direction measured.
        te4 = self._claim("TE4").known_divergence
        self.assertIn("PENDING D1", te4)
        self.assertNotIn("OVER-states", te4)
        self.assertNotIn("UNDER-states", te4)

    def test_a_reviewed_divergence_stops_flagging(self):
        # Both directions. A check asserted only in its failing state might be
        # failing for an unrelated reason.
        from unittest.mock import patch
        import dataclasses
        signed = dataclasses.replace(self._claim("PT2"),
                                     reviewed_by="A Reviewer",
                                     reviewed_on="2026-09-12")
        with patch.object(legal_claims, "CLAIMS", (signed,)):
            findings = legal_claims.evidence_findings()
        self.assertFalse(any("diverges" in f for f in findings), findings)


class TestTheCitationStateIsWellFormed(unittest.TestCase):
    """
    CHECK 8, tracked from Stage C1 where this repository's OWN data fell into
    the gap: a reason was recorded without the "unresolved: " prefix, leaving
    two claims neither checked nor attempted-unresolved.
    """

    def test_every_real_claim_is_in_one_of_the_three_states(self):
        for claim in legal_claims.CLAIMS:
            with self.subTest(claim=claim.id):
                state = claim.citation_checked_on.strip()
                recognised = (not state
                              or claim.citation_attempt_unresolved
                              or claim.citation_is_checked
                              or provenance._looks_like_a_date(state))
                self.assertTrue(recognised,
                                f"{claim.id} is in no recognised citation state")

    def test_a_bare_reason_with_no_prefix_is_a_violation(self):
        # The exact mistake made in C1.
        from unittest.mock import patch
        malformed = _probe(claim_type=provenance.STATUTORY, basis="",
                           instrument="Some Act, 1952",
                           instrument_status=provenance.IN_FORCE,
                           provision="s. 4", source_url="https://example.invalid/x",
                           citation_checked_on="could not reach the source")
        with patch.object(legal_claims, "CLAIMS", (malformed,)):
            problems = legal_claims.evidence_findings()
        self.assertTrue(any("C1" in p and "three recognised states" in p
                            for p in problems), problems)

    def test_the_three_recognised_forms_do_not_flag(self):
        from unittest.mock import patch
        for state in ("", "2026-09-03", "unresolved: tried, 403"):
            with self.subTest(state=state or "<empty>"):
                ok = _probe(claim_type=provenance.STATUTORY, basis="",
                            instrument="Some Act, 1952",
                            instrument_status=provenance.IN_FORCE,
                            provision="s. 4",
                            source_url="https://example.invalid/x",
                            reviewed_by="R", reviewed_on="2026-09-12",
                            citation_checked_on=state)
                with patch.object(legal_claims, "CLAIMS", (ok,)):
                    problems = legal_claims.evidence_findings()
                self.assertFalse(any("three recognised states" in p
                                     for p in problems), problems)
