"""Resumption saves objective calls without changing the search path or budget."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


def test_cached_replay_reproduces_complete_search(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("resume_merged_track_search")
    original = []

    def objective(point):
        value = float((point[0] + 37) ** 2 + (point[1] - 48) ** 2)
        original.append(dict(east_north_km=point.tolist(), score=value, final=False))
        return value

    expected = tool.search.regional_search(objective)
    calls = []

    def recompute(point):
        calls.append(point.tolist())
        return float((point[0] + 37) ** 2 + (point[1] - 48) ** 2)

    actual = tool.search.regional_search(tool.replay_objective(recompute, original[:100]))
    assert actual == expected
    assert len(calls) == len(original) - 100
    assert not any(p in calls for p in [r["east_north_km"] for r in original[:100]])


def test_conflicting_cache_is_rejected(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("resume_merged_track_search")
    with pytest.raises(ValueError, match="conflicting"):
        tool.replay_objective(
            lambda p: 0,
            [
                dict(east_north_km=[0, 0], score=1, final=False),
                dict(east_north_km=[0, 0], score=2, final=False),
            ],
        )


def test_evaluate_sealed_fit_uses_coordinate_pairs_and_preserves_fit(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("resume_merged_track_search")
    path = tmp_path / "fit.json"
    path.write_text(json.dumps(dict(endpoint=dict(latitude_deg=37.0, longitude_deg=-122.0))))
    before = path.read_bytes()
    evaluation = tool.evaluate_frozen(tmp_path, (37.0, -122.0))
    assert evaluation["position_error_km"] == 0
    assert evaluation["fit_sha256"] == hashlib.sha256(before).hexdigest()
    assert path.read_bytes() == before
    assert evaluation["reference_used_only_after_fit"]
