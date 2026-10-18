"""Reference-frame conversions between TEME, ECEF and the observer horizon.

Pure numerical code: no catalog, storage, HTTP or CLI import.  Every function is
vectorized over satellites and over window knots so that a whole constellation
can be converted in one call.

Stated approximations, both far below the angular scale of any real antenna
beam:

* UT1 is approximated by UTC.  |UT1-UTC| < 0.9 s, which rotates the Earth by at
  most 0.00375 deg and displaces a 6,900 km orbit radius by under 500 m.
* Polar motion is neglected in the TEME-to-ECEF rotation, worth a few metres.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# WGS84 defining parameters.
WGS84_SEMI_MAJOR_AXIS_KM = 6378.137
WGS84_FLATTENING = 1.0 / 298.257223563
WGS84_ECCENTRICITY_SQUARED = WGS84_FLATTENING * (2.0 - WGS84_FLATTENING)

# IERS mean Earth rotation rate, radians per second.
EARTH_ROTATION_RATE_RAD_S = 7.292115146706979e-5

_UNIX_EPOCH_JULIAN_DAY = 2440587.5
_NS_PER_DAY = 86_400_000_000_000
_SECONDS_PER_DAY = 86_400.0
_J2000_JULIAN_DAY = 2451545.0
_JULIAN_CENTURY_DAYS = 36525.0


def julian_day_from_utc_ns(
    utc_ns: NDArray[np.int64] | int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Split UTC nanoseconds into a Julian day number and a day fraction.

    The pair is kept separate because ``sgp4`` accumulates far less rounding
    error when the large and small parts are supplied independently.
    """

    values = np.atleast_1d(np.asarray(utc_ns, dtype=np.int64))
    whole_days, remainder_ns = np.divmod(values, _NS_PER_DAY)
    julian_day = _UNIX_EPOCH_JULIAN_DAY + whole_days.astype(np.float64)
    fraction = remainder_ns.astype(np.float64) / float(_NS_PER_DAY)
    return julian_day, fraction


def greenwich_mean_sidereal_time_rad(
    julian_day: NDArray[np.float64], fraction: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Greenwich mean sidereal angle for each instant, in radians.

    Uses the IAU 1982 polynomial, the same series ``sgp4`` itself applies for
    its TEME reductions, so the two remain mutually consistent.
    """

    centuries = (julian_day - _J2000_JULIAN_DAY + fraction) / _JULIAN_CENTURY_DAYS
    seconds = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * centuries
        + 0.093104 * centuries**2
        - 6.2e-6 * centuries**3
    )
    return np.deg2rad(np.mod(seconds / 240.0, 360.0))


def geodetic_to_ecef_km(
    latitude_deg: float, longitude_deg: float, altitude_m: float
) -> NDArray[np.float64]:
    """Convert one WGS84 geodetic position to ECEF kilometres."""

    latitude = np.deg2rad(latitude_deg)
    longitude = np.deg2rad(longitude_deg)
    altitude_km = altitude_m / 1000.0
    sin_latitude = np.sin(latitude)
    prime_vertical = WGS84_SEMI_MAJOR_AXIS_KM / np.sqrt(
        1.0 - WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    return np.array(
        [
            (prime_vertical + altitude_km) * np.cos(latitude) * np.cos(longitude),
            (prime_vertical + altitude_km) * np.cos(latitude) * np.sin(longitude),
            (prime_vertical * (1.0 - WGS84_ECCENTRICITY_SQUARED) + altitude_km) * sin_latitude,
        ],
        dtype=np.float64,
    )


def teme_to_ecef(
    position_teme_km: NDArray[np.float64],
    velocity_teme_km_s: NDArray[np.float64],
    gmst_rad: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Rotate TEME position and velocity into the co-rotating ECEF frame.

    ``position_teme_km`` and ``velocity_teme_km_s`` are shaped ``(..., 3)`` and
    ``gmst_rad`` broadcasts against their leading axes.  The velocity gains the
    ``-omega x r`` term so that range rate is measured relative to a ground
    observer rather than to inertial space.
    """

    angle = np.asarray(gmst_rad, dtype=np.float64)
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)
    x_teme = position_teme_km[..., 0]
    y_teme = position_teme_km[..., 1]
    z_teme = position_teme_km[..., 2]
    position_ecef = np.stack(
        (
            cos_angle * x_teme + sin_angle * y_teme,
            -sin_angle * x_teme + cos_angle * y_teme,
            z_teme,
        ),
        axis=-1,
    )
    vx_teme = velocity_teme_km_s[..., 0]
    vy_teme = velocity_teme_km_s[..., 1]
    vz_teme = velocity_teme_km_s[..., 2]
    rotated_velocity = np.stack(
        (
            cos_angle * vx_teme + sin_angle * vy_teme,
            -sin_angle * vx_teme + cos_angle * vy_teme,
            vz_teme,
        ),
        axis=-1,
    )
    velocity_ecef = rotated_velocity + EARTH_ROTATION_RATE_RAD_S * np.stack(
        (
            position_ecef[..., 1],
            -position_ecef[..., 0],
            np.zeros_like(position_ecef[..., 2]),
        ),
        axis=-1,
    )
    return position_ecef, velocity_ecef


def ecef_to_enu_matrix(latitude_deg: float, longitude_deg: float) -> NDArray[np.float64]:
    """Rotation from ECEF into the observer's east/north/up frame."""

    latitude = np.deg2rad(latitude_deg)
    longitude = np.deg2rad(longitude_deg)
    sin_lat, cos_lat = np.sin(latitude), np.cos(latitude)
    sin_lon, cos_lon = np.sin(longitude), np.cos(longitude)
    return np.array(
        [
            [-sin_lon, cos_lon, 0.0],
            [-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat],
            [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
        ],
        dtype=np.float64,
    )


def look_angles(
    position_ecef_km: NDArray[np.float64],
    velocity_ecef_km_s: NDArray[np.float64],
    observer_ecef_km: NDArray[np.float64],
    enu_matrix: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return azimuth (deg), elevation (deg), range (km) and range rate (km/s).

    Azimuth is measured clockwise from true north.  Range rate is positive when
    the object is receding, matching the sign convention of the Doppler shift
    formula ``f_rx = f_tx * (1 - range_rate / c)``.
    """

    relative = position_ecef_km - observer_ecef_km
    east_north_up = relative @ enu_matrix.T
    slant_range = np.linalg.norm(relative, axis=-1)
    east = east_north_up[..., 0]
    north = east_north_up[..., 1]
    up = east_north_up[..., 2]
    azimuth = np.mod(np.rad2deg(np.arctan2(east, north)), 360.0)
    # arctan2 against the horizontal leg rather than arcsin of up/range: arcsin
    # has unbounded derivative at +-90 deg, so a satellite near zenith loses
    # roughly half the available precision.  arctan2 is well conditioned across
    # the whole range and returns exactly 90 deg for a zenith pass.
    elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))
    with np.errstate(invalid="ignore", divide="ignore"):
        range_rate = np.where(
            slant_range > 0.0,
            np.einsum("...i,...i->...", relative, velocity_ecef_km_s) / slant_range,
            0.0,
        )
    return azimuth, elevation, slant_range, range_rate
