"""
tests/test_ctc_reconciliation.py — D-S2: never subtract across two different
amounts of money.

Every expected value here is DERIVED, not copied from a run. The like-for-like
figures are computed by calling optimize() with the structure's own modelled
total — the same deterministic function the route calls, with the argument the
design says it should have been given. Copying a number out of a run would pin
the bug on the days the bug is present.

See CTC_RECONCILIATION_DESIGN.md. The three sites:
  A  /api/batch-audit's unclaimed_savings
  B  negotiate()'s total_annual_saving, via _build_current_structure's clamp
  C  the correction flow's rebuilt special_allowance
"""

import unittest

from tax_engine import SalaryStructure, reconciliation_gap
from optimizer import optimize, best_regime_for_given_structure
from app import _build_current_structure, _build_optimize_response

from tests.test_review_workflow import ReviewQueueTestCase, _client


RENT = 240_000
CITY = "metro"


def _row(ctc, basic, hra, special, pf, name="Row", **extra):
    row = {
        "name": name, "ctc": ctc, "basic": basic, "hra": hra, "lta": 0,
        "special_allowance": special, "employer_pf": pf, "employer_nps": 0,
        "nps_opted": False, "rent_paid": RENT, "city": CITY,
        "band_min": ctc * 0.5, "band_max": ctc * 1.5,
    }
    row.update(extra)
    return row


def _structure(row):
    return SalaryStructure(
        ctc=row["ctc"], basic=row["basic"], hra=row["hra"], lta=row["lta"],
        special_allowance=row["special_allowance"], employer_pf=row["employer_pf"],
        employer_nps=row["employer_nps"], nps_opted=row["nps_opted"],
    )


def _like_for_like_saving(structure):
    """
    What unclaimed_savings must be: the current tax on this structure, minus
    the best tax achievable by re-splitting THE SAME money. Derived here from
    the structure itself, never from a recorded figure.
    """
    current = best_regime_for_given_structure(structure, RENT, CITY)
    optimal = optimize(ctc=structure.total(), rent_paid=RENT, city=CITY,
                       nps_opted=structure.nps_opted)
    return round(max(0.0, current["tax_breakdown"]["total_tax"]
                     - optimal["recommended"].tax_breakdown["total_tax"]), 2)


# A row whose components reconcile to its stated CTC exactly.
def _reconciling_row(ctc, name="Reconciles"):
    basic = round(ctc * 0.40, 2)
    pf = round(basic * 0.12, 2)
    hra = round(basic * 0.50, 2)
    return _row(ctc, basic, hra, round(ctc - basic - hra - pf, 2), pf, name=name)


# The ordinary real case: the stated CTC carries a statutory gratuity accrual
# that this tool does not model, so the components sum to less than it.
def _gratuity_row(ctc, name="Gratuity"):
    basic = round(ctc * 0.40, 2)
    gratuity = round(basic * 0.0481, 2)
    pf = round(basic * 0.12, 2)
    hra = round(basic * 0.50, 2)
    return _row(ctc, basic, hra, round(ctc - basic - hra - pf - gratuity, 2), pf,
                name=name), gratuity


def _clean_gratuity_row(ctc, name="CleanGratuity"):
    """
    A gratuity row whose basic clears R1's 50% floor, so its compliance route is
    'clean' and can be pinned. Returns (row, structure).
    """
    basic = round(ctc * 0.60, 2)
    gratuity = round(basic * 0.0481, 2)
    pf = round(basic * 0.12, 2)
    hra = round(basic * 0.30, 2)
    row = _row(ctc, basic, hra, round(ctc - basic - hra - pf - gratuity, 2), pf,
               name=name)
    return row, _structure(row)


