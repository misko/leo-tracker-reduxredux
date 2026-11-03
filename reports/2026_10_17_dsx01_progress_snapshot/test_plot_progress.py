"""Guard complete-policy coverage plots against changing the comparison cohort."""

import unittest

from plot_progress import combine


class CohortTests(unittest.TestCase):
    def test_preserves_policy_tradeoffs_without_window_winners(self):
        rows = combine(dict(
            original=[dict(window="a", observations=10, assigned=2),
                      dict(window="b", observations=5, assigned=1)],
            variant=[dict(window="b", observations=5, assigned=0),
                     dict(window="a", observations=10, assigned=8)],
        ))
        self.assertEqual([r["variant"] for r in rows], [8, 0])
        self.assertEqual(sum(r["variant"] for r in rows), 8)

    def test_rejects_missing_duplicate_or_changed_denominators(self):
        original = [dict(window="a", observations=10, assigned=2)]
        for invalid in [[], original * 2,
                        [dict(window="a", observations=11, assigned=2)],
                        [dict(window="a", observations=10, assigned=11)]]:
            with self.assertRaises(ValueError):
                combine(dict(original=original, variant=invalid))
