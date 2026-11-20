"""Memoize one exactly repeated native normal solve in the compact phase workflow."""

import ctypes
import os
import struct
import weakref
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from time import process_time
from unittest.mock import patch

import numpy as np

METHOD = "v5_phase_cache"
MAX_INPUT = 4 * 1024**2
MAX_RESULT = 256 * 1024

_memcmp = ctypes.CDLL(None).memcmp
_memcmp.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
_memcmp.restype = ctypes.c_int


def identity(value):
    """The result key includes the original numerical representation and layout."""
    if (
        type(value) is np.ndarray
        and value.dtype.kind in "bifuc"
        and (value.flags.c_contiguous or value.flags.f_contiguous)
    ):
        return ("array", value.shape, value.dtype.str, value.strides), value.nbytes
    if isinstance(value, np.generic) and value.dtype.kind in "bifuc":
        return ("scalar", value.dtype.str, value.tobytes()), 0
    if isinstance(value, float):
        return ("float", struct.pack("=d", value)), 0
    if type(value) in (bool, int, str, type(None)):
        return (type(value), value), 0
    raise TypeError("unsupported normal-solve argument")


class NormalMemo:
    def __init__(self, active=True):
        self.active = active
        self.entry = None
        self.counts = Counter()

    def solve(self, call, backend, *args, **kwargs):
        self.counts["calls"] += 1
        now = process_time()
        try:
            return self.evaluate(call, backend, args, kwargs)
        finally:
            self.counts["cpu_s"] += process_time() - now

    def evaluate(self, call, backend, args, kwargs):
        if not self.active:
            return self.native(call, backend, args, kwargs)
        keys = tuple(sorted(kwargs))
        values = (*args, *(kwargs[k] for k in keys))
        try:
            descriptors = [identity(x) for x in values]
        except TypeError:
            self.entry = None
            return self.native(call, backend, args, kwargs)
        total = sum(n for _, n in descriptors)
        if total > MAX_INPUT:
            self.entry = None
            self.counts["input_budget_fallbacks"] += 1
            return self.native(call, backend, args, kwargs)
        signature = (len(args), keys, tuple(d for d, _ in descriptors))
        entry = self.entry
        if (
            entry is not None
            and entry[0]() is backend
            and entry[1] == os.getpid()
            and entry[2] == signature
            and all(
                not n or _memcmp(v.ctypes.data, stored, n) == 0
                for v, (_, n), stored in zip(values, descriptors, entry[3], strict=True)
            )
        ):
            self.counts["hits"] += 1
            return deepcopy(entry[4])
        self.entry = None
        del entry
        result = self.native(call, backend, args, kwargs)
        size = sum(v.nbytes for v in result.values() if isinstance(v, np.ndarray))
        if size <= MAX_RESULT:
            raw = tuple(
                v.tobytes(order="A") if n else None
                for v, (_, n) in zip(values, descriptors, strict=True)
            )
            self.entry = weakref.ref(backend), os.getpid(), signature, raw, deepcopy(result)
            self.counts["retained_bytes_peak"] = max(
                self.counts["retained_bytes_peak"],
                total + size,
            )
        else:
            self.counts["result_budget_fallbacks"] += 1
        return result

    def native(self, call, backend, args, kwargs):
        self.counts["native_calls"] += 1
        return call(backend, *args, **kwargs)


@contextmanager
def normal_memo(active):
    from leo.analysis.localization_v4.backend import ProcessBound

    operation = ProcessBound.__call__
    memo = NormalMemo(active)

    def solve(backend, *args, **kwargs):
        return memo.solve(operation, backend, *args, **kwargs)

    with patch.object(ProcessBound, "__call__", solve):
        yield memo.counts
