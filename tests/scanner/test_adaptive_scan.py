"""Actual C cooldown/weighted scheduler, with synthetic device time; no RF."""

import ctypes as ct
import errno
import subprocess
from collections import Counter

import pytest

from tools.native_presence import ROOT


class Config(ct.Structure):
    _fields_ = [(k, ct.c_uint64) for k in ("session", "generation", "start_counter")] + [
        (k, ct.c_uint32)
        for k in (
            "rate_hz",
            "target_count",
            "maximum_visits",
            "warmup_visits",
            "missed_dwells",
            "active_weight",
            "quiet_weight",
            "cooldown_ms",
            "maximum_revisit_ms",
            "hop_budget_ms",
            "maximum_result_age_ms",
            "unhealthy_limit",
        )
    ]


class Observation(ct.Structure):
    _fields_ = [
        (k, ct.c_uint64) for k in ("session", "generation", "visit", "valid_start", "valid_end")
    ] + [(k, ct.c_uint32) for k in ("rate_hz", "rx", "target", "outcome", "healthy")]


class Choice(ct.Structure):
    _fields_ = [
        (k, ct.c_uint64)
        for k in ("visit", "decision_counter", "basis_visit", "cooldown_remaining_samples")
    ] + [
        (k, ct.c_uint32)
        for k in ("target", "reason", "active_mask", "quiet_mask", "consecutive_misses")
    ]


class Target(ct.Structure):
    _fields_ = [(k, ct.c_uint64) for k in ("last_detection_end", "last_visit_start")] + [
        (k, ct.c_uint32) for k in ("state", "consecutive_misses", "visits", "has_detection")
    ]


@pytest.fixture(scope="module")
def policy(tmp_path_factory):
    output = tmp_path_factory.mktemp("adaptive-scan") / "policy.so"
    source = ROOT / "src/leo/scanner/native_presence/adaptive_scan.c"
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
            str(source),
            "-o",
            str(output),
        ],
        check=True,
    )
    lib = ct.CDLL(str(output))
    lib.leo_adaptive_create.argtypes = [ct.POINTER(ct.c_void_p), ct.POINTER(Config)]
    lib.leo_adaptive_destroy.argtypes = [ct.c_void_p]
    lib.leo_adaptive_choose.argtypes = [ct.c_void_p, ct.c_uint64, ct.POINTER(Choice)]
    lib.leo_adaptive_commit.argtypes = [ct.c_void_p, ct.c_uint64, ct.c_uint64]
    lib.leo_adaptive_observe.argtypes = [ct.c_void_p, ct.POINTER(Observation), ct.c_uint64]
    lib.leo_adaptive_fallback.argtypes = [ct.c_void_p]
    lib.leo_adaptive_target.argtypes = [ct.c_void_p, ct.c_uint32, ct.POINTER(Target)]
    return lib


class Scan:
    def __init__(self, lib, *, rate=2500000, targets=8, start=2**53 + 217, **changes):
        self.lib = lib
        self.config = Config(
            71, 9, start, rate, targets, 2500, 3, 3, 3, 1, 2000, 3000, 160, 1000, 3
        )
        for k, v in changes.items():
            setattr(self.config, k, v)
        self.ptr = ct.c_void_p()
        assert lib.leo_adaptive_create(ct.byref(self.ptr), ct.byref(self.config)) == 0
        self.now = start

    def close(self):
        self.lib.leo_adaptive_destroy(self.ptr)
        self.ptr = ct.c_void_p()

    def choose(self):
        c = Choice()
        assert self.lib.leo_adaptive_choose(self.ptr, self.now, ct.byref(c)) == 0
        return c

    def commit(self, c):
        start = self.now
        self.now += self.config.rate_hz * 120 // 1000
        assert self.lib.leo_adaptive_commit(self.ptr, start, self.now) == 0
        return Observation(71, 9, c.visit, start, self.now, self.config.rate_hz, 1, c.target, 0, 1)

    def observe(self, o):
        assert self.lib.leo_adaptive_observe(self.ptr, ct.byref(o), self.now) == 0

    def step(self, outcome=1, healthy=1):
        c = self.choose()
        o = self.commit(c)
        o.outcome, o.healthy = outcome, healthy
        self.observe(o)
        return c

    def target(self, i):
        t = Target()
        assert self.lib.leo_adaptive_target(self.ptr, i, ct.byref(t)) == 0
        return t


@pytest.fixture
def scan(policy):
    s = Scan(policy)
    yield s
    s.close()


