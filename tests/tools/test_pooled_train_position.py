"""Pooled support must retain disjoint sessions without aliased track IDs."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_duplicate_track_ids_fail_closed():
    path = Path(__file__).resolve().parents[2] / "reports/2026_09_23_pooled_train_position/run.py"
    spec = importlib.util.spec_from_file_location("pooled", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helper = SimpleNamespace(prepare=lambda *args: ([{"track_id": "same"}], []))
    with pytest.raises(ValueError, match="duplicate"):
        module.prepare(helper, None, [["a"], ["b"]], [{"fixed_tracks": []}, {"fixed_tracks": []}])
