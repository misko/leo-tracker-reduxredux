import copy
import json
from pathlib import Path

import pytest

from tools.freeze_native_presence_holdout import freeze, local_counter, selection
from tools.native_presence import ROOT


@pytest.fixture
def protocol():
    return json.loads((ROOT / "config/analysis/arm-presence-holdout-v1.json").read_text())


def test_full_tiling_is_balanced_and_bounded(protocol):
    indices = selection(protocol)
    assert len(indices) == 24
    assert all(sum(i % 8 == target for i in indices) == 3 for target in range(8))
    assert len(indices) * len(protocol["sessions"]) * len(protocol["probe_offsets_ms"]) == 576


@pytest.mark.parametrize(
    "change",
    [
        {"receiver": 0},
        {"probe_offsets_ms": [0, 50, 100]},
        {"reference_candidates": 2},
        {"reference_margin": 0.03},
        {"sweeps": [False]},
        {"sweeps": [2, 1]},
        {"sweeps": [1, 1]},
        {"sweeps": [290]},
        {"sweeps": list(range(5))},
    ],
)
def test_unreviewed_geometry_is_rejected(protocol, change):
    with pytest.raises(ValueError):
        selection({**protocol, **change})


def test_previously_used_or_duplicate_sessions_are_rejected(protocol):
    altered = copy.deepcopy(protocol)
    for value in (
        protocol["excluded_previously_examined_sessions"][0],
        protocol["sessions"][1]["session_id"],
    ):
        altered["sessions"][0]["session_id"] = value
        with pytest.raises(ValueError):
            selection(altered)


def test_counter_offsets_preserve_integer_precision():
    assert local_counter(10**16 + 17, 5000000, 100) == 10**16 + 500017
    for args in ((2**64 - 1, 5000000, 0), (0, 3000000, 0), (0, 5000000, 120), (0.0, 5000000, 0)):
        with pytest.raises(ValueError):
            local_counter(*args)


def test_archive_outputs_rejected_before_any_read(tmp_path):
    for output in (tmp_path / "result", Path("/mnt/qnap01/result")):
        with pytest.raises(ValueError, match="archive"):
            freeze(tmp_path, output, tmp_path / "missing.json")
