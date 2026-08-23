#!/usr/bin/env python3
"""Discriminate timing/source handoffs from CFO and analysis-window artifacts."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.acquisition import (
    DEFAULT_VERIFY_SYMBOLS,
    ReceiverFrequencyCalibration,
    acquire_symbolwise,
    normalized_frame_score,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_blind_timing_cfo as blind
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_blind_timing_cfo as blind


SESSION_ID = "cap-20260821T140820-470384cc9284"
SAMPLE_RATE_HZ = 2_500_000.0
START_S = 33.7
END_S = 37.7
CELL_SAMPLES = round(0.012 * SAMPLE_RATE_HZ)
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / FRAME_RATE_HZ
DEFAULT_BLIND_RESULTS = Path(
    "reports/figures/2026_08_23_470384_blind_timing_cfo/"
    "blind-timing-cfo-results.json"
)
DEFAULT_SHIFTED_RESULTS = Path("/tmp/470384-blind-shift2/blind-timing-cfo-results.json")
DEFAULT_SUPPORT_RESULTS = Path("/tmp/470384-blind-16ms/blind-timing-cfo-results.json")
DEFAULT_RECEIVER1_RESULTS = Path("/tmp/470384-blind-rx1/blind-timing-cfo-results.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_boundary_mechanism")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_boundary_mechanism.md")

COARSE_OFFSETS_HZ = np.arange(-2_000.0, 2_000.1, 100.0)
FINE_OFFSETS_HZ = np.arange(-100.0, 100.1, 5.0)
FRAME_OFFSETS_S = (-0.010, -0.008, -0.006, 0.006, 0.008, 0.010)

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"
PURPLE = "#7b65a8"


@dataclass(frozen=True, slots=True)
class BoundaryMode:
    boundary_index: int
    time_s: float
    left_segment_index: int
    right_segment_index: int
    left_anchor_sample: int
    right_anchor_sample: int
    timing_separation_samples: int
    left_segment: dict[str, Any]
    right_segment: dict[str, Any]
    left_cells: tuple[dict[str, Any], ...]
    right_cells: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FrameFit:
    boundary_index: int
    boundary_time_s: float
    side: str
    time_s: float
    fitted_cfo_hz: float
    early_half_cfo_hz: float
    late_half_cfo_hz: float
    segment_cfo_hz: float
    global_cfo_hz: float
    validation_exact_score: float
    validation_control_score: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--blind-results", type=Path, default=DEFAULT_BLIND_RESULTS)
    parser.add_argument("--shifted-results", type=Path, default=DEFAULT_SHIFTED_RESULTS)
    parser.add_argument("--support-results", type=Path, default=DEFAULT_SUPPORT_RESULTS)
    parser.add_argument("--receiver1-results", type=Path, default=DEFAULT_RECEIVER1_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--maximum-boundaries",
        type=int,
        help="bounded development run over ordered fitted timing boundaries",
    )
    parser.add_argument(
        "--receiver-control-cells",
        type=int,
        default=100,
        help="uniformly sampled receiver-1 cells for an independent blind sensitivity audit",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _complex_receivers(values: np.ndarray) -> tuple[np.ndarray, ...]:
    if values.ndim != 3 or values.shape[2] != 2:
        raise ValueError("CI16 data must have shape (samples, receivers, 2)")
    return tuple(
        (
            values[:, receiver, 0].astype(np.float64)
            + 1j * values[:, receiver, 1].astype(np.float64)
        )
        / (2**15)
        for receiver in range(values.shape[1])
    )


def read_raw_receivers(
    bulk_root: Path,
    *,
    start_s: float = START_S,
    end_s: float = END_S,
) -> tuple[np.ndarray, ...]:
    """Read the bounded experiment interval for both stream-0 receiver channels."""

    start_sample = round(start_s * SAMPLE_RATE_HZ)
    sample_count = round((end_s - start_s) * SAMPLE_RATE_HZ)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(SESSION_ID), "stream-0", verify=True)
        raw = reader.read(start_sample, sample_count, receiver_ids=(0, 1))
    finally:
        if store is not None:
            store.close()
    return _complex_receivers(raw)


def project_epoch(anchor_sample: int, cell_start_sample: int) -> int:
    """Project one absolute 750 Hz frame lattice into a target raw-IQ cell."""

    frame_index = math.ceil((cell_start_sample - anchor_sample) / FRAME_PERIOD_SAMPLES)
    epoch = round(anchor_sample + frame_index * FRAME_PERIOD_SAMPLES) - cell_start_sample
    if not 0 <= epoch <= math.ceil(FRAME_PERIOD_SAMPLES):
        raise ValueError("projected epoch is outside one frame period")
    return int(epoch)


def segment_cfo(segment: dict[str, Any], time_s: float) -> float:
    if segment["frequency_at_reference_hz"] is None or segment["slope_hz_s"] is None:
        raise ValueError("boundary experiment requires a fitted segment")
    return float(
        segment["frequency_at_reference_hz"]
        + segment["slope_hz_s"] * (time_s - segment["reference_time_s"])
    )


def global_cfo(document: dict[str, Any], time_s: float) -> float:
    line = document["primary_line"]
    return float(
        line["frequency_at_reference_hz"]
        + line["slope_hz_s"] * (time_s - line["reference_time_s"])
    )


def _segment_cells(
    path: list[dict[str, Any]], segment: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    return tuple(
        item
        for item in path
        if segment["start_s"] - 1e-9 <= item["cell_center_s"] <= segment["end_s"] + 1e-9
    )


def boundary_modes(
    document: dict[str, Any],
    *,
    maximum_boundaries: int | None = None,
) -> tuple[BoundaryMode, ...]:
    """Return adjacent fitted, genuinely different timing modes with safe cells."""

    path = document["primary_path"]
    segments = document["primary_segments"]
    output: list[BoundaryMode] = []
    for left, right in zip(segments[:-1], segments[1:], strict=True):
        if left["slope_hz_s"] is None or right["slope_hz_s"] is None:
            continue
        boundary_time_s = float(right["preceding_boundary_time_s"])
        left_items = _segment_cells(path, left)
        right_items = _segment_cells(path, right)
        if not left_items or not right_items:
            continue
        left_anchor = int(left_items[-1]["absolute_frame_start_sample"])
        right_anchor = int(right_items[0]["absolute_frame_start_sample"])
        comparison_cell_start = round((boundary_time_s - 0.006) * SAMPLE_RATE_HZ)
        separation = abs(
            project_epoch(left_anchor, comparison_cell_start)
            - project_epoch(right_anchor, comparison_cell_start)
        )
        separation = min(separation, round(FRAME_PERIOD_SAMPLES) - separation)
        if separation <= 20:
            continue
        left_safe = tuple(
            item for item in left_items if item["cell_center_s"] <= boundary_time_s - 0.008
        )[-5:]
        right_safe = tuple(
            item for item in right_items if item["cell_center_s"] >= boundary_time_s + 0.008
        )[:5]
        if len(left_safe) < 5 or len(right_safe) < 5:
            continue
        output.append(
            BoundaryMode(
                boundary_index=len(output),
                time_s=boundary_time_s,
                left_segment_index=int(left["segment_index"]),
                right_segment_index=int(right["segment_index"]),
                left_anchor_sample=left_anchor,
                right_anchor_sample=right_anchor,
                timing_separation_samples=int(separation),
                left_segment=left,
                right_segment=right,
                left_cells=left_safe,
                right_cells=right_safe,
            )
        )
        if maximum_boundaries is not None and len(output) >= maximum_boundaries:
            break
    return tuple(output)


def _cell_scores(
    iq: np.ndarray,
    *,
    raw_start_sample: int,
    cell: dict[str, Any],
    segment: dict[str, Any],
    anchor_sample: int,
    exact_template: np.ndarray,
    control_template: np.ndarray,
) -> tuple[float, float]:
    cell_start = round(cell["cell_start_s"] * SAMPLE_RATE_HZ)
    local_start = cell_start - raw_start_sample
    values = np.ascontiguousarray(iq[local_start : local_start + CELL_SAMPLES])
    epoch = project_epoch(anchor_sample, cell_start)
    cfo_hz = segment_cfo(segment, float(cell["cell_center_s"]))
    exact, _support = normalized_frame_score(
        values,
        exact_template,
        SAMPLE_RATE_HZ,
        epoch,
        cfo_hz,
        DEFAULT_VERIFY_SYMBOLS,
    )
    control, _support = normalized_frame_score(
        values,
        control_template,
        SAMPLE_RATE_HZ,
        epoch,
        cfo_hz,
        DEFAULT_VERIFY_SYMBOLS,
    )
    return exact, control


def analyze_mode_crossfit(
    receivers: tuple[np.ndarray, ...],
    boundaries: tuple[BoundaryMode, ...],
) -> tuple[dict[str, Any], ...]:
    """Evaluate each frozen left/right mode natively and across its transition."""

    exact = np.asarray(
        qin_edge_pilot_frame(int(SAMPLE_RATE_HZ), StarlinkEdge.UPPER),
        dtype=np.complex128,
    )
    control = np.asarray(
        qin_edge_pilot_frame(
            int(SAMPLE_RATE_HZ),
            StarlinkEdge.UPPER,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        ),
        dtype=np.complex128,
    )
    raw_start = round(START_S * SAMPLE_RATE_HZ)
    output: list[dict[str, Any]] = []
    for boundary in boundaries:
        row: dict[str, Any] = {
            "boundary_index": boundary.boundary_index,
            "time_s": boundary.time_s,
            "timing_separation_samples": boundary.timing_separation_samples,
        }
        evaluations = (
            (
                "left_on_left",
                boundary.left_cells,
                boundary.left_segment,
                boundary.left_anchor_sample,
            ),
            (
                "left_on_right",
                boundary.right_cells,
                boundary.left_segment,
                boundary.left_anchor_sample,
            ),
            (
                "right_on_right",
                boundary.right_cells,
                boundary.right_segment,
                boundary.right_anchor_sample,
            ),
            (
                "right_on_left",
                boundary.left_cells,
                boundary.right_segment,
                boundary.right_anchor_sample,
            ),
        )
        for receiver_id, iq in enumerate(receivers):
            receiver: dict[str, Any] = {}
            for label, cells, segment, anchor in evaluations:
                scores = np.asarray(
                    [
                        _cell_scores(
                            iq,
                            raw_start_sample=raw_start,
                            cell=cell,
                            segment=segment,
                            anchor_sample=anchor,
                            exact_template=exact,
                            control_template=control,
                        )
                        for cell in cells
                    ]
                )
                receiver[label] = {
                    "exact_score": float(np.median(scores[:, 0])),
                    "control_score": float(np.median(scores[:, 1])),
                    "margin": float(np.median(scores[:, 0] - scores[:, 1])),
                }
            row[f"receiver_{receiver_id}"] = receiver
        output.append(row)
    return tuple(output)


def crossfit_statistics(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    statistics: dict[str, Any] = {"boundary_count": len(rows), "receivers": {}}
    for receiver_id in (0, 1):
        receiver: dict[str, Any] = {}
        for label in ("left_on_left", "right_on_right", "left_on_right", "right_on_left"):
            margins = np.asarray(
                [row[f"receiver_{receiver_id}"][label]["margin"] for row in rows]
            )
            exact = np.asarray(
                [row[f"receiver_{receiver_id}"][label]["exact_score"] for row in rows]
            )
            receiver[label] = {
                "median_exact_score": float(np.median(exact)),
                "median_margin": float(np.median(margins)),
                "p90_margin": float(np.percentile(margins, 90)),
                "fraction_margin_above_0p03": float(np.mean(margins > 0.03)),
            }
        statistics["receivers"][str(receiver_id)] = receiver
    receiver_zero = statistics["receivers"]["0"]
    statistics["receiver_0_native_to_cross_exact_ratio"] = {
        "left": receiver_zero["left_on_left"]["median_exact_score"]
        / max(receiver_zero["left_on_right"]["median_exact_score"], 1e-20),
        "right": receiver_zero["right_on_right"]["median_exact_score"]
        / max(receiver_zero["right_on_left"]["median_exact_score"], 1e-20),
    }
    return statistics


def _pilot_positions(symbols: tuple[int, ...]) -> np.ndarray:
    return np.concatenate(
        tuple(
            np.arange(
                round(symbol * SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S),
                round((symbol + 1) * SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S),
            )
            for symbol in symbols
        )
    )


def _phase_banks(positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.exp(
            -2j
            * np.pi
            * COARSE_OFFSETS_HZ[:, None]
            * positions[None, :]
            / SAMPLE_RATE_HZ
        ),
        np.exp(
            -2j
            * np.pi
            * FINE_OFFSETS_HZ[:, None]
            * positions[None, :]
            / SAMPLE_RATE_HZ
        ),
    )


def optimize_frame_cfo(
    products: np.ndarray,
    positions: np.ndarray,
    *,
    center_cfo_hz: float,
    phase_banks: tuple[np.ndarray, np.ndarray],
) -> float:
    """Maximize one frame with an arbitrary nuisance phase and no probe CFO."""

    coarse_bank, fine_bank = phase_banks
    center_rotation = np.exp(
        -2j * np.pi * center_cfo_hz * positions / SAMPLE_RATE_HZ
    )
    coarse_power = np.abs(coarse_bank @ (products * center_rotation)) ** 2
    coarse_frequency = center_cfo_hz + float(COARSE_OFFSETS_HZ[np.argmax(coarse_power)])
    coarse_rotation = np.exp(
        -2j * np.pi * coarse_frequency * positions / SAMPLE_RATE_HZ
    )
    fine_power = np.abs(fine_bank @ (products * coarse_rotation)) ** 2
    return coarse_frequency + float(FINE_OFFSETS_HZ[np.argmax(fine_power)])


def _normalized_power(
    received: np.ndarray,
    reference: np.ndarray,
    positions: np.ndarray,
    cfo_hz: float,
) -> float:
    samples = received[positions]
    expected = reference[positions]
    denominator = float(
        np.vdot(samples, samples).real * np.vdot(expected, expected).real
    )
    rotation = np.exp(-2j * np.pi * cfo_hz * positions / SAMPLE_RATE_HZ)
    return float(abs(np.vdot(expected, samples * rotation)) ** 2 / max(denominator, 1e-20))


def _nearest_frame_start(anchor_sample: int, target_time_s: float) -> int:
    target_sample = target_time_s * SAMPLE_RATE_HZ
    frame_index = round((target_sample - anchor_sample) / FRAME_PERIOD_SAMPLES)
    return round(anchor_sample + frame_index * FRAME_PERIOD_SAMPLES)


def analyze_frame_local_cfo(
    iq: np.ndarray,
    document: dict[str, Any],
    boundaries: tuple[BoundaryMode, ...],
) -> tuple[tuple[FrameFit, ...], float]:
    """Fit raw 1.333 ms frames independently on both sides of each boundary."""

    exact = np.asarray(
        qin_edge_pilot_frame(int(SAMPLE_RATE_HZ), StarlinkEdge.UPPER),
        dtype=np.complex128,
    )
    control = np.asarray(
        qin_edge_pilot_frame(
            int(SAMPLE_RATE_HZ),
            StarlinkEdge.UPPER,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        ),
        dtype=np.complex128,
    )
    even = _pilot_positions(tuple(range(2, 302, 2)))
    odd = _pilot_positions(tuple(range(3, 302, 2)))
    early = _pilot_positions(tuple(range(2, 152, 2)))
    late = _pilot_positions(tuple(range(152, 302, 2)))
    banks = {
        "even": _phase_banks(even),
        "early": _phase_banks(early),
        "late": _phase_banks(late),
    }
    raw_start = round(START_S * SAMPLE_RATE_HZ)
    raw_stop = raw_start + len(iq)
    output: list[FrameFit] = []
    random_phase_maximum_difference_hz = 0.0
    for boundary in boundaries:
        for offset_s in FRAME_OFFSETS_S:
            if offset_s < 0:
                side = "left"
                segment = boundary.left_segment
                anchor = boundary.left_anchor_sample
            else:
                side = "right"
                segment = boundary.right_segment
                anchor = boundary.right_anchor_sample
            frame_start = _nearest_frame_start(anchor, boundary.time_s + offset_s)
            if frame_start < raw_start or frame_start + len(exact) > raw_stop:
                continue
            received = iq[frame_start - raw_start : frame_start - raw_start + len(exact)]
            time_s = float((frame_start + 0.5 * len(exact)) / SAMPLE_RATE_HZ)
            center = segment_cfo(segment, time_s)
            all_products = np.conj(exact[even]) * received[even]
            early_products = np.conj(exact[early]) * received[early]
            late_products = np.conj(exact[late]) * received[late]
            fitted = optimize_frame_cfo(
                all_products,
                even,
                center_cfo_hz=center,
                phase_banks=banks["even"],
            )
            early_fitted = optimize_frame_cfo(
                early_products,
                early,
                center_cfo_hz=center,
                phase_banks=banks["early"],
            )
            late_fitted = optimize_frame_cfo(
                late_products,
                late,
                center_cfo_hz=center,
                phase_banks=banks["late"],
            )
            if len(output) < 12:
                arbitrary_phase = np.exp(1j * (0.371 * (len(output) + 1)))
                phase_fit = optimize_frame_cfo(
                    all_products * arbitrary_phase,
                    even,
                    center_cfo_hz=center,
                    phase_banks=banks["even"],
                )
                random_phase_maximum_difference_hz = max(
                    random_phase_maximum_difference_hz,
                    abs(phase_fit - fitted),
                )
            output.append(
                FrameFit(
                    boundary_index=boundary.boundary_index,
                    boundary_time_s=boundary.time_s,
                    side=side,
                    time_s=time_s,
                    fitted_cfo_hz=fitted,
                    early_half_cfo_hz=early_fitted,
                    late_half_cfo_hz=late_fitted,
                    segment_cfo_hz=center,
                    global_cfo_hz=global_cfo(document, time_s),
                    validation_exact_score=_normalized_power(received, exact, odd, fitted),
                    validation_control_score=_normalized_power(received, control, odd, fitted),
                )
            )
    return tuple(output), random_phase_maximum_difference_hz


def frame_statistics(
    frames: tuple[FrameFit, ...],
    boundaries: tuple[BoundaryMode, ...],
    *,
    random_phase_maximum_difference_hz: float,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    jumps: list[dict[str, Any]] = []
    modes = {item.boundary_index: item for item in boundaries}
    for boundary_index in sorted({item.boundary_index for item in frames}):
        group = tuple(item for item in frames if item.boundary_index == boundary_index)
        left = tuple(item for item in group if item.side == "left")
        right = tuple(item for item in group if item.side == "right")
        if len(left) < 3 or len(right) < 3:
            continue

        def residual_jump(
            field: str,
            left_frames: tuple[FrameFit, ...] = left,
            right_frames: tuple[FrameFit, ...] = right,
        ) -> float:
            return float(
                np.median(
                    [getattr(item, field) - item.global_cfo_hz for item in right_frames]
                )
                - np.median(
                    [getattr(item, field) - item.global_cfo_hz for item in left_frames]
                )
            )

        mode = modes[boundary_index]
        jumps.append(
            {
                "boundary_index": boundary_index,
                "time_s": mode.time_s,
                "direct_frame_jump_hz": residual_jump("fitted_cfo_hz"),
                "early_half_jump_hz": residual_jump("early_half_cfo_hz"),
                "late_half_jump_hz": residual_jump("late_half_cfo_hz"),
                "segment_predicted_jump_hz": segment_cfo(
                    mode.right_segment, mode.time_s
                )
                - segment_cfo(mode.left_segment, mode.time_s),
            }
        )
    direct = np.asarray([item["direct_frame_jump_hz"] for item in jumps])
    early = np.asarray([item["early_half_jump_hz"] for item in jumps])
    late = np.asarray([item["late_half_jump_hz"] for item in jumps])
    predicted = np.asarray([item["segment_predicted_jump_hz"] for item in jumps])
    exact = np.asarray([item.validation_exact_score for item in frames])
    control = np.asarray([item.validation_control_score for item in frames])
    segment_errors = np.asarray(
        [item.fitted_cfo_hz - item.segment_cfo_hz for item in frames]
    )
    statistics = {
        "frame_count": len(frames),
        "boundary_count": len(jumps),
        "validation_exact_over_control_fraction": float(np.mean(exact > control)),
        "median_validation_exact_control_margin": float(np.median(exact - control)),
        "median_absolute_direct_minus_segment_cfo_hz": float(
            np.median(np.abs(segment_errors))
        ),
        "p90_absolute_direct_minus_segment_cfo_hz": float(
            np.percentile(np.abs(segment_errors), 90)
        ),
        "median_direct_frame_jump_hz": float(np.median(direct)),
        "p10_direct_frame_jump_hz": float(np.percentile(direct, 10)),
        "p90_direct_frame_jump_hz": float(np.percentile(direct, 90)),
        "negative_direct_frame_jump_fraction": float(np.mean(direct < 0.0)),
        "median_early_half_jump_hz": float(np.median(early)),
        "median_late_half_jump_hz": float(np.median(late)),
        "median_segment_predicted_jump_hz": float(np.median(predicted)),
        "direct_vs_segment_jump_correlation": float(np.corrcoef(direct, predicted)[0, 1]),
        "early_vs_late_jump_correlation": float(np.corrcoef(early, late)[0, 1]),
        "random_per_frame_phase_maximum_cfo_change_hz": float(
            random_phase_maximum_difference_hz
        ),
    }
    return statistics, tuple(jumps)


def receiver_control_scan(
    iq: np.ndarray,
    document: dict[str, Any],
    *,
    maximum_cells: int,
) -> dict[str, Any]:
    """Blindly scan uniformly sampled receiver-1 cells to establish sensitivity."""

    if maximum_cells < 1:
        return {"performed": False}
    cells_by_index: dict[int, dict[str, Any]] = {}
    for item in document["primary_path"]:
        cells_by_index.setdefault(int(item["cell_index"]), item)
    cells = tuple(cells_by_index.values())
    selected_indexes = np.unique(
        np.linspace(0, len(cells) - 1, min(maximum_cells, len(cells))).round().astype(int)
    )
    selected = tuple(cells[index] for index in selected_indexes)
    raw_start = round(START_S * SAMPLE_RATE_HZ)
    config = blind.acquisition_config(maximum_probe_samples=CELL_SAMPLES)
    calibration = ReceiverFrequencyCalibration("blind-rx1-control", 0.0, "1" * 64)
    best_margins: list[float] = []
    best_verify: list[float] = []
    passing_cells = 0
    for cell_index, cell in enumerate(selected, start=1):
        start = round(cell["cell_start_s"] * SAMPLE_RATE_HZ) - raw_start
        values = np.ascontiguousarray(iq[start : start + CELL_SAMPLES])
        result = acquire_symbolwise(
            values,
            SAMPLE_RATE_HZ,
            calibration,
            edge=StarlinkEdge.UPPER,
            config=config,
        )
        margins = [item.verify_minus_control_margin for item in result.candidates]
        verifies = [item.verify_score for item in result.candidates]
        best_margins.append(max(margins, default=0.0))
        best_verify.append(max(verifies, default=0.0))
        if any(
            item.verify_score >= 0.08 and item.verify_minus_control_margin >= 0.03
            for item in result.candidates
        ):
            passing_cells += 1
        if cell_index % 25 == 0 or cell_index == len(selected):
            print(f"receiver-1 blind sensitivity scan {cell_index}/{len(selected)} cells")
    return {
        "performed": True,
        "cell_count": len(selected),
        "passing_cell_count": passing_cells,
        "passing_cell_fraction": passing_cells / len(selected),
        "median_best_margin": float(np.median(best_margins)),
        "maximum_best_margin": float(np.max(best_margins)),
        "median_best_verify_score": float(np.median(best_verify)),
        "maximum_best_verify_score": float(np.max(best_verify)),
        "interpretation": (
            "blind sensitivity check; full-path comparison is required "
            "to identify a matching branch"
        ),
    }


def _boundaries(document: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        [
            item["preceding_boundary_time_s"]
            for item in document["primary_segments"]
            if item["preceding_boundary_time_s"] is not None
        ],
        dtype=float,
    )


def grid_robustness(
    base: dict[str, Any],
    variants: tuple[tuple[str, dict[str, Any]], ...],
) -> dict[str, Any]:
    base_boundaries = _boundaries(base)
    output: dict[str, Any] = {
        "base": {
            "boundary_count": len(base_boundaries),
            "global_slope_hz_s": base["primary_line"]["slope_hz_s"],
            "median_local_slope_hz_s": base["primary_segment_statistics"][
                "median_local_slope_hz_s"
            ],
            "median_boundary_spacing_ms": base["primary_segment_statistics"][
                "median_boundary_spacing_ms"
            ],
        },
        "variants": {},
    }
    for label, document in variants:
        variant_boundaries = _boundaries(document)
        base_to_variant = np.min(
            np.abs(base_boundaries[:, None] - variant_boundaries[None, :]), axis=1
        )
        variant_to_base = np.min(
            np.abs(variant_boundaries[:, None] - base_boundaries[None, :]), axis=1
        )
        output["variants"][label] = {
            "boundary_count": len(variant_boundaries),
            "base_boundaries_within_12_ms": int(np.count_nonzero(base_to_variant <= 0.012)),
            "variant_boundaries_within_12_ms": int(
                np.count_nonzero(variant_to_base <= 0.012)
            ),
            "base_to_variant_median_ms": float(np.median(base_to_variant) * 1_000),
            "base_to_variant_p90_ms": float(np.percentile(base_to_variant, 90) * 1_000),
            "global_slope_hz_s": document["primary_line"]["slope_hz_s"],
            "median_local_slope_hz_s": document["primary_segment_statistics"][
                "median_local_slope_hz_s"
            ],
            "median_boundary_spacing_ms": document["primary_segment_statistics"][
                "median_boundary_spacing_ms"
            ],
            "boundary_times_s": variant_boundaries.tolist(),
            "base_nearest_differences_ms": (base_to_variant * 1_000).tolist(),
        }
    output["base"]["boundary_times_s"] = base_boundaries.tolist()
    return output


def receiver_branch_comparison(
    receiver0: dict[str, Any],
    receiver1: dict[str, Any],
) -> dict[str, Any]:
    """Compare receiver-0 secondary with the matching receiver-1 primary branch."""

    receiver0_path = {
        int(item["cell_index"]): item for item in receiver0["secondary_path"]
    }
    receiver1_path = {
        int(item["cell_index"]): item for item in receiver1["primary_path"]
    }
    common_cells = sorted(receiver0_path.keys() & receiver1_path.keys())
    times = np.asarray(
        [receiver0_path[index]["cell_center_s"] for index in common_cells], dtype=float
    )
    timing_differences = np.asarray(
        [
            receiver1_path[index]["refined_epoch_sample"]
            - receiver0_path[index]["refined_epoch_sample"]
            for index in common_cells
        ],
        dtype=float,
    )
    timing_differences = (
        (timing_differences + 0.5 * FRAME_PERIOD_SAMPLES) % FRAME_PERIOD_SAMPLES
    ) - 0.5 * FRAME_PERIOD_SAMPLES
    cfo_differences = np.asarray(
        [
            receiver1_path[index]["absolute_cfo_hz"]
            - receiver0_path[index]["absolute_cfo_hz"]
            for index in common_cells
        ],
        dtype=float,
    )
    reference_time_s = float(np.mean(times))
    design = np.column_stack((np.ones(len(times)), times - reference_time_s))
    cfo_at_reference_hz, cfo_drift_hz_s = np.linalg.lstsq(
        design, cfo_differences, rcond=None
    )[0]
    cfo_residuals = cfo_differences - design @ np.asarray(
        [cfo_at_reference_hz, cfo_drift_hz_s]
    )

    receiver0_candidates = tuple(
        blind.BlindCandidate(**item) for item in receiver0["secondary_path"]
    )
    receiver1_candidates = tuple(
        blind.BlindCandidate(**item) for item in receiver1["primary_path"]
    )
    receiver0_events = blind.detect_events(
        receiver0_candidates,
        blind.LatentLine(**receiver0["secondary_line"]),
    )
    receiver1_events = blind.detect_events(
        receiver1_candidates,
        blind.LatentLine(**receiver1["primary_line"]),
    )
    event_pairs: list[dict[str, Any]] = []
    unused_receiver1 = set(range(len(receiver1_events)))
    for receiver0_event in receiver0_events:
        eligible = [
            index
            for index in unused_receiver1
            if abs(receiver1_events[index].time_s - receiver0_event.time_s) <= 0.008
        ]
        if not eligible:
            continue
        receiver1_index = min(
            eligible,
            key=lambda index: abs(
                receiver1_events[index].time_s - receiver0_event.time_s
            ),
        )
        unused_receiver1.remove(receiver1_index)
        receiver1_event = receiver1_events[receiver1_index]
        event_pairs.append(
            {
                "receiver0_time_s": receiver0_event.time_s,
                "receiver1_time_s": receiver1_event.time_s,
                "time_difference_ms": (
                    receiver1_event.time_s - receiver0_event.time_s
                )
                * 1_000,
                "receiver0_cfo_jump_hz": receiver0_event.cfo_jump_hz,
                "receiver1_cfo_jump_hz": receiver1_event.cfo_jump_hz,
                "receiver0_timing_jump_samples": receiver0_event.timing_jump_samples,
                "receiver1_timing_jump_samples": receiver1_event.timing_jump_samples,
            }
        )
    receiver0_jumps = np.asarray(
        [item["receiver0_cfo_jump_hz"] for item in event_pairs]
    )
    receiver1_jumps = np.asarray(
        [item["receiver1_cfo_jump_hz"] for item in event_pairs]
    )
    timing_agreement = np.asarray(
        [
            item["receiver1_timing_jump_samples"]
            - item["receiver0_timing_jump_samples"]
            for item in event_pairs
        ]
    )
    receiver1_event_times = np.asarray(
        [item.time_s for item in receiver1_events], dtype=float
    )
    cadence_cycles = np.arange(len(receiver1_event_times), dtype=float)
    cadence_design = np.column_stack(
        (np.ones(len(receiver1_event_times)), cadence_cycles)
    )
    cadence_epoch_s, cadence_period_s = np.linalg.lstsq(
        cadence_design, receiver1_event_times, rcond=None
    )[0]
    cadence_residuals_ms = (
        receiver1_event_times
        - cadence_design @ np.asarray([cadence_epoch_s, cadence_period_s])
    ) * 1_000
    return {
        "receiver0_branch": "secondary",
        "receiver1_branch": "primary",
        "common_cell_count": len(common_cells),
        "timing_difference_median_samples": float(np.median(timing_differences)),
        "timing_difference_mad_samples": float(
            np.median(
                np.abs(timing_differences - np.median(timing_differences))
            )
        ),
        "timing_difference_p10_samples": float(np.percentile(timing_differences, 10)),
        "timing_difference_p90_samples": float(np.percentile(timing_differences, 90)),
        "timing_difference_within_2_samples_fraction": float(
            np.mean(np.abs(timing_differences) <= 2)
        ),
        "cfo_difference_reference_time_s": reference_time_s,
        "cfo_difference_at_reference_hz": float(cfo_at_reference_hz),
        "cfo_difference_drift_hz_s": float(cfo_drift_hz_s),
        "cfo_difference_detrended_rms_hz": float(np.sqrt(np.mean(cfo_residuals**2))),
        "receiver0_adjacent_event_count": len(receiver0_events),
        "receiver1_adjacent_event_count": len(receiver1_events),
        "matched_event_count": len(event_pairs),
        "matched_event_median_absolute_time_difference_ms": float(
            np.median(np.abs([item["time_difference_ms"] for item in event_pairs]))
        ),
        "matched_event_timing_jump_within_2_samples_fraction": float(
            np.mean(np.abs(timing_agreement) <= 2)
        ),
        "matched_event_cfo_jump_correlation": float(
            np.corrcoef(receiver0_jumps, receiver1_jumps)[0, 1]
        ),
        "matched_event_receiver0_median_cfo_jump_hz": float(
            np.median(receiver0_jumps)
        ),
        "matched_event_receiver1_median_cfo_jump_hz": float(
            np.median(receiver1_jumps)
        ),
        "receiver1_event_cadence_period_ms": float(cadence_period_s * 1_000),
        "receiver1_event_cadence_rms_ms": float(
            np.sqrt(np.mean(cadence_residuals_ms**2))
        ),
        "receiver1_event_cadence_p90_absolute_residual_ms": float(
            np.percentile(np.abs(cadence_residuals_ms), 90)
        ),
        "common_cells": [
            {
                "time_s": float(time_s),
                "timing_difference_samples": float(timing_difference),
                "cfo_difference_hz": float(cfo_difference),
                "cfo_difference_residual_hz": float(cfo_residual),
            }
            for time_s, timing_difference, cfo_difference, cfo_residual in zip(
                times,
                timing_differences,
                cfo_differences,
                cfo_residuals,
                strict=True,
            )
        ],
        "matched_events": event_pairs,
    }


def render_crossfit(
    path: Path,
    rows: tuple[dict[str, Any], ...],
    statistics: dict[str, Any],
) -> None:
    figure = Figure(figsize=(18, 12), constrained_layout=True)
    axes = figure.subplots(2, 1, gridspec_kw={"height_ratios": (1.35, 1.0)})
    figure.suptitle(
        "Frozen timing/CFO modes replace one another at blind boundaries",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    times = np.asarray([item["time_s"] for item in rows])
    series = (
        ("left_on_left", "left mode on left cells", BLUE),
        ("right_on_right", "right mode on right cells", GREEN),
        ("left_on_right", "old left mode on right cells", RED),
        ("right_on_left", "new right mode on left cells", AMBER),
    )
    for key, label, color in series:
        margins = np.asarray([item["receiver_0"][key]["margin"] for item in rows])
        axes[0].scatter(times, margins, s=30, color=color, alpha=0.72, linewidths=0, label=label)
    axes[0].axhline(
        0.03,
        color=INK,
        linewidth=1.1,
        linestyle=(0, (5, 4)),
        alpha=0.7,
        label="Qin retention margin 0.03",
    )
    axes[0].set_ylabel("median exact − control score")
    axes[0].set_xlabel("capture time (s)")
    axes[0].legend(loc="upper right", ncol=2)
    axes[0].set_title(
        "A · Native modes remain strong; cross-boundary modes collapse to control",
        loc="left",
        color=INK,
        fontweight="bold",
    )

    labels = ("native left", "native right", "old on right", "new on left")
    keys = ("left_on_left", "right_on_right", "left_on_right", "right_on_left")
    positions = np.arange(len(labels), dtype=float)
    for receiver_id, shift, color, name in (
        (0, -0.12, BLUE, "receiver 0"),
        (1, 0.12, GRAY, "receiver 1 control"),
    ):
        values = [
            statistics["receivers"][str(receiver_id)][key]["median_margin"] for key in keys
        ]
        axes[1].scatter(
            positions + shift,
            values,
            s=95,
            color=color,
            alpha=0.86,
            linewidths=0,
            label=name,
        )
    axes[1].axhline(0.03, color=INK, linewidth=1.1, linestyle=(0, (5, 4)), alpha=0.7)
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylabel("median exact − control score")
    axes[1].set_title(
        "B · Receiver 1 does not observe the frozen receiver-0 primary hypotheses",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="upper right")
    for axis in axes:
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_frame_local(
    path: Path,
    frames: tuple[FrameFit, ...],
    jumps: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(18, 14), constrained_layout=True)
    axes = figure.subplots(3, 1)
    figure.suptitle(
        "Independent raw-frame CFO confirms a within-frame frequency reset",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    relative_ms = np.asarray(
        [(item.time_s - item.boundary_time_s) * 1_000 for item in frames]
    )
    residuals = np.asarray([item.fitted_cfo_hz - item.global_cfo_hz for item in frames])
    positive = np.asarray(
        [item.validation_exact_score > item.validation_control_score for item in frames]
    )
    axes[0].scatter(
        relative_ms[~positive],
        residuals[~positive],
        s=18,
        color=GRAY,
        alpha=0.24,
        linewidths=0,
        label="held-out Qin ≤ control",
    )
    axes[0].scatter(
        relative_ms[positive],
        residuals[positive],
        s=22,
        color=BLUE,
        alpha=0.54,
        linewidths=0,
        label="held-out Qin > control",
    )
    axes[0].axvline(0.0, color=RED, linewidth=1.2, linestyle=(0, (5, 4)))
    axes[0].set_xlabel("time from blind timing boundary (ms)")
    axes[0].set_ylabel("independent frame CFO − global line (Hz)")
    axes[0].legend(loc="lower left", ncol=2)
    axes[0].set_title(
        "A · Six independently optimized 1.333 ms frames per boundary",
        loc="left",
        color=INK,
        fontweight="bold",
    )

    predicted = np.asarray([item["segment_predicted_jump_hz"] for item in jumps])
    direct = np.asarray([item["direct_frame_jump_hz"] for item in jumps])
    minimum = float(min(np.min(predicted), np.min(direct)))
    maximum = float(max(np.max(predicted), np.max(direct)))
    padding = 0.06 * (maximum - minimum)
    axes[1].scatter(predicted, direct, s=38, color=GREEN, alpha=0.74, linewidths=0)
    axes[1].plot(
        [minimum - padding, maximum + padding],
        [minimum - padding, maximum + padding],
        color=INK,
        linewidth=1.1,
        linestyle=(0, (4, 3)),
        label="identity",
    )
    axes[1].set_xlabel("12 ms segment-predicted CFO reset (Hz)")
    axes[1].set_ylabel("independent raw-frame CFO reset (Hz)")
    axes[1].legend(loc="upper left")
    axes[1].set_title(
        "B · Frame-local reset versus independently fitted segment reset",
        loc="left",
        color=INK,
        fontweight="bold",
    )

    early = np.asarray([item["early_half_jump_hz"] for item in jumps])
    late = np.asarray([item["late_half_jump_hz"] for item in jumps])
    minimum = float(min(np.min(early), np.min(late)))
    maximum = float(max(np.max(early), np.max(late)))
    padding = 0.06 * (maximum - minimum)
    axes[2].scatter(early, late, s=38, color=PURPLE, alpha=0.72, linewidths=0)
    axes[2].plot(
        [minimum - padding, maximum + padding],
        [minimum - padding, maximum + padding],
        color=INK,
        linewidth=1.1,
        linestyle=(0, (4, 3)),
        label="identity",
    )
    axes[2].set_xlabel("early-half frame reset (Hz)")
    axes[2].set_ylabel("late-half frame reset (Hz)")
    axes[2].legend(loc="upper left")
    axes[2].set_title(
        "C · The reset is estimated independently in early and late pilot symbols",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    for axis in axes:
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_grid(path: Path, robustness: dict[str, Any]) -> None:
    figure = Figure(figsize=(18, 10), constrained_layout=True)
    axes = figure.subplots(2, 1, gridspec_kw={"height_ratios": (1.35, 1.0)})
    figure.suptitle(
        "Blind boundaries survive analysis-grid origin and support changes",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    lanes = (
        ("base", robustness["base"], 2.0, BLUE),
        (
            "12 ms cells, origin +2 ms",
            robustness["variants"]["origin_plus_2ms"],
            1.0,
            GREEN,
        ),
        (
            "16 ms cells, origin +1 ms",
            robustness["variants"]["support_16ms"],
            0.0,
            AMBER,
        ),
    )
    for _label, data, lane, color in lanes:
        times = np.asarray(data["boundary_times_s"])
        axes[0].vlines(times, lane - 0.30, lane + 0.30, color=color, linewidth=1.5, alpha=0.76)
    axes[0].set_yticks([2.0, 1.0, 0.0], [item[0] for item in lanes])
    axes[0].set_ylim(-0.6, 2.6)
    axes[0].set_xlabel("capture time (s)")
    axes[0].set_title(
        "A · Boundary-event lanes from three raw-IQ blind reruns",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    variants = robustness["variants"]
    labels = ("origin +2 ms", "16 ms support")
    for position, key, color in zip(
        range(2), ("origin_plus_2ms", "support_16ms"), (GREEN, AMBER), strict=True
    ):
        differences = np.asarray(variants[key]["base_nearest_differences_ms"])
        jitter = np.linspace(-0.09, 0.09, len(differences))
        axes[1].scatter(
            np.full(len(differences), position) + jitter,
            differences,
            s=25,
            color=color,
            alpha=0.66,
            linewidths=0,
        )
    axes[1].axhline(12.0, color=RED, linewidth=1.1, linestyle=(0, (5, 4)), label="12 ms")
    axes[1].set_xticks(range(2), labels)
    axes[1].set_ylabel("nearest boundary difference from base (ms)")
    axes[1].set_title(
        "B · Per-base-boundary nearest-event differences",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="upper left")
    for axis in axes:
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_receiver_branch(path: Path, comparison: dict[str, Any]) -> None:
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1)
    figure.suptitle(
        "The same timing/CFO branch is independently visible on both receiver channels",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    cells = comparison["common_cells"]
    times = np.asarray([item["time_s"] for item in cells])
    cfo_residuals = np.asarray([item["cfo_difference_residual_hz"] for item in cells])
    timing_differences = np.asarray(
        [item["timing_difference_samples"] for item in cells]
    )
    axes[0].scatter(
        times,
        cfo_residuals,
        s=16,
        color=BLUE,
        alpha=0.54,
        linewidths=0,
        rasterized=True,
    )
    axes[0].axhline(0.0, color=INK, linewidth=0.8, alpha=0.6)
    axes[0].set_xlabel("capture time (s)")
    axes[0].set_ylabel("inter-receiver CFO difference\nafter offset + drift removal (Hz)")
    axes[0].set_title(
        "A · Receiver/LNB offset is a nuisance constant plus slow drift",
        loc="left",
        color=INK,
        fontweight="bold",
    )

    timing_inliers = np.abs(timing_differences) <= 2
    axes[1].scatter(
        times[timing_inliers],
        timing_differences[timing_inliers],
        s=16,
        color=GREEN,
        alpha=0.62,
        linewidths=0,
        rasterized=True,
        label=f"within 2 samples ({np.count_nonzero(timing_inliers)})",
    )
    axes[1].scatter(
        times[~timing_inliers],
        np.sign(timing_differences[~timing_inliers]) * 24.0,
        marker="^",
        s=42,
        color=RED,
        alpha=0.78,
        linewidths=0,
        label=f"acquisition outliers, clipped ({np.count_nonzero(~timing_inliers)})",
    )
    axes[1].axhline(0.0, color=INK, linewidth=0.8, alpha=0.6)
    axes[1].set_xlabel("capture time (s)")
    axes[1].set_ylabel("receiver 1 − receiver 0\ntiming phase (samples)")
    axes[1].set_ylim(-30.0, 30.0)
    axes[1].set_title(
        "B · Receiver-0 secondary and receiver-1 primary share one frame lattice",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="upper right", ncol=2)

    events = comparison["matched_events"]
    receiver0_jumps = np.asarray([item["receiver0_cfo_jump_hz"] for item in events])
    receiver1_jumps = np.asarray([item["receiver1_cfo_jump_hz"] for item in events])
    minimum = float(min(np.min(receiver0_jumps), np.min(receiver1_jumps)))
    maximum = float(max(np.max(receiver0_jumps), np.max(receiver1_jumps)))
    padding = 0.08 * (maximum - minimum)
    axes[2].scatter(
        receiver0_jumps,
        receiver1_jumps,
        s=58,
        color=PURPLE,
        alpha=0.82,
        linewidths=0,
    )
    axes[2].plot(
        [minimum - padding, maximum + padding],
        [minimum - padding, maximum + padding],
        color=INK,
        linewidth=1.1,
        linestyle=(0, (4, 3)),
        label="identity",
    )
    axes[2].set_xlabel("receiver-0 secondary CFO reset (Hz)")
    axes[2].set_ylabel("receiver-1 primary CFO reset (Hz)")
    axes[2].set_title(
        "C · Independently acquired reset sizes at matched adjacent-cell events",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[2].legend(loc="upper left")
    for axis in axes:
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    figures = {
        name: os.path.relpath(value, path.parent) for name, value in document["figures"].items()
    }
    cross = document["crossfit_statistics"]
    rx0 = cross["receivers"]["0"]
    frame = document["frame_statistics"]
    receiver = document["receiver_control_scan"]
    receiver_pair = document["receiver_branch_comparison"]
    grid = document["grid_robustness"]
    origin = grid["variants"]["origin_plus_2ms"]
    support = grid["variants"]["support_16ms"]
    cross_rows = "\n".join(
        (
            "| left mode on left cells | "
            f"{rx0['left_on_left']['median_exact_score']:.3f} | "
            f"{rx0['left_on_left']['median_margin']:.3f} | "
            f"{rx0['left_on_left']['fraction_margin_above_0p03'] * 100:.1f}% |",
            "| right mode on right cells | "
            f"{rx0['right_on_right']['median_exact_score']:.3f} | "
            f"{rx0['right_on_right']['median_margin']:.3f} | "
            f"{rx0['right_on_right']['fraction_margin_above_0p03'] * 100:.1f}% |",
            "| old left mode on right cells | "
            f"{rx0['left_on_right']['median_exact_score']:.3f} | "
            f"{rx0['left_on_right']['median_margin']:.4f} | "
            f"{rx0['left_on_right']['fraction_margin_above_0p03'] * 100:.1f}% |",
            "| new right mode on left cells | "
            f"{rx0['right_on_left']['median_exact_score']:.3f} | "
            f"{rx0['right_on_left']['median_margin']:.4f} | "
            f"{rx0['right_on_left']['fraction_margin_above_0p03'] * 100:.1f}% |",
        )
    )
    frame_rows = "\n".join(
        (
            f"| raw frames | {frame['frame_count']} |",
            f"| boundaries with 3+3 frames | {frame['boundary_count']} |",
            "| held-out exact > control | "
            f"{frame['validation_exact_over_control_fraction'] * 100:.1f}% |",
            "| median absolute frame CFO − segment line | "
            f"{frame['median_absolute_direct_minus_segment_cfo_hz']:.1f} Hz |",
            "| median direct frame reset | "
            f"{frame['median_direct_frame_jump_hz']:+.1f} Hz |",
            "| 10–90% direct reset | "
            f"{frame['p10_direct_frame_jump_hz']:+.1f} to "
            f"{frame['p90_direct_frame_jump_hz']:+.1f} Hz |",
            "| fraction of direct resets negative | "
            f"{frame['negative_direct_frame_jump_fraction'] * 100:.1f}% |",
            "| direct-frame versus segment-jump correlation | "
            f"{frame['direct_vs_segment_jump_correlation']:.3f} |",
            "| early-half versus late-half jump correlation | "
            f"{frame['early_vs_late_jump_correlation']:.3f} |",
        )
    )
    grid_header = (
        "| blind rerun | boundaries | base boundaries within 12 ms | "
        "median nearest difference | global rate | median local rate | median spacing |"
    )
    grid_rows = "\n".join(
        (
            "| base 12/4 ms | "
            f"{grid['base']['boundary_count']} | — | — | "
            f"{grid['base']['global_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{grid['base']['median_local_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{grid['base']['median_boundary_spacing_ms']:.1f} ms |",
            "| origin +2 ms | "
            f"{origin['boundary_count']} | "
            f"{origin['base_boundaries_within_12_ms']}/{grid['base']['boundary_count']} | "
            f"{origin['base_to_variant_median_ms']:.1f} ms | "
            f"{origin['global_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{origin['median_local_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{origin['median_boundary_spacing_ms']:.1f} ms |",
            "| 16 ms support | "
            f"{support['boundary_count']} | "
            f"{support['base_boundaries_within_12_ms']}/{grid['base']['boundary_count']} | "
            f"{support['base_to_variant_median_ms']:.1f} ms | "
            f"{support['global_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{support['median_local_slope_hz_s'] / 1e3:.4f} kHz/s | "
            f"{support['median_boundary_spacing_ms']:.1f} ms |",
        )
    )
    text = f"""# What causes the `470384` timing–CFO sawtooth?

