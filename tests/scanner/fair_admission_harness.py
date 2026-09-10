"""Virtual-time admission experiment with real SDK/pool/numerical subprocess.

Only the owner clock and worker publication timing are controlled. Zero RX1 IQ
is deliberately synthetic: this compares admission, not historic RF verdicts,
ARM CPU costs, acquisition duty, or physically paced performance.
"""

import ctypes as ct
import errno
import json
import os
import signal
import time
from dataclasses import dataclass

import numpy as np

from tests.scanner.test_adaptive_scan import Observation
from tests.scanner.test_scanner_glrt_fair_admission import Admission, AdmissionStats
from tests.scanner.test_scanner_glrt_port import Config, Session, load_port
from tests.scanner.test_scanner_glrt_positive import PositivePolicy
from tests.scanner.test_scanner_glrt_protection import Protection, Stats
from tools.native_presence import ROOT, build_scanner_glrt_port, build_worker

NATIVE = ROOT / "tests/scanner/native"
EPOCH_NS = 1_000_000_000
ORIGIN = 2**53 + 347


class Dispatch(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in ("visit", "valid_end", "published_ns")] + [
        ("target", ct.c_uint32),
        ("unused", ct.c_uint32),
    ]


@dataclass(frozen=True)
class Geometry:
    start: int
    end: int
    target: int


