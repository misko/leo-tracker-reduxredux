#!/usr/bin/env python3
"""Prototype source-alias GLRT -> Qin frames -> ramp-local rates on five dwells."""

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

from leo.analysis.starlink import StarlinkEdge  # noqa: E402
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.analysis.starlink.pilot_methods import (  # noqa: E402
    _conditioned_correlation_workspace,
)
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

try:
    import report_d373c04a_glrt_frames as rate_tool
except ModuleNotFoundError:  # pragma: no cover - repository-root import
    from tools import report_d373c04a_glrt_frames as rate_tool


DEFAULT_SOURCE_RESULTS = Path(
    "reports/figures/2026_08_23_additional_subsecond_pilot_dwells/additional-dwell-results.json"
)
DEFAULT_OLD_RESULTS = Path(
    "reports/figures/2026_08_24_five_dwell_doppler_prototypes/five-dwell-doppler-prototypes.json"
)
DEFAULT_D2_RESULTS = Path(
    "reports/figures/2026_08_24_d373c04a_glrt_frames/d373c04a-glrt-frames.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_five_dwell_multiscale_local_rates")
DEFAULT_REPORT = Path("reports/2026_08_24_five_dwell_multiscale_local_rates.md")
DEFAULT_RESULT = DEFAULT_OUTPUT_ROOT / "five-dwell-multiscale-local-rates.json"

SAMPLE_RATE_HZ = 2_500_000.0
FRAME_RATE_HZ = 750.0
PROBE_DURATION_S = 0.020
GLRT_GATE = 0.10
FRAME_GATE = 0.20
MAXIMUM_MODEL_ERROR_HZ = 2_500.0
SYMBOLS = np.arange(2, 302, dtype=int)
RESIDUAL_GRID_HZ = np.arange(-6_000.0, 6_000.0 + 12.5, 25.0)

