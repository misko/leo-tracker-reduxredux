"""One-way reception-time Doppler, including Earth rotation during light time.

Relativistic control follows the frequency-ratio terms through c^-2 in Deng
and Xie (2013), https://arxiv.org/html/1312.0725, equations 2-3. The optional
potential is Earth monopole only; atmospheric and Shapiro terms are omitted.
"""

import numpy as np

from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import geodetic_to_ecef_km

C_KM_S = 299792.458
EARTH_GM_KM3_S2 = 398600.4418


def rotate_z(values, angle):
    result = np.array(values, dtype=float, copy=True)
    c, s = np.cos(angle), np.sin(angle)
    x, y = result[..., 0].copy(), result[..., 1].copy()
    result[..., 0], result[..., 1] = c * x - s * y, s * x + c * y
    return result


def rotational_velocity(position, omega):
    result = np.zeros_like(position)
    result[..., 0], result[..., 1] = -omega * position[..., 1], omega * position[..., 0]
    return result


def reception_frequency(
    states,
    times,
    receiver_km,
    *,
    relativistic=False,
    omega=EARTH_ROTATION_RAD_S,
    carrier_hz=11.5e9,
    earth_potential=True,
):
    """Evaluate emission states iteratively, expressed in reception-frame axes.

    states(t) returns ECEF position and velocity at emission time, with the
    caller's orbital phase already applied. Independent of CFO or site truth.
    """
    t, rx = np.asarray(times, float), np.asarray(receiver_km, float)
    if t.ndim != 1 or rx.shape != (3,) or not np.isfinite(t).all() or not np.isfinite(rx).all():
        raise ValueError("finite receive times and one receiver position required")
    delay = np.zeros(len(t))
    for _ in range(5):
        p, v = states(t - delay)
        position = rotate_z(p, -omega * delay)
        updated = np.linalg.norm(position - rx, axis=1) / C_KM_S
        change = np.max(abs(updated - delay))
        delay = updated
        if change < 1e-12:
            break
    p, v = states(t - delay)
    position = rotate_z(p, -omega * delay)
    tx_velocity = rotate_z(v + rotational_velocity(p, omega), -omega * delay)
    rx_velocity = rotational_velocity(rx, omega)
    line = position - rx
    direction = line / np.linalg.norm(line, axis=1)[:, None]
    bt = np.sum(direction * tx_velocity, axis=1) / C_KM_S
    br = direction @ rx_velocity / C_KM_S
    fraction = (br - bt) / (1 + bt)
    if relativistic:
        log_ratio = np.log1p(fraction) + 0.5 * (
            np.log1p(-np.sum(tx_velocity**2, axis=1) / C_KM_S**2)
            - np.log1p(-(rx_velocity @ rx_velocity) / C_KM_S**2)
        )
        if earth_potential:
            log_ratio += (
                EARTH_GM_KM3_S2
                * (1 / np.linalg.norm(rx) - 1 / np.linalg.norm(position, axis=1))
                / C_KM_S**2
            )
        fraction = np.expm1(log_ratio)
    return carrier_hz * fraction, delay


def paired_reception_frequency(
    bank, times, labels, phases, latitude, longitude, *, relativistic=False
):
    def states(emission_times):
        return paired_phase_states(bank, emission_times, labels, phases)

    return reception_frequency(
        states, times, geodetic_to_ecef_km(latitude, longitude, 0), relativistic=relativistic
    )