def build(root):
    root.mkdir()
    include = ROOT / "src/leo/scanner/native_presence"
    sdk = build_scanner_glrt_port(
        root / "sdk.so",
        cflags=(
            "-I",
            str(include),
            "-Wl,--wrap=clock_gettime",
            "-Wl,--wrap=leo_probe_publish_held",
            str(NATIVE / "protection_clock.c"),
            str(NATIVE / "fair_dispatch_trace.c"),
        ),
    )
    config = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_bytes()
    )
    flags = tuple(config["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in config["variants"][0]["defines"].items()
    )
    flags += tuple(
        f"-DLEO_PRESENCE_{name}=1"
        for name in (
            "DIFFERENTIAL_CI16",
            "RANK_HYBRID_PROJECTION",
            "GLRT_SYMBOL_DIVERSITY",
            "RANK_AMPLITUDE_WEIGHTED",
            "BOUNDED_MAGNITUDE",
            "CONDITIONED_BLOCK_ROTATION",
            "ENERGY_SUPPORT",
            "ENERGY_SYMBOL_SUPPORT",
        )
    )
    worker = build_worker(
        root / "worker",
        cflags=(*flags, "-I", str(include)),
        ldflags=(str(NATIVE / "fair_worker_gate.c"), "-Wl,--wrap=leo_probe_complete"),
        dependencies=(NATIVE / "fair_worker_gate.c",),
    )
    return sdk, worker


def load(sdk):
    p = load_port(sdk)
    p.leo_scanner_glrt_open_positive.argtypes = [
        ct.POINTER(ct.c_void_p),
        ct.POINTER(Config),
        ct.c_char_p,
        ct.c_char_p,
        ct.POINTER(PositivePolicy),
    ]
    for name, structure in (
        ("enable_protection", Protection),
        ("protection_stats", Stats),
        ("enable_fair_admission", Admission),
        ("admission_stats", AdmissionStats),
        ("observation", Observation),
    ):
        getattr(p, "leo_scanner_glrt_" + name).argtypes = [ct.c_void_p, ct.POINTER(structure)]
    p.leo_scanner_glrt_enable_cooperative_skips.argtypes = [ct.c_void_p]
    p.leo_test_clock.argtypes = [ct.c_uint64, ct.c_int]
    p.leo_test_dispatch_get.argtypes = [ct.c_uint32, ct.POINTER(Dispatch)]
    p.leo_test_dispatch_count.restype = ct.c_uint32
    return p


def _stopped(pid):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        found, status = os.waitpid(pid, os.WNOHANG | os.WUNTRACED)
        if found:
            assert os.WIFSTOPPED(status) and os.WSTOPSIG(status) == signal.SIGSTOP, status
            return
        time.sleep(0.0001)
    raise TimeoutError("owned numerical worker did not reach its publication gate")


def run(
    sdk,
    worker,
    directory,
    rate,
    geometry,
    costs_ms,
    *,
    block_ms=20,
    owner_jitter_ms=(0,),
    maximum_pending_age_ms=120,
):
    """Controlled completion costs are indexed by source visit, not dispatch.

    Owner calls occur at delivered block ends; result publication is released
    just before the first poll on/after its prescribed completion. The real
    subprocess must reach both gates, so slow test-host computation cannot be
    silently reinterpreted as prescribed ARM timing. All waiting is test-only.
    """
    if rate not in (2500000, 5000000) or not 0 < block_ms <= 20:
        raise ValueError("unsupported fixture geometry")
    if not isinstance(maximum_pending_age_ms, int) or not 1 <= maximum_pending_age_ms <= 240:
        raise ValueError("pending age must be an integer in 1..240 ms")
    if not geometry or len(geometry) != len(costs_ms) or len(geometry) > 2500:
        raise ValueError("invalid fixture inventory")
    if any(not np.isfinite(c) or not 0 < c < 450 for c in costs_ms):
        raise ValueError("fixture costs must be finite and below admission watchdog bounds")
    if not owner_jitter_ms or any(
        not np.isfinite(jitter) or not 0 <= jitter < block_ms for jitter in owner_jitter_ms
    ):
        raise ValueError("delivery jitter must preserve the increasing owner clock")
    dwell = rate * 120 // 1000
    if any(
        g.end - g.start != dwell
        or not 0 <= g.target < 8
        or g.start < ORIGIN
        or (i and g.start < geometry[i - 1].end)
        for i, g in enumerate(geometry)
    ):
        raise ValueError("invalid or overlapping source visits")
    directory.mkdir()
    p = load(sdk)
    p.leo_test_clock(0, 0)
    p.leo_test_dispatch_reset()
    s = Session(p, worker, directory, rate, positive_policy=PositivePolicy(0.175, 0.025))
    pending_completion = None
    stopped_after_result = False
    checks, records, feedback = [], [], []
    callbacks, now_ns = 0, EPOCH_NS
    block_count = rate * block_ms // 1000
    iq = np.zeros((block_count, 4), dtype=np.int16)
    iq[:, :2] = 30000
    before = iq.copy()
    next_visit = 0
    a, protection = AdmissionStats(), Stats()

    def before_poll(source_end, poll_index):
        nonlocal pending_completion, stopped_after_result, now_ns
        proposed = EPOCH_NS + (source_end - ORIGIN) * 1_000_000_000 // rate
        proposed += round(owner_jitter_ms[poll_index % len(owner_jitter_ms)] * 1e6)
        # A partial final block may be shorter than the jitter difference.
        # Delivery cannot precede the prior delivery. Keep the SDK's actual
        # backwards-clock guard intact; correct only the artificial schedule.
        now_ns = max(now_ns, proposed)
        p.leo_test_clock(now_ns, 1)
        if pending_completion is not None and now_ns >= pending_completion:
            os.kill(s.worker_pid, signal.SIGCONT)
            _stopped(s.worker_pid)  # Result is published while virtual time stays fixed.
            checks[-1]["harvested_ms"] = (now_ns - EPOCH_NS) / 1e6
            pending_completion = None
            stopped_after_result = True

    def after_poll():
        nonlocal pending_completion, stopped_after_result
        frame = s.frame()
        assert frame.legacy_metadata == b"legacy"
        if frame.flags & 4:
            assert p.leo_scanner_glrt_protection_stats(s.ptr, ct.byref(protection)) == 0
            raise AssertionError({name: getattr(protection, name) for name, _ in Stats._fields_})
        records.extend(frame.results)
        while True:
            observation = Observation()
            status = p.leo_scanner_glrt_observation(s.ptr, ct.byref(observation))
            if status in (0, -errno.ENODATA):
                break
            assert status == 1 and observation.healthy
            feedback.append((observation.visit, observation.outcome, observation.healthy))
        total = p.leo_test_dispatch_count()
        assert total in (len(checks), len(checks) + 1)
        if total > len(checks):
            assert pending_completion is None
            dispatch = Dispatch()
            assert p.leo_test_dispatch_get(total - 1, ct.byref(dispatch)) == 0
            assert dispatch.published_ns == now_ns
            visit = int(dispatch.visit)
            assert dispatch.valid_end == geometry[visit].end
            assert dispatch.target == geometry[visit].target
            checks.append(
                {
                    "visit": visit,
                    "target": int(dispatch.target),
                    "ready_ms": (dispatch.valid_end - ORIGIN) * 1000 / rate,
                    "started_ms": (now_ns - EPOCH_NS) / 1e6,
                    "completed_ms": (now_ns - EPOCH_NS) / 1e6 + costs_ms[visit],
                }
            )
            if stopped_after_result:
                os.kill(s.worker_pid, signal.SIGCONT)
                stopped_after_result = False
            _stopped(s.worker_pid)  # Actual numerical work is done, still owns its IQ slot.
            pending_completion = now_ns + round(costs_ms[visit] * 1e6)
        assert p.leo_scanner_glrt_admission_stats(s.ptr, ct.byref(a)) == 0
        assert a.enabled and a.pending <= 1 and a.running <= 1
        assert p.leo_scanner_glrt_protection_stats(s.ptr, ct.byref(protection)) == 0
        assert not protection.disabled and protection.occupied_slots <= 3

    try:
        p.leo_test_clock(EPOCH_NS, 1)
        assert (
            p.leo_scanner_glrt_enable_protection(s.ptr, ct.byref(Protection(3, 450, 500, 4))) == 0
        )
        assert p.leo_scanner_glrt_enable_cooperative_skips(s.ptr) == 0
        assert (
            p.leo_scanner_glrt_enable_fair_admission(
                s.ptr, ct.byref(Admission(maximum_pending_age_ms, 2500))
            )
            == 0
        )
        end = ORIGIN
        for first in range(ORIGIN, geometry[-1].end, block_count):
            end = min(first + block_count, geometry[-1].end)
            before_poll(end, callbacks)
            while next_visit < len(geometry) and geometry[next_visit].start < end:
                g = geometry[next_visit]
                assert s.visit(next_visit, g.start, g.target % 4 + 1, g.target // 4) == 0
                next_visit += 1
            assert s.block(first, iq[: end - first]) == 0
            after_poll()
            callbacks += 1
        assert p.leo_scanner_glrt_finish(s.ptr, 0) == 0
        after_poll()
        for attempt in range(100):
            if not a.pending and not a.running:
                break
            end += block_count
            before_poll(end, callbacks + attempt)
            after_poll()
        assert not a.pending and not a.running and pending_completion is None
        if stopped_after_result:
            os.kill(s.worker_pid, signal.SIGCONT)
            stopped_after_result = False
        records.extend(r for frame in s.drain() for r in frame.results)
        assert [r.visit for r in records] == list(range(len(geometry)))
        assert [r[0] for r in feedback] == list(range(len(geometry)))
        selected = {c["visit"] for c in checks}
        assert {r.visit for r in records if r.search_window_mask == 63} == selected
        assert all(r.verdict == "unavailable" for r in records)
        for r, observation in zip(records, feedback, strict=True):
            assert r.valid_start == geometry[r.visit].start and r.valid_end == geometry[r.visit].end
            if r.visit not in selected:
                assert r.search_window_mask == 0 and observation[1:] == (0, 1)
        np.testing.assert_array_equal(iq, before)
        return {
            "checks": checks,
            "records": len(records),
            "callbacks": callbacks,
            "admission": {name: getattr(a, name) for name, _ in AdmissionStats._fields_},
            "protection": {name: getattr(protection, name) for name, _ in Stats._fields_},
        }
    finally:
        s.close()  # Owns/reaps only this subprocess, even if a gate/assertion fails.
        p.leo_test_clock(0, 0)
