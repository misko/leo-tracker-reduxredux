"""Standalone five-refresh compact cavity with bounded numerical working sets."""

import ctypes
import gc
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache

METHOD = "v5_direct_lifetime"
columns_active = ContextVar("compact_track_columns", default=False)


@contextmanager
def projection_columns():
    token = columns_active.set(True)
    try:
        yield
    finally:
        columns_active.reset(token)


def project(operation, stencil, coordinates, options):
    if columns_active.get():
        from .direct_lifetime_kernels import TrackColumns, TrackField

        source = TrackColumns(operation, stencil, coordinates, options, Counter())
        return tuple(TrackField(source, k) for k in range(3))
    return operation(stencil, *coordinates, **options)


def regional_bank(*args, **kwargs):
    from leo.analysis.localization_v3 import orbits

    from .direct_lifetime_kernels import regional_bank as streamed

    return streamed(orbits, Counter(), *args, **kwargs)


def phase_history(prepare, parser, archive, elements, metadata):
    from .direct_lifetime_kernels import last_use

    with last_use(parser, {}) as consume:
        return prepare(archive, elements, metadata, element_parser=consume)


def phase_widths(scan, labels):
    from leo.analysis.localization_v3.retained_position import phase_widths as widths

    from .direct_lifetime_kernels import alignment_only

    return widths(scan, labels, bank_reader=alignment_only)


def dispose_model(model):
    for name in (
        "calculate",
        "curved_calculate",
        "state",
        "conditional_frequency",
        "_fixed_phase_geometry_cache",
    ):
        model.__dict__.pop(name, None)


@cache
def arena_trim():
    trim = ctypes.CDLL(None).malloc_trim
    trim.argtypes = [ctypes.c_size_t]
    trim.restype = ctypes.c_int
    return trim


def reclaim():
    gc.collect()
    arena_trim()(0)


def main():
    from . import v5_direct_cavity

    if v5_direct_cavity.METHOD != METHOD:
        raise RuntimeError("Use the source-bound direct lifetime release bundle")
    v5_direct_cavity.main()


if __name__ == "__main__":
    main()
