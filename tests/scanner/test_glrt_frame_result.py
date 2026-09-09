"""Worker-to-wire binding tests; no hardware, network, archive or database."""

import ctypes as ct
import math
import struct
import subprocess

import pytest

from leo.contracts.scanner_glrt_frame import decode_frame
from tests.scanner.test_adaptive_scan import Observation
from tests.scanner.test_glrt_frame_codec import Frame, Record
from tests.scanner.test_native_presence_pool import Evidence, Request
from tools.native_presence import ROOT


class Policy(ct.Structure):
    _fields_ = [
        ("minimum_exact_score", ct.c_double),
        ("minimum_margin", ct.c_double),
        ("classification_enabled", ct.c_uint32),
        ("absence_enabled", ct.c_uint32),
    ]


@pytest.fixture(scope="module")
def adapter(tmp_path_factory):
    output = tmp_path_factory.mktemp("glrt-frame-result") / "adapter.so"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(ROOT / "src/leo/scanner/native_presence/frame_codec.c"),
            str(ROOT / "src/leo/scanner/native_presence/frame_result.c"),
            "-lm",
            "-o",
            str(output),
        ],
        check=True,
    )
    lib = ct.CDLL(str(output))
    lib.leo_glrt_result_record.argtypes = [
        ct.POINTER(Evidence),
        ct.POINTER(Policy),
        ct.POINTER(Record),
    ]
    lib.leo_glrt_unavailable_record.argtypes = [ct.POINTER(Request), ct.c_int, ct.POINTER(Record)]
    lib.leo_glrt_result_observation.argtypes = [
        ct.POINTER(Evidence),
        ct.POINTER(Policy),
        ct.POINTER(Observation),
    ]
    lib.leo_glrt_frame_encode.argtypes = [
        ct.POINTER(Frame),
        ct.c_void_p,
        ct.c_size_t,
        ct.POINTER(ct.c_size_t),
    ]
    return lib


def evidence(rate=5000000, window=4, start=10**16 + 37):
    e = Evidence()
    e.request = Request(
        71, 9, 14, 81, start, start + rate // 50 * 6, start, rate, rate // 50 * 6, 1, 3, 1
    )
    e.dwell.search_window_mask = 63
    e.dwell.confirmation_window_mask = 1 << window
    e.dwell.rank.order[0] = window
    e.dwell.total_cpu_ms, e.dwell.total_wall_ms = 73.125, 89.25
    e.evidence.candidate_count = 1
    c = e.evidence.candidates[0]
    c.epoch, c.fractional_complete, c.fractional_offset_samples = 43, 1, -0.375
    c.exact_score, c.control_score, c.margin = 0.25, 0.125, 0.125
    c.tracking_cfo_hz = 123456.25
    return e


def convert(lib, e, policy=None):
    r = Record()
    assert (
        lib.leo_glrt_result_record(ct.byref(e), ct.byref(policy) if policy else None, ct.byref(r))
        == 0
    )
    return r


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("window", range(6))
@pytest.mark.parametrize("start", [0, 10**16 + 37, 2**64 - 600001])
def test_original_dwell_epoch_and_fraction_survive_frame_encoding(adapter, rate, window, start):
    e = evidence(rate, window, start)
    r = convert(adapter, e)
    assert r.verdict == 0 and r.reason == 5  # unqualified, not a positive or absence claim
    assert r.search_window_mask == 63
    assert r.confirmation_start == start + window * rate // 50
    assert r.confirmation_end == r.confirmation_start + rate // 50
    assert r.epoch_sample_counter == r.confirmation_start + 43
    assert r.fractional_offset_samples == -0.375
    assert r.cpu_ms == 73.125 and r.wall_ms == 89.25
    legacy = ct.create_string_buffer(b"unchanged-hop-metadata")
    frame = Frame()
    frame.session, frame.generation, frame.frame_sequence = 71, 9, 900
    frame.result_sequence_limit, frame.result_count = 15, 1
    frame.algorithm_sha256[:] = bytes([1]) * 32
    frame.configuration_sha256[:] = bytes([2]) * 32
    frame.legacy_metadata = ct.addressof(legacy)
    frame.legacy_bytes = len(legacy.value)
    frame.results[0] = r
    output, written = ct.create_string_buffer(1024), ct.c_size_t()
    assert (
        adapter.leo_glrt_frame_encode(ct.byref(frame), output, len(output), ct.byref(written)) == 0
    )
    decoded = decode_frame(output.raw[: written.value])
    assert decoded.frame_sequence == 900 and decoded.results[0].visit == 81
    assert decoded.legacy_metadata == legacy.value
    assert decoded.results[0].epoch_sample_counter == start + window * rate // 50 + 43
    assert decoded.results[0].fractional_offset_samples == -0.375


