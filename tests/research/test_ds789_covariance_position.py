import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_covariance_position import CovariancePosition, profile_offsets


def test_offset_global_profile_and_stationarity():
    residual = np.array([[10.0, 30.0, -20.0], [1e7, 1e7 + 3, 1e7 - 2], [-5e6, -5e6 + 4, -5e6 - 3]])
    precision = np.eye(3) / 10000
    offsets, q, _, stationarity = profile_offsets(residual, precision)
    assert stationarity < 1e-8
    for i, offset in enumerate(offsets):
        probes = np.r_[
            np.linspace(min(0.0, residual[i].mean()), max(0.0, residual[i].mean()), 10001),
            offset - 1,
            offset + 1,
        ]
        losses = (
            3.5 * np.log1p(((residual[i][None, :] - probes[:, None]) ** 2).sum(axis=1) / 40000)
            + probes**2 / 2e12
        )
        selected = 3.5 * np.log1p(q[i] / 4) + offset**2 / 2e12
        assert selected <= losses.min() + 1e-9


def test_profiled_mixture_gradient_and_held_values_do_not_affect_fit():
    rng = np.random.default_rng(9)
    design = rng.normal(size=(3, 12, 3)) * 30

    class Linear:
        def __init__(self, document, config):
            pass

        def prediction(self, track, x):
            return np.einsum("knp,p->kn", design, x), np.ones(3, dtype=bool)

    track = {
        "track_id": "t",
        "mask": np.arange(12) % 3 != 0,
        "y": rng.normal(size=12) * 100,
        "times_s": np.arange(12),
        "catalogue_size": 100,
    }
    docs = [{"session_id": "s", "tracks": [track]}]
    for decay in (0, 10):
        model = CovariancePosition(docs, {}, decay, Linear)
        point = np.array([0.1, -0.2, 0.3])
        loss, grad = model.value_gradient(point)
        for axis in range(3):
            delta = np.eye(3)[axis] * 1e-4
            finite = (
                model.evaluate(point + delta, gradient=False)["score"]
                - model.evaluate(point - delta, gradient=False)["score"]
            ) / 2e-4
            np.testing.assert_allclose(-grad[axis], finite, atol=1e-7)
        track["y"][~track["mask"]] += 1e6
        changed_loss, changed_grad = model.value_gradient(point)
        assert loss == changed_loss
        np.testing.assert_array_equal(grad, changed_grad)
