from hashlib import sha256
import json

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3 import incremental_ingress as trial


def test_delivery_uses_absolute_ready_times_and_counts_only_requested_bytes(monkeypatch):
    tick = [0]
    monkeypatch.setattr(trial, "perf_counter_ns", lambda: tick[0])
    monkeypatch.setattr(trial, "sleep", lambda seconds: tick.__setitem__(0, tick[0]+round(seconds*1e9)))
    monkeypatch.setattr(trial, "BLOCK", 4)
    stream = trial.Delivery(6, [100, 200])
    assert stream.transfer(4, lambda: b"aaaa") == b"aaaa"
    assert stream.sleep_ns == 100
    tick[0] += 120
    assert stream.transfer(2, lambda: b"bb") == b"bb"
    assert stream.sleep_ns == 100 and stream.last_byte == 220
    with pytest.raises(ValueError, match="exceeded its exact byte boundary"):
        stream.transfer(1, lambda: b"x")


def test_actual_delivery_has_no_wait_schedule(monkeypatch):
    monkeypatch.setattr(trial, "sleep", lambda *_: pytest.fail("unpaced read tried to sleep"))
    stream = trial.Delivery(6, None)
    assert stream.transfer(4, lambda: b"0123") == b"0123"
    assert stream.transfer(2, lambda: b"45") == b"45"
    assert stream.offset == 6 and stream.positive_reads == 2 and stream.sleep_ns == 0
    assert not stream.paced_chunks


def test_feed_requires_complete_length_and_matches_hash_before_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(trial, "BLOCK", 4)
    contents = b"012345"
    path = tmp_path / "member.zst"
    path.write_bytes(contents)
    pin = sha256(contents).hexdigest()
    for corrupt in (False, True):
        with path.open("rb") as source:
            feed = trial.CompressedFeed(source.fileno(), trial.Delivery(6, [0, 0], corrupt=corrupt), pin)
            retained = feed.read(4)
            assert retained == b"0123" and not feed.finished
            with pytest.raises(BundleCorruptionError, match="final authority"):
                feed.finish()
            tail = feed.read(4)
            assert tail == (b"44" if corrupt else b"45") and retained == b"0123"
            if corrupt:
                with pytest.raises(BundleCorruptionError, match="final authority"):
                    feed.finish()
                assert not feed.finished
            else:
                feed.finish()
                assert feed.finished
    assert path.read_bytes() == contents


@pytest.mark.parametrize("failure", (None, "decoded_window", "decoded_member", "late_checksum"))
def test_original_decoded_checks_and_late_failure_precede_packet_return(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(trial, "BLOCK", 128)
    writer = ShortWindowWriter(tmp_path, "signed", configuration={"window_ms": 20},
                               radio={"id": "synthetic"}, receiver_ids=(0, 1), chunk_windows=4)
    rng = np.random.default_rng(689)
    arrays = [rng.integers(-30000, 30000, size=(320, 2, 2), dtype="<i2") for _ in range(4)]
    for i, array in enumerate(arrays):
        writer.append(sequence=i, target_id="t", samples=array, acquisition={}, powers=({}, {}))
    directory = writer.finish(stop_reason="max_visits")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    member = manifest["chunks"][0]
    if failure == "decoded_window":
        index = directory / member["index_relative_path"]
        rows = [json.loads(row) for row in index.read_bytes().splitlines()]
        rows[1]["iq_sha256"] = "sha256:" + "0"*64
        data = b"".join(canonical_json_bytes(row)+b"\n" for row in rows)
        index.write_bytes(data)
        member.update(index_bytes=len(data), index_sha256="sha256:"+sha256(data).hexdigest())
    if failure == "decoded_member":
        member["uncompressed_sha256"] = "sha256:"+"0"*64
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    reader = ShortWindowReader(directory)
    size = member["compressed_bytes"]
    delivery = trial.Delivery(size, None, corrupt=failure == "late_checksum")
    windows = []
    seal = tmp_path / "only-if-complete"

    def acquire():
        with trial.provisional_decoder(directory / member["payload_relative_path"], member, delivery):
            for item in reader.windows():
                windows.append(item.samples)
        seal.write_text("complete")

    if failure:
        with pytest.raises(BundleCorruptionError):
            acquire()
        assert not seal.exists() and len(windows) >= 1
    else:
        acquire()
        assert seal.exists() and len(windows) == len(arrays)
    for observed, original in zip(windows, arrays):
        assert not observed.flags.writeable
        np.testing.assert_array_equal(observed, original)
