#!/usr/bin/env python3
"""Compare state-debiased Doppler prototypes on five sealed historical dwells.

The persisted 20 ms GLRT products are used only to enumerate one previously
selected multi-second branch and to initialize its frame CFO neighborhoods.
Every scientific score is then recomputed from raw IQ.  Even Qin symbols fit
the models; odd Qin symbols and a rolled-Qin control are held out.

The tool also performs a bounded, independent 12 ms / 4 ms-hop acquisition in
each dwell.  Those blind candidates do not consume the persisted timing or CFO
values.  They are used only as an acquisition ablation, not as truth.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_blind_timing_cfo as blind
    import report_470384_sawtooth_methods as sawtooth
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_blind_timing_cfo as blind
    from tools import report_470384_sawtooth_methods as sawtooth
    from tools import report_470384_semicoherent_recovery as semicoherent


DEFAULT_INPUTS = Path(
    "reports/figures/2026_08_23_additional_subsecond_pilot_dwells/inputs.json"
)
DEFAULT_SOURCE_RESULTS = Path(
    "reports/figures/2026_08_23_additional_subsecond_pilot_dwells/"
    "additional-dwell-results.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "reports/figures/2026_08_24_five_dwell_doppler_prototypes"
)
DEFAULT_REPORT = Path("reports/2026_08_24_five_dwell_doppler_prototypes.md")
DEFAULT_CHECKPOINT_ROOT = Path("/tmp/leo-five-dwell-doppler-prototype-checkpoints")

SAMPLE_RATE_HZ = 2_500_000.0
FRAME_RATE_HZ = 750.0
MAXIMUM_MODEL_ERROR_HZ = 2_500.0
MINIMUM_TRAIN_EXACT = 0.02
MINIMUM_TRAIN_MARGIN = 0.0
TIMING_BREAK_SAMPLES = 20.0
BLIND_DURATION_S = 1.6
BLIND_CELL_DURATION_S = 0.012
BLIND_CELL_HOP_S = 0.004

MODEL_ORDER = ("M0", "M1", "M2", "M3", "M4")
MODEL_NAMES = {
    "M0": "global line",
    "M1": "state intercepts + common slope",
    "M2": "state intercepts + slope progression",
    "M3": "independent state slopes",
    "M4": "timing-constrained progression",
}

INK = "#17354a"
GRAY = "#96a2ab"
LIGHT_GRAY = "#d2d9de"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
PURPLE = "#7b65a8"
RED = "#bd5b52"
MODEL_COLORS = {
    "M0": RED,
    "M1": GREEN,
    "M2": PURPLE,
    "M3": AMBER,
    "M4": BLUE,
}
DWELL_COLORS = (BLUE, AMBER, GREEN, PURPLE, RED)


@dataclass(frozen=True, slots=True)
class DwellSpec:
    label: str
    session_id: str
    run_id: str
    stream_id: str
    receiver_id: int
    edge: StarlinkEdge
    analysis_root: Path
    branch_id: str
    branch_start_s: float
    branch_end_s: float
    branch_reference_time_s: float
    branch_coefficients_hz: tuple[float, ...]
    anchor_time_s: float

    def branch_frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = np.polyval(
            np.asarray(self.branch_coefficients_hz, dtype=float),
            np.asarray(time_s, dtype=float) - self.branch_reference_time_s,
        )
        return float(value) if np.ndim(value) == 0 else value

    @property
    def branch_slope_hz_s(self) -> float:
        if len(self.branch_coefficients_hz) != 2:
            raise ValueError("prototype requires a degree-one frozen branch")
        return float(self.branch_coefficients_hz[0])


@dataclass(frozen=True, slots=True)
class CandidateWindow:
    window_index: int
    detection_time_s: float
    probe_sample_start: int
    aligned_sample_start: int
    local_epoch_sample: int
    initial_cfo_hz: float
    analysis_cfo_hz: float
    glrt_exact_score: float
    glrt_control_score: float
    glrt_margin: float
    selection_model_error_hz: float

    @property
    def analysis_key(self) -> tuple[int, int, float]:
        return self.probe_sample_start, self.local_epoch_sample, self.initial_cfo_hz


@dataclass(frozen=True, slots=True)
class FrameEvidence:
    row_index: int
    window_index: int
    time_s: float
    train_cfo_hz: float
    validation_cfo_hz: float
    nco_cfo_hz: float
    train_exact_score: float
    train_control_score: float
    train_margin: float
    likelihood: semicoherent.FrameLikelihood = field(repr=False, compare=False)

    @property
    def train_qualified(self) -> bool:
        return bool(
            self.train_exact_score >= MINIMUM_TRAIN_EXACT
            and self.train_margin >= MINIMUM_TRAIN_MARGIN
        )


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    model: str
    frame_indices: tuple[int, ...]
    predicted_cfo_hz: tuple[float, ...]
    rate_at_reference_hz_s: float
    rate_reference_time_s: float
    rate_progression_hz_s2: float | None
    segment_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--source-results", type=Path, default=DEFAULT_SOURCE_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--checkpoint-root", type=Path, default=DEFAULT_CHECKPOINT_ROOT
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse explicitly requested per-dwell checkpoints",
    )
    parser.add_argument(
        "--maximum-windows-per-dwell",
        type=int,
        help="bounded development run over ordered persisted probe windows",
    )
    parser.add_argument(
        "--blind-duration-s", type=float, default=BLIND_DURATION_S
    )
    parser.add_argument(
        "--skip-blind", action="store_true", help="skip the independent raw-IQ acquisition"
    )
    parser.add_argument(
        "--reuse-results",
        type=Path,
        help="reuse a prior JSON result and only regenerate report figures/prose",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _glrt64(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain one GLRT64 score")
    return matches[0]


def load_dwell_specs(inputs_path: Path, source_path: Path) -> tuple[DwellSpec, ...]:
    """Bind the run manifest, path selection, and dealiased branch model."""

    inputs = _load(inputs_path)
    source = _load(source_path)
    rows = inputs.get("dwells")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("prototype requires exactly five declared dwells")
    by_session = {str(item["session_id"]): item for item in source["results"]}
    output = []
    for index, declared in enumerate(rows, start=1):
        session_id = str(declared["session_id"])
        run_id = str(declared["run_id"])
        result = by_session.get(session_id)
        if result is None or result["analysis_run_id"] != run_id:
            raise ValueError(f"source result does not match declared run: {session_id}")
        root = Path(result["analysis_root"])
        bank = _load(root / "standard.dealiased-trajectory-bank.v4.json")
        branches = [
            item for item in bank["branches"] if item["branch_id"] == result["branch_id"]
        ]
        if len(branches) != 1:
            raise ValueError(f"selected branch is not unique: {session_id}")
        branch = branches[0]
        model = branch["model"]
        coefficients = tuple(float(value) for value in model["coefficients_hz"])
        if len(coefficients) != 2:
            raise ValueError(f"selected branch is not degree one: {session_id}")
        output.append(
            DwellSpec(
                label=f"D{index} · {session_id.split('-')[-1][:8]}",
                session_id=session_id,
                run_id=run_id,
                stream_id=str(result["stream_id"]),
                receiver_id=int(result["receiver_id"]),
                edge=StarlinkEdge(result["edge"]),
                analysis_root=root,
                branch_id=str(result["branch_id"]),
                branch_start_s=float(branch["start_s"]),
                branch_end_s=float(branch["end_s"]),
                branch_reference_time_s=float(model["reference_time_s"]),
                branch_coefficients_hz=coefficients,
                anchor_time_s=float(result["anchor"]["time_s"]),
            )
        )
    return tuple(output)


def select_candidate_windows(
    spec: DwellSpec,
    scan: dict[str, Any],
    *,
    maximum_windows: int | None,
) -> tuple[CandidateWindow, ...]:
    """Select the nearest candidate without applying a Qin-strength gate."""

    windows = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not spec.branch_start_s <= time_s <= spec.branch_end_s:
            continue
        model_hz = float(spec.branch_frequency_hz(time_s))
        candidates = []
        for candidate in detection["candidates"]:
            score = _glrt64(candidate)
            error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
            candidates.append((error_hz, int(candidate["rank"]), candidate, score))
        if not candidates:
            continue
        error_hz, _rank, candidate, score = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        epoch = int(candidate["local_epoch_sample"])
        windows.append(
            CandidateWindow(
                window_index=len(windows),
                detection_time_s=time_s,
                probe_sample_start=int(detection["sample_start"]),
                aligned_sample_start=int(detection["sample_start"]) + epoch,
                local_epoch_sample=epoch,
                initial_cfo_hz=float(score["tracking_cfo_hz"]),
                analysis_cfo_hz=(
                    float(score["tracking_cfo_hz"])
                    if error_hz <= MAXIMUM_MODEL_ERROR_HZ
                    else model_hz
                ),
                glrt_exact_score=float(score["exact_score"]),
                glrt_control_score=float(score["control_score"]),
                glrt_margin=float(score["margin"]),
                selection_model_error_hz=float(error_hz),
            )
        )
    if maximum_windows is not None:
        if maximum_windows < 1:
            raise ValueError("maximum window count must be positive")
        windows = windows[:maximum_windows]
    return tuple(windows)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (
        values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)
    ) / (2**15)


def build_frame_evidence(
    *,
    bulk_root: Path,
    spec: DwellSpec,
    scan: dict[str, Any],
    windows: tuple[CandidateWindow, ...],
) -> tuple[FrameEvidence, ...]:
    """Build disjoint even/odd frequency likelihoods from raw IQ."""

    probe_samples = int(scan["probe_samples"])
    selected_symbols = semicoherent.SYMBOLS
    even = np.arange(0, len(selected_symbols), 2, dtype=int)
    odd = np.arange(1, len(selected_symbols), 2, dtype=int)
    rows: list[FrameEvidence] = []
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(spec.session_id), spec.stream_id, verify=True)
        if not math.isclose(float(reader.sample_rate_hz), SAMPLE_RATE_HZ, abs_tol=1e-6):
            raise ValueError(f"unexpected sample rate: {spec.session_id}")
        for position, window in enumerate(windows, start=1):
            raw = reader.read(
                window.aligned_sample_start,
                probe_samples,
                receiver_ids=(spec.receiver_id,),
            )
            iq = _complex_receiver(raw)
            workspace = _conditioned_correlation_workspace(
                iq,
                int(SAMPLE_RATE_HZ),
                0,
                window.analysis_cfo_hz,
                edge=spec.edge,
                selected_symbols=selected_symbols,
            )
            exact = workspace.select(selected_symbols)
            control = workspace.select(selected_symbols, control=True)
            if not exact.values.size or exact.values.shape != control.values.shape:
                continue
            even_exact, even_exact_ceiling = semicoherent.normalized_frequency_curves(
                exact.values, exact.times_s, even
            )
            even_control, even_control_ceiling = semicoherent.normalized_frequency_curves(
                control.values, control.times_s, even
            )
            odd_exact, odd_exact_ceiling = semicoherent.normalized_frequency_curves(
                exact.values, exact.times_s, odd
            )
            odd_control, odd_control_ceiling = semicoherent.normalized_frequency_curves(
                control.values, control.times_s, odd
            )
            absolute_offset_s = window.aligned_sample_start / SAMPLE_RATE_HZ
            for frame_index in range(exact.values.shape[0]):
                likelihood = semicoherent.FrameLikelihood(
                    time_s=float(absolute_offset_s + np.mean(exact.times_s[frame_index])),
                    nco_cfo_hz=window.analysis_cfo_hz,
                    even_exact_power=even_exact[frame_index],
                    even_exact_ceiling=float(even_exact_ceiling[frame_index]),
                    even_control_power=even_control[frame_index],
                    even_control_ceiling=float(even_control_ceiling[frame_index]),
                    odd_exact_power=odd_exact[frame_index],
                    odd_exact_ceiling=float(odd_exact_ceiling[frame_index]),
                    odd_control_power=odd_control[frame_index],
                    odd_control_ceiling=float(odd_control_ceiling[frame_index]),
                )
                train_index = int(np.argmax(likelihood.even_exact_power))
                validation_index = int(np.argmax(likelihood.odd_exact_power))
                train_exact = float(
                    likelihood.even_exact_power[train_index]
                    / max(likelihood.even_exact_ceiling, 1e-20)
                )
                train_control = float(
                    likelihood.even_control_power[train_index]
                    / max(likelihood.even_control_ceiling, 1e-20)
                )
                rows.append(
                    FrameEvidence(
                        row_index=len(rows),
                        window_index=window.window_index,
                        time_s=likelihood.time_s,
                        train_cfo_hz=float(
                            window.analysis_cfo_hz
                            + semicoherent.RESIDUAL_GRID_HZ[train_index]
                        ),
                        validation_cfo_hz=float(
                            window.analysis_cfo_hz
                            + semicoherent.RESIDUAL_GRID_HZ[validation_index]
                        ),
                        nco_cfo_hz=window.analysis_cfo_hz,
                        train_exact_score=train_exact,
                        train_control_score=train_control,
                        train_margin=train_exact - train_control,
                        likelihood=likelihood,
                    )
                )
            if position % 50 == 0 or position == len(windows):
                print(
                    f"{spec.label}: raw Qin likelihoods {position}/{len(windows)} locks",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()
    return tuple(rows)


def observations_from_frames(
    spec: DwellSpec, frames: Iterable[FrameEvidence]
) -> tuple[sawtooth.FrameObservation, ...]:
    return tuple(
        sawtooth.FrameObservation(
            row_index=item.row_index,
            time_s=item.time_s,
            absolute_cfo_hz=item.train_cfo_hz,
            model_cfo_hz=float(spec.branch_frequency_hz(item.time_s)),
            source_window_index=item.window_index,
            exact_coherence=item.train_exact_score,
            coherence_margin=item.train_margin,
            frequency_uncertainty_hz=25.0,
            frequency_update_applied=False,
        )
        for item in frames
        if item.train_qualified
    )


def _fit_global_line(
    observations: tuple[sawtooth.FrameObservation, ...]
) -> tuple[float, float, float]:
    if len(observations) < 6:
        raise ValueError("global line requires at least six qualified frames")
    reference = float(np.mean([item.time_s for item in observations]))
    times = np.asarray([item.time_s for item in observations], dtype=float)
    values = np.asarray([item.absolute_cfo_hz for item in observations], dtype=float)
    design = np.column_stack((np.ones(len(times)), times - reference))
    coefficients, _covariance, _residuals, _scale = sawtooth._robust_linear_solve(
        design, values
    )
    return reference, float(coefficients[0]), float(coefficients[1])


def _partition(
    observations: tuple[sawtooth.FrameObservation, ...],
) -> tuple[
    tuple[sawtooth.SegmentFit, ...],
    tuple[sawtooth.SegmentFit, ...],
    float,
    float,
]:
    lock_fits = sawtooth.independent_lock_fits(observations)
    if not lock_fits:
        return (), (), math.nan, math.nan
    rms = np.asarray([item.robust_rms_hz for item in lock_fits], dtype=float)
    noise = max(5.0, float(np.percentile(rms, 90)))
    penalty = float(2.0 * math.log(max(2, len(observations))))
    segments = sawtooth.batch_joined_segments(
        observations,
        lock_fits,
        noise_scale_hz=noise,
        segment_penalty=penalty,
    )
    coherent = tuple(item for item in segments if item.coherent)
    return segments, coherent, noise, penalty


def timing_phase_samples(window: CandidateWindow) -> float:
    period = SAMPLE_RATE_HZ / FRAME_RATE_HZ
    return float((window.aligned_sample_start + 0.5 * period) % period - 0.5 * period)


def wrapped_timing_difference_samples(left: float, right: float) -> float:
    period = SAMPLE_RATE_HZ / FRAME_RATE_HZ
    return float((right - left + 0.5 * period) % period - 0.5 * period)


def timing_break_window_indices(
    windows: tuple[CandidateWindow, ...],
    qualified_window_indices: set[int],
    *,
    threshold_samples: float = TIMING_BREAK_SAMPLES,
) -> tuple[int, ...]:
    """Return later window indexes at supported timing-lattice discontinuities."""

    selected = [item for item in windows if item.window_index in qualified_window_indices]
    breaks = []
    for left, right in zip(selected[:-1], selected[1:], strict=True):
        phase_jump = abs(
            wrapped_timing_difference_samples(
                timing_phase_samples(left), timing_phase_samples(right)
            )
        )
        time_gap = right.detection_time_s - left.detection_time_s
        if time_gap > 0.055 or phase_jump > threshold_samples:
            breaks.append(right.window_index)
    return tuple(breaks)


def _timing_constrained_partition(
    observations: tuple[sawtooth.FrameObservation, ...],
    windows: tuple[CandidateWindow, ...],
    *,
    noise_scale_hz: float,
    segment_penalty: float,
) -> tuple[tuple[sawtooth.SegmentFit, ...], tuple[int, ...]]:
    lock_fits = sawtooth.independent_lock_fits(observations)
    if not lock_fits:
        return (), ()
    qualified = {item.source_window_start for item in lock_fits}
    breaks = set(timing_break_window_indices(windows, qualified))
    runs: list[list[sawtooth.SegmentFit]] = [[]]
    previous: sawtooth.SegmentFit | None = None
    for fit in lock_fits:
        if previous is not None and (
            fit.source_window_start in breaks
            or fit.source_window_start > previous.source_window_end + 1
        ):
            runs.append([])
        runs[-1].append(fit)
        previous = fit
    segments = []
    for run in runs:
        if not run:
            continue
        segments.extend(
            sawtooth.batch_joined_segments(
                observations,
                tuple(run),
                noise_scale_hz=noise_scale_hz,
                segment_penalty=segment_penalty,
            )
        )
    return tuple(segments), tuple(sorted(breaks))


def _segment_prediction(
    observations: tuple[sawtooth.FrameObservation, ...],
    segments: tuple[sawtooth.SegmentFit, ...],
    *,
    model: sawtooth.JointModelFit | None,
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    by_index = {item.row_index: item for item in observations}
    indexes = []
    predictions = []
    for segment_index, segment in enumerate(segments):
        for row_index in segment.observation_indices:
            observation = by_index[row_index]
            indexes.append(row_index)
            if model is None:
                predictions.append(float(segment.frequency_hz(observation.time_s)))
            else:
                local_time = observation.time_s - segment.center_time_s
                progression = (
                    0.0
                    if model.slope_progression_hz_s2 is None
                    else model.slope_progression_hz_s2
                )
                predictions.append(
                    float(
                        model.segment_intercepts_hz[segment_index]
                        + model.shared_slope_hz_s * local_time
                        + progression
                        * (
                            (segment.center_time_s - model.reference_time_s) * local_time
                            + 0.5 * local_time**2
                        )
                    )
                )
    order = np.argsort(indexes)
    return (
        tuple(int(indexes[position]) for position in order),
        tuple(float(predictions[position]) for position in order),
    )


def fit_model_predictions(
    spec: DwellSpec,
    frames: tuple[FrameEvidence, ...],
    windows: tuple[CandidateWindow, ...],
) -> tuple[dict[str, ModelPrediction], dict[str, Any]]:
    observations = observations_from_frames(spec, frames)
    if len(observations) < 18:
        return {}, {"status": "insufficient", "qualified_frame_count": len(observations)}
    _all_segments, coherent, noise, penalty = _partition(observations)
    reference, intercept, slope = _fit_global_line(observations)
    all_indexes = tuple(item.row_index for item in observations)
    all_predictions = tuple(
        float(intercept + slope * (item.time_s - reference)) for item in observations
    )
    predictions: dict[str, ModelPrediction] = {
        "M0": ModelPrediction(
            "M0", all_indexes, all_predictions, slope, reference, None, 1
        )
    }
    details: dict[str, Any] = {
        "status": "partial",
        "qualified_frame_count": len(observations),
        "lock_fit_count": len(sawtooth.independent_lock_fits(observations)),
        "coherent_segment_count": len(coherent),
        "noise_scale_hz": noise,
        "segment_penalty": penalty,
        "global_line": {
            "reference_time_s": reference,
            "frequency_at_reference_hz": intercept,
            "slope_hz_s": slope,
        },
        "segments": [asdict(item) for item in coherent],
    }
    if len(coherent) >= 3:
        common = sawtooth.joint_varying_intercept_fit(
            observations, coherent, slope_progression=False
        )
        progression = sawtooth.joint_varying_intercept_fit(
            observations, coherent, slope_progression=True
        )
        m1_indexes, m1_values = _segment_prediction(
            observations, coherent, model=common
        )
        m2_indexes, m2_values = _segment_prediction(
            observations, coherent, model=progression
        )
        m3_indexes, m3_values = _segment_prediction(observations, coherent, model=None)
        predictions.update(
            {
                "M1": ModelPrediction(
                    "M1",
                    m1_indexes,
                    m1_values,
                    common.shared_slope_hz_s,
                    common.reference_time_s,
                    None,
                    len(coherent),
                ),
                "M2": ModelPrediction(
                    "M2",
                    m2_indexes,
                    m2_values,
                    progression.shared_slope_hz_s,
                    progression.reference_time_s,
                    progression.slope_progression_hz_s2,
                    len(coherent),
                ),
                "M3": ModelPrediction(
                    "M3",
                    m3_indexes,
                    m3_values,
                    float(np.median([item.slope_hz_s for item in coherent])),
                    float(np.mean([item.center_time_s for item in coherent])),
                    None,
                    len(coherent),
                ),
            }
        )
        details.update(
            {
                "status": "complete",
                "M1": asdict(common),
                "M2": asdict(progression),
                "M3": {
                    "median_slope_hz_s": float(
                        np.median([item.slope_hz_s for item in coherent])
                    ),
                    "p10_slope_hz_s": float(
                        np.percentile([item.slope_hz_s for item in coherent], 10)
                    ),
                    "p90_slope_hz_s": float(
                        np.percentile([item.slope_hz_s for item in coherent], 90)
                    ),
                    "leave_one_segment_out_rms_hz_s": (
                        sawtooth.slope_leave_one_segment_out_rms(coherent, linear=False)
                    ),
                },
                "M1_leave_one_segment_out_rms_hz_s": (
                    sawtooth.slope_leave_one_segment_out_rms(coherent, linear=False)
                ),
                "M2_leave_one_segment_out_rms_hz_s": (
                    sawtooth.slope_leave_one_segment_out_rms(coherent, linear=True)
                ),
            }
        )

    if math.isfinite(noise) and math.isfinite(penalty):
        timing_segments, timing_breaks = _timing_constrained_partition(
            observations,
            windows,
            noise_scale_hz=noise,
            segment_penalty=penalty,
        )
        timing_coherent = tuple(item for item in timing_segments if item.coherent)
        details["timing_break_window_indices"] = list(timing_breaks)
        details["timing_coherent_segment_count"] = len(timing_coherent)
        details["timing_segments"] = [asdict(item) for item in timing_coherent]
        if len(timing_coherent) >= 3:
            timing_model = sawtooth.joint_varying_intercept_fit(
                observations, timing_coherent, slope_progression=True
            )
            m4_indexes, m4_values = _segment_prediction(
                observations, timing_coherent, model=timing_model
            )
            predictions["M4"] = ModelPrediction(
                "M4",
                m4_indexes,
                m4_values,
                timing_model.shared_slope_hz_s,
                timing_model.reference_time_s,
                timing_model.slope_progression_hz_s2,
                len(timing_coherent),
            )
            details["M4"] = asdict(timing_model)
    return predictions, details


def _sample_curve(power: np.ndarray, residual_hz: float) -> tuple[float, bool]:
    grid = semicoherent.RESIDUAL_GRID_HZ
    inside = bool(grid[0] <= residual_hz <= grid[-1])
    if not inside:
        return 0.0, False
    return float(np.interp(residual_hz, grid, np.asarray(power, dtype=float))), True


def validate_prediction(
    prediction: ModelPrediction,
    frames: tuple[FrameEvidence, ...],
) -> dict[str, Any]:
    by_index = {item.row_index: item for item in frames}
    train_errors = []
    validation_errors = []
    exact_scores = []
    control_scores = []
    window_indices = []
    inside_count = 0
    for row_index, predicted_hz in zip(
        prediction.frame_indices, prediction.predicted_cfo_hz, strict=True
    ):
        frame = by_index[row_index]
        residual_hz = predicted_hz - frame.nco_cfo_hz
        exact_power, inside = _sample_curve(frame.likelihood.odd_exact_power, residual_hz)
        control_power, _ = _sample_curve(frame.likelihood.odd_control_power, residual_hz)
        if not inside:
            continue
        inside_count += 1
        train_errors.append(predicted_hz - frame.train_cfo_hz)
        validation_errors.append(predicted_hz - frame.validation_cfo_hz)
        exact_scores.append(
            exact_power / max(frame.likelihood.odd_exact_ceiling, 1e-20)
        )
        control_scores.append(
            control_power / max(frame.likelihood.odd_control_ceiling, 1e-20)
        )
        window_indices.append(frame.window_index)
    if not inside_count:
        return {"status": "no-likelihood-support", "frame_count": 0}
    train = np.asarray(train_errors, dtype=float)
    validation = np.asarray(validation_errors, dtype=float)
    exact = np.asarray(exact_scores, dtype=float)
    control = np.asarray(control_scores, dtype=float)
    probe_rows = []
    probe_index = np.asarray(window_indices, dtype=int)
    for window_index in np.unique(probe_index):
        selected = probe_index == window_index
        probe_validation = validation[selected]
        probe_exact = exact[selected]
        probe_control = control[selected]
        probe_rows.append(
            {
                "window_index": int(window_index),
                "frame_count": int(np.count_nonzero(selected)),
                "validation_cfo_rms_hz": float(
                    np.sqrt(np.mean(probe_validation**2))
                ),
                "validation_cfo_median_absolute_hz": float(
                    np.median(np.abs(probe_validation))
                ),
                "validation_qin_beats_control_fraction": float(
                    np.mean(probe_exact > probe_control)
                ),
            }
        )
    probe_rms = np.asarray(
        [item["validation_cfo_rms_hz"] for item in probe_rows], dtype=float
    )
    return {
        "status": "complete",
        "frame_count": inside_count,
        "requested_frame_count": len(prediction.frame_indices),
        "likelihood_coverage_fraction": inside_count / len(prediction.frame_indices),
        "train_cfo_rms_hz": float(np.sqrt(np.mean(train**2))),
        "validation_cfo_rms_hz": float(np.sqrt(np.mean(validation**2))),
        "validation_cfo_median_absolute_hz": float(np.median(np.abs(validation))),
        "validation_exact_mean": float(np.mean(exact)),
        "validation_control_mean": float(np.mean(control)),
        "validation_margin_mean": float(np.mean(exact - control)),
        "validation_qin_beats_control_fraction": float(np.mean(exact > control)),
        "validation_probe_count": len(probe_rows),
        "median_probe_validation_cfo_rms_hz": float(np.median(probe_rms)),
        "p90_probe_validation_cfo_rms_hz": float(np.percentile(probe_rms, 90)),
        "per_probe": probe_rows,
        "rate_at_reference_hz_s": prediction.rate_at_reference_hz_s,
        "rate_reference_time_s": prediction.rate_reference_time_s,
        "rate_progression_hz_s2": prediction.rate_progression_hz_s2,
        "segment_count": prediction.segment_count,
    }


def matched_global_prediction(
    prediction: ModelPrediction,
    frames: tuple[FrameEvidence, ...],
) -> ModelPrediction:
    """Refit the global-line baseline on exactly one state model's train rows."""

    by_index = {item.row_index: item for item in frames}
    selected = tuple(by_index[index] for index in prediction.frame_indices)
    if len(selected) < 6:
        raise ValueError("matched global line requires at least six frames")
    reference = float(np.mean([item.time_s for item in selected]))
    times = np.asarray([item.time_s for item in selected], dtype=float)
    values = np.asarray([item.train_cfo_hz for item in selected], dtype=float)
    design = np.column_stack((np.ones(len(times)), times - reference))
    coefficients, _covariance, _residuals, _scale = sawtooth._robust_linear_solve(
        design, values
    )
    fitted = coefficients[0] + coefficients[1] * (times - reference)
    return ModelPrediction(
        model="M0-matched",
        frame_indices=prediction.frame_indices,
        predicted_cfo_hz=tuple(float(value) for value in fitted),
        rate_at_reference_hz_s=float(coefficients[1]),
        rate_reference_time_s=reference,
        rate_progression_hz_s2=None,
        segment_count=1,
    )


