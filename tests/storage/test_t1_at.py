import pytest

from leo.analysis.t1_at import associate
from leo.contracts.digests import canonical_digest
from leo.contracts.t1_at import T1AtProductV1
from leo.storage.t1_at import T1AtInputFile, T1AtProductStore
from tests.analysis.test_t1_at import source


def product():
    prepared = source((), ())
    return T1AtProductV1(
        **associate(prepared),
        prepared_input_sha256=canonical_digest(prepared.model_dump(mode="json")),
        input_manifest_sha256=prepared.input_manifest_sha256,
        analysis_manifest_sha256=prepared.analysis_manifest_sha256,
    )


def test_immutable_idempotent_publish(tmp_path):
    store = T1AtProductStore(tmp_path)
    value = product()
    store.save(value)
    store.save(value)
    paths = list(tmp_path.rglob("product.json"))
    assert len(paths) == 1
    assert T1AtProductV1.model_validate_json(paths[0].read_bytes()) == value
    assert store.load(value.prepared_input_sha256) == value
    assert store.load("sha256:" + "b" * 64) is None
    with pytest.raises(ValueError, match="conflicts"):
        store.save(value.model_copy(update=dict(session_id="different")))
    assert T1AtProductV1.model_validate_json(paths[0].read_bytes()) == value
    assert not list(tmp_path.rglob("*.partial"))


def test_qnap_rejected_before_write():
    with pytest.raises(ValueError, match="read-only"):
        T1AtProductStore(__import__("pathlib").Path("/mnt/qnap01/anything"))


def test_input_session_binding(tmp_path):
    path = tmp_path / "prepared.json"
    value = source((), ())
    path.write_text(value.model_dump_json())
    assert T1AtInputFile(path).load(value.session_id) == value
    with pytest.raises(ValueError, match="session differs"):
        T1AtInputFile(path).load("different")


def test_discovery_bank_digest_and_array_inventory(tmp_path):
    import numpy as np

    from leo.contracts.digests import sha256_digest
    from leo.storage.t1_at import T1AtDiscoveryFile
    from tests.analysis.test_t1_at_prediction import bank

    data = bank()
    values = {k: getattr(data, k) for k in data.__dataclass_fields__ if k != "manifest"}
    archive = tmp_path / "prediction-bank.npz"
    np.savez_compressed(archive, **values)
    manifest = data.manifest.model_copy(
        update=dict(bank_sha256=sha256_digest(archive.read_bytes()))
    )
    path = tmp_path / "input.json"
    path.write_text(manifest.model_dump_json())
    loaded = T1AtDiscoveryFile(path).load(manifest.evidence.session_id)
    np.testing.assert_array_equal(loaded.position_km, data.position_km)
    archive.write_bytes(b"different")
    with pytest.raises(ValueError, match="digest mismatch"):
        T1AtDiscoveryFile(path).load(manifest.evidence.session_id)
