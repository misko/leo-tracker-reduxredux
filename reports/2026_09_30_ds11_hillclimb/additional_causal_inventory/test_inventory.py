import importlib.util
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("additional_causal_inventory", HERE / "inventory.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_journal_keeps_exact_provider_digest_publication():
    text = (
        '1790701431.972715 host env[1]: {"event":"tle_collection","providers":['
        '{"provider":"space-track","digest":"sha256:abc","status":"published"},'
        '{"provider":"huggingface","digest":null,"status":"rate_limited"}]}\n'
    )
    rows = MODULE.parse_journal(text)
    assert len(rows) == 2
    assert rows[0]["journal_published_utc_ns"] == 1790701431972715000
    assert rows[0]["snapshot_sha256"] == "sha256:abc"
    assert rows[1]["status"] == "rate_limited"


def test_qualifying_receipt_requires_completed_file_exact_digest_and_pre_capture(monkeypatch):
    ref = SimpleNamespace(provider="space-track", digest="sha256:abc", path=Path("unused"))
    monkeypatch.setattr(
        MODULE,
        "file_times",
        lambda path: {
            "file_birth_utc": "birth",
            "file_mtime_utc": "mtime",
            "file_birth_utc_ns": 100,
            "file_mtime_utc_ns": 110,
        },
    )
    rows = [
        {"provider": "space-track", "snapshot_sha256": "sha256:wrong", "status": "published", "journal_published_utc_ns": 120, "journal_published_unix_s": "0.0", "journal_line": "wrong"},
        {"provider": "space-track", "snapshot_sha256": "sha256:abc", "status": "published", "journal_published_utc_ns": 105, "journal_published_unix_s": "0.0", "journal_line": "before-file"},
        {"provider": "space-track", "snapshot_sha256": "sha256:abc", "status": "published", "journal_published_utc_ns": 150, "journal_published_unix_s": "0.0", "journal_line": "qualified"},
    ]
    assert MODULE.qualifying_receipt(ref, 140, rows) is None
    proof = MODULE.qualifying_receipt(ref, 200, rows)
    assert proof["journal_line"] == "qualified"
    assert proof["journal_published_utc_ns"] == 150


def test_newest_element_rule_uses_epoch_then_source_time_and_digest():
    older_epoch_late_source = (10, 500, "sha256:z", "old")
    newer_epoch_early_source = (20, 100, "sha256:a", "new")
    same_epoch_later_source = (20, 200, "sha256:b", "newer-source")
    assert MODULE.choose_newest(
        [older_epoch_late_source, newer_epoch_early_source, same_epoch_later_source]
    ) == same_epoch_later_source
