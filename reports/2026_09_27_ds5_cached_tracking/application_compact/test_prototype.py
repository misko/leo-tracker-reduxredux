from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from prototype import compact_conditioned_glrt64_score, compact_glrt64_correlations  # noqa: E402
from leo.analysis.starlink.pilot_methods import (  # noqa: E402
    _conditioned_correlation_workspace,
    conditioned_glrt64_score,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge, qin_edge_pilot_frame  # noqa: E402


def test_oracle_is_the_pinned_application_source() -> None:
    import hashlib
    import leo.analysis.starlink.pilot_methods as pilot_methods
    import leo.scanner.detector as detector

    expected = {
        ROOT / "src/leo/scanner/detector.py": (
            "01c21e7b138bc66c84efc341fff94d7938d18ed04ef9961286d4cabe73879270"
        ),
        ROOT / "src/leo/analysis/starlink/pilot_methods.py": (
            "d6a599d7eb9cb4d6de5f7e6781cb6ea3ce65de422723d94ebfec9ea0a1fa4193"
        ),
    }
    assert Path(detector.__file__).resolve() == ROOT / "src/leo/scanner/detector.py"
    assert Path(pilot_methods.__file__).resolve() == (
        ROOT / "src/leo/analysis/starlink/pilot_methods.py"
    )
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def _random(rate: int, count: int, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    return np.asarray(
        generator.normal(size=count) + 1j * generator.normal(size=count),
        dtype=np.complex128,
    )


def _pilot(rate: int, edge: StarlinkEdge, epoch: int, cfo_hz: float) -> np.ndarray:
    count = rate // 50
    output = np.zeros(count, dtype=np.complex128)
    template = np.asarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128)
    frame = 0
    while True:
        start = epoch + round(frame * rate / FRAME_RATE_HZ)
        if start + len(template) > count:
            break
        indexes = np.arange(start, start + len(template), dtype=float)
        output[start : start + len(template)] += template * np.exp(
            2j * np.pi * cfo_hz * indexes / rate
        )
        frame += 1
    return output


def _assert_correlations_exact(
    values: np.ndarray,
    rate: int,
    edge: StarlinkEdge,
    epoch: int,
    cfo_hz: float,
) -> None:
    symbols = np.arange(2, 66)
    workspace = _conditioned_correlation_workspace(
        values,
        rate,
        epoch,
        cfo_hz,
        edge=edge,
        selected_symbols=symbols,
    )
    expected = (workspace.select(symbols), workspace.select(symbols, control=True))
    actual = compact_glrt64_correlations(values, rate, epoch, cfo_hz, edge=edge)
    for left, right in zip(expected, actual, strict=True):
        np.testing.assert_array_equal(right.values, left.values)
        np.testing.assert_array_equal(right.normalized_power, left.normalized_power)
        np.testing.assert_array_equal(right.times_s, left.times_s)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("edge", [StarlinkEdge.LOWER, StarlinkEdge.UPPER])
@pytest.mark.parametrize("kind", ["random", "zero", "pilot"])
def test_compact_score_and_correlations_are_exact(rate: int, edge: StarlinkEdge, kind: str) -> None:
    epoch = 347
    cfo_hz = 12345.5
    count = rate // 50
    if kind == "random":
        values = _random(rate, count, rate + (edge is StarlinkEdge.UPPER))
    elif kind == "zero":
        values = np.zeros(count, dtype=np.complex128)
    else:
        values = _pilot(rate, edge, epoch, cfo_hz)
    before = values.copy()
    _assert_correlations_exact(values, rate, edge, epoch, cfo_hz)
    expected = conditioned_glrt64_score(
        values,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=cfo_hz,
        edge=edge,
    )
    actual = compact_conditioned_glrt64_score(
        values,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=cfo_hz,
        edge=edge,
    )
    assert actual == expected
    np.testing.assert_array_equal(values, before)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_truncated_single_frame_support_is_exact(rate: int) -> None:
    edge = StarlinkEdge.LOWER
    epoch = 19
    template = qin_edge_pilot_frame(rate, edge)
    stop = round(66 * rate * 4.4e-6)
    values = _random(rate, epoch + min(stop, len(template)) + 1, 808 + rate)
    _assert_correlations_exact(values, rate, edge, epoch, -399_123.25)
    assert compact_conditioned_glrt64_score(
        values,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=-399_123.25,
        edge=edge,
    ) == conditioned_glrt64_score(
        values,
        rate,
        epoch_sample=epoch,
        acquired_cfo_hz=-399_123.25,
        edge=edge,
    )


@pytest.mark.parametrize(
    ("values", "cfo_hz", "edge", "glrt_size"),
    [
        (np.zeros(0, dtype=np.complex128), 0.0, "lower", 512),
        (np.zeros((2, 2), dtype=np.complex128), 0.0, "lower", 512),
        (np.ones(100, dtype=np.complex128), float("nan"), "lower", 512),
        (np.ones(100, dtype=np.complex128), 0.0, "invalid", 512),
        (np.ones(100, dtype=np.complex128), 0.0, "lower", True),
    ],
)
def test_invalid_inputs_match_oracle_exception_type(values, cfo_hz, edge, glrt_size) -> None:
    calls = (conditioned_glrt64_score, compact_conditioned_glrt64_score)
    errors = []
    for function in calls:
        with pytest.raises(Exception) as raised:
            function(
                values,
                2_500_000,
                epoch_sample=0,
                acquired_cfo_hz=cfo_hz,
                edge=edge,
                glrt_size=glrt_size,
            )
        errors.append(type(raised.value))
    assert errors[0] is errors[1]