class TestTheAuditComparesLikeWithLike(unittest.TestCase):
    """
    Site A. The defect: optimize() was called with the STATED ctc while the
    current tax came from the components as supplied, so the subtraction
    crossed two different amounts of money.
    """

    def test_a_reconciling_row_is_unchanged(self):
        # The both-states pair. This case worked before the fix and must keep
        # working, so the fix cannot be satisfied by breaking it.
        for ctc in (600_000, 1_200_000, 1_800_000, 3_600_000):
            with self.subTest(ctc=ctc):
                s = _structure(_reconciling_row(ctc))
                self.assertEqual(reconciliation_gap(s), 0.0)
                current = best_regime_for_given_structure(s, RENT, CITY)
                stated = optimize(ctc=s.ctc, rent_paid=RENT, city=CITY, nps_opted=False)
                # With no gap the two bases are the same computation.
                self.assertEqual(
                    round(max(0.0, current["tax_breakdown"]["total_tax"]
                              - stated["recommended"].tax_breakdown["total_tax"]), 2),
                    _like_for_like_saving(s))

    def test_the_optimum_is_built_from_the_money_that_is_actually_there(self):
        # The identity that is the whole argument. Today the route optimises
        # from structure.ctc, so this fails wherever ctc != total().
        for ctc in (1_800_000, 2_400_000, 3_600_000, 5_000_000):
            with self.subTest(ctc=ctc):
                row, _ = _gratuity_row(ctc)
                s = _structure(row)
                self.assertGreater(reconciliation_gap(s), 0.0)
                optimal = optimize(ctc=s.total(), rent_paid=RENT, city=CITY,
                                   nps_opted=False)["recommended"]
                self.assertAlmostEqual(optimal.structure.total(), s.total(), places=2)


class TestSiteATheBatchAuditRoute(ReviewQueueTestCase):
    """Site A through the real route, which is where the figure is published."""

    def setUp(self):
        super().setUp()
        self.client = _client()

    def _audit(self, rows):
        resp = self.client.post("/api/batch-audit", json={"rows": rows})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    def test_the_gratuity_row_reports_the_like_for_like_saving(self):
        for ctc in (1_800_000, 2_400_000, 3_600_000):
            with self.subTest(ctc=ctc):
                row, _ = _gratuity_row(ctc)
                body = self._audit([row])
                self.assertEqual(body["rows"][0]["unclaimed_savings"],
                                 _like_for_like_saving(_structure(row)))

    def test_the_reconciliation_gap_is_reported_and_equals_the_gratuity(self):
        row, gratuity = _gratuity_row(3_600_000)
        body = self._audit([row])
        self.assertAlmostEqual(body["rows"][0]["reconciliation_gap"], gratuity, places=2)

    def test_the_row_says_which_ctc_the_figure_was_computed_against(self):
        row, _ = _gratuity_row(3_600_000)
        body = self._audit([row])
        self.assertEqual(body["rows"][0]["ctc_basis"], "modelled")

    def test_components_exceeding_the_stated_ctc_do_not_invent_a_saving(self):
        # The fabricating direction: the ctc column understates the structure,
        # so the "optimum" was a cheaper structure and the whole difference was
        # reported as money on the table. There is no saving here — the
        # structure is already optimal for the money it holds.
        good = _reconciling_row(1_548_000)
        row = dict(good, ctc=1_000_000, name="Understated",
                   band_min=500_000, band_max=1_500_000)
        s = _structure(row)
        self.assertLess(reconciliation_gap(s), 0.0)
        body = self._audit([row])
        self.assertEqual(body["rows"][0]["unclaimed_savings"], _like_for_like_saving(s))
        self.assertAlmostEqual(body["rows"][0]["reconciliation_gap"],
                               row["ctc"] - s.total(), places=2)

    def test_the_summary_counts_rows_that_do_not_reconcile(self):
        g1, _ = _gratuity_row(1_800_000, name="G1")
        g2, _ = _gratuity_row(2_400_000, name="G2")
        body = self._audit([_reconciling_row(1_200_000), g1, g2])
        self.assertEqual(body["summary"]["rows_not_reconciling"], 2)
        self.assertEqual(body["summary"]["valid_row_count"], 3)


