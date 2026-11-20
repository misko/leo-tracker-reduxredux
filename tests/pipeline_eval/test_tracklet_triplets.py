from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import tracklet_triplets as model


def test_three_snapshots_cancel_a_shared_carrier_offset_and_keep_central_peak_consistent():
    t = (0.25, 4.25, 8.25)

    def capture(offset):
        probes = [
            dict(
                valid_start_counter=round((a - 0.010) * 100_000),
                receiver_id=0,
                channel=3,
                actual_rf_hz=model.RF,
                candidates=[
                    dict(
                        fractional_tracking_cfo_hz=v + offset,
                        fractional_margin=0.8,
                        passed_fractional_margin_gate=True,
                        candidate_rank=i,
                    )
                    for i, v in enumerate(values)
                ],
            )
            for a, values in zip(t, ((109_000,), (102_000, 104_000), (97_000,)), strict=True)
        ]
        return SimpleNamespace(probes=probes, first_counter=0, sample_rate_hz=100_000, probe_ms=20)

    (a,) = model.triplets(capture(0.0))
    (b,) = model.triplets(capture(112_000.0))
    np.testing.assert_allclose(a.features, b.features)
    assert a.features.shape == (2, 2)
    np.testing.assert_allclose(a.features, [[-1500, -1500], [500, -500]])


def test_unequal_snapshot_spacing_propagates_the_covariance_of_the_middle_measurement():
    t = np.array([0, 3.6, 8.2])
    d0, d1 = np.diff(t)
    A = np.array([[-1 / t[-1], 0, 1 / t[-1]], [1 / d0, -1 / d0 - 1 / d1, 1 / d1]])
    cov = model.ENDPOINT_NOISE_HZ**2 * A @ A.T + np.eye(2) * model.NUISANCE_HZ_S**2
    test = model.Triplet(0, tuple(t), np.array([[-1800.0], [300.0]]), model.PERIOD)
    _, _, _, beta, (s, q), _, _ = model.observation([test])
    assert s[0] ** 2 == pytest.approx(cov[0, 0])
    assert beta[0] == pytest.approx(cov[1, 0] / cov[0, 0])
    assert q[0] ** 2 == pytest.approx(cov[1, 1] - cov[1, 0] ** 2 / cov[0, 0])


def test_joint_likelihood_resolves_deliberate_slope_tie_and_detects_reversed_shape():
    trial = model.Triplet(0, (0.0, 4.0, 8.0), np.array([[-2200.0], [600.0]]), model.PERIOD)
    obs = model.observation([trial])
    prediction = np.array([[[-2200.0], [-2200.0]], [[600.0], [180.0]]])
    joint, slope, reverse = model.mixture(prediction, np.ones((2, 1)), obs)[:, :, 0]
    assert joint[2] == pytest.approx(1, abs=0.01)
    assert slope[2] == pytest.approx(2)
    assert joint[0] > reverse[0] + 1