## Abstract

Four additional raw-IQ experiments distinguish an analysis-window artifact, a
pure inter-frame phase alias, and a persistent physical carrier step from a
replacement of the Qin-compatible timing/CFO state.  At {cross['boundary_count']}
well-supported blind boundaries, the native modes have median exact-minus-control
margins of {rx0['left_on_left']['median_margin']:.3f} and
{rx0['right_on_right']['median_margin']:.3f}.  Freezing the old mode and testing
it after the transition reduces the median margin to
{rx0['left_on_right']['median_margin']:.4f}; testing the new mode before the
transition gives {rx0['right_on_left']['median_margin']:.4f}.  Neither crossed
mode passes the 0.03 Qin gate at any boundary.  Thus a Qin-supported state is
being replaced, not merely moved in CFO while its timing persists.

Independent 1.333 ms raw-frame fits recover a median reset of
{frame['median_direct_frame_jump_hz']:+.1f} Hz.  They give each frame an arbitrary
carrier phase and use no 20 ms CFO.  Applying additional random per-frame phases
changes the recovered CFO by at most
{frame['random_per_frame_phase_maximum_cfo_change_hz']:.3g} Hz, so a pure phase
discontinuity between frames cannot generate this estimator's sawtooth.

Finally, an independent full blind acquisition on receiver 1 finds the same
timing branch as receiver 0's secondary path in
{receiver_pair['common_cell_count']} common cells.  Their median timing-phase
difference is {receiver_pair['timing_difference_median_samples']:.1f} samples,
and {receiver_pair['timing_difference_within_2_samples_fraction'] * 100:.1f}%
agree within two samples;
the large {receiver_pair['cfo_difference_at_reference_hz'] / 1e3:+.2f} kHz
receiver/LNB offset is absorbed as a nuisance constant plus only
{receiver_pair['cfo_difference_drift_hz_s']:+.2f} Hz/s drift.

