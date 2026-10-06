from pathlib import Path

import pytest

from leo.storage.regional_position import RegionalPositionStore
from tests.contracts.test_regional_position_products import document

PNG = b"\x89PNG\r\n\x1a\nfixture"


def test_roundtrip_both_maps_and_immutable_publication(tmp_path):
    store = RegionalPositionStore(tmp_path, read_only=False)
    assert store.status("scan-1").state == "pending"
    images = {"T1AT": PNG, "V16": PNG + b"v16"}
    manifest = store.publish(document(), images)
    assert store.publish(document(), images) == manifest
    reader = RegionalPositionStore(tmp_path)
    assert reader.status("scan-1").manifest == manifest
    for method, payload in images.items():
        assert reader.artifact("scan-1", method) == payload
    with pytest.raises(ValueError, match="immutable"):
        store.publish(document(), {"T1AT": PNG + b"changed", "V16": images["V16"]})
    with pytest.raises(PermissionError):
        reader.publish(document(), images)


@pytest.mark.parametrize("target", ["T1AT.png", "V16.png", "document.json"])
def test_tampered_products_are_rejected(tmp_path, target):
    store = RegionalPositionStore(tmp_path, read_only=False)
    store.publish(document(), {"T1AT": PNG, "V16": PNG})
    path = tmp_path / store.namespace / "scan-1" / target
    path.write_bytes(path.read_bytes() + b"altered")
    with pytest.raises(ValueError):
        store.artifact("scan-1", target.split(".")[0] if target.endswith("png") else "T1AT")


def test_no_partial_method_publication_or_traversal(tmp_path):
    store = RegionalPositionStore(tmp_path, read_only=False)
    with pytest.raises(ValueError, match="both"):
        store.publish(document(), {"T1AT": PNG})
    assert store.status("scan-1").state == "pending"
    with pytest.raises(ValueError):
        store.artifact("scan-1", "../outside")
    with pytest.raises(ValueError):
        store.status("../outside")
    with pytest.raises(ValueError, match="QNAP"):
        RegionalPositionStore(Path("/mnt/qnap01/forbidden"), read_only=False)


def test_namespace_symlink_cannot_redirect_publication(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / RegionalPositionStore.namespace).symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        RegionalPositionStore(tmp_path, read_only=False).publish(
            document(), {"T1AT": PNG, "V16": PNG}
        )
    assert list(outside.iterdir()) == []
