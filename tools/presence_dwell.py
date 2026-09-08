"""Desktop bindings for end-to-end native screening and confirmation research."""

from __future__ import annotations

import ctypes as ct
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import Nuisance, Result, array, pointer
from tools.presence_window_rank import RankResult


class TimingProposal(ct.Structure):
    _fields_ = [("epoch", ct.c_uint32)] + [
        (name, ct.c_double)
        for name in ("score", "fold_cpu_ms", "correlation_cpu_ms", "total_cpu_ms", "total_wall_ms")
    ]


class DwellResult(ct.Structure):
    _fields_ = [
        ("rank", RankResult),
        ("confirmation_count", ct.c_uint32),
        ("confirmation_window_mask", ct.c_uint32),
        ("confirmations", Result * 6),
        ("nuisances", Nuisance * 6),
        ("prefix_cpu_ms", ct.c_double * 6),
        ("prefix_wall_ms", ct.c_double * 6),
        ("total_cpu_ms", ct.c_double),
        ("total_wall_ms", ct.c_double),
        ("timing_proposals", TimingProposal * 6),
    ]


def unpack(value):
    """Serialize research structures only; this is not a wire ABI."""
    if isinstance(value, ct.Structure):
        return {name: unpack(getattr(value, name)) for name, _ in value._fields_}
    if isinstance(value, ct.Array):
        return [unpack(x) for x in value]
    return value


class NativeDwell:
    def __init__(
        self, library: Path, rate: int, edge: str, bins: int, timing_bins: int | None = None
    ):
        if (
            type(rate) is not int
            or rate not in (2500000, 5000000)
            or edge not in ("lower", "upper")
        ):
            raise ValueError("unsupported dwell geometry")
        if type(bins) is not int or bins not in (512, 1024, 2048, 4096, 8192):
            raise ValueError("unsupported proposal grid")
        if timing_bins is not None and (
            type(timing_bins) is not int or timing_bins not in (512, 1024, 2048, 4096, 8192)
        ):
            raise ValueError("unsupported timing grid")
        self.rate = rate
        self.library = ct.CDLL(str(library))
        self.library.leo_presence_dwell_create.argtypes = [
            ct.c_uint32,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
        ]
        self.library.leo_presence_dwell_create.restype = ct.c_void_p
        self.library.leo_presence_dwell_destroy.argtypes = [ct.c_void_p]
        self.library.leo_presence_dwell_destroy.restype = None
        self.library.leo_presence_dwell_run_ci16.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
            ct.c_uint32,
            ct.POINTER(DwellResult),
        ]
        self.library.leo_presence_dwell_run_ci16.restype = ct.c_int
        exact, control = [array(qin_edge_pilot_frame(rate, edge, symbol_roll=k)) for k in (0, 17)]
        if timing_bins is not None:
            self.library.leo_presence_dwell_create_multires.argtypes = [
                *self.library.leo_presence_dwell_create.argtypes,
                ct.c_uint32,
            ]
            self.library.leo_presence_dwell_create_multires.restype = ct.c_void_p
            self.workspace = self.library.leo_presence_dwell_create_multires(
                rate, pointer(exact), pointer(control), len(exact), bins, timing_bins
            )
        else:
            self.workspace = self.library.leo_presence_dwell_create(
                rate, pointer(exact), pointer(control), len(exact), bins
            )
        if not self.workspace:
            raise ValueError("native dwell initialization failed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_presence_dwell_destroy(self.workspace)
            self.workspace = None

    def run(self, iq, *, maximum=6, seeded=True):
        if not self.workspace:
            raise ValueError("native dwell workspace is closed")
        values = np.asarray(iq)
        if (
            values.dtype != np.dtype("int16")
            or values.shape != (self.rate // 50 * 6, 2)
            or type(maximum) is not int
            or not 1 <= maximum <= 6
            or type(seeded) is not bool
        ):
            raise ValueError("complete CI16 dwell and bounded confirmation policy required")
        values = np.ascontiguousarray(values)
        result = DwellResult()
        if self.library.leo_presence_dwell_run_ci16(
            self.workspace, pointer(values), len(values), maximum, int(seeded), ct.byref(result)
        ):
            raise ValueError("native dwell rejected input")
        return result
