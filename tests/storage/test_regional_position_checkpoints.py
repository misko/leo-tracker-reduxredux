import pytest

from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

DIGEST = "sha256:" + "a" * 64


def test_resume_roundtrip_binding_isolation_and_immutable_conflict(tmp_path):
    store = RegionalCheckpointStore(tmp_path, "scan-1", DIGEST)
    assert store.get("point:50:50") is None
    with store.writer():
        store.put("point:50:50", {"vector": [1, 2], "reason": None})
        store.put("point:50:50", {"vector": [1, 2], "reason": None})
        with pytest.raises(ValueError, match="conflict"):
            store.put("point:50:50", {"vector": [3, 4]})
    assert RegionalCheckpointStore(tmp_path, "scan-1", DIGEST).get("point:50:50")["vector"] == [
        1,
        2,
    ]
    assert RegionalCheckpointStore(tmp_path, "scan-2", DIGEST).get("point:50:50") is None
    assert (
        RegionalCheckpointStore(tmp_path, "scan-1", "sha256:" + "b" * 64).get("point:50:50") is None
    )


def test_checkpoint_tampering_and_nonfinite_values_fail(tmp_path):
    store = RegionalCheckpointStore(tmp_path, "scan-1", DIGEST)
    with store.writer():
        store.put("test", {"number": 42})
        with pytest.raises(ValueError):
            store.put("nan", {"nested": [float("nan")]})
    path = next(tmp_path.rglob("*.json"))
    path.write_bytes(path.read_bytes().replace(b"42", b"43"))
    with pytest.raises(ValueError, match="verification"):
        store.get("test")
