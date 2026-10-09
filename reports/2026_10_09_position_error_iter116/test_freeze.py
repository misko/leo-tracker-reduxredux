import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "freeze116_test", Path(__file__).with_name("freeze.py")
)
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def inputs(tmp_path, session=None):
    document = dict(
        session_id=session or F.PILOT_SESSION,
        diagnostics=dict(bank=dict(retained_numbers=[1, 2])),
        methods=[dict(points=[dict(east_km=0, north_km=0, spacing_km=40, score=7)])],
    )
    imported = dict(
        session_id=document["session_id"], bank_numbers=[1, 2], records=[dict(point=[0, 0])]
    )
    a, b = tmp_path / "document.json", tmp_path / "import.json"
    a.write_text(json.dumps(document))
    b.write_text(json.dumps(imported))
    return a, b


def test_freezer_refuses_new_members_without_metadata_rule(tmp_path):
    a, b = inputs(tmp_path, "other-recording")
    with pytest.raises(ValueError, match="only the previously"):
        F.prepare_plan(a, b, {}, repository=tmp_path)


def test_freezer_does_not_invent_unavailable_array_hashes(tmp_path, monkeypatch):
    a, b = inputs(tmp_path)
    monkeypatch.setattr(F, "source_check", lambda *a: [])
    with pytest.raises(ValueError, match="preflight identity"):
        F.prepare_plan(a, b, {}, repository=tmp_path)
    assert not (tmp_path / "protocol.json").exists()


def test_freezer_rejects_lost_ordinary_point_coverage(tmp_path, monkeypatch):
    a, b = inputs(tmp_path)
    value = json.loads(b.read_text())
    value["records"] = []
    b.write_text(json.dumps(value))
    monkeypatch.setattr(F, "source_check", lambda *a: [])
    with pytest.raises(ValueError, match="coverage changed"):
        F.prepare_plan(a, b, {}, repository=tmp_path)
