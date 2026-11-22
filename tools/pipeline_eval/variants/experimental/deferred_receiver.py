"""Resolve delayed continuation queries with the released two-scan receiver."""

from contextlib import ExitStack, contextmanager
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ...qualification import blind_compact_run
from ...qualification.full_v5_check import _probe
from .deferred_continuation import DeferredContinuation


def _immutable_iq(samples):
    if (samples.shape != (200_000, 2, 2) or samples.dtype != np.dtype("<i2")
            or not samples.flags.c_contiguous):
        raise ValueError("deferred receiver requires a complete interleaved CI16 window")
    owner = samples
    while isinstance(owner, (np.ndarray, memoryview)):
        owner = owner.base if isinstance(owner, np.ndarray) else owner.obj
    if isinstance(owner, bytes) and not samples.flags.writeable:
        return samples
    return np.frombuffer(samples.tobytes(), dtype="<i2").reshape(samples.shape)


class _FactorCapture:
    def __init__(self):
        self.row = None

    def select(self, row):
        if self.row is not None:
            raise ValueError("one native request must capture exactly one lane")
        self.row = row
        return None, None, []


class DeferredReceiver:
    """Keep each delayed query on its original full window and physical lane."""

    def __init__(self, max_pending=64):
        self.max_pending = max_pending
        self.planner = DeferredContinuation(max_pending)
        self.native_calls = 0
        self.query_cpu_ns = 0
        self._active = False

    def wrap(self, detector):
        @contextmanager
        def deferred(method, edge, *, binary=None, pilot=None):
            if method != "cancellation" or self._active:
                raise ValueError("deferred receiver requires one independent cancellation context")
            planner = self.planner = DeferredContinuation(self.max_pending)
            self.native_calls = self.query_cpu_ns = 0
            capture = _FactorCapture()
            self._active = True
            try:
                with ExitStack() as context:
                    # Only the stock detector constructor takes the capture in place of
                    # Continuation. Its C call and candidate validation remain unchanged.
                    with patch.object(blind_compact_run, "Continuation", lambda: capture):
                        receive = context.enter_context(detector(method, edge, binary=binary,
                                                                 pilot=pilot))

                    def measure(window, lane, row):
                        request = SimpleNamespace(**vars(window), receiver_ids=(lane,))
                        started = process_time_ns()
                        try:
                            receive(request)
                            measured = capture.row
                            if measured is None or dict(measured, candidates=[]) != row:
                                raise ValueError("deferred factor metadata differs from its probe")
                            self.native_calls += 1
                            return measured["candidates"]
                        finally:
                            capture.row = None
                            self.query_cpu_ns += process_time_ns() - started

                    def select(window):
                        if not self._active or self.planner is not planner:
                            raise RuntimeError("deferred receiver scope has closed")
                        if (tuple(window.receiver_ids) != (0, 1)
                                or window.sample_rate_hz != 10_000_000):
                            raise ValueError("deferred receiver requires both 10 MS/s antennas")
                        target, acquisition = window.target, window.acquisition
                        center = (target["rf_center_hz"] - target["lnb_lo_hz"]
                                  - acquisition["actual_if_center_hz"])
                        lo, hi = center - 800000, center + 800000
                        if not (-5e6 <= lo < hi <= 5e6 and hi - lo <= 1600000):
                            raise ValueError("native exported factors disagree with the receiver")
                        fixed = SimpleNamespace(acquisition=dict(acquisition), target=dict(target),
                                                sample_rate_hz=window.sample_rate_hz,
                                                samples=_immutable_iq(window.samples))
                        rows = []
                        for lane in (0, 1):
                            row = _probe(fixed, lane, ())
                            chosen = planner.select(
                                row, lambda lane=lane, row=row: measure(fixed, lane, row),
                            )
                            rows.append(dict(row, candidates=chosen))
                        return rows

                    yield select
            finally:
                for visit in tuple(planner.pending):
                    planner.discard(visit)
                self._active = False

        return deferred
