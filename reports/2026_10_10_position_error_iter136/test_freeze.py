import json

import freeze
import pytest


def fixture(monkeypatch, tmp_path):
    here = tmp_path / "reports/iter136"
    here.mkdir(parents=True)
    clean = tmp_path / "reports/2026_10_10_position_error_iter132"
    (clean / "results").mkdir(parents=True)
    members = [dict(label=f"m{i}", dataset="synthetic", session_id=f"s{i}") for i in range(12)]
    (clean / "protocol.json").write_text(json.dumps(dict(sources={}, members=members)))
    for i, member in enumerate(members):
        (clean / "results" / (member["label"] + ".json")).write_text(
            json.dumps(
                dict(
                    label=member["label"],
                    protocol_sha256=freeze.AUTHORITY,
                    status="failed" if i == 3 else "complete",
                )
            )
        )
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "HERE", here)
    monkeypatch.setattr(freeze, "sha", lambda path: freeze.AUTHORITY)
    return here, clean


def test_all_members_preserved_and_explicit_closure(monkeypatch, tmp_path):
    here, _ = fixture(monkeypatch, tmp_path)
    (here / "report.py").write_text("outside scientific closure")
    plan = freeze.prepare()
    assert len(plan["members"]) == 12
    assert plan["members"][3]["label"] == "m3"
    assert plan["maximum_endpoint_evaluations"] == 24
    assert plan["optimizer_calls"] == 0
    assert len(plan["inputs"]) == 13
    assert not any(p.endswith("report.py") for p in plan["sources"])


@pytest.mark.parametrize(
    "field,value", [("label", "foreign"), ("protocol_sha256", "foreign"), ("status", "pending")]
)
def test_foreign_prerequisite_cannot_create_protocol(monkeypatch, tmp_path, field, value):
    here, clean = fixture(monkeypatch, tmp_path)
    path = clean / "results/m3.json"
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="foreign/nonterminal"):
        freeze.main()
    assert not (here / "protocol.json").exists()


def test_exclusive_freeze(monkeypatch, tmp_path):
    here, _ = fixture(monkeypatch, tmp_path)
    freeze.main()
    original = (here / "protocol.json").read_bytes()
    with pytest.raises(FileExistsError):
        freeze.main()
    assert (here / "protocol.json").read_bytes() == original
