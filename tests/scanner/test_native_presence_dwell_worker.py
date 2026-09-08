"""Full-dwell IPC tests; no hardware, network, archive or database dependency."""

import ctypes as ct
import json
import signal
import struct
import subprocess

import numpy as np
import pytest

from tests.scanner.test_glrt_frame_result import adapter as adapter
from tests.scanner.test_glrt_frame_result import convert
from tests.scanner.test_native_presence_pool import (
    Pool,
    receive,
    running_worker,
)
from tests.scanner.test_native_presence_pool import (
    library as library,
)
from tests.scanner.test_native_presence_pool import (
    smoke_parent as smoke_parent,
)
from tools.native_presence import ROOT, build_dwell_presence, build_worker, write_templates
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_presence_dwell_controls import generate


@pytest.fixture(scope="module", params=["normalized", "amplitude", "diverse", "amplitude-diverse"])
def artifacts(tmp_path_factory, request):
    root = tmp_path_factory.mktemp(f"dwell-worker-{request.param}")
    config = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    flags = (
        tuple(config["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in config["variants"][0]["defines"].items())
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1")
    )
    if "amplitude" in request.param:
        flags += ("-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1",)
    if "diverse" in request.param:
        flags += ("-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1",)
    return build_worker(root / "worker", cflags=flags), build_dwell_presence(
        root / "dwell.so", cflags=flags
    )


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("rx", [0, 1])
def test_complete_dwell_split_strided_copy_and_fixed_receiver(library, rate, rx):
    pool = Pool(library, rate, dwell=True, rx=rx)
    try:
        request = pool.request()
        assert 7200000 < pool.bytes < 7500000
        count = request.sample_count
        guard = 19
        samples = np.arange((count + 2 * guard) * 4, dtype=np.int16).reshape(-1, 4)
        original = samples.copy()
        assert pool.begin(request) == 1
        for start in range(0, len(samples), 8191):
            rc = pool.feed(
                request.valid_start - guard + start, samples[start : start + 8191], 4, 2 * rx
            )
            if rc == 1:
                break
            assert rc == 0
        slot, got, values = pool.take()
        np.testing.assert_array_equal(values, samples[guard : guard + count, 2 * rx : 2 * rx + 2])
        assert got.probe_start == request.valid_start > 2**53
        assert got.sample_count == 6 * rate // 50
        assert pool.complete(slot, got) == 0
        assert pool.read().request.rx == rx
        np.testing.assert_array_equal(samples, original)
        for field, value in (
            ("rx", 1 - rx),
            ("sample_count", rate // 50),
            ("probe_start", pool.request(1).valid_start + 1),
        ):
            invalid = pool.request(1)
            setattr(invalid, field, value)
            assert pool.begin(invalid) == -1
        assert pool.stats().occupied_slots == 0
    finally:
        pool.mapping.close()


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_full_dwell_pool_retains_working_slot_and_counts_result_overflow(library, rate):
    pool = Pool(library, rate, dwell=True)
    try:
        for sequence in range(3):
            request = pool.request(sequence)
            samples = np.full((request.sample_count, 2), sequence, dtype=np.int16)
            assert pool.begin(request) == 1
            assert pool.feed(request.valid_start, samples) == 1
        slot, first, values = pool.take()
        assert pool.begin(pool.request(3)) == 0
        np.testing.assert_array_equal(values, 0)
        assert pool.complete(slot, first) == 0
        for sequence in (1, 2):
            slot, request, values = pool.take()
            np.testing.assert_array_equal(values, sequence)
            assert pool.complete(slot, request) == 0
        for sequence in range(3, 70):
            request = pool.request(sequence)
            assert pool.begin(request) == 1
            assert pool.feed(request.valid_start, samples) == 1
            slot, got, _ = pool.take()
            assert pool.complete(slot, got) == 0
        assert pool.stats().result_dropped == 6
        assert pool.stats().occupied_slots == 0
        assert [pool.read().request.sequence for _ in range(64)] == list(range(64))
    finally:
        pool.mapping.close()


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("window", [0, 3, 5])
def test_worker_full_dwell_matches_direct_fractional_execution(
    library, artifacts, adapter, rate, window
):
    binary, reference = artifacts
    with running_worker(library, binary, rate, dwell=True) as (pool, process, wake):
        for edge, label in enumerate(("lower", "upper")):
            iq, _ = generate(rate, label, 1901, "pilot_plus_tone", window)
            before = iq.copy()
            request = pool.request(edge)
            request.edge = edge
            assert pool.begin(request) == 1
            middle = len(iq) // 2
            assert pool.feed(request.valid_start, iq[:middle]) == 0
            assert pool.stats().occupied_slots == 1 and pool.stats().completed == edge
            assert pool.feed(request.valid_start + middle, iq[middle:]) == 1
            wake.write(b"1")
            result = receive(pool, process, 1)[0]
            with NativeDwell(reference, rate, label, 512) as native:
                expected = native.run(iq, maximum=1, seeded=False)
                expected_screens = unpack(native.screens())
            assert result.status == 0
            assert result.dwell.search_window_mask == 63
            assert result.dwell.confirmation_window_mask == 1 << window
            assert result.dwell.rank.order[0] == window
            assert unpack(result.dwell.screens) == expected_screens
            assert result.dwell.total_cpu_ms >= result.evidence.total_cpu_ms
            assert result.dwell.total_wall_ms >= result.evidence.total_wall_ms
            record = convert(adapter, result)
            assert record.verdict == 0 and record.reason == 5
            assert record.confirmation_start == request.valid_start + window * rate // 50
            assert (
                record.epoch_sample_counter
                == record.confirmation_start + result.evidence.candidates[0].epoch
            )
            assert (
                record.fractional_offset_samples
                == result.evidence.candidates[0].fractional_offset_samples
            )
            a, b = unpack(result.evidence), unpack(expected.confirmations[0])
            assert a["candidate_count"] == b["candidate_count"] == 1
            for field in (
                "epoch",
                "fractional_complete",
                "fractional_offset_samples",
                "tracking_cfo_hz",
                "exact_score",
                "control_score",
                "margin",
                "acquired_cfo_hz",
            ):
                assert a["candidates"][0][field] == pytest.approx(
                    b["candidates"][0][field], rel=1e-9, abs=1e-10
                )
            np.testing.assert_array_equal(iq, before)
        wake.close()
        assert process.wait(timeout=3) == 0
        assert pool.stats().completed == 2 and pool.stats().occupied_slots == 0


def test_full_dwell_eof_drains_queued_work_without_new_input(library, artifacts):
    with running_worker(library, artifacts[0], 2500000, dwell=True) as (pool, process, wake):
        process.send_signal(signal.SIGSTOP)
        for seq in range(3):
            request = pool.request(seq)
            assert pool.begin(request) == 1
            assert (
                pool.feed(request.valid_start, np.zeros((request.sample_count, 2), dtype=np.int16))
                == 1
            )
        assert pool.begin(pool.request(3)) == 0
        wake.write(b"1")
        wake.close()
        process.send_signal(signal.SIGCONT)
        assert process.wait(timeout=5) == 0
        results = [pool.read() for _ in range(3)]
        assert [r.request.sequence for r in results] == [0, 1, 2]
        assert all(r.status == 0 and r.dwell.search_window_mask == 63 for r in results)
        assert pool.stats().occupied_slots == 0


def test_full_dwell_gap_or_partial_eof_is_not_a_negative_result(library, artifacts):
    with running_worker(library, artifacts[0], 2500000, dwell=True) as (pool, process, wake):
        request = pool.request()
        assert pool.begin(request) == 1
        samples = np.zeros((100, 2), dtype=np.int16)
        assert pool.feed(request.valid_start, samples) == 0
        assert pool.feed(request.valid_start + 101, samples) == -1
        assert pool.stats().aborted == 1 and pool.read() is None
        request = pool.request(1)
        assert pool.begin(request) == 1
        assert pool.feed(request.valid_start, samples) == 0
        wake.close()
        assert process.wait(timeout=3) == 2
        assert pool.read() is None and pool.stats().completed == 0
        pool.lib.leo_probe_abort(ct.byref(pool.collector))


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("period", [None, 120, 126])
def test_native_parent_full_dwell_pacing_and_identity(
    smoke_parent, artifacts, tmp_path, rate, period
):
    templates, pack = tmp_path / "templates", tmp_path / "dwells.pack"
    write_templates(templates, rate)
    counter = 10**16 + 37
    with pack.open("xb") as output:
        output.write(struct.pack("<4sII", b"LDP1", rate, 2))
        for edge in range(2):
            output.write(struct.pack("<QQII", counter + edge * rate, 90 + edge, edge, 3))
            output.write(np.zeros((rate // 50 * 6, 2), dtype="<i2").tobytes())
    spacing = period or 126
    command = [str(smoke_parent), str(artifacts[0]), str(templates), str(pack), str(2 * spacing)]
    if period is not None:
        command.append(str(period))
    run = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    assert len(rows) == 3
    for seq, row in enumerate(rows[:-1]):
        assert row["schema"] == "native-worker-dwell-result-v1"
        assert row["sequence"] == seq and row["visit"] == 90 + seq
        assert row["rx"] == 1 and row["channel"] == 3 and row["edge"] == seq
        assert row["device_counter"] == str(counter + seq * rate)
        assert row["valid_end"] == str(counter + seq * rate + rate // 50 * 6)
        assert row["sample_count"] == rate // 50 * 6
        assert row["search_window_mask"] == 63 and row["confirmation_window_mask"] == 1
        assert row["rank"]["order"] == list(range(6))
        assert row["screen_diagnostics"]["available_mask"] == 3
        assert row["candidates"] == []
        assert row["total_cpu_ms"] >= row["confirmation_cpu_ms"]
    terminal = rows[-1]
    assert terminal["schema"] == "native-worker-dwell-summary-v1"
    assert terminal["completed"] == terminal["submitted"] == 2
    assert terminal["skipped"] == terminal["dropped"] == 0
    assert terminal["arrival_period_ms"] == spacing
    assert terminal["duration_ms"] == 2 * spacing
    assert 7200000 < terminal["pool_bytes"] < 7500000
    assert "not RF or full archived-stream" in terminal["scope"]


@pytest.mark.parametrize("period", ["0", "119", "127", "120.0", "invalid"])
def test_native_parent_rejects_unreviewed_arrival_period_before_open(smoke_parent, period):
    run = subprocess.run(
        [str(smoke_parent), "/missing-worker", "/missing-template", "/missing-pack", "240", period],
        capture_output=True,
        timeout=3,
    )
    assert run.returncode == 2 and not run.stdout and not run.stderr


@pytest.mark.parametrize(
    "mutation", ["empty", "too_many", "truncated", "trailing", "overflow", "edge", "rate"]
)
def test_native_parent_rejects_malformed_full_dwell_pack(
    smoke_parent, artifacts, tmp_path, mutation
):
    rate = 2500000
    templates, pack = tmp_path / "templates", tmp_path / "dwells.pack"
    write_templates(templates, rate)
    count = 0 if mutation == "empty" else (49 if mutation == "too_many" else 1)
    counter = 2**64 - 2 if mutation == "overflow" else 10**16 + 37
    data = struct.pack(
        "<4sIIQQII",
        b"LDP1",
        5000000 if mutation == "rate" else rate,
        count,
        counter,
        91,
        2 if mutation == "edge" else 1,
        3,
    )
    data += np.zeros((rate // 50 * 6, 2), dtype="<i2").tobytes()
    if mutation == "truncated":
        data = data[:-1]
    if mutation == "trailing":
        data += b"x"
    pack.write_bytes(data)
    run = subprocess.run(
        [str(smoke_parent), str(artifacts[0]), str(templates), str(pack), "126"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert run.returncode == 2 and not run.stdout


def test_native_parent_does_not_report_success_when_evidence_output_is_full(
    smoke_parent, artifacts, tmp_path
):
    templates = tmp_path / "templates"
    write_templates(templates, 2500000)
    with open("/dev/full", "wb") as full:
        run = subprocess.run(
            [str(smoke_parent), str(artifacts[0]), str(templates)],
            stdout=full,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    assert run.returncode == 2
    assert "flush replay evidence" in run.stderr
