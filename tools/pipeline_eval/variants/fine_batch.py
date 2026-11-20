"""Batch the qualified prefix FFT across independent capture frame lanes."""

import ctypes
import os
import subprocess
from pathlib import Path

import numpy as np

from . import fine_search

SOURCE = Path(__file__).with_suffix(".c")
LANES = 4


def supports_host():
    return bool(np._core._multiarray_umath.__cpu_features__.get("AVX2"))


def build(work):
    if not supports_host():
        raise RuntimeError("the batched fine transform requires AVX2 support")
    library = work / "fine_batch.so"
    command = ["cc", *fine_search.FLAGS, "-mavx2", str(SOURCE), "-lm", "-o", str(library)]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, check=True)
    return library, command


class FineBatch(fine_search.FineSearch):
    """Share arithmetic across frame lanes while keeping producer normalization."""

    def __init__(self, library, acquisition):
        if not supports_host():
            raise RuntimeError("the batched fine transform requires AVX2 support")
        super().__init__(library, acquisition)
        if not self.compatible:
            return
        transform = ctypes.CDLL(str(library)).fine_batch_transform
        transform.argtypes = self.transform.argtypes
        transform.restype = None
        self.transform = transform
        # C vector loads need 32-byte alignment independently of NumPy's allocator.
        size = LANES * self.work.size
        buf = np.empty(size + 2, dtype=np.complex128)
        start = (-buf.ctypes.data % 32) // buf.itemsize
        self.work = buf[start : start + size]
        self.compatible = self._matches_runtime()
