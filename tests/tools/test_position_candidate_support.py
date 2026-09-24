import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction

PATH = Path(__file__).parents[2] / "tools/research/audit_position_candidate_support.py"
SPEC = importlib.util.spec_from_file_location("candidate_support_subject", PATH)
assert SPEC.loader is not None
SUBJECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUBJECT
SPEC.loader.exec_module(SUBJECT)


def _prediction(measured):
    measured = np.asarray(measured, dtype=float)
    model = np.stack([np.arange(6), np.arange(6)[::-1]])[:, None, :]
    return AdaptiveTrackPrediction(
        "track",
        tuple(map(str, range(6))),
        np.arange(6.0),
        measured,
        np.array([1, 0, 1, 0, 1, 0], dtype=bool),
        np.array(["a", "b"]),
        np.array([0.0]),
        model,
        np.ones(2, dtype=bool),
    )


def test_selection_is_invariant_to_reserved_frequency_mutation():
    original = _prediction(np.arange(6) + 10.0)
    changed_y = original.measured_hz.copy()
    changed_y[~original.training_mask] += 1e8
    before = SUBJECT.select_training(original)
    after = SUBJECT.select_training(_prediction(changed_y))
    assert (before["candidate_id"], before["tau_s"], before["training_rms_hz"]) == (
        after["candidate_id"],
        after["tau_s"],
        after["training_rms_hz"],
    )


def test_weighted_rms_and_span_buckets():
    rows = [{"weight_s": 1, "x": 3.0}, {"weight_s": 3, "x": 1.0}]
    assert SUBJECT.weighted_rms(rows, "x") == np.sqrt(3.0)
    assert [SUBJECT.span_bucket(value) for value in (3, 10, 20, 40)] == [
        "03-09s",
        "10-19s",
        "20-39s",
        "40s+",
    ]
