from types import SimpleNamespace

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants import joint_pass_id as solver
from tools.pipeline_eval.variants import rate_triplets


def test_native_epoch_consistency_is_measured_with_carrier_and_keeps_frame_seams():
    time = np.arange(24, dtype=float)
    rf = 11.48e9
    delay = 1290 + 4 * time + 0.15 * time**2
    cfo = -(4 + 0.30 * time) / 1e6 * rf - 8300
    phase = (delay + 0.2 * time) % solver.FRAME_US
    unwrapped = solver.frame_prefix(phase, cfo, rf, time, 16)
    assert unwrapped is not None
    np.testing.assert_allclose(np.diff(unwrapped), np.diff(delay + 0.2 * time), atol=1e-10)
    shuffled = np.random.default_rng(731).permutation(phase)
    assert solver.frame_prefix(shuffled, cfo, rf, time, 16) is None


def test_affine_correction_uses_no_heldout_values():
    t = np.linspace(0, 24, 24)
    values = 25 + 0.24 * t
    values[16:] += 10
    residual, drift = solver.affine(values, t, 16)
    np.testing.assert_allclose(residual[:16], 0, atol=1e-10)
    np.testing.assert_allclose(residual[16:], 10, atol=1e-10)
    assert abs(drift - 0.24) < 1e-10


def test_shared_fractional_transmitter_law_selects_across_rf():
    tracks, table = [], []
    rng = np.random.default_rng(716)
    for i in range(12):
        group, orbit = i // 6, i % 6
        rf = 11.2e9 + i * 40e6
        actual = (1200 if group == 0 else -9200) + (orbit - 3) * 190 * rf / solver.REFERENCE_RF
        tracks.append(SimpleNamespace(group=group, rf_hz=rf))
        table.append(
            [
                solver.Option(orbit, 4 if orbit % 2 else 0, actual, 0.2),
                solver.Option(i + 20, 0, float(rng.uniform(-105_000, 105_000)), 0),
            ]
        )
    _, chosen, _, _, phases = solver.identify(tracks, table)
    assert {k: v.orbit for k, v in chosen.items()} == {i: i % 6 for i in range(12)}
    assert phases == {k: float(4 if k % 2 else 0) for k in range(6)}


def test_frequency_and_frame_fit_predicts_heldout_physical_samples():
    latlon = [23.0, 140.3]
    site = geodetic_to_ecef_km(*latlon, 0)
    design = rate_triplets.ecef_to_enu_matrix(*latlon)
    n = 6
    times = np.arange(-20, 321)
    begin = np.linspace(30, 220, n)
    angle = np.arange(n) * 2.39996
    along = np.cos(angle)[:, None] * design[0] + np.sin(angle)[:, None] * design[1]
    across = np.sin(angle)[:, None] * design[0] - np.cos(angle)[:, None] * design[1]
    closest = 6830 * design[2] + 210 * across
    relative = (times[None, :] - begin[:, None]) * 7.45
    p = closest[:, None, :] + relative[..., None] * along[:, None, :]
    v = np.tile(along[:, None, :] * 7.45, (1, len(times), 1))
    bank = solver.Bank(np.arange(n), p, v)
    track, identity, phases, cfo = [], {}, {}, {}
    c = 2500.0
    for i, t0 in enumerate(begin):
        t = t0 + np.linspace(-18, 18, 24)
        pp, vv = bank.states(i, t, 0)
        rf = 11.15e9 + 120e6 * i
        measured, delay = solver.project(pp, vv, site, rf)
        measured += 1800 + c * (rf / 1e9 - 11.5)
        track.append(solver.Track(0, i + 1, rf, t, measured, delay + 500 + 0.3 * t, 24, 1))
        identity[i], phases[i], cfo[i] = solver.Option(i, 0, 0, 0), 0.0, 0.0
    tile = {"center": rate_triplets.offset_site(latlon, 2, -3), "width_km": 25.0}
    fitted = solver.fit(
        bank,
        track,
        identity,
        tile,
        tile["center"],
        np.array([1800, 0, 0, 0]),
        cfo,
        phases,
        True,
        dict.fromkeys(range(n), 0),
    )
    assert fitted["conditional_rms_hz"] < 12
    assert fitted["heldout_frame_rms_us"] < 0.2
    assert rate_triplets.separation(latlon, fitted["forced_latlon"]) < 0.1
    assert abs(fitted["fitted_c_hz_per_ghz"] - c) < 0.05 * c
