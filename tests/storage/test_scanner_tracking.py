from pathlib import Path

import pytest

from leo.contracts.scanner_tracking import ScannerTrackingStatusV1
from leo.storage.scanner_tracking import ScannerTrackingStore
from tests.application.test_scanner_tracking import PNG, service


def test_pending_read_is_read_only_and_rejects_unsafe_ids(tmp_path):
    store = ScannerTrackingStore(tmp_path)
    assert store.status("scan-test").state == "pending"
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        store.status("../escape")
    with pytest.raises(PermissionError):
        store.save(ScannerTrackingStatusV1(session_id="scan-test"))
    with pytest.raises(ValueError):
        ScannerTrackingStore(Path("/mnt/qnap01"))


def test_sealed_publication_tamper_detection_and_immutability(tmp_path, monkeypatch):
    runner, store = service(tmp_path, monkeypatch)
    product = runner.run("scan-test").product
    store.publish(product)
    with pytest.raises(ValueError):
        store.save(ScannerTrackingStatusV1(session_id="scan-test"))
    with pytest.raises(ValueError):
        store.put_artifact("scan-test", "trajectory", PNG + b"changed")
    (tmp_path / "scanner-shared-tracking-v1" / "scan-test" / "trajectory.png").write_bytes(
        PNG + b"changed"
    )
    with pytest.raises(ValueError, match="digest"):
        store.artifact("scan-test", "trajectory")
