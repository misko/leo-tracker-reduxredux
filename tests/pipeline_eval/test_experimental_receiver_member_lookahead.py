import json
import os
from collections import Counter
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError, PathConfinementError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.scanner import ScannerIqStore
from leo.storage.short_window import ShortWindowWriter
from tools.pipeline_eval.variants.experimental import receiver_ingress, receiver_member_prefetch
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_member_lookahead import (
    PREFIX_BYTES, advise_prefix, compressed_member_lookahead,
)
from tools.pipeline_eval.variants.experimental.receiver_member_prefetch import compressed_member_prefetch


@pytest.fixture
def sealed(tmp_path):
    target = dict(target_id="t", edge="lower", channel=1, rf_center_hz=2_000_000, lnb_lo_hz=0)
    writer = ShortWindowWriter(
        tmp_path, "test-lookahead", configuration=dict(sample_rate_hz=2_500_000, targets=[target]),
        radio={"serial": "synthetic"}, receiver_ids=(0, 1), chunk_windows=2,
    )
    samples = np.arange(800, dtype="<i2").reshape(200, 2, 2)
    for i in range(8):
        writer.append(sequence=i, target_id="t", acquisition={"sample_start": i * 200},
                      samples=(i + samples).astype("<i2"), powers=({}, {}))
    return writer.finish(stop_reason="max_visits")


def source(path, **scope):
    header = sha256_digest((path / "manifest.json").read_bytes())
    return FastSegmentSource(dict(path=str(path), manifest_digest=header), **scope)


def payloads(path):
    return [path / chunk.payload_relative_path for chunk in source(path).reader.manifest.chunks]


def snapshot(window):
    assert not window.samples.flags.writeable
    return window.sequence, window.iq_sha256, window.acquisition, window.target, window.samples.tobytes()


def install_advice(monkeypatch, function):
    monkeypatch.setattr(os, "posix_fadvise", function, raising=False)
    monkeypatch.setattr(os, "POSIX_FADV_WILLNEED", 3, raising=False)


def test_hints_follow_the_first_visible_window_and_bounded_scope(sealed, monkeypatch):
    members = payloads(sealed)
    identities = {(p.stat().st_dev, p.stat().st_ino): i for i, p in enumerate(members)}
    hints = []

    def advice(fd, offset, length, mode):
        info = os.fstat(fd)
        hints.append((identities[info.st_dev, info.st_ino], offset, length, mode))

    install_advice(monkeypatch, advice)
    scope = dict(start_sequence=1, stop_sequence=5)
    baseline = [snapshot(w) for w in source(sealed, **scope).windows()]
    with compressed_input_buffer(), compressed_member_lookahead() as stats:
        windows = source(sealed, **scope).windows()
        observed = [snapshot(next(windows))]
        assert hints == [(1, 0, members[1].stat().st_size, 3)]
        observed.extend(map(snapshot, windows))
        # A separate restricted segment with just one touched chunk submits no hint.
        assert len(list(source(sealed, start_sequence=6, stop_sequence=8).windows())) == 2
    assert observed == baseline
    assert hints[-1] == (2, 0, members[2].stat().st_size, 3)
    assert stats.attempts == stats.submitted == len(hints) == 2
    assert stats.submitted_bytes == sum(row[2] for row in hints)
    assert stats.wall_ns > 0 and stats.cpu_ns > 0


def test_advice_prefix_is_capped_even_for_a_larger_file(tmp_path):
    file = tmp_path / "test.zst"
    size = PREFIX_BYTES + 4096
    with file.open("wb") as stream:
        stream.truncate(size)
    chunk = SimpleNamespace(compressed_bytes=size, payload_relative_path=file.name)
    calls = []
    result = advise_prefix(tmp_path, chunk, lambda fd, *args: calls.append(args), 3)
    assert result == PREFIX_BYTES and calls == [(0, PREFIX_BYTES, 3)]


