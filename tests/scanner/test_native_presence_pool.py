"""Pure shared-memory collector tests: no radio, daemon, PostgreSQL, or archive."""

import ctypes as ct
import json
import mmap
import os
import select
import signal
import struct
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import (
    ROOT,
    NativePresence,
    Nuisance,
    Result,
    build_library,
    build_worker,
    pointer,
    write_templates,
)


class Request(ct.Structure):
    _fields_ = [
        (k, ct.c_uint64)
        for k in (
            "session",
            "generation",
            "sequence",
            "visit",
            "valid_start",
            "valid_end",
            "probe_start",
        )
    ] + [(k, ct.c_uint32) for k in ("rate_hz", "sample_count", "rx", "channel", "edge")]


class Evidence(ct.Structure):
    _fields_ = [
        ("request", Request),
        ("status", ct.c_int32),
        ("evidence", Result),
        ("nuisance", Nuisance),
    ]


class Collector(ct.Structure):
    _fields_ = [("pool", ct.c_void_p)] + [(k, ct.c_uint32) for k in ("slot", "copied", "active")]


class Stats(ct.Structure):
    _fields_ = [
        (k, ct.c_uint32)
        for k in (
            "submitted",
            "busy",
            "invalid",
            "aborted",
            "completed",
            "result_dropped",
            "pending_results",
            "occupied_slots",
        )
    ]


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    output = tmp_path_factory.mktemp("native-pool") / "pool.so"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "src/leo/scanner/native_presence/pool.c"),
            "-o",
            str(output),
        ],
        check=True,
    )
    lib = ct.CDLL(str(output))
    lib.leo_probe_pool_bytes.restype = ct.c_size_t
    lib.leo_probe_pool_init.argtypes = [ct.c_void_p, ct.c_uint64, ct.c_uint64, ct.c_uint32]
    lib.leo_probe_pool_stats.argtypes = [ct.c_void_p, ct.POINTER(Stats)]
    lib.leo_probe_begin.argtypes = [ct.POINTER(Collector), ct.c_void_p, ct.POINTER(Request)]
    lib.leo_probe_feed.argtypes = [
        ct.POINTER(Collector),
        ct.c_uint64,
        ct.c_void_p,
        ct.c_size_t,
        ct.c_size_t,
        ct.c_size_t,
    ]
    lib.leo_probe_abort.argtypes = [ct.POINTER(Collector)]
    lib.leo_probe_take.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_uint32),
        ct.POINTER(Request),
        ct.POINTER(ct.c_void_p),
    ]
    lib.leo_probe_complete.argtypes = [ct.c_void_p, ct.c_uint32, ct.POINTER(Evidence)]
    lib.leo_probe_read_result.argtypes = [ct.c_void_p, ct.POINTER(Evidence)]
    return lib


class Pool:
    def __init__(self, lib, rate=2500000, shared_fd=-1):
        self.lib, self.rate = lib, rate
        if shared_fd >= 0:
            os.ftruncate(shared_fd, lib.leo_probe_pool_bytes())
        self.mapping = mmap.mmap(shared_fd, lib.leo_probe_pool_bytes(), flags=mmap.MAP_SHARED)
        self.address = ct.addressof(ct.c_char.from_buffer(self.mapping))
        assert lib.leo_probe_pool_init(self.address, 71, 9, rate) == 0
        self.collector = Collector()

    def request(self, sequence=0, offset=0):
        start = 10**16 + 37 + sequence * self.rate
        return Request(
            71,
            9,
            sequence,
            sequence,
            start,
            start + self.rate * 120 // 1000,
            start + self.rate * offset // 1000,
            self.rate,
            self.rate // 50,
            1,
            1,
            0,
        )

    def begin(self, request):
        return self.lib.leo_probe_begin(ct.byref(self.collector), self.address, ct.byref(request))

    def feed(self, counter, samples, stride=2, rx_offset=0):
        return self.lib.leo_probe_feed(
            ct.byref(self.collector), counter, pointer(samples), len(samples), stride, rx_offset
        )

    def take(self):
        slot, request, iq = ct.c_uint32(), Request(), ct.c_void_p()
        status = self.lib.leo_probe_take(
            self.address, ct.byref(slot), ct.byref(request), ct.byref(iq)
        )
        if status == 0:
            return None
        assert status == 1
        values = np.ctypeslib.as_array(
            ct.cast(iq, ct.POINTER(ct.c_int16)), shape=(request.sample_count * 2,)
        ).reshape(-1, 2)
        return slot.value, request, values

    def complete(self, slot, request):
        result = Evidence(request=request, status=0)
        return self.lib.leo_probe_complete(self.address, slot, ct.byref(result))

    def read(self):
        result = Evidence()
        return (
            result if self.lib.leo_probe_read_result(self.address, ct.byref(result)) == 1 else None
        )

    def stats(self):
        result = Stats()
        self.lib.leo_probe_pool_stats(self.address, ct.byref(result))
        return result


