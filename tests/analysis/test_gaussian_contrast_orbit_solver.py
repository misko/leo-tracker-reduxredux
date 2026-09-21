import numpy as np

from leo.analysis.research.gaussian_contrast_orbit_solver import (
    GaussianContrastOrbitConfig,
    GaussianContrastOrbitData,
    fit_gaussian_contrast_orbit,
)
from tests.analysis.test_formal_orbit import _synthetic


def _data(data):
    return GaussianContrastOrbitData(**data.__dict__)


def test_gaussian_contrast_recovers_position_and_isolates_heldout_values():
    source, region, truth = _synthetic()
    config = GaussianContrastOrbitConfig(measurement_sigma_hz=16, ar1_rho=0.8)
    a = fit_gaussian_contrast_orbit(_data(source), region, [0, 0], config)
    poisoned = GaussianContrastOrbitData(
        **{
            **source.__dict__,
            "y_hz": np.where(source.training, source.y_hz, source.y_hz + 1e7),
        }
    )
    b = fit_gaussian_contrast_orbit(poisoned, region, [0, 0], config)
    assert a.converged
    assert np.linalg.norm(np.asarray(a.x_km) - truth) < 2.0
    assert np.allclose(a.x_km, b.x_km, atol=1e-7)
    assert np.isclose(a.negative_log_posterior, b.negative_log_posterior)
    assert a.evaluation_rms_hz != b.evaluation_rms_hz


def test_singleton_segment_supplies_no_contrast_or_scale_information():
    source, region, _ = _synthetic()
    base = _data(source)
    values = {}
    for name, value in source.__dict__.items():
        if name == "observation_id":
            values[name] = None
        elif name == "y_hz":
            values[name] = np.r_[value, 1e9]
        elif name == "training":
            values[name] = np.r_[value, True]
        elif name in {"segment", "track"}:
            values[name] = np.r_[value, np.max(value) + 1]
        elif np.asarray(value).ndim == 2:
            values[name] = np.concatenate((value, value[:1]))
        else:
            values[name] = np.r_[value, value[0]]
    augmented = GaussianContrastOrbitData(**values)
    config = GaussianContrastOrbitConfig(
        measurement_sigma_hz=16, ar1_rho=0.8, infer_measurement_sigma=True
    )
    a = fit_gaussian_contrast_orbit(base, region, [0, 0], config)
    b = fit_gaussian_contrast_orbit(augmented, region, [0, 0], config)
    assert np.allclose(a.x_km, b.x_km, atol=1e-6)
    assert np.isclose(a.measurement_sigma_hz, b.measurement_sigma_hz, rtol=2e-6)
    assert np.isclose(a.negative_log_posterior, b.negative_log_posterior, atol=2e-5)