class TestSiteAContainment(ReviewQueueTestCase):
    """
    Pinned so the containment claim in CTC_RECONCILIATION_DESIGN.md §5 cannot
    break silently. These figures must NOT move when the basis changes.
    """

    def setUp(self):
        super().setUp()
        self.client = _client()

    def test_routing_treasury_and_the_structure_figures_are_untouched(self):
        # Basic at 60%, which is where the optimiser puts it, so R1's 50% floor
        # does not fire and the row's clean route is the one being pinned. The
        # 40%-basic rows used elsewhere in this file escalate on R1, which is
        # correct and would make this assertion about the wrong thing.
        row, s = _clean_gratuity_row(3_600_000)
        body = self.client.post("/api/batch-audit", json={"rows": [row]}).get_json()
        r = body["rows"][0]
        # The funding gate's figure follows the real components, and always did.
        self.assertAlmostEqual(r["treasury_forecast"]["total_capital_outlay"],
                               s.total(), places=2)
        # Routing takes compliance + guardrail only; neither carries the
        # subtraction this fix changes.
        self.assertEqual(r["orchestration"]["route"], "auto_pass_candidate")
        self.assertEqual(r["excess_contribution"], 0.0)


class TestSiteBNegotiationDoesNotFabricateLeverage(unittest.TestCase):
    """
    Site B, the most severe. _build_current_structure()'s max(0.0, ...) clamp
    pinned special allowance at zero when the extracted components already
    exceeded the stated CTC, so the structure over-reconciled without limit and
    negotiate() compared it against an optimum for a smaller CTC.
    """

    OVERFLOWING = [
        (1_800_000, 1_400_000, 700_000),
        (2_400_000, 1_600_000, 800_000),
        (3_600_000, 3_000_000, 1_500_000),
    ]

    def test_an_over_reconciling_extraction_keeps_its_real_components(self):
        for ctc, basic, hra in self.OVERFLOWING:
            with self.subTest(ctc=ctc):
                s = _build_current_structure({"basic": basic, "hra": hra, "lta": 0},
                                             ctc, "new")
                # The clamp used to force special_allowance to 0 and swallow the
                # overflow. The components are what they are.
                self.assertGreater(s.total(), ctc)
                self.assertLess(reconciliation_gap(s), 0.0)

    def _pipeline(self, ctc, extracted):
        """
        The REAL path. An earlier version of these tests called negotiate()
        directly with ctc=structure.total() and a recommendation built from the
        same figure — that is, with the corrected arguments supplied by hand, so
        the test passed with the defect fully present. It asserted nothing.
        The route reaches negotiate() through the pipeline, and the pipeline is
        where the wrong argument is chosen, so that is what has to be exercised.
        """
        response, raw = _build_optimize_response(
            ctc, RENT, CITY, False, extracted, False, skip_ai=True)
        structure = _build_current_structure(extracted, ctc, raw["recommended"].regime)
        return response, structure

    def test_no_saving_is_offered_that_the_structure_cannot_deliver(self):
        # Each of these structures is already optimal for the money it holds, so
        # the honest answer is zero. Shipped today: Rs 90,417.60, Rs 44,928.00
        # and Rs 3,61,670.40 — measured through this exact call, not recalled.
        for ctc, basic, hra in self.OVERFLOWING:
            with self.subTest(ctc=ctc):
                response, structure = self._pipeline(
                    ctc, {"basic": basic, "hra": hra, "lta": 0})
                self.assertEqual(response["negotiation"]["total_annual_saving"],
                                 _like_for_like_saving(structure))

    def test_the_response_says_the_input_disagrees_with_itself(self):
        # Section 6.3: a negative gap is an input error, and this is the one
        # place the tool should be loud — an offer letter whose components
        # exceed its stated CTC has been misread, and nothing downstream of it
        # is trustworthy until that is resolved.
        for ctc, basic, hra in self.OVERFLOWING:
            with self.subTest(ctc=ctc):
                response, structure = self._pipeline(
                    ctc, {"basic": basic, "hra": hra, "lta": 0})
                self.assertTrue(response["components_exceed_stated_ctc"])
                self.assertAlmostEqual(response["reconciliation_gap"],
                                       reconciliation_gap(structure), places=2)

    def test_a_reconciling_extraction_is_unchanged(self):
        # The both-states pair for Site B: the ordinary path keeps its real,
        # genuine saving. Derived from the structure, not pinned to a figure.
        extracted = {"basic": 1_440_000, "hra": 720_000, "lta": 0}
        response, structure = self._pipeline(3_600_000, extracted)
        self.assertEqual(reconciliation_gap(structure), 0.0)
        self.assertFalse(response["components_exceed_stated_ctc"])
        self.assertEqual(response["negotiation"]["total_annual_saving"],
                         _like_for_like_saving(structure))
        # And it is a real number, not an incidental zero — otherwise this
        # both-states pair would pass even if the fix zeroed every saving.
        self.assertGreater(response["negotiation"]["total_annual_saving"], 0)


