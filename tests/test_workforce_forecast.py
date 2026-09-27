"""
Workforce cost forecast (addition spec 2.1) — WORKFORCE_COST_FORECAST_DESIGN.md §8.

Every test here pins a claim the design makes, most of them measured at
1aad5a8 before any code existed. If one fails after an engine change, the claim
it pins has stopped being true, and the label the forecast shows beside its
figures may now be false. Fix the claim, not the test.

The direction test (TestInflatedCtcDirection) is deliberately limited to the
total and TDS. EPFO, NPS and take-home measurably go both ways (253 regime flips
in 22,080 comparisons, design §7 D-W2). Do not widen it.
"""
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import workforce_forecast as wf
from optimizer import optimize
from payroll_breakdown import treasury_forecast

TOTAL_LINES = ("net_take_home", "tds", "epfo_challan", "nps_remittance", "professional_tax")


def one_cohort(**kw):
    cohort = {"headcount": 1, "ctc": 1_200_000, "city": "metro", "join_month": "2026-04"}
    cohort.update(kw)
    return cohort


def run(start, end, *cohorts):
    return wf.forecast({"period": {"start": start, "end": end}, "cohorts": list(cohorts)})


class TestFullYearIdentity(unittest.TestCase):
    """The strongest check (design §8): one hire joining in April, over the whole
    year, reproduces treasury_forecast() component by component, to the paisa.
    Any proration or aggregation bug breaks it."""

    CASES = [
        (600_000, "metro", False, None, "karnataka"),
        (1_200_000, "non_metro", True, None, "maharashtra"),
        (1_800_000, "metro", False, 0, "karnataka"),
        (1_800_000, "metro", True, 300_000, "tamil_nadu"),
        (3_600_000, "metro", False, 600_000, None),
        (6_000_000, "non_metro", True, 1_200_000, "delhi"),
    ]

    def test_every_component_matches_treasury_forecast(self):
        for ctc, city, nps, rent, loc in self.CASES:
            with self.subTest(ctc=ctc, city=city, nps=nps, rent=rent, loc=loc):
                t = run("2026-04", "2027-03", one_cohort(
                    ctc=ctc, city=city, nps_opted=nps, rent_paid=rent, work_location=loc))["totals"]
                rec = optimize(ctc=ctc, rent_paid=rent or 0, city=city, nps_opted=nps)["recommended"]
                tf = treasury_forecast(rec.structure, rec.tax_breakdown, loc)
                self.assertAlmostEqual(t["net_take_home"], tf["net_take_home_annual"], places=2)
                self.assertAlmostEqual(t["tds"], tf["tds_escrow_annual"], places=2)
                # Both TDS cases coincide over a full year (design §3, §6).
                self.assertAlmostEqual(t["tds_if_declared"], tf["tds_escrow_annual"], places=2)
                self.assertAlmostEqual(t["epfo_challan"], tf["epfo_challan_annual"], places=2)
                self.assertAlmostEqual(t["nps_remittance"], tf["nps_remittance_annual"], places=2)
                self.assertAlmostEqual(t["professional_tax"], tf["professional_tax_annual"], places=2)
                self.assertAlmostEqual(t["total"], tf["total_capital_outlay"], places=2)


class TestLinearityAndTotals(unittest.TestCase):

    def test_n_hires_equal_n_times_one(self):
        one = run("2026-10", "2027-03", one_cohort(ctc=2_400_000, rent_paid=400_000, join_month="2026-11"))
        many = run("2026-10", "2027-03", one_cohort(ctc=2_400_000, rent_paid=400_000, join_month="2026-11", headcount=7))
        for line, value in one["totals"].items():
            self.assertAlmostEqual(many["totals"][line], 7 * value, places=1, msg=line)

    def test_components_sum_to_total_and_total_is_prorated_ctc(self):
        r = run("2026-07", "2027-03", one_cohort(ctc=1_500_000, headcount=3, join_month="2026-09", rent_paid=200_000))
        for m in r["months"]:
            self.assertAlmostEqual(sum(m[k] for k in TOTAL_LINES), m["total"], places=1)
        # Joined September: 7 months of the period employed, 3 hires.
        self.assertAlmostEqual(r["totals"]["total"], 3 * 1_500_000 * 7 / 12, places=1)

    def test_tds_case_moves_net_and_tds_by_equal_and_opposite_amounts(self):
        r = run("2027-01", "2027-03", one_cohort(ctc=3_000_000, rent_paid=0, join_month="2027-01"))["totals"]
        self.assertAlmostEqual(r["tds_if_declared"] - r["tds"],
                               r["net_take_home"] - r["net_take_home_if_declared"], places=1)
        self.assertGreater(r["tds_if_declared"], r["tds"])

    def test_months_before_joining_contribute_nothing(self):
        r = run("2026-10", "2026-12", one_cohort(join_month="2026-12"))
        self.assertEqual([m["headcount"] for m in r["cohorts"][0]["months"]], [0, 0, 1])
        self.assertEqual(r["months"][0]["total"], 0)


