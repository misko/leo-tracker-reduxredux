from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import marginal
from tools.pipeline_eval.variants import algo08_curved_design as variant


@pytest.mark.parametrize("fitted_c", [False, True])
def test_curved_design_follows_current_inputs_without_mutating_old_results(fitted_c, monkeypatch):
    rng = np.random.default_rng(404)
    n = 19
    problem = SimpleNamespace(
        variant="radio_noise", labels=[9, 15, 25], supported=[25, 9], supported_local=[2, 0],
        flat_labels=np.arange(n) % 3, reference=np.array([0.1, -0.5, 1.22]),
        phase_sigma=np.array([2.5, 1.5, 3.]), q=rng.uniform(0.9, 1.1, n),
        hardware=rng.normal(size=(n, 8 + int(fitted_c))), smooth=rng.normal(size=(n, 6)),
        constants=np.eye(n, 4) * 1000, values=rng.normal(size=n), sigma=100.,
    )
    frequency, elevation, derivative = rng.normal(size=(3, n))
    derivative[2] = -0.
    modes = rng.normal(size=(n, 3))
    modes[0] = -0.
    monkeypatch.setattr(marginal, "_phase_geometry", lambda *args: (
        frequency, elevation, derivative, modes,
    ))
    stock = marginal.JointMarginal.calculate
    prior_result = None
    for change in range(3):
        if change == 1:
            problem.hardware[3, 2] *= -2.
            problem.flat_labels[2] = 1
            problem.constants[3, 2] = -0.
        if change == 2:
            problem.supported_local[:] = [0, 0]
        expected = stock(problem, [0., 0.], geometry_only=True)
        with variant.measured_curved_design(enabled=True) as count:
            actual = marginal.JointMarginal.calculate(problem, [0., 0.], geometry_only=True)
        assert actual["features"].flags.c_contiguous
        for key, array in expected.items():
            assert actual[key].tobytes() == array.tobytes(), key
        assert count["direct_assembly_calls"] == int(change != 2)
        if prior_result is not None:
            assert not np.shares_memory(prior_result[0], actual["features"])
            assert prior_result[0].tobytes() == prior_result[1]
        prior_result = actual["features"], actual["features"].tobytes()


@pytest.mark.parametrize("trim", [False, True])
@pytest.mark.parametrize("history", [False, True])
def test_selected_design_preserves_native_values_layout_and_source(trim, history):
    rows, columns = 29, 47
    rng = np.random.default_rng(2711)
    features = rng.normal(size=(rows, columns))
    features[1, -5:] = -0.
    features[2, -5:] = np.nextafter(0., 1.)
    scales = np.ones(columns)
    if history:
        scales[-10:] = 0.3
    keep = np.ones(rows, dtype=bool)
    if trim:
        keep[::7] = False
    expected = (features * scales)[keep]
    original = features.tobytes()
    actual = variant.selected_design(features, scales, keep)
    assert actual.dtype == expected.dtype
    assert actual.strides == expected.strides
    assert actual.tobytes() == expected.tobytes()
    actual[:] = 0
    assert features.tobytes() == original
