import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_receiver_drift.py"
    spec = importlib.util.spec_from_file_location("position_receiver_drift_model", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prediction(track_id, offset, slope, reserved_delta=0.0, visible=True):
    times = np.arange(8.0)
    training = np.asarray([1, 0, 1, 0, 1, 0, 1, 0], dtype=bool)
    measured = offset + slope * times
    measured = measured.copy()
    measured[~training] += reserved_delta
    return AdaptiveTrackPrediction(
        track_id,
        tuple(f"{track_id}-{index}" for index in range(8)),
        times,
        measured,
        training,
        np.asarray(["candidate", "wrong"]),
        np.asarray([0.0]),
        np.stack((np.zeros(8), 100.0 * times))[:, None, :],
        np.asarray([visible, visible]),
    )


def test_recovers_one_slope_shared_by_tracks_with_separate_intercepts():
    module = subject()
    rows = [prediction("a", 20.0, 2.5), prediction("b", -70.0, 2.5)]
    receivers = [np.asarray(["RX1"] * 8), np.asarray(["RX1"] * 8)]
    result = module.fit_receiver_slopes(rows, receivers, 0, 0.0)
    np.testing.assert_allclose(result["slopes_hz_per_s"]["RX1"], 2.5, atol=1e-12)


def test_reserved_rows_cannot_change_fitted_candidate_intercept_or_slope():
    module = subject()
    receivers = [np.asarray(["RX1"] * 8), np.asarray(["RX1"] * 8)]
    before = module.fit_receiver_slopes(
        [prediction("a", 20.0, 2.5), prediction("b", -70.0, 2.5)], receivers, 0, 100.0
    )
    after = module.fit_receiver_slopes(
        [prediction("a", 20.0, 2.5, 1e7), prediction("b", -70.0, 2.5, -1e7)],
        receivers,
        0,
        100.0,
    )
    assert before["slopes_hz_per_s"] == after["slopes_hz_per_s"]
    assert [row["candidate_id"] for row in before["tracks"]] == [
        row["candidate_id"] for row in after["tracks"]
    ]
    np.testing.assert_allclose(
        [row["offset_hz"] for row in before["tracks"]],
        [row["offset_hz"] for row in after["tracks"]],
    )
    assert before["reserved_rms_hz"] is None
    evaluated = module.fit_receiver_slopes(
        [prediction("a", 20.0, 2.5), prediction("b", -70.0, 2.5)],
        receivers,
        0,
        100.0,
        include_evaluation=True,
    )
    assert evaluated["reserved_rms_hz"] is not None


def test_all_invisible_candidates_are_rejected_explicitly():
    module = subject()
    with np.testing.assert_raises_regex(ValueError, "all candidates are invisible"):
        module.fit_receiver_slopes(
            [prediction("a", 20.0, 2.5, visible=False)],
            [np.asarray(["RX1"] * 8)],
            0,
            100.0,
        )
