import pytest

from reports.ALGO08.v3 import solver_exception_0129 as transfer


def test_saved_authority_and_cutoff_must_match_before_transfer(monkeypatch):
    for name, value in (("SESSION", "signed-session"), ("ISSUED", 2), ("ADMITTED", 1), ("CUTOFF", 10)):
        monkeypatch.setattr(transfer, name, value)
    region = {"width_km": 25}
    monkeypatch.setattr(transfer, "read", lambda _: region)
    doc = {"source": {"session_id": "signed-session", "input_manifest_sha256": "sha256:" + transfer.INVENTORY_PIN,
                      "raw_recording_authority_digest": "original", "probes": [{}, {}]},
           "provenance": {"processed_windows": 1}, "clock_anchor": {"before": {"realtime_ns": 10}}}
    inventory = {"window_count": 2, "segments": [{"path": "/original/member", "manifest_digest": "manifest"}]}
    pair = {"archive": {"snapshots_sha256": transfer.ARCHIVE_PIN},
            "runs": {"candidate": {"raw_authority": "original", "native_sha256": "sha256:" + transfer.NATIVE_PIN,
                                   "failure_observation": {"exit_code": 1}},
                     "baseline": {"receipt": {"region": region}}},
            "cache_observation": {"manifests": [{"path": "/original/member/manifest.json", "sha256": "manifest"}]}}
    assert transfer.validate(pair, doc, inventory) == [["/original/member/manifest.json", "manifest"]]
    doc["clock_anchor"]["before"]["realtime_ns"] += 1
    with pytest.raises(ValueError, match="cutoff"):
        transfer.validate(pair, doc, inventory)
