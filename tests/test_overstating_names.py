"""
tests/test_overstating_names.py — D-S5: two names that describe more than their
content.

Both were found by the deliberate sweep in NEIGHBOURING_ROUTE_CLAIM_SWEEP.md, not
by an incident, and neither is an arithmetic error. They are recorded and fixed
together because they fail the same way: a reader who trusts the name gets a
wrong idea of what is there.

  1. `/api/batch-audit`'s `summary.total_rows` is the VALID-row count. Malformed
     rows still appear in `rows[]` carrying an `error`, and are not counted.
  2. `api_export_approved_row`'s docstring promised "a Bulk Salary Revision
     XLSX, current vs. corrected". The workbook has no current column at all.

The second is pinned here by asserting what the workbook actually contains,
rather than by asserting the text of a docstring. A docstring test would break on
rewording; a content test breaks only if the file changes, which is the thing the
docstring is supposed to describe.
"""

import unittest

from salary_revision_export import build_salary_revision_workbook

from tests.test_review_workflow import ReviewQueueTestCase, _client


GOOD_ROW = {
    "name": "Valid", "ctc": 1_548_000, "basic": 600_000, "hra": 300_000, "lta": 0,
    "special_allowance": 576_000, "employer_pf": 72_000, "employer_nps": 0,
    "nps_opted": False, "rent_paid": 240_000, "city": "metro",
    "band_min": 1_400_000, "band_max": 1_700_000,
}
MALFORMED_ROW = {"name": "Malformed", "ctc": "not-a-number", "basic": 1,
                 "band_min": 1, "band_max": 2}


class TestTheValidRowCountSaysWhatItCounts(ReviewQueueTestCase):
    """
    D-S5 part 1. The field is the valid-row count, so it is named that.

    Its one consumer already reads it correctly — `batch-flow.tsx` passes it as
    `processedCount` against the uploaded row count and renders
    "Processed Records: N / M" with a throughput percentage, which surfaces the
    gap rather than hiding it. So this is a rename for the next caller, not a
    repair of a live defect, and the test says so rather than implying a bug.
    """

    def setUp(self):
        super().setUp()
        self.client = _client()

    def _audit(self, rows):
        resp = self.client.post("/api/batch-audit", json={"rows": rows})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    def test_the_count_is_named_for_the_rows_it_counts(self):
        body = self._audit([GOOD_ROW, dict(GOOD_ROW, name="Valid2"), MALFORMED_ROW])
        summary = body["summary"]
        self.assertEqual(summary["valid_row_count"], 2)
        # Three rows were submitted and three come back; one carries an error.
        self.assertEqual(len(body["rows"]), 3)
        self.assertIn("error", body["rows"][2])

    def test_the_overstating_name_is_gone_rather_than_kept_beside_the_new_one(self):
        # Keeping both would be two names for one value, which is the second
        # source of truth this project does not allow. The rename has to be a
        # rename.
        body = self._audit([GOOD_ROW])
        self.assertNotIn("total_rows", body["summary"])

    def test_every_other_summary_field_is_untouched(self):
        # The rename must not be the vehicle for anything else.
        body = self._audit([GOOD_ROW, MALFORMED_ROW])
        summary = body["summary"]
        for field in ("clean_count", "flagged_count", "epfo_cap_exceeded_count",
                      "regime_mismatch_count", "statutory_violation_count",
                      "total_excess_contribution", "total_unclaimed_savings",
                      "rows_not_reconciling"):
            with self.subTest(field=field):
                self.assertIn(field, summary)
        self.assertEqual(summary["flagged_count"],
                         summary["valid_row_count"] - summary["clean_count"])


class TestTheWorkbookHasNoCurrentColumn(unittest.TestCase):
    """
    D-S5 part 2. `api_export_approved_row`'s docstring promised "current vs.
    corrected". `build_salary_revision_workbook()` reads only `corrected` — the
    word `current` appeared in that module exactly once, in a docstring
    describing a parameter it never used.

    Pinning the workbook's real content so the docstring cannot drift back into
    describing a comparison the file does not contain. **This is not a decision
    that the file SHOULD contain one** — whether a revision sheet ought to show
    current beside corrected is a product question, recorded as such and not
    settled here.
    """

    ROW = {
        "employee_name": "Ivan", "ctc": 4_000_000,
        "corrected": {"basic": 2_000_000, "hra": 1_000_000, "lta": 0,
                      "special_allowance": 760_000, "employer_pf": 240_000,
                      "employer_nps": 0},
    }

    def test_the_custom_sheet_has_exactly_the_corrected_columns(self):
        wb = build_salary_revision_workbook([dict(self.ROW)])
        header = [c.value for c in wb["Custom Structure"][1]]
        self.assertEqual(header, ["Employee Name", "CTC", "Basic", "HRA", "LTA",
                                  "Special Allowance", "Employer PF",
                                  "Employer NPS"])

    def test_no_sheet_anywhere_names_a_current_column(self):
        wb = build_salary_revision_workbook([dict(self.ROW)])
        for sheet in wb.sheetnames:
            header = [str(c.value) for c in wb[sheet][1] if c.value is not None]
            with self.subTest(sheet=sheet):
                self.assertFalse([h for h in header if "current" in h.lower()],
                                 f"{sheet} header names a current column: {header}")

    def test_the_corrected_values_are_what_lands_in_the_cells(self):
        wb = build_salary_revision_workbook([dict(self.ROW)])
        custom = wb["Custom Structure"]
        as_dict = dict(zip([c.value for c in custom[1]],
                           [c.value for c in custom[2]]))
        for field, label in (("basic", "Basic"), ("hra", "HRA"),
                             ("special_allowance", "Special Allowance"),
                             ("employer_pf", "Employer PF")):
            with self.subTest(field=field):
                self.assertEqual(as_dict[label], self.ROW["corrected"][field])

    def test_the_workbook_does_not_require_a_current_key(self):
        # The caller stopped passing one, because nothing read it. Building
        # without it must work — otherwise the dead parameter is load-bearing
        # after all, and that is worth knowing.
        wb = build_salary_revision_workbook([dict(self.ROW)])
        self.assertEqual(wb.sheetnames,
                         ["Read Me", "Default Structure", "Custom Structure"])

    def test_a_supplied_current_is_still_accepted_and_still_ignored(self):
        # Defensive: an older caller (or a test) may still pass `current`. It
        # must not crash, and it must not appear.
        row = dict(self.ROW, current={"basic": 1_800_000, "hra": 900_000,
                                      "lta": 100_000, "special_allowance": 300_000,
                                      "employer_pf": 900_000, "employer_nps": 0})
        wb = build_salary_revision_workbook([row])
        custom = wb["Custom Structure"]
        as_dict = dict(zip([c.value for c in custom[1]],
                           [c.value for c in custom[2]]))
        self.assertEqual(as_dict["Basic"], self.ROW["corrected"]["basic"])


if __name__ == "__main__":
    unittest.main()
