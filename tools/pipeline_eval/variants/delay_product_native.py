"""Portable C implementations of decimation and local coherent frequency estimation."""

import ctypes as ct
import os
import subprocess
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy import signal

SOURCE = Path(__file__).with_name("delay_product_kernel.c")


def compile_kernel(work):
    work.mkdir(exist_ok=True, parents=True)
    compiler = os.environ.get("CC", "cc")
    flags = ["-O3", "-std=c11", "-fopenmp-simd", "-ffp-contract=off", "-fPIC", "-shared"]
    identity = sha256(SOURCE.read_bytes() + compiler.encode() + repr(flags).encode()).hexdigest()[
        :16
    ]
    path = work / ("delay-" + identity + ".so")
    if not path.exists():
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        subprocess.run([compiler, *flags, str(SOURCE), "-lm", "-o", str(tmp)], check=True)
        tmp.replace(path)
    return path


@lru_cache(maxsize=4)
def coefficients(stride):
    return signal.firwin(20 * stride + 1, 1 / stride, window=("kaiser", 5.0)).astype(np.float32)


class Kernel:
    def __init__(self, path):
        self.lib = ct.CDLL(str(path))
        self.lib.delay_decimate.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
            ct.c_void_p,
        ]
        self.lib.delay_refine.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
            ct.c_double,
            ct.c_double,
            ct.c_void_p,
        ]

    def decimate(self, samples, stride):
        h = coefficients(stride)
        out = np.empty(len(samples) // stride, np.complex64)
        samples = np.ascontiguousarray(samples, dtype=np.complex64)
        if samples.shape != (200000,) or self.lib.delay_decimate(
            samples.ctypes.data, h.ctypes.data, len(h), stride, out.ctypes.data
        ):
            raise ValueError("invalid input to native decimator")
        return out

    def refine(self, samples, code, epoch, hz, lo, hi):
        a = np.ascontiguousarray(samples, dtype=np.complex64)
        c = np.ascontiguousarray(code, dtype=np.complex64)
        out = np.empty(4, float)
        if (
            a.shape != (200000,)
            or c.shape != (2816,)
            or self.lib.delay_refine(
                a.ctypes.data, c.ctypes.data, epoch, hz, lo, hi, out.ctypes.data
            )
        ):
            raise ValueError("invalid input to native pilot refiner")
        return dict(epoch=out[0], hz=out[1], sample=int(out[2]), score=out[3])
