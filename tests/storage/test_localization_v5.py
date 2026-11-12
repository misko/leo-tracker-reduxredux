import pytest

from leo.application.localization_v3_result import _publish_saved
from leo.contracts import localization_v5
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v4 import LocalizationV4Store
from leo.storage.localization_v5 import LocalizationV5Store
from tests.localization_v5_fixture import evidence_fixture


def test_v5_store_owns_namespace_receipt_and_publication(tmp_path):
    evidence, pngs = evidence_fixture()
    store = LocalizationV5Store(tmp_path)
    receipt = store.save(evidence, pngs)
    assert store.load('run')['pngs'] == pngs
    assert receipt['receipt']['model_version'] == localization_v5.MODEL
    assert (tmp_path / 'localization-v5-v1/run/manifest.json').is_file()
    for cls in (LocalizationV3Store, LocalizationV4Store):
        with pytest.raises(FileNotFoundError):
            cls(tmp_path).load('run')
        with pytest.raises(ValueError):
            cls(tmp_path).save(evidence, pngs)
    publication = FastStandardAnalysisStore(tmp_path)
    manifest = _publish_saved('run', store, publication, contract=localization_v5)
    assert manifest['implementation_model'] == localization_v5.MODEL
    assert manifest['terminal_sha256'] == receipt['sha256']
    assert _publish_saved('run', store, publication, contract=localization_v5) == manifest
