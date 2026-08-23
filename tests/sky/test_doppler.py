from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from leo.contracts.sky import DopplerPolynomialV1
from leo.sky.doppler import (
    SPEED_OF_LIGHT_KM_S,
    average_doppler_rate_hz_s,
    doppler_shift_hz,
    evaluate_doppler_polynomial,
    fit_doppler_polynomial,
)

KU_BAND_HZ = 11.7e9
ANCHOR_NS = 1_787_238_197_000_000_000


def test_approaching_objects_shift_upwards_and_receding_downwards() -> None:
    approaching = float(doppler_shift_hz(KU_BAND_HZ, -7.5))
    receding = float(doppler_shift_hz(KU_BAND_HZ, +7.5))
    assert approaching > 0.0
    assert receding < 0.0
    assert approaching == pytest.approx(-receding, rel=1e-12)


def test_shift_magnitude_matches_the_closed_form() -> None:
    rate = -3.2
    expected = -KU_BAND_HZ * rate / SPEED_OF_LIGHT_KM_S
    assert float(doppler_shift_hz(KU_BAND_HZ, rate)) == pytest.approx(expected, rel=1e-12)
    # A 7.5 km/s radial rate at Ku band is a few hundred kHz, the scale that
    # makes Doppler search necessary in the first place.
    assert 250e3 < abs(float(doppler_shift_hz(KU_BAND_HZ, 7.5))) < 350e3


def test_a_stationary_object_has_no_shift() -> None:
    assert float(doppler_shift_hz(KU_BAND_HZ, 0.0)) == 0.0


def test_shift_is_vectorized_over_a_track() -> None:
    rates = np.array([-5.0, 0.0, 5.0])
    shifts = doppler_shift_hz(KU_BAND_HZ, rates)
    assert shifts.shape == (3,)
    assert shifts[0] > shifts[1] > shifts[2]


def test_average_rate_is_the_full_window_doppler_chord() -> None:
    offsets = np.array([-60.0, -30.0, 0.0, 30.0, 60.0])
    range_rates = np.array([-5.0, -3.0, 0.0, 2.0, 4.0])
    shifts = doppler_shift_hz(KU_BAND_HZ, range_rates)

    average = average_doppler_rate_hz_s(KU_BAND_HZ, range_rates, offsets)

    assert average == pytest.approx(float((shifts[-1] - shifts[0]) / 120.0))


def test_average_rate_scales_with_the_channel_center_frequency() -> None:
    offsets = np.array([-60.0, 0.0, 60.0])
    range_rates = np.array([-5.0, 0.0, 4.0])
    ch1 = average_doppler_rate_hz_s(10_825_000_000, range_rates, offsets)
    ch8 = average_doppler_rate_hz_s(12_575_000_000, range_rates, offsets)

    assert ch8 / ch1 == pytest.approx(12_575 / 10_825)


