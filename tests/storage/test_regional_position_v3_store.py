import pytest

from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store
from tests.contracts.test_regional_position_v3 import document


def test_b7_publication_is_immutable_and_separate_from_v2(tmp_path):
    store = B7Store(tmp_path, read_only=False)
    png = b"\x89PNG\r\n\x1a\nfixture"
    manifest = store.publish(document(), {"V16": png})
    assert store.status("scan-1").manifest == manifest
    assert Hard60Store(tmp_path).status("scan-1").manifest is None
    with pytest.raises(ValueError, match="immutable"):
        store.publish(document(), {"V16": png + b"different"})