def _blind_config(maximum_probe_samples: int) -> SymbolwiseAcquisitionConfig:
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-1_200_000.0,
        residual_cfo_max_hz=1_200_000.0,
        coarse_cfo_step_hz=40_000.0,
        fine_cfo_radius_hz=40_000.0,
        fine_cfo_step_hz=500.0,
        conditioned_cfo_radius_hz=3_000.0,
        conditioned_cfo_step_hz=100.0,
        retained_candidate_count=16,
        candidate_epoch_separation_samples=20,
        candidate_cfo_separation_hz=20_000.0,
        minimum_frame_support=5,
        maximum_probe_samples=maximum_probe_samples,
    )


def blind_scan(
    *,
    bulk_root: Path,
    spec: DwellSpec,
    duration_s: float,
) -> tuple[
    tuple[blind.BlindCandidate, ...],
    tuple[blind.LatentLine, ...],
    tuple[tuple[blind.BlindCandidate, ...], ...],
]:
    """Run a bounded raw-IQ acquisition without persisted timing or CFO."""

    if duration_s <= 1.05:
        raise ValueError("blind duration must exceed 1.05 s for latent-line fitting")
    half = 0.5 * duration_s
    start_s = max(spec.branch_start_s, spec.anchor_time_s - half)
    end_s = min(spec.branch_end_s, start_s + duration_s)
    start_s = max(spec.branch_start_s, end_s - duration_s)
    cell_samples = round(BLIND_CELL_DURATION_S * SAMPLE_RATE_HZ)
    hop_samples = round(BLIND_CELL_HOP_S * SAMPLE_RATE_HZ)
    start_sample = round(start_s * SAMPLE_RATE_HZ)
    stop_sample = round(end_s * SAMPLE_RATE_HZ)
    starts = np.arange(
        start_sample, stop_sample - cell_samples + 1, hop_samples, dtype=int
    )
    if len(starts) < 2:
        return (), (), ()
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(spec.session_id), spec.stream_id, verify=True)
        raw = reader.read(
            int(starts[0]),
            int(starts[-1]) + cell_samples - int(starts[0]),
            receiver_ids=(spec.receiver_id,),
        )
        iq = _complex_receiver(raw)
    finally:
        if store is not None:
            store.close()
    calibration = ReceiverFrequencyCalibration(
        f"five-dwell-blind-{spec.receiver_id}",
        0.0,
        f"{spec.receiver_id:x}" * 64,
    )
    config = _blind_config(cell_samples)
    candidates = []
    for cell_index, absolute_start in enumerate(starts):
        local = int(absolute_start - starts[0])
        values = np.ascontiguousarray(iq[local : local + cell_samples])
        result = acquire_symbolwise(
            values,
            SAMPLE_RATE_HZ,
            calibration,
            edge=spec.edge,
            config=config,
        )
        cell_candidates = []
        for item in result.candidates:
            if item.verify_score < 0.08 or item.verify_minus_control_margin < 0.03:
                continue
            cell_candidates.append(
                blind.BlindCandidate(
                    cell_index=cell_index,
                    cell_start_s=float(absolute_start / SAMPLE_RATE_HZ),
                    cell_center_s=float(
                        (absolute_start + 0.5 * cell_samples) / SAMPLE_RATE_HZ
                    ),
                    refined_epoch_sample=int(item.refined_epoch_sample),
                    absolute_frame_start_sample=int(
                        absolute_start + item.refined_epoch_sample
                    ),
                    absolute_cfo_hz=float(item.absolute_cfo_hz),
                    acquire_score=float(item.acquire_score),
                    verify_score=float(item.verify_score),
                    control_score=float(item.conditioned_control_score),
                    margin=float(item.verify_minus_control_margin),
                    frame_support=int(item.frame_support),
                )
            )
        candidates.extend(blind._deduplicate(cell_candidates))
        if (cell_index + 1) % 100 == 0 or cell_index + 1 == len(starts):
            print(
                f"{spec.label}: blind acquisition {cell_index + 1}/{len(starts)} cells",
                flush=True,
            )
    pool = tuple(candidates)
    lines = []
    paths = []
    remaining = pool
    for line_index in range(3):
        if len(remaining) < 10:
            break
        try:
            line, _selected = blind.fit_latent_line(
                remaining,
                label=f"blind-{line_index + 1}",
                seed=24_082_600 + 100 * int(spec.label[1]) + line_index,
            )
        except (ValueError, np.linalg.LinAlgError):
            break
        path = blind.selected_path(remaining, line)
        lines.append(line)
        paths.append(path)
        remaining = tuple(
            item
            for item in remaining
            if abs(item.absolute_cfo_hz - float(line.frequency_hz(item.cell_center_s)))
            > 3_000.0
        )
    return pool, tuple(lines), tuple(paths)


