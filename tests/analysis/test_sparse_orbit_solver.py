import numpy as np

from leo.analysis.research.sparse_orbit_solver import (
    SparseOrbitConfig,
    SparseOrbitData,
    fit_sparse_orbit,
)
from tests.analysis.test_formal_orbit import _synthetic


def _sparse_data(data):
    return SparseOrbitData(**data.__dict__)


def test_stabilized_solver_recovers_position_and_reports_nuisance_trace():
    data, region, truth = _synthetic()
    result = fit_sparse_orbit(
        _sparse_data(data),
        region,
        [0, 0],
        SparseOrbitConfig(measurement_sigma_hz=16, ar1_rho=0.8, robust_df=4),
    )
    assert result.converged
    assert np.linalg.norm(np.asarray(result.x_km) - truth) < 2.0
    assert 0 < result.nuisance_iterations <= 120
    assert result.nuisance_backtracks >= 0
    assert result.nuisance_scaled_step < 1e-5


def test_heldout_values_do_not_affect_sparse_fit():
    data, region, _ = _synthetic()
    original = _sparse_data(data)
    poisoned = SparseOrbitData(
        **{
            **data.__dict__,
            "y_hz": np.where(data.training, data.y_hz, data.y_hz + 1e7),
        }
    )
    config = SparseOrbitConfig(measurement_sigma_hz=16, ar1_rho=0.8)
    a = fit_sparse_orbit(original, region, [0, 0], config)
    b = fit_sparse_orbit(poisoned, region, [0, 0], config)
    assert np.allclose(a.x_km, b.x_km, atol=1e-7)
    assert np.isclose(a.negative_log_posterior, b.negative_log_posterior)
    assert a.evaluation_rms_hz != b.evaluation_rms_hz


def test_normalized_stop_handles_different_parameter_units():
    data, region, _ = _synthetic()
    result = fit_sparse_orbit(
        _sparse_data(data),
        region,
        [0, 0],
        SparseOrbitConfig(
            measurement_sigma_hz=16,
            ar1_rho=0.8,
            nuisance_tolerance=3e-5,
        ),
    )
    assert result.nuisance_converged
    assert result.nuisance_scaled_step < 3e-5
