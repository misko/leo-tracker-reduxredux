import json
from contextlib import ExitStack
from ctypes.util import find_library

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.variants.experimental.receiver_arena_ingress import rotating_arenas
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_window_ingress import WindowStreams
from tools.pipeline_eval.variants.experimental.receiver_zstd_arena import runtime


@pytest.fixture(scope="module")
def library():
    name = find_library("zstd")
    if name is None:
        pytest.skip("The optional arena reader requires the system libzstd runtime")
    return runtime(name)


@pytest.fixture
def sealed(tmp_path):
    writer = ShortWindowWriter(
        tmp_path,
        "sealed",
        configuration={"window_ms": 20},
        radio={"id": "synthetic"},
        receiver_ids=(0, 1),
        chunk_windows=2,
    )
    for sequence in range(10):
        values = np.full((400, 2, 2), sequence, dtype="<i2")
        writer.append(
            sequence=sequence, target_id="t1", samples=values, acquisition={}, powers=({}, {})
        )
    return writer.finish(stop_reason="max_visits")


def test_rotates_released_arenas_and_exhaustion_keeps_external_slices_immutable(sealed, library):
    with rotating_arenas(library) as arenas, compressed_input_buffer(), arenas.install(None):
        windows = ShortWindowReader(sealed).windows()
        first = next(windows).samples[::2]
        next(windows)
        second = next(windows).samples.reshape(-1)
        next(windows)
        third = next(windows).samples
        assert arenas.counts == {"allocations": 2, "decoded": 2, "borrowed_fallback": 1}
        assert (
            not first.flags.writeable and not second.flags.writeable and not third.flags.writeable
        )
        with pytest.raises(ValueError, match="WRITEABLE"):
            first.setflags(write=True)
        address = first.ctypes.data
        del first
        assert next(windows).index.sequence == 5
        fourth = next(windows).samples
        assert fourth.ctypes.data == address and np.all(fourth == 6)
        assert np.all(second == 2) and np.all(third == 4)
        assert arenas.counts["reuses"] == 1
        windows.close()
    assert np.all(second == 2) and np.all(third == 4) and np.all(fourth == 6)


def _observed(path, stop):
    seen = []
    try:
        for window in ShortWindowReader(path).windows(start_sequence=2, stop_sequence=stop):
            seen.append((window.index, window.samples.tobytes()))
    except BundleCorruptionError as error:
        return seen, str(error), type(error.__cause__)
    return seen, None, None


@pytest.mark.parametrize("stop", [3, 4])
@pytest.mark.parametrize("strategy", ["arena", "persistent", "window"])
@pytest.mark.parametrize(
    "damage", ["member", "index", "window", "decoded", "truncated", "extra-frame"]
)
def test_partial_and_full_scopes_keep_existing_validation_order_on_bad_chunks(
    sealed,
    library,
    stop,
    damage,
    strategy,
):
    manifest_path = sealed / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][1]
    member_path = sealed / chunk["payload_relative_path"]
    payload = member_path.read_bytes()
    if damage == "member":
        member_path.write_bytes(payload[:-1])
    elif damage in ("window", "index"):
        index_path = sealed / chunk["index_relative_path"]
        rows = [json.loads(row) for row in index_path.read_bytes().splitlines()]
        rows[-1]["iq_sha256"] = "sha256:" + "0" * 64
        data = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index_path.write_bytes(data)
        if damage == "window":
            chunk["index_sha256"] = sha256_digest(data)
    elif damage == "decoded":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
    else:
        payload = (
            payload[:-1] if damage == "truncated" else payload + zstd.ZstdCompressor().compress(b"")
        )
        member_path.write_bytes(payload)
        chunk["compressed_bytes"] = len(payload)
        chunk["compressed_sha256"] = sha256_digest(payload)
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with compressed_input_buffer():
        expected = _observed(sealed, stop)
        with ExitStack() as stack:
            decoder = (
                stack.enter_context(rotating_arenas(library))
                if strategy == "arena"
                else WindowStreams(loan_buffers=strategy == "window")
            )
            stack.enter_context(decoder.install(None))
            assert _observed(sealed, stop) == expected
        if strategy != "arena":
            return
        if damage in ("truncated", "extra-frame"):
            assert decoder.counts["frame_fallback"] == 1
        elif damage in ("window", "decoded"):
            assert decoder.counts["decoded"] == 1


def test_missing_decoder_uses_owned_canonical_windows(sealed):
    expected = _observed(sealed, 5)
    with rotating_arenas(None) as arenas, arenas.install(None):
        assert _observed(sealed, 5) == expected
    assert arenas.counts == {"unsupported": 2}


def test_window_slots_release_only_after_every_array_view_is_gone(sealed):
    decoder = WindowStreams(loan_buffers=True)
    with decoder.install(None):
        windows = ShortWindowReader(sealed).windows()
        first = next(windows).samples[::2]
        second = next(windows).samples.reshape(-1)
        third = next(windows).samples
        assert np.all(first == 0) and np.all(second == 1) and np.all(third == 2)
        assert (
            not first.flags.writeable and not second.flags.writeable and not third.flags.writeable
        )
        assert decoder.counts["owned_windows"] == 1
        address = first.ctypes.data
        del first
        fourth = next(windows).samples
        assert fourth.ctypes.data == address and np.all(fourth == 3)
        assert decoder.counts["reuses"] == 1
        windows.close()
    assert np.all(second == 1) and np.all(third == 2) and np.all(fourth == 3)


def test_persistent_decoder_falls_back_for_overlapping_streams_and_resumes_after_close(sealed):
    decoder = WindowStreams(loan_buffers=True)
    with decoder.install(None):
        reader = ShortWindowReader(sealed)
        with ExitStack() as stack:
            outer = reader.windows(start_sequence=1, stop_sequence=5)
            stack.callback(outer.close)
            assert next(outer).index.sequence == 1
            nested = reader.windows(start_sequence=2, stop_sequence=3)
            assert [w.index.sequence for w in nested] == [2]
            assert [w.index.sequence for w in outer] == [2, 3, 4]
        assert [w.index.sequence for w in reader.windows(start_sequence=7, stop_sequence=10)] == [
            7,
            8,
            9,
        ]
    assert decoder.counts["nested_streams"] == 1
    assert decoder.counts["streams"] == 5