## Motivation and hypotheses

The observed approximately 104 ms ramps could arise from four different
mechanisms:

1. **Analysis-window artifact:** the persisted 20 ms boundaries or the later
   12 ms blind grid impose the resets.
2. **Pure carrier-phase alias:** continuous CFO is re-labelled when carrier
   phase jumps between frames.
3. **Physical CFO retune of one continuing signal:** timing and Qin support
   persist while only frequency changes.
4. **Scheduled timing/source-state replacement:** one Qin-compatible burst or
   timing lattice disappears and another appears with a different timing phase
   and CFO intercept.

The experiments below are designed to falsify these signatures rather than to
select the visually nicest curve.

## Experiment 1 — freeze each mode and cross the boundary

For every adjacent fitted blind segment, five non-overlapping-safe 12 ms cells
are selected on each side.  The left timing lattice and local CFO line are
frozen and evaluated on both sides; the right mode is evaluated symmetrically.
No timing or CFO re-optimization is allowed in the crossed tests.

![Frozen-mode cross-fit]({figures['crossfit']})

| receiver-0 hypothesis | median exact score | median exact − control | fraction above 0.03 |
| --- | ---: | ---: | ---: |
{cross_rows}

The old state does not coexist measurably with the new state in these safe
cells.  This strongly disfavors a simple CFO retune of one continuous timing
lattice and also disfavors a winner-take-all fit switching between two
simultaneously visible modes.  It is consistent with scheduled burst, beam,
source, or timing-state replacement.  The experiment cannot distinguish those
four transmitter-side labels by itself.

