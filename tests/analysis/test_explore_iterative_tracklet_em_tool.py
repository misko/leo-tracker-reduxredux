from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "explore_iterative_tracklet_em.py"
    spec = importlib.util.spec_from_file_location("explore_iterative_tracklet_em_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _config(tool):
    return tool.MethodConfig(
        "symbolwise",
        "test",
        0.02,
        0.0,
        8_000.0,
        6,
        2,
        1.0,
        12_000.0,
        5_000.0,
        30_000.0,
        8_000.0,
    )


def test_one_second_seeds_merge_and_em_rejects_clutter() -> None:
    tool = _tool()
    tracker = tool._module("iterative_em_test_tracker", "explore_glrt64_tracks.py")
    candidates = []
    for index in range(40):
        time_s = index * 0.1
        frequency = 300_000.0 - 2_000.0 * time_s + ((index % 3) - 1) * 500.0
        score = 0.03 if index % 4 == 0 else 0.005
        candidates.append(
            tracker.Candidate(
                index,
                time_s,
                frequency,
                0.0,
                frequency,
                score,
                0.0,
                score,
                0.9,
            )
        )
    # Positive-score clutter is well outside the fitted corridor.
    clutter_index = len(candidates)
    candidates.append(
        tracker.Candidate(
            clutter_index,
            2.05,
            420_000.0,
            0.0,
            420_000.0,
            0.01,
            0.0,
            0.01,
            0.0,
        )
    )
    candidates = tuple(sorted(candidates, key=lambda candidate: candidate.time_s))
    # Restore index identity after sorting, matching production candidate tuples.
    candidates = tuple(
        tracker.Candidate(
            index,
            candidate.time_s,
            candidate.acquired_cfo_hz,
            0.0,
            candidate.refined_cfo_hz,
            candidate.glrt64_score,
            0.0,
            candidate.glrt64_margin,
            candidate.qam_accuracy,
        )
        for index, candidate in enumerate(candidates)
    )
    scores_array = np.asarray([candidate.glrt64_margin for candidate in candidates])
    config = _config(tool)

    seeds = tool._initial_seeds(candidates, scores_array, config)
    merged, events = tool._merge_groups(candidates, list(seeds), config)
    retained = [
        group
        for group in merged
        if candidates[int(group[-1])].time_s - candidates[int(group[0])].time_s >= 1.5
    ]
    refined, _ = tool._hard_em(candidates, scores_array, retained, config)

    assert len(seeds) == 4
    assert len(events) == 3
    assert len(refined) == 1
    assert candidates.index(next(c for c in candidates if c.time_s == 2.05)) not in refined[0]
    assert len(refined[0]) == 40