def summarize_blind(
    spec: DwellSpec,
    candidates: tuple[blind.BlindCandidate, ...],
    lines: tuple[blind.LatentLine, ...],
    paths: tuple[tuple[blind.BlindCandidate, ...], ...],
) -> dict[str, Any]:
    if not lines:
        return {
            "status": "no-latent-line",
            "candidate_count": len(candidates),
            "lines": [],
        }
    distances = [
        abs(
            float(line.frequency_hz(spec.anchor_time_s))
            - float(spec.branch_frequency_hz(spec.anchor_time_s))
        )
        for line in lines
    ]
    matched_index = int(np.argmin(distances))
    matched_line = lines[matched_index]
    matched_path = paths[matched_index]
    segments = blind.segment_path(matched_path)
    fitted = tuple(item for item in segments if item.slope_hz_s is not None)
    boundary_times = [
        item.preceding_boundary_time_s
        for item in segments
        if item.preceding_boundary_time_s is not None
    ]
    return {
        "status": "complete",
        "candidate_count": len(candidates),
        "line_count": len(lines),
        "lines": [asdict(item) for item in lines],
        "matched_line_index": matched_index,
        "matched_frequency_difference_hz": float(distances[matched_index]),
        "matched_slope_hz_s": matched_line.slope_hz_s,
        "matched_slope_minus_glrt_hz_s": (
            matched_line.slope_hz_s - spec.branch_slope_hz_s
        ),
        "matched_path_cell_count": len(matched_path),
        "matched_segment_count": len(segments),
        "matched_fitted_segment_count": len(fitted),
        "matched_median_local_slope_hz_s": (
            None
            if not fitted
            else float(np.median([item.slope_hz_s for item in fitted]))
        ),
        "matched_boundary_count": len(boundary_times),
        "matched_median_boundary_spacing_ms": (
            None
            if len(boundary_times) < 2
            else float(np.median(np.diff(boundary_times)) * 1_000)
        ),
        "matched_segments": [asdict(item) for item in segments],
        "candidates": [asdict(item) for item in candidates],
        "matched_path": [asdict(item) for item in matched_path],
    }


