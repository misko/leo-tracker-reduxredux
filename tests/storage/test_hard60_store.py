import pytest

from leo.storage.regional_position import RegionalPositionStore
from leo.storage.regional_position_v2 import Hard60Store
from tests.contracts.test_regional_position_products import document as legacy_document
from tests.contracts.test_regional_position_v2 import document


def test_versions_coexist_and_new_publication_cannot_overwrite_existing(tmp_path):
    legacy = RegionalPositionStore(tmp_path, read_only=False)
    new = Hard60Store(tmp_path, read_only=False)
    png = b"\x89PNG\r\n\x1a\nfixture"
    legacy.publish(legacy_document(), {"T1AT": png, "V16": png})
    before = legacy.status("scan-1")
    new.publish(document(), {"V16": png})
    assert legacy.status("scan-1") == before
    assert new.status("scan-1").manifest.document.schema_version == 2
    assert new.artifact("scan-1", "V16") == png
    with pytest.raises(ValueError, match="conflict"):
        new.publish(document(), {"V16": png + b"changed"})
    with pytest.raises(ValueError, match="unknown"):
        new.artifact("scan-1", "T1AT")
