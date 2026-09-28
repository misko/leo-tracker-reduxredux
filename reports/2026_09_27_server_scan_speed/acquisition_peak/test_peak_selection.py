from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
MODULE_NAME = "leo.analysis.starlink._acquisition_peak_candidate"
SPEC = importlib.util.spec_from_file_location(
    MODULE_NAME,
    HERE / "candidate" / "acquisition.py",
)
assert SPEC is not None and SPEC.loader is not None
candidate = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = candidate
SPEC.loader.exec_module(candidate)


def _reference(
    residuals: tuple[float, ...],
    rows: tuple[np.ndarray, ...],
    count: int,
    epoch_separation: int,
    cfo_separation: float,
    epoch_count: int,
) -> tuple[tuple[float, int, float], ...]:
    peaks = [
        (float(scores[epoch]), epoch, residual)
        for residual, scores in zip(residuals, rows, strict=True)
        for epoch in candidate._local_peak_indexes(scores)
    ]
    peaks.sort(key=lambda item: (item[0], -abs(item[2]), -item[1]), reverse=True)
    return candidate._retain_separated(
        peaks,
        count,
        epoch_separation,
        cfo_separation,
        epoch_count,
    )


@pytest.mark.parametrize("seed", range(64))
def test_heap_retention_exactly_matches_full_stable_sort(seed: int) -> None:
    rng = np.random.default_rng(seed)
    epoch_count = int(rng.integers(2, 6000))
    residuals = tuple(float(value) for value in range(-400_000, 400_001, 80_000))
    rows = tuple(
        np.round(rng.random(epoch_count), decimals=int(rng.integers(1, 8)))
        for _ in residuals
    )
    expected = _reference(residuals, rows, 8, 20, 80_000.0, epoch_count)
    actual = candidate._retain_score_map_peaks(
        residuals,
        rows,
        8,
        20,
        80_000.0,
        epoch_count,
    )
    assert actual == expected


def test_heap_retention_preserves_stable_complete_ties_and_boundaries() -> None:
    residuals = (-80_000.0, 80_000.0, 0.0)
    rows = (
        np.array([0.0, 2.0, 0.0, 2.0, 0.0, 1.0, 0.0]),
        np.array([0.0, 2.0, 0.0, 2.0, 0.0, 1.0, 0.0]),
        np.array([3.0, 0.0, 1.0, 0.0, 3.0, 0.0, 1.0]),
    )
    expected = _reference(residuals, rows, 8, 1, 80_000.0, 7)
    actual = candidate._retain_score_map_peaks(residuals, rows, 8, 1, 80_000.0, 7)
    assert actual == expected


def test_heap_retention_handles_no_peaks() -> None:
    residuals = (-80_000.0, 0.0, 80_000.0)
    rows = tuple(np.zeros(32) for _ in residuals)
    expected = _reference(residuals, rows, 8, 20, 80_000.0, 32)
    actual = candidate._retain_score_map_peaks(residuals, rows, 8, 20, 80_000.0, 32)
    assert actual == expected == ((0.0, 0, 0.0),)