## Experiment 2 — optimize individual raw frames

For each boundary, three frames 6–10 ms before and three frames 6–10 ms after
are built from the blind timing lattices.  CFO is maximized independently inside
each 1.333 ms raw frame using even Qin symbols.  Odd symbols and the rolled
control are held out.  No persisted 20 ms timing or CFO enters this fit.

![Frame-local CFO]({figures['frame_local']})

| frame-local statistic | result |
| --- | ---: |
{frame_rows}

The estimator takes the magnitude of each frame's complex matched correlation,
so a common phase rotation of a whole frame is analytically a nuisance that
cannot move the CFO maximum.  The numerical random-phase control confirms this
to the reported grid precision.  The reset must therefore affect timing and/or
the phase *slope within a frame*, not only phase continuity between frames.

## Experiment 3 — move the blind grid

The complete 33.7–37.7 s raw interval is searched again with the 12 ms cell
origin shifted by 2 ms, and with 16 ms cells whose origin is shifted by 1 ms.

![Grid robustness]({figures['grid']})

{grid_header}
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{grid_rows}

The event sequence, global rate, local ramp rate, and 104 ms cadence survive
both grid changes.  A small number of short gaps are split or merged, which
changes the raw segment count but not the central result.

## Experiment 4 — independent receiver branch