@pytest.mark.parametrize("forecast", [compressed_member_lookahead, compressed_member_prefetch])
@pytest.mark.parametrize("damage", ["compressed", "index", "window", "symlink", "hardlink", "decoded"])
def test_verification_exposes_the_same_rows_and_first_error(sealed, tmp_path, monkeypatch, damage, forecast):
    manifest_path = sealed / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    chunk = document["chunks"][1]
    payload = sealed / chunk["payload_relative_path"]
    if damage in ("symlink", "hardlink"):
        substitute = tmp_path / "substitute.zst"
        payload.rename(substitute)
        (payload.symlink_to if damage == "symlink" else payload.hardlink_to)(substitute)
    elif damage == "decoded":
        chunk["uncompressed_sha256"] = "sha256:" + "0" * 64
        manifest_path.write_bytes(canonical_json_bytes(document))
    elif damage == "window":
        index = sealed / chunk["index_relative_path"]
        rows = [json.loads(line) for line in index.read_bytes().splitlines()]
        rows[0]["iq_sha256"] = "sha256:" + "0" * 64
        content = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        index.write_bytes(content)
        chunk.update(index_sha256=sha256_digest(content), index_bytes=len(content))
        manifest_path.write_bytes(canonical_json_bytes(document))
    else:
        member = payload if damage == "compressed" else sealed / chunk["index_relative_path"]
        invalid = bytearray(member.read_bytes())
        invalid[-1] ^= 1
        member.write_bytes(invalid)
    calls = []
    install_advice(monkeypatch, lambda *_: calls.append(True))

    def until_failure():
        visible = []
        with pytest.raises((BundleCorruptionError, PathConfinementError)) as error:
            for row in source(sealed).windows():
                visible.append(snapshot(row))
        return visible, type(error.value), str(error.value)

    with compressed_input_buffer():
        before = until_failure()
        with forecast():
            after = until_failure()
    assert before == after
    assert [row[0] for row in after[0]] == list(range(4 if damage == "decoded" else 2))
    if damage in ("symlink", "hardlink"):
        assert not calls


def test_advice_error_does_not_advance_or_abort_the_reader(sealed, monkeypatch):
    def failure(*_):
        raise OSError("advice unavailable")

    install_advice(monkeypatch, failure)
    original = FastSegmentSource.windows
    with compressed_member_lookahead() as stats:
        assert [w.sequence for w in source(sealed).windows()] == list(range(8))
    assert stats.attempts == 3 and stats.submitted == stats.submitted_bytes == 0
    assert FastSegmentSource.windows is original


def test_prefetch_overlaps_processing_and_reads_each_touched_member_once(sealed, monkeypatch):
    scope = dict(start_sequence=1, stop_sequence=5)
    expected = [snapshot(window) for window in source(sealed, **scope).windows()]
    members = payloads(sealed)
    inodes = [path.stat().st_ino for path in members]
    entered, finish = Event(), Event()
    counts = Counter()
    actual_read = receiver_ingress.read_regular_descriptor

    def read(fd, size, **options):
        inode = os.fstat(fd).st_ino
        counts[inode] += 1
        if inode == inodes[1]:
            entered.set()
            assert finish.wait(5)
        return actual_read(fd, size, **options)

    monkeypatch.setattr(receiver_member_prefetch, "read_regular_descriptor", read)
    monkeypatch.setattr(receiver_ingress, "read_regular_descriptor", read)
    original_read = ScannerIqStore._read_regular
    original_windows = FastSegmentSource.windows
    with compressed_input_buffer(), compressed_member_prefetch() as stats:
        windows = source(sealed, **scope).windows()
        observed = [snapshot(next(windows))]
        try:
            assert entered.wait(5)
            assert stats.submitted == 1 and stats.hits == 0
        finally:
            finish.set()
        observed.extend(map(snapshot, windows))

    assert observed == expected
    assert counts == Counter(inodes[:3])
    assert stats.submitted == stats.hits == 2 and stats.fallback == 0
    assert stats.submitted_bytes == stats.hit_bytes == sum(path.stat().st_size for path in members[1:3])
    assert stats.worker_cpu_ns > 0 and stats.demand_wait_ns > 0
    assert ScannerIqStore._read_regular is original_read
    assert FastSegmentSource.windows is original_windows


def test_prefetch_rechecks_member_at_demand_and_falls_back_on_replacement(sealed, monkeypatch):
    expected = [snapshot(window) for window in source(sealed).windows()]
    member = payloads(sealed)[1]
    ready = Event()
    actual_prefetch = receiver_member_prefetch.prefetch_member

    def complete(root, name, size, stats):
        result = actual_prefetch(root, name, size, stats)
        if (root / name) == member:
            assert result is not None
            ready.set()
        return result

    monkeypatch.setattr(receiver_member_prefetch, "prefetch_member", complete)
    with compressed_input_buffer(), compressed_member_prefetch() as stats:
        windows = source(sealed).windows()
        visible = [snapshot(next(windows))]
        assert ready.wait(5)
        replaced = member.with_name("replacement.zst")
        replaced.write_bytes(member.read_bytes())
        replaced.replace(member)
        visible.extend(map(snapshot, windows))

    assert visible == expected
    assert stats.submitted == 3 and stats.hits == 2 and stats.fallback == 1


def test_prefetch_uses_the_normal_reader_above_its_allocation_bound(sealed, monkeypatch):
    monkeypatch.setattr(receiver_member_prefetch, "MAX_PREFETCH_BYTES", 1)
    with compressed_input_buffer(), compressed_member_prefetch() as stats:
        assert [window.sequence for window in source(sealed).windows()] == list(range(8))
    assert stats.submitted == stats.hits == stats.fallback == 0
