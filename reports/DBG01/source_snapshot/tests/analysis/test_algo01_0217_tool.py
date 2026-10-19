"""Guards for diagnostic geometry and fixed-data prior sensitivity."""

from types import SimpleNamespace

import investigate_algo01_ds23_0217 as module
import numpy as np


def test_regional_starts_do_not_depend_on_reference_gps():
    starts = np.asarray(module.STARTS)
    assert starts.shape == (81, 2)
    assert len(module.DISCOVERY_STARTS) == 13
    assert np.max(np.linalg.norm(starts, axis=1)) <= 10
    np.testing.assert_array_equal(starts[0], [0, 0])
    assert np.max(abs(starts)) <= 12.5


def test_prior_sensitivity_does_not_modify_cached_baseline_widths(monkeypatch):
    monkeypatch.setattr(module, "DiagnosticNormal", lambda *a, **kw: SimpleNamespace(labels=[1, 3]))
    monkeypatch.setattr(module, "phase_widths", lambda *a: (np.array([1.1, 4.0]), None))
    scan = SimpleNamespace(radio_sigma_hz=150)
    keep = np.ones(3, bool)
    baseline = module.problem(scan, {}, "c0", keep)
    wider = module.problem(scan, {}, "c0", keep, variant="phase_x2")
    floor = module.problem(scan, {}, "c0", keep, variant="phase_floor3")
    np.testing.assert_allclose(baseline.phase_sigma, [1.1, 4.0])
    np.testing.assert_allclose(wider.phase_sigma, [2.2, 8.0])
    np.testing.assert_allclose(floor.phase_sigma, [3.0, 4.0])
    np.testing.assert_allclose(module.problem(scan, {}, "c0", keep).phase_sigma, [1.1, 4.0])


def test_diagnostic_hessian_has_position_loss_units():
    from report_algo01_ds23_0217 import finite_hessian

    matrix = np.array([[2.0, 0.3], [0.3, 1.0]])
    result = finite_hessian(lambda x: 10 + x @ matrix @ x, np.array([1.0, -2.0]))
    np.testing.assert_allclose(result, 2 * matrix, rtol=1e-8, atol=1e-8)


def test_fixed_precision_ablation_preserves_measurements_and_gaussian_priors(monkeypatch):
    features = np.ones((4, 1)) * 100
    p = module.FixedGaussian.__new__(module.FixedGaussian)
    p.values = np.array([80.0, 100.0, 90.0, 10000.0])
    p.q = np.ones(4)
    p.keep = np.array([True, True, True, False])
    p.point_noise = np.full(4, 40.0)
    p.slices = [slice(0, 4)]
    p.noise_volume = 0.0
    monkeypatch.setattr(
        module.JointMarginal,
        "calculate",
        lambda self, x: dict(features=features, intercept=np.zeros(4)),
    )
    result = p.calculate(np.zeros(2))
    expected = module.integrated_gaussian(p.values[:3], features[:3], 40.0)
    np.testing.assert_allclose(result["coefficient"], expected["coefficient"])
    np.testing.assert_array_equal(result["noise_precision"], [1.0])
    np.testing.assert_array_equal(result["coefficient_prior_precision"], [1.0])
    np.testing.assert_allclose(
        result["conditional_residual_hz"], p.values - features @ expected["coefficient"]
    )
    assert result["gamma_cost"] == 0
