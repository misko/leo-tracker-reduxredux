"""Verify a shared cone must contain each candidate's whole observed track."""

import numpy as np
import pytest
from cones import axes, enu_los, support


def test_axes_separation_and_controls():
    pair = axes("nominal")
    assert abs(np.degrees(np.arccos(pair[0] @ pair[1])) - 20) < 1e-10
    np.testing.assert_array_equal(axes("swapped"), pair[::-1])
    np.testing.assert_array_equal(axes("copointed"), [[0, 0, 1], [0, 0, 1]])


def test_interpolation_and_enu_frame():
    # At latitude/longitude zero: ECEF X is up, Y east, Z north.
    positions = np.array([[[[2.0, 0, 0]], [[2.0, 2, 0]]]])
    result = enu_los(positions, [-1, 1], 0, np.array([1.0, 0, 0]), 0, 0)
    np.testing.assert_allclose(result, [[[1 / np.sqrt(2), 0, 1 / np.sqrt(2)]]])
    with pytest.raises(ValueError):
        enu_los(positions, [-1, 1], 2, np.zeros(3), 0, 0)


def test_full_training_arc_and_held_isolation():
    angles = np.radians([[10, 35, 15], [15, 15, 60]])
    los = np.stack([np.sin(angles), np.zeros_like(angles), np.cos(angles)], axis=-1)
    result = support(los, 0, [True, True, False], [0.6, 0.4], "copointed")
    assert result["widths"][0]["supported_candidates"] == 1
    assert result["widths"][0]["training_posterior_mass"] == 0.4
    assert result["widths"][0]["conditional_held_all_inside_mass"] == 0
    changed = los.copy()
    changed[:, 2] = [0, 0, 1]
    new = support(changed, 0, [True, True, False], [0.6, 0.4], "copointed")
    assert [r["training_posterior_mass"] for r in new["widths"]] == [
        r["training_posterior_mass"] for r in result["widths"]
    ]
    assert new["widths"][0]["conditional_held_all_inside_mass"] == 1
