import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction

PATH = Path(__file__).parents[2] / "tools/research/audit_position_receiver_drift.py"
SPEC = importlib.util.spec_from_file_location("receiver_drift_subject", PATH)
assert SPEC.loader is not None
SUBJECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUBJECT
SPEC.loader.exec_module(SUBJECT)


def test_shared_slope_recovers_injected_value_with_track_intercepts():
    rows = []
    for offset in (10.0, -40.0, 90.0):
        time = np.arange(8.0)
        rows.append({
            "times_s": time,
            "training_mask": np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=bool),
            "residual_hz": offset + 2.5 * time,
        })
    assert np.isclose(SUBJECT.fit_shared_slope(rows), 2.5)


def _prediction(measured):
    measured = np.asarray(measured, dtype=float)
    model = np.stack([np.arange(8), np.arange(8)[::-1]])[:, None, :]
    return AdaptiveTrackPrediction(
        "t", tuple(map(str, range(8))), np.arange(8.0), measured,
        np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=bool), np.array(["a", "b"]),
        np.array([0.0]), model, np.ones(2, dtype=bool),
    )


def test_track_choice_and_fitted_values_ignore_reserved_frequency_mutation():
    original = _prediction(np.arange(8) + 100.0)
    changed = original.measured_hz.copy()
    changed[~original.training_mask] += 1e7
    before = SUBJECT.select_track(original)
    after = SUBJECT.select_track(_prediction(changed))
    assert (before["candidate_id"], before["tau_s"], before["cfo_hz"]) == (
        after["candidate_id"], after["tau_s"], after["cfo_hz"]
    )
    assert SUBJECT.fit_shared_slope([before]) == SUBJECT.fit_shared_slope([after])
