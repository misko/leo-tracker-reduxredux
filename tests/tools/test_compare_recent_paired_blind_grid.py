import importlib.util
from pathlib import Path

import numpy as np


def _subject():
    path = Path(__file__).parents[2] / "tools/research/compare_recent_paired_blind_grid.py"
    spec = importlib.util.spec_from_file_location("compare_recent_paired_blind_grid", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_visit_partition_never_splits_receivers_and_survives_permutation():
    subject = _subject()
    visits = {f"g{index}": index for index in range(10)}
    left = {
        "paired_visit_ids": [f"g{index}" for index in (0, 1, 2, 5, 7, 8)],
        "tracklet_id": "left",
        "t_s": list(range(6)),
        "y_hz": list(range(6)),
    }
    right = {
        "paired_visit_ids": [f"g{index}" for index in (0, 2, 3, 5, 6, 9)],
        "tracklet_id": "right",
        "t_s": list(range(6)),
        "y_hz": list(range(6)),
    }
    partition = subject._shared_partition(left, right, set(), set(), visits)
    reversed_partition = subject._shared_partition(right, left, set(), set(), visits)

    assert partition == reversed_partition
    for series in (left, right):
        mask = np.asarray([partition[visits[value]] for value in series["paired_visit_ids"]])
        assert min(np.sum(mask), np.sum(~mask)) >= 2


def test_anchor_rows_are_removed_before_shared_partition_is_applied():
    subject = _subject()
    series = {
        "paired_visit_ids": [f"g{index}" for index in range(6)],
        "tracklet_id": "track",
        "t_s": list(range(6)),
        "y_hz": list(range(6)),
    }
    visit = {f"g{index}": index for index in range(6)}
    partition = {index: index < 3 for index in range(1, 6)}
    arc = subject._arc(series, {"g0"}, partition, visit)

    assert len(arc.time_s) == 5
    np.testing.assert_array_equal(arc.training, [True, True, False, False, False])
