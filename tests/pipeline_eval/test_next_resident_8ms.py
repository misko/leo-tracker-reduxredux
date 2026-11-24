from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("next_resident_8ms")


def snapshot(items, resident=True):
    return dict(unavailable={}, members=len(items), observed_members=len(items),
                cached_pages=len(items) if resident else 0, observed_file_pages=len(items))


def test_no_body_open_for_cold_manifest(study, tmp_path, monkeypatch):
    monkeypatch.setattr(study, "BULK", tmp_path)
    path = tmp_path / "leo/fast-scan-recordings/original/segment/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"deliberately unreadable json")
    (path.parent / "iq-000000.ci16.zst").write_bytes(b"raw")
    (path.parent / "windows-000000.jsonl").write_bytes(b"idx")
    row = {"case": "test", "bytes": 3, "visits": 64, "segments": [{"path": str(path), "sha256": "unused"}]}
    probe = lambda entries: snapshot(entries, resident=entries[0][1] != "manifest.json")
    result = study.observe(row, probe)
    assert not result["admitted_original"]
    assert result["match_prior_payload_extent"]
    assert result["observed"]["payload"]["cached_pages"] == 1


def test_signed_full_extent_and_all_indexes_are_required(study, tmp_path, monkeypatch):
    monkeypatch.setattr(study, "BULK", tmp_path)
    path = tmp_path / "leo/fast-scan-recordings/original/segment/manifest.json"
    path.parent.mkdir(parents=True)
    part = dict(payload_relative_path="signed", index_relative_path="index", compressed_bytes=3, index_bytes=3,
                compressed_sha256="p", index_sha256="i")
    manifest = json.dumps({"chunks": [part]}).encode()
    path.write_bytes(manifest)
    check = sha256(manifest).hexdigest()
    row = {"case": "test", "bytes": 3, "visits": 64, "segments": [{"path": str(path), "sha256": check}]}
    assert study.observe(row, snapshot)["admitted_original"]
    assert not study.observe(dict(row, bytes=4), snapshot)["admitted_original"]
    probe = lambda entries: snapshot(entries, resident=entries[0][1] != "index")
    assert not study.observe(row, probe)["admitted_original"]
