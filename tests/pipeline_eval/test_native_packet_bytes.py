import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from native_packet_bytes import NativePacketBytes
from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.storage.fast_scan import immutable_json


def packet():
    return dict(source={"probes":[{"margin":.031886, "epoch":117.25, "cfo":-1298.759},
                                  {"candidates":[]}], "session_id":"élévation"},
                clock_anchor={"sample_counter":187})


def test_snapshot_matches_released_writer_and_full_terminal_binding(tmp_path):
    path = tmp_path/"detections.json"
    original = packet()
    immutable_json(path, original)
    calls = []

    def encode(value):
        calls.append(value)
        return canonical_json_bytes(value)

    snapshot = NativePacketBytes.capture(original, encode)
    assert snapshot.load_verified(path) == (original, canonical_digest(original))
    assert snapshot.verified_readback(path) == (path.read_bytes(), canonical_digest(original))
    assert len(calls) == 1


def test_readback_never_reuses_a_digest_across_changed_typed_rows(tmp_path):
    path = tmp_path/"detections.json"
    original = packet()
    pre_held = NativePacketBytes.capture(original, canonical_json_bytes)
    original["source"]["probes"][0]["cfo"] = 1298.759
    immutable_json(path, original)
    with pytest.raises(ValueError, match="differ"):
        pre_held.load_verified(path)
    selected = NativePacketBytes.capture(original, canonical_json_bytes)
    assert selected.load_verified(path) == (original, canonical_digest(original))
    assert selected.sha256 != pre_held.sha256


def test_same_value_in_a_different_noncanonical_file_requires_original_fallback(tmp_path):
    path = tmp_path/"detections.json"
    original = packet()
    snapshot = NativePacketBytes.capture(original, canonical_json_bytes)
    path.write_text(json.dumps(original, indent=4))
    with pytest.raises(ValueError, match="differ"):
        snapshot.verified_readback(path)
    assert canonical_digest(json.loads(path.read_bytes())) == snapshot.sha256


def test_mutable_buffer_cannot_mint_a_byte_snapshot():
    with pytest.raises(TypeError, match="immutable"):
        NativePacketBytes(bytearray(b"{}"))
