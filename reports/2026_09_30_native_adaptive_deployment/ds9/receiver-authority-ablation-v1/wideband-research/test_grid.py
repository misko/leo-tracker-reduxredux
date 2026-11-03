#!/usr/bin/env python3
"""Capacity and endpoint tests for the isolated wideband reference grid."""

from __future__ import annotations

import argparse
import ctypes
import math
from pathlib import Path


def invoke(function: object, start: float, stop: float, capacity: int) -> tuple[int, list[float]]:
    sentinel = 9.87654321e123
    values = (ctypes.c_double * 22)(*[sentinel] * 22)
    count = function(start, stop, values, capacity)
    if count < 0:
        assert list(values) == [sentinel] * 22, "rejection wrote output"
        return count, []
    return count, list(values[:count])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    library = ctypes.CDLL(str(args.library.resolve()))
    grid = library.leo_full_search_reference_grid_probe
    grid.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.c_size_t]
    grid.restype = ctypes.c_int

    count, values = invoke(grid, -440_000.0, 440_000.0, 22)
    assert count == 12 and values == [-440_000.0 + 80_000.0 * k for k in range(12)]

    # The frozen 1e-9 endpoint tolerance intentionally treats one binary64
    # step above the aligned endpoint as equal to that endpoint.
    count, values = invoke(grid, -440_000.0, math.nextafter(440_000.0, math.inf), 22)
    assert count == 12 and values[-1] == 440_000.0

    stop = 440_000.0 + 1e-6
    assert invoke(grid, -440_000.0, stop, 12)[0] == -1
    count, values = invoke(grid, -440_000.0, stop, 22)
    assert count == 13 and values[-2] == 440_000.0 and values[-1] == stop

    assert invoke(grid, -450_000.0, 450_000.0, 12)[0] == -1
    count, values = invoke(grid, -450_000.0, 450_000.0, 22)
    assert count == 13 and values[-1] == 450_000.0

    count, values = invoke(grid, -800_000.0, 800_000.0, 22)
    assert count == 21 and values[0] == -800_000.0 and values[-1] == 800_000.0

    for start, stop in (
        (math.nan, 1.0),
        (0.0, math.inf),
        (1.0, 0.0),
    ):
        assert invoke(grid, start, stop, 22)[0] == -1

    print("wideband reference grid: endpoint and fail-before-write tests pass")


if __name__ == "__main__":
    main()
