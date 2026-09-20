import json
from pathlib import Path

import pytest


def test_metadata_joins_by_identity_not_source_order(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from diagnose_wide_capture_groups import episode_metadata

    root = tmp_path / "evidence"
    root.mkdir()
    doc = dict(
        inventory=dict(sample_rate_hz=20000000),
        episodes=[dict(episode_id="b", members=["b1"]), dict(episode_id="a", members=["a1", "a2"])],
        series=[
            dict(tracklet_id="b1", channel=2, edge="upper"),
            dict(tracklet_id="a2", channel=1, edge="upper"),
            dict(tracklet_id="a1", channel=1, edge="lower"),
        ],
    )
    path = root / "scan.json"
    path.write_text(json.dumps(doc))
    assignments = [
        dict(session_id="scan", episode_id="a", norad=1),
        dict(session_id="scan", episode_id="b", norad=2),
    ]
    rows, sources = episode_metadata(assignments, tmp_path)
    assert [(r["channel"], r["edge"]) for r in rows] == [("1", "mixed"), ("2", "upper")]
    assert all(r["sample_rate_hz"] == 20000000 for r in rows)
    assert len(sources) == 1
    doc["series"].pop()
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="member evidence"):
        episode_metadata(assignments, tmp_path)
