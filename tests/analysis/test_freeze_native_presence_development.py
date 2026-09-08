"""Selection is bounded and rate/edge balanced, without opening hardware/storage."""

import json
from pathlib import Path

import pytest

from tools.freeze_native_presence_development import freeze, visit_indices
from tools.native_presence import ROOT


@pytest.fixture
def protocol():
    return json.loads((ROOT / "config/analysis/arm-presence-wide-development-v1.json").read_text())


def test_frozen_selection_covers_all_targets_without_cherry_picking(protocol):
    indices = visit_indices(protocol)
    assert len(indices) == 40
    assert indices == tuple(sorted(set(indices)))
    assert all(sum(i % 8 == target for i in indices) == 5 for target in range(8))
    assert not set(indices).intersection(range(1200, 1216))


@pytest.mark.parametrize(
    "change",
    [
        {"receiver": 0},
        {"probe_duration_ms": 120},
        {"reference_candidates": 2},
        {"sweeps": []},
        {"sweeps": [2, 1]},
        {"sweeps": [1, 1]},
        {"sweeps": [-1]},
        {"sweeps": [1.5]},
        {"sweeps": list(range(9))},
    ],
)
def test_rejects_unreviewed_geometry_and_unbounded_selection(protocol, change):
    with pytest.raises(ValueError):
        visit_indices({**protocol, **change})


def test_rejects_archive_and_qnap_outputs_before_storage_is_opened(tmp_path):
    for output in (tmp_path / "experiment", Path("/mnt/qnap01/experiment")):
        with pytest.raises(ValueError, match="capture or QNAP"):
            freeze(tmp_path, output, tmp_path / "nonexistent.json")
