import importlib.util
import sys
from pathlib import Path

import numpy as np


def load(name, relative):
    path = Path(__file__).parents[2] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_packed_score_matches_scalar_across_blocks_and_ignores_reserved_values():
    fast = load("test_fast_score", "reports/2026_09_23_long_training_fast_score/score.py")
    slow = load("test_slow_score", "reports/2026_09_23_long_training_search/search.py")
    rng = np.random.default_rng(723)
    receiver, up = slow.receiver_ecef(38.0, -121.0)
    prepared = []
    for i, n in enumerate((7, 11, 9)):
        position = receiver + up * 700 + rng.normal(0, 50, (8, n, 3))
        velocity = rng.normal(0, 2, (8, n, 3))
        prepared.append(
            {
                "track_id": str(i),
                "position": position,
                "velocity": velocity,
                "measured_hz": rng.normal(0, 1000, n),
                "training_mask": np.arange(n) % 3 != 0,
                "weight_s": n,
            }
        )
    expected, selected = slow.score_point(prepared, np.arange(8).astype(str), 38.0, -121.0)
    for block in (1, 3, 8, 20):
        result = fast.score(fast.pack(prepared), receiver, up, block_size=block)
        np.testing.assert_allclose(result[0], expected, atol=1e-8)
        assert list(result[1]) == [int(row["candidate_id"]) for row in selected]
        np.testing.assert_allclose(
            result[2], [row["frequency_offset_hz"] for row in selected], atol=1e-8
        )
        np.testing.assert_allclose(
            result[3], [row["training_rms_hz"] for row in selected], atol=1e-8
        )
    original = fast.score(fast.pack(prepared), receiver, up)
    for track in prepared:
        track["measured_hz"][~track["training_mask"]] += 1e8
    altered = fast.score(fast.pack(prepared), receiver, up)
    for left, right in zip(original, altered, strict=True):
        np.testing.assert_array_equal(left, right)
