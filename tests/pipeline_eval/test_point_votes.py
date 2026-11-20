from types import SimpleNamespace

import numpy as np
from scipy.spatial import cKDTree

from tools.pipeline_eval.variants import point_votes as votes


def test_frame_phase_wrap_and_differential_carrier_are_pair_features():
    rate = 10_000_000
    origin = 3_000_000_000_000
    t1 = 1.47
    lag = round(t1 * rate)
    epoch0 = 1700.25
    code_slope = -29.5
    epoch1 = (epoch0 + t1 * code_slope - lag) % (rate / 750)

    def probe(time_samples, epoch, freq):
        return dict(
            receiver_id=0,
            channel=1,
            actual_rf_hz=11.6e9,
            valid_start_counter=origin + time_samples,
            candidates=[
                dict(
                    integer_epoch_sample=int(epoch),
                    fractional_epoch_offset_samples=epoch - int(epoch),
                    fractional_tracking_cfo_hz=freq,
                    fractional_margin=0.2,
                    passed_fractional_margin_gate=True,
                )
            ],
        )

    first, second = probe(0, epoch0, 5000.5), probe(lag, epoch1, 5000.5 - 2300 * t1)
    source = SimpleNamespace(
        probes=[first, second], first_counter=origin, sample_rate_hz=rate, probe_ms=20
    )
    (pair,), _ = votes.pair_votes(source)
    assert np.isclose(pair.cfo_slope, -2300, atol=1e-8)
    assert np.isclose(pair.code_slope, code_slope, atol=1e-7)
    for row in source.probes:
        row["candidates"][0]["fractional_tracking_cfo_hz"] += 12500 + row["actual_rf_hz"] * 3e-7
    (shifted,), _ = votes.pair_votes(source)
    assert abs(shifted.cfo_slope - pair.cfo_slope) < 1e-8


def test_worldwide_pair_votes_recover_an_arbitrary_planted_point():
    rate = 10_000_000
    planted = (-13.3, 161.2)
    earth = votes.geodetic_to_ecef_km(*planted, 0)
    up = earth / np.linalg.norm(earth)
    east = np.cross([0, 0, 1], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    bias = -96.0
    bank = []
    for interval in range(36):
        angle = 2 * np.pi * interval / 13
        direction = np.cos(angle) * east + np.sin(angle) * north
        transverse = np.cross(up, direction)
        p0 = earth + up * (550 + 10 * (interval % 7)) + transverse * 180
        p0 += direction * (28 * (interval % 19) - 250)
        v0 = direction * 7.5
        dt = 1.51
        accel = -8e-3 * p0 / np.linalg.norm(p0)
        p1, v1 = p0 + v0 * dt + 0.5 * accel * dt**2, v0 + accel * dt
        d0, d1 = p0 - earth, p1 - earth
        r0, r1 = np.linalg.norm(d0), np.linalg.norm(d1)
        rf = 11.6e9
        f_slope = ((d0 @ v0) / r0 - (d1 @ v1) / r1) * rf / (dt * votes.LIGHT_KM_S)
        frame_slope = (r1 - r0) * rate / (dt * votes.LIGHT_KM_S) + bias
        pair = votes.Pair(2 * interval, 2 * interval + dt, rf, f_slope, frame_slope, 0.2, interval)
        tree = cKDTree([p0 / np.linalg.norm(p0)])
        bank.append(votes.OrbitPair(pair, p0[None], p1[None], v0[None], v1[None], tree))
    train = [item for item in bank if item.pair.interval % 4 != 3]
    held = [item for item in bank if item.pair.interval % 4 == 3]
    result, metrics = votes._search(train, held, rate, tile=None)
    xyz = votes.geodetic_to_ecef_km(*result, 0)
    assert np.linalg.norm(xyz - earth) < 15
    assert metrics["sample_clock_slope"] == bias
    assert metrics["support_validation"] >= 0.9
    assert metrics["held_lead"] >= 0.07


def test_empty_candidate_stream_withholds_without_a_forced_guess():
    capture = SimpleNamespace(probes=[], first_counter=0, sample_rate_hz=10_000_000, probe_ms=20)
    result = votes.solve(capture)
    assert result["status"] == "withheld"
    assert result["metrics"]["selected_pairs"] == 0
    assert all(
        arm["latlon"] is None and arm["forced_latlon"] is None for arm in result["arms"].values()
    )


def test_converged_finalists_cannot_supply_a_spatial_lead():
    result = votes.validation_metrics([(0.0, 0.0), (0.001, -0.001)], [0.8, 0.4], supplied=True)
    assert result["held_lead"] is None
    assert votes.decision(result) == (False, "no spatially separated validation alternative")