@pytest.mark.parametrize("mask", range(256))
def test_all_activity_combinations_have_expected_shares_and_no_starvation(policy, mask):
    s = Scan(policy)
    try:
        counts = Counter()
        last = {}
        maximum_gap = 0
        # Continually observed activity, not a fabricated prediction for an
        # unvisited target. Counts exclude startup and its last pending result.
        active = mask.bit_count()
        weights = [3 if mask & (1 << i) else 1 for i in range(8)] if active else [1] * 8
        period = sum(weights)
        for i in range(48 + period * 20):
            c = s.choose()
            o = s.commit(c)
            o.outcome = 1 if mask & (1 << c.target) else 2
            s.observe(o)
            if i < 24:
                assert c.target == i % 8 and c.reason == 0
            if i >= 48:
                counts[c.target] += 1
                if c.target in last:
                    maximum_gap = max(maximum_gap, i - last[c.target])
                last[c.target] = i
                assert c.active_mask == mask
                assert c.quiet_mask == 255 ^ mask
        # A deadline override may move a visit across this finite boundary.
        assert all(abs(counts[i] - weights[i] * 20) <= 1 for i in range(8))
        assert maximum_gap * 120 <= 3000
    finally:
        s.close()


def test_four_channel_example_allocates_thirty_thirty_thirty_ten(policy):
    s = Scan(policy, targets=4)
    try:
        counts = Counter()
        for i in range(20 + 100):
            c = s.choose()
            o = s.commit(c)
            o.outcome = 2 if c.target == 1 else 1
            s.observe(o)
            if i >= 20:
                counts[c.target] += 1
        assert counts == {0: 30, 1: 10, 2: 30, 3: 30}
    finally:
        s.close()


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_three_misses_stay_active_until_exact_cooldown_boundary(policy, rate):
    s = Scan(policy, targets=1, rate=rate)
    try:
        s.step(1)
        detection_end = s.now
        for _ in range(3):
            s.step(2)
        s.now = detection_end + 2 * rate - 1
        c = s.choose()
        assert c.active_mask == 1 and c.quiet_mask == 0
        assert c.consecutive_misses == 3 and c.cooldown_remaining_samples == 1
        o = s.commit(c)
        o.outcome = 2
        s.observe(o)
        c = s.choose()
        assert c.quiet_mask == 1 and c.reason == 3
    finally:
        s.close()
    # Independently check equality, rather than skipping past the boundary.
    s = Scan(policy, targets=1, rate=rate)
    try:
        s.step(1)
        detection_end = s.now
        for _ in range(3):
            s.step(2)
        s.now = detection_end + 2 * rate
        assert s.choose().quiet_mask == 1
    finally:
        s.close()


@pytest.mark.parametrize("misses", [0, 1, 2])
def test_elapsed_time_alone_does_not_demote(policy, misses):
    s = Scan(policy, targets=1)
    try:
        s.step(1)
        for _ in range(misses):
            s.step(2)
        s.now += s.config.rate_hz * 3
        c = s.choose()
        assert c.active_mask == 1 and c.quiet_mask == 0
    finally:
        s.close()


def test_unknown_breaks_streak_and_new_positive_renews_cooldown(policy):
    s = Scan(policy, targets=1)
    try:
        for outcome in (1, 2, 2, 0, 2, 2, 1):
            s.step(outcome)
        last_positive = s.now
        c = s.choose()
        assert c.active_mask == 1 and c.consecutive_misses == 0
        assert c.cooldown_remaining_samples == 2 * s.config.rate_hz
        assert s.target(0).last_detection_end == last_positive
    finally:
        s.close()


def test_lower_and_upper_are_independent(scan):
    for _ in range(48):
        c = scan.choose()
        o = scan.commit(c)
        o.outcome = 1 if c.target == 4 else 2
        scan.observe(o)
    c = scan.choose()
    assert c.active_mask == 16 and c.quiet_mask == 239


def test_results_apply_in_source_order_and_duplicates_cannot_refresh(scan):
    first = scan.commit(scan.choose())
    second = scan.commit(scan.choose())
    second.outcome = 1
    scan.observe(second)
    c = scan.choose()
    assert c.basis_visit == 2**64 - 1 and c.active_mask == 0
    scan.commit(c)
    first.outcome = 2
    scan.observe(first)
    c = scan.choose()
    assert c.basis_visit == 1 and c.active_mask == 2
    assert scan.lib.leo_adaptive_observe(scan.ptr, ct.byref(second), scan.now) == -errno.EALREADY


def test_stale_positive_is_unknown_not_a_fresh_detection(scan):
    o = scan.commit(scan.choose())
    o.outcome = 1
    scan.now += scan.config.rate_hz + 1
    scan.observe(o)
    assert scan.choose().active_mask == 0
    assert scan.target(0).has_detection == 0


