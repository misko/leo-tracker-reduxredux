"""Desktop-only bindings for the whole-dwell proposal experiment."""

from __future__ import annotations

import ctypes as ct
import struct
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.native_presence import array, pointer


class RankResult(ct.Structure):
    _fields_ = [
        ("scores", ct.c_double * 6),
        ("order", ct.c_uint32 * 6),
        ("projected_epoch_samples", ct.c_uint32 * 6),
        *[
            (name, ct.c_double)
            for name in ("fold_cpu_ms", "correlation_cpu_ms", "total_cpu_ms", "total_wall_ms")
        ],
    ]


class RankScreens(ct.Structure):
    _fields_ = [
        ("available_mask", ct.c_uint32),
        ("selected", ct.c_uint32),
        ("scores", (ct.c_double * 6) * 2),
        ("contrast", ct.c_double * 2),
        ("order", (ct.c_uint32 * 6) * 2),
        ("epochs", (ct.c_uint32 * 6) * 2),
    ]


def read_screens(library, workspace, function):
    if not workspace:
        raise ValueError("native workspace is closed")
    getter = getattr(library, function)
    getter.argtypes = [ct.c_void_p, ct.POINTER(RankScreens)]
    getter.restype = ct.c_int
    screens = RankScreens()
    if getter(workspace, ct.byref(screens)):
        raise ValueError("no completed dwell screen available")
    return screens


def write_rank_probe(path: Path, iq, rate: int, edge: str, counter: int):
    values = np.asarray(iq)
    if (
        type(rate) is not int
        or rate not in (2500000, 5000000)
        or edge not in ("lower", "upper")
        or values.dtype != np.dtype("int16")
        or values.shape != (rate * 120 // 1000, 2)
        or type(counter) is not int
        or not 0 <= counter <= 2**64 - 1 - len(values)
    ):
        raise ValueError("complete single-RX CI16 dwell and exact uint64 interval required")
    if any(path.resolve().is_relative_to(p) for p in (Path("/mnt/qnap01"), Path("/srv/bulk/leo"))):
        raise ValueError("replay output cannot be written under archive storage")
    with path.open("xb") as stream:
        stream.write(
            struct.pack("<4sIIIIQ", b"LRK1", rate, int(edge == "upper"), len(values), 2, counter)
        )
        stream.write(np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16").tobytes())
        stream.write(values.astype("<i2").tobytes())


class NativeWindowRank:
    def __init__(self, library: Path, rate: int, edge: str, bins: int):
        if (
            type(rate) is not int
            or rate not in (2500000, 5000000)
            or edge not in ("lower", "upper")
        ):
            raise ValueError("unsupported rank geometry")
        if type(bins) is not int or bins not in (512, 1024, 2048, 4096, 8192):
            raise ValueError("unsupported rank grid")
        self.rate = rate
        self.library = ct.CDLL(str(library))
        self.library.leo_presence_rank_create.argtypes = [
            ct.c_uint32,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
        ]
        self.library.leo_presence_rank_create.restype = ct.c_void_p
        self.library.leo_presence_rank_destroy.argtypes = [ct.c_void_p]
        self.library.leo_presence_rank_destroy.restype = None
        self.library.leo_presence_rank_ci16.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(RankResult),
        ]
        self.library.leo_presence_rank_ci16.restype = ct.c_int
        exact = array(qin_edge_pilot_frame(rate, edge))
        self.workspace = self.library.leo_presence_rank_create(
            rate, pointer(exact), len(exact), bins
        )
        if not self.workspace:
            raise ValueError("native rank initialization failed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.workspace:
            self.library.leo_presence_rank_destroy(self.workspace)
            self.workspace = None

    def run(self, iq):
        if not self.workspace:
            raise ValueError("rank workspace is closed")
        values = np.asarray(iq)
        if values.dtype != np.dtype("int16") or values.shape != (self.rate * 120 // 1000, 2):
            raise ValueError("one complete CI16 RX dwell required")
        values = np.ascontiguousarray(values)
        result = RankResult()
        if self.library.leo_presence_rank_ci16(
            self.workspace, pointer(values), len(values), ct.byref(result)
        ):
            raise ValueError("native rank rejected input")
        return result

    def screens(self):
        return read_screens(self.library, self.workspace, "leo_presence_rank_get_screens")
