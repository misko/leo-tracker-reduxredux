from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

import leo.analysis.standard.full_capture_glrt20ms as full_capture
from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.acquisition import AcquisitionCandidate
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodScore,
    conditioned_glrt64_score,
    conditioned_glrt64_scores,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig


def _scalar_scores(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_samples: tuple[int, ...],
    acquired_cfo_hz: tuple[float, ...],
    edge: StarlinkEdge,
    glrt_size: int = 512,
) -> tuple[PilotMethodScore, ...]:
    return tuple(
        conditioned_glrt64_score(
            samples,
            sample_rate_hz,
            epoch_sample=epoch,
            acquired_cfo_hz=cfo_hz,
            edge=edge,
            glrt_size=glrt_size,
        )
        for epoch, cfo_hz in zip(epoch_samples, acquired_cfo_hz, strict=True)
    )


def _assert_score_equivalence(
    scalar: tuple[PilotMethodScore, ...],
    batch: tuple[PilotMethodScore, ...],
) -> None:
    assert len(batch) == len(scalar)
    for expected, actual in zip(scalar, batch, strict=True):
        assert actual.method is expected.method
        assert actual.exact_score == pytest.approx(expected.exact_score, abs=1e-12)
        assert actual.control_score == pytest.approx(expected.control_score, abs=1e-12)
        assert actual.margin == pytest.approx(expected.margin, abs=2e-12)
        assert actual.residual_cfo_hz == pytest.approx(expected.residual_cfo_hz, abs=1e-8)
        assert actual.tracking_cfo_hz == pytest.approx(expected.tracking_cfo_hz, abs=1e-8)


@pytest.mark.parametrize("edge", tuple(StarlinkEdge))
@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 5_000_000))
def test_batch_matches_scalar_at_each_native_rate_and_edge(
    edge: StarlinkEdge,
    sample_rate_hz: int,
) -> None:
    sample_count = sample_rate_hz // 50
    generator = np.random.default_rng(sample_rate_hz + int(edge is StarlinkEdge.UPPER))
    samples = generator.normal(size=sample_count) + 1j * generator.normal(size=sample_count)
    epoch_limit = round(sample_rate_hz / FRAME_RATE_HZ)
    epochs = tuple(int(value) for value in generator.integers(0, epoch_limit, size=10))
    frequencies = tuple(float(value) for value in generator.uniform(-500_000, 500_000, size=10))

    scalar = _scalar_scores(
        samples,
        sample_rate_hz,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
    )
    batch = conditioned_glrt64_scores(
        samples,
        sample_rate_hz,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
    )

    _assert_score_equivalence(scalar, batch)
    scalar_winner = max(range(len(scalar)), key=lambda index: (scalar[index].margin, -index))
    batch_winner = max(range(len(batch)), key=lambda index: (batch[index].margin, -index))
    assert batch_winner == scalar_winner
    for margin_gate in (0.0, 0.025, 0.05, 0.25):
        assert tuple(item.margin >= margin_gate for item in batch) == tuple(
            item.margin >= margin_gate for item in scalar
        )


def test_batch_uses_scalar_fallback_for_unsupported_glrt_geometry() -> None:
    generator = np.random.default_rng(0x64BA7C)
    samples = generator.normal(size=30_000) + 1j * generator.normal(size=30_000)
    epochs = (0, 17, 1_200, 3_332)
    frequencies = (-400_000.0, -123_456.75, 0.0, 399_999.5)

    scalar = _scalar_scores(
        samples,
        5_000_000,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=StarlinkEdge.UPPER,
        glrt_size=64,
    )
    batch = conditioned_glrt64_scores(
        samples,
        5_000_000,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=StarlinkEdge.UPPER,
        glrt_size=64,
    )

    assert batch == scalar


def test_nonuniform_3m_geometry_uses_scalar_fallback() -> None:
    generator = np.random.default_rng(3_000_000)
    samples = generator.normal(size=60_000) + 1j * generator.normal(size=60_000)
    epochs = (0, 41, 2_001, 3_999)
    frequencies = (-400_000.0, -81_250.0, 120_000.0, 400_000.0)

    scalar = _scalar_scores(
        samples,
        3_000_000,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=StarlinkEdge.LOWER,
    )
    batch = conditioned_glrt64_scores(
        samples,
        3_000_000,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=StarlinkEdge.LOWER,
    )

    assert batch == scalar


