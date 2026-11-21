"""Resident standalone time-first receiver for a 20 ms signed stereo capture."""

import ctypes as ct
import os
import subprocess
from pathlib import Path

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from . import delay_product_native as native

SOURCE = Path(__file__).with_suffix(".c")
HEADER = SOURCE.with_suffix(".h")
FLAGS = [
    "-O3",
    "-std=c11",
    "-fopenmp-simd",
    "-ffp-contract=off",
    "-fno-math-errno",
    "-fno-strict-aliasing",
]


def build(directory):
    from hashlib import sha256

    directory.mkdir(exist_ok=True, parents=True)
    cc = os.environ.get("CC", "cc")
    signature = sha256(
        b"".join(p.read_bytes() for p in (SOURCE, HEADER, native.SOURCE))
        + repr([cc, *FLAGS]).encode()
    ).hexdigest()[:16]
    path = directory / ("timing-first-" + signature + ".so")
    if not path.exists():
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        subprocess.run(
            [
                cc,
                *FLAGS,
                "-shared",
                "-fPIC",
                str(SOURCE),
                str(native.SOURCE),
                "-lm",
                "-o",
                str(tmp),
            ],
            check=True,
        )
        tmp.replace(path)
    return path


class Result(ct.Structure):
    _fields_ = [
        ("epoch", ct.c_double),
        ("hz", ct.c_double),
        ("score", ct.c_double),
        ("confirmation", ct.c_int),
    ]


class Receiver:
    def __init__(self, path, edge, physical=False):
        lib = self.lib = ct.CDLL(str(path))
        lib.timing_first_create.argtypes = [ct.c_int, ct.c_void_p, ct.c_void_p]
        lib.timing_first_create.restype = ct.c_void_p
        lib.timing_first_free.argtypes = [ct.c_void_p]
        lib.timing_first_free.restype = None
        lib.timing_first_detect.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
            ct.c_double,
            ct.POINTER(Result),
        ]
        lib.timing_first_bytes.argtypes = [ct.c_void_p]
        lib.timing_first_bytes.restype = ct.c_size_t
        pilot = qin_edge_pilot_frame(10000000, edge)
        taps = native.coefficients(4)
        self.ctx = lib.timing_first_create(
            1 if physical else 4, pilot.ctypes.data, taps.ctypes.data
        )
        if not self.ctx:
            raise MemoryError("time-first receiver initialization failed")
        self.workspace_bytes = lib.timing_first_bytes(self.ctx)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.lib.timing_first_free(self.ctx)
        self.ctx = None

    def __call__(self, iq, lane, lo, hi):
        if (
            not self.ctx
            or iq.shape != (200000, 2, 2)
            or iq.dtype.str != "<i2"
            or not iq.flags.c_contiguous
        ):
            raise ValueError("expected a resident receiver and contiguous two-antenna 10 MS/s CI16")
        result = Result()
        if self.lib.timing_first_detect(self.ctx, iq.ctypes.data, lane, lo, hi, ct.byref(result)):
            raise ValueError("invalid receiver lane or physical frequency range")
        if result.confirmation:
            return dict(
                epoch=result.epoch,
                hz=result.hz,
                score=result.score,
                confirmation={1: "later_symbols", 2: "seven_frame_pairs"}[result.confirmation],
            )
        return None