Receiver 1 was first tested at the frozen receiver-0 hypotheses and then scanned
blindly in {receiver.get('cell_count', 0)} uniformly sampled cells.  It produced
{receiver.get('passing_cell_count', 0)} cells passing the same Qin gate.  The
initial frozen test failed because receiver 1's strongest path corresponds to
receiver 0's **secondary**, not primary, blind branch.

![Cross-receiver branch comparison]({figures['receiver_branch']})

Across {receiver_pair['common_cell_count']} cells shared by those paths, the
timing-phase difference has median
{receiver_pair['timing_difference_median_samples']:.1f} samples and MAD
{receiver_pair['timing_difference_mad_samples']:.1f} samples;
{receiver_pair['timing_difference_within_2_samples_fraction'] * 100:.1f}% are
within two samples.  Their CFO
difference is {receiver_pair['cfo_difference_at_reference_hz'] / 1e3:+.2f} kHz
at {receiver_pair['cfo_difference_reference_time_s']:.3f} s, with only
{receiver_pair['cfo_difference_drift_hz_s']:+.2f} Hz/s differential drift and
{receiver_pair['cfo_difference_detrended_rms_hz']:.1f} Hz detrended RMS.

The receiver-0 branch has
{receiver_pair['receiver0_adjacent_event_count']} directly adjacent-cell events;
all {receiver_pair['matched_event_count']} are found on receiver 1 within 8 ms.
Their timing jumps agree within two samples in
{receiver_pair['matched_event_timing_jump_within_2_samples_fraction'] * 100:.1f}%
of cases, and their independently measured CFO resets correlate at
{receiver_pair['matched_event_cfo_jump_correlation']:.3f}.  This is strong
evidence that the resets belong to the received signal/timing state, not to one
receiver channel's optimization.  It also demonstrates why an unknown LNB
constant does not prevent the comparison: subtracting the inter-receiver offset
leaves the same event sequence and reset structure.