def test_classification_policy_is_explicit_and_absence_requires_separate_enable(adapter):
    e = evidence()
    assert convert(adapter, e, Policy(0.2, 0.025, 0, 0)).reason == 5
    r = convert(adapter, e, Policy(0.2, 0.025, 1, 0))
    assert r.verdict == 1 and r.reason == 0
    r = convert(adapter, e, Policy(0.3, 0.025, 1, 0))
    assert r.verdict == 0 and r.reason == 4
    r = convert(adapter, e, Policy(0.3, 0.025, 1, 1))
    assert r.verdict == 2 and r.reason == 0
    e.evidence.candidate_count = 0
    for policy, verdict, reason in (
        (None, 0, 5),
        (Policy(0.2, 0.025, 1, 0), 0, 4),
        (Policy(0.2, 0.025, 1, 1), 2, 0),
    ):
        r = convert(adapter, e, policy)
        assert (r.verdict, r.reason) == (verdict, reason)
        assert r.confirmation_start == r.confirmation_end
        assert r.epoch_sample_counter == r.fractional_offset_samples == 0


@pytest.mark.parametrize(
    "kind,expected,healthy",
    [
        ("positive", 1, 1),
        ("below_threshold", 2, 1),
        ("no_candidate", 2, 1),
        ("fractional_incomplete", 0, 1),
        ("worker_failed", 0, 0),
        ("positive_and_incomplete", 1, 1),
        ("negative_and_incomplete", 0, 1),
    ],
)
def test_scheduling_hint_distinguishes_completed_miss_from_unknown(
    adapter, kind, expected, healthy
):
    e, p = evidence(), Policy(0.175, 0.025, 1, 0)
    if kind == "worker_failed":
        e.status = -1
    if kind == "no_candidate":
        e.evidence.candidate_count = 0
    if kind in ("below_threshold", "negative_and_incomplete"):
        p.minimum_exact_score = 0.3
    if "and_incomplete" in kind:
        e.evidence.candidate_count = 2
        e.evidence.candidates[1] = e.evidence.candidates[0]
        e.evidence.candidates[1].fractional_complete = 0
    if kind == "fractional_incomplete":
        e.evidence.candidates[0].fractional_complete = 0
    o = Observation()
    assert adapter.leo_glrt_result_observation(ct.byref(e), ct.byref(p), ct.byref(o)) == 0
    assert (o.outcome, o.healthy) == (expected, healthy)
    assert (o.session, o.generation, o.visit, o.valid_start, o.valid_end) == (
        e.request.session,
        e.request.generation,
        e.request.visit,
        e.request.valid_start,
        e.request.valid_end,
    )
    assert (o.target, o.rate_hz, o.rx) == (6, 5000000, 1)
    # An evaluated miss remains unavailable in the existing public frame;
    # scheduling evidence cannot silently enable a NO_SIGNAL assertion.
    assert convert(adapter, e, p).verdict == (1 if expected == 1 else 0)


@pytest.mark.parametrize("p", [None, Policy(0.175, 0.025, 0, 0), Policy(0.175, 0.025, 1, 1)])
def test_scheduling_observation_requires_positive_only_policy(adapter, p):
    o = Observation()
    ct.memset(ct.byref(o), 0xAA, ct.sizeof(o))
    original = bytes(o)
    assert (
        adapter.leo_glrt_result_observation(
            ct.byref(evidence()), ct.byref(p) if p else None, ct.byref(o)
        )
        == -1
    )
    assert bytes(o) == original


def test_failed_or_incomplete_fractional_work_cannot_become_absence(adapter):
    e = evidence()
    p = Policy(0.2, 0.025, 1, 1)
    e.status = -1
    r = convert(adapter, e, p)
    assert r.verdict == 0 and r.reason == 2 and r.search_window_mask == 0
    assert r.exact_score == 0 and r.epoch_sample_counter == 0
    e.status = 0
    e.evidence.candidates[0].fractional_complete = 0
    r = convert(adapter, e, p)
    assert r.verdict == 0 and r.reason == 4
    assert r.confirmation_start == r.confirmation_end and r.epoch_sample_counter == 0


@pytest.mark.parametrize("reason", range(1, 7))
def test_supervisor_can_report_skipped_or_failed_dwell_without_worker_result(adapter, reason):
    e = evidence()
    r = Record()
    assert adapter.leo_glrt_unavailable_record(ct.byref(e.request), reason, ct.byref(r)) == 0
    assert r.sequence == e.request.sequence and r.visit == e.request.visit
    assert r.valid_start == e.request.valid_start and r.valid_end == e.request.valid_end
    assert r.verdict == 0 and r.reason == reason and r.search_window_mask == 0
    assert r.search_start == r.search_end == r.confirmation_start == r.confirmation_end
    assert r.epoch_sample_counter == r.fractional_offset_samples == r.exact_score == 0


