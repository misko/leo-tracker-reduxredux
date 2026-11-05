import io
import json
import zipfile
from copy import deepcopy

import numpy as np
import pytest

from leo.storage.errors import PathConfinementError
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v3_codec import pack, unpack
from tests.localization_v3_fixture import evidence_fixture


def test_lossless_archive_is_deterministic_and_deduplicates_arrays():
    _, pngs = evidence_fixture()
    array = np.arange(12, dtype=">f8").reshape(3, 4)
    value = {
        1: (array, array.copy()),
        "minus_zero": -0.0,
        "inf": float("inf"),
        "nan": float("nan"),
        "numpy": np.float32(0.1),
        "empty": np.zeros((0, 2)),
    }
    raw = pack(value, pngs)
    assert raw == pack(deepcopy(value), pngs)
    restored, images = unpack(raw)
    assert images == pngs and list(restored) == list(value)
    assert isinstance(restored[1], tuple)
    np.testing.assert_array_equal(restored[1][0], array, strict=True)
    assert restored[1][0] is restored[1][1] and not restored[1][0].flags.writeable
    assert restored["minus_zero"].hex() == (-0.0).hex()
    assert np.isnan(restored["nan"]) and np.isposinf(restored["inf"])
    assert type(restored["numpy"]) is np.float32
    assert restored["numpy"].tobytes() == value["numpy"].tobytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        # NumPy scalar bytes live in the tree, not a separate archive member.
        # One tree, two distinct arrays and one shared tiny PNG.
        assert len(archive.namelist()) == 4
    with pytest.raises(ValueError, match="Object arrays"):
        pack(np.array([object()], dtype=object), pngs)


def test_archive_rejects_tampered_and_unbound_members():
    _, pngs = evidence_fixture()
    raw = pack(np.arange(3), pngs)
    for corruption in ("blob", "extra"):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(output, "w") as target:
            for name in original.namelist():
                data = original.read(name)
                if corruption == "blob" and name != "values.json":
                    data += b"changed"
                target.writestr(name, data)
            if corruption == "extra":
                target.writestr("../unbound", b"never extracted")
        with pytest.raises(ValueError, match="digest mismatch|Unbound"):
            unpack(output.getvalue())


def test_inline_scalars_preserve_dtype_and_bits_including_structured_values():
    _, pngs = evidence_fixture()
    values = [
        np.float32(-0.0),
        np.float64(float("nan")),
        np.int64(-3),
        np.uint64(2**64 - 1),
        np.complex128(1 + 2j),
        np.datetime64("2026-11-05", "ns"),
        np.str_(""),
        np.bytes_(b""),
        np.array((2, 0.5), dtype=[("n", "i4"), ("x", "f8")])[()],
    ]
    restored, _ = unpack(pack(values, pngs))
    for original, saved in zip(values, restored, strict=True):
        assert type(saved) is type(original)
        assert saved.dtype == original.dtype
        assert saved.tobytes() == original.tobytes()


def test_result_commit_is_immutable_and_reloads_all_evidence(tmp_path):
    evidence, pngs = evidence_fixture()
    store = LocalizationV3Store(tmp_path)
    saved = store.save(evidence, pngs)
    assert store.save(evidence, pngs) == saved
    loaded = store.load("run")
    assert loaded["evidence"] == evidence and loaded["pngs"] == pngs
    assert loaded["sha256"] == saved["sha256"]
    changed = deepcopy(evidence)
    changed["render"]["title"] = "different"
    with pytest.raises(ValueError, match="immutable"):
        store.save(changed, pngs)
    assert store.load("run")["evidence"] == evidence
    path = tmp_path / "localization-v3-v1/run" / (saved["receipt"]["result_sha256"][7:] + ".zip")
    path.write_bytes(path.read_bytes()[:-10])
    with pytest.raises(ValueError, match="integrity"):
        store.load("run")


def test_failed_manifest_commit_is_not_a_completed_result(tmp_path, monkeypatch):
    import leo.storage.localization_v3 as storage

    evidence, pngs = evidence_fixture()
    store = LocalizationV3Store(tmp_path)
    original = storage.immutable_json

    def interrupt(*args):
        raise OSError("injected interruption")

    monkeypatch.setattr(storage, "immutable_json", interrupt)
    with pytest.raises(OSError, match="interruption"):
        store.save(evidence, pngs)
    with pytest.raises(FileNotFoundError):
        store.load("run")
    monkeypatch.setattr(storage, "immutable_json", original)
    store.save(evidence, pngs)
    assert store.load("run")["evidence"] == evidence


def test_cross_scan_and_untrusted_paths_fail(tmp_path):
    evidence, pngs = evidence_fixture()
    store = LocalizationV3Store(tmp_path)
    store.save(evidence, pngs)
    manifest = tmp_path / "localization-v3-v1/run/manifest.json"
    changed = json.loads(manifest.read_text())
    changed["run_id"] = "other"
    manifest.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="another run"):
        store.load("run")
    with pytest.raises(ValueError):
        store.load("../outside")
    (tmp_path / "localization-v3-v1/escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PathConfinementError, match="symlink"):
        store.load("escape")
    with pytest.raises(ValueError, match="local"):
        LocalizationV3Store("/mnt/qnap01/not-written")
