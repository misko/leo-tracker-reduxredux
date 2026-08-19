"""Pure, bounded known-pilot detector-family evaluation on one IQ probe."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from leo.analysis.qam import analyze_pilot_qam
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)

_FIRST_PILOT_SYMBOL = 2
_LAST_PILOT_SYMBOL = 301
_GLRT_SIZE = 512


class PilotMethod(StrEnum):
    ANCHOR8 = "anchor8"
    DIFFERENTIAL16 = "differential16"
    DIFFERENTIAL32 = "differential32"
    GLRT32 = "glrt32"
    GLRT64 = "glrt64"
    EDGE_TRACKER = "edge_tracker"
    SYMBOLWISE = "symbolwise"
    QAM_ACCURACY = "qam_accuracy"


@dataclass(frozen=True, slots=True)
class PilotMethodScore:
    method: PilotMethod
    exact_score: float
    control_score: float | None
    margin: float
    residual_cfo_hz: float
    tracking_cfo_hz: float


@dataclass(frozen=True, slots=True)
class PilotProbeDetection:
    status: NumericalStatus
    sample_start: int
    time_s: float
    local_epoch_sample: int | None
    acquired_cfo_hz: float | None
    scores: tuple[PilotMethodScore, ...]
    qam_accuracy: float | None
    qam_evm: float | None
    reason: str
    source_candidate_count: int = 0
    truncated_candidate_count: int = 0
    candidates: tuple[PilotMethodCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class PilotMethodCandidate:
    """All-method evidence for one retained timing/CFO acquisition basin."""

    rank: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    scores: tuple[PilotMethodScore, ...]
    qam_accuracy: float | None
    qam_evm: float | None


@dataclass(frozen=True, slots=True)
class _SymbolCorrelations:
    values: np.ndarray
    normalized_power: np.ndarray
    times_s: np.ndarray

    @property
    def symbol_step_s(self) -> float:
        if self.values.shape[1] < 2:
            return OFDM_SYMBOL_DURATION_S
        return float(np.median(np.diff(self.times_s, axis=1)))


def detect_pilot_methods(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    sample_start: int,
    calibration: ReceiverFrequencyCalibration,
    acquisition_config: SymbolwiseAcquisitionConfig,
) -> PilotProbeDetection:
    """Acquire once, then evaluate every detector on the identical winner."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("pilot-method samples must be a nonempty vector")
    if sample_start < 0:
        raise ValueError("sample_start must be nonnegative")
    acquisition = acquire_symbolwise(
        values,
        sample_rate_hz,
        calibration,
        config=acquisition_config,
    )
    winner = acquisition.winner
    if winner is None:
        return PilotProbeDetection(
            acquisition.status,
            sample_start,
            sample_start / sample_rate_hz,
            None,
            None,
            (),
            None,
            None,
            "symbolwise acquisition produced no candidate",
        )
    candidate = _evaluate_candidate(values, sample_rate_hz, winner)
    return PilotProbeDetection(
        NumericalStatus.COMPLETE,
        sample_start,
        sample_start / sample_rate_hz,
        candidate.local_epoch_sample,
        candidate.acquired_cfo_hz,
        candidate.scores,
        candidate.qam_accuracy,
        candidate.qam_evm,
        "known-pilot detector family; candidate-only and payload was not decoded",
    )


