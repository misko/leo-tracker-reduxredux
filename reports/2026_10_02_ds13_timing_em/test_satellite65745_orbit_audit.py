import numpy as np
import pytest
import satellite65745_orbit_audit as audit


def test_weighted_trend_recovers_known_slope_and_constant():
    time = np.linspace(-25, 25, 50)
    result = audit.weighted_fit(np.column_stack([np.ones(50), time]),
                                13 + 4 * time, np.linspace(.8, 1, 50))
    np.testing.assert_allclose(result["coefficients"], [13, 4], atol=1e-10)
    assert result["weighted_rms_hz"] < 1e-10


def test_degenerate_timing_shape_reports_rank_loss():
    result = audit.weighted_fit(np.column_stack([np.ones(10), np.full(10, 3)]),
                                np.arange(10), np.ones(10))
    assert result["rank"] == 1
    with pytest.raises(ValueError):
        audit.weighted_fit(np.ones((10, 1)), np.ones(10), np.zeros(10))


def test_timing_derivative_and_curvature_units(monkeypatch):
    def quadratic(_data, _parameters, _satellite, times):
        times = np.asarray(times)
        return (2 * times**2 + 3 * times + 5)[:, None], np.ones((len(times), 1), bool)

    monkeypatch.setattr(audit, "orbital_curve", quadratic)
    times = np.array([240., 260., 290.])
    _, derivative, curvature = audit.physical_derivatives(None, None, 0, times)
    np.testing.assert_allclose(derivative, 4 * times + 3, atol=1e-6)
    np.testing.assert_allclose(curvature, 4, atol=1e-6)
