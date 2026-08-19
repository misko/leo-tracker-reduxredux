from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "compare_glrt_symbolwise_segmentation.py"
    spec = importlib.util.spec_from_file_location("compare_glrt_symbolwise_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_symbolwise_grows_five_sigma_seeds_through_positive_corridor() -> None:
    tool = _tool()
    tracker = tool._module("symbolwise_growth_tracker", "explore_glrt64_tracks.py")
    jitter_hz = (0.0, 6_000.0, -6_000.0, 0.0) * 3
    scores = np.asarray((0.03,) * 8 + (0.002,) * 4)
    candidates = tuple(
        tracker.Candidate(
            index,
            index * 0.2,
            300_000.0 + jitter,
            0.0,
            300_000.0 + jitter,
            score,
            0.0,
            score,
            0.9,
        )
        for index, (jitter, score) in enumerate(zip(jitter_hz, scores, strict=True))
    )
    # Supply a stable negative tail for the five-sigma estimate without putting
    # those controls on this positive candidate timeline.
    scale_scores = np.concatenate((scores, np.asarray((-0.001, -0.001))))
    gate = 5.0 * tool._negative_side_sigma(scale_scores)
    adjusted = scores.copy()
    assert gate < 0.03
    # The helper requires its own negative tail; make the final weak sample a
    # negative control and expect growth through the preceding positive points.
    adjusted[-1] = -0.001

    _, selected, tracks = tool._symbolwise_seed_and_grow(tracker, candidates, adjusted)

    assert len(tracks) == 1
    assert np.count_nonzero(selected) >= 8
    assert tracks[0].start_s == 0.0
    assert tracks[0].end_s >= 2.0
