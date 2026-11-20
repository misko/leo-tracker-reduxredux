from types import SimpleNamespace

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants import joint_pass_id as joint
from tools.pipeline_eval.variants import rate_triplets as triplet
from tools.pipeline_eval.variants import region_challenge as method


def test_hardware_reservation_excludes_complete_subblocks_before_tracking():
    origin, rate = 438723, 1000
    counters = [0, 8599, 8600, 9999, 10000, 18599, 18600, 21000]
    probes = [{"valid_start_counter": origin + t, "candidates": [t]} for t in counters]
    capture = SimpleNamespace(first_counter=origin, sample_rate_hz=rate, probes=probes)
    training, held = method.partition(capture)
    assert [p["candidates"][0] for p in training.probes] == [0, 8599, 10000, 18599, 21000]
    assert [p["candidates"][0] for p in held] == [8600, 9999, 18600]
    assert len(capture.probes) == len(counters)


def test_oversampling_one_time_block_does_not_create_independent_evidence():
    blocks = np.array([0, 0, 0, 2, 2])
    values = np.array([2, 2, 2, 3, 3])
    assert abs(method.block_score(values, blocks) - np.log(6)) < 1e-10
    assert abs(method.block_score(np.repeat(values, 4), np.repeat(blocks, 4)) - np.log(6)) < 1e-10


def test_competition_rejects_an_inside_estimate_when_one_outside_fit_is_better():
    same = method.comparison(3, [3] * 8)
    np.testing.assert_allclose(same, (0, 0), atol=1e-15)
    assert method.comparison(0, [1, *[-10] * 7])[0] < 0
    assert method.comparison(np.log(9), [0] * 8)[1] > np.log(8)


def test_geometry_uses_nine_equal_tiles_with_a_shared_start_lattice():
    assert method.REGIONS[0] == (0, 0)
    assert len(method.REGIONS) == len(set(method.REGIONS)) == 9
    lattices = [{(2 * x + a, 2 * y + b) for a, b in method.STARTS} for x, y in method.REGIONS]
    assert all(len(grid) == 5 for grid in lattices)
    assert len(set.union(*lattices)) == 33


def test_fixed_emitter_prefers_planted_geometry_on_reserved_carrier_and_frame_samples():
    times = np.array([8.7, 9, 9.3, 18.7, 19, 19.3, 28.7, 29, 29.3])
    station = geodetic_to_ecef_km(0, 0, 0)
    rf = 11.6e9
    knots = np.arange(joint.ORIGIN_S, 51)
    p = np.stack((np.full(len(knots), 6860), 7.5 * (knots - 19), np.zeros(len(knots))), axis=1)
    v = np.tile([0, 7.5, 0], (len(knots), 1))
    bank = joint.Bank(np.array([101]), p[None], v[None])
    freq, delay = joint.project(*bank.states(0, times, 0), station, rf)
    arrival = (delay + 1100 + 0.4 * times) % joint.FRAME_US
    held = method.Held(
        times,
        (times // 10).astype(int),
        triplet.wrap(freq)[:, None],
        arrival[:, None],
        {0: np.arange(len(times))},
    )
    args = (
        bank,
        [SimpleNamespace(group=0, rf_hz=rf, t=np.array([0]))],
        {0: joint.Option(0, 0, 0, 0)},
        {0: 0},
        held,
    )
    calibration = (np.zeros(9), {0: (1100, 0.4)}, {0: 0}, False)
    inside = method.validate(*args, {"forced_latlon": [0, 0]}, *calibration)
    outside = method.validate(*args, {"forced_latlon": [0, 0.25]}, *calibration)
    assert inside["conditional_rms_hz"] < 1e-8
    assert inside["heldout_frame_rms_us"] < 1e-8
    assert inside["validation_score"] > outside["validation_score"] + 15
