from types import SimpleNamespace

import numpy as np
import pytest

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.variants import folded_doppler as folded

RATE = 10_000_000
SECONDS = 120
LIGHT_KM_S = 299792.458
CENTER = tuple(folded.earth_mesh()[193])
LOCATION = folded._offset(CENTER, 3, -4)


def fixture(random_peaks=False, alter_held=False):
    rng = np.random.default_rng(592)
    origin = geodetic_to_ecef_km(*LOCATION, 0)
    axes = ecef_to_enu_matrix(*LOCATION)
    orbits, probes = [], []
    for index, degrees in enumerate((15, 90, 170, 235)):
        a = np.deg2rad(degrees)
        along = np.sin(a) * axes[0] + np.cos(a) * axes[1]
        across = np.cos(a) * axes[0] - np.sin(a) * axes[1]
        motion = 7.1 * along
        at_zero = origin + axes[2] * (510 + 33 * index) + across * (70 - 20 * index)
        closest = 23 + 19 * index
        ts = np.arange(0, SECONDS + 3, folded.KNOT_STEP_S)
        xyz = at_zero + (ts - closest)[:, None] * motion
        orbits.append(np.column_stack((xyz, np.broadcast_to(motion, xyz.shape))))
        rf = 11.2e9 + 250e6 * index
        carrier = (100e3, -80e3, 33e3, -60e3)[index]
        for second in range(SECONDS):
            time = second + 0.01
            dx = (at_zero - origin) + (time - closest) * motion
            doppler = -float(dx @ motion) / np.linalg.norm(dx) * rf / LIGHT_KM_S
            cfo = folded._wrap(doppler + carrier + rng.normal(0, 25))
            clutter = rng.uniform(-120e3, 120e3)
            null = rng.uniform(-120e3, 120e3)
            if random_peaks or (alter_held and int(time / folded.BIN_S) % 3 == 2):
                cfo = null
            probes.append(
                dict(
                    valid_start_counter=second * RATE,
                    probe_start_ms=0,
                    receiver_id=0,
                    actual_rf_hz=rf,
                    channel=index + 1,
                    candidates=[
                        dict(
                            fractional_margin=0.35,
                            passed_fractional_margin_gate=True,
                            fractional_tracking_cfo_hz=cfo,
                        ),
                        dict(
                            fractional_margin=0.1,
                            passed_fractional_margin_gate=True,
                            fractional_tracking_cfo_hz=clutter,
                        ),
                    ],
                )
            )
    capture = SimpleNamespace(
        probes=probes, sample_rate_hz=RATE, probe_ms=20, first_counter=0, duration_s=SECONDS
    )
    return capture, folded.orbit_bank(np.array(orbits), np.arange(100, 104))


@pytest.mark.parametrize("tile", (CENTER, None))
def test_optimistic_planted_signal(tile, monkeypatch):
    capture, orbit = fixture()
    monkeypatch.setattr(folded, "orbital_states", lambda _: (orbit, {}))
    result = folded.solve(capture, tile=tile)
    assert result["status"] == "ok", result
    assert result["metrics"]["confirmed_independent_profiles"] >= 3
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    xyz = geodetic_to_ecef_km(*result["arms"]["c0"]["latlon"], 0)
    assert np.linalg.norm(xyz - geodetic_to_ecef_km(*LOCATION, 0)) < 2.0


def test_null_withholds_and_held_peaks_cannot_move_training_offset(monkeypatch):
    null, orbit = fixture(random_peaks=True)
    monkeypatch.setattr(folded, "orbital_states", lambda _: (orbit, {}))
    assert folded.solve(null, tile=CENTER)["status"] == "withheld"

    original, _ = fixture()
    permuted, _ = fixture(alter_held=True)
    original, _ = folded.observations(original)
    permuted, _ = folded.observations(permuted)
    left = folded.Accumulator(original, orbit)(LOCATION, 1024)
    right = folded.Accumulator(permuted, orbit)(LOCATION, 1024)
    assert [(p["norad"], p["offset_hz"], p["train_bins"]) for p in left.profiles] == [
        (p["norad"], p["offset_hz"], p["train_bins"]) for p in right.profiles
    ]
    assert right.validation < left.validation


def test_constant_rf_calibration_is_an_exact_offset_reparameterization():
    rng = np.random.default_rng(81)
    offsets = rng.uniform(-500e3, 500e3, 16)
    rf = rng.uniform(10.7e9, 12.7e9, 16)
    fitted = 187_000 * (rf / 1e9 - 11.5)
    profiled = folded._wrap(offsets - fitted)
    np.testing.assert_allclose(folded._wrap(profiled + fitted), folded._wrap(offsets), atol=1e-9)
