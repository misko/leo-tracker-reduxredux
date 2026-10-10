import json

import freeze
import pytest

AUTHORITY = "08624494f298852b5b29bacf89e1cb3c12c54c05698c3b42e8a0804e8bb34567"


def fixture(monkeypatch, tmp_path):
    here = tmp_path / "reports/iter135"
    here.mkdir(parents=True)
    clean = tmp_path / "reports/2026_10_10_position_error_iter132"
    (clean / "results").mkdir(parents=True)
    members = [
        dict(label=f"member-{i}", dataset="synthetic", session_id=f"session-{i}") for i in range(12)
    ]
    (clean / "protocol.json").write_text(json.dumps(dict(sources={}, members=members)))
    for index, member in enumerate(members):
        (clean / "results" / (member["label"] + ".json")).write_text(
            json.dumps(
                dict(
                    label=member["label"],
                    protocol_sha256=AUTHORITY,
                    status="failed" if index == 3 else "complete",
                )
            )
        )
    monkeypatch.setattr(freeze, "HERE", here)
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    # This test isolates membership/source-list policy; hashing is separately
    # exercised by the real freeze preflight and runner admission tests.
    monkeypatch.setattr(freeze, "sha", lambda path: AUTHORITY)
    return here, clean, members


def test_all_twelve_preserved_including_failed_prerequisite_and_report_excluded(
    monkeypatch, tmp_path
):
    here, _, members = fixture(monkeypatch, tmp_path)
    (here / "report.py").write_text("reporting is outside numerical closure")
    plan = freeze.prepare()
    assert [m["label"] for m in plan["members"]] == [m["label"] for m in members]
    assert plan["maximum_fit_calls"] == 48
    assert not any(name.endswith("/report.py") for name in plan["sources"])
    assert len(plan["inputs"]) == 13


@pytest.mark.parametrize(
    "field,value", [("label", "foreign"), ("protocol_sha256", "foreign"), ("status", "pending")]
)
def test_foreign_or_nonterminal_receipt_rejected_before_protocol_creation(
    monkeypatch, tmp_path, field, value
):
    here, clean, _ = fixture(monkeypatch, tmp_path)
    path = clean / "results/member-3.json"
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="foreign/nonterminal"):
        freeze.main()
    assert not (here / "protocol.json").exists()


def test_failed_preflight_does_not_touch_existing_protocol(monkeypatch, tmp_path):
    here, clean, _ = fixture(monkeypatch, tmp_path)
    target = here / "protocol.json"
    target.write_text("existing sealed content")
    (clean / "results/member-3.json").unlink()
    with pytest.raises(FileNotFoundError):
        freeze.main()
    assert target.read_text() == "existing sealed content"


def test_successful_freeze_is_exclusive(monkeypatch, tmp_path):
    here, _, _ = fixture(monkeypatch, tmp_path)
    freeze.main()
    before = (here / "protocol.json").read_bytes()
    with pytest.raises(FileExistsError):
        freeze.main()
    assert (here / "protocol.json").read_bytes() == before
