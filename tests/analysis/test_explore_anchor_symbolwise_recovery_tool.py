from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "explore_anchor_symbolwise_recovery.py"
    spec = importlib.util.spec_from_file_location("explore_anchor_symbolwise_recovery_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_negative_tail_scale_does_not_use_positive_signal_values() -> None:
    tool = _tool()
    baseline = tool._negative_side_sigma(np.asarray([-2.0, -1.0, 100.0, 200.0]))
    changed_signal = tool._negative_side_sigma(np.asarray([-2.0, -1.0, 1_000.0, 2_000.0]))

    assert baseline == changed_signal


def test_hysteresis_retains_weak_neighbors_only_when_component_has_enough_seeds() -> None:
    tool = _tool()
    tracker = tool._module("recovery_test_tracker", "explore_glrt64_tracks.py")
    candidates = tuple(
        tracker.Candidate(index, index * 0.05, 300_000.0, 0.0, 300_000.0, score, 0.0, score, 0.9)
        for index, score in enumerate((0.06, 0.16, 0.17, 0.06, 0.06, 0.06))
    )
    scores = np.asarray([item.glrt64_margin for item in candidates])

    rejected = tool._hysteresis_selection(
        tracker,
        candidates,
        scores,
        high=0.15,
        low=0.05,
        minimum_high_points=3,
    )
    retained = tool._hysteresis_selection(
        tracker,
        candidates,
        scores,
        high=0.15,
        low=0.05,
        minimum_high_points=2,
    )

    assert not np.any(rejected)
    assert np.all(retained)


def test_glrt_seeded_corridor_recovers_jittery_contiguous_track() -> None:
    tool = _tool()
    tracker = tool._module("recovery_corridor_tracker", "explore_glrt64_tracks.py")
    jitter_hz = (0.0, 6_000.0, -6_000.0, 0.0) * 3
    candidates = tuple(
        tracker.Candidate(
            index,
            index * 0.2,
            300_000.0 + jitter,
            0.0,
            300_000.0 + jitter,
            0.20,
            0.0,
            0.20,
            0.9,
        )
        for index, jitter in enumerate(jitter_hz)
    )
    policy = tool.RecoveryPolicy(
        "glrt64_corridor",
        "test corridor",
        np.ones(len(candidates), dtype=bool),
        "robust_corridor",
    )

    strict = tool._tracklets(tracker, candidates, policy.selection)
    recovered = tool._tracks_for_policy(tracker, candidates, policy)

    assert strict
    assert all(track.point_count < len(candidates) for track in strict)
    assert len(recovered) == 1
    assert recovered[0].candidate_indexes == tuple(range(len(candidates)))
