import shutil
from pathlib import Path

import pytest

from leo.contracts.scanner_tracking import (
    ScannerTrackingProductV1,
    ScannerTrackingProductV4,
    ScannerTrackingStatusV5,
)
from leo.storage.adaptive_hop_analysis import _seal
from leo.storage.scanner_tracking import ScannerTrackingStore
from tests.application.test_scanner_tracking import PNG, service


def test_pending_read_is_read_only_and_rejects_unsafe_ids(tmp_path):
    store = ScannerTrackingStore(tmp_path)
    assert store.status("scan-test").state == "pending"
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        store.status("../escape")
    with pytest.raises(PermissionError):
        store.save(ScannerTrackingStatusV5(session_id="scan-test"))
    with pytest.raises(ValueError):
        ScannerTrackingStore(Path("/mnt/qnap01"))


def test_sealed_publication_tamper_detection_and_immutability(tmp_path, monkeypatch):
    runner, store = service(tmp_path, monkeypatch)
    product = runner.run("scan-test").product
    store.publish(product)
    with pytest.raises(ValueError):
        store.save(ScannerTrackingStatusV5(session_id="scan-test"))
    with pytest.raises(ValueError):
        store.put_artifact("scan-test", "trajectory", PNG + b"changed")
    (tmp_path / "scanner-shared-tracking-v5" / "scan-test" / "trajectory.png").write_bytes(
        PNG + b"changed"
    )
    with pytest.raises(ValueError, match="digest"):
        store.artifact("scan-test", "trajectory")


def test_legacy_utc_blocked_publication_is_pending_for_v2_reconstruction(tmp_path, monkeypatch):
    runner, _ = service(tmp_path, monkeypatch)
    current = runner.run("scan-test").product
    legacy = ScannerTrackingProductV1.model_validate(
        {
            **current.model_dump(
                exclude={"schema_version", "analysis_id", "trajectory_time_basis"}
            ),
            "trajectory_state": "unsupported",
            "tle_state": "unavailable",
            "reasons": ["capture lacks qualified UTC timing authority"],
            "projected_candidate_count": 0,
            "physical_group_count": 0,
            "eligible_group_count": 0,
            "attempted_group_count": 0,
            "deferred_group_count": 0,
            "tracklets": [],
            "tle_candidates": [],
            "unscored_groups": [],
            "artifacts": [],
            "tle_match_config_digest": None,
        }
    )
    v5 = tmp_path / "scanner-shared-tracking-v5"
    shutil.rmtree(v5)
    directory = tmp_path / "scanner-shared-tracking-v1" / "scan-test"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_bytes(_seal(legacy))

    status = ScannerTrackingStore(tmp_path).status("scan-test")
    assert status.state == "pending"
    assert status.product is None


def test_public_status_keeps_v4_while_v5_worker_sees_pending(tmp_path, monkeypatch):
    runner, _ = service(tmp_path, monkeypatch)
    current = runner.run("scan-test").product
    legacy = ScannerTrackingProductV4.model_validate(
        current.model_dump(exclude={"schema_version", "analysis_id"})
    )
    v5 = tmp_path / "scanner-shared-tracking-v5"
    shutil.rmtree(v5)
    directory = tmp_path / "scanner-shared-tracking-v4" / "scan-test"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_bytes(_seal(legacy))

    store = ScannerTrackingStore(tmp_path)
    assert store.status("scan-test").product == legacy
    assert store.analysis_status("scan-test").state == "pending"
