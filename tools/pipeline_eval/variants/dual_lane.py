"""Join complete stock or fifth-center native results from two antenna contexts."""

import ctypes as ct
from contextlib import AbstractContextManager
from threading import Lock
from time import perf_counter_ns, process_time_ns

import numpy as np

from . import center_union, differential_pilot

MODES = ("stock", "fifth", "absent")


class Lane(ct.Structure):
    _fields_ = [
        ("cpu", ct.c_int32),
        ("hint", ct.c_int32),
        ("cpu_ns", ct.c_uint64),
        ("wall_ns", ct.c_uint64),
        ("union", center_union.Lane),
    ]


class Trace(ct.Structure):
    _fields_ = [("lanes", Lane * 2)]


class DualLane(AbstractContextManager):
    """Pin the optional helper to one CPU and run the first lane on the caller."""

    def __init__(self, library, edge, *, helper_cpu=-1):
        from leo.analysis.starlink import templates
        from leo.analysis.starlink.native_short_window import _Result

        rate = differential_pilot.RATE
        port = ct.CDLL(str(library))
        self.ctx, self.out, self.trace = ct.c_void_p(), _Result(), Trace()
        self.lock = Lock()
        size = port.leo_dual_lane_trace_size_v1
        size.restype = ct.c_size_t
        if size() != ct.sizeof(self.trace):
            raise ValueError("native dual-lane trace layout changed")
        create = port.leo_dual_lane_create_v1
        create.argtypes = (ct.POINTER(ct.c_void_p),) + (ct.c_void_p,) * 4 + (ct.c_int,)
        create.restype = ct.c_int
        self.call = port.leo_dual_lane_analyze_v1
        self.call.argtypes = (
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(_Result),
            ct.POINTER(Trace),
        )
        self.call.restype = ct.c_int
        self.destroy = port.leo_dual_lane_destroy_v1
        self.destroy.argtypes = (ct.c_void_p,)
        self.destroy.restype = None
        bank = differential_pilot.filters(edge)
        refs = (
            np.asarray(templates.qin_edge_pilot_frame(rate, edge), dtype="<c16"),
            np.asarray(
                templates.qin_edge_pilot_frame(
                    rate, edge, symbol_roll=templates.CONTROL_SYMBOL_ROLL
                ),
                dtype="<c16",
            ),
            np.stack([row[0] for row in bank], dtype="<c8"),
            np.stack([row[1] for row in bank], dtype="<f8"),
        )
        status = create(ct.byref(self.ctx), *(a.ctypes.data for a in refs), helper_cpu)
        if status:
            raise RuntimeError(f"unable to create dual-lane native context: {status}")

    def analyze(self, samples, mode="fifth", *, trace=False):
        with self.lock:
            return self._analyze(samples, mode, trace)

    def _analyze(self, samples, mode, trace):
        from leo.analysis.starlink.native_short_window import _ROW_COUNTS, _candidate

        start, cpu = perf_counter_ns(), process_time_ns()
        if not self.ctx.value:
            raise RuntimeError("dual-lane native context is closed")
        if (
            samples.shape != (differential_pilot.SAMPLES, 2, 2)
            or samples.dtype != np.dtype("<i2")
            or not samples.flags.c_contiguous
        ):
            raise ValueError("dual-lane detector needs two complete contiguous CI16 receiver lanes")
        status = self.call(
            self.ctx,
            MODES.index(mode),
            samples.ctypes.data,
            len(samples),
            ct.byref(self.out),
            ct.byref(self.trace) if trace else None,
        )
        typed = perf_counter_ns() - start
        if status or self.out.row_count != 2:
            raise RuntimeError(f"dual native output was not complete: {status}")
        if any(not 0 <= row.candidate_count <= 8 for row in self.out.rows[:2]):
            raise ValueError("native output changed the candidate count bounds")
        rows = [
            dict(
                {k: getattr(r, k) for k in _ROW_COUNTS},
                candidates=[_candidate(c) for c in r.candidates[: r.candidate_count]],
            )
            for r in self.out.rows[:2]
        ]
        if [r["receiver_id"] for r in rows] != [0, 1]:
            raise ValueError("native output changed the physical receiver order")
        result = dict(
            schema="leo-native-glrt-short-window/v1",
            algorithm_id="wave8-gate314-source-v1",
            sample_rate_hz=differential_pilot.RATE,
            dwell_ms=20,
            probe_ms=20,
            probe_stride_ms=20,
            receiver_count=2,
            input_complex_times=len(samples),
            window_start_sample=0,
            window_end_sample_exclusive=len(samples),
            refinement_mode="ordinary-with-fractional-epoch",
            rows=rows,
        )
        if not trace:
            return result
        wall, spent = perf_counter_ns() - start, process_time_ns() - cpu
        return result, dict(
            wall_ns=wall,
            cpu_ns=spent,
            typed_ns=typed,
            lanes=[
                dict(cpu=ln.cpu, hint=ln.hint, cpu_ns=ln.cpu_ns, wall_ns=ln.wall_ns)
                for ln in self.trace.lanes
            ],
        )

    def __exit__(self, *_):
        with self.lock:
            if self.ctx.value:
                self.destroy(self.ctx)
                self.ctx = ct.c_void_p()