@pytest.mark.parametrize("frequency", (0.0, -1.0, float("nan"), float("inf")))
def test_invalid_downlink_frequency_is_rejected(frequency: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        doppler_shift_hz(frequency, 1.0)


def test_fit_recovers_a_known_cubic_exactly() -> None:
    offsets = np.linspace(-60.0, 60.0, 5)
    truth = {"constant": -1234.5, "slope": 87.25, "acceleration": -0.75, "jerk": 0.004}
    shift = (
        truth["constant"]
        + truth["slope"] * offsets
        + truth["acceleration"] * offsets**2 / 2.0
        + truth["jerk"] * offsets**3 / 6.0
    )

    polynomial = fit_doppler_polynomial(
        offsets, shift, downlink_frequency_hz=KU_BAND_HZ, reference_utc_ns=ANCHOR_NS
    )

    assert polynomial.degree == 3
    assert polynomial.frequency_at_reference_hz == pytest.approx(truth["constant"], rel=1e-9)
    assert polynomial.slope_hz_s == pytest.approx(truth["slope"], rel=1e-9)
    assert polynomial.acceleration_hz_s2 == pytest.approx(truth["acceleration"], rel=1e-7)
    assert polynomial.jerk_hz_s3 == pytest.approx(truth["jerk"], rel=1e-6)
    assert polynomial.residual_rms_hz == pytest.approx(0.0, abs=1e-6)


def test_the_constant_term_is_the_shift_at_the_reference_instant() -> None:
    offsets = np.linspace(-60.0, 60.0, 5)
    shift = 500.0 + 3.0 * offsets - 0.01 * offsets**2

    polynomial = fit_doppler_polynomial(
        offsets, shift, downlink_frequency_hz=KU_BAND_HZ, reference_utc_ns=ANCHOR_NS
    )

    assert polynomial.frequency_at_reference_hz == pytest.approx(float(shift[2]), rel=1e-9)
    assert polynomial.reference_utc_ns == ANCHOR_NS


def test_evaluation_round_trips_the_fitted_samples() -> None:
    offsets = np.linspace(-60.0, 60.0, 5)
    shift = -900.0 + 12.0 * offsets + 0.05 * offsets**2 - 0.0007 * offsets**3

    polynomial = fit_doppler_polynomial(
        offsets, shift, downlink_frequency_hz=KU_BAND_HZ, reference_utc_ns=ANCHOR_NS
    )

    assert evaluate_doppler_polynomial(polynomial, offsets) == pytest.approx(shift, rel=1e-6)


def test_requested_degree_is_reduced_when_knots_are_scarce() -> None:
    offsets = np.array([-30.0, 0.0, 30.0])
    shift = 10.0 + 2.0 * offsets + 0.5 * offsets**2 / 2.0

    polynomial = fit_doppler_polynomial(
        offsets, shift, downlink_frequency_hz=KU_BAND_HZ, reference_utc_ns=ANCHOR_NS
    )

    assert polynomial.degree == 2
    assert polynomial.jerk_hz_s3 == 0.0
    assert polynomial.acceleration_hz_s2 == pytest.approx(0.5, rel=1e-9)


def test_residual_reports_a_genuine_misfit() -> None:
    offsets = np.linspace(-60.0, 60.0, 5)
    shift = np.array([0.0, 500.0, -500.0, 500.0, 0.0])

    polynomial = fit_doppler_polynomial(
        offsets, shift, downlink_frequency_hz=KU_BAND_HZ, reference_utc_ns=ANCHOR_NS, degree=1
    )

    assert polynomial.degree == 1
    assert polynomial.residual_rms_hz > 100.0


def test_fit_rejects_malformed_input() -> None:
    offsets = np.linspace(-60.0, 60.0, 5)
    with pytest.raises(ValueError, match="degree must be"):
        fit_doppler_polynomial(
            offsets,
            offsets,
            downlink_frequency_hz=KU_BAND_HZ,
            reference_utc_ns=ANCHOR_NS,
            degree=4,
        )
    with pytest.raises(ValueError, match="equal length"):
        fit_doppler_polynomial(
            offsets,
            offsets[:3],
            downlink_frequency_hz=KU_BAND_HZ,
            reference_utc_ns=ANCHOR_NS,
        )
    with pytest.raises(ValueError, match="finite"):
        fit_doppler_polynomial(
            offsets,
            np.array([0.0, 1.0, float("nan"), 3.0, 4.0]),
            downlink_frequency_hz=KU_BAND_HZ,
            reference_utc_ns=ANCHOR_NS,
        )
    with pytest.raises(ValueError, match="at least two samples"):
        fit_doppler_polynomial(
            np.array([0.0]),
            np.array([1.0]),
            downlink_frequency_hz=KU_BAND_HZ,
            reference_utc_ns=ANCHOR_NS,
        )


def test_contract_rejects_coefficients_above_the_declared_degree() -> None:
    with pytest.raises(ValidationError, match="jerk requires"):
        DopplerPolynomialV1(
            degree=2,
            reference_utc_ns=ANCHOR_NS,
            downlink_frequency_hz=KU_BAND_HZ,
            frequency_at_reference_hz=0.0,
            slope_hz_s=0.0,
            acceleration_hz_s2=1.0,
            jerk_hz_s3=1.0,
            residual_rms_hz=0.0,
        )
    with pytest.raises(ValidationError, match="acceleration requires"):
        DopplerPolynomialV1(
            degree=1,
            reference_utc_ns=ANCHOR_NS,
            downlink_frequency_hz=KU_BAND_HZ,
            frequency_at_reference_hz=0.0,
            slope_hz_s=0.0,
            acceleration_hz_s2=1.0,
            residual_rms_hz=0.0,
        )
