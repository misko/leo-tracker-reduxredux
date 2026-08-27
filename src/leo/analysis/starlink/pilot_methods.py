"""Pure, bounded known-pilot detector-family evaluation on one IQ probe."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from leo.analysis.qam.pilot import PilotQamResult

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
    StarlinkEdge,
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


STANDARD_PILOT_METHODS = (
    PilotMethod.ANCHOR8,
    PilotMethod.GLRT64,
    PilotMethod.SYMBOLWISE,
)

PrimaryQamObserver = Callable[["PilotQamResult"], None]


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


@dataclass(frozen=True, slots=True)
class _ConditionedCorrelationWorkspace:
    """All 300 symbol correlations shared by the nested detector subsets."""

    exact_values: tuple[np.ndarray, ...]
    exact_power: tuple[np.ndarray, ...]
    control_values: tuple[np.ndarray, ...]
    control_power: tuple[np.ndarray, ...]
    times_s: tuple[np.ndarray, ...]
    valid_rows: tuple[np.ndarray, ...]

    def select(self, symbols: np.ndarray, *, control: bool = False) -> _SymbolCorrelations:
        chosen = np.asarray(symbols, dtype=int)
        if chosen.ndim != 1 or not chosen.size or np.any(np.diff(chosen) <= 0):
            raise ValueError("symbols must be nonempty and strictly increasing")
        if chosen[0] < _FIRST_PILOT_SYMBOL or chosen[-1] > _LAST_PILOT_SYMBOL:
            raise ValueError("pilot symbol lies outside 2..301")
        offsets = chosen - _FIRST_PILOT_SYMBOL
        valid = np.logical_and.reduce(tuple(self.valid_rows[int(index)] for index in offsets))
        invalid = np.flatnonzero(~valid)
        frame_count = int(invalid[0]) if invalid.size else len(valid)
        values = self.control_values if control else self.exact_values
        powers = self.control_power if control else self.exact_power
        shape = (frame_count, len(chosen))
        if not frame_count:
            return _SymbolCorrelations(
                np.zeros(shape, dtype=np.complex128),
                np.zeros(shape, dtype=float),
                np.zeros(shape, dtype=float),
            )
        return _SymbolCorrelations(
            np.stack(tuple(values[int(index)][:frame_count] for index in offsets), axis=1),
            np.stack(tuple(powers[int(index)][:frame_count] for index in offsets), axis=1),
            np.stack(tuple(self.times_s[int(index)][:frame_count] for index in offsets), axis=1),
        )


def detect_pilot_methods(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    sample_start: int,
    calibration: ReceiverFrequencyCalibration,
    acquisition_config: SymbolwiseAcquisitionConfig,
    edge: StarlinkEdge,
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
        edge=edge,
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
    candidate = _evaluate_candidate(values, sample_rate_hz, winner, edge=edge)
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
    edge: StarlinkEdge,
    maximum_scored_candidates: int = 4,
    glrt_size: int = _GLRT_SIZE,
    primary_qam_observer: PrimaryQamObserver | None = None,
) -> PilotProbeDetection:
    """V2 acquisition preserving bounded multi-basin all-method evidence."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("pilot-method samples must be a nonempty vector")
    if sample_start < 0:
        raise ValueError("sample_start must be nonnegative")
    if maximum_scored_candidates < 1 or glrt_size < 2:
        raise ValueError("candidate count must be positive and GLRT size at least two")
    acquisition = acquire_symbolwise(
        values,
        sample_rate_hz,
        calibration,
        edge=edge,
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
    if primary_qam_observer is None:
        # Preserve the historical private-call shape for callers and tests that
        # replace the evaluator while keeping all persisted outputs byte-stable.
        candidates = tuple(
            _evaluate_standard_candidate(
                values,
                sample_rate_hz,
                candidate,
                edge=edge,
                glrt_size=glrt_size,
            )
            for candidate in retained
        )
    else:
        candidates = tuple(
            _evaluate_standard_candidate(
                values,
                sample_rate_hz,
                candidate,
                edge=edge,
                glrt_size=glrt_size,
                primary_qam_observer=primary_qam_observer,
            )
            for candidate in retained
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
    *,
    edge: StarlinkEdge,
) -> PilotMethodCandidate:
    return _evaluate_candidate_with_policy(
        values,
        sample_rate_hz,
        candidate,
        edge=edge,
        include_qam=True,
        standard_cutline=False,
        glrt_size=_GLRT_SIZE,
    )


def _evaluate_standard_candidate(
    values: np.ndarray,
    sample_rate_hz: int,
    candidate,
    *,
    edge: StarlinkEdge,
    glrt_size: int,
    primary_qam_observer: PrimaryQamObserver | None = None,
) -> PilotMethodCandidate:
    return _evaluate_candidate_with_policy(
        values,
        sample_rate_hz,
        candidate,
        edge=edge,
        include_qam=candidate.rank == 0,
        standard_cutline=True,
        glrt_size=glrt_size,
        primary_qam_observer=primary_qam_observer,
    )


def _evaluate_candidate_with_policy(
    values: np.ndarray,
    sample_rate_hz: int,
    candidate,
    *,
    edge: StarlinkEdge,
    include_qam: bool,
    standard_cutline: bool,
    glrt_size: int,
    primary_qam_observer: PrimaryQamObserver | None = None,
) -> PilotMethodCandidate:
    # Keep QAM behind the numerical call boundary: QAM itself imports these
    # acquisition primitives, and an eager package-level import makes import
    # success depend on whether callers import QAM or Starlink first.
    from leo.analysis.qam import analyze_pilot_qam

    # QAM is an independent confirmer, not a trajectory proposal. Evaluate it
    # once on the primary acquisition basin instead of repeating the same
    # expensive frame solve for every ranked alternative.
    if include_qam:
        qam = analyze_pilot_qam(
            values,
            sample_rate_hz,
            epoch_sample=candidate.refined_epoch_sample,
            absolute_cfo_hz=candidate.absolute_cfo_hz,
            edge=edge,
        )
        if primary_qam_observer is not None:
            primary_qam_observer(qam)
        qam_accuracy = None if qam.metrics is None else qam.metrics.hard_symbol_accuracy
        qam_evm = None if qam.metrics is None else qam.metrics.rms_evm
    else:
        qam_accuracy = None
        qam_evm = None
    scores = conditioned_pilot_method_scores(
        values,
        sample_rate_hz,
        epoch_sample=candidate.refined_epoch_sample,
        acquired_cfo_hz=candidate.absolute_cfo_hz,
        symbolwise_exact=candidate.verify_score,
        symbolwise_control=candidate.conditioned_control_score,
        qam_accuracy=qam_accuracy,
        edge=edge,
        standard_cutline=standard_cutline,
        glrt_size=glrt_size,
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
    edge: StarlinkEdge,
    standard_cutline: bool = False,
    glrt_size: int = _GLRT_SIZE,
) -> tuple[PilotMethodScore, ...]:
    """Evaluate all confirmers at one already-acquired epoch and CFO."""

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("conditioned pilot samples must be a nonempty vector")
    finite = (acquired_cfo_hz, symbolwise_exact, symbolwise_control)
    if any(not math.isfinite(value) for value in finite):
        raise ValueError("conditioned pilot inputs must be finite")
    if isinstance(glrt_size, bool) or not isinstance(glrt_size, int) or glrt_size < 2:
        raise ValueError("GLRT size must be an integer of at least two")
    anchors = np.unique(np.rint(np.linspace(2, 301, 8)).astype(int))
    # Standard deliberately reports the three reviewed detector views. GLRT64
    # is the only trajectory-proposal lane; Symbolwise is already available
    # from acquisition and Anchor-8 remains the sparse diagnostic comparison.
    requested = (
        {
            PilotMethod.ANCHOR8: anchors,
            PilotMethod.GLRT64: np.arange(2, 66),
        }
        if standard_cutline
        else {
            PilotMethod.ANCHOR8: anchors,
            PilotMethod.DIFFERENTIAL16: np.arange(2, 18),
            PilotMethod.DIFFERENTIAL32: np.arange(2, 34),
            PilotMethod.GLRT32: np.arange(2, 34),
            PilotMethod.GLRT64: np.arange(2, 66),
            PilotMethod.EDGE_TRACKER: np.arange(2, 302),
        }
    )
    workspace = _conditioned_correlation_workspace(
        values,
        sample_rate_hz,
        epoch_sample,
        acquired_cfo_hz,
        edge=edge,
        selected_symbols=np.unique(np.concatenate(tuple(requested.values()))),
    )
    exact = {method: workspace.select(symbols) for method, symbols in requested.items()}
    control = {
        method: workspace.select(symbols, control=True) for method, symbols in requested.items()
    }
    anchor_exact = _anchor_score(exact[PilotMethod.ANCHOR8])
    anchor_control = _anchor_score(control[PilotMethod.ANCHOR8])
    if not standard_cutline:
        differential16, differential16_cfo = _differential(exact[PilotMethod.DIFFERENTIAL16])
        differential16_control = _differential(control[PilotMethod.DIFFERENTIAL16])[0]
        differential32, differential32_cfo = _differential(exact[PilotMethod.DIFFERENTIAL32])
        differential32_control = _differential(control[PilotMethod.DIFFERENTIAL32])[0]
        (glrt32, glrt32_cfo), (glrt32_control, _) = _glrt_pair(
            exact[PilotMethod.GLRT32], control[PilotMethod.GLRT32], size=glrt_size
        )
    (glrt64, glrt64_cfo), (glrt64_control, _) = _glrt_pair(
        exact[PilotMethod.GLRT64], control[PilotMethod.GLRT64], size=glrt_size
    )
    if not standard_cutline:
        edge_score = _edge_tracker(exact[PilotMethod.EDGE_TRACKER])
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
            PilotMethod.GLRT64,
            glrt64,
            glrt64_control,
            glrt64_cfo,
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
    if not standard_cutline:
        result[1:1] = [
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
        ]
        result.insert(
            -1,
            _score(
                PilotMethod.EDGE_TRACKER,
                edge_score,
                edge_control,
                0.0,
                acquired_cfo_hz,
            ),
        )
    if qam_accuracy is not None and not standard_cutline:
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


def conditioned_glrt64_score(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_sample: int,
    acquired_cfo_hz: float,
    edge: StarlinkEdge | str = StarlinkEdge.LOWER,
    glrt_size: int = _GLRT_SIZE,
) -> PilotMethodScore:
    """Evaluate only GLRT-64 at one acquired epoch/CFO.

    Fast scanners still use the reviewed symbolwise acquisition to find an
    epoch and coarse CFO, but must not pay for Anchor-8, QAM, or trajectory
    products when GLRT-64 is the sole requested decision lane.
    """

    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("conditioned pilot samples must be a nonempty vector")
    if not math.isfinite(acquired_cfo_hz):
        raise ValueError("acquired CFO must be finite")
    if isinstance(glrt_size, bool) or not isinstance(glrt_size, int) or glrt_size < 2:
        raise ValueError("GLRT size must be an integer of at least two")
    selected_edge = StarlinkEdge(edge)
    symbols = np.arange(2, 66)
    workspace = _conditioned_correlation_workspace(
        values,
        sample_rate_hz,
        epoch_sample,
        acquired_cfo_hz,
        selected_symbols=symbols,
        edge=selected_edge,
    )
    exact = workspace.select(symbols)
    control = workspace.select(symbols, control=True)
    (score, residual_cfo_hz), (control_score, _) = _glrt_pair(exact, control, size=glrt_size)
    return _score(
        PilotMethod.GLRT64,
        score,
        control_score,
        residual_cfo_hz,
        acquired_cfo_hz,
    )


def conditioned_glrt64_scores(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_samples: Sequence[int],
    acquired_cfo_hz: Sequence[float],
    edge: StarlinkEdge | str = StarlinkEdge.LOWER,
    glrt_size: int = _GLRT_SIZE,
) -> tuple[PilotMethodScore, ...]:
    """Evaluate GLRT-64 for several acquired candidates in one exact batch.

    The candidate dimension is only an execution detail: every returned score
    uses the same per-candidate frames, pilot/control definitions, and GLRT grid
    as :func:`conditioned_glrt64_score`. Unsupported symbol geometry falls back
    to that scalar oracle.
    """

    values = np.asarray(samples, dtype=np.complex128)
    epochs = np.asarray(epoch_samples)
    frequencies = np.asarray(acquired_cfo_hz, dtype=float)
    if values.ndim != 1 or not values.size:
        raise ValueError("conditioned pilot samples must be a nonempty vector")
    if epochs.ndim != 1 or frequencies.ndim != 1 or len(epochs) != len(frequencies):
        raise ValueError("candidate epochs and CFOs must be equally sized vectors")
    if not len(epochs):
        return ()
    if not np.issubdtype(epochs.dtype, np.integer):
        raise ValueError("candidate epochs must be integers")
    if np.any(epochs < 0):
        raise ValueError("candidate epochs must be nonnegative")
    if not np.all(np.isfinite(frequencies)):
        raise ValueError("acquired CFOs must be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if isinstance(glrt_size, bool) or not isinstance(glrt_size, int) or glrt_size < 2:
        raise ValueError("GLRT size must be an integer of at least two")

    selected_edge = StarlinkEdge(edge)
    symbols = np.arange(2, 66)
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    local_starts = np.rint(symbols * symbol_period).astype(int)
    local_stops = np.rint((symbols + 1) * symbol_period).astype(int)
    exact_template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, selected_edge), np.complex128
    )
    local_stops = np.minimum(local_stops, len(exact_template))
    counts = local_stops - local_starts
    symbol_times_s = (local_starts + (counts - 1) / 2) / sample_rate_hz
    symbol_step_s = float(np.median(np.diff(symbol_times_s)))
    expected_times_s = symbol_times_s[0] + np.arange(len(symbols)) * symbol_step_s
    if (
        np.any(counts < 2)
        or len(symbols) > glrt_size
        or 2 * len(symbols) - 1 > glrt_size
        or not np.allclose(symbol_times_s, expected_times_s, rtol=0.0, atol=1e-15)
    ):
        return tuple(
            conditioned_glrt64_score(
                values,
                sample_rate_hz,
                epoch_sample=int(epoch),
                acquired_cfo_hz=float(frequency),
                edge=selected_edge,
                glrt_size=glrt_size,
            )
            for epoch, frequency in zip(epochs, frequencies, strict=True)
        )

    control_template = np.asarray(
        qin_edge_pilot_frame(
            sample_rate_hz,
            selected_edge,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        ),
        np.complex128,
    )
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    frame_starts_by_candidate: list[np.ndarray] = []
    for epoch in epochs:
        starts: list[int] = []
        frame = 0
        while True:
            frame_start = int(epoch) + round(frame * frame_period)
            if frame_start + int(local_stops[-1]) > len(values):
                break
            starts.append(frame_start)
            frame += 1
        frame_starts_by_candidate.append(np.asarray(starts, dtype=int))
    maximum_frames = max((len(starts) for starts in frame_starts_by_candidate), default=0)
    if not maximum_frames:
        return tuple(
            _score(PilotMethod.GLRT64, 0.0, 0.0, 0.0, float(frequency))
            for frequency in frequencies
        )

    candidate_count = len(epochs)
    symbol_count = len(symbols)
    exact_values = np.zeros(
        (candidate_count, maximum_frames, symbol_count), dtype=np.complex128
    )
    control_values = np.zeros_like(exact_values)
    for count in np.unique(counts):
        positions = np.flatnonzero(counts == count)
        relative = local_starts[positions, None] + np.arange(int(count))[None, :]
        exact_reference = exact_template[relative]
        control_reference = control_template[relative]
        rotations = np.exp(
            -2j
            * np.pi
            * frequencies[:, None, None]
            * relative[None, :, :]
            / sample_rate_hz
        )
        for frame_index in range(maximum_frames):
            active_indexes = np.asarray(
                [
                    index
                    for index, starts in enumerate(frame_starts_by_candidate)
                    if frame_index < len(starts)
                ],
                dtype=int,
            )
            if not active_indexes.size:
                continue
            frame_starts = np.asarray(
                [
                    frame_starts_by_candidate[index][frame_index]
                    for index in active_indexes
                ],
                dtype=int,
            )
            absolute = frame_starts[:, None, None] + relative[None, :, :]
            corrected = values[absolute] * rotations[active_indexes]
            exact_values[
                active_indexes[:, None], frame_index, positions[None, :]
            ] = np.sum(
                np.conj(exact_reference)[None, :, :] * corrected,
                axis=2,
            )
            control_values[
                active_indexes[:, None], frame_index, positions[None, :]
            ] = np.sum(
                np.conj(control_reference)[None, :, :] * corrected,
                axis=2,
            )

    short_size = 1 << (2 * symbol_count - 2).bit_length()

    def evaluate(correlations: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        transformed = np.fft.fft(correlations, n=short_size, axis=2)
        autocorrelation = np.fft.ifft(np.sum(np.abs(transformed) ** 2, axis=1), axis=1)
        packed = np.zeros((candidate_count, glrt_size), dtype=np.complex128)
        packed[:, :symbol_count] = autocorrelation[:, :symbol_count]
        packed[:, -(symbol_count - 1) :] = autocorrelation[:, -(symbol_count - 1) :]
        spectrum = np.fft.fft(packed, axis=1).real
        ceiling = np.sum(np.sum(np.abs(correlations), axis=2) ** 2, axis=1)
        normalized = np.divide(
            spectrum,
            ceiling[:, None],
            out=np.zeros_like(spectrum),
            where=ceiling[:, None] > 0,
        )
        best = np.argmax(normalized, axis=1)
        return normalized[np.arange(candidate_count), best], best

    exact_scores, best_indexes = evaluate(exact_values)
    control_scores, _ = evaluate(control_values)
    candidate_symbol_steps = tuple(
        (
            float(
                np.median(
                    np.diff(
                        (
                            starts[:, None]
                            + local_starts[None, :]
                            + (counts[None, :] - 1) / 2
                        )
                        / sample_rate_hz,
                        axis=1,
                    )
                )
            )
            if len(starts)
            else None
        )
        for starts in frame_starts_by_candidate
    )
    residual_cfo_hz = np.asarray(
        [
            0.0 if step is None else float(np.fft.fftfreq(glrt_size, d=step)[best])
            for step, best in zip(candidate_symbol_steps, best_indexes, strict=True)
        ],
        dtype=float,
    )
    return tuple(
        _score(
            PilotMethod.GLRT64,
            float(exact_score),
            float(control_score),
            float(residual),
            float(acquired),
        )
        for exact_score, control_score, residual, acquired in zip(
            exact_scores,
            control_scores,
            residual_cfo_hz,
            frequencies,
            strict=True,
        )
    )


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
    edge: StarlinkEdge,
    symbol_roll: int,
) -> _SymbolCorrelations:
    chosen = np.asarray(symbols, dtype=int)
    if chosen.ndim != 1 or not chosen.size or np.any(np.diff(chosen) <= 0):
        raise ValueError("symbols must be nonempty and strictly increasing")
    if chosen[0] < _FIRST_PILOT_SYMBOL or chosen[-1] > _LAST_PILOT_SYMBOL:
        raise ValueError("pilot symbol lies outside 2..301")
    template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, edge, symbol_roll=symbol_roll),
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