@pytest.fixture
def pool(library):
    pool = Pool(library)
    yield pool
    pool.mapping.close()


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("offset", [0, 40, 100])
def test_collector_splits_blocks_excludes_guards_and_copies_one_rx(library, rate, offset):
    pool = Pool(library, rate)
    try:
        request = pool.request(offset=offset)
        guard = 17
        count = rate * 120 // 1000 + guard
        samples = np.arange(count * 4, dtype=np.int16).reshape(count, 4)
        original = samples.copy()
        assert pool.begin(request) == 1
        for start in range(0, count, 7919):
            rc = pool.feed(request.valid_start - guard + start, samples[start : start + 7919], 4, 2)
            if rc == 1:
                break
            assert rc == 0
        slot, got, iq = pool.take()
        begin = guard + rate * offset // 1000
        np.testing.assert_array_equal(iq, samples[begin : begin + rate // 50, 2:4])
        assert got.probe_start == request.probe_start and got.probe_start > 2**53
        assert pool.complete(slot, got) == 0
        result = pool.read()
        assert result.request.sequence == request.sequence
        assert pool.stats().occupied_slots == 0
        np.testing.assert_array_equal(samples, original)
    finally:
        pool.mapping.close()


def test_full_pool_never_overwrites_an_in_use_probe(pool):
    samples = np.zeros((pool.rate // 50, 2), dtype=np.int16)
    for seq in range(3):
        request = pool.request(seq)
        assert pool.begin(request) == 1
        samples[:] = seq
        assert pool.feed(request.probe_start, samples) == 1
    slot, request, values = pool.take()
    assert pool.begin(pool.request(3)) == 0
    np.testing.assert_array_equal(values, 0)
    assert pool.complete(slot, request) == 0
    assert pool.begin(pool.request(3)) == 1
    samples[:] = 3
    assert pool.feed(pool.request(3).probe_start, samples) == 1
    for seq in (1, 2, 3):
        slot, request, values = pool.take()
        assert request.sequence == seq
        np.testing.assert_array_equal(values, seq)
        assert pool.complete(slot, request) == 0
    assert pool.stats().busy == 1
    assert [pool.read().request.sequence for _ in range(4)] == list(range(4))


def test_duplicate_prefix_is_not_copied_twice_but_gaps_abort(pool):
    request = pool.request()
    samples = np.arange(request.sample_count * 2, dtype=np.int16).reshape(-1, 2)
    assert pool.begin(request) == 1
    assert pool.feed(request.probe_start, samples[:100]) == 0
    assert pool.feed(request.probe_start, samples[:50]) == 0
    assert pool.feed(request.probe_start + 50, samples[50:]) == 1
    slot, got, values = pool.take()
    np.testing.assert_array_equal(values, samples)
    assert pool.complete(slot, got) == 0
    assert pool.begin(pool.request(1)) == 1
    assert pool.feed(pool.request(1).probe_start + 1, samples) == -1
    assert pool.take() is None and pool.stats().aborted == 1
    assert pool.begin(pool.request(2)) == 1
    pool.lib.leo_probe_abort(ct.byref(pool.collector))
    assert pool.stats().occupied_slots == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("session", 72),
        ("generation", 10),
        ("rate_hz", 5000000),
        ("rx", 2),
        ("channel", 0),
        ("edge", 2),
        ("sample_count", 1),
        ("valid_end", 0),
        ("probe_start", 2**64 - 1),
    ],
)
def test_invalid_or_stale_request_cannot_enter_the_pool(pool, field, value):
    request = pool.request()
    setattr(request, field, value)
    assert pool.begin(request) == -1
    assert pool.stats().invalid == 1 and pool.stats().occupied_slots == 0


def test_result_overflow_is_observable_and_does_not_block_probe_reuse(pool):
    samples = np.zeros((pool.rate // 50, 2), dtype=np.int16)
    for sequence in range(70):
        request = pool.request(sequence)
        assert pool.begin(request) == 1
        assert pool.feed(request.probe_start, samples) == 1
        slot, got, _ = pool.take()
        assert pool.complete(slot, got) == 0
    stats = pool.stats()
    assert stats.completed == 70 and stats.result_dropped == 6
    assert stats.pending_results == 64 and stats.occupied_slots == 0
    assert [pool.read().request.sequence for _ in range(64)] == list(range(64))
    assert pool.read() is None


def test_result_with_wrong_identity_is_rejected(pool):
    request = pool.request()
    assert pool.begin(request) == 1
    assert pool.feed(request.probe_start, np.zeros((request.sample_count, 2), dtype=np.int16)) == 1
    slot, got, _ = pool.take()
    got.generation += 1
    assert pool.complete(slot, got) == -1
    got.generation -= 1
    assert pool.complete(slot, got) == 0


@pytest.fixture(scope="module")
def worker_artifacts(tmp_path_factory):
    directory = tmp_path_factory.mktemp("isolated-worker")
    policy = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = tuple(policy["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in policy["variants"][0]["defines"].items()
    )
    return build_worker(directory / "worker", cflags=flags), build_library(
        directory / "reference.so", cflags=flags
    )


@contextmanager
def running_worker(library, binary, rate, *, damage=None):
    shared = os.memfd_create("leo-test-pool")
    templates = os.memfd_create("leo-test-templates")
    notify, write = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
    writer = os.fdopen(write, "wb", buffering=0)
    unrelated = os.memfd_create("must-not-reach-detector")
    pool, process = None, None
    try:
        pool = Pool(library, rate, shared)
        n = round(rate / 750)
        payload = struct.pack("<4sII", b"LPT1", rate, n)
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                payload += np.asarray(
                    qin_edge_pilot_frame(rate, edge, symbol_roll=roll), dtype="<c16"
                ).tobytes()
        if damage == "magic":
            payload = b"BAD!" + payload[4:]
        elif damage == "truncated":
            payload = payload[:-1]
        elif damage == "rate":
            payload = payload[:4] + struct.pack("<I", 5000000) + payload[8:]
        assert os.write(templates, payload) == len(payload)
        if damage != "writable":
            readonly = os.open(f"/proc/self/fd/{templates}", os.O_RDONLY | os.O_CLOEXEC)
            os.close(templates)
            templates = readonly
        process = subprocess.Popen(
            [
                str(binary),
                str(shared),
                str(notify),
                str(templates),
                str(os.getpid()),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(shared, notify, templates, unrelated),
        )
        if damage is None:
            assert select.select([process.stdout], [], [], 5)[0], "worker startup timed out"
            assert process.stdout.readline() == b"ready\n"
            assert not Path(f"/proc/{process.pid}/fd/{unrelated}").exists()
            assert "NoNewPrivs:\t1" in Path(f"/proc/{process.pid}/status").read_text()
        yield pool, process, writer
    finally:
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            process.stdout.close()
            process.stderr.close()
        if pool:
            pool.mapping.close()
        writer.close()
        for fd in (shared, templates, notify, unrelated):
            os.close(fd)


def receive(pool, process, count):
    results, deadline = [], time.monotonic() + 5
    while len(results) < count and time.monotonic() < deadline:
        value = pool.read()
        if value is not None:
            results.append(value)
        else:
            assert process.poll() is None, "worker exited before result delivery"
            time.sleep(0.001)
    assert len(results) == count, "worker result deadline exceeded"
    return results


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_isolated_process_preserves_evidence_across_shared_memory(library, worker_artifacts, rate):
    binary, reference = worker_artifacts
    rng = np.random.default_rng(177)
    values = 50 * (rng.normal(size=rate // 50) + 1j * rng.normal(size=rate // 50))
    template = qin_edge_pilot_frame(rate, "lower")
    for frame in range(15):
        start = 47 + round(frame * rate / 750)
        stop = min(len(values), start + len(template))
        if stop > start:
            values[start:stop] += (
                1200
                * template[: stop - start]
                * np.exp(2j * np.pi * 100123 * np.arange(start, stop) / rate)
            )
    assert max(np.abs(values.real).max(), np.abs(values.imag).max()) < 32767
    iq = np.rint(np.column_stack((values.real, values.imag))).astype(np.int16)
    original = iq.copy()
    with running_worker(library, binary, rate) as (pool, process, wake):
        for edge, label in enumerate(("lower", "upper")):
            request = pool.request(edge)
            request.edge = edge
            assert pool.begin(request) == 1
            assert pool.feed(request.probe_start, iq) == 1
            wake.write(b"1")
            actual = receive(pool, process, 1)[0]
            with NativePresence(reference, rate, label) as native:
                expected = native.run(iq[:, 0].astype(float) + 1j * iq[:, 1])
            assert actual.status == 0 and actual.request.sequence == edge
            assert actual.evidence.candidate_count == expected.candidate_count
            if edge == 0:
                assert actual.evidence.candidate_count == 1
                assert actual.evidence.candidates[0].fractional_complete
                assert actual.evidence.candidates[0].margin > 0.1
            for a, b in zip(
                actual.evidence.candidates[: expected.candidate_count],
                expected.candidates[: expected.candidate_count],
                strict=True,
            ):
                assert a.epoch == b.epoch and a.fractional_complete == b.fractional_complete
                assert a.exact_score == pytest.approx(b.exact_score, rel=1e-9, abs=1e-10)
                assert a.tracking_cfo_hz == pytest.approx(b.tracking_cfo_hz, abs=0.001)
        wake.close()
        assert process.wait(timeout=3) == 0
    np.testing.assert_array_equal(iq, original)


def test_stalled_worker_does_not_block_submission_and_eof_drains(library, worker_artifacts):
    with running_worker(library, worker_artifacts[0], 2500000) as (pool, process, wake):
        process.send_signal(signal.SIGSTOP)
        samples = np.zeros((pool.rate // 50, 2), dtype=np.int16)
        started = time.monotonic()
        for sequence in range(3):
            request = pool.request(sequence)
            assert pool.begin(request) == 1
            assert pool.feed(request.probe_start, samples) == 1
        assert pool.begin(pool.request(3)) == 0
        assert time.monotonic() - started < 1
        assert pool.stats().busy == 1 and pool.stats().occupied_slots == 3
        wake.write(b"1")
        wake.close()
        process.send_signal(signal.SIGCONT)
        assert process.wait(timeout=3) == 0
        assert [pool.read().request.sequence for _ in range(3)] == [0, 1, 2]
        assert pool.stats().completed == 3


def test_worker_crash_never_creates_a_negative_result(library, worker_artifacts):
    with running_worker(library, worker_artifacts[0], 2500000) as (pool, process, _wake):
        process.kill()
        process.wait(timeout=3)
        assert pool.read() is None
        samples = np.zeros((pool.rate // 50, 2), dtype=np.int16)
        for sequence in range(3):
            request = pool.request(sequence)
            assert pool.begin(request) == 1
            assert pool.feed(request.probe_start, samples) == 1
        assert pool.begin(pool.request(3)) == 0
        assert pool.stats().completed == 0 and pool.read() is None


@pytest.mark.parametrize("damage", ["magic", "truncated", "rate", "writable"])
def test_worker_rejects_invalid_or_writable_templates(library, worker_artifacts, damage):
    with running_worker(library, worker_artifacts[0], 2500000, damage=damage) as (
        pool,
        process,
        _wake,
    ):
        assert process.wait(timeout=5) == 2
        assert process.stdout.read() == b""
        assert pool.read() is None and pool.stats().completed == 0


def test_partial_probe_at_eof_is_not_reported_as_analyzed(library, worker_artifacts):
    with running_worker(library, worker_artifacts[0], 2500000) as (pool, process, wake):
        request = pool.request(0)
        assert pool.begin(request) == 1
        assert pool.feed(request.probe_start, np.zeros((100, 2), dtype=np.int16)) == 0
        wake.close()
        assert process.wait(timeout=3) == 2
        assert pool.read() is None and pool.stats().completed == 0
        pool.lib.leo_probe_abort(ct.byref(pool.collector))
        assert pool.stats().occupied_slots == 0


@pytest.fixture(scope="module")
def smoke_parent(tmp_path_factory):
    binary = tmp_path_factory.mktemp("native-worker-parent") / "smoke"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/fixtures/scanner_presence_worker_smoke.c"),
            str(ROOT / "src/leo/scanner/native_presence/pool.c"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    return binary


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_native_parent_worker_smoke(smoke_parent, worker_artifacts, tmp_path, rate):
    templates = tmp_path / "templates.bin"
    write_templates(templates, rate)
    result = subprocess.run(
        [str(smoke_parent), str(worker_artifacts[0]), str(templates)],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    receipt = json.loads(result.stdout)
    assert receipt["schema"] == "native-worker-ipc-smoke-v1"
    assert receipt["rate_hz"] == rate
    assert receipt["submitted"] == receipt["completed"] == 10
    assert receipt["dropped"] == 0
    assert 1200000 < receipt["pool_bytes"] < 1300000


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_native_parent_paces_and_preserves_saved_counter(
    smoke_parent, worker_artifacts, tmp_path, rate
):
    from tools.qualify_presence_worker import verify

    templates = tmp_path / "templates.bin"
    write_templates(templates, rate)
    pack = tmp_path / "probes.pack"
    counter = 10**16 + 27
    pack.write_bytes(
        struct.pack("<4sIIQQII", b"LPP1", rate, 1, counter, 83, 0, 4) + bytes(rate // 50 * 4)
    )
    result = subprocess.run(
        [str(smoke_parent), str(worker_artifacts[0]), str(templates), str(pack), "252"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    with NativePresence(worker_artifacts[1], rate, "lower") as reference:
        expected = reference.run(np.zeros(rate // 50))
        assert expected.candidate_count == 0
        nuisance = reference.nuisance()
    manifest = {
        "schema": "org.leo.research.presence-worker-pack/v1",
        "rate_hz": rate,
        "records": [
            {
                "device_counter": str(counter),
                "edge": "lower",
                "provenance": {"channel": 4, "visit": 83},
                "expected": {"candidates": [], "nuisance": nuisance},
            }
        ],
    }
    checked = verify(result.stdout, manifest, 252)
    assert checked["executions"] == 2 and checked["all_outputs_match_desktop"]
    for bad in (
        result.stdout.replace(str(counter), str(counter + 1)),
        result.stdout.replace('"skipped":0', '"skipped":1'),
        result.stdout[: result.stdout.rfind('{"schema":"native-worker-paced-summary')],
    ):
        with pytest.raises(ValueError):
            verify(bad, manifest, 252)


def test_worker_exits_when_native_parent_dies(smoke_parent, worker_artifacts, tmp_path):
    templates = tmp_path / "templates.bin"
    write_templates(templates, 2500000)
    pack = tmp_path / "probes.pack"
    pack.write_bytes(
        struct.pack("<4sIIQQII", b"LPP1", 2500000, 1, 10**16 + 21, 8, 0, 1) + bytes(50000 * 4)
    )
    parent = subprocess.Popen(
        [str(smoke_parent), str(worker_artifacts[0]), str(templates), str(pack), "10000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    child_handle = None
    try:
        children = Path(f"/proc/{parent.pid}/task/{parent.pid}/children")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            assert parent.poll() is None
            for value in children.read_text().split():
                pid = int(value)
                if Path(f"/proc/{pid}/exe").resolve() == worker_artifacts[0].resolve():
                    child_handle = os.pidfd_open(pid)
                    break
            if child_handle is not None:
                break
            time.sleep(0.001)
        assert child_handle is not None, "isolated child did not start"
        parent.kill()
        parent.wait(timeout=3)
        assert select.select([child_handle], [], [], 3)[0], "worker outlived its parent"
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=3)
        parent.stderr.close()
        if child_handle is not None:
            if not select.select([child_handle], [], [], 0)[0]:
                signal.pidfd_send_signal(child_handle, signal.SIGKILL)
            os.close(child_handle)
