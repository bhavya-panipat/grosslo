"""
tests/test_funding_figure_source_of_truth.py — D-S7: one funding figure per
submission, enforced rather than conventional.

The defect: the Finance funding gate sums the STORED forecast
(`finance-flow.tsx:826` reduces `r.computed.treasury_forecast.total_capital_outlay`
over pending rows) while `/api/submissions/<id>/rows/<i>/export` ignored that
stored value and recomputed one. The same row is seen by both in sequence, so the
amount funded was not necessarily the amount instructed.

**Why a naive equality test would be worthless, and what this file does instead.**
On an unchanged engine the stored and freshly-computed forecasts are identical, so
a test that merely compares them passes *whether or not the fix is present* — it
would have passed before D-S7. Every assertion here that matters therefore runs
after a FORCED DIVERGENCE: the stored forecast is mutated in the database to a
value the engine would never produce, and the export must still serve it. That is
what makes this a standing check against a future engine change rather than a
coincidence of today's code.

It is the same trap the treasury-NPS work hit, where four identity assertions all
ran on structures where the missing term was zero.

See FUNDING_FIGURE_SOURCE_OF_TRUTH_DESIGN.md.
"""

import json
import unittest

import review_queue

from tests.test_review_workflow import ReviewQueueTestCase, _client, _login_as


ROW = {
    "employee_name": "Funding Figure", "ctc": 1_800_000, "rent_paid": 0,
    "city": "metro", "nps_opted": True,
    "band_min": 1_700_000, "band_max": 1_900_000, "work_location": "karnataka",
    "bank_account_number": "1234567890", "ifsc": "HDFC0000001",
    "email": "funding@test.com",
}

# Deliberately not a figure the engine could produce for this structure: a
# sentinel, so a test that passes cannot be passing because the two paths agree.
SENTINEL_OUTLAY = 12_345_678.91
SENTINEL_NET = 9_876_543.21


class _Base(ReviewQueueTestCase):

    def setUp(self):
        super().setUp()
        self.client = _client()
        _login_as(self.client, "finance")

    def _submit_and_approve(self, row=None):
        resp = self.client.post("/api/submissions",
                                json={"source": "single", "row": dict(row or ROW)})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        sid = resp.get_json()["submission_id"]
        decide = self.client.post(f"/api/submissions/{sid}/rows/0/decide",
                                  json={"decision": "approve"})
        self.assertEqual(decide.status_code, 200)
        return sid

    def _stored_computed(self, sid):
        tenant_id = review_queue._checked_tenant_id(1)
        return review_queue.get_submission(tenant_id, sid)["rows"][0]["computed"]

    def _rewrite_stored_computed(self, sid, mutate):
        """Mutate the stored computed blob in place, as a pre-fix row or a
        later engine change would leave it."""
        tenant_id = review_queue._checked_tenant_id(1)
        with review_queue._conn(tenant_id) as conn:
            raw = conn.execute(
                "SELECT computed_json FROM submission_rows "
                "WHERE tenant_id = %s AND submission_id = %s AND row_index = 0",
                (tenant_id, sid)).fetchone()["computed_json"]
            computed = json.loads(raw)
            mutate(computed)
            conn.execute(
                "UPDATE submission_rows SET computed_json = %s "
                "WHERE tenant_id = %s AND submission_id = %s AND row_index = 0",
                (json.dumps(computed), tenant_id, sid))

    def _export(self, sid):
        return self.client.post(f"/api/submissions/{sid}/rows/0/export")