def test_missing_results_expire_without_waiting_and_latch_fallback(scan):
    stale = []
    for _ in range(3):
        stale.append(scan.commit(scan.choose()))
    scan.now += scan.config.rate_hz + 1
    c = scan.choose()
    assert c.reason == 4 and c.basis_visit == 2
    assert all(scan.target(i).consecutive_misses == 0 for i in range(8))
    assert scan.lib.leo_adaptive_observe(scan.ptr, ct.byref(stale[0]), scan.now) == -errno.EALREADY
    o = scan.commit(c)
    o.outcome = 1
    scan.observe(o)
    assert all(scan.step(1).reason == 4 for _ in range(16))


def test_healthy_incomplete_estimation_does_not_trip_worker_health(scan):
    assert all(scan.step(0, healthy=1).reason != 4 for _ in range(64))


def test_explicit_fault_retains_contiguous_round_robin(scan):
    for _ in range(27):
        scan.step()
    scan.lib.leo_adaptive_fallback(scan.ptr)
    choices = [scan.step() for _ in range(16)]
    assert all(c.reason == 4 for c in choices)
    assert [c.target for c in choices] == [i % 8 for i in range(27, 43)]


def test_exploration_deadline_overrides_weighting(policy):
    s = Scan(policy, maximum_revisit_ms=1280)
    try:
        choices = []
        for _ in range(120):
            c = s.choose()
            o = s.commit(c)
            o.outcome = 1 if c.target < 7 else 2
            s.observe(o)
            choices.append(c)
        assert any(c.reason == 2 and c.target == 7 for c in choices[24:])
        previous = {}
        for c in choices[24:]:
            if c.target in previous:
                assert c.decision_counter - previous[c.target] <= s.config.rate_hz * 1280 // 1000
            previous[c.target] = c.decision_counter
    finally:
        s.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("session", 72),
        ("generation", 10),
        ("target", 7),
        ("rx", 0),
        ("rate_hz", 5000000),
        ("valid_end", 0),
        ("outcome", 3),
        ("healthy", 2),
    ],
)
def test_bad_observation_leaves_policy_unchanged(scan, field, value):
    o = scan.commit(scan.choose())
    setattr(o, field, value)
    assert scan.lib.leo_adaptive_observe(scan.ptr, ct.byref(o), scan.now) == -errno.EINVAL
    assert scan.choose().basis_visit == 2**64 - 1


def test_failed_evaluation_cannot_assert_detection(scan):
    o = scan.commit(scan.choose())
    o.healthy, o.outcome = 0, 1
    assert scan.lib.leo_adaptive_observe(scan.ptr, ct.byref(o), scan.now) == -errno.EINVAL


def test_choice_requires_commit_and_rejects_backwards_or_partial_geometry(scan):
    c = scan.choose()
    assert scan.lib.leo_adaptive_choose(scan.ptr, scan.now, ct.byref(Choice())) == -errno.EBUSY
    assert scan.lib.leo_adaptive_commit(scan.ptr, scan.now - 1, scan.now + 299999) == -errno.EINVAL
    assert scan.lib.leo_adaptive_commit(scan.ptr, scan.now, scan.now + 1) == -errno.EINVAL
    scan.commit(c)
    assert scan.lib.leo_adaptive_choose(scan.ptr, scan.now - 1, ct.byref(Choice())) == -errno.EINVAL


def test_scan_reset_does_not_reuse_activity(policy):
    s = Scan(policy)
    for _ in range(24):
        s.step()
    assert s.choose().active_mask == 255
    s.close()
    s = Scan(policy)
    try:
        c = s.choose()
        assert c.active_mask == c.quiet_mask == 0 and c.target == 0 and c.reason == 0
    finally:
        s.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("session", 0),
        ("rate_hz", 60000000),
        ("target_count", 9),
        ("maximum_visits", 2501),
        ("warmup_visits", 0),
        ("missed_dwells", 0),
        ("active_weight", 0),
        ("quiet_weight", 4),
        ("cooldown_ms", 0),
        ("maximum_revisit_ms", 500),
        ("hop_budget_ms", 119),
        ("maximum_result_age_ms", 0),
        ("unhealthy_limit", 0),
    ],
)
def test_invalid_configuration_is_rejected_without_changing_output(policy, field, value):
    c = Config(71, 9, 0, 2500000, 8, 2500, 3, 3, 3, 1, 2000, 3000, 160, 1000, 3)
    setattr(c, field, value)
    ptr = ct.c_void_p(123)
    assert policy.leo_adaptive_create(ct.byref(ptr), ct.byref(c)) == -errno.EINVAL
    assert ptr.value == 123
