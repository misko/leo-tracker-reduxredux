import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))

import ds7_baseline_adapter as baseline  # noqa: E402
import ds7_fast_baseline_adapter as fast  # noqa: E402


def test_batched_offsets_match_frozen_scalar_profiler():
    rng = np.random.default_rng(20260927)
    values = rng.normal(size=(17, 31)) * rng.lognormal(5, 1, size=(17, 1))
    values += rng.normal(scale=4e5, size=(17, 1))
    offsets, audits = fast.fit_stationary_offsets(values)
    expected = [baseline.fit_stationary_offset(row) for row in values]
    np.testing.assert_array_equal(offsets, [row[0] for row in expected])
    assert audits == [row[1] for row in expected]


def test_fast_module_preserves_public_numerical_interface():
    assert fast.REFERENCE_RF_HZ == baseline.REFERENCE_RF_HZ
    assert fast.Stationary is baseline.Stationary
    assert fast.JointObjective is baseline.JointObjective
    assert callable(fast.load_documents)


def test_track_without_held_observation_is_legitimately_excluded():
    tracks = [
        {"track_id": "eligible", "training_mask": [True, True, False]},
        {"track_id": "no-held", "training_mask": [True, True, True]},
    ]
    eligible, excluded = fast.partition_eligible_tracks(tracks)
    assert set(eligible) == {"eligible"}
    assert excluded == [
        {
            "track_id": "no-held",
            "training_observations": 3,
            "held_out_observations": 0,
            "reasons": ["no_held_out_observation"],
        }
    ]
    fast.validate_eligible_coverage(["eligible"], eligible)


def test_missing_eligible_track_is_rejected():
    eligible = {"first": {}, "second": {}}
    with np.testing.assert_raises_regex(ValueError, "missing=\\['second'\\]"):
        fast.validate_eligible_coverage(["first"], eligible)


def test_training_rms_uses_visible_training_map_candidate(monkeypatch):
    track = {
        "y": np.array([10.0, 20.0, 1_000.0]),
        "mask": np.array([True, True, False]),
    }
    document = {"tracks": [track]}

    class Model:
        def __init__(self, supplied, _config):
            self.document = supplied

        def prediction(self, _track, _x):
            return np.array([[10.0, 20.0, 0.0], [110.0, 120.0, 1_000.0]]), np.array(
                [True, False]
            )

    def fake_profile(_residual, _mask):
        return (
            np.array([5.0, 50.0]),
            np.zeros(2),
            [{"converged": True}, {"converged": True}],
            np.array([1.0, 100.0]),
        )

    monkeypatch.setattr(baseline, "Stationary", Model)
    monkeypatch.setattr(fast, "profile", fake_profile)
    assert fast.training_rms_hz([document], {}, np.zeros(3)) == 1.0
