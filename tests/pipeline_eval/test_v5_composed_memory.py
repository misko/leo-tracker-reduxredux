import json
from contextlib import contextmanager

import pytest

from tools.pipeline_eval.variants import v5_composed_memory as composed


def test_composition_keeps_both_contexts_live_and_preserves_downstream_evidence(
    tmp_path, monkeypatch
):
    active = []

    @contextmanager
    def columns():
        active.append("track columns")
        try:
            yield {"calls": 3}
        finally:
            assert active.pop() == "track columns"

    @contextmanager
    def late(directory):
        assert directory == tmp_path
        active.append("late bank")
        try:
            yield {"rows": 128}
        finally:
            assert active.pop() == "late bank"

    def salvage(request, result, library):
        assert (request, library) == ("request", "library")
        assert active == ["track columns", "late bank"]
        result.write_text(
            json.dumps(dict(metrics={"salvage": True}, arms={"c0": {}, "fitted_c": {}}))
        )

    monkeypatch.setattr(composed.v5_track_projection, "track_projection", columns)
    monkeypatch.setattr(composed.v5_stream_recovery, "streamed_recovery", late)
    monkeypatch.setattr(composed.v5_tiled_salvage, "worker", salvage)
    result = tmp_path / "result.json"
    composed.worker("request", result, "library")
    assert not active
    assert json.loads(result.read_bytes()) == {
        "boundary": composed.BOUNDARY,
        "arms": {"c0": {}, "fitted_c": {}},
        "metrics": {
            "salvage": True,
            "track_projection": {"calls": 3},
            "bounded_recovery_rows": {"rows": 128},
        },
    }


def test_failed_component_exits_both_policies(tmp_path, monkeypatch):
    active = []

    @contextmanager
    def policy(*args):
        active.append(1)
        try:
            yield {}
        finally:
            active.pop()

    def fail(*args):
        assert len(active) == 2
        raise ValueError("unavailable component")

    monkeypatch.setattr(composed.v5_track_projection, "track_projection", policy)
    monkeypatch.setattr(composed.v5_stream_recovery, "streamed_recovery", policy)
    monkeypatch.setattr(composed.v5_tiled_salvage, "worker", fail)
    with pytest.raises(ValueError, match="unavailable component"):
        composed.worker("request", tmp_path / "result.json", "library")
    assert not active