@pytest.mark.parametrize("reason", [-1, 0, 7, 2147483647])
def test_supervisor_cannot_invent_completion_or_reason(adapter, reason):
    r = Record()
    ct.memset(ct.byref(r), 0xAA, ct.sizeof(r))
    before = bytes(r)
    assert (
        adapter.leo_glrt_unavailable_record(ct.byref(evidence().request), reason, ct.byref(r)) == -1
    )
    assert bytes(r) == before


def test_best_passing_candidate_is_retained_even_if_another_has_larger_margin(adapter):
    e = evidence()
    e.evidence.candidate_count = 2
    e.evidence.candidates[1] = e.evidence.candidates[0]
    e.evidence.candidates[1].exact_score = 0.2
    e.evidence.candidates[1].control_score = 0
    e.evidence.candidates[1].margin = 0.2
    e.evidence.candidates[1].epoch = 90
    r = convert(adapter, e, Policy(0.225, 0.025, 1, 0))
    assert r.verdict == 1 and r.epoch_sample_counter == r.confirmation_start + 43


@pytest.mark.parametrize(
    "field,value",
    [
        ("rx", 2),
        ("channel", 0),
        ("edge", 2),
        ("session", 0),
        ("sample_count", 100000),
        ("rate_hz", 60000000),
        ("probe_start", 0),
    ],
)
def test_bad_request_does_not_mutate_output(adapter, field, value):
    e = evidence()
    setattr(e.request, field, value)
    r = Record()
    ct.memset(ct.byref(r), 0xAA, ct.sizeof(r))
    before = bytes(r)
    assert adapter.leo_glrt_result_record(ct.byref(e), None, ct.byref(r)) == -1
    assert bytes(r) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("epoch", -1),
        ("epoch", 100000),
        ("fractional_complete", 2),
        ("fractional_offset_samples", math.nan),
        ("fractional_offset_samples", 3),
        ("exact_score", math.inf),
        ("control_score", -1),
        ("margin", 0.9),
    ],
)
def test_malformed_candidates_rejected(adapter, field, value):
    e = evidence()
    setattr(e.evidence.candidates[0], field, value)
    with pytest.raises(AssertionError):
        convert(adapter, e)


@pytest.mark.parametrize(
    "mask,window,confirmed", [(0, 0, 1), (31, 0, 1), (63, 6, 64), (63, 0, 3), (63, 4, 1)]
)
def test_partial_or_inconsistent_search_is_rejected(adapter, mask, window, confirmed):
    e = evidence()
    e.dwell.search_window_mask, e.dwell.rank.order[0], e.dwell.confirmation_window_mask = (
        mask,
        window,
        confirmed,
    )
    with pytest.raises(AssertionError):
        convert(adapter, e)


@pytest.mark.parametrize(
    "policy",
    [
        Policy(math.nan, 0.1, 1, 0),
        Policy(0.1, 0, 1, 0),
        Policy(0.1, 0.1, 2, 0),
        Policy(0.1, 0.1, 0, 1),
    ],
)
def test_invalid_policy_rejected(adapter, policy):
    with pytest.raises(AssertionError):
        convert(adapter, evidence(), policy)


def verify_native_smoke(raw):
    offset, seq = 0, 0
    for rate in (2500000, 5000000):
        for edge in ("lower", "upper"):
            for window in range(6):
                for start in (0, 10**16 + 37, 2**64 - 600001):
                    size = struct.unpack_from("<I", raw, offset + 8)[0]
                    frame = decode_frame(raw[offset : offset + size])
                    offset += size
                    assert frame.session == 71 and frame.generation == 9
                    assert (
                        frame.frame_sequence == seq + 900 and frame.result_sequence_limit == seq + 1
                    )
                    assert frame.legacy_metadata == b"synthetic" and len(frame.results) == 1
                    r = frame.results[0]
                    assert r.visit == seq + 81 and r.sequence == seq and r.rate_hz == rate
                    assert r.edge == edge and r.channel == 3 and r.rx == 1
                    assert r.valid_start == start and r.valid_end == start + rate // 50 * 6
                    assert r.confirmation_start == start + window * rate // 50
                    assert r.epoch_sample_counter == r.confirmation_start + 43
                    assert r.fractional_offset_samples == -0.375 and r.cfo_hz == -123456.25
                    assert r.verdict == "unavailable" and r.reason == "unqualified_classifier"
                    assert r.exact_score == 0.25 and r.control_score == r.margin == 0.125
                    assert r.cpu_ms == 73.125 and r.wall_ms == 89.25
                    seq += 1
    assert offset == len(raw) and seq == 72
    return seq


def test_standalone_native_worker_frame_records_match_python(tmp_path):
    binary = tmp_path / "frame-smoke"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/fixtures/scanner_presence_frame_result_smoke.c"),
            str(ROOT / "src/leo/scanner/native_presence/frame_result.c"),
            str(ROOT / "src/leo/scanner/native_presence/frame_codec.c"),
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
    )
    run = subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)
    assert not run.stderr
    assert verify_native_smoke(run.stdout) == 72