def _conditioned_correlation_workspace(
    samples: np.ndarray,
    sample_rate_hz: int,
    epoch_sample: int,
    cfo_hz: float,
    *,
    edge: StarlinkEdge,
    selected_symbols: np.ndarray | None = None,
) -> _ConditionedCorrelationWorkspace:
    """Correlate exact/control pilots once, retaining per-symbol frame support."""

    exact_template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, edge), dtype=np.complex128)
    control_template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, edge, symbol_roll=CONTROL_SYMBOL_ROLL),
        dtype=np.complex128,
    )
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    symbol_period = sample_rate_hz * OFDM_SYMBOL_DURATION_S
    symbols = np.arange(_FIRST_PILOT_SYMBOL, _LAST_PILOT_SYMBOL + 1)
    selected = symbols if selected_symbols is None else np.asarray(selected_symbols, dtype=int)
    if (
        selected.ndim != 1
        or not selected.size
        or np.any(np.diff(selected) <= 0)
        or selected[0] < _FIRST_PILOT_SYMBOL
        or selected[-1] > _LAST_PILOT_SYMBOL
    ):
        raise ValueError("selected workspace symbols must be unique, ordered, and supported")
    selected_positions = selected - _FIRST_PILOT_SYMBOL
    local_starts = np.rint(symbols * symbol_period).astype(int)
    local_stops = np.minimum(
        np.rint((symbols + 1) * symbol_period).astype(int), len(exact_template)
    )
    counts = local_stops - local_starts
    frame_starts = []
    frame = 0
    while True:
        frame_start = epoch_sample + round(frame * frame_period)
        if frame_start >= len(samples) or frame_start + local_starts[0] >= len(samples):
            break
        frame_starts.append(frame_start)
        frame += 1
    shape = (len(frame_starts), len(symbols))
    exact_matrix = np.zeros(shape, dtype=np.complex128)
    exact_power_matrix = np.zeros(shape, dtype=float)
    control_matrix = np.zeros(shape, dtype=np.complex128)
    control_power_matrix = np.zeros(shape, dtype=float)
    time_matrix = np.zeros(shape, dtype=float)
    valid_matrix = np.zeros(shape, dtype=bool)

    for count in np.unique(counts[selected_positions]):
        if count < 2:
            continue
        positions = selected_positions[counts[selected_positions] == count]
        relative = local_starts[positions, None] + np.arange(int(count))[None, :]
        relative_rotation = np.exp(-2j * np.pi * cfo_hz * relative / sample_rate_hz)
        exact_reference = exact_template[relative]
        control_reference = control_template[relative]
        exact_energy = np.sum(np.abs(exact_reference) ** 2, axis=1)
        control_energy = np.sum(np.abs(control_reference) ** 2, axis=1)
        for frame_index, frame_start in enumerate(frame_starts):
            starts = frame_start + local_starts[positions]
            valid = (starts >= 0) & (starts + count <= len(samples))
            if not np.any(valid):
                continue
            active_positions = positions[valid]
            absolute = frame_start + relative[valid]
            # The frame start contributes one common phase to every symbol in
            # that frame. Factor it from the cached within-frame rotations
            # instead of evaluating one exponential per received sample.
            frame_rotation = np.exp(-2j * np.pi * cfo_hz * frame_start / sample_rate_hz)
            received = samples[absolute]
            corrected = received * relative_rotation[valid] * frame_rotation
            received_energy = np.sum(np.abs(received) ** 2, axis=1)
            exact_correlation = np.sum(np.conj(exact_reference[valid]) * corrected, axis=1)
            control_correlation = np.sum(np.conj(control_reference[valid]) * corrected, axis=1)
            exact_matrix[frame_index, active_positions] = exact_correlation
            control_matrix[frame_index, active_positions] = control_correlation
            exact_power_matrix[frame_index, active_positions] = np.abs(
                exact_correlation
            ) ** 2 / np.maximum(exact_energy[valid] * received_energy, 1e-20)
            control_power_matrix[frame_index, active_positions] = np.abs(
                control_correlation
            ) ** 2 / np.maximum(control_energy[valid] * received_energy, 1e-20)
            time_matrix[frame_index, active_positions] = (
                starts[valid] + (count - 1) / 2
            ) / sample_rate_hz
            valid_matrix[frame_index, active_positions] = True

    exact_values = tuple(exact_matrix[:, index].copy() for index in range(len(symbols)))
    exact_power = tuple(exact_power_matrix[:, index].copy() for index in range(len(symbols)))
    control_values = tuple(control_matrix[:, index].copy() for index in range(len(symbols)))
    control_power = tuple(control_power_matrix[:, index].copy() for index in range(len(symbols)))
    times = tuple(time_matrix[:, index].copy() for index in range(len(symbols)))
    valid_rows = tuple(valid_matrix[:, index].copy() for index in range(len(symbols)))
    return _ConditionedCorrelationWorkspace(
        tuple(exact_values),
        tuple(exact_power),
        tuple(control_values),
        tuple(control_power),
        tuple(times),
        tuple(valid_rows),
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
        float(np.angle(total) / (2 * np.pi * correlations.symbol_step_s)) if total != 0 else 0.0
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


def _glrt_pair(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
    *,
    size: int = _GLRT_SIZE,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Evaluate exact/control with an exact uniform FFT or the direct oracle."""

    _validate_glrt_pair(exact, control)
    if not exact.values.size:
        return (0.0, 0.0), (0.0, 0.0)
    if _uniform_glrt_geometry(exact, size=size):
        if 2 * exact.values.shape[1] - 1 <= size:
            return _glrt_pair_autocorrelation(exact, control, size=size)
        return _glrt_pair_fft(exact, control, size=size)
    return _glrt_pair_direct(exact, control, size=size)


def _glrt_pair_autocorrelation(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
    *,
    size: int = _GLRT_SIZE,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Evaluate paired GLRT spectra from summed short autocorrelations."""

    _validate_glrt_pair(exact, control)
    if not exact.values.size:
        return (0.0, 0.0), (0.0, 0.0)
    if not _uniform_glrt_geometry(exact, size=size):
        raise ValueError("GLRT symbol geometry is not a supported uniform grid")
    symbol_count = exact.values.shape[1]
    if 2 * symbol_count - 1 > size:
        raise ValueError("GLRT transform cannot contain the aperiodic autocorrelation")

    # The squared magnitude of each row transform is the transform of its
    # aperiodic autocorrelation. Sum those short autocorrelations first, then
    # evaluate only one target-size transform for exact and one for control.
    short_size = 1 << (2 * symbol_count - 2).bit_length()
    frame_count = exact.values.shape[0]
    combined = np.concatenate((exact.values, control.values), axis=0)
    short = np.fft.fft(combined, n=short_size, axis=1)
    grid = np.fft.fftfreq(size, d=exact.symbol_step_s)

    def evaluate(values: np.ndarray, transformed: np.ndarray) -> tuple[float, float]:
        autocorrelation = np.fft.ifft(np.sum(np.abs(transformed) ** 2, axis=0))
        packed = np.zeros(size, dtype=np.complex128)
        packed[:symbol_count] = autocorrelation[:symbol_count]
        if symbol_count > 1:
            packed[-(symbol_count - 1) :] = autocorrelation[-(symbol_count - 1) :]
        spectrum = np.fft.fft(packed).real
        ceiling = _coherent_ceiling(values)
        normalized = spectrum / ceiling if ceiling > 0 else spectrum
        best = int(np.argmax(normalized))
        return float(normalized[best]), float(grid[best])

    return (
        evaluate(exact.values, short[:frame_count]),
        evaluate(control.values, short[frame_count:]),
    )


def _glrt_pair_fft(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
    *,
    size: int = _GLRT_SIZE,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Evaluate a paired GLRT exactly on one uniform DFT grid."""

    _validate_glrt_pair(exact, control)
    if not exact.values.size:
        return (0.0, 0.0), (0.0, 0.0)
    if not _uniform_glrt_geometry(exact, size=size):
        raise ValueError("GLRT symbol geometry is not a supported uniform grid")
    frame_count = exact.values.shape[0]
    combined = np.concatenate((exact.values, control.values), axis=0)
    transformed = np.fft.fft(combined, n=size, axis=1)
    grid = np.fft.fftfreq(size, d=exact.symbol_step_s)

    def evaluate(values: np.ndarray, transformed_values: np.ndarray) -> tuple[float, float]:
        spectrum = np.sum(np.abs(transformed_values) ** 2, axis=0)
        ceiling = _coherent_ceiling(values)
        normalized = spectrum / ceiling if ceiling > 0 else spectrum
        best = int(np.argmax(normalized))
        return float(normalized[best]), float(grid[best])

    return (
        evaluate(exact.values, transformed[:frame_count]),
        evaluate(control.values, transformed[frame_count:]),
    )


def _glrt_pair_direct(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
    *,
    size: int = _GLRT_SIZE,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Direct paired phase-bank oracle for arbitrary supported geometry."""

    _validate_glrt_pair(exact, control)
    if not exact.values.size:
        return (0.0, 0.0), (0.0, 0.0)
    grid = np.fft.fftfreq(size, d=exact.symbol_step_s)
    # Every row shares the same within-frame sample geometry. Absolute frame
    # time affects only a discarded common phase, so one compact phase bank is
    # sufficient for all supported frames.
    lags = exact.times_s[0] - exact.times_s[0, 0]
    phase = np.exp(-2j * np.pi * grid[:, None] * lags[None, :])

    def evaluate(correlations: _SymbolCorrelations) -> tuple[float, float]:
        spectrum = np.sum(
            np.abs(np.sum(correlations.values[None, :, :] * phase[:, None, :], axis=2)) ** 2,
            axis=1,
        )
        ceiling = _coherent_ceiling(correlations.values)
        normalized = spectrum / ceiling if ceiling > 0 else spectrum
        best = int(np.argmax(normalized))
        return float(normalized[best]), float(grid[best])

    return evaluate(exact), evaluate(control)


def _validate_glrt_pair(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
) -> None:
    if exact.values.shape != control.values.shape or not np.array_equal(
        exact.times_s, control.times_s
    ):
        raise ValueError("paired GLRT correlations must have identical geometry")


def _uniform_glrt_geometry(correlations: _SymbolCorrelations, *, size: int) -> bool:
    if correlations.values.ndim != 2 or correlations.times_s.shape != correlations.values.shape:
        return False
    if correlations.values.shape[1] > size:
        return False
    lags = correlations.times_s - correlations.times_s[:, :1]
    expected = np.arange(correlations.values.shape[1], dtype=float) * correlations.symbol_step_s
    return bool(np.allclose(lags, expected[None, :], rtol=0.0, atol=1e-15))


def _edge_tracker(correlations: _SymbolCorrelations) -> float:
    return (
        float(np.mean(correlations.normalized_power)) if correlations.normalized_power.size else 0.0
    )
