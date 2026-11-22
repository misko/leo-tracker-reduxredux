"""Experimental scan-local memo for byte-identical ordinary likelihood calls."""

import ctypes as ct
from collections import Counter, OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

DEFAULTS = dict(prior_groups=None, powers=1.0, noise_nu=4.0, prior_nu=4.0, iterations=256)


def ordinary_arrays(values):
    arrays, descriptors = [], []
    for value in values:
        if value is None:
            arrays.append(None)
            descriptors.append(None)
            continue
        if type(value) not in (np.ndarray, int, float) and not isinstance(value, np.generic):
            return None
        array = np.asarray(value)
        if array.dtype.kind not in "fiub" or not array.flags.c_contiguous:
            return None
        arrays.append(array)
        descriptors.append((type(value), array.dtype.str, array.shape, array.strides))
    return arrays, tuple(descriptors)


def small_signature(arrays):
    raw, design, *other = arrays
    n, p = design.shape
    rows, cols = [0, n//2, n-1], [0, p//2, p-1]
    sampled = raw[rows].tobytes(), design[np.ix_(rows, cols)].tobytes() if p else b""
    return sampled + tuple(sha256(memoryview(a).cast("B") if a.size else b"").digest()
                           if a is not None else b"" for a in other)


class Memo:
    def __init__(self, limit):
        self.limit = limit
        self.entries = OrderedDict()
        self.bytes = 0
        self.counts = Counter()
        self.memcmp = ct.CDLL(None).memcmp
        self.memcmp.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t]
        self.memcmp.restype = ct.c_int

    def lookup(self, key, arrays):
        old = self.entries.get(key)
        if old is None:
            return None
        witness, result, _ = old
        if any(self.memcmp(a.ctypes.data, b.ctypes.data, a.nbytes)
               for a, b in zip(arrays, witness, strict=True) if a is not None and a.nbytes):
            self.counts["hint_collisions"] += 1
            return None
        self.entries.move_to_end(key)
        self.counts["hits"] += 1
        return deepcopy(result)

    def insert(self, key, arrays, value):
        nbytes = sum(a.nbytes for a in arrays if a is not None)
        nbytes += sum(np.asarray(a).nbytes for a in value.values())
        if nbytes > self.limit:
            return
        previous = self.entries.pop(key, None)
        if previous is not None:
            self.bytes -= previous[2]
        while self.bytes + nbytes > self.limit:
            _, expired = self.entries.popitem(last=False)
            self.bytes -= expired[2]
        witness = tuple(a.copy() if a is not None else None for a in arrays)
        self.entries[key] = witness, deepcopy(value), nbytes
        self.bytes += nbytes
        self.counts["witness_bytes_copied"] += nbytes
        self.counts["peak_bytes"] = max(self.counts["peak_bytes"], self.bytes)


@contextmanager
def ordinary_likelihood_reuse(*, maximum_bytes=64 * 2**20):
    memo = Memo(maximum_bytes)
    bound, original_grid = native_bound.NativeBound.__call__, handoff.grid_handoff

    def grid():
        return False

    def grid_handoff(port, library, in_grid):
        nonlocal grid
        grid = in_grid
        return original_grid(port, library, in_grid)

    def call(owner, raw, features, sigma, groups, **options):
        if grid():
            memo.counts["grid_bypasses"] += 1
            return bound(owner, raw, features, sigma, groups, **options)
        start = process_time_ns()
        original = (raw, features, sigma, groups)
        evidence = None
        if not (options.keys() - DEFAULTS.keys()):
            evidence = ordinary_arrays((*original, *(DEFAULTS | options).values()))
        if evidence is None or raw is None or features is None:
            return bound(owner, *original, **options)
        arrays, descriptors = evidence
        if (arrays[0].ndim != 1 or arrays[1].ndim != 2 or not len(arrays[0])
                or arrays[1].shape[0] != len(arrays[0])):
            return bound(owner, *original, **options)
        # Bind the configured provider, original fallback, and conditioning to this owner.
        key = (owner, owner.run, owner.original, owner.min_rcond, descriptors,
               small_signature(arrays))
        result = memo.lookup(key, arrays)
        memo.counts["lookup_cpu_ns"] += process_time_ns() - start
        memo.counts["lookups"] += 1
        if result is not None:
            return result
        memory_errors = owner.counts["fallback_memory"]
        result = bound(owner, *original, **options)
        if owner.counts["fallback_memory"] == memory_errors:
            start = process_time_ns()
            memo.insert(key, arrays, result)
            memo.counts["insert_cpu_ns"] += process_time_ns() - start
        return result

    with (
        patch.object(handoff, "grid_handoff", grid_handoff),
        patch.object(native_bound.NativeBound, "__call__", call),
    ):
        yield memo.counts