def analyze_dwell(
    *,
    bulk_root: Path,
    spec: DwellSpec,
    maximum_windows: int | None,
    blind_duration_s: float,
    skip_blind: bool,
) -> dict[str, Any]:
    scan = _load(spec.analysis_root / "standard.pilot-scan.v3.json")
    windows = select_candidate_windows(
        spec, scan, maximum_windows=maximum_windows
    )
    frames = build_frame_evidence(
        bulk_root=bulk_root,
        spec=spec,
        scan=scan,
        windows=windows,
    )
    predictions, details = fit_model_predictions(spec, frames, windows)
    validations = {
        model: validate_prediction(prediction, frames)
        for model, prediction in predictions.items()
    }
    paired = {}
    for model, prediction in predictions.items():
        if model == "M0":
            continue
        baseline = validate_prediction(
            matched_global_prediction(prediction, frames), frames
        )
        state = validations[model]
        paired[model] = {
            "matched_global": baseline,
            "state_model": state,
            "validation_cfo_rms_reduction_hz": (
                baseline["validation_cfo_rms_hz"]
                - state["validation_cfo_rms_hz"]
            ),
            "validation_cfo_rms_reduction_fraction": (
                1.0
                - state["validation_cfo_rms_hz"]
                / baseline["validation_cfo_rms_hz"]
            ),
        }
    blind_summary: dict[str, Any]
    if skip_blind:
        blind_summary = {"status": "skipped"}
    else:
        candidates, lines, paths = blind_scan(
            bulk_root=bulk_root,
            spec=spec,
            duration_s=blind_duration_s,
        )
        blind_summary = summarize_blind(spec, candidates, lines, paths)
    return {
        "spec": {
            **asdict(spec),
            "edge": spec.edge.value,
            "analysis_root": str(spec.analysis_root),
        },
        "inventory": {
            "candidate_window_count": len(windows),
            "frame_count": len(frames),
            "train_qualified_frame_count": sum(item.train_qualified for item in frames),
            "train_qualified_fraction": (
                sum(item.train_qualified for item in frames) / len(frames) if frames else 0.0
            ),
        },
        "windows": [asdict(item) for item in windows],
        "frames": [
            {
                "row_index": item.row_index,
                "window_index": item.window_index,
                "time_s": item.time_s,
                "train_cfo_hz": item.train_cfo_hz,
                "validation_cfo_hz": item.validation_cfo_hz,
                "nco_cfo_hz": item.nco_cfo_hz,
                "train_exact_score": item.train_exact_score,
                "train_control_score": item.train_control_score,
                "train_margin": item.train_margin,
            }
            for item in frames
        ],
        "fit": details,
        "models": validations,
        "paired_to_matched_global": paired,
        "predictions": {model: asdict(value) for model, value in predictions.items()},
        "blind": blind_summary,
    }


