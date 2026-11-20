"""Bounded exact reuse of the immutable scan stencil's initial track projections."""

import math
import struct
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

import numpy as np

MAX_BYTES = 48 * 1024**2
MAX_ENTRIES = 512
MAX_CHECKSUMS = 32_768
_report = ContextVar("initial_projection_reuse_receipt", default=None)


class Columns:
    def __init__(self, stencil, operation, budget=MAX_BYTES):
        self.stencil = stencil
        self.operation = operation
        self.limit = budget
        self.entries = {}
        self.retained = 0
        self.stats = dict(eligible_reads=0, hits=0, stored=0, retained_bytes=0, bypasses=0)

    def read(self, source, columns):
        if source.stencil is not self.stencil:
            return self.operation(source, columns)
        if source.last is not None and np.array_equal(columns, source.last[0]):
            return self.operation(source, columns)
        if columns.ndim != 1 or columns.dtype.kind not in "iu":
            return self.operation(source, columns)
        if set(source.options) - {"altitude_m", "rf_hz"} or len(source.coordinates) != 2:
            return self.operation(source, columns)
        lat, lon = source.coordinates
        h, rf = source.options.get("altitude_m", 0.0), source.options.get("rf_hz", 11.5e9)
        if not all(math.isfinite(value) for value in (lat, lon, h, rf)):
            return self.operation(source, columns)
        # The admitted stencil is a single live immutable instance. This key covers
        # the remaining native parameters, including signed zero and column order.
        coordinate = struct.pack("=dddd", lat, lon, h, rf)
        token = (source.operation, coordinate, columns.dtype.str, columns.tobytes())
        self.stats["eligible_reads"] += 1
        if token in self.entries:
            original_columns, values = self.entries[token]
            self.stats["hits"] += 1
            source.last = original_columns, values
            return values
        values = self.operation(source, columns)
        # Include fixed overhead, the key bytes and both copies of the indices.
        size = 1024 + 2 * columns.nbytes + sum(array.nbytes for array in values)
        if len(self.entries) < MAX_ENTRIES and self.retained + size <= self.limit:
            snapshot = columns.copy()
            for array in values:
                array.setflags(write=False)
            snapshot.setflags(write=False)
            self.entries[token] = snapshot, values
            self.retained += size
            self.stats["stored"] += 1
            self.stats["retained_bytes"] = self.retained
        else:
            self.stats["bypasses"] += 1
        return values


@contextmanager
def shared_initial_columns(stencil):
    from .direct_lifetime_kernels import TrackColumns

    if any(
        getattr(stencil, key).flags.writeable
        for key in (
            "positions",
            "velocities",
            "index",
            "fraction",
            "rotation",
        )
    ):
        raise ValueError("initial projection reuse requires an immutable orbital stencil")
    original = TrackColumns.read
    cache = Columns(stencil, original)

    # Assign a regular descriptor: TrackColumns instances remain the first argument.
    def dispatch(source, columns):
        return cache.read(source, columns)

    TrackColumns.read = dispatch
    try:
        yield
    finally:
        TrackColumns.read = original
        _report.set(cache.stats)
        cache.entries.clear()


def receipt():
    return _report.get()


def prepare_with_checksum_reuse(operation, *args, limit=MAX_CHECKSUMS, **kwargs):
    from leo.sky import propagation

    original = propagation.element_line_checksum
    checked = lru_cache(maxsize=limit)(original)

    def validate(line):
        # The admitted key covers exactly the columns the original checksum reads.
        return checked(line[:68])

    propagation.element_line_checksum = validate
    try:
        return operation(*args, **kwargs)
    finally:
        propagation.element_line_checksum = original
        count = checked.cache_info()
        _report.set(
            dict(
                hits=count.hits,
                misses=count.misses,
                entries=count.currsize,
                max_entries=count.maxsize,
            )
        )
        checked.cache_clear()
