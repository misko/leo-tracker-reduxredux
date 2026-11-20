from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import trackless_likelihood as fit


def test_folded_same_lane_rate_cancels_rf_offset_and_preserves_snapshot_alternatives():
    def at(time_s, values, rf_hz=12e9):
        return dict(
            valid_start_counter=int((time_s - 0.010) * 100_000),
            receiver_id=0,
            channel=2,
            actual_rf_hz=rf_hz,
            candidates=[
                dict(
                    candidate_rank=i,
                    fractional_margin=0.42,
                    fractional_tracking_cfo_hz=f,
                    passed_fractional_margin_gate=True,
                )
                for i, f in enumerate(values)
            ],
        )

    n = fit.PERIOD / 2
    a = [at(0.25, [-n + 200, 35_000]), at(2.25, [n - 700, 25_000])]
    b = [at(0.25, [-n + 200 + 3000, 38_000]), at(2.25, [n - 700 + 3000, 28_000])]
    options = dict(first_counter=0, sample_rate_hz=100_000, probe_ms=20)
    (left,) = fit.slices(SimpleNamespace(probes=a, **options))
    (right,) = fit.slices(SimpleNamespace(probes=b, **options))
    assert len(left.rates) == 4
    np.testing.assert_allclose(left.rates, right.rates)
    assert left.rates[0] == pytest.approx(-450 * fit.RF / 12e9)
    assert not fit.slices(SimpleNamespace(probes=[a[0], at(2.25, [n - 700], 12.1e9)], **options))


def test_orbit_normalization_prevents_duplicate_or_unrelated_orbits_inflating_likelihood():
    data = np.array([[25.0]])
    mask, sigma, support = np.ones_like(data, dtype=bool), np.array([100.0]), np.array([100_000.0])
    unit = np.array([[25.0]])
    single = fit.mixture(unit, np.ones_like(unit), data, mask, sigma, support)
    duplicates = fit.mixture(
        np.repeat(unit, 40, axis=0), np.ones((40, 1)), data, mask, sigma, support
    )
    unrelated = fit.mixture(
        np.array([[25.0], [2500.0]]), np.ones((2, 1)), data, mask, sigma, support
    )
    assert single[0][0] == pytest.approx(duplicates[0][0])
    assert duplicates[3][0] == pytest.approx(40)
    assert unrelated[0][0] < single[0][0]


def test_epoch_weights_stop_dense_dual_receiver_lanes_magnifying_one_epoch():
    epochs = np.array([0, 0, 0, 1, 2])
    held = np.array([True, True, True, True, False])
    values = np.array([3.0, 3.0, 3.0, -3.0, 10_000.0])
    np.testing.assert_array_equal(fit.epoch_means(values, epochs, held), [3.0, -3.0])