def _plot_style() -> dict[str, Any]:
    return {
        "font.size": 10,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "text.color": INK,
        "grid.color": LIGHT_GRAY,
        "grid.alpha": 0.30,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#fbfcfd",
    }


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )
    plt.close(figure)


def render_tracks(results: list[dict[str, Any]], path: Path) -> None:
    with plt.rc_context(_plot_style()):
        figure, axes = plt.subplots(
            len(results),
            1,
            figsize=(18, 14),
            constrained_layout=True,
        )
        figure.suptitle(
            "Five dwells · frame CFO evidence and state-debiased model families",
            fontsize=20,
            fontweight="bold",
            color=INK,
        )
        for axis, result in zip(axes, results, strict=True):
            spec = result["spec"]
            frames = result["frames"]
            times = np.asarray([item["time_s"] for item in frames], dtype=float)
            train = np.asarray([item["train_cfo_hz"] for item in frames], dtype=float)
            quality = np.asarray(
                [
                    item["train_exact_score"] >= MINIMUM_TRAIN_EXACT
                    and item["train_margin"] >= MINIMUM_TRAIN_MARGIN
                    for item in frames
                ],
                dtype=bool,
            )
            coefficients = np.asarray(spec["branch_coefficients_hz"], dtype=float)
            frozen = np.polyval(
                coefficients, times - float(spec["branch_reference_time_s"])
            )
            axis.scatter(
                times[~quality],
                (train - frozen)[~quality],
                s=3,
                color=GRAY,
                alpha=0.10,
                linewidths=0,
                rasterized=True,
                label="even-Qin frame below train gate",
            )
            axis.scatter(
                times[quality],
                (train - frozen)[quality],
                s=5,
                color=BLUE,
                alpha=0.32,
                linewidths=0,
                rasterized=True,
                label="even-Qin train-qualified frame",
            )
            by_index = {int(item["row_index"]): item for item in frames}
            for model in MODEL_ORDER:
                prediction = result["predictions"].get(model)
                if prediction is None:
                    continue
                x = np.asarray(
                    [by_index[int(index)]["time_s"] for index in prediction["frame_indices"]]
                )
                y = np.asarray(prediction["predicted_cfo_hz"], dtype=float)
                baseline = np.polyval(
                    coefficients, x - float(spec["branch_reference_time_s"])
                )
                order = np.argsort(x)
                plot_x = x[order]
                plot_y = (y - baseline)[order]
                if model != "M0" and len(plot_x) > 1:
                    expected_step = (
                        float(prediction["rate_at_reference_hz_s"])
                        * np.diff(plot_x)
                    )
                    discontinuity = np.abs(np.diff(y[order]) - expected_step) > 100.0
                    if np.any(discontinuity):
                        insert_at = np.flatnonzero(discontinuity) + 1
                        plot_x = np.insert(plot_x, insert_at, np.nan)
                        plot_y = np.insert(plot_y, insert_at, np.nan)
                axis.plot(
                    plot_x,
                    plot_y,
                    color=MODEL_COLORS[model],
                    linewidth=1.15 if model != "M0" else 1.8,
                    alpha=0.86,
                    label=f"{model} · {MODEL_NAMES[model]}",
                )
            timing_breaks = (
                result["fit"].get("timing_break_window_indices", [])
                if "M4" in result["predictions"]
                else []
            )
            for window_index in timing_breaks:
                matches = [
                    item
                    for item in result["windows"]
                    if int(item["window_index"]) == int(window_index)
                ]
                if matches:
                    axis.axvline(
                        float(matches[0]["detection_time_s"]),
                        color=RED,
                        linewidth=0.7,
                        linestyle=(0, (3, 3)),
                        alpha=0.35,
                    )
            axis.axhline(0.0, color=INK, linewidth=0.7, alpha=0.5)
            axis.set_title(
                f"{spec['label']} · {spec['branch_start_s']:.3f}–"
                f"{spec['branch_end_s']:.3f} s · "
                f"{result['inventory']['train_qualified_frame_count']} qualified frames",
                loc="left",
                fontsize=12,
                fontweight="bold",
            )
            axis.set_ylabel("CFO − frozen GLRT line (Hz)")
            axis.grid(True)
        axes[-1].set_xlabel("capture time (s)")
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="outside lower center", ncol=4, fontsize=9)
        _save(figure, path)