class TestTheGateFigureAndTheExportFigureAreTheSame(_Base):
    """The headline invariant, and the reason the file exists."""

    def test_the_export_serves_the_stored_forecast_not_a_fresh_one(self):
        sid = self._submit_and_approve()
        stored = self._stored_computed(sid)["treasury_forecast"]
        body = self._export(sid).get_json()
        # Whole dict, not just the total: a matching total with different
        # components is the same bug wearing a disguise.
        self.assertEqual(body["treasury_forecast"], stored)

    def test_a_forced_divergence_is_still_served_from_storage(self):
        # THE STANDING CHECK. Without this the suite cannot tell "serves stored"
        # from "recomputes something that happens to match".
        sid = self._submit_and_approve()

        def bend(computed):
            computed["treasury_forecast"]["total_capital_outlay"] = SENTINEL_OUTLAY
            computed["treasury_forecast"]["net_take_home_annual"] = SENTINEL_NET
        self._rewrite_stored_computed(sid, bend)

        stored = self._stored_computed(sid)["treasury_forecast"]
        self.assertEqual(stored["total_capital_outlay"], SENTINEL_OUTLAY,
                         "precondition: the mutation must have landed")

        body = self._export(sid).get_json()
        self.assertEqual(body["treasury_forecast"]["total_capital_outlay"],
                         SENTINEL_OUTLAY)
        self.assertEqual(body["treasury_forecast"], stored)

    def test_the_payout_amount_follows_the_stored_forecast_too(self):
        # Otherwise the payload would carry a stored funding figure beside a
        # freshly computed payment, which is the D-S4 defect moved rather than
        # removed.
        sid = self._submit_and_approve()
        self._rewrite_stored_computed(
            sid, lambda c: c["treasury_forecast"].update(net_take_home_annual=SENTINEL_NET))
        body = self._export(sid).get_json()
        self.assertEqual(body["payouts"][0]["amount"],
                         int(round(round(SENTINEL_NET / 12, 2) * 100)))

    def test_payout_basis_gross_follows_the_stored_structure(self):
        # gross_monthly_cash, employee_pf_monthly and tds_monthly are read from
        # the STRUCTURE, not the forecast — `_payout_basis`'s docstring claims
        # "every figure comes from the forecast", and that was never true. So
        # serving a stored forecast beside a freshly recomputed structure would
        # leave the payload mixing bases: the D-S4 defect moved, not removed.
        #
        # Mutating the stored structure is what distinguishes the two sources.
        # An arbitrary sentinel on `net_take_home_annual` could not: it makes
        # net == gross - withholdings unsatisfiable by construction, so such a
        # test would assert nothing about where the figures came from. (An
        # earlier draft of this test did exactly that.)
        sid = self._submit_and_approve()
        stored = self._stored_computed(sid)
        regime = stored["recommended_regime"]
        bumped = stored[f"{regime}_regime_best"]["structure"]["basic"] + 120_000

        def bend(computed):
            computed[f"{regime}_regime_best"]["structure"]["basic"] = bumped
        self._rewrite_stored_computed(sid, bend)

        basis = self._export(sid).get_json()["payout_basis"]
        s = self._stored_computed(sid)[f"{regime}_regime_best"]["structure"]
        expected_gross = round((s["basic"] + s["hra"] + s["lta"]
                                + s["special_allowance"]) / 12, 2)
        self.assertAlmostEqual(basis["gross_monthly_cash"], expected_gross, places=2)

    def test_payout_basis_reconciles_on_an_ordinary_export(self):
        # net == gross - employee PF - TDS - PT, on the payload's own numbers.
        # A never-flip test, kept deliberately: it holds before and after D-S7
        # and exists so a stored/fresh mix cannot pass unnoticed while the
        # figures happen to agree.
        sid = self._submit_and_approve()
        basis = self._export(sid).get_json()["payout_basis"]
        self.assertAlmostEqual(
            basis["net_monthly"],
            basis["gross_monthly_cash"] - basis["employee_pf_monthly"]
            - basis["tds_monthly"] - basis["professional_tax_monthly"],
            delta=1.0)

    def test_the_computation_basis_label_says_stored(self):
        # D-S4 shipped this label reading recomputed_at_export for the forecast.
        # D-S7 makes that false, so the label moves with the behaviour.
        sid = self._submit_and_approve()
        basis = self._export(sid).get_json()["computation_basis"]
        self.assertEqual(basis["treasury_forecast"]["source"], "stored_at_submission")
        self.assertEqual(basis["guardrail"]["source"], "stored_at_submission")


class TestARowWithNoStoredForecastIsRefused(_Base):
    """
    D-S7b, ruled refuse. A row whose funding figure was never recorded cannot
    have been funded against a recorded figure, so there is nothing to honour —
    and silently recomputing would reintroduce the divergence for exactly the
    oldest rows.
    """

    def test_the_export_is_refused_with_a_reason_naming_the_missing_figure(self):
        sid = self._submit_and_approve()
        self._rewrite_stored_computed(sid, lambda c: c.pop("treasury_forecast", None))
        self.assertNotIn("treasury_forecast", self._stored_computed(sid),
                         "precondition: the stored forecast must be gone")
        resp = self._export(sid)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("treasury_forecast", resp.get_json()["error"])

    def test_a_row_that_has_one_still_exports(self):
        # The both-states pair: the refusal must not be satisfied by refusing
        # everything.
        sid = self._submit_and_approve()
        self.assertEqual(self._export(sid).status_code, 200)

    def test_the_refusal_does_not_fall_back_to_recomputing(self):
        sid = self._submit_and_approve()
        self._rewrite_stored_computed(sid, lambda c: c.pop("treasury_forecast", None))
        body = self._export(sid).get_json()
        self.assertNotIn("treasury_forecast", body)
        self.assertNotIn("payouts", body)


class TestNothingElseMoves(_Base):
    """Containment: D-S7 changes where a figure comes from, not what else the
    route does."""

    def test_the_guardrail_is_still_the_stored_one(self):
        sid = self._submit_and_approve()
        stored = self._stored_computed(sid)
        body = self._export(sid).get_json()
        self.assertEqual(body["guardrail"], stored.get("guardrail"))

    def test_an_unapproved_row_is_still_refused_first(self):
        resp = self.client.post("/api/submissions",
                                json={"source": "single", "row": dict(ROW)})
        sid = resp.get_json()["submission_id"]
        export = self._export(sid)
        self.assertEqual(export.status_code, 400)
        self.assertIn("not approved", export.get_json()["error"])

    def test_missing_bank_details_are_still_refused(self):
        # The guard that, as it happens, is the only thing excluding the one
        # real row D-S7b's population measurement found.
        row = dict(ROW, employee_name="No Bank", email="nobank@test.com")
        row.pop("bank_account_number"); row.pop("ifsc")
        sid = self._submit_and_approve(row)
        export = self._export(sid)
        self.assertEqual(export.status_code, 400)
        self.assertIn("bank_account_number", export.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
