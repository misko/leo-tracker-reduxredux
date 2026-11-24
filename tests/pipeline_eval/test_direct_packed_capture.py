from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.ci16_packing import Packing, SOURCE
from reports.ALGO08.v3.direct_packed_capture import Capture, close_file, write_capture
from reports.ALGO08.v3.north_direct_multichunk import normalized_native
from reports.ALGO08.v3.seekable_member import SAMPLES, WINDOW_BYTES, ShortWindowIndexV2, digest


@pytest.fixture
def example(tmp_path):
    binary = tmp_path/"packing.so"
    subprocess.run(["cc", "-O2", "-shared", "-fPIC", str(SOURCE), "-o", str(binary)], check=True)
    codec = Packing(binary)
    target = dict(target_id="test", edge="lower", channel=1, rf_center_hz=11_300_000_000, lnb_lo_hz=9_750_000_000)
    header = SimpleNamespace(sample_rate_hz=10_000_000, receiver_ids=(0, 1), radio={"serial": "test"},
                             configuration={"sample_rate_hz": 10_000_000, "window_ms": 20, "targets": [target]})
    owned = []
    for sequence, offset in enumerate((0, 1, 0)):
        data = np.full((SAMPLES, 2, 2), sequence, dtype="<i2").tobytes()
        index = ShortWindowIndexV2(sequence=sequence, target_id="test", sample_count=SAMPLES, receiver_count=2,
                                   payload_offset_bytes=offset*WINDOW_BYTES, payload_bytes=WINDOW_BYTES,
                                   iq_sha256=digest(data), acquisition={"global_visit": sequence}, powers=({}, {}))
        owned.append(SimpleNamespace(index=index, samples=np.frombuffer(data, dtype="<i2").reshape(SAMPLES, 2, 2)))
    with TemporaryDirectory(dir="/dev/shm", prefix="test-direct-packed-") as directory:
        recording = Path(directory)/"capture"
        pin, document = write_capture(recording, header, owned, (2, 1), codec)
        yield recording, pin, document, codec, owned


def test_independent_multichunk_authority_and_complete_readback(example):
    recording, pin, document, codec, owned = example
    capture = Capture(recording, pin, codec)
    _, _, inventory = capture.inventory(recording)
    actual = tuple(capture.segment(inventory["segments"][0]).windows())
    assert [window.sequence for window in actual] == [0, 1, 2]
    assert [window.iq_sha256 for window in actual] == [window.index.iq_sha256 for window in owned]
    assert all(np.array_equal(issued.samples, verified.samples) for issued, verified in zip(owned, actual, strict=True))
    assert [m["checks"]["full_checks"] for m in capture.audit] == [2, 1]
    assert [m["original_decoded_sha256"] for m in capture.audit] == [c["uncompressed_sha256"] for c in document["chunks"]]
    assert [m["encoded_blocks"] for m in capture.audit] == [4, 2]
    with pytest.raises(ValueError, match="one complete"):
        capture.segment(inventory["segments"][0])


def test_root_pin_and_corrupt_end_of_member_rejected(example):
    recording, pin, document, codec, _ = example
    with pytest.raises(ValueError, match="digest"):
        Capture(recording, digest(b"some other issuer"), codec)
    capture = Capture(recording, pin, codec)
    damaged = recording/document["chunks"][1]["directory"]/codec.part_files[1]
    encoded = bytearray(damaged.read_bytes())
    encoded[-1] ^= 1
    damaged.chmod(0o600)
    damaged.write_bytes(encoded)
    with pytest.raises(ValueError, match="digest"):
        list(capture.windows())
    assert len(capture.audit) == 1


def test_arbitrary_validly_hashed_chronology_still_rejected(example):
    recording, _, document, codec, _ = example
    metadata = recording/"capture.json"
    metadata.unlink()
    document["chunks"][1]["first_sequence"] = 3
    pin = close_file(metadata, document)
    with pytest.raises(ValueError, match="geometry"):
        Capture(recording, pin, codec)


def test_native_normalization_preserves_candidate_order_and_policy():
    packet = dict(provenance={"run_id": "path-specific", "detector_sha256": "pinned"},
                  source={"session_id": "path-specific", "analysis_manifest_sha256": "own", "probes": [1, 2]})
    assert normalized_native(packet) == {"provenance": {"detector_sha256": "pinned"}, "source": {"probes": [1, 2]}}
