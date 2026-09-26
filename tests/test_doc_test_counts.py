"""
The documented test counts are generated, not maintained
(scripts/generate_test_counts_md.py).

Without this test, "generated" would mean "generated at some point", and the
drift it exists to remove would come back through the side door — someone
corrects a number by hand because it is right there and readable, and nothing
notices. That is not hypothetical here: README.md's count read "150 tests total
across five files", described itself as "counted directly from the test methods
in the repo, not estimated", invited the reader to re-run and confirm, and was
465 tests and thirteen files out of date. Correcting it by hand went 615, 625,
633 inside a week, because the number is downstream of every commit that
touches tests/.

The same guard as tests/test_compliance_rules.py's
TestTheDocumentIsGeneratedNotMaintained, for the same reason.
"""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "generate_test_counts_md.py")


class TestTheCountsAreGeneratedNotMaintained(unittest.TestCase):

    def test_the_committed_counts_match_what_the_generator_produces(self):
        result = subprocess.run([sys.executable, SCRIPT, "--check"],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(
            result.returncode, 0,
            "The test counts in README.md / FINOS_PROJECT_BRIEF.md are out of "
            "sync with the suite. Run:\n"
            "    python3 scripts/generate_test_counts_md.py\n\n"
            f"{result.stdout}{result.stderr}")

    def test_the_hand_written_descriptions_survive_generation(self):
        # The generator owns the numbers and nothing else. If it ever started
        # rewriting the prose, the docs would still be "in sync" and would have
        # lost the thing they are kept for — what each file actually covers.
        #
        # This reads the committed file rather than invoking the generator: a
        # test that writes to the repo would silently "fix" the docs while the
        # check above reported them broken, and would mutate a tree other
        # sessions share. The check above already proves the committed file is
        # what the generator produces, so asserting on it asserts on generated
        # output.
        with open(os.path.join(ROOT, "README.md")) as f:
            doc = f.read()
        for phrase in ("the marginal relief calculation",
                       "the maker-checker flow end",
                       "every routing outcome",
                       "never subtract across two"):
            self.assertIn(phrase, doc,
                          f"generation dropped hand-written prose: {phrase!r}")


if __name__ == "__main__":
    unittest.main()