class TestProfessionalTaxTiming(unittest.TestCase):

    def test_february_carries_the_higher_instalment(self):
        r = run("2027-01", "2027-03", one_cohort(work_location="karnataka", join_month="2027-01"))
        pt = {m["month"]: m["professional_tax"] for m in r["months"]}
        self.assertGreater(pt["2027-02"], pt["2027-01"])
        self.assertEqual(pt["2027-01"], pt["2027-03"])

    def test_unrecognised_location_is_flagged_not_silently_zero(self):
        c = run("2026-10", "2026-10", one_cohort(work_location="goa", join_month="2026-10"))["cohorts"][0]
        self.assertFalse(c["pt_state_recognized"])


class TestPartYearTds(unittest.TestCase):
    """Design §3's table, pinned. B (the primary figure) is the tax on the
    part-year pay; A (tds_if_declared) is the annual tax prorated. Rent Rs
    3,00,000, metro, no NPS, as measured."""

    # (ctc, months employed in FY, B, A), rupees, from the §3 table at 1aad5a8.
    TABLE = [
        (1_800_000, 3, 0, 31_021), (1_800_000, 6, 0, 62_041), (1_800_000, 9, 0, 93_062),
        (2_400_000, 3, 0, 61_893), (2_400_000, 9, 124_082, 185_679),
        (3_600_000, 6, 124_082, 291_065), (3_600_000, 9, 321_547, 436_597),
        (6_000_000, 3, 80_652, 319_254), (6_000_000, 6, 408_408, 638_508),
        (6_000_000, 9, 842_712, 957_762),
    ]
    JOIN = {3: "2027-01", 6: "2026-10", 9: "2026-07"}

    def test_table(self):
        for ctc, months, b, a in self.TABLE:
            with self.subTest(ctc=ctc, months=months):
                c = run(self.JOIN[months], "2027-03",
                        one_cohort(ctc=ctc, rent_paid=300_000, join_month=self.JOIN[months]))["cohorts"][0]
                self.assertEqual(c["months_employed_in_fy"], months)
                self.assertAlmostEqual(c["totals"]["tds"], b, delta=1)
                self.assertAlmostEqual(c["totals"]["tds_if_declared"], a, delta=1)


class TestRent(unittest.TestCase):

    def test_rent_never_increases_tax(self):
        """Design §4: across the dense grid, rent only ever lowers tax. This is
        what makes a zero-rent default an upper bound on TDS."""
        for ctc, city, pct in itertools.product(range(500_000, 6_000_001, 500_000),
                                                ("metro", "non_metro"), (0.1, 0.2, 0.3, 0.4)):
            with self.subTest(ctc=ctc, city=city, pct=pct):
                at_zero = optimize(ctc=ctc, rent_paid=0, city=city, nps_opted=False)
                with_rent = optimize(ctc=ctc, rent_paid=ctc * pct, city=city, nps_opted=False)
                self.assertLessEqual(with_rent["recommended"].tax_breakdown["total_tax"],
                                     at_zero["recommended"].tax_breakdown["total_tax"] + 0.01)

    def test_rent_is_required_exactly_when_it_can_change_the_tax(self):
        for ctc, city in itertools.product((600_000, 1_500_000, 1_800_000, 3_000_000), ("metro", "non_metro")):
            with self.subTest(ctc=ctc, city=city):
                can = wf.rent_can_matter(ctc, city, False)
                if can:
                    with self.assertRaises(wf.ForecastError) as ctx:
                        run("2026-10", "2026-10", one_cohort(ctc=ctc, city=city, join_month="2026-10"))
                    self.assertIn("rent paid is required", str(ctx.exception))
                else:
                    c = run("2026-10", "2026-10", one_cohort(ctc=ctc, city=city, join_month="2026-10"))["cohorts"][0]
                    self.assertTrue(c["rent_assumed_zero"])
                    self.assertFalse(c["rent_required"])

    def test_measured_boundaries_still_hold(self):
        """The design reports rent can matter from Rs 16L (metro) and Rs 27L
        (non-metro) at 1aad5a8. Pinned as observations: if the engine moves
        them, this fails and the design's §4 figures need re-measuring."""
        self.assertFalse(wf.rent_can_matter(1_575_000, "metro", False))
        self.assertTrue(wf.rent_can_matter(1_600_000, "metro", False))
        self.assertFalse(wf.rent_can_matter(2_675_000, "non_metro", False))
        self.assertTrue(wf.rent_can_matter(2_700_000, "non_metro", False))


