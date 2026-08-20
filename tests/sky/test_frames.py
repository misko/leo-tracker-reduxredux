from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from leo.contracts.sky import SkyWindowV1
from leo.sky.frames import (
    WGS84_FLATTENING,
    WGS84_SEMI_MAJOR_AXIS_KM,
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

# Vallado verification object 00005, published with the sgp4 distribution.
VALLADO_00005 = (
    "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753\n"
    "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667\n"
)
SPINNAKER_LATITUDE_DEG = 37.858988
SPINNAKER_LONGITUDE_DEG = -122.478103


def test_geodetic_to_ecef_matches_closed_form_at_equator_and_pole() -> None:
    equator = geodetic_to_ecef_km(0.0, 0.0, 0.0)
    assert equator == pytest.approx([WGS84_SEMI_MAJOR_AXIS_KM, 0.0, 0.0], abs=1e-9)

    pole = geodetic_to_ecef_km(90.0, 0.0, 0.0)
    semi_minor = WGS84_SEMI_MAJOR_AXIS_KM * (1.0 - WGS84_FLATTENING)
    assert pole == pytest.approx([0.0, 0.0, semi_minor], abs=1e-9)

    quarter = geodetic_to_ecef_km(0.0, 90.0, 0.0)
    assert quarter == pytest.approx([0.0, WGS84_SEMI_MAJOR_AXIS_KM, 0.0], abs=1e-9)


def test_altitude_extends_along_the_geodetic_normal() -> None:
    surface = geodetic_to_ecef_km(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG, 0.0)
    raised = geodetic_to_ecef_km(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG, 1_000.0)
    assert float(np.linalg.norm(raised - surface)) == pytest.approx(1.0, abs=1e-9)

    up = ecef_to_enu_matrix(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG)[2]
    assert (raised - surface) / 1.0 == pytest.approx(up, abs=1e-9)


def test_enu_matrix_is_orthonormal_and_right_handed() -> None:
    matrix = ecef_to_enu_matrix(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG)
    assert matrix @ matrix.T == pytest.approx(np.eye(3), abs=1e-12)
    assert float(np.linalg.det(matrix)) == pytest.approx(1.0, abs=1e-12)


def test_look_angles_recover_zenith_and_the_cardinal_horizon() -> None:
    observer = geodetic_to_ecef_km(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG, 0.0)
    enu = ecef_to_enu_matrix(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG)
    east, north, up = enu[0], enu[1], enu[2]
    still = np.zeros(3)

    azimuth, elevation, slant, rate = look_angles(observer + 550.0 * up, still, observer, enu)
    assert float(elevation) == pytest.approx(90.0, abs=1e-9)
    assert float(slant) == pytest.approx(550.0, abs=1e-9)
    assert float(rate) == pytest.approx(0.0, abs=1e-12)

    for vector, expected_azimuth in ((north, 0.0), (east, 90.0), (-north, 180.0), (-east, 270.0)):
        azimuth, elevation, _, _ = look_angles(observer + 10.0 * vector, still, observer, enu)
        assert float(azimuth) == pytest.approx(expected_azimuth, abs=1e-9)
        assert float(elevation) == pytest.approx(0.0, abs=1e-9)


def test_range_rate_sign_is_positive_when_receding() -> None:
    observer = geodetic_to_ecef_km(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG, 0.0)
    enu = ecef_to_enu_matrix(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG)
    up = enu[2]
    position = observer + 550.0 * up

    _, _, _, receding = look_angles(position, 7.5 * up, observer, enu)
    _, _, _, approaching = look_angles(position, -7.5 * up, observer, enu)
    assert float(receding) == pytest.approx(7.5, abs=1e-9)
    assert float(approaching) == pytest.approx(-7.5, abs=1e-9)


def test_gmst_advances_by_one_sidereal_turn_per_sidereal_day() -> None:
    start_ns = 1_787_238_197_269_841_071
    sidereal_day_ns = 86_164_090_530_833
    day, fraction = julian_day_from_utc_ns(np.array([start_ns, start_ns + sidereal_day_ns]))
    angles = greenwich_mean_sidereal_time_rad(day, fraction)
    difference = float(np.mod(angles[1] - angles[0] + math.pi, 2.0 * math.pi) - math.pi)
    assert difference == pytest.approx(0.0, abs=1e-6)


def test_julian_day_split_keeps_the_fraction_bounded() -> None:
    day, fraction = julian_day_from_utc_ns(np.array([0, 1_787_238_197_269_841_071]))
    assert float(day[0]) == pytest.approx(2440587.5, abs=1e-12)
    assert float(fraction[0]) == pytest.approx(0.0, abs=1e-15)
    assert 0.0 <= float(fraction[1]) < 1.0


_SYNTHETIC_RADIUS_KM = 6_921.0
_SYNTHETIC_RATE_RAD_S = 1.1e-3
_ANCHOR_NS = 1_787_238_197_000_000_000


def _synthetic_state(utc_ns: NDArray[np.int64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """A circular TEME orbit whose velocity is exactly the derivative of its position.

    SGP4 cannot serve this role: its reported velocity is not the exact
    derivative of its reported position, which
    ``test_sgp4_velocity_is_not_the_exact_derivative_of_its_position``
    characterises.  A synthetic state isolates the frame conversion under test.
    """

    seconds = (utc_ns - _ANCHOR_NS).astype(np.float64) / 1e9
    angle = _SYNTHETIC_RATE_RAD_S * seconds
    inclination = np.deg2rad(53.0)
    in_plane = np.stack((np.cos(angle), np.sin(angle), np.zeros_like(angle)), axis=-1)
    in_plane_rate = np.stack((-np.sin(angle), np.cos(angle), np.zeros_like(angle)), axis=-1)
    tilt = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(inclination), -np.sin(inclination)],
            [0.0, np.sin(inclination), np.cos(inclination)],
        ]
    )
    position = _SYNTHETIC_RADIUS_KM * (in_plane @ tilt.T)
    velocity = _SYNTHETIC_RADIUS_KM * _SYNTHETIC_RATE_RAD_S * (in_plane_rate @ tilt.T)
    return position[None, :, :], velocity[None, :, :]