def test_batch_preserves_empty_zero_duplicate_and_permuted_inventories() -> None:
    assert (
        conditioned_glrt64_scores(
            np.ones(15_000, dtype=np.complex128),
            5_000_000,
            epoch_samples=(),
            acquired_cfo_hz=(),
        )
        == ()
    )

    samples = np.zeros(15_000, dtype=np.complex128)
    epochs = (1_700, 12, 1_700, len(samples) + 100)
    frequencies = (77_000.0, -91_000.0, 77_000.0, 310_000.0)
    permutation = (3, 0, 2, 1)
    original = conditioned_glrt64_scores(
        samples,
        5_000_000,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=StarlinkEdge.UPPER,
    )
    permuted = conditioned_glrt64_scores(
        samples,
        5_000_000,
        epoch_samples=tuple(epochs[index] for index in permutation),
        acquired_cfo_hz=tuple(frequencies[index] for index in permutation),
        edge=StarlinkEdge.UPPER,
    )

    assert original[0] == original[2]
    for new_index, original_index in enumerate(permutation):
        assert permuted[new_index] == original[original_index]


@pytest.mark.parametrize(
    ("epochs", "frequencies", "message"),
    (
        ((0, 1), (0.0,), "equally sized"),
        ((0.5,), (0.0,), "must be integers"),
        ((-1,), (0.0,), "must be nonnegative"),
        ((0,), (float("nan"),), "must be finite"),
    ),
)
def test_batch_rejects_invalid_candidate_inventories(
    epochs: tuple[float, ...],
    frequencies: tuple[float, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        conditioned_glrt64_scores(
            np.ones(15_000, dtype=np.complex128),
            5_000_000,
            epoch_samples=cast(tuple[int, ...], epochs),
            acquired_cfo_hz=frequencies,
        )


def _candidate(rank: int, epoch: int, cfo_hz: float) -> AcquisitionCandidate:
    return AcquisitionCandidate(
        rank=rank,
        coarse_epoch_sample=epoch,
        coarse_residual_cfo_hz=cfo_hz,
        refined_epoch_sample=epoch,
        residual_cfo_hz=cfo_hz,
        absolute_cfo_hz=cfo_hz,
        coarse_score=0.1,
        acquire_score=0.1,
        verify_score=0.1,
        conditioned_exact_score=0.1,
        conditioned_control_score=0.0,
        verify_minus_control_margin=0.1,
        frame_support=1,
    )


def _score(margin: float, tracking_cfo_hz: float) -> PilotMethodScore:
    return PilotMethodScore(
        method=PilotMethod.GLRT64,
        exact_score=0.1 + margin,
        control_score=0.1,
        margin=margin,
        residual_cfo_hz=0.0,
        tracking_cfo_hz=tracking_cfo_hz,
    )


def test_near_tied_batch_margins_use_original_scalar_winner_rule(monkeypatch) -> None:
    candidates = (_candidate(0, 0, 10_000.0), _candidate(1, 1, 20_000.0))
    monkeypatch.setattr(
        full_capture,
        "conditioned_glrt64_scores",
        lambda *_args, **_kwargs: (
            _score(0.2, 10_000.0),
            _score(0.2 + 1e-15, 20_000.0),
        ),
    )
    scalar_scores = {
        10_000.0: _score(0.2 + 2e-15, 10_000.0),
        20_000.0: _score(0.2, 20_000.0),
    }
    calls: list[float] = []

    def scalar(*_args, acquired_cfo_hz, **_kwargs):
        calls.append(acquired_cfo_hz)
        return scalar_scores[acquired_cfo_hz]

    monkeypatch.setattr(full_capture, "conditioned_glrt64_score", scalar)

    candidate, result = full_capture._winning_candidate_glrt64(
        np.ones(15_000, dtype=np.complex128),
        5_000_000,
        candidates,
        edge=StarlinkEdge.UPPER,
        glrt_size=512,
    )

    assert candidate.rank == 0
    assert result is scalar_scores[10_000.0]
    assert calls == [10_000.0, 20_000.0]


def test_separated_batch_winner_only_rescores_published_geometry(monkeypatch) -> None:
    candidates = (
        _candidate(0, 0, 10_000.0),
        _candidate(1, 0, 10_000.0),
        _candidate(2, 1, 20_000.0),
    )
    monkeypatch.setattr(
        full_capture,
        "conditioned_glrt64_scores",
        lambda *_args, **_kwargs: (
            _score(0.3, 10_000.0),
            _score(0.3, 10_000.0),
            _score(0.1, 20_000.0),
        ),
    )
    published = _score(0.3, 10_000.0)
    calls: list[float] = []

    def scalar(*_args, acquired_cfo_hz, **_kwargs):
        calls.append(acquired_cfo_hz)
        return published

    monkeypatch.setattr(full_capture, "conditioned_glrt64_score", scalar)

    candidate, result = full_capture._winning_candidate_glrt64(
        np.ones(15_000, dtype=np.complex128),
        5_000_000,
        candidates,
        edge=StarlinkEdge.UPPER,
        glrt_size=512,
    )

    assert candidate.rank == 0
    assert result is published
    assert calls == [10_000.0]


def test_full_capture_phase_slope_handoff_uses_fractional_glrt_epoch(monkeypatch) -> None:
    candidate = _candidate(0, 17, 10_000.0)
    score = _score(0.3, 10_000.0)
    monkeypatch.setattr(
        full_capture,
        "acquire_symbolwise",
        lambda *_args, **_kwargs: SimpleNamespace(
            candidates=(candidate,),
            status=full_capture.NumericalStatus.COMPLETE,
            reason="fixture",
        ),
    )
    monkeypatch.setattr(
        full_capture,
        "_winning_candidate_glrt64",
        lambda *_args, **_kwargs: (candidate, score),
    )
    monkeypatch.setattr(
        full_capture,
        "_fractional_glrt_epoch",
        lambda *_args, **_kwargs: ("complete", 0.375, (0.1, 0.2, 0.3, 0.2, 0.1)),
    )
    observed_offsets: list[float] = []

    def phase_slope(*_args, fractional_epoch_offset_samples, **_kwargs):
        observed_offsets.append(fractional_epoch_offset_samples)
        return SimpleNamespace(frames=())

    monkeypatch.setattr(full_capture, "analyze_pilot_phase_slope", phase_slope)

    result = full_capture._analyze_window(
        0,
        0,
        np.ones(50_000, dtype=np.complex128),
        sample_rate_hz=2_500_000,
        edge=StarlinkEdge.LOWER,
        acquisition_config=full_capture.SymbolwiseAcquisitionConfig(maximum_probe_samples=50_000),
        glrt_size=512,
        margin_gate=0.025,
        refine_fractional_epoch=True,
    )

    assert observed_offsets == [0.375]
    assert result.fractional_epoch_offset_samples == pytest.approx(0.375)


def _scalar_winner(
    samples: np.ndarray,
    sample_rate_hz: int,
    candidates: tuple[AcquisitionCandidate, ...],
    *,
    edge: StarlinkEdge,
    glrt_size: int,
) -> tuple[AcquisitionCandidate, PilotMethodScore]:
    scored = tuple(
        (
            candidate,
            conditioned_glrt64_score(
                samples,
                sample_rate_hz,
                epoch_sample=candidate.refined_epoch_sample,
                acquired_cfo_hz=candidate.absolute_cfo_hz,
                edge=edge,
                glrt_size=glrt_size,
            ),
        )
        for candidate in candidates
    )
    return max(scored, key=lambda item: (item[1].margin, -item[0].rank))


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_production_window_matches_original_scalar_implementation(
    monkeypatch,
    sample_rate_hz: int,
) -> None:
    edge = StarlinkEdge.UPPER
    epoch = 37
    cfo_hz = 142_000.0
    template = qin_edge_pilot_frame(sample_rate_hz, edge)
    samples = np.zeros(sample_rate_hz // 50, dtype=np.complex128)
    frame = 0
    while True:
        start = epoch + round(frame * sample_rate_hz / FRAME_RATE_HZ)
        if start + len(template) > len(samples):
            break
        indexes = np.arange(start, start + len(template))
        samples[start : start + len(template)] += template * np.exp(
            2j * np.pi * cfo_hz * indexes / sample_rate_hz
        )
        frame += 1
    generator = np.random.default_rng(sample_rate_hz)
    samples += 0.02 * (
        generator.normal(size=len(samples)) + 1j * generator.normal(size=len(samples))
    )
    acquisition = full_capture._acquisition_config(len(samples), TrajectoryFeedbackConfig())

    batch_result = full_capture._analyze_window(
        7,
        sample_rate_hz // 10,
        samples,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
        acquisition_config=acquisition,
        glrt_size=512,
        margin_gate=0.025,
    )
    monkeypatch.setattr(full_capture, "_winning_candidate_glrt64", _scalar_winner)
    scalar_result = full_capture._analyze_window(
        7,
        sample_rate_hz // 10,
        samples,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
        acquisition_config=acquisition,
        glrt_size=512,
        margin_gate=0.025,
    )

    assert batch_result == scalar_result
