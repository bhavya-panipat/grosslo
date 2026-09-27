"""
tests/test_export_computation_basis.py — D-S4, ruled 2026-09-28: label, don't
recompute.

The per-row RazorpayX export mixes two bases in one payload. `guardrail` is the
verdict a human approved, stored at submission; `treasury_forecast`, `payouts`
and `payout_basis` are recomputed at export (NEIGHBOURING_ROUTE_CLAIM_SWEEP.md,
X1). Recomputing the guardrail too would silently replace an approved verdict
with one nobody reviewed, so the payload now says which part came from where.

The load-bearing test is the sentinel one: it overwrites the stored guardrail
and requires the export to serve the overwritten value. A route that quietly
recomputed the guardrail would pass every labelling test and fail that one.
"""

import json
import unittest

import app as flask_app
import review_queue
from optimizer import optimize
from payroll_breakdown import treasury_forecast

from tests.test_export_basis_flags import ROW, _ExportBase


class TestComputationBasisLabel(_ExportBase):

    def _export(self, sid):
        resp = self.client.post(f"/api/submissions/{sid}/rows/0/export")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    def test_each_part_says_where_it_came_from(self):
        sid = self._submit_and_approve(dict(ROW))
        basis = self._export(sid)["computation_basis"]
        self.assertEqual(basis["guardrail"]["source"], "stored_at_submission")
        self.assertEqual(basis["guardrail"]["note"], flask_app.GUARDRAIL_STORED_NOTE)
        for part in ("treasury_forecast", "payouts", "payout_basis"):
            with self.subTest(part=part):
                self.assertEqual(basis[part]["source"], "recomputed_at_export")

    def test_the_guardrail_is_dated_by_its_submission(self):
        sid = self._submit_and_approve(dict(ROW))
        tenant_id = review_queue._checked_tenant_id(1)
        created_at = review_queue.get_submission(tenant_id, sid)["created_at"]
        basis = self._export(sid)["computation_basis"]
        self.assertEqual(basis["guardrail"]["computed_at"], created_at)
        # The recomputed parts carry the export's own time, not the submission's.
        self.assertNotEqual(basis["treasury_forecast"]["computed_at"], created_at)

    def test_the_stored_guardrail_is_served_not_recomputed(self):
        """The property the ruling rests on, proven rather than asserted."""
        sid = self._submit_and_approve(dict(ROW))
        sentinel = {"passed": False, "checks": [], "SENTINEL": "stored verdict"}
        tenant_id = review_queue._checked_tenant_id(1)
        with review_queue._conn(tenant_id) as conn:
            cur = conn.execute(
                "SELECT computed_json FROM submission_rows "
                "WHERE tenant_id = %s AND submission_id = %s AND row_index = 0",
                (tenant_id, sid))
            computed = json.loads(cur.fetchone()["computed_json"])
            computed["guardrail"] = sentinel
            conn.execute(
                "UPDATE submission_rows SET computed_json = %s "
                "WHERE tenant_id = %s AND submission_id = %s AND row_index = 0",
                (json.dumps(computed), tenant_id, sid))
        self.assertEqual(self._export(sid)["guardrail"], sentinel)

    def test_the_recomputed_parts_are_unchanged_by_the_label(self):
        sid = self._submit_and_approve(dict(ROW))
        body = self._export(sid)
        rec = optimize(ctc=ROW["ctc"], rent_paid=ROW["rent_paid"], city=ROW["city"],
                       nps_opted=ROW["nps_opted"])["recommended"]
        fresh = treasury_forecast(rec.structure, rec.tax_breakdown,
                                  work_location=ROW["work_location"])
        self.assertEqual(body["treasury_forecast"], fresh)


if __name__ == "__main__":
    unittest.main()
