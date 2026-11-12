import pytest

from leo.application.localization_v3_result import _publish_saved
from leo.contracts import localization_v4
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v4 import LocalizationV4Store
from tests.localization_v4_fixture import evidence_fixture


def test_native_archive_uses_separate_namespace_and_publication_model(tmp_path):
    evidence, pngs = evidence_fixture()
    store = LocalizationV4Store(tmp_path)
    receipt = store.save(evidence, pngs)
    loaded = store.load("run")
    assert loaded["evidence"]["provenance"] == evidence["provenance"]
    assert loaded["pngs"] == pngs
    assert receipt["receipt"]["model_version"] == localization_v4.MODEL
    assert (tmp_path / "localization-v4-v1" / "run" / "manifest.json").is_file()
    with pytest.raises(FileNotFoundError):
        LocalizationV3Store(tmp_path).load("run")
    with pytest.raises(ValueError):
        LocalizationV3Store(tmp_path).save(evidence, pngs)
    publication = FastStandardAnalysisStore(tmp_path)
    manifest = _publish_saved("run", store, publication, contract=localization_v4)
    assert manifest["implementation_model"] == localization_v4.MODEL
    assert manifest["terminal_sha256"] == receipt["sha256"]
    assert _publish_saved("run", store, publication, contract=localization_v4) == manifest
