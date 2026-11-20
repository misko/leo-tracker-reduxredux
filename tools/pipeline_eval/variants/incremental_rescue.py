"""Stock-first wide short-window detection with one isolated donor region."""

import ctypes as ct
from contextvars import ContextVar
from time import perf_counter_ns, process_time_ns

import numpy as np

from . import differential_pilot as reference
from .differential_runtime_fft import FftScout
from .incremental_rescue_graft import ENTRY, SCOUT_ENTRY

DECISIONS = ("stock_positive", "no_hint", "overlap", "donor_negative", "rescued")
PROPOSE = ct.CFUNCTYPE(ct.c_int32, ct.c_int32)


class SingleLaneScout(FftScout):
    """Use the qualified FFTW arithmetic on only the requested CI16 lane."""

    def __init__(self, library, edge):
        self.evaluate_one = getattr(ct.CDLL(str(library)), SCOUT_ENTRY)
        self.evaluate_one.argtypes = [ct.c_void_p] * 5 + [ct.c_int]
        self.evaluate_one.restype = None
        super().__init__(library, edge)

    def one_surface(self, samples, rx):
        if (
            samples.shape != (reference.SAMPLES, 2, 2)
            or samples.dtype != np.dtype("<i2")
            or rx not in (0, 1)
        ):
            raise ValueError("expected a valid lane in a dual-RX 20 ms CI16 window at 10 MS/s")
        if not self.native:
            raise RuntimeError("the differential FFTW scout is closed")
        samples = np.ascontiguousarray(samples)
        values = np.empty(reference.FRAME, dtype="<f8")
        self.evaluate_one(
            self.native,
            samples.ctypes.data,
            self.filters.ctypes.data,
            self.energy.ctypes.data,
            values.ctypes.data,
            rx,
        )
        return values

    def __call__(self, samples, edge, rx):
        if edge != self.edge:
            raise ValueError("a differential FFTW context is bound to one edge")
        scores = self.one_surface(samples, rx)
        centers = reference.ranked_centers(scores)
        return centers, [float(scores[k]) for k in centers]


class Lane(ct.Structure):
    _fields_ = [
        ("count", ct.c_int32),
        ("ordinary", ct.c_int32 * 4),
        *((name, ct.c_int32) for name in ("hint", "requested", "evaluated", "decision")),
        *((name, ct.c_double) for name in ("scout_cpu", "scout_wall", "rescue_cpu", "rescue_wall")),
    ]

    def contents(self, rx):
        first = max(0, self.hint - 1)
        return dict(
            rx=rx,
            decision=DECISIONS[self.decision],
            stock_positive=self.decision == 0,
            donor_positive=self.decision == 4,
            hint=self.hint if self.hint >= 0 else None,
            ordinary=list(self.ordinary[: self.count]),
            selected=[self.hint] if self.evaluated else [],
            requested_epochs=list(range(first, first + self.requested)),
            evaluated_epochs=list(range(first, first + self.evaluated)),
            **{
                f"{name}_ns": round(getattr(self, name) * 1e6)
                for name in ("scout_cpu", "scout_wall", "rescue_cpu", "rescue_wall")
            },
        )


class Trace(ct.Structure):
    _fields_ = [("lanes", Lane * 2)]


class IncrementalRescueCall:
    """Use the existing decoder, with a synchronous lazy callback from the native loop."""

    def __init__(self, native, edge, *, scout):
        from leo.analysis.starlink.native_short_window import _Result

        if (
            native.receiver_count != 2
            or native.sample_rate_hz != reference.RATE
            or not native.fractional_epoch
        ):
            raise ValueError("one-region rescue requires dual-RX 10 MS/s fractional short windows")
        self.native, self.edge, self.scout = native, edge, scout
        self.arguments = ContextVar("incremental_rescue_call", default=None)
        entry = getattr(native._library, ENTRY)
        entry.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            PROPOSE,
            ct.POINTER(_Result),
            ct.POINTER(Trace),
        ]
        entry.restype = ct.c_int
        ordinary = native._analyze

        def dispatch(context, raw, count, output):
            active = self.arguments.get()
            if active is None:
                return ordinary(context, raw, count, output)
            propose, trace = active
            return entry(context, raw, count, propose, output, ct.byref(trace))

        native._analyze = dispatch

    def __call__(self, samples, *, decode=None, timings=False):
        started_cpu, started_wall = process_time_ns(), perf_counter_ns()
        trace = Trace()
        proposals = [([], []), ([], [])]
        errors = []

        @PROPOSE
        def propose(rx):
            try:
                centers, scores = self.scout(samples, self.edge, rx)
                proposals[rx] = centers, scores
                return centers[0] if centers else -1
            except BaseException as error:
                errors.append(error)
                return -2

        token = self.arguments.set((propose, trace))
        try:
            payload = (decode or self.native.analyze)(samples, include_timings=timings)
        except Exception:
            if errors:
                raise errors[0] from None
            raise
        finally:
            self.arguments.reset(token)
        lanes = [lane.contents(rx) for rx, lane in enumerate(trace.lanes)]
        elapsed = {
            f"{stage}_{clock}_ns": sum(lane[f"{stage}_{clock}_ns"] for lane in lanes)
            for stage in ("scout", "rescue")
            for clock in ("cpu", "wall")
        }
        for name, total in (
            ("cpu", process_time_ns() - started_cpu),
            ("wall", perf_counter_ns() - started_wall),
        ):
            elapsed[f"combined_{name}_ns"] = total
            elapsed[f"stock_{name}_ns"] = total - sum(
                elapsed[f"{stage}_{name}_ns"] for stage in ("scout", "rescue")
            )
        return payload, proposals, lanes, elapsed