def detect_pilot_method_candidates(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    sample_start: int,
    calibration: ReceiverFrequencyCalibration,
    acquisition_config: SymbolwiseAcquisitionConfig,
    maximum_scored_candidates: int = 4,
) -> PilotProbeDetection:
    """V2 acquisition preserving bounded multi-basin all-method evidence."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("pilot-method samples must be a nonempty vector")
    if sample_start < 0:
        raise ValueError("sample_start must be nonnegative")
    if maximum_scored_candidates < 1:
        raise ValueError("maximum_scored_candidates must be positive")
    acquisition = acquire_symbolwise(
        values,
        sample_rate_hz,
        calibration,
        config=acquisition_config,
    )
    if acquisition.winner is None:
        return PilotProbeDetection(
            acquisition.status,
            sample_start,
            sample_start / sample_rate_hz,
            None,
            None,
            (),
            None,
            None,
            "symbolwise acquisition produced no candidate",
        )
    retained = acquisition.candidates[:maximum_scored_candidates]
    candidates = tuple(
        _evaluate_candidate(values, sample_rate_hz, candidate) for candidate in retained
    )
    primary = candidates[0]
    return PilotProbeDetection(
        NumericalStatus.COMPLETE,
        sample_start,
        sample_start / sample_rate_hz,
        primary.local_epoch_sample,
        primary.acquired_cfo_hz,
        primary.scores,
        primary.qam_accuracy,
        primary.qam_evm,
        "bounded multi-basin known-pilot family; candidate-only and no payload decoded",
        source_candidate_count=len(acquisition.candidates),
        truncated_candidate_count=len(acquisition.candidates) - len(candidates),
        candidates=candidates,
    )


def _evaluate_candidate(
    values: np.ndarray,
    sample_rate_hz: int,
    candidate,
) -> PilotMethodCandidate:
    qam = analyze_pilot_qam(
        values,
        sample_rate_hz,
        epoch_sample=candidate.refined_epoch_sample,
        absolute_cfo_hz=candidate.absolute_cfo_hz,
    )
    qam_accuracy = None if qam.metrics is None else qam.metrics.hard_symbol_accuracy
    qam_evm = None if qam.metrics is None else qam.metrics.rms_evm
    scores = conditioned_pilot_method_scores(
        values,
        sample_rate_hz,
        epoch_sample=candidate.refined_epoch_sample,
        acquired_cfo_hz=candidate.absolute_cfo_hz,
        symbolwise_exact=candidate.verify_score,
        symbolwise_control=candidate.conditioned_control_score,
        qam_accuracy=qam_accuracy,
    )
    return PilotMethodCandidate(
        rank=candidate.rank,
        local_epoch_sample=candidate.refined_epoch_sample,
        acquired_cfo_hz=candidate.absolute_cfo_hz,
        scores=scores,
        qam_accuracy=qam_accuracy,
        qam_evm=qam_evm,
    )


def conditioned_pilot_method_scores(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_sample: int,
    acquired_cfo_hz: float,
    symbolwise_exact: float,
    symbolwise_control: float,
    qam_accuracy: float | None,
) -> tuple[PilotMethodScore, ...]:
    """Evaluate all confirmers at one already-acquired epoch and CFO."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("conditioned pilot samples must be a nonempty vector")
    finite = (acquired_cfo_hz, symbolwise_exact, symbolwise_control)
    if any(not math.isfinite(value) for value in finite):
        raise ValueError("conditioned pilot inputs must be finite")
    anchors = np.unique(np.rint(np.linspace(2, 301, 8)).astype(int))
    requested = {
        PilotMethod.ANCHOR8: anchors,
        PilotMethod.DIFFERENTIAL16: np.arange(2, 18),
        PilotMethod.DIFFERENTIAL32: np.arange(2, 34),
        PilotMethod.GLRT32: np.arange(2, 34),
        PilotMethod.GLRT64: np.arange(2, 66),
        PilotMethod.EDGE_TRACKER: np.arange(2, 302),
    }
    exact = {
        method: _symbol_correlations(
            values,
            sample_rate_hz,
            epoch_sample,
            acquired_cfo_hz,
            symbols,
            symbol_roll=0,
        )
        for method, symbols in requested.items()
    }
    control = {
        method: _symbol_correlations(
            values,
            sample_rate_hz,
            epoch_sample,
            acquired_cfo_hz,
            symbols,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        )
        for method, symbols in requested.items()
    }
    anchor_exact = _anchor_score(exact[PilotMethod.ANCHOR8])
    anchor_control = _anchor_score(control[PilotMethod.ANCHOR8])
    differential16, differential16_cfo = _differential(
        exact[PilotMethod.DIFFERENTIAL16]
    )
    differential16_control = _differential(control[PilotMethod.DIFFERENTIAL16])[0]
    differential32, differential32_cfo = _differential(
        exact[PilotMethod.DIFFERENTIAL32]
    )
    differential32_control = _differential(control[PilotMethod.DIFFERENTIAL32])[0]
    glrt32, glrt32_cfo = _glrt(exact[PilotMethod.GLRT32])
    glrt32_control = _glrt(control[PilotMethod.GLRT32])[0]
    glrt64, glrt64_cfo = _glrt(exact[PilotMethod.GLRT64])
    glrt64_control = _glrt(control[PilotMethod.GLRT64])[0]
    edge = _edge_tracker(exact[PilotMethod.EDGE_TRACKER])
    edge_control = _edge_tracker(control[PilotMethod.EDGE_TRACKER])
    result = [
        _score(
            PilotMethod.ANCHOR8,
            anchor_exact,
            anchor_control,
            0.0,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.DIFFERENTIAL16,
            differential16,
            differential16_control,
            differential16_cfo,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.DIFFERENTIAL32,
            differential32,
            differential32_control,
            differential32_cfo,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.GLRT32,
            glrt32,
            glrt32_control,
            glrt32_cfo,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.GLRT64,
            glrt64,
            glrt64_control,
            glrt64_cfo,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.EDGE_TRACKER,
            edge,
            edge_control,
            0.0,
            acquired_cfo_hz,
        ),
        _score(
            PilotMethod.SYMBOLWISE,
            symbolwise_exact,
            symbolwise_control,
            0.0,
            acquired_cfo_hz,
        ),
    ]
    if qam_accuracy is not None:
        if not math.isfinite(qam_accuracy) or not 0 <= qam_accuracy <= 1:
            raise ValueError("QAM accuracy must lie in [0,1]")
        result.append(
            PilotMethodScore(
                PilotMethod.QAM_ACCURACY,
                qam_accuracy,
                None,
                qam_accuracy,
                0.0,
                acquired_cfo_hz,
            )
        )
    return tuple(result)