class TestInflatedCtcDirection(unittest.TestCase):
    """Design §7, D-W2: when the entered CTC carries an unmodelled provision,
    the total cash need and TDS are never understated. ONLY those two lines —
    see the module docstring."""

    def test_total_and_tds_never_understated(self):
        for ctc, city, nps, rf, p in itertools.product(range(500_000, 6_000_001, 250_000),
                                                       ("metro", "non_metro"), (False, True),
                                                       (0, 0.2, 0.4), (0.02, 0.04, 0.06)):
            with self.subTest(ctc=ctc, city=city, nps=nps, rf=rf, p=p):
                truth = optimize(ctc=ctc, rent_paid=ctc * rf, city=city, nps_opted=nps)["recommended"]
                entered = optimize(ctc=ctc / (1 - p), rent_paid=ctc * rf, city=city, nps_opted=nps)["recommended"]
                t = treasury_forecast(truth.structure, truth.tax_breakdown, "karnataka")
                e = treasury_forecast(entered.structure, entered.tax_breakdown, "karnataka")
                self.assertGreaterEqual(e["total_capital_outlay"], t["total_capital_outlay"] - 0.5)
                self.assertGreaterEqual(e["tds_escrow_annual"], t["tds_escrow_annual"] - 0.5)

    def test_provision_excluded_is_subtracted_before_optimising(self):
        c = run("2026-10", "2026-10", one_cohort(ctc=1_000_000, provision_excluded=50_000,
                                                 join_month="2026-10"))["cohorts"][0]
        self.assertEqual(c["cash_ctc"], 950_000)
        self.assertAlmostEqual(c["totals"]["total"], 950_000 / 12, places=1)


class TestRefusals(unittest.TestCase):
    """D-W3: the engine holds FY 2026-27 rates only. Anything past March 2027
    is refused with its reason, never computed on assumed law."""

    def test_period_past_the_rate_year_is_refused(self):
        with self.assertRaises(wf.ForecastError) as ctx:
            run("2027-02", "2027-04", one_cohort(join_month="2027-02"))
        self.assertIn("next year's are not yet enacted", str(ctx.exception))

    def test_period_before_the_rate_year_is_refused(self):
        with self.assertRaises(wf.ForecastError):
            run("2026-03", "2026-05", one_cohort())

    def test_join_outside_the_year_is_refused(self):
        with self.assertRaises(wf.ForecastError):
            run("2026-10", "2026-12", one_cohort(join_month="2027-04"))

    def test_bad_inputs_are_refused(self):
        bad = [one_cohort(headcount=0), one_cohort(ctc=-1), one_cohort(ctc=50_000_000),
               one_cohort(city="tier3"), one_cohort(provision_excluded=1_200_000),
               one_cohort(rent_paid=-5), one_cohort(join_month="October")]
        for cohort in bad:
            with self.subTest(cohort=cohort), self.assertRaises(wf.ForecastError):
                run("2026-10", "2026-12", cohort)
        with self.assertRaises(wf.ForecastError):
            wf.forecast({"period": {"start": "2026-12", "end": "2026-10"}, "cohorts": [one_cohort()]})
        with self.assertRaises(wf.ForecastError):
            wf.forecast({"period": {"start": "2026-10", "end": "2026-12"}, "cohorts": []})


class TestLabelsAndGuards(unittest.TestCase):

    def test_tds_note_carries_the_day_one_condition(self):
        """D-W1 was approved on condition that the UI says the s. 392 reading is
        not practitioner-confirmed from day one, and never states it as law."""
        note = run("2026-10", "2026-10", one_cohort(join_month="2026-10"))["notes"]["tds_basis"]
        self.assertIn("not practitioner-confirmed", note)
        self.assertNotIn("the law says", note.lower())

    def test_rate_year_matches_the_tax_engine_header(self):
        """A rate update that moves tax_engine.py to another year must move this
        forecast's year too, or it would forecast on the wrong law."""
        with open(os.path.join(os.path.dirname(__file__), "..", "tax_engine.py")) as f:
            header = f.readline() + f.readline()
        self.assertIn(wf.FORECAST_FY_LABEL, header)


class TestRoute(unittest.TestCase):

    def setUp(self):
        import app as flask_app
        self.client = flask_app.app.test_client()

    def test_valid_request(self):
        res = self.client.post("/api/workforce-forecast", json={
            "period": {"start": "2026-10", "end": "2026-12"},
            "cohorts": [one_cohort(join_month="2026-10", headcount=2)]})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertAlmostEqual(body["totals"]["total"], 2 * 1_200_000 * 3 / 12, places=1)
        self.assertEqual(body["fy"], wf.FORECAST_FY_LABEL)

    def test_refusal_is_a_400_with_the_reason(self):
        res = self.client.post("/api/workforce-forecast", json={
            "period": {"start": "2027-02", "end": "2027-05"}, "cohorts": [one_cohort()]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("not yet enacted", res.get_json()["error"])

    def test_non_json_body_is_a_400(self):
        res = self.client.post("/api/workforce-forecast", data="nope", content_type="text/plain")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
