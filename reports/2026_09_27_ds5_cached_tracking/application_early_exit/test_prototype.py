from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from prototype import detect_first_glrt64_early  # noqa: E402
import leo.scanner.detector as detector  # noqa: E402
from leo.scanner import ScanTarget, ScannerConfiguration  # noqa: E402
from leo.analysis.starlink import StarlinkEdge  # noqa: E402


@dataclass(frozen=True)
class Hit:
    probe: int
    receiver: int
    rank: int = 0
    margin: float = 0.2
    tracking_cfo_hz: float = 1_000.0


def configuration() -> ScannerConfiguration:
    return ScannerConfiguration(
        sample_rate_hz=1_000,
        bandwidth_hz=1_000,
        dwell_ms=120,
        receiver_ids=(0, 1),
        maximum_acquisition_candidates=2,
        targets=(
            ScanTarget(
                channel=1,
                edge=StarlinkEdge.LOWER,
                rf_center_hz=10_709_687_500,
                if_center_hz=959_687_500,
            ),
        ),
    )


def samples(config: ScannerConfiguration) -> np.ndarray:
    indexes = np.arange(config.dwell_samples, dtype=float)
    return np.stack((indexes * 10, indexes * 10 + 1), axis=1).astype(np.complex128)


def run_with_hits(function, declared: tuple[Hit, ...]):
    config = configuration()
    values = samples(config)
    calls = {"acquire": 0, "score": 0}
    lookup = {(hit.probe, hit.receiver, hit.rank): hit for hit in declared}

    def locate(probe):
        encoded = int(probe[0].real)
        return encoded // (config.probe_stride_samples * 10), encoded % 10

    def acquire(probe, _rate, _calibration, *, edge, config):
        del edge, config
        calls["acquire"] += 1
        probe_index, receiver = locate(probe)
        candidates = []
        for rank in range(2):
            hit = lookup.get((probe_index, receiver, rank))
            cfo = hit.tracking_cfo_hz if hit else 100_000.0 + 20_000 * rank
            candidates.append(
                SimpleNamespace(rank=rank, refined_epoch_sample=rank + 2, absolute_cfo_hz=cfo)
            )
        return SimpleNamespace(candidates=tuple(candidates))

    def score(probe, _rate, *, epoch_sample, acquired_cfo_hz, edge):
        del edge, acquired_cfo_hz
        calls["score"] += 1
        probe_index, receiver = locate(probe)
        rank = epoch_sample - 2
        hit = lookup.get((probe_index, receiver, rank))
        margin = hit.margin if hit else -0.1
        cfo = hit.tracking_cfo_hz if hit else 100_000.0 + 20_000 * rank
        return SimpleNamespace(
            margin=margin,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=cfo,
            exact_score=margin + 0.1,
            control_score=0.1,
        )

    module = sys.modules[function.__module__]
    with patch.object(module, "acquire_symbolwise", acquire), patch.object(
        module, "conditioned_glrt64_score", score
    ):
        result = function(values, config, edge=StarlinkEdge.LOWER)
    return result, calls


@pytest.mark.parametrize(
    ("declared", "expected_first"),
    [
        ((Hit(0, 0), Hit(2, 0)), (0, 0, 0)),
        ((Hit(3, 1), Hit(5, 1)), (1, 3, 0)),
        ((), None),
        ((Hit(0, 0, margin=0.1), Hit(0, 1, margin=0.5), Hit(2, 0), Hit(2, 1)), (0, 0, 0)),
        ((Hit(0, 0, rank=0, margin=0.2), Hit(0, 0, rank=1, margin=0.2), Hit(2, 0)), (0, 0, 0)),
        ((Hit(0, 0), Hit(1, 0)), None),
        ((Hit(0, 0, tracking_cfo_hz=0.0), Hit(2, 0, tracking_cfo_hz=8_000.0)), (0, 0, 0)),
        ((Hit(0, 0, tracking_cfo_hz=0.0), Hit(2, 0, tracking_cfo_hz=8_000.000001)), None),
    ],
    ids=(
        "first-probe-two",
        "late-confirmation",
        "negative",
        "competing-receivers",
        "candidate-tie",
        "overlap-does-not-confirm",
        "inclusive-cfo-edge",
        "outside-cfo-edge",
    ),
)
def test_exactly_matches_detector_scenarios(
    declared: tuple[Hit, ...], expected_first: tuple[int, int, int] | None
) -> None:
    expected, oracle_calls = run_with_hits(detector.detect_first_glrt64, declared)
    actual, candidate_calls = run_with_hits(detect_first_glrt64_early, declared)
    assert actual == expected
    observed_first = None if actual.first is None else (
        actual.first.receiver_id,
        actual.first.probe_index,
        actual.first.candidate_rank,
    )
    assert observed_first == expected_first
    if actual.first is not None:
        assert candidate_calls["acquire"] <= oracle_calls["acquire"]
        assert candidate_calls["score"] <= oracle_calls["score"]
    else:
        assert candidate_calls == oracle_calls


@pytest.mark.parametrize("shape", [(120,), (119, 2), (120, 1), (120, 3)])
def test_invalid_shape_matches_detector(shape: tuple[int, ...]) -> None:
    config = configuration()
    values = np.zeros(shape, dtype=np.complex64)
    errors = []
    for function in (detector.detect_first_glrt64, detect_first_glrt64_early):
        with pytest.raises(Exception) as raised:
            function(values, config, edge=StarlinkEdge.LOWER)
        errors.append((type(raised.value), str(raised.value)))
    assert errors[0] == errors[1]


def test_earliest_confirmation_finishes_entire_probe_then_stops() -> None:
    declared = (Hit(0, 0), Hit(2, 0))
    expected, oracle_calls = run_with_hits(detector.detect_first_glrt64, declared)
    actual, candidate_calls = run_with_hits(detect_first_glrt64_early, declared)
    assert actual == expected
    assert oracle_calls == {"acquire": 22, "score": 44}
    assert candidate_calls == {"acquire": 6, "score": 12}
