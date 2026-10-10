import json

import pytest

from leo.storage.fast_scan import FastScanStore, FastSegmentSource
from tests.fast_scan_support import recording


def test_inventory_replay_hashes_and_immutable_reports(tmp_path):
    path = recording(tmp_path / "raw")
    store = FastScanStore(tmp_path / "bulk")
    session, digest, doc = store.ingest(path)
    assert store.ingest(path) == (session, digest, doc)
    assert store.source(session, digest) == doc
    windows = list(FastSegmentSource(doc["segments"][0]).windows())
    assert [w.acquisition["sample_start"] for w in windows] == [0, 100000, 200000]
    assert windows[0].acquisition.get("sample_start_utc_ns") is None
    store.publish("run", {"points": [1], "counts": {"processed": 2}})
    store.publish("run", {"points": [1], "counts": {"processed": 2}})
    assert "points" not in store.page()["items"][0]
    with pytest.raises(ValueError, match="immutable"):
        store.publish("run", {})
    manifest = path / "manifest.json"
    value = json.loads(manifest.read_text())
    value["stop_reason"] = "modified"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="manifest changed"):
        FastSegmentSource(doc["segments"][0])


def test_rejects_rate_generation_and_unsafe_names(tmp_path):
    store = FastScanStore(tmp_path / "bulk")
    with pytest.raises(ValueError, match="2.5 MS/s"):
        store.ingest(recording(tmp_path / "rate", rate=5000000))
    with pytest.raises(ValueError, match="mixed stream"):
        store.ingest(recording(tmp_path / "generation", generation_change=True))
    with pytest.raises(ValueError, match="identifier"):
        store.detail("../secret")


def test_owned_publications_reject_symlinked_directories(tmp_path):
    from leo.storage.errors import PathConfinementError

    bulk = tmp_path / "bulk"
    bulk.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (bulk / "fast-scan-reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathConfinementError):
        FastScanStore(bulk).publish("run", {"points": []})
    assert list(outside.iterdir()) == []


def test_automatic_progress_is_separate_from_immutable_results(tmp_path):
    store = FastScanStore(tmp_path)
    store.publish("run", {"points": [], "run_id": "run"})
    store.update_automatic("capture", state="glrt")
    store.update_automatic("capture", state="tracking", run_id="run")
    assert store.automatic_status("capture")["run_id"] == "run"
    assert store.automatic_page()["items"][0]["state"] == "tracking"
    assert store.detail("run") == {"points": [], "run_id": "run"}
    with pytest.raises(ValueError):
        store.update_automatic("../escape", state="complete")
