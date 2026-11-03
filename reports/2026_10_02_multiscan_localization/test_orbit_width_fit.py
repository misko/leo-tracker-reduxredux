import numpy as np
import pytest

from orbit_width_fit import (
    OrbitWidthLikelihood,
    diagnostic_orbit_widths,
    effective_orbit_sigmas,
)


class RecordingPrepared:
    def __init__(self):
        self.sigma_hz = None

    def evaluate(self, predicted, visible, **options):
        self.sigma_hz = np.asarray(options["sigma_hz"]).copy()
        result = {"total_log_likelihood": -1.0}
        if options["return_gradient"]:
            result["prediction_gradient"] = np.zeros_like(predicted)
        if options["return_precision"]:
            result["prediction_precision"] = np.ones_like(predicted)
        return result


def diagnostic(width=350.0):
    return {
        "schema": "tle-time-alignment-diagnostic/v1",
        "constraints": {
            "reference_coordinates_read": False,
            "future_tle_used": False,
        },
        "satellites": [
            {
                "catalog_number": 64136,
                "aligned_doppler_hz": {
                    "raw_zero_frequency_adjustment": {"trimmed_95_rms": width},
                    "constant_fit": {"residual": {"trimmed_95_rms": 12.0}},
                    "linear_fit": {"residual": {"trimmed_95_rms": 3.0}},
                },
            }
        ],
    }


def test_effective_width_uses_quadrature_and_is_immutable():
    source = np.array([0.0, 300.0])
    result = effective_orbit_sigmas(source)
    np.testing.assert_allclose(result, [200.0, np.sqrt(200.0**2 + 300.0**2)])
    source[1] = 0.0
    assert result[1] > 200.0
    with pytest.raises(ValueError):
        result[0] = 1.0


def test_diagnostic_width_retains_constant_bias():
    assert diagnostic_orbit_widths(diagnostic())[64136] == 350.0


@pytest.mark.parametrize(
    "document",
    [
        {**diagnostic(), "constraints": {"reference_coordinates_read": True}},
        {**diagnostic(), "constraints": {"reference_coordinates_read": False, "future_tle_used": True}},
    ],
)
def test_diagnostic_width_rejects_reference_or_future_tle(document):
    with pytest.raises(ValueError):
        diagnostic_orbit_widths(document)


def test_adapter_feeds_frozen_column_widths_and_derivative_flags():
    prepared = RecordingPrepared()
    supplied = np.array([250.0, 700.0])
    adapter = OrbitWidthLikelihood(prepared, {"raw_satellite_mass": [0.4, 0.4]}, supplied)
    supplied[:] = 1.0
    result = adapter.evaluate(
        np.zeros((3, 2)),
        np.ones((3, 2), dtype=bool),
        sigma_hz=200.0,
        satellite_weights=[0.5, 0.5],
        background_mass=0.2,
        return_gradient=True,
        return_precision=True,
    )
    np.testing.assert_array_equal(prepared.sigma_hz, [250.0, 700.0])
    assert result["prediction_gradient"].shape == (3, 2)
    assert result["prediction_precision"].shape == (3, 2)
    with pytest.raises(ValueError):
        adapter.sigma_hz[0] = 1.0


def test_adapter_rejects_column_or_base_width_mismatch():
    adapter = OrbitWidthLikelihood(RecordingPrepared(), {}, [250.0, 700.0])
    with pytest.raises(ValueError, match="columns"):
        adapter.evaluate(
            np.zeros((3, 1)),
            np.ones((3, 1), dtype=bool),
            sigma_hz=200.0,
            satellite_weights=[1.0],
            background_mass=0.2,
        )
    with pytest.raises(ValueError, match="base width"):
        adapter.evaluate(
            np.zeros((3, 2)),
            np.ones((3, 2), dtype=bool),
            sigma_hz=201.0,
            satellite_weights=[0.5, 0.5],
            background_mass=0.2,
        )
