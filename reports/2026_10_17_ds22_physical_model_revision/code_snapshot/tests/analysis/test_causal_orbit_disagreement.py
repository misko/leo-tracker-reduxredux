"""An older epoch collected in the future is still forbidden."""

import importlib
from pathlib import Path


def test_previous_version_requires_past_collection_and_distinct_epoch(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("audit_causal_orbit_disagreement")
    records = [
        dict(norad=1, epoch=e, collected=c, digest=d)
        for e, c, d in [(50, 70, "a"), (50, 80, "b"), (75, 101, "future"), (90, 99, "same-epoch")]
    ]
    result = tool.previous_versions({1: 90}, records, 100)
    assert result[1]["digest"] == "b"