INK = "#17354a"
GRAY = "#96a2ab"
LIGHT_GRAY = "#d2d9de"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
PURPLE = "#7b65a8"
RED = "#bd5b52"
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
    start_s: float
    end_s: float
    reference_time_s: float
    coefficients_hz: tuple[float, float]
    anchor_time_s: float

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = np.polyval(
            np.asarray(self.coefficients_hz),
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )
        return float(value) if np.ndim(value) == 0 else value


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


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--source-results", type=Path, default=DEFAULT_SOURCE_RESULTS)
    parser.add_argument("--old-results", type=Path, default=DEFAULT_OLD_RESULTS)
    parser.add_argument("--d2-results", type=Path, default=DEFAULT_D2_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--refresh-all",
        action="store_true",
        help="recompute every frame from raw IQ instead of reusing matching aliases",
    )
    parser.add_argument(
        "--reuse-results",
        type=Path,
        help="reuse a complete five-dwell result and only regenerate figures/report",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def load_specs(source_path: Path) -> tuple[DwellSpec, ...]:
    source = _load(source_path)
    rows = source.get("results")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("source result must contain exactly five dwells")
    output = []
    for index, item in enumerate(rows, start=1):
        coefficients = tuple(float(value) for value in item["trajectory_coefficients_hz"])
        if len(coefficients) != 2:
            raise ValueError("five-dwell prototype requires degree-one branches")
        analysis_root = Path(item["analysis_root"])
        bank = _load(analysis_root / "standard.dealiased-trajectory-bank.v4.json")
        branches = [
            branch for branch in bank["branches"] if branch["branch_id"] == item["branch_id"]
        ]
        if len(branches) != 1:
            raise ValueError("source result must identify exactly one retained branch")
        branch = branches[0]
        output.append(
            DwellSpec(
                label=f"D{index} · {str(item['session_id']).split('-')[-1][:8]}",
                session_id=str(item["session_id"]),
                run_id=str(item["analysis_run_id"]),
                stream_id=str(item["stream_id"]),
                receiver_id=int(item["receiver_id"]),
                edge=StarlinkEdge(item["edge"]),
                analysis_root=analysis_root,
                branch_id=str(item["branch_id"]),
                start_s=float(branch["start_s"]),
                end_s=float(branch["end_s"]),
                reference_time_s=float(item["trajectory_reference_time_s"]),
                coefficients_hz=(coefficients[0], coefficients[1]),
                anchor_time_s=float(item["anchor"]["time_s"]),
            )
        )
    return tuple(output)


def _glrt64(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def select_candidate_windows(spec: DwellSpec, scan: dict[str, Any]) -> tuple[CandidateWindow, ...]:
    """Select the source-alias candidate while preserving its timing epoch."""

    windows = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not spec.start_s <= time_s <= spec.end_s:
            continue
        model_hz = float(spec.frequency_hz(time_s))
        candidates = []
        for candidate in detection["candidates"]:
            score = _glrt64(candidate)
            error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
            candidates.append((error_hz, int(candidate["rank"]), candidate, score))
        if not candidates:
            continue
        error_hz, _rank, candidate, score = min(candidates, key=lambda item: (item[0], item[1]))
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
    return tuple(windows)


def normalized_frequency_curves(
    values: np.ndarray,
    times_s: np.ndarray,
    symbol_indexes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    correlations = np.asarray(values, dtype=np.complex128)
    moments = np.asarray(times_s, dtype=float)
    indexes = np.asarray(symbol_indexes, dtype=int)
    selected_times = moments[:, indexes]
    lags = selected_times - np.mean(selected_times, axis=1, keepdims=True)
    if not np.allclose(lags, lags[:1], rtol=0.0, atol=2e-12):
        raise ValueError("frames do not share one within-frame symbol geometry")
    selected = correlations[:, indexes]
    phase_bank = np.exp(-2j * np.pi * lags[0, None, :] * RESIDUAL_GRID_HZ[:, None])
    powers = np.abs(selected @ phase_bank.T) ** 2
    ceilings = np.sum(np.abs(selected), axis=1) ** 2
    return np.asarray(powers, dtype=np.float32), np.asarray(ceilings, dtype=float)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15)


def build_frame_rows(
    *,
    bulk_root: Path,
    spec: DwellSpec,
    scan: dict[str, Any],
    windows: tuple[CandidateWindow, ...],
) -> list[dict[str, Any]]:
    probe_samples = int(scan["probe_samples"])
    even = np.arange(0, len(SYMBOLS), 2, dtype=int)
    odd = np.arange(1, len(SYMBOLS), 2, dtype=int)
    rows = []
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
                selected_symbols=SYMBOLS,
            )
            exact = workspace.select(SYMBOLS)
            control = workspace.select(SYMBOLS, control=True)
            if not exact.values.size or exact.values.shape != control.values.shape:
                continue
            even_exact, even_exact_ceiling = normalized_frequency_curves(
                exact.values, exact.times_s, even
            )
            even_control, even_control_ceiling = normalized_frequency_curves(
                control.values, control.times_s, even
            )
            odd_exact, _odd_ceiling = normalized_frequency_curves(exact.values, exact.times_s, odd)
            absolute_offset_s = window.aligned_sample_start / SAMPLE_RATE_HZ
            for frame_index in range(exact.values.shape[0]):
                train_index = int(np.argmax(even_exact[frame_index]))
                validation_index = int(np.argmax(odd_exact[frame_index]))
                train_exact = float(
                    even_exact[frame_index, train_index]
                    / max(float(even_exact_ceiling[frame_index]), 1e-20)
                )
                train_control = float(
                    even_control[frame_index, train_index]
                    / max(float(even_control_ceiling[frame_index]), 1e-20)
                )
                rows.append(
                    {
                        "row_index": len(rows),
                        "window_index": window.window_index,
                        "time_s": float(absolute_offset_s + np.mean(exact.times_s[frame_index])),
                        "train_cfo_hz": float(
                            window.analysis_cfo_hz + RESIDUAL_GRID_HZ[train_index]
                        ),
                        "validation_cfo_hz": float(
                            window.analysis_cfo_hz + RESIDUAL_GRID_HZ[validation_index]
                        ),
                        "nco_cfo_hz": window.analysis_cfo_hz,
                        "train_exact_score": train_exact,
                        "train_control_score": train_control,
                        "train_margin": train_exact - train_control,
                    }
                )
            if position % 40 == 0 or position == len(windows):
                print(
                    f"{spec.label}: raw Qin frames {position}/{len(windows)} windows",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()
    return rows


def _spec_document(spec: DwellSpec) -> dict[str, Any]:
    return {
        "label": spec.label,
        "session_id": spec.session_id,
        "run_id": spec.run_id,
        "stream_id": spec.stream_id,
        "receiver_id": spec.receiver_id,
        "edge": spec.edge.value,
        "analysis_root": str(spec.analysis_root),
        "branch_id": spec.branch_id,
        "branch_start_s": spec.start_s,
        "branch_end_s": spec.end_s,
        "branch_reference_time_s": spec.reference_time_s,
        "branch_coefficients_hz": list(spec.coefficients_hz),
        "anchor_time_s": spec.anchor_time_s,
    }


def _coefficients_match(left: dict[str, Any], spec: DwellSpec) -> bool:
    coefficients = np.asarray(left.get("branch_coefficients_hz", ()), dtype=float)
    return bool(
        coefficients.shape == (2,)
        and np.allclose(coefficients, spec.coefficients_hz, atol=1e-6, rtol=0.0)
        and math.isclose(
            float(left["branch_reference_time_s"]),
            spec.reference_time_s,
            abs_tol=1e-9,
        )
    )


def _seed_documents(old_results_path: Path, d2_results_path: Path) -> dict[str, dict[str, Any]]:
    output = {}
    if old_results_path.exists():
        old = _load(old_results_path)
        for item in old.get("dwells", []):
            output[str(item["spec"]["session_id"])] = {
                "spec": item["spec"],
                "windows": item["windows"],
                "frames": item["frames"],
                "source": "prior raw-IQ frame analysis at matching source alias",
            }
    if d2_results_path.exists():
        item = _load(d2_results_path)
        output[str(item["session_id"])] = {
            "spec": item["spec"],
            "windows": item["windows"],
            "frames": item["frames"],
            "source": "corrected source-alias raw-IQ frame analysis",
        }
    return output


def _dwell_summary(document: dict[str, Any]) -> dict[str, Any]:
    windows = document["windows"]
    frames = document["frames"]
    return {
        "window_count": len(windows),
        "source_alias_near_window_count": sum(
            float(item["selection_model_error_hz"]) <= MAXIMUM_MODEL_ERROR_HZ for item in windows
        ),
        "strong_glrt_window_count": sum(
            float(item["glrt_exact_score"]) >= GLRT_GATE
            and float(item["glrt_margin"]) > 0.0
            and float(item["selection_model_error_hz"]) <= MAXIMUM_MODEL_ERROR_HZ
            for item in windows
        ),
        "frame_count": len(frames),
        "strong_frame_count": sum(
            float(item["train_exact_score"]) >= FRAME_GATE and float(item["train_margin"]) > 0.0
            for item in frames
        ),
    }


def analyze_dwell(
    *,
    bulk_root: Path,
    spec: DwellSpec,
    seed: dict[str, Any] | None,
    refresh: bool,
) -> dict[str, Any]:
    if not refresh and seed is not None and _coefficients_match(seed["spec"], spec):
        windows = seed["windows"]
        frames = seed["frames"]
        frame_source = seed["source"]
    else:
        scan = _load(spec.analysis_root / "standard.pilot-scan.v3.json")
        selected = select_candidate_windows(spec, scan)
        windows = [asdict(item) for item in selected]
        frames = build_frame_rows(
            bulk_root=bulk_root,
            spec=spec,
            scan=scan,
            windows=selected,
        )
        frame_source = "recomputed from digest-verified raw IQ at source alias"
    document = {
        "session_id": spec.session_id,
        "stream_id": spec.stream_id,
        "receiver_id": spec.receiver_id,
        "edge": spec.edge.value,
        "frame_source": frame_source,
        "frame_duration_s": 1.0 / FRAME_RATE_HZ,
        "probe_duration_s": PROBE_DURATION_S,
        "frame_qin_gate": FRAME_GATE,
        "glrt_qin_gate": GLRT_GATE,
        "spec": _spec_document(spec),
        "windows": windows,
        "frames": frames,
    }
    document["summary"] = _dwell_summary(document)
    primary = rate_tool._rate_fit_at_gate(document, exact_gate=FRAME_GATE)
    sensitivity = []
    for gate in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        result = rate_tool._rate_fit_at_gate(document, exact_gate=gate)
        sensitivity.append(
            {
                "exact_gate": gate,
                "status": result["status"],
                "qualified_frame_count": result["qualified_frame_count"],
                "coherent_segment_count": result.get("coherent_segment_count", 0),
                "common_slope_hz_s": (
                    result["common_slope"]["shared_slope_hz_s"]
                    if result["status"] == "complete"
                    else None
                ),
                "odd_validation_rms_hz": (
                    result["errors"]["common_slope"]["odd_validation"]["rms_hz"]
                    if result["status"] == "complete"
                    else None
                ),
            }
        )
    document["rate_analysis"] = primary
    document["gate_sensitivity"] = sensitivity
    return document


def analyze_all(
    *,
    bulk_root: Path,
    source_results_path: Path,
    old_results_path: Path,
    d2_results_path: Path,
    refresh_all: bool,
) -> dict[str, Any]:
    specs = load_specs(source_results_path)
    seeds = _seed_documents(old_results_path, d2_results_path)
    dwells = []
    for spec in specs:
        print(f"{spec.label}: source-alias multiscale analysis", flush=True)
        dwells.append(
            analyze_dwell(
                bulk_root=bulk_root,
                spec=spec,
                seed=seeds.get(spec.session_id),
                refresh=refresh_all,
            )
        )
    return {
        "schema": "org.leo.research.five-dwell-multiscale-local-rates/v1",
        "algorithm": "source-alias-glrt-qin-frame-ramp-family-v1",
        "configuration": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "frame_rate_hz": FRAME_RATE_HZ,
            "probe_duration_s": PROBE_DURATION_S,
            "glrt_exact_gate": GLRT_GATE,
            "frame_exact_gate": FRAME_GATE,
            "maximum_source_alias_model_error_hz": MAXIMUM_MODEL_ERROR_HZ,
            "ramp_minimum_span_s": rate_tool.MINIMUM_COHERENT_SPAN_S,
            "ramp_maximum_raw_rms_hz": rate_tool.MAXIMUM_COHERENT_RMS_HZ,
        },
        "source_results_path": str(source_results_path),
        "candidate_only": True,
        "known_pilots_only": True,
        "payload_decoded": False,
        "dwells": dwells,
    }


def _model_frequency(document: dict[str, Any], times_s: np.ndarray) -> np.ndarray:
    spec = document["spec"]
    return rate_tool.model_frequency(
        times_s,
        spec["branch_coefficients_hz"],
        float(spec["branch_reference_time_s"]),
    )


def render_dwell(path: Path, document: dict[str, Any]) -> None:
    windows = document["windows"]
    frames = document["frames"]
    window_times = np.asarray([item["detection_time_s"] for item in windows])
    window_cfo = np.asarray([item["initial_cfo_hz"] for item in windows])
    window_residual = window_cfo - _model_frequency(document, window_times)
    window_strong = np.asarray(
        [
            item["glrt_exact_score"] >= GLRT_GATE
            and item["glrt_margin"] > 0.0
            and item["selection_model_error_hz"] <= MAXIMUM_MODEL_ERROR_HZ
            for item in windows
        ]
    )
    frame_times = np.asarray([item["time_s"] for item in frames])
    frame_cfo = np.asarray([item["train_cfo_hz"] for item in frames])
    frame_residual = frame_cfo - _model_frequency(document, frame_times)
    frame_strong = np.asarray(
        [item["train_exact_score"] >= FRAME_GATE and item["train_margin"] > 0.0 for item in frames]
    )
    supported = np.concatenate((window_residual[window_strong], frame_residual[frame_strong]))
    residual_limit = max(500.0, 1.2 * float(np.percentile(np.abs(supported), 99)))
    residual_limit = min(3_000.0, residual_limit)

    figure = Figure(figsize=(18, 12), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": (0.8, 1.0, 1.35)})
    figure.suptitle(
        f"{document['spec']['label']} · source-alias acquisition to local rate",
        fontsize=20,
        color=INK,
        fontweight="bold",
    )
    for index, item in enumerate(windows):
        start = float(item["detection_time_s"])
        for axis in axes:
            axis.axvline(
                start,
                color=RED,
                linewidth=0.55,
                linestyle=(0, (3, 3)),
                alpha=0.16,
                zorder=0,
            )
        segment_time = np.asarray([start, start + PROBE_DURATION_S])
        segment_residual = float(item["initial_cfo_hz"]) - _model_frequency(document, segment_time)
        axes[1].plot(
            segment_time,
            segment_residual,
            color=AMBER if window_strong[index] else GRAY,
            linewidth=1.8 if window_strong[index] else 0.8,
            alpha=0.78 if window_strong[index] else 0.18,
        )
    axes[0].scatter(
        window_times,
        [item["glrt_exact_score"] for item in windows],
        s=17,
        color=AMBER,
        alpha=0.75,
        linewidths=0,
        label="exact Qin GLRT64",
    )
    axes[0].scatter(
        window_times,
        [item["glrt_control_score"] for item in windows],
        s=14,
        color=GRAY,
        alpha=0.52,
        linewidths=0,
        label="rolled control",
    )
    axes[0].axhline(
        GLRT_GATE,
        color=RED,
        linewidth=0.9,
        linestyle=(0, (5, 4)),
        alpha=0.65,
        label=f"GLRT gate {GLRT_GATE:.2f}",
    )
    axes[1].scatter(
        window_times[window_strong],
        np.clip(window_residual[window_strong], -residual_limit, residual_limit),
        s=12,
        color=AMBER,
        alpha=0.75,
        linewidths=0,
        label=f"supported 20 ms windows ({np.count_nonzero(window_strong)})",
    )
    visible = np.abs(frame_residual) <= residual_limit
    axes[2].scatter(
        frame_times[~frame_strong & visible],
        frame_residual[~frame_strong & visible],
        s=5,
        color=GRAY,
        alpha=0.12,
        linewidths=0,
        rasterized=True,
        label=f"weak frame maxima ({np.count_nonzero(~frame_strong)})",
    )
    axes[2].scatter(
        frame_times[frame_strong & visible],
        frame_residual[frame_strong & visible],
        s=7,
        color=BLUE,
        alpha=0.48,
        linewidths=0,
        rasterized=True,
        label=f"strong 1.333 ms frames ({np.count_nonzero(frame_strong)})",
    )
    analysis = document["rate_analysis"]
    if analysis["status"] == "complete":
        common = analysis["common_slope"]
        for segment_index, segment in enumerate(analysis["segments"]):
            times = np.linspace(segment["start_time_s"], segment["end_time_s"], 24)
            predicted = common["segment_intercepts_hz"][segment_index] + common[
                "shared_slope_hz_s"
            ] * (times - segment["center_time_s"])
            axes[2].plot(
                times,
                predicted - _model_frequency(document, times),
                color=GREEN,
                linewidth=2.0,
                alpha=0.90,
                label="recovered ramp family" if segment_index == 0 else None,
            )
        outcome = (
            f"{analysis['coherent_segment_count']} ramps · corrected rate "
            f"{common['shared_slope_hz_s'] / 1_000:.3f} kHz/s"
        )
    else:
        outcome = "no ≥20 ms / ≤40 Hz-RMS ramp family"
    titles = (
        "A · 20 ms source-alias GLRT acquisition",
        "B · Persisted constant-CFO GLRT windows",
        f"C · Raw-IQ frame CFO and batch-recovered ramps · {outcome}",
    )
    axes[0].set_ylabel("normalized score")
    for axis in axes[1:]:
        axis.axhline(0.0, color=INK, linewidth=0.8, alpha=0.60)
        axis.set_ylabel("CFO − frozen GLRT line (Hz)")
        axis.set_ylim(-residual_limit, residual_limit)
    for axis, title in zip(axes, titles, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0].legend(loc="lower left", ncol=3, frameon=False)
    axes[1].legend(loc="lower left", frameon=False)
    axes[2].legend(loc="lower left", ncol=3, frameon=False)
    axes[-1].set_xlabel("capture time (s)")
    axes[-1].set_xlim(
        float(document["spec"]["branch_start_s"]),
        float(document["spec"]["branch_end_s"]),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_rate_summary(path: Path, document: dict[str, Any]) -> None:
    dwells = document["dwells"]
    labels = [item["spec"]["label"].replace(" · ", "\n") for item in dwells]
    glrt = np.asarray([item["spec"]["branch_coefficients_hz"][0] / 1_000 for item in dwells])
    corrected = np.asarray(
        [
            (
                item["rate_analysis"]["common_slope"]["shared_slope_hz_s"] / 1_000
                if item["rate_analysis"]["status"] == "complete"
                else np.nan
            )
            for item in dwells
        ]
    )
    repeatability = np.asarray(
        [
            (
                item["rate_analysis"]["common_slope"]["leave_one_segment_out_rms_hz_s"] / 1_000
                if item["rate_analysis"]["status"] == "complete"
                else np.nan
            )
            for item in dwells
        ]
    )
    fixed_rms = np.asarray(
        [
            (
                item["rate_analysis"]["errors"]["source_glrt_slope"]["odd_validation"]["rms_hz"]
                if item["rate_analysis"]["status"] == "complete"
                else np.nan
            )
            for item in dwells
        ]
    )
    corrected_rms = np.asarray(
        [
            (
                item["rate_analysis"]["errors"]["common_slope"]["odd_validation"]["rms_hz"]
                if item["rate_analysis"]["status"] == "complete"
                else np.nan
            )
            for item in dwells
        ]
    )
    figure = Figure(figsize=(15, 6.5), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Five-dwell source-alias GLRT versus frame-ramp local rates",
        fontsize=19,
        color=INK,
        fontweight="bold",
    )
    positions = np.arange(len(dwells))
    axes[0].scatter(
        positions,
        glrt,
        s=65,
        marker="s",
        color=AMBER,
        label="frozen GLRT rate",
        zorder=3,
    )
    axes[0].errorbar(
        positions,
        corrected,
        yerr=repeatability,
        fmt="o",
        markersize=7,
        color=BLUE,
        ecolor=BLUE,
        elinewidth=1.8,
        capsize=4,
        label="ramp-common rate ± LOO repeatability",
        zorder=4,
    )
    for index, value in enumerate(corrected):
        if np.isfinite(value):
            axes[0].annotate(
                f"{value:.3f}",
                (index, value),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color=INK,
            )
    axes[0].set_xticks(positions, labels)
    axes[0].set_ylabel("absolute CFO rate (kHz/s)")
    axes[0].set_title("A · Rate estimate", loc="left", color=INK, fontweight="bold")
    axes[0].legend(loc="lower left", frameon=False)
    width = 0.34
    axes[1].bar(
        positions - width / 2,
        fixed_rms,
        width,
        color=AMBER,
        alpha=0.78,
        label="force GLRT slope",
    )
    axes[1].bar(
        positions + width / 2,
        corrected_rms,
        width,
        color=BLUE,
        alpha=0.82,
        label="free ramp intercepts + common slope",
    )
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylabel("odd-Qin CFO prediction RMS (Hz)")
    axes[1].set_title(
        "B · Independent odd-symbol validation",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="upper left", frameon=False)
    for axis in axes:
        axis.grid(True, axis="y", alpha=0.17)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_gate_sensitivity(path: Path, document: dict[str, Any]) -> None:
    figure = Figure(figsize=(14, 7), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True)
    figure.suptitle(
        "Qin-gate sensitivity of recovered ramp families",
        fontsize=19,
        color=INK,
        fontweight="bold",
    )
    for color, dwell in zip(DWELL_COLORS, document["dwells"], strict=True):
        rows = dwell["gate_sensitivity"]
        gates = np.asarray([item["exact_gate"] for item in rows])
        rates = np.asarray(
            [
                (
                    item["common_slope_hz_s"] / 1_000
                    if item["common_slope_hz_s"] is not None
                    else np.nan
                )
                for item in rows
            ]
        )
        segments = np.asarray([item["coherent_segment_count"] for item in rows])
        label = dwell["spec"]["label"]
        axes[0].plot(gates, rates, marker="o", color=color, label=label)
        axes[1].plot(gates, segments, marker="o", color=color, label=label)
    axes[0].set_ylabel("common ramp rate (kHz/s)")
    axes[0].set_title(
        "A · Rate should remain stable once a real family is isolated",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].set_ylabel("coherent ramp count")
    axes[1].set_xlabel("minimum normalized even-Qin frame score")
    axes[1].set_title(
        "B · Availability versus frame-quality gate",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[0].legend(loc="best", ncol=3, frameon=False)
    for axis in axes:
        axis.grid(True, alpha=0.17)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_all(document: dict[str, Any], output_root: Path) -> dict[str, Any]:
    dwell_figures = {}
    for dwell in document["dwells"]:
        short_id = dwell["session_id"].split("-")[-1][:8]
        path = output_root / f"{short_id}-multiscale-evidence.png"
        render_dwell(path, dwell)
        dwell_figures[short_id] = str(path)
    rate_summary = output_root / "five-dwell-rate-and-validation.png"
    gate_sensitivity = output_root / "five-dwell-gate-sensitivity.png"
    render_rate_summary(rate_summary, document)
    render_gate_sensitivity(gate_sensitivity, document)
    return {
        "per_dwell": dwell_figures,
        "rate_and_validation": str(rate_summary),
        "gate_sensitivity": str(gate_sensitivity),
    }


def _assessment(dwell: dict[str, Any]) -> str:
    analysis = dwell["rate_analysis"]
    if analysis["status"] != "complete":
        return "No validated ramp family"
    glrt = float(analysis["source_glrt_rate_hz_s"])
    corrected = float(analysis["common_slope"]["shared_slope_hz_s"])
    repeatability = float(analysis["common_slope"]["leave_one_segment_out_rms_hz_s"])
    reduction = 1.0 - (
        analysis["errors"]["common_slope"]["odd_validation"]["rms_hz"]
        / analysis["errors"]["source_glrt_slope"]["odd_validation"]["rms_hz"]
    )
    if abs(corrected - glrt) < 300.0:
        return "GLRT and local rate agree"
    if repeatability > 800.0:
        return "Reset-biased; large ramp scatter"
    if reduction > 0.20:
        return "GLRT is reset-biased"
    return "Rate differs; validation gain is weak"


def write_report(document: dict[str, Any], report_path: Path, result_path: Path) -> None:
    def relative(path: str | Path) -> str:
        return Path(os.path.relpath(Path(path), report_path.parent)).as_posix()

    summary_figure = relative(document["figures"]["rate_and_validation"])
    gate_figure = relative(document["figures"]["gate_sensitivity"])
    result_relative = relative(result_path)
    table_header = (
        "| dwell | strong GLRT | strong frames | ramps | GLRT rate (kHz/s) | "
        "local rate ± LOO RMS (kHz/s) | odd RMS, GLRT→local (Hz) | assessment |"
    )
    table_rows = []
    sections = []
    for dwell in document["dwells"]:
        summary = dwell["summary"]
        analysis = dwell["rate_analysis"]
        label = dwell["spec"]["label"]
        short_id = dwell["session_id"].split("-")[-1][:8]
        glrt = float(dwell["spec"]["branch_coefficients_hz"][0]) / 1_000
        if analysis["status"] == "complete":
            common = analysis["common_slope"]
            corrected = common["shared_slope_hz_s"] / 1_000
            repeatability = common["leave_one_segment_out_rms_hz_s"] / 1_000
            ramps = analysis["coherent_segment_count"]
            fixed_rms = analysis["errors"]["source_glrt_slope"]["odd_validation"]["rms_hz"]
            corrected_rms = analysis["errors"]["common_slope"]["odd_validation"]["rms_hz"]
            rate_cell = f"{corrected:.3f} ± {repeatability:.3f}"
            validation_cell = f"{fixed_rms:.1f} → {corrected_rms:.1f}"
            details = f"""
The strict frame gate recovers {ramps} coherent ramps containing
{analysis["coherent_frame_count"]} frames. The common within-ramp rate is
**{corrected:.4f} kHz/s**, compared with the frozen GLRT rate of
{glrt:.4f} kHz/s. Leave-one-ramp-out repeatability is
{repeatability:.4f} kHz/s; odd-Qin CFO RMS changes from {fixed_rms:.2f} to
{corrected_rms:.2f} Hz.
"""
        else:
            ramps = analysis.get("coherent_segment_count", 0)
            rate_cell = "—"
            validation_cell = "—"
            details = f"""
No ramp family passes the ≥{1_000 * rate_tool.MINIMUM_COHERENT_SPAN_S:.0f} ms,
≤{rate_tool.MAXIMUM_COHERENT_RMS_HZ:.0f} Hz-RMS coherence gate at the primary
frame threshold. This dwell remains unresolved; no local-rate point estimate is
forced.
"""
        table_rows.append(
            "| "
            f"{label} | {summary['strong_glrt_window_count']}/{summary['window_count']} | "
            f"{summary['strong_frame_count']}/{summary['frame_count']} | {ramps} | "
            f"{glrt:.3f} | {rate_cell} | {validation_cell} | {_assessment(dwell)} |"
        )
        image = relative(document["figures"]["per_dwell"][short_id])
        sections.append(
            f"""## {label} — `{dwell["session_id"]}`

![{label} multiscale evidence]({image})

{details.strip()}

Frame evidence source: {dwell["frame_source"]}.
"""
        )
    text = f"""# Five-dwell multiscale local-rate prototype

## Abstract

This prototype applies one consistent three-scale pipeline to five sealed
historical Starlink dwells: source-alias 20 ms GLRT acquisition, independent
1.333 ms even-Qin frame CFO fitting with odd-Qin validation, and batch recovery
of 20–125 ms continuous ramps followed by a free-intercept common-slope fit.
The 20 ms CFO values locate the signal and timing lattice but do not define the
reported local rate.

The experiment corrects a prior D2/D4 failure mode: a canonical CFO alias was
used as a raw-IQ acquisition alias, which selected different timing candidates.
Here every dwell is tied to the source trajectory alias and its associated GLRT
timing epoch before frame analysis.

## Cross-dwell result

![Five-dwell rate and validation summary]({summary_figure})

{table_header}
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(table_rows)}

The error comparison is paired: both slopes are evaluated on the same recovered
ramps with one free CFO intercept per ramp. Even Qin symbols fit the model and
odd Qin symbols provide the independent within-frame validation view.

## Pipeline

1. Read the previously selected source trajectory alias and its original
   absolute-CFO line.
2. At every 20 ms detection, bind the nearest source-alias GLRT candidate to its
   own timing epoch; do not substitute the canonical/dealiased alias.
3. Recompute an even-Qin residual-CFO likelihood for every complete 1.333 ms
   frame and retain the maximizing CFO, exact strength, and rolled-control
   margin. The odd Qin symbols independently maximize the validation CFO.
4. Require normalized even-Qin strength ≥ {FRAME_GATE:.2f} and positive
   exact-minus-control margin.
5. Robustly fit each timing lock and globally partition consecutive locks into
   continuous ramps. A retained ramp must span at least
   {1_000 * rate_tool.MINIMUM_COHERENT_SPAN_S:.0f} ms and fit within
   {rate_tool.MAXIMUM_COHERENT_RMS_HZ:.0f} Hz raw RMS.
6. Fit one free CFO intercept per ramp plus a shared absolute-CFO slope. Report
   formal conditional error, leave-one-ramp-out repeatability, gate sensitivity,
   and odd-symbol prediction error.

## Qin-gate sensitivity

![Qin gate sensitivity]({gate_figure})

The permissive 0.02 threshold from the first prototype is intentionally absent:
maximizing hundreds of CFO cells lets noise maxima pass it. The plotted
0.05–0.30 sweep tests whether a rate appears only at one hand-picked threshold.
A credible dwell should settle to a stable rate as weak frames are removed.

{chr(10).join(sections)}

## Interpretation limits

The fitted slope is an emitter-state-debiased **received-CFO rate**, not yet a
satellite-only Doppler truth value. Free ramp intercepts remove constant carrier
assignments and discrete retunes, but LNB/receiver drift and any continuous
transmitter drift remain. TLE association must therefore compare these rates
while carrying a receiver-drift nuisance term or a simultaneous reference.

The current prototype maximizes each frame likelihood before segmentation. A
next iteration should optimize the full per-frame likelihood jointly over ramp
intercepts, change points, and common slope; this result is the point-estimate
baseline against which that joint-likelihood version should be tested.

## Reproduction

```bash
uv run python tools/report_five_dwell_multiscale_local_rates.py \\
  --reuse-results {result_path.as_posix()}
```

Machine-readable frames, selected windows, ramp fits, sensitivity sweeps, and
validation metrics are in [{result_path.name}]({result_relative}).
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    if arguments.reuse_results is None:
        document = analyze_all(
            bulk_root=arguments.bulk_root,
            source_results_path=arguments.source_results,
            old_results_path=arguments.old_results,
            d2_results_path=arguments.d2_results,
            refresh_all=arguments.refresh_all,
        )
    else:
        document = _load(arguments.reuse_results)
        if len(document.get("dwells", ())) != 5:
            raise ValueError("reused result must contain exactly five dwells")
    document["figures"] = render_all(document, arguments.output_root)
    result_path = arguments.output_root / DEFAULT_RESULT.name
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(stable_measurement_floats(document), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(document, arguments.report_path, result_path)
    summary = []
    for dwell in document["dwells"]:
        analysis = dwell["rate_analysis"]
        summary.append(
            {
                "dwell": dwell["spec"]["label"],
                "glrt_rate_hz_s": dwell["spec"]["branch_coefficients_hz"][0],
                "local_rate_hz_s": (
                    analysis["common_slope"]["shared_slope_hz_s"]
                    if analysis["status"] == "complete"
                    else None
                ),
                "coherent_segment_count": analysis.get("coherent_segment_count", 0),
            }
        )
    print(
        json.dumps(
            {
                "summary": summary,
                "figures": document["figures"],
                "report": str(arguments.report_path),
                "result": str(result_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