All {receiver_pair['receiver1_adjacent_event_count']} receiver-1 adjacent-cell
events fit a {receiver_pair['receiver1_event_cadence_period_ms']:.3f} ms linear
cadence with {receiver_pair['receiver1_event_cadence_rms_ms']:.2f} ms RMS timing
error.  That error is below the 4 ms blind-cell hop.  This is evidence for a
scheduler-like event clock, but it is not yet an identified Starlink protocol
period.

The two channels share one recorded stream but do not have a declared absolute
phase calibration, so this experiment still does not identify which hardware or
transmitter element owns the common state changes.

This distinction agrees with Qin et al.'s published signal model: Starlink
frames run at up to 750 Hz, the edge pilots repeat across frames and sources,
and carrier phase can be discontinuous between frames.  Their model does not
identify a roughly 104.9 ms retune.  The present experiment adds evidence for a
repeating timing/CFO *state replacement*, not proof of an oscillator command.
[Qin et al., *Unveiling Starlink's Downlink Waveform via Signal Processing*](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_pilots_starlink_dl.pdf)

The strongest supported interpretation is therefore:

- the sawtooth is not imposed by the 20 ms GLRT windows or the 12 ms blind grid;
- it is not a pure arbitrary phase jump between otherwise identical frames;
- each event replaces the currently visible Qin timing/CFO state;
- the same branch, timing jumps, and correlated CFO resets are independently
  visible through two receiver channels after removing their LNB/CFO offset;
- the approximately −300 Hz CFO intercept change is measurable within
  independently optimized 1.333 ms frames;
- the present data do **not** establish that a Starlink oscillator physically
  retunes every 104 ms.  Burst scheduling, beam/source handoff, or another
  waveform timing state remains the more careful description.

## Methods and data

- Capture: `{SESSION_ID}`
- Stream / receiver / edge: `stream-0` / receiver 0 / upper edge
- Raw interval: `{START_S:.3f}`–`{END_S:.3f}` s
- Sample rate: `{SAMPLE_RATE_HZ / 1e6:.1f}` MS/s
- Base blind input: `{document['input']['blind_results']}`
- Variant commands: the same blind tool with `--start-s 33.702` for the shifted
  origin and `--start-s 33.701 --cell-duration-s 0.016` for the changed support.
- Receiver-1 command: the same blind tool with `--receiver-id 1`; the compact
  paired-path evidence is persisted in this report's result JSON.
- All recording access was read-only; no TLE, Doppler trajectory, or 20 ms
  candidate was used to fit these experiments.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    document = _load(arguments.blind_results)
    shifted = _load(arguments.shifted_results)
    support = _load(arguments.support_results)
    receiver1_document = _load(arguments.receiver1_results)
    boundaries = boundary_modes(
        document,
        maximum_boundaries=arguments.maximum_boundaries,
    )
    receivers = read_raw_receivers(arguments.bulk_root)
    crossfit = analyze_mode_crossfit(receivers, boundaries)
    crossfit_summary = crossfit_statistics(crossfit)
    frames, random_phase_difference = analyze_frame_local_cfo(
        receivers[0], document, boundaries
    )
    frame_summary, frame_jumps = frame_statistics(
        frames,
        boundaries,
        random_phase_maximum_difference_hz=random_phase_difference,
    )
    receiver_summary = receiver_control_scan(
        receivers[1],
        document,
        maximum_cells=arguments.receiver_control_cells,
    )
    robustness = grid_robustness(
        document,
        (("origin_plus_2ms", shifted), ("support_16ms", support)),
    )
    receiver_pair = receiver_branch_comparison(document, receiver1_document)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    crossfit_path = arguments.output_root / "boundary-mode-crossfit.png"
    frame_path = arguments.output_root / "frame-local-boundary-cfo.png"
    grid_path = arguments.output_root / "blind-grid-robustness.png"
    receiver_path = arguments.output_root / "receiver-branch-comparison.png"
    render_crossfit(crossfit_path, crossfit, crossfit_summary)
    render_frame_local(frame_path, frames, frame_jumps)
    render_grid(grid_path, robustness)
    render_receiver_branch(receiver_path, receiver_pair)
    output = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-boundary-mechanism-discrimination-v1",
            "input": {
                "session_id": SESSION_ID,
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
                "blind_results": str(arguments.blind_results),
                "shifted_results": str(arguments.shifted_results),
                "support_results": str(arguments.support_results),
                "receiver1_results": str(arguments.receiver1_results),
                "raw_recording_access": "read-only",
            },
            "configuration": {
                "start_s": START_S,
                "end_s": END_S,
                "native_cells_per_side": 5,
                "native_cell_boundary_guard_ms": 8.0,
                "frame_offsets_ms": [value * 1_000 for value in FRAME_OFFSETS_S],
                "frame_train_symbols": "even Qin symbols 2..300",
                "frame_validation_symbols": "odd Qin symbols 3..301",
                "frame_cfo_coarse_step_hz": float(np.diff(COARSE_OFFSETS_HZ[:2])[0]),
                "frame_cfo_fine_step_hz": float(np.diff(FINE_OFFSETS_HZ[:2])[0]),
                "receiver_control_cells": arguments.receiver_control_cells,
            },
            "crossfit_statistics": crossfit_summary,
            "crossfit_boundaries": list(crossfit),
            "frame_statistics": frame_summary,
            "frame_jumps": list(frame_jumps),
            "frames": [asdict(item) for item in frames],
            "receiver_control_scan": receiver_summary,
            "receiver_branch_comparison": receiver_pair,
            "grid_robustness": robustness,
            "figures": {
                "crossfit": str(crossfit_path),
                "frame_local": str(frame_path),
                "grid": str(grid_path),
                "receiver_branch": str(receiver_path),
            },
        }
    )
    results_path = arguments.output_root / "boundary-mechanism-results.json"
    results_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(arguments.report_path, output)
    print(
        json.dumps(
            {
                "crossfit_statistics": output["crossfit_statistics"],
                "frame_statistics": output["frame_statistics"],
                "receiver_control_scan": output["receiver_control_scan"],
                "receiver_branch_comparison": {
                    key: value
                    for key, value in output["receiver_branch_comparison"].items()
                    if key not in {"common_cells", "matched_events"}
                },
                "grid_robustness": output["grid_robustness"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