def _synthetic_range_and_rate(half_width_s: int) -> tuple[float, float, float]:
    window = SkyWindowV1(anchor_utc_ns=_ANCHOR_NS, half_width_s=half_width_s, sample_count=3)
    knots = np.asarray(window.knot_utc_ns(), dtype=np.int64)
    position_teme, velocity_teme = _synthetic_state(knots)
    day, fraction = julian_day_from_utc_ns(knots)
    gmst = greenwich_mean_sidereal_time_rad(day, fraction)
    position, velocity = teme_to_ecef(position_teme, velocity_teme, gmst[None, :])
    observer = geodetic_to_ecef_km(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG, 0.0)
    enu = ecef_to_enu_matrix(SPINNAKER_LATITUDE_DEG, SPINNAKER_LONGITUDE_DEG)
    _, _, slant, rate = look_angles(position, velocity, observer, enu)
    return float(slant[0, 0]), float(slant[0, 2]), float(rate[0, 1])


def test_analytic_range_rate_is_the_true_derivative_of_range() -> None:
    """A central difference must converge on the analytic rate at second order.

    Agreeing to a fixed tolerance would only show the two are close.  Halving
    the step and requiring the residual to fall by about four proves the
    analytic expression really is the derivative, and in particular that the
    ``-omega x r`` term and the sidereal rotation rate agree with each other.
    """

    # Steps of 4, 8 and 16 s keep truncation well above the floating-point
    # floor; at 1 s the residual is already down to 4e-7 km/s and rounding
    # noise alone distorts the ratio.
    residuals = []
    analytic_rates = []
    for half_width_s in (4, 8, 16):
        before, after, analytic = _synthetic_range_and_rate(half_width_s)
        residuals.append(abs((after - before) / (2.0 * half_width_s) - analytic))
        analytic_rates.append(analytic)

    assert analytic_rates[0] == pytest.approx(analytic_rates[-1], rel=1e-12)
    for coarse, fine in zip(residuals[1:], residuals[:-1], strict=True):
        assert math.log2(coarse / fine) == pytest.approx(2.0, abs=0.05)


def test_sgp4_velocity_is_not_the_exact_derivative_of_its_position() -> None:
    """Characterise SGP4's internal position/velocity inconsistency.

    This is a property of the theory, not of this repository, but it sets the
    floor on predicted Doppler accuracy and it explains why the convergence
    test above uses a synthetic state.  Pinning the magnitude means a future
    change in the propagator is noticed rather than absorbed.
    """

    catalogue = parse_element_sets(VALLADO_00005)
    satellite = catalogue.satellites[0]
    minutes = 1_000.0
    residuals = []
    for step_s in (1.0, 4.0, 16.0):
        offset = step_s / 60.0
        _, _, velocity = satellite.sgp4_tsince(minutes)
        _, before, _ = satellite.sgp4_tsince(minutes - offset)
        _, after, _ = satellite.sgp4_tsince(minutes + offset)
        difference = (np.asarray(after) - np.asarray(before)) / (2.0 * step_s)
        residuals.append(float(np.linalg.norm(difference - np.asarray(velocity))))

    assert min(residuals) > 1e-4, "an exactly consistent propagator would converge to zero"
    assert max(residuals) < 1e-2
    assert max(residuals) / min(residuals) < 1.5, "the residual is a floor, not truncation"


def test_teme_to_ecef_preserves_radius_and_rotates_about_the_pole() -> None:
    position = np.array([[7000.0, 0.0, 1234.0]])
    velocity = np.array([[0.0, 7.5, 0.0]])
    gmst = np.array([0.75])
    rotated, _ = teme_to_ecef(position, velocity, gmst)
    assert float(np.linalg.norm(rotated)) == pytest.approx(
        float(np.linalg.norm(position)), abs=1e-9
    )
    assert float(rotated[0, 2]) == pytest.approx(1234.0, abs=1e-12)
