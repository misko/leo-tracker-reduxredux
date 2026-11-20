"""Expose independent coarse-activity admission on the native dual detector."""

import ctypes as ct
from math import isfinite
from threading import Lock

import numpy as np

ENTRY = "leo_native_glrt_analyze_lane_screen_v1"
RATE = 10_000_000
FLOOR = 0.152


class LaneScore(ct.Structure):
    _fields_ = [
        ("threshold", ct.c_double),
        ("coarse_max", ct.c_double),
        ("rejected", ct.c_int32),
    ]


class LaneScreen:
    """Persistent native dual detector with one independent activity score per physical lane."""

    def __init__(self, library, edge):
        from leo.analysis.starlink.native_short_window import NativeShortWindow, _Result
        from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

        self.lock = Lock()
        refs = (
            np.asarray(qin_edge_pilot_frame(RATE, edge, symbol_roll=roll), dtype="<c16")
            for roll in (0, CONTROL_SYMBOL_ROLL)
        )
        self.native = NativeShortWindow(
            str(library), *refs, sample_rate_hz=RATE, fractional_epoch=True
        )
        try:
            self.entry = getattr(self.native._library, ENTRY)
            self.entry.argtypes = (
                ct.c_void_p,
                ct.POINTER(ct.c_int16),
                ct.c_size_t,
                ct.c_double,
                ct.POINTER(_Result),
                ct.POINTER(LaneScore),
            )
            self.entry.restype = ct.c_int
            self.scores = (LaneScore * 2)()
            self.threshold = 0.0
            self.native._analyze = self._analyze
        except BaseException:
            self.native.close()
            raise

    def _analyze(self, context, samples, count, result):
        return self.entry(context, samples, count, self.threshold, result, self.scores)

    def analyze(self, samples, threshold, *, trace=False):
        """Return both physical rows and optionally each lane's actual score and decision."""
        if not isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("a coarse activity threshold must be finite and within [0, 1]")
        with self.lock:
            self.threshold = threshold
            decoded = self.native.analyze(samples, include_timings=trace)
            if threshold:
                decoded["algorithm_id"] = "wide-regional-lane-screen-v1"
            if not trace:
                return decoded
            witness = [
                dict(coarse_max=score.coarse_max, rejected=bool(score.rejected))
                for score in self.scores
            ]
            return decoded, witness

    def close(self):
        with self.lock:
            self.native.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
