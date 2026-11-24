from random import Random
from types import SimpleNamespace

import pytest
import zstandard

from reports.ALGO08.v3 import partial_window_attestation as witness


def row(sequence, offset, body):
    return dict(sequence=sequence, decoded_offset_bytes=offset, decoded_bytes=len(body),
                sha256=witness.digest(body))


def test_attestation_keeps_empty_issued_visits_and_stops_at_first_short_row():
    rows = [row(0, 0, b"first"), row(1, 5, b""), row(2, 5, b"longer"), row(3, 11, b"fourth")]
    verified, extent, stop = witness.complete_prefix(b"firstlon", rows)
    assert verified == rows[:2] and extent == 5
    assert stop == dict(sequence=2, emitted_bytes=3, expected_bytes=6, reason="incomplete_decoded_visit")


def test_mismatched_full_visit_refuses_further_attestation():
    rows = [row(0, 0, b"first"), row(1, 5, b"good"), row(2, 9, b"next")]
    with pytest.raises(ValueError, match="digest mismatch at visit 1"):
        witness.complete_prefix(b"firstevilnext", rows)
    rows[1]["decoded_offset_bytes"] = 7
    with pytest.raises(ValueError, match="contiguous"):
        witness.complete_prefix(b"firstevilnext", rows)


def test_primary_decoder_leaves_end_of_frame_unverified():
    source = Random(123).randbytes(360_000)
    encoded = zstandard.ZstdCompressor(write_checksum=True).compress(source)
    raw, proof = witness.partial_decode(encoded[:210_000], len(source))
    assert raw == source[:len(raw)] and len(raw) < len(source)
    assert proof["decoded_bytes"] == len(raw) and not proof["frame_eof"]
    with pytest.raises(ValueError, match="incomplete original frame"):
        witness.partial_decode(encoded, len(source))
    with pytest.raises(ValueError, match="signed decoded extent"):
        witness.partial_decode(encoded[:210_000], 20)


def test_secondary_must_agree_including_the_unattested_trailing_bytes(monkeypatch):
    raw = b"exact signed visit and incomplete next"
    completed = SimpleNamespace(returncode=1, stderr=b"Read error: premature end", stdout=raw)
    monkeypatch.setattr(witness.subprocess, "run", lambda *_a, **_k: completed)
    assert witness.confirm_decode(b"encoded", raw)["decoded_sha256"] == witness.digest(raw)
    completed.stdout = raw[:-1]
    with pytest.raises(ValueError, match="same incomplete"):
        witness.confirm_decode(b"encoded", raw)