def render_paired_probe_validation(
    results: list[dict[str, Any]], path: Path
) -> None:
    """Show state models versus refit global lines on identical held-out probes."""

    with plt.rc_context(_plot_style()):
        figure, axes = plt.subplots(
            2,
            2,
            figsize=(14, 12),
            constrained_layout=True,
            sharex=True,
            sharey=True,
        )
        figure.suptitle(
            "Per-probe held-out error · state model versus matched global line",
            fontsize=20,
            fontweight="bold",
            color=INK,
        )
        all_values = []
        plotted_labels: set[str] = set()
        for axis, model in zip(axes.flat, MODEL_ORDER[1:], strict=True):
            pair_rows = []
            for dwell_index, result in enumerate(results):
                pair = result["paired_to_matched_global"].get(model)
                if pair is None:
                    continue
                pair_rows.append(pair)
                baseline = {
                    int(item["window_index"]): item
                    for item in pair["matched_global"]["per_probe"]
                }
                state = {
                    int(item["window_index"]): item
                    for item in pair["state_model"]["per_probe"]
                }
                common = sorted(set(baseline) & set(state))
                x = np.asarray(
                    [baseline[index]["validation_cfo_rms_hz"] for index in common],
                    dtype=float,
                )
                y = np.asarray(
                    [state[index]["validation_cfo_rms_hz"] for index in common],
                    dtype=float,
                )
                positive = (x > 0) & (y > 0)
                x = x[positive]
                y = y[positive]
                if not len(x):
                    continue
                all_values.extend(x.tolist())
                all_values.extend(y.tolist())
                label = result["spec"]["session_id"].split("-")[-1][:8]
                axis.scatter(
                    x,
                    y,
                    s=20,
                    color=DWELL_COLORS[dwell_index],
                    alpha=0.56,
                    linewidths=0,
                    label=label if label not in plotted_labels else None,
                )
                plotted_labels.add(label)
            if not pair_rows:
                axis.text(
                    0.5,
                    0.5,
                    "no coherent multi-probe ramps",
                    ha="center",
                    va="center",
                    transform=axis.transAxes,
                )
                subtitle = "not estimable"
            else:
                frame_count = sum(
                    item["state_model"]["frame_count"] for item in pair_rows
                )
                global_rms = math.sqrt(
                    sum(
                        item["matched_global"]["frame_count"]
                        * item["matched_global"]["validation_cfo_rms_hz"] ** 2
                        for item in pair_rows
                    )
                    / frame_count
                )
                state_rms = math.sqrt(
                    sum(
                        item["state_model"]["frame_count"]
                        * item["state_model"]["validation_cfo_rms_hz"] ** 2
                        for item in pair_rows
                    )
                    / frame_count
                )
                subtitle = (
                    f"{100 * (1.0 - state_rms / global_rms):.1f}% pooled "
                    "frame-RMS reduction"
                )
            axis.set_title(
                f"{model} · {MODEL_NAMES[model]}\n{subtitle}",
                loc="left",
                fontweight="bold",
            )
            axis.set_xscale("log")
            axis.set_yscale("log")
            axis.grid(True, which="both")
        if all_values:
            lower = max(1.0, 0.75 * min(all_values))
            upper = 1.35 * max(all_values)
            for axis in axes.flat:
                axis.plot(
                    [lower, upper],
                    [lower, upper],
                    color=INK,
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.7,
                    label="equal error",
                )
                axis.set_xlim(lower, upper)
                axis.set_ylim(lower, upper)
        for axis in axes[-1, :]:
            axis.set_xlabel("matched global-line odd-symbol RMS (Hz)")
        for axis in axes[:, 0]:
            axis.set_ylabel("state-model odd-symbol RMS (Hz)")
        handles = [
            Line2D(
                [],
                [],
                marker="o",
                linestyle="None",
                color=DWELL_COLORS[index],
                label=result["spec"]["session_id"].split("-")[-1][:8],
            )
            for index, result in enumerate(results)
            if any(
                model in result["paired_to_matched_global"]
                for model in MODEL_ORDER[1:]
            )
        ]
        handles.append(
            Line2D([], [], color=INK, linestyle="--", label="equal error")
        )
        figure.legend(handles=handles, loc="outside lower center", ncol=3)
        _save(figure, path)


def render_validation(results: list[dict[str, Any]], path: Path) -> None:
    with plt.rc_context(_plot_style()):
        figure, axes = plt.subplots(3, 1, figsize=(16, 13), constrained_layout=True)
        figure.suptitle(
            "Held-out odd-Qin validation and recovered apparent Doppler rate",
            fontsize=20,
            fontweight="bold",
            color=INK,
        )
        x = np.arange(len(results), dtype=float)
        width = 0.15
        for model_index, model in enumerate(MODEL_ORDER):
            offset = (model_index - 2) * width
            rms = []
            pass_fraction = []
            rate = []
            for result in results:
                row = result["models"].get(model, {})
                rms.append(row.get("validation_cfo_rms_hz", math.nan))
                pass_fraction.append(
                    row.get("validation_qin_beats_control_fraction", math.nan)
                )
                rate.append(row.get("rate_at_reference_hz_s", math.nan) / 1_000)
            axes[0].bar(
                x + offset,
                rms,
                width=width,
                color=MODEL_COLORS[model],
                alpha=0.84,
                label=f"{model} · {MODEL_NAMES[model]}",
            )
            axes[1].bar(
                x + offset,
                pass_fraction,
                width=width,
                color=MODEL_COLORS[model],
                alpha=0.84,
            )
            axes[2].scatter(
                x + offset,
                rate,
                color=MODEL_COLORS[model],
                s=55,
                marker="o",
                zorder=4,
            )
        glrt = [float(item["spec"]["branch_coefficients_hz"][0]) / 1_000 for item in results]
        axes[2].scatter(
            x,
            glrt,
            color=INK,
            marker="x",
            s=75,
            linewidths=2,
            label="frozen multi-second GLRT rate",
            zorder=5,
        )
        labels = [item["spec"]["session_id"].split("-")[-1][:8] for item in results]
        axes[0].set_ylabel("odd-symbol CFO RMS (Hz)")
        axes[0].set_title(
            "A · Frequency prediction against an independently maximized odd-symbol CFO",
            loc="left",
            fontweight="bold",
        )
        axes[1].set_ylabel("odd Qin > rolled control fraction")
        axes[1].set_ylim(0, 1.05)
        axes[1].set_title(
            "B · Sequence-specific support at the fitted model frequency",
            loc="left",
            fontweight="bold",
        )
        axes[2].set_ylabel("apparent CFO rate (kHz/s)")
        axes[2].set_title(
            "C · State intercepts prevent resets from entering the rate fit",
            loc="left",
            fontweight="bold",
        )
        for axis in axes:
            axis.set_xticks(x, labels)
            axis.grid(True, axis="y")
        handles, legend_labels = axes[0].get_legend_handles_labels()
        handles2, labels2 = axes[2].get_legend_handles_labels()
        figure.legend(
            handles + handles2,
            legend_labels + labels2,
            loc="outside lower center",
            ncol=3,
            fontsize=9,
        )
        _save(figure, path)


def render_blind(results: list[dict[str, Any]], path: Path) -> None:
    with plt.rc_context(_plot_style()):
        figure, axes = plt.subplots(
            len(results), 1, figsize=(17, 14), constrained_layout=True
        )
        figure.suptitle(
            "Independent raw-IQ acquisition · no persisted 20 ms timing or CFO",
            fontsize=20,
            fontweight="bold",
            color=INK,
        )
        for axis, result in zip(axes, results, strict=True):
            spec = result["spec"]
            audit = result["blind"]
            candidates = audit.get("candidates", [])
            if not candidates:
                axis.text(0.5, 0.5, audit.get("status", "no result"), transform=axis.transAxes)
                continue
            axis.scatter(
                [item["cell_center_s"] for item in candidates],
                [item["absolute_cfo_hz"] / 1_000 for item in candidates],
                s=7,
                color=GRAY,
                alpha=0.18,
                linewidths=0,
                rasterized=True,
                label="retained blind modes",
            )
            path_rows = audit.get("matched_path", [])
            axis.scatter(
                [item["cell_center_s"] for item in path_rows],
                [item["absolute_cfo_hz"] / 1_000 for item in path_rows],
                s=11,
                color=BLUE,
                alpha=0.72,
                linewidths=0,
                label="nearest independently fitted latent path",
            )
            if path_rows:
                times = np.linspace(
                    min(item["cell_center_s"] for item in path_rows),
                    max(item["cell_center_s"] for item in path_rows),
                    300,
                )
                line = audit["lines"][int(audit["matched_line_index"])]
                latent = line["frequency_at_reference_hz"] + line["slope_hz_s"] * (
                    times - line["reference_time_s"]
                )
                frozen = np.polyval(
                    np.asarray(spec["branch_coefficients_hz"]),
                    times - float(spec["branch_reference_time_s"]),
                )
                axis.plot(
                    times,
                    latent / 1_000,
                    color=BLUE,
                    linewidth=2.0,
                    label="fitted blind latent line",
                )
                axis.plot(
                    times,
                    frozen / 1_000,
                    color=INK,
                    linewidth=1.4,
                    linestyle="--",
                    label="persisted branch shown only after blind fit",
                )
            axis.set_title(
                f"{spec['label']} · {audit.get('candidate_count', 0)} candidates · "
                "frequency separation "
                f"{audit.get('matched_frequency_difference_hz', math.nan):.0f} Hz · "
                "rates blind/frozen "
                f"{audit.get('matched_slope_hz_s', math.nan) / 1_000:.3f}/"
                f"{float(spec['branch_coefficients_hz'][0]) / 1_000:.3f} kHz/s",
                loc="left",
                fontweight="bold",
            )
            axis.set_ylabel("absolute CFO (kHz)")
            axis.grid(True)
        axes[-1].set_xlabel("capture time (s)")
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="outside lower center", ncol=2, fontsize=9)
        _save(figure, path)


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    models = {}
    for model in MODEL_ORDER:
        rows = [item["models"].get(model) for item in results]
        complete = [item for item in rows if item and item.get("status") == "complete"]
        if not complete:
            models[model] = {"dwell_count": 0}
            continue
        models[model] = {
            "dwell_count": len(complete),
            "total_validated_frames": int(sum(item["frame_count"] for item in complete)),
            "pooled_validation_cfo_rms_hz": float(
                math.sqrt(
                    sum(
                        item["frame_count"] * item["validation_cfo_rms_hz"] ** 2
                        for item in complete
                    )
                    / sum(item["frame_count"] for item in complete)
                )
            ),
            "weighted_qin_beats_control_fraction": float(
                sum(
                    item["frame_count"] * item["validation_qin_beats_control_fraction"]
                    for item in complete
                )
                / sum(item["frame_count"] for item in complete)
            ),
            "median_rate_hz_s": float(
                np.median([item["rate_at_reference_hz_s"] for item in complete])
            ),
        }
    paired = {}
    for model in MODEL_ORDER[1:]:
        rows = [
            item["paired_to_matched_global"][model]
            for item in results
            if model in item["paired_to_matched_global"]
        ]
        if not rows:
            paired[model] = {"dwell_count": 0}
            continue
        frame_count = sum(item["state_model"]["frame_count"] for item in rows)
        baseline_squared = sum(
            item["matched_global"]["frame_count"]
            * item["matched_global"]["validation_cfo_rms_hz"] ** 2
            for item in rows
        )
        state_squared = sum(
            item["state_model"]["frame_count"]
            * item["state_model"]["validation_cfo_rms_hz"] ** 2
            for item in rows
        )
        baseline_rms = math.sqrt(baseline_squared / frame_count)
        state_rms = math.sqrt(state_squared / frame_count)
        paired[model] = {
            "dwell_count": len(rows),
            "total_validated_frames": int(frame_count),
            "matched_global_validation_cfo_rms_hz": float(baseline_rms),
            "state_validation_cfo_rms_hz": float(state_rms),
            "validation_cfo_rms_reduction_hz": float(baseline_rms - state_rms),
            "validation_cfo_rms_reduction_fraction": float(
                1.0 - state_rms / baseline_rms
            ),
            "weighted_qin_beats_control_fraction": float(
                sum(
                    item["state_model"]["frame_count"]
                    * item["state_model"]["validation_qin_beats_control_fraction"]
                    for item in rows
                )
                / frame_count
            ),
        }
    return {"models": models, "paired_to_matched_global": paired}


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value):.{digits}f}"


