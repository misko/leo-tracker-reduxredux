from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore
from tests.contracts.test_adaptive_tle_position import document

PNG = b"\x89PNG\r\n\x1a\nsmall"


def test_store_round_trip_and_immutable_conflict(tmp_path):
    writer = AdaptiveTlePositionStore(tmp_path, read_only=False)
    with writer.writer("scan-1"):
        manifest = writer.publish(document(), PNG)
    reader = AdaptiveTlePositionStore(tmp_path)
    assert reader.status("scan-1").manifest == manifest
    assert reader.artifact("scan-1") == PNG
    changed = document().model_copy(update={"configuration_sha256": canonical_digest("changed")})
    with writer.writer("scan-1"), pytest.raises(ValueError, match="immutable"):
        writer.publish(changed, PNG)


def test_store_refuses_qnap():
    with pytest.raises(ValueError, match="QNAP"):
        AdaptiveTlePositionStore(Path("/mnt/qnap01/adaptive"))
