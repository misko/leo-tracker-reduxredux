import numpy as np
import pytest

from tools.pipeline_eval.qualification import external_blind_trial as trial
from tools.pipeline_eval.scoring import validate_result
from tools.pipeline_eval.variants import external_blind_doppler as solver


def test_anonymous_chain_uses_measured_continuity_across_interleaved_tones():
    original = [(i * 10**9, -900 + 2 * i) for i in range(90)]
    rival = [(i * 10**9, 1100 - 7 * i) for i in range(90)]
    later = [(200 * 10**9, -720)]
    assert trial.anonymous_chains(original + rival + later) == [original, rival, later]


def test_early_orbit_and_clock_validate_same_physical_trace_only():
    xyz = np.zeros((3, 1, 32, 3))
    xyz[..., 0] = 7000
    velocities = np.zeros_like(xyz)
    velocities[:, 0, :, 0] = np.arange(32) * np.array([[0.05], [0.03], [0.08]])
    rf = np.array([137.5e6])
    measurements = 325 - velocities[0, :, :, 0] * (rf[0] / solver.LIGHT_KM_S)
    bank = solver.Bank(
        xyz, velocities, np.ones((3, 1), bool), np.array([12, 15, 17]), measurements, rf
    )
    train, held, norad, margin, available = solver.score_point(bank, (0, 0), measurements)
    assert train[0] < 1e-9 and held[0] < 1e-9
    assert (norad[0], available[0]) == (12, 3)
    assert margin[0] > solver.MIN_ORBIT_MARGIN_HZ
    reversed_fit = solver.score_point(bank, (0, 0), measurements[:, ::-1])
    assert reversed_fit[1][0] > solver.MAX_PREDICTION_ERROR_HZ


def test_worker_rejects_label_fields_and_non_board_requests():
    with pytest.raises(ValueError, match="unexpected field"):
        solver.orbit_bank([dict(norad=41182)], [{}, {}, {}], 0)
    with pytest.raises(ValueError, match="offered tiles"):
        solver.infer(dict(tracks=[], catalogue=[], cutoff_ns=0, tiles={"only": [0, 0]}))
    result = solver.outcome(
        [10.0, 20.0], "insufficient_held_tile_margin", dict(held_robust_rms_hz=20.0)
    )
    validate_result(result)
    assert result["arms"]["c0"]["forced_latlon"] == [10.0, 20.0]
    assert result["arms"]["fitted_c"]["status"] == "unavailable"
