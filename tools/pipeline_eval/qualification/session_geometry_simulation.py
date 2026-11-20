"""Circular inertial LEO passes over a separate WGS84 site."""

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km, teme_to_ecef

from ..variants import session_geometry as model

ORIGIN = (-34.9011, -56.1645)
TRUTH_OFFSET_KM = (1.8, -2.8)
TRUTH_HEIGHT_M = 250.0
GM_KM3_S2 = 398600.4418
EARTH_RAD_S = 7.292115e-5
SEED = 127671


def circular_states(origin, bearing_deg, cross_track_km, altitude_km, elapsed_s):
    latitude, longitude = np.deg2rad(origin)
    up = np.array(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    east = np.array([-np.sin(longitude), np.cos(longitude), 0])
    north = np.cross(up, east)
    bearing = np.deg2rad(bearing_deg)
    along = north * np.cos(bearing) + east * np.sin(bearing)
    across = np.cross(along, up)
    cross = cross_track_km / 6371.0
    closest = np.cos(cross) * up + np.sin(cross) * across
    radius = 6371 + altitude_km
    omega = np.sqrt(GM_KM3_S2 / radius**3)
    orbit_angle = elapsed_s[:, None] * omega
    position = radius * (np.cos(orbit_angle) * closest + np.sin(orbit_angle) * along)
    velocity = radius * omega * (-np.sin(orbit_angle) * closest + np.cos(orbit_angle) * along)
    return teme_to_ecef(position, velocity, EARTH_RAD_S * elapsed_s)


def truth():
    return [*model.geographic(ORIGIN, TRUTH_OFFSET_KM).tolist(), TRUTH_HEIGHT_M]


def generate():
    rng = np.random.default_rng(SEED)
    site = geodetic_to_ecef_km(*truth())
    captures = []
    for ordinal in range(10):
        visit = "visit-1" if ordinal < 5 else "visit-2"
        arcs = []
        for pass_index in range(2):
            phase = rng.choice([-1.0, -0.75, -0.50, 0.50, 0.75, 1.0])
            center_s = rng.uniform(-35, 35)
            times_s = np.linspace(0, 100 + 5 * pass_index, 161)
            elapsed = times_s - times_s.mean() + center_s
            bearing = (ordinal * 137.508 + pass_index * 85) % 360
            cross = rng.uniform(-370, 370)
            altitude = rng.uniform(500, 575)
            pos, vel = circular_states(ORIGIN, bearing, cross, altitude, elapsed)
            exact_pos, exact_vel = circular_states(
                ORIGIN, bearing, cross, altitude, elapsed + phase
            )
            line = exact_pos - site
            radial = np.sum(line * exact_vel, axis=-1) / np.linalg.norm(line, axis=-1)
            ideal = (-model.RF_HZ / model.LIGHT_KM_S) * radial
            offset_hz = rng.uniform(-25000, 25000)
            rate_hz_s = rng.uniform(-12, 12)
            noisy = ideal + offset_hz + rate_hz_s * elapsed + rng.normal(0, 40.0, len(elapsed))
            observed = np.round(noisy / model.BIN_HZ) * model.BIN_HZ
            arcs.append(model.Arc(times_s, observed, pos, vel))
        captures.append(model.Capture(f"sim-{ordinal + 1:02d}", visit, tuple(arcs)))
    return captures
