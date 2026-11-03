import unittest

import numpy as np

from plot_remaining import ALIAS, align, cfo, members_mask


class RemainingTests(unittest.TestCase):
    def test_alignment_rejects_reordered_rows(self):
        metadata = [dict(time_s=1., observation_id="a"), dict(time_s=2., observation_id="b")]
        state = dict(associated=np.array([True, False]), times_s=np.array([1., 2.]))
        np.testing.assert_array_equal(align(metadata, state), [True, False])
        with self.assertRaises(AssertionError):
            align(metadata[::-1], state)

    def test_exact_membership_never_expands_to_context_points(self):
        metadata = [dict(observation_id=k) for k in ("a", "b", "c")]
        np.testing.assert_array_equal(members_mask(metadata, ["b"]), [False, True, False])
        for bad in [["x"], ["a", "a"]]:
            with self.assertRaises(ValueError):
                members_mask(metadata, bad)

    def test_fold_is_per_mark_and_alias_invariant(self):
        values = np.array([2000., -70000., 110000.])
        np.testing.assert_allclose(cfo(values, True), cfo(values + ALIAS, True), atol=1e-10)
        np.testing.assert_array_equal(cfo(values, False), values / 1000)
