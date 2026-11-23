from collections import Counter
from contextlib import closing, contextmanager
from functools import partial
import json

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.fused_block_input import Native, fused_windows
from reports.ALGO08.v3.fused_block_input_trial import build
from reports.ALGO08.v3.sparse_cold_input import PAYLOAD
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes


pytestmark = pytest.mark.hardware  # Installed Gauss libzstd and packed SHA library.


@pytest.fixture(scope="module")
def decoder(tmp_path_factory):
    library = tmp_path_factory.mktemp("fused-native") / "fused.so"
    build(library)
    return Native(library)


@pytest.fixture
def sealed(tmp_path):
    writer = ShortWindowWriter(tmp_path, "fused", configuration={"window_ms": 20},
                               radio={"id": "fixture"}, receiver_ids=(0, 1), chunk_windows=2)
    for i in range(4):
        writer.append(sequence=i, target_id="pilot", samples=np.full((500, 2, 2), i*5, dtype="<i2"),
                      acquisition={}, powers=({}, {}))
    return writer.finish(stop_reason="max_visits")


@contextmanager
def observed(path, install):
    with install(PAYLOAD / "paired-sha256.so"):
        rows = []
        try:
            for window in ShortWindowReader(path).windows(stop_sequence=3):
                # Keep the actual NumPy views across later decoding and context exit.
                rows.append((window.index, window.samples))
        except BundleCorruptionError as error:
            yield rows, str(error)
        else:
            yield rows, None


@pytest.mark.parametrize("damage", (None, "compressed", "index", "window", "member", "extra_frame"))
def test_both_digest_failures_keep_original_acceptance_and_window_order(sealed, decoder, damage):
    manifest_path = sealed / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][-1]
    data = sealed / chunk["payload_relative_path"]
    if damage == "compressed":
        data.write_bytes(data.read_bytes()[:-1])
    elif damage == "extra_frame":
        import zstandard

        appended = data.read_bytes() + zstandard.ZstdCompressor().compress(b"")
        data.write_bytes(appended)
        chunk.update(compressed_bytes=len(appended), compressed_sha256=sha256_digest(appended))
    elif damage in ("index", "window"):
        index = sealed / chunk["index_relative_path"]
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[-1]["iq_sha256"] = "sha256:" + "0"*64
        authored = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index.write_bytes(authored)
        if damage == "window":
            chunk["index_sha256"] = sha256_digest(authored)
    elif damage == "member":
        chunk["uncompressed_sha256"] = "sha256:" + "0"*64
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    stats = Counter()
    with observed(sealed, paired_decoded_hashes) as original:
        expected, original_error = original
    with observed(sealed, partial(fused_windows, decoder, stats=stats)) as fused:
        actual, fused_error = fused
    assert fused_error == original_error
    assert (fused_error is not None) == (damage in {"compressed", "index", "window", "member"})
    assert stats["fallbacks"] == (damage == "extra_frame")
    for (exp_row, exp), (act_row, act) in zip(expected, actual, strict=True):
        assert exp_row == act_row and not act.flags.writeable
        np.testing.assert_array_equal(exp, act)


def test_partial_reader_delivers_first_window_before_finishing_the_member(sealed, decoder):
    stats = Counter()
    with fused_windows(decoder, PAYLOAD / "paired-sha256.so", stats):
        with closing(ShortWindowReader(sealed).windows(stop_sequence=2)) as windows:
            first = next(windows)
            assert stats["fused_frames"] == 1 and "decoded_member" not in stats
            assert len(list(windows)) == 1
    assert stats["windows"] == 2
    assert stats["decoded_member"] == ShortWindowReader(sealed).manifest.chunks[0].uncompressed_sha256
    assert np.count_nonzero(first.samples) == 0
