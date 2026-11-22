"""Opt-in native path selection for the original Graph track preparation."""

from collections import Counter
from contextlib import contextmanager
from ctypes import CDLL, POINTER, byref, c_double, c_int64, c_uint32, c_void_p
from hashlib import sha256
from pathlib import Path
import platform
import subprocess
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis import graph_tracklets as graph
from leo.analysis.localization_v3 import tracks


ABI_VERSION = 1
REFERENCE_SHA256 = "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27"


def build(library):
    source = Path(__file__).with_suffix(".c")
    subprocess.run(
        ["cc", "-std=c11", "-O3", "-fPIC", "-shared", "-fno-fast-math", "-ffp-contract=off",
         "-frounding-math", str(source), "-o", str(library)],
        check=True,
    )


def vector(value, dtype, length):
    return (isinstance(value, np.ndarray) and value.dtype == dtype
            and value.shape == (length,) and value.flags.c_contiguous and value.flags.aligned)


def adjacency(rows, endpoint, points):
    if len(rows) != points:
        return None
    lengths = np.array([len(row) for row in rows], dtype=np.int64)
    offsets = np.r_[0, np.cumsum(lengths)]
    if offsets[-1] != len(endpoint):
        return None
    ids = np.concatenate(rows) if points else np.empty(0, dtype=np.int64)
    if not vector(ids, np.dtype("int64"), len(endpoint)) or not np.all((ids >= 0) & (ids < len(ids))):
        return None
    nodes = np.repeat(np.arange(points), lengths)
    if not np.array_equal(endpoint[ids], nodes):
        return None
    if np.any((nodes[1:] == nodes[:-1]) & (ids[1:] <= ids[:-1])):
        return None
    return offsets, ids


def pack(t, original):
    source, target, duration, velocity, incoming, outgoing = original
    points, edges = len(t), len(source)
    if edges >= 2**27 or not all(vector(a, np.dtype("int64"), edges) for a in (source, target)):
        return None
    if not all(vector(a, np.dtype("float64"), size)
               for a, size in ((t, points), (duration, edges), (velocity, edges))):
        return None
    if (not np.all((source >= 0) & (target < points) & (source < target))
            or not np.all(np.abs(t) <= 2**40) or not np.all(np.abs(velocity) <= 2**40)
            or not np.all((duration >= 2**-20) & (duration <= 2**20))):
        return None
    before, after = adjacency(incoming, target, points), adjacency(outgoing, source, points)
    if before is None or after is None:
        return None
    return t, source, target, duration, velocity, *before, *after


class NativePath:
    def __init__(self, library):
        if platform.machine() != "x86_64":
            raise ValueError("The native Graph path ABI requires x86-64")
        try:
            self.library = CDLL(str(library))
            abi = self.library.leo_graph_path_abi
            self.operation = self.library.leo_graph_path_v1
        except (OSError, AttributeError) as exc:
            raise ValueError("Could not load the versioned native Graph path ABI") from exc
        abi.argtypes = []
        abi.restype = c_uint32
        if abi() != ABI_VERSION:
            raise ValueError("Unsupported native Graph path ABI version")
        self.operation.restype = c_int64
        self.operation.argtypes = ([c_int64, c_int64] + [c_void_p] * 11
                                  + [c_double, c_double, c_double, c_int64, c_double,
                                     c_void_p, POINTER(c_double)])

    def solve(self, packed, y, available, enabled, cfg):
        t, source, target, duration, velocity, *_ = packed
        points, edges = len(t), len(source)
        if (not vector(available, np.dtype(bool), points)
                or not vector(enabled, np.dtype(bool), edges)
                or not vector(y, np.dtype("float64"), points)
                or not all(type(value) in (float, int) for value in (
                    cfg.association_sigma, cfg.track_penalty, cfg.noise_sigma_hz, cfg.min_span_s))):
            return None
        if (not 2**-20 <= cfg.noise_sigma_hz <= 2**20
                or not 0 < cfg.association_sigma <= 2**20
                or not 0 <= cfg.track_penalty <= 2**40
                or not 0 < cfg.min_span_s <= 2**40
                or not 3 <= cfg.min_points < 2**63):
            return None
        path = np.empty(points, dtype=np.int64)
        value = c_double()
        count = self.operation(
            points, edges, *(array.ctypes.data for array in (*packed, available, enabled)),
            cfg.association_sigma**2, cfg.track_penalty, 2 * cfg.noise_sigma_hz**2,
            cfg.min_points, cfg.min_span_s, path.ctypes.data, byref(value),
        )
        if count < 0:
            return None
        edges = path[:count][::-1].copy()
        if not count:
            return np.array([], int), np.array([]), edges, 0.0
        path = np.r_[source[edges], target[edges[-1]]]
        lifted = y[path[0]] + np.r_[0.0, np.cumsum(velocity[edges] * duration[edges])]
        return path, lifted, edges, value.value


@contextmanager
def native_paths(library, *, verify=False, required=False):
    """Scope a private packing cache to one lane and call the original on fallback."""
    metrics = Counter()
    try:
        if sha256(Path(graph.__file__).read_bytes()).hexdigest() != REFERENCE_SHA256:
            raise ValueError("The reference Graph path source differs from the reviewed recurrence")
        kernel = NativePath(library)
    except (OSError, ValueError):
        if required:
            raise
        metrics["unavailable"] = 1
        yield metrics
        return
    fit_lane = tracks.fit_lane

    def scoped_lane(*args, **kwargs):
        reference = graph._best_path
        packed, input_graph = None, None

        def search(t, y, original, available, enabled, cfg):
            nonlocal packed, input_graph
            if input_graph is not original:
                start = process_time_ns()
                packed, input_graph = pack(t, original), original
                metrics["pack_ns"] += process_time_ns() - start
                metrics["packed_lanes" if packed is not None else "unpacked_lanes"] += 1
            start = process_time_ns()
            result = kernel.solve(packed, y, available, enabled, cfg) if packed is not None else None
            metrics["search_ns"] += process_time_ns() - start
            if result is None:
                metrics["reference_paths"] += 1
                return reference(t, y, original, available, enabled, cfg)
            metrics["native_paths"] += 1
            if verify:
                expected = reference(t, y, original, available, enabled, cfg)
                if any(actual.tobytes() != prior.tobytes() for actual, prior in
                       zip(result[:3], expected[:3], strict=True)) or result[3].hex() != expected[3].hex():
                    raise AssertionError("Native ordered path differs from the reference recurrence")
                metrics["verified_paths"] += 1
            return result

        with patch.object(graph, "_best_path", search):
            return fit_lane(*args, **kwargs)

    with patch.object(tracks, "fit_lane", scoped_lane):
        yield metrics
