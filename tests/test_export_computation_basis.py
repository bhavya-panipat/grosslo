"""
tests/test_export_computation_basis.py — D-S4, ruled 2026-09-28: label, don't
recompute.

The per-row RazorpayX export mixes two bases in one payload. `guardrail` is the
verdict a human approved, stored at submission (NEIGHBOURING_ROUTE_CLAIM_SWEEP.md,
X1). Recomputing it would silently replace an approved verdict with one nobody
reviewed, so the payload says which part came from where.

**Retargeted 2026-09-28 by D-S7a, which this file's own source comment
anticipated.** When D-S4 shipped, `treasury_forecast`, `payouts` and
`payout_basis` were recomputed at export and labelled so. D-S7a then ruled the
stored figure canonical — the Finance funding gate already sums it — so all four
parts now read `stored_at_submission`. The assertions below moved with the
behaviour rather than being deleted, and each carries a note saying which ruling
moved it.

The load-bearing test is the sentinel one: it overwrites the stored guardrail
and requires the export to serve the overwritten value. A route that quietly
recomputed the guardrail would pass every labelling test and fail that one.
"""

import json
import unittest

import app as flask_app
import review_queue

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
        # D-S7a: these three read stored_at_submission since the export stopped
        # recomputing. Before that ruling they read recomputed_at_export.
        for part in ("treasury_forecast", "payouts", "payout_basis"):
            with self.subTest(part=part):
                self.assertEqual(basis[part]["source"], "stored_at_submission")

    def test_the_guardrail_is_dated_by_its_submission(self):
        sid = self._submit_and_approve(dict(ROW))
        tenant_id = review_queue._checked_tenant_id(1)
        created_at = review_queue.get_submission(tenant_id, sid)["created_at"]
        basis = self._export(sid)["computation_basis"]
        self.assertEqual(basis["guardrail"]["computed_at"], created_at)
        # D-S7a: every part is now dated by the submission, because every part
        # comes from it. Before that ruling this asserted the opposite for
        # treasury_forecast — it carried the export's own time.
        self.assertEqual(basis["treasury_forecast"]["computed_at"], created_at)

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

    def test_the_served_forecast_is_the_stored_one_not_a_fresh_computation(self):
        """
        D-S7a retargeted this. It previously asserted the payload's forecast
        equalled a FRESH optimize()+treasury_forecast() — which still passes
        today, because an unchanged engine produces the same dict, and would
        silently start failing on the first engine change while the route was
        behaving correctly. Comparing against storage is the assertion that
        survives; comparing against a fresh computation is precisely what D-S7
        exists to stop anything relying on.
        """
        sid = self._submit_and_approve(dict(ROW))
        tenant_id = review_queue._checked_tenant_id(1)
        stored = review_queue.get_submission(tenant_id, sid)["rows"][0]["computed"]
        self.assertEqual(self._export(sid)["treasury_forecast"],
                         stored["treasury_forecast"])


if __name__ == "__main__":
    unittest.main()
