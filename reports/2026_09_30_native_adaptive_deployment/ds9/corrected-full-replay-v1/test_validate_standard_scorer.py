#!/usr/bin/env python3
"""Focused tests for the report-only standard scorer validator."""

from __future__ import annotations

import unittest

import numpy as np
from validate_standard_scorer import (
    interpolate,
    possible_satellites,
    validate_mask_and_weight,
)


class HermiteInterpolationTests(unittest.TestCase):
    def test_linear_state_is_exact(self) -> None:
        states = np.zeros((1, 2, 6), dtype=float)
        states[0, 0, :3] = (1.0, 2.0, 3.0)
        states[0, 1, :3] = (3.0, 6.0, 9.0)
        states[0, 0, 3:] = states[0, 1, 3:] = (1.0, 2.0, 3.0)
        position, velocity = interpolate(states, np.asarray([[0.5]]), 2.0)
        np.testing.assert_array_equal(position[0, 0, 0], (2.0, 4.0, 6.0))
        np.testing.assert_array_equal(velocity[0, 0, 0], (1.0, 2.0, 3.0))

    def test_nonfinite_coordinate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-finite interpolation coordinate"):
            interpolate(np.zeros((1, 2, 6)), np.asarray([[np.nan]]), 1.0)

    def test_out_of_range_coordinate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside saved authority"):
            interpolate(np.zeros((1, 2, 6)), np.asarray([[2.0]]), 1.0)

    def test_mask_and_encoded_weight_are_bound(self) -> None:
        times = np.asarray((0.1, 0.9, 1.1, 2.1))
        np.testing.assert_array_equal(
            validate_mask_and_weight(times, np.asarray((0, 1, 1, 0)), 3),
            (False, True, True, False),
        )
        with self.assertRaisesRegex(ValueError, "not binary"):
            validate_mask_and_weight(times, np.asarray((0, 2, 1, 0)), 3)
        with self.assertRaisesRegex(ValueError, "weight differs"):
            validate_mask_and_weight(times, np.asarray((0, 1, 1, 0)), 4)

    def test_horizon_prefilter_rejects_below_and_keeps_above(self) -> None:
        states = np.zeros((2, 3, 6), dtype=float)
        states[0, :, 0] = -2.0
        states[1, :, 0] = 2.0
        possible = possible_satellites(
            states,
            np.asarray((0.0, 1.0)),
            np.asarray((1.0, 0.0, 0.0)),
            np.asarray((1.0, 0.0, 0.0)),
            -5.0,
            6.0,
        )
        np.testing.assert_array_equal(possible, (False, True))


if __name__ == "__main__":
    unittest.main()
