from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "explore_glrt64_tracks.py"
    spec = importlib.util.spec_from_file_location("explore_glrt64_tracks_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(tool, index: int, time_s: float, cfo_hz: float):
    return tool.Candidate(index, time_s, cfo_hz, 0.0, cfo_hz, 0.8, 0.05, 0.75, 0.95)


def test_continuity_keeps_frequency_branches_separate() -> None:
    tool = _tool()
    candidates = tuple(
        [_candidate(tool, i, i * 0.05, 300_000 - i * 200) for i in range(6)]
        + [_candidate(tool, 6 + i, 0.40 + i * 0.05, 400_000 - i * 100) for i in range(6)]
    )

    tracks = tool.continuity_tracks(candidates, np.ones(12, dtype=bool))

    assert len(tracks) == 2
    assert [track.point_count for track in tracks] == [6, 6]


def test_predictive_linker_bridges_a_bounded_missed_probe() -> None:
    tool = _tool()
    candidates = tuple(
        _candidate(tool, index, time_s, 300_000 - time_s * 4_000)
        for index, time_s in enumerate((0.0, 0.05, 0.10, 0.20, 0.25, 0.30))
    )

    tracks = tool.predictive_tracks(candidates, np.ones(6, dtype=bool))

    assert len(tracks) == 1
    assert tracks[0].point_count == 6
    assert tracks[0].rms_residual_hz < 1.0


def test_stitcher_joins_consistent_tracklets_across_a_longer_gap() -> None:
    tool = _tool()
    times = (0.0, 0.05, 0.10, 0.15, 0.20, 1.00, 1.05, 1.10, 1.15, 1.20)
    candidates = tuple(
        _candidate(tool, index, time_s, 300_000 - time_s * 4_000)
        for index, time_s in enumerate(times)
    )

    tracks = tool.stitched_predictive_tracks(candidates, np.ones(10, dtype=bool))

    assert len(tracks) == 1
    assert tracks[0].point_count == 10
    assert tracks[0].rms_residual_hz < 1.0


def test_robust_quadratic_rejects_far_frequency_outliers() -> None:
    tool = _tool()
    values = [
        _candidate(tool, index, index * 0.05, 310_000 - 4_000 * index * 0.05) for index in range(20)
    ]
    values.extend(
        _candidate(tool, 20 + index, 0.025 + index * 0.10, -300_000 + index * 50_000)
        for index in range(5)
    )
    candidates = tuple(sorted(values, key=lambda item: item.time_s))

    tracks = tool.robust_quadratic_tracks(
        candidates,
        np.ones(len(candidates), dtype=bool),
        iterations=500,
        seed=7,
    )

    assert tracks
    assert tracks[0].point_count == 20
    assert tracks[0].rms_residual_hz < 1.0
