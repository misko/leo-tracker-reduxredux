from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from reports.ALGO08.v3 import ci16_packed_storage_trial as runner
from reports.ALGO08.v3.future_capture_storage import ORIGINAL, verified_source


def reference(tmp_path, monkeypatch, *, second_probe="same"):
    density = {
        "source": {"path": str(tmp_path / "member"), "manifest_digest": "manifest-pin"},
        "original_member": {
            "chunk_index": 0, "first_sequence": 0, "window_count": 64, "compressed_sha256": "compressed-pin",
            "uncompressed_sha256": "decoded-pin", "index_sha256": "index-pin",
            "compressed_bytes": 77_442_779, "index_bytes": 172_750,
        },
        "receivers": {"mixed": [
            {"probes_sha256": pin, "visits": {"full": 8, "short_primary": 56}, "selected": 67}
            for pin in ("same", second_probe)
        ]},
    }
    before = {"timing": {"input_blocks": 0}, "no_blocking_payload_fallback": True}
    monkeypatch.setattr(runner, "DENSE_STAGE", tmp_path)
    for name, value, attribute in (("result.json", density, "DENSE_RECEIPT"), ("staged.json", before, "DENSE_STAGING")):
        payload = json.dumps(value).encode()
        (tmp_path / name).write_bytes(payload)
        monkeypatch.setattr(runner, attribute, sha256(payload).hexdigest())
    return tmp_path / "member"


def test_dense_transfer_uses_the_sealed_member_and_probe_reference(tmp_path, monkeypatch):
    location = reference(tmp_path, monkeypatch)
    result = runner.dense_member()
    assert (result.case, result.path, result.compressed_bytes, result.prior_probes) == (
        "DS30-0008", location, 77_442_779, "same")
    assert (result.manifest, result.decoded, result.index) == ("manifest-pin", "decoded-pin", "index-pin")


def test_dense_transfer_rejects_shifted_results(tmp_path, monkeypatch):
    reference(tmp_path, monkeypatch, second_probe="other")
    with pytest.raises(ValueError, match="receiver reference changed"):
        runner.dense_member()


def test_original_storage_path_fails_before_payload_access():
    backing = replace(ORIGINAL, path=Path("/srv/bulk/does-not-exist"))
    with pytest.raises(ValueError, match="tmpfs"):
        verified_source(None, None, backing)