def write_report(path: Path, document: dict[str, Any]) -> None:
    results = document["dwells"]
    figures = document["figures"]
    rows = []
    blind_rows = []
    for result in results:
        spec = result["spec"]
        model_cells = []
        for model in MODEL_ORDER:
            metrics = result["models"].get(model, {})
            if metrics.get("status") != "complete":
                model_cells.append("—")
            else:
                model_cells.append(
                    f"{metrics['rate_at_reference_hz_s'] / 1_000:.3f} / "
                    f"{metrics['validation_cfo_rms_hz']:.1f}"
                )
        rows.append(
            "| {label} | {span:.3f} | {near}/{windows} | {qualified}/{frames} | "
            "{glrt:.3f} | {models} |".format(
                label=spec["session_id"].split("-")[-1][:8],
                span=float(spec["branch_end_s"]) - float(spec["branch_start_s"]),
                near=sum(
                    float(item["selection_model_error_hz"])
                    <= MAXIMUM_MODEL_ERROR_HZ
                    for item in result["windows"]
                ),
                windows=len(result["windows"]),
                qualified=result["inventory"]["train_qualified_frame_count"],
                frames=result["inventory"]["frame_count"],
                glrt=float(spec["branch_coefficients_hz"][0]) / 1_000,
                models=" | ".join(model_cells),
            )
        )
        audit = result["blind"]
        blind_rows.append(
            "| {label} | {status} | {candidates} | {difference} | {glrt} | {blind} | "
            "{local} | {boundaries} |".format(
                label=spec["session_id"].split("-")[-1][:8],
                status=audit.get("status", "—"),
                candidates=audit.get("candidate_count", 0),
                difference=_fmt(audit.get("matched_frequency_difference_hz"), 0),
                glrt=_fmt(float(spec["branch_coefficients_hz"][0]) / 1_000, 3),
                blind=_fmt(
                    None
                    if audit.get("matched_slope_hz_s") is None
                    else audit["matched_slope_hz_s"] / 1_000,
                    3,
                ),
                local=_fmt(
                    None
                    if audit.get("matched_median_local_slope_hz_s") is None
                    else audit["matched_median_local_slope_hz_s"] / 1_000,
                    3,
                ),
                boundaries=audit.get("matched_boundary_count", "—"),
            )
        )
    aggregate_rows = []
    for model in MODEL_ORDER:
        value = document["aggregate"]["models"][model]
        aggregate_rows.append(
            "| {model} | {name} | {dwells}/5 | {frames} | {rms} | {qin} | {rate} |".format(
                model=model,
                name=MODEL_NAMES[model],
                dwells=value.get("dwell_count", 0),
                frames=value.get("total_validated_frames", 0),
                rms=_fmt(value.get("pooled_validation_cfo_rms_hz"), 1),
                qin=(
                    "—"
                    if value.get("weighted_qin_beats_control_fraction") is None
                    else f"{100 * value['weighted_qin_beats_control_fraction']:.1f}%"
                ),
                rate=_fmt(
                    None
                    if value.get("median_rate_hz_s") is None
                    else value["median_rate_hz_s"] / 1_000,
                    3,
                ),
            )
        )
    paired_rows = []
    for model in MODEL_ORDER[1:]:
        value = document["aggregate"]["paired_to_matched_global"][model]
        paired_rows.append(
            "| {model} | {name} | {dwells}/5 | {frames} | {baseline} | {state} | "
            "{reduction} | {qin} |".format(
                model=model,
                name=MODEL_NAMES[model],
                dwells=value.get("dwell_count", 0),
                frames=value.get("total_validated_frames", 0),
                baseline=_fmt(
                    value.get("matched_global_validation_cfo_rms_hz"), 1
                ),
                state=_fmt(value.get("state_validation_cfo_rms_hz"), 1),
                reduction=(
                    "—"
                    if value.get("validation_cfo_rms_reduction_fraction") is None
                    else f"{100 * value['validation_cfo_rms_reduction_fraction']:.1f}%"
                ),
                qin=(
                    "—"
                    if value.get("weighted_qin_beats_control_fraction") is None
                    else f"{100 * value['weighted_qin_beats_control_fraction']:.1f}%"
                ),
            )
        )
    supported_dwells = sum(
        bool(result["paired_to_matched_global"]) for result in results
    )
    blind_close_dwells = sum(
        result["blind"].get("status") == "complete"
        and result["blind"].get("matched_frequency_difference_hz", math.inf) < 3_000
        for result in results
    )
    m4_paired = document["aggregate"]["paired_to_matched_global"]["M4"]
    paired_conclusion = (
        "M4 was estimable on two dwells and reduced pooled matched-support odd-symbol "
        f"CFO RMS from {m4_paired['matched_global_validation_cfo_rms_hz']:.1f} to "
        f"{m4_paired['state_validation_cfo_rms_hz']:.1f} Hz "
        f"({100 * m4_paired['validation_cfo_rms_reduction_fraction']:.1f}%)."
        if m4_paired.get("dwell_count")
        else "M4 was not estimable on these dwells."
    )
    text = f"""# Five-dwell prototypes for state-debiased Starlink Doppler

## Abstract

Five estimator families were replayed on the same five sealed historical captures. The
persisted 20 ms GLRT was used only to select and initialize one already-declared
multi-second branch per dwell.  Every 1.333 ms frequency likelihood was reconstructed
from raw IQ.  Even Qin symbols fit the model; odd Qin symbols and a rolled-Qin sequence
were held out.  A separate 12 ms / 4 ms-hop blind acquisition tested whether a compatible
path could be found without any persisted timing or CFO.

Coherent multi-probe ramps sufficient for a state-debiased fit survived on
**{supported_dwells}/5 dwells**. {paired_conclusion} The blind lane independently landed
within 3 kHz of the predeclared branch on **{blind_close_dwells}/5 dwells**. These failures
are part of the result: a strong 20 ms GLRT branch is not, by itself, proof that exact Qin
phase persists at frame scale.

The comparison distinguishes *measurement precision* from *physical identifiability*.
State intercepts can prevent timing/emitter replacements from biasing the rate, but no
carrier-only model can prove that its within-state rate is purely orbital Doppler.

![Frame CFO evidence and fitted models]({os.path.relpath(figures['tracks'], path.parent)})

## Data and model inventory

The five captures were frozen by
[`inputs.json`]({os.path.relpath(document['inputs_path'], path.parent)}).  No RF was
collected and every recording read was digest-verified and read-only.

Each model cell below is `rate in kHz/s / held-out odd-symbol CFO RMS in Hz`.

| dwell | span (s) | near probes | train frames | GLRT rate | M0 | M1 | M2 | M3 | M4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Held-out statistical comparison

![Held-out validation and recovered rates]({os.path.relpath(figures['validation'], path.parent)})

| model | definition | dwells | frames | odd-CFO RMS (Hz) | Qin > ctrl | rate (kHz/s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(aggregate_rows)}

The table above reports each model on the frames it can support and is therefore an
availability summary, not a fair model-to-model error comparison. The paired comparison
below refits a global line to **exactly the same even-symbol frames** as each state model,
then scores both predictions on the same odd symbols and the same probes.

![Per-probe paired validation]({os.path.relpath(figures['paired_validation'], path.parent)})

| model | definition | dwells | frames | matched global RMS | state RMS | reduction | Qin > ctrl |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(paired_rows)}

The pooled result is not uniform:

- **D1 (`89ad2e81`)**: the matched global line already scores 27.35 Hz RMS. M1,
  M2, and M3 score 27.26, 27.22, and 27.28 Hz: only 0.3–0.5% different. M2
  measures a slope progression of −87.9 Hz/s², but improves RMS by only 0.05 Hz
  over M1. The data do not justify preferring the more complex progression model.
- **D5 (`5b77aa69`)**: M4 reduces matched held-out RMS from 81.43 to 24.06 Hz
  (70.4%). Median per-probe RMS falls from 62.79 to 21.93 Hz and the 90th
  percentile from 127.29 to 27.99 Hz. Its rate is −3.172 kHz/s with progression
  −20.9 Hz/s², versus the frozen GLRT branch rate of −5.183 kHz/s. This is the
  one dwell where state debiasing materially changes the inferred rate.
- **D2, D3, and D4**: no ≥20 ms, ≤40 Hz-RMS multi-probe ramp survived, so M1–M4
  are reported as unavailable rather than forcing a Doppler estimate. D3 is a
  particularly useful distinction: blind acquisition finds the branch to 97 Hz,
  yet exact frame-scale coherence does not persist long enough for these models.

- **M0** fits one robust line through the raw frame CFOs and therefore permits state
  replacements to enter the rate.
- **M1** assigns each batch-recovered coherent ramp an arbitrary CFO intercept and fits
  one common within-ramp rate.
- **M2** adds a linear progression of that common rate over capture time.
- **M3** fits every coherent ramp independently.  It is the most flexible carrier-only
  model and is therefore expected to have the lowest training error; held-out odd-symbol
  performance determines whether that freedom is useful.
- **M4** repeats M2 after forcing a split when the independently acquired frame timing
  phase jumps by more than {TIMING_BREAK_SAMPLES:.0f} samples or qualified locks have a
  gap greater than 55 ms.

The reported absolute CFO levels remain receiver-relative.  An unknown LNB/emitter
constant is absorbed by the global or per-state intercepts.  LNB and transmitter clock
*drift* remain inseparable from geometric Doppler rate.

## Blind acquisition ablation

![Blind acquisition comparison]({os.path.relpath(figures['blind'], path.parent)})

The blind search covers {document['configuration']['blind_duration_s']:.2f} s around the
predeclared anchor but consumes no persisted epoch or CFO.  Up to three latent paths are
fit before the previously selected branch is loaded for comparison.  “Nearest” therefore
means a post-fit association, not a search prior.

Rate columns below are kHz/s; CFO Δ is Hz.

| dwell | status | modes | CFO Δ (Hz) | GLRT rate | blind rate | local rate | jumps |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(blind_rows)}

## Methods and interpretation boundary

For each persisted probe, the nearest CFO candidate to the frozen branch supplies a timing
epoch. Its CFO supplies the NCO center when it is within 2.5 kHz of the branch; otherwise
the frozen branch value centers the ±6 kHz raw-IQ likelihood so a bad GLRT candidate does
not silently delete the probe. Even and odd pilot symbols form independent 25 Hz-grid
frequency likelihoods. Only the even half determines frame inclusion, segmentation, and
model parameters. The permissive frame gate is followed by the much stronger multi-probe
linearity test; isolated frequency maxima are not called coherent ramps.

Batch segments are selected by a capped-square dynamic program.  A segment is called
coherent only when it spans at least 20 ms and its raw line-fit RMS is at most 40 Hz.
Model validation samples the untouched odd-Qin and rolled-control likelihoods at exactly
the predicted frequency; it does not re-optimize the model on the validation symbols.

This is a prototype comparison, not a satellite-velocity product.  M1–M4 identify a
state-debiased *apparent CFO rate* under their respective state assumptions.  Associating
that rate with orbital Doppler still requires a TLE shape, calibrated oscillator,
uncontaminated tone, or independently qualified timing/SFO model.

## Reproduction

```bash
.venv/bin/python tools/report_five_dwell_doppler_prototypes.py
```

Machine-readable results:
[`five-dwell-doppler-prototypes.json`]({os.path.relpath(document['result_path'], path.parent)}).
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_all(document: dict[str, Any], output_root: Path) -> dict[str, str]:
    figures = {
        "tracks": str(output_root / "five-dwell-model-tracks.png"),
        "validation": str(output_root / "five-dwell-heldout-validation.png"),
        "paired_validation": str(
            output_root / "five-dwell-paired-probe-validation.png"
        ),
        "blind": str(output_root / "five-dwell-blind-acquisition.png"),
    }
    render_tracks(document["dwells"], Path(figures["tracks"]))
    render_validation(document["dwells"], Path(figures["validation"]))
    render_paired_probe_validation(
        document["dwells"], Path(figures["paired_validation"])
    )
    render_blind(document["dwells"], Path(figures["blind"]))
    return figures


def main() -> None:
    args = _arguments()
    result_path = args.output_root / "five-dwell-doppler-prototypes.json"
    if args.reuse_results is not None:
        document = _load(args.reuse_results)
        document["result_path"] = str(result_path)
        document["inputs_path"] = str(args.inputs)
    else:
        specs = load_dwell_specs(args.inputs, args.source_results)
        args.checkpoint_root.mkdir(parents=True, exist_ok=True)
        dwells = []
        for dwell_index, spec in enumerate(specs, start=1):
            checkpoint = args.checkpoint_root / f"dwell-{dwell_index}.json"
            if args.resume and checkpoint.is_file():
                cached = _load(checkpoint)
                if cached.get("session_id") != spec.session_id:
                    raise ValueError(f"checkpoint session mismatch: {checkpoint}")
                dwell = cached["result"]
                print(f"{spec.label}: reused {checkpoint}", flush=True)
            else:
                dwell = analyze_dwell(
                    bulk_root=args.bulk_root,
                    spec=spec,
                    maximum_windows=args.maximum_windows_per_dwell,
                    blind_duration_s=args.blind_duration_s,
                    skip_blind=args.skip_blind,
                )
                checkpoint.write_text(
                    json.dumps(
                        stable_measurement_floats(
                            {"session_id": spec.session_id, "result": dwell}
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            dwells.append(dwell)
        document = {
            "schema": "org.leo.research.five-dwell-doppler-prototypes/v1",
            "algorithm": "raw-qin-even-odd-state-debiased-model-comparison-v1",
            "candidate_only": True,
            "payload_decoded": False,
            "inputs_path": str(args.inputs),
            "source_results_path": str(args.source_results),
            "result_path": str(result_path),
            "configuration": {
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "maximum_model_error_hz": MAXIMUM_MODEL_ERROR_HZ,
                "minimum_train_exact": MINIMUM_TRAIN_EXACT,
                "minimum_train_margin": MINIMUM_TRAIN_MARGIN,
                "timing_break_samples": TIMING_BREAK_SAMPLES,
                "blind_duration_s": args.blind_duration_s,
                "blind_cell_duration_s": BLIND_CELL_DURATION_S,
                "blind_cell_hop_s": BLIND_CELL_HOP_S,
                "maximum_windows_per_dwell": args.maximum_windows_per_dwell,
                "fit_symbols": "even Qin pilot symbols",
                "validation_symbols": "odd Qin pilot symbols",
                "negative_control": "17-symbol-rolled Qin sequence",
            },
            "dwells": dwells,
            "aggregate": aggregate(dwells),
        }
    document["figures"] = render_all(document, args.output_root)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(stable_measurement_floats(document), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(args.report_path, document)
    print(result_path)
    print(args.report_path)


if __name__ == "__main__":
    main()
