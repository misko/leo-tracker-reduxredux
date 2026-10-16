import json
import os

import pytest

from leo.storage.fast_scan import FastScanStore
from leo.storage.shared_fast_scan import SharedFastScanStore


def source(tmp_path):
    old = FastScanStore(tmp_path)
    old.publish_tracking_input("run", {"session_id": "test"})
    store = SharedFastScanStore(tmp_path, "shared-scan-q-v1")
    return old, store, next(store.inputs())


def terminal(store, job, **changes):
    document = dict(schema_version=1, kind="fast-scan.shared-position",
        model_version=store.model_version, input_sha256=job["input_sha256"], state="complete",
        position=dict(latitude_deg=38., longitude_deg=-121.),
        selection=dict(accepted=True, stationarity=.0001))
    document.update(changes)
    folder = store.workspace(job["job_id"])/"output"
    folder.mkdir(exist_ok=True)
    (folder/"terminal.json").write_text(json.dumps(document))
    return document


def test_reads_do_not_create_and_legacy_outputs_unchanged(tmp_path):
    missing = tmp_path/"absent"
    store = SharedFastScanStore(missing, "shared-scan-q-v1")
    assert store.page() == {"items": []}
    assert not missing.exists()
    old, store, job = source(tmp_path)
    old.update_automatic("capture", state="complete")
    old.publish("run", {"original": True})
    store.launch(job)
    expected = terminal(store, job)
    _, receipt = store.terminal(job)
    store.update(job, state="complete", terminal=receipt)
    assert store.detail(job["job_id"])["result"] == expected
    assert old.automatic_status("capture")["state"] == "complete"
    assert old.detail("run") == {"original": True}
    (store.workspace(job["job_id"])/"output"/"terminal.json").write_text(
        json.dumps(dict(expected, position=dict(latitude_deg=39., longitude_deg=-121.))))
    with pytest.raises(ValueError, match="digest changed"):
        store.detail(job["job_id"])


@pytest.mark.parametrize("changes", [dict(model_version="other"), dict(input_sha256="wrong"),
    dict(position=None), dict(position=dict(latitude_deg=float("nan"), longitude_deg=0)),
    dict(selection=dict(accepted=False, stationarity=0)),
    dict(selection=dict(accepted=True, stationarity=.002))])
def test_invalid_complete_or_identity_never_published(tmp_path, changes):
    _, store, job = source(tmp_path)
    terminal(store, job, **changes)
    with pytest.raises(ValueError):
        store.terminal(job)


def test_newest_first_hash_cache_mutation_and_version_isolation(tmp_path, monkeypatch):
    old, store, job = source(tmp_path)
    old.publish_tracking_input("new", {"new": True})
    os.utime(old.tracking_input_path("new"), ns=(10**18, 10**18))
    os.utime(old.tracking_input_path("run"), ns=(10**17, 10**17))
    jobs = list(store.inputs())
    assert [j["run_id"] for j in jobs] == ["new", "run"]
    import leo.storage.shared_fast_scan as module
    original = module.sha256_digest
    calls = []
    monkeypatch.setattr(module, "sha256_digest", lambda v: (calls.append(1), original(v))[1])
    assert list(store.inputs()) == jobs and not calls
    old.tracking_input_path("run").write_text('{"changed":true}')
    updated = list(store.inputs())
    assert len(calls) == 1
    assert updated[1]["job_id"] != job["job_id"]
    with pytest.raises(ValueError, match="source changed"):
        store.verify_input(job)
    assert next(SharedFastScanStore(tmp_path, "v2").inputs())["job_id"] != updated[0]["job_id"]


def test_qnap_and_symlink_escape_rejected(tmp_path):
    with pytest.raises(ValueError):
        SharedFastScanStore("/mnt/qnap01/output", "v1")
    _, store, job = source(tmp_path)
    folder = store.workspace(job["job_id"])
    outside = tmp_path/"outside"
    outside.mkdir()
    (folder/"output").symlink_to(outside, target_is_directory=True)
    from leo.storage.errors import PathConfinementError
    with pytest.raises(PathConfinementError):
        store.terminal(job)
    (folder/"status.json").symlink_to(outside/"private.json")
    with pytest.raises(PathConfinementError):
        store.status(job["job_id"])