class TestSiteCTheCorrectionKeepsTheAuditedStructure(unittest.TestCase):
    """
    Site C. The correction flow posts the audited row's components back,
    including its special_allowance, and _build_current_structure() recomputed
    it — absorbing the reconciliation gap into taxable pay, so the correction
    worked on a structure the audit never showed.
    """

    def test_a_supplied_special_allowance_is_honoured(self):
        row, gratuity = _gratuity_row(3_600_000)
        audited = {
            "basic": row["basic"], "hra": row["hra"], "lta": row["lta"],
            "special_allowance": row["special_allowance"],
            "employer_pf": row["employer_pf"], "employer_nps": row["employer_nps"],
        }
        s = _build_current_structure(audited, row["ctc"], "new")
        self.assertAlmostEqual(s.special_allowance, row["special_allowance"], places=2)
        # The audit and the correction now describe the same structure.
        self.assertAlmostEqual(s.total(), _structure(row).total(), places=2)
        self.assertAlmostEqual(reconciliation_gap(s), gratuity, places=2)

    def test_an_absent_special_allowance_is_still_balanced(self):
        # The extraction path supplies no special allowance and must keep
        # balancing exactly as before — this half of the behaviour is unchanged.
        s = _build_current_structure({"basic": 1_440_000, "hra": 720_000, "lta": 0},
                                     3_600_000, "new")
        self.assertAlmostEqual(s.total(), 3_600_000, places=2)

    def test_an_explicit_zero_special_allowance_is_not_treated_as_absent(self):
        # 0 is a real value a correction can carry, and `or`-style defaulting
        # would silently rebalance it. Pinned because it is the obvious way to
        # get this wrong.
        s = _build_current_structure(
            {"basic": 1_440_000, "hra": 720_000, "lta": 0, "special_allowance": 0,
             "employer_pf": 172_800}, 3_600_000, "new")
        self.assertEqual(s.special_allowance, 0)


class TestReconciliationGapItself(unittest.TestCase):

    def test_zero_when_the_structure_reconciles(self):
        self.assertEqual(reconciliation_gap(_structure(_reconciling_row(1_800_000))), 0.0)

    def test_positive_when_the_stated_ctc_carries_unmodelled_money(self):
        row, gratuity = _gratuity_row(2_400_000)
        self.assertAlmostEqual(reconciliation_gap(_structure(row)), gratuity, places=2)

    def test_negative_when_the_components_exceed_the_stated_ctc(self):
        row = dict(_reconciling_row(1_548_000), ctc=1_000_000)
        self.assertAlmostEqual(reconciliation_gap(_structure(row)), -548_000, places=2)


if __name__ == "__main__":
    unittest.main()
