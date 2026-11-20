"""Development binding for the standalone original coarse acquisition."""

import ctypes as ct
import os
import subprocess
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).with_suffix(".c")
HEADER = SOURCE.with_suffix(".h")
QIN = SOURCE.with_name("portable_coarse_qin.h")
EPOCHS = 13_333
SEEDS = 8
FLAGS = (
    "-std=c11",
    "-O3",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-ffp-contract=off",
    "-fopenmp-simd",
    "-fno-math-errno",
    "-fno-trapping-math",
)


class Capture(ct.Structure):
    _fields_ = (
        ("samples", ct.c_uint),
        ("edge", ct.c_uint),
        ("lane_mask", ct.c_uint),
        ("center_hz", ct.c_double * 2),
        ("low_hz", ct.c_double),
        ("high_hz", ct.c_double),
    )


class Seed(ct.Structure):
    _fields_ = (
        ("epoch", ct.c_uint),
        ("bins", ct.c_uint),
        ("absolute_hz", ct.c_double),
        ("residual_hz", ct.c_double),
    )


class Peak(ct.Structure):
    _fields_ = (
        ("score", ct.c_double),
        ("residual_hz", ct.c_double),
        ("original_epoch", ct.c_uint),
        ("refined_epoch", ct.c_uint),
        ("cfo_lane", ct.c_uint),
    )


def build(work):
    target = work / "portable_coarse.so"
    command = [
        "cc",
        *FLAGS,
        "-march=x86-64-v3",
        "-shared",
        "-fPIC",
        str(SOURCE),
        "-lm",
        "-o",
        str(target),
    ]
    subprocess.run(command, check=True, env=os.environ | {"TMPDIR": str(work)}, timeout=30)
    return target, command


def unpack(structure):
    return {k: getattr(structure, k) for k, _ in structure._fields_}


class Coarse:
    def __init__(self, library, edge):
        self.library = lib = ct.CDLL(str(library))
        self.edge = ("lower", "upper").index(edge)
        lib.portable_coarse_create.argtypes = (ct.c_uint,)
        lib.portable_coarse_create.restype = ct.c_void_p
        lib.portable_coarse_free.argtypes = (ct.c_void_p,)
        lib.portable_coarse_free.restype = None
        lib.portable_coarse_workspace_bytes.argtypes = ()
        lib.portable_coarse_workspace_bytes.restype = ct.c_size_t
        lib.portable_coarse_template.argtypes = (ct.c_void_p, ct.c_uint)
        lib.portable_coarse_template.restype = ct.POINTER(ct.c_double)
        lib.portable_coarse_scores.argtypes = (ct.c_void_p, ct.POINTER(ct.c_uint))
        lib.portable_coarse_scores.restype = ct.POINTER(ct.c_double)
        lib.portable_coarse_support.argtypes = (ct.c_void_p,)
        lib.portable_coarse_support.restype = ct.POINTER(ct.c_uint16)
        lib.portable_coarse_acquire.argtypes = (
            ct.c_void_p,
            ct.c_void_p,
            ct.POINTER(Capture),
            ct.c_uint,
            ct.c_uint,
            ct.POINTER(Seed),
            ct.POINTER(Peak),
            ct.POINTER(ct.c_uint),
        )
        lib.portable_coarse_acquire.restype = ct.c_int
        self.handle = lib.portable_coarse_create(self.edge)
        if not self.handle:
            raise MemoryError("standalone coarse workspace allocation failed")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.library.portable_coarse_free(self.handle)

    @property
    def workspace_bytes(self):
        return self.library.portable_coarse_workspace_bytes()

    def template(self, control=False):
        data = self.library.portable_coarse_template(self.handle, int(control))
        return np.ctypeslib.as_array(data, shape=(2 * EPOCHS,)).copy().view(np.complex128)

    def acquire(self, raw, lane, anchors, centers, limits, *, lane_mask=3):
        if raw.ndim != 3 or raw.shape[1:] != (2, 2) or raw.dtype != np.int16:
            raise ValueError("expected real stereo CI16")
        raw = np.ascontiguousarray(raw)
        header = Capture(len(raw), self.edge, lane_mask, (ct.c_double * 2)(*centers), *limits)
        seeds, peaks, number = (Seed * SEEDS)(), (Peak * SEEDS)(), ct.c_uint()
        status = self.library.portable_coarse_acquire(
            self.handle,
            raw.ctypes.data,
            ct.byref(header),
            lane,
            anchors,
            seeds,
            peaks,
            ct.byref(number),
        )
        if status:
            raise ValueError("unsupported standalone coarse capture geometry")
        return [unpack(seeds[i]) for i in range(number.value)], [
            unpack(peaks[i]) for i in range(number.value)
        ]

    def grid(self):
        count = ct.c_uint()
        grid = self.library.portable_coarse_scores(self.handle, ct.byref(count))
        support = self.library.portable_coarse_support(self.handle)
        return (
            np.ctypeslib.as_array(grid, shape=(count.value * EPOCHS,)).copy().reshape(-1, EPOCHS),
            np.ctypeslib.as_array(support, shape=(EPOCHS,)).copy(),
        )
