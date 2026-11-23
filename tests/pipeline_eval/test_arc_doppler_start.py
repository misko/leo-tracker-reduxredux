from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from arc_doppler_start import arcs, contrast, select
from arc_doppler_start_trial import recall


def test_contrast_cancels_constant_without_ignoring_horizon():
    predicted = np.array([[1., 4., 9., 16., 25., 36.], [2., 9., 6., 4., 3., 0.]])
    tangent = np.zeros_like(predicted)
    elevation = np.ones_like(predicted)
    observed = predicted[0] + 20_000
    sigma = np.ones(2)
    loss, _ = contrast(observed, predicted, tangent, elevation, sigma)
    shifted, _ = contrast(observed - 20_000., predicted, tangent, elevation, sigma)
    np.testing.assert_allclose(loss, shifted, rtol=0, atol=1e-15)
    assert np.argmin(loss) == 0
    elevation[0, 2] = -1
    before, _ = contrast(observed, predicted, tangent, elevation, sigma)
    assert np.argmin(before) == 1


def test_fixed_stencil_requires_two_curved_axes_and_interior():
    assert select(np.array([0., 0., 0., 2., 2.]), 10.)[1] == "flat_or_indefinite"
    assert select(np.array([1., 5., -2., 2., 2.]), 10.)[1] == "edge_or_outside"
    point, reason = select(np.array([0., 1.4, .6, .7, 1.3]), 10.)
    np.testing.assert_allclose(point, [2., -1.5])
    assert reason is None


def test_selects_one_longest_arc_per_receiver_bank_and_third():
    tracks = [dict(receiver=r, channel=c, times=np.linspace(t, t + span, n)) for r, c, t, span, n in
              [(1, 1, 2, 16, 7), (1, 1, 1, 19, 10), (1, 8, 2, 19, 7), (2, 1, 15, 19, 7), (2, 2, 100, 20, 5)]]
    selected = arcs(tracks, [0, 1, 2, 3, 4])
    assert [index for _, index in selected] == [1, 2, 3]


def test_recall_compares_signed_alias_separately_from_orbit_presence():
    original = [("a", 3, 123, 0), ("b", 8, 456, -1)]
    candidate = [("a", 3, 123, 1), ("b", 8, 456, -1)]
    result = recall(original, candidate, {"a": [3, 4], "b": [7, 8]})
    assert result["sampled_original_winners"] == 2
    assert result["matching_owner_alias_rows"] == 1
    assert not result["full_signature"]