def _score(
    method: PilotMethod,
    exact: float,
    control: float,
    residual_cfo_hz: float,
    acquired_cfo_hz: float,
) -> PilotMethodScore:
    values = (exact, control, residual_cfo_hz, acquired_cfo_hz)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("pilot score values must be finite")
    return PilotMethodScore(
        method,
        exact,
        control,
        exact - control,
        residual_cfo_hz,
        acquired_cfo_hz + residual_cfo_hz,
    )


def _symbol_correlations(
    samples: np.ndarray,
    sample_rate_hz: int,
    epoch_sample: int,
    cfo_hz: float,
    symbols: np.ndarray,
    *,
    symbol_roll: int,
) -> _SymbolCorrelations:
    chosen = np.asarray(symbols, dtype=int)
    if chosen.ndim != 1 or not chosen.size or np.any(np.diff(chosen) <= 0):
        raise ValueError("symbols must be nonempty and strictly increasing")
    if chosen[0] < _FIRST_PILOT_SYMBOL or chosen[-1] > _LAST_PILOT_SYMBOL:
        raise ValueError("pilot symbol lies outside 2..301")
    template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, "lower", symbol_roll=symbol_roll),
        dtype=np.complex128,
    )
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    rows: list[list[complex]] = []
    powers: list[list[float]] = []
    moments: list[list[float]] = []
    frame = 0
    while True:
        frame_start = epoch_sample + round(frame * frame_period)
        if frame_start >= len(samples):
            break
        row: list[complex] = []
        row_power: list[float] = []
        row_moments: list[float] = []
        complete = True
        for symbol in chosen:
            local_start = round(int(symbol) * symbol_period)
            local_stop = min(round((int(symbol) + 1) * symbol_period), len(template))
            count = local_stop - local_start
            start = frame_start + local_start
            if count < 2 or start < 0 or start + count > len(samples):
                complete = False
                break
            indexes = np.arange(start, start + count, dtype=float)
            local = template[local_start:local_stop]
            corrected = samples[start : start + count] * np.exp(
                -2j * np.pi * cfo_hz * indexes / sample_rate_hz
            )
            correlation = complex(np.vdot(local, corrected))
            denominator = float(np.vdot(local, local).real * np.vdot(corrected, corrected).real)
            row.append(correlation)
            row_power.append(abs(correlation) ** 2 / max(denominator, 1e-20))
            row_moments.append((start + (count - 1) / 2) / sample_rate_hz)
        if not complete:
            break
        rows.append(row)
        powers.append(row_power)
        moments.append(row_moments)
        frame += 1
    shape = (len(rows), len(chosen))
    return _SymbolCorrelations(
        np.asarray(rows, dtype=np.complex128) if rows else np.zeros(shape, dtype=np.complex128),
        np.asarray(powers, dtype=float) if rows else np.zeros(shape, dtype=float),
        np.asarray(moments, dtype=float) if rows else np.zeros(shape, dtype=float),
    )


def _coherent_ceiling(values: np.ndarray) -> float:
    return float(np.sum(np.sum(np.abs(values), axis=1) ** 2)) if values.size else 0.0


def _anchor_score(correlations: _SymbolCorrelations) -> float:
    ceiling = _coherent_ceiling(correlations.values)
    power = float(np.sum(np.abs(np.sum(correlations.values, axis=1)) ** 2))
    return power / ceiling if ceiling > 0 else 0.0


def _differential(correlations: _SymbolCorrelations) -> tuple[float, float]:
    leading = correlations.values[:, 1:]
    trailing = correlations.values[:, :-1]
    products = leading * np.conj(trailing)
    total = complex(np.sum(products))
    weight = float(np.sum(np.abs(leading) * np.abs(trailing)))
    residual = (
        float(np.angle(total) / (2 * np.pi * correlations.symbol_step_s))
        if total != 0
        else 0.0
    )
    return (abs(total) / weight if weight > 0 else 0.0, residual)


def _glrt(correlations: _SymbolCorrelations) -> tuple[float, float]:
    if not correlations.values.size:
        return 0.0, 0.0
    grid = np.fft.fftfreq(_GLRT_SIZE, d=correlations.symbol_step_s)
    lags = correlations.times_s - correlations.times_s[:, :1]
    phase = np.exp(-2j * np.pi * grid[:, None, None] * lags[None, :, :])
    spectrum = np.sum(
        np.abs(np.sum(correlations.values[None, :, :] * phase, axis=2)) ** 2,
        axis=1,
    )
    ceiling = _coherent_ceiling(correlations.values)
    normalized = spectrum / ceiling if ceiling > 0 else spectrum
    best = int(np.argmax(normalized))
    return float(normalized[best]), float(grid[best])


def _edge_tracker(correlations: _SymbolCorrelations) -> float:
    return (
        float(np.mean(correlations.normalized_power))
        if correlations.normalized_power.size
        else 0.0
    )
