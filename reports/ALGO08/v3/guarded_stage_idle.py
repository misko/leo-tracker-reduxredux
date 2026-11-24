"""Admit individual physical reads only during measured low-load intervals."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from pathlib import Path
from time import perf_counter, sleep


FULL_LIMIT = 20.0
QUEUE_LIMIT = 2
MIN_QUIET_S = 1.0
POLL_S = .25
LAST_READ_MARGIN_S = 1.0


class IdleWindowExpired(Exception):
    """The bounded opportunity ended without authorizing a further read."""


@dataclass(frozen=True)
class Load:
    at: float
    full_avg10: float
    full_total_us: int
    in_flight: int
    weighted_ms: int


def sample(device, now):
    full = next(line for line in Path("/proc/pressure/io").read_text().splitlines() if line.startswith("full "))
    pressure = dict(pair.split("=", 1) for pair in full.split()[1:])
    counts = device.read_text().split()
    return Load(now(), float(pressure["avg10"]), int(pressure["total"]), int(counts[8]), int(counts[10]))


class QuietInterval:
    def __init__(self):
        self.last = None
        self.since = None
        self.queue_mean = None
        self.current_full = None

    def observe(self, state):
        if state.full_avg10 >= FULL_LIMIT or state.in_flight > QUEUE_LIMIT:
            self.last = self.since = self.queue_mean = self.current_full = None
            return False
        if self.last is None:
            self.last, self.since = state, state.at
            return False
        span = state.at - self.last.at
        if span >= POLL_S * .8:
            self.queue_mean = (state.weighted_ms - self.last.weighted_ms) / (span * 1000)
            self.current_full = (state.full_total_us - self.last.full_total_us) / (span * 10_000)
            self.last = state
            if not (0 <= self.queue_mean <= QUEUE_LIMIT and 0 <= self.current_full < FULL_LIMIT):
                self.since = state.at
                return False
        return state.at - self.since >= MIN_QUIET_S


class IdleAdmission:
    def __init__(self, device, deadline, log, *, now=perf_counter, wait=sleep, observe=sample):
        self.device, self.deadline, self.log = device, deadline, log
        self.now, self.wait, self.sample = now, wait, observe
        self.quiet = QuietInterval()
        self.waiting = False
        self.last_report = float("-inf")
        self.reads = 0
        self.wait_s = 0.0

    def check_budget(self):
        remaining = self.deadline - self.now()
        if remaining <= LAST_READ_MARGIN_S:
            raise IdleWindowExpired("Idle staging opportunity reached its deadline")
        return remaining

    def details(self, state):
        return dict(full_avg10=state.full_avg10, in_flight=state.in_flight,
                    device_mean_queue=self.quiet.queue_mean, recent_full_pct=self.quiet.current_full,
                    admitted_reads=self.reads, remaining_seconds=max(0, self.deadline - self.now()))

    @contextmanager
    def slot(self, lock):
        began = self.now()
        while True:
            self.check_budget()
            state = self.sample(self.device, self.now)
            reason = "storage_busy"
            if self.quiet.observe(state):
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    reason = "gauss_busy"
                else:
                    try:
                        self.check_budget()
                        state = self.sample(self.device, self.now)
                        if self.quiet.observe(state):
                            self.wait_s += self.now() - began
                            self.reads += 1
                            if self.waiting or self.reads == 1:
                                self.log(event="idle_admitted", **self.details(state))
                            self.waiting = False
                            yield
                            return
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
            when = self.now()
            if not self.waiting or when - self.last_report >= 15:
                self.log(event="idle_wait", reason=reason, **self.details(state))
                self.last_report = when
            self.waiting = True
            self.wait(min(POLL_S, self.check_budget() - LAST_READ_MARGIN_S))
