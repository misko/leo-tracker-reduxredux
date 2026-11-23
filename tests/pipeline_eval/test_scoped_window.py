from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from threading import Event

import numpy as np
import pytest
import zstandard

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.scoped_window_trial import ObservedStream, PAIRED, decoded_route
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes


def test_concurrent_retention_pins_all_slots_until_owned_fallback():
    windows = tuple(bytes((n,)) * 100 for n in range(7))
    compressed = zstandard.ZstdCompressor().compress(b"".join(windows))
    held_ready, check = Event(), Event()

    def hold_retained_arrays(arrays):
        assert all(not a.flags.writeable for a in arrays)
        held_ready.set()
        assert check.wait(5)
        return [a.tobytes() for a in arrays]

    counts = Counter()
    with (zstandard.ZstdDecompressor().stream_reader(compressed) as released,
          ThreadPoolExecutor(max_workers=1) as consumer):
        stream = ObservedStream(released, True, counts, None)
        # NumPy's derived buffers must retain the exporter independently of the temporary loans.
        arrays = [np.frombuffer(stream.read(100), dtype=np.uint8).view() for _ in range(3)]
        retained = consumer.submit(hold_retained_arrays, arrays)
        del arrays
        try:
            assert held_ready.wait(5)
            for expected in windows[3:]:
                raw = stream.read(100)
                assert type(raw) is bytes and raw == expected
        finally:
            check.set()
        assert retained.result(timeout=5) == list(windows[:3])
    assert counts["readonly_views"] == 3 and counts["owned_windows"] == 4


def test_unsupported_stream_uses_original_owned_bytes():
    counters = Counter()

    class ReadOnlyAPI:
        read = BytesIO(b"abcd").read

    stream = ObservedStream(ReadOnlyAPI(), True, counters, None)
    assert stream.read(4) == b"abcd"
    assert counters["unsupported_streams"] == counters["owned_windows"] == 1


@pytest.mark.hardware
@pytest.mark.parametrize("damaged", (None, "index", "compressed", "window", "whole"))
def test_verified_reader_checks_the_original_integrity_boundaries(tmp_path, damaged):
    assert PairedSha256(PAIRED).hardware
    writer = ShortWindowWriter(tmp_path, "signed", configuration={"window_ms": 20},
                               radio={"id": "test"}, receiver_ids=(0, 1), chunk_windows=5)
    expected = []
    for i in range(5):
        samples = (np.arange(4000, dtype="<i2") + 101*i).reshape(-1, 2, 2)
        expected.append(samples.tobytes())
        writer.append(sequence=i, target_id="one", samples=samples, acquisition={}, powers=({}, {}))
    root = writer.finish(stop_reason="max_visits")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk, = manifest["chunks"]
    if damaged in ("index", "compressed", "whole"):
        label = {"index": "index", "compressed": "compressed", "whole": "uncompressed"}[damaged]
        chunk[label+"_sha256"] = "sha256:" + "0"*64
    if damaged == "window":
        index = root / chunk["index_relative_path"]
        lines = [json.loads(row) for row in index.read_bytes().splitlines()]
        lines[2]["iq_sha256"] = "sha256:" + "0"*64
        content = b"".join(canonical_json_bytes(row)+b"\n" for row in lines)
        index.write_bytes(content)
        chunk.update(index_bytes=len(content), index_sha256=sha256_digest(content))
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    def observe(use_view):
        with decoded_route(use_view, Counter()), paired_decoded_hashes(PAIRED):
            retained = []
            try:
                for row in ShortWindowReader(root).windows():
                    assert not row.samples.flags.writeable
                    retained.append(row.samples)
            except BundleCorruptionError as error:
                return [a.tobytes() for a in retained], str(error)
        return [a.tobytes() for a in retained], None

    release, borrowed = observe(False), observe(True)
    assert borrowed == release
    if damaged is None:
        assert borrowed == (expected, None)
    else:
        assert borrowed[1] is not None
