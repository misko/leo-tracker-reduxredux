#!/usr/bin/env python3
"""Evaluate the modulo-pi pilot PNT Kalman tracker on verified recorded IQ."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam import (
    PilotPhaseDopplerTrackingResult,
    PilotPntKalmanConfig,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_phase_doppler_tracking,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.robust_linear import HuberLinearFit, fit_huber_linear_irls
from leo.analysis.starlink import CONTROL_SYMBOL_ROLL, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

OUTPUT_ROOT = Path("reports/figures/2026_08_22_pilot_pnt_kalman")
PRIMARY_SESSION = "cap-20260821T140820-470384cc9284"
PRIMARY_RUN = "capture-438ad263e01048ef82f660975ec55a08"
PRIMARY_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
HOLDOUT_SESSION = "cap-20260822T143411-4e2a0c111a30"
HOLDOUT_RUN = "reprocess-a3fc4c77b1234b58ab5f7292b23db161"
HOLDOUT_SCOPE = "sha256:d7412c34fc4f03bbe33b2818b87aa0e902893daf9be899e9e01585a404122ba0"
WINDOW_S = 0.100


@dataclass(frozen=True, slots=True)
class Case:
    label: str
    role: str
    session_id: str
    run_id: str
    scope_key: str
    stream: str
    receiver: int
    edge: StarlinkEdge
    detection_time_s: float
    sample_start: int
    local_epoch_sample: int
    candidate_rank: int
    initial_cfo_hz: float
    qam_accuracy: float | None
    glrt_margin: float
    standard_degree_one_rate_hz_s: float | None


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: Case
    modulo_pi: PilotPntKalmanResult
    ordinary: PilotPhaseDopplerTrackingResult
    rolled: PilotPntKalmanResult
    measured_frequency_line: HuberLinearFit
    modulo_supported_innovation_rms_rad: float
    modulo_accepted_innovation_rms_rad: float
    ordinary_innovation_rms_rad: float
    modulo_phase_acceptance: float
    ordinary_phase_acceptance: float
    final_rate_error_vs_measured_line_hz_s: float
    final_rate_error_vs_standard_hz_s: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--holdout-count", type=int, default=8)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _scientific_root(bulk_root: Path, case: Case) -> Path:
    return (
        bulk_root
        / "analysis"
        / case.session_id
        / case.run_id
        / "scientific"
        / "path-standard"
        / case.scope_key
    )


def _glrt(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate must contain exactly one GLRT64 score")
    return matches[0]


def _standard_rate(
    final_bank: dict[str, Any],
    *,
    time_s: float,
    cfo_hz: float,
) -> float | None:
    eligible: list[tuple[float, float]] = []
    for track in final_bank.get("trajectories", []):
        coefficients = tuple(float(value) for value in track["absolute_coefficients_hz"])
        if len(coefficients) != 2:
            continue
        if not float(track["start_s"]) <= time_s <= float(track["end_s"]):
            continue
        predicted = float(np.polyval(coefficients, time_s - float(track["reference_time_s"])))
        eligible.append((abs(predicted - cfo_hz), coefficients[0]))
    return None if not eligible else min(eligible)[1]


def _primary_case(bulk_root: Path) -> Case:
    provisional = Case(
        label="P0",
        role="post-hoc mechanism case",
        session_id=PRIMARY_SESSION,
        run_id=PRIMARY_RUN,
        scope_key=PRIMARY_SCOPE,
        stream="stream-0",
        receiver=0,
        edge=StarlinkEdge.UPPER,
        detection_time_s=34.725,
        sample_start=0,
        local_epoch_sample=0,
        candidate_rank=6,
        initial_cfo_hz=0.0,
        qam_accuracy=None,
        glrt_margin=0.0,
        standard_degree_one_rate_hz_s=None,
    )
    scan = _read_json(_scientific_root(bulk_root, provisional) / "standard.pilot-scan.v3.json")
    detection = next(item for item in scan["detections"] if float(item["time_s"]) == 34.725)
    candidate = next(item for item in detection["candidates"] if int(item["rank"]) == 6)
    glrt = _glrt(candidate)
    return Case(
        label="P0",
        role="post-hoc mechanism case",
        session_id=PRIMARY_SESSION,
        run_id=PRIMARY_RUN,
        scope_key=PRIMARY_SCOPE,
        stream="stream-0",
        receiver=0,
        edge=StarlinkEdge.UPPER,
        detection_time_s=float(detection["time_s"]),
        sample_start=int(detection["sample_start"]),
        local_epoch_sample=int(candidate["local_epoch_sample"]),
        candidate_rank=int(candidate["rank"]),
        initial_cfo_hz=float(glrt["tracking_cfo_hz"]),
        qam_accuracy=(
            None if candidate.get("qam_accuracy") is None else float(candidate["qam_accuracy"])
        ),
        glrt_margin=float(glrt["margin"]),
        standard_degree_one_rate_hz_s=None,
    )


def _holdout_cases(bulk_root: Path, count: int) -> tuple[Case, ...]:
    if count < 1:
        raise ValueError("holdout count must be positive")
    provisional = Case(
        label="H0",
        role="manifest-verified later-dwell holdout",
        session_id=HOLDOUT_SESSION,
        run_id=HOLDOUT_RUN,
        scope_key=HOLDOUT_SCOPE,
        stream="stream-0",
        receiver=1,
        edge=StarlinkEdge.LOWER,
        detection_time_s=0.0,
        sample_start=0,
        local_epoch_sample=0,
        candidate_rank=0,
        initial_cfo_hz=0.0,
        qam_accuracy=None,
        glrt_margin=0.0,
        standard_degree_one_rate_hz_s=None,
    )
    root = _scientific_root(bulk_root, provisional)
    scan = _read_json(root / "standard.pilot-scan.v3.json")
    final_bank = _read_json(root / "standard.final-trajectory-bank.v3.json")
    pool: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            accuracy = candidate.get("qam_accuracy")
            if accuracy is None:
                continue
            glrt = _glrt(candidate)
            if float(glrt["margin"]) < 0.05:
                continue
            pool.append((float(accuracy), detection, candidate, glrt))
    pool.sort(
        key=lambda item: (
            -item[0],
            float(item[1]["time_s"]),
            int(item[2]["rank"]),
        )
    )
    selected: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for item in pool:
        time_s = float(item[1]["time_s"])
        if all(abs(time_s - float(other[1]["time_s"])) >= 0.15 for other in selected):
            selected.append(item)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f"only {len(selected)} separated holdout windows were available")
    cases = []
    for index, (accuracy, detection, candidate, glrt) in enumerate(selected, start=1):
        time_s = float(detection["time_s"])
        cfo_hz = float(glrt["tracking_cfo_hz"])
        cases.append(
            Case(
                label=f"H{index}",
                role="manifest-verified later-dwell holdout",
                session_id=HOLDOUT_SESSION,
                run_id=HOLDOUT_RUN,
                scope_key=HOLDOUT_SCOPE,
                stream="stream-0",
                receiver=1,
                edge=StarlinkEdge.LOWER,
                detection_time_s=time_s,
                sample_start=int(detection["sample_start"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                candidate_rank=int(candidate["rank"]),
                initial_cfo_hz=cfo_hz,
                qam_accuracy=accuracy,
                glrt_margin=float(glrt["margin"]),
                standard_degree_one_rate_hz_s=_standard_rate(
                    final_bank,
                    time_s=time_s,
                    cfo_hz=cfo_hz,
                ),
            )
        )
    return tuple(cases)


def _complex_receiver(raw: np.ndarray) -> np.ndarray:
    if raw.ndim != 3 or raw.shape[2] != 2 or raw.shape[1] != 1:
        raise ValueError(f"unexpected IQ shape: {raw.shape}")
    return raw[:, 0, 0].astype(float) + 1j * raw[:, 0, 1].astype(float)


def _measured_line(result: PilotPntKalmanResult) -> HuberLinearFit:
    supported = [frame for frame in result.frames if frame.measurement_supported]
    if len(supported) < 3:
        raise ValueError("pilot Kalman case has fewer than three supported CFO measurements")
    time_s = np.asarray([frame.time_s for frame in supported])
    values_hz = np.asarray([frame.absolute_cfo_measurement_hz for frame in supported])
    reference = float(np.mean(time_s))
    initial = np.polyfit(time_s - reference, values_hz, 1)
    return fit_huber_linear_irls(
        time_s,
        values_hz,
        initial_coefficients_hz=(float(initial[0]), float(initial[1])),
        reference_time_s=reference,
        scale_floor_hz=5.0,
    )


def _rms(values: list[float]) -> float:
    return math.nan if not values else float(math.sqrt(np.mean(np.square(values))))


def _analyze_case(reader, case: Case) -> CaseResult:
    sample_count = round(WINDOW_S * reader.sample_rate_hz)
    raw = reader.read(case.sample_start, sample_count, receiver_ids=(case.receiver,))
    iq = _complex_receiver(raw)
    common = {
        "epoch_sample": case.local_epoch_sample,
        "initial_absolute_cfo_hz": case.initial_cfo_hz,
        "edge": case.edge,
    }
    modulo = analyze_contiguous_pilot_pnt_kalman(
        iq,
        reader.sample_rate_hz,
        **common,
    )
    ordinary = analyze_contiguous_pilot_phase_doppler_tracking(
        iq,
        reader.sample_rate_hz,
        **common,
    )
    rolled = analyze_contiguous_pilot_pnt_kalman(
        iq,
        reader.sample_rate_hz,
        expected_symbol_roll=CONTROL_SYMBOL_ROLL,
        **common,
    )
    line = _measured_line(modulo)
    supported = [frame for frame in modulo.frames if frame.measurement_supported]
    accepted = [frame for frame in supported if frame.phase_update_applied]
    ordinary_supported = [
        frame
        for frame in ordinary.frames
        if frame.exact_coherence >= 0.02 and frame.coherence_margin >= 0
    ]
    final_rate = modulo.frames[-1].tracked_doppler_rate_hz_s
    return CaseResult(
        case=case,
        modulo_pi=modulo,
        ordinary=ordinary,
        rolled=rolled,
        measured_frequency_line=line,
        modulo_supported_innovation_rms_rad=_rms(
            [frame.phase_innovation_modulo_pi_rad for frame in supported]
        ),
        modulo_accepted_innovation_rms_rad=_rms(
            [frame.phase_innovation_modulo_pi_rad for frame in accepted]
        ),
        ordinary_innovation_rms_rad=_rms(
            [frame.phase_innovation_rad for frame in ordinary_supported]
        ),
        modulo_phase_acceptance=len(accepted) / len(supported),
        ordinary_phase_acceptance=(
            ordinary.phase_update_count / len(ordinary_supported) if ordinary_supported else 0.0
        ),
        final_rate_error_vs_measured_line_hz_s=final_rate - line.slope_hz_per_s,
        final_rate_error_vs_standard_hz_s=(
            None
            if case.standard_degree_one_rate_hz_s is None
            else final_rate - case.standard_degree_one_rate_hz_s
        ),
    )


def _serialize_result(result: CaseResult) -> dict[str, Any]:
    case = asdict(result.case)
    case["edge"] = result.case.edge.value
    line = asdict(result.measured_frequency_line)
    modulo = result.modulo_pi
    ordinary = result.ordinary
    rolled = result.rolled
    return {
        "case": case,
        "degree_one_measured_frequency_line": line,
        "modulo_pi": {
            "frame_count": len(modulo.frames),
            "supported_frame_count": modulo.supported_frame_count,
            "phase_update_count": modulo.phase_update_count,
            "frequency_update_count": modulo.frequency_update_count,
            "timing_update_count": modulo.timing_update_count,
            "reacquisition_count": modulo.reacquisition_count,
            "rate_bootstrap_frame_index": modulo.rate_bootstrap_frame_index,
            "phase_lock_qualified": modulo.phase_lock_qualified,
            "phase_lock_reason": modulo.phase_lock_reason,
            "ambiguity_transition_count": modulo.phase_ambiguity_transition_count,
            "supported_innovation_rms_rad": result.modulo_supported_innovation_rms_rad,
            "accepted_innovation_rms_rad": result.modulo_accepted_innovation_rms_rad,
            "phase_acceptance": result.modulo_phase_acceptance,
            "final_doppler_rate_hz_s": modulo.frames[-1].tracked_doppler_rate_hz_s,
            "final_rate_sigma_hz_s": modulo.frames[-1].doppler_rate_sigma_hz_s,
            "final_timing_rate_s_s": modulo.frames[-1].tracked_timing_rate_s_s,
        },
        "ordinary_2pi": {
            "frame_count": len(ordinary.frames),
            "phase_update_count": ordinary.phase_update_count,
            "frequency_update_count": ordinary.frequency_update_count,
            "phase_reset_count": ordinary.phase_reset_count,
            "innovation_rms_rad": result.ordinary_innovation_rms_rad,
            "phase_acceptance": result.ordinary_phase_acceptance,
            "final_doppler_rate_hz_s": ordinary.frames[-1].tracked_doppler_rate_hz_s,
        },
        "rolled_control": {
            "status": rolled.status.value,
            "frame_count": len(rolled.frames),
            "supported_frame_count": rolled.supported_frame_count,
        },
        "rate_comparison": {
            "kalman_minus_measured_degree_one_hz_s": (
                result.final_rate_error_vs_measured_line_hz_s
            ),
            "kalman_minus_standard_degree_one_hz_s": (result.final_rate_error_vs_standard_hz_s),
        },
        "frames": [
            {
                "time_s": frame.time_s,
                "exact_coherence": frame.exact_coherence,
                "control_coherence": frame.control_coherence,
                "measurement_supported": frame.measurement_supported,
                "phase_innovation_modulo_pi_rad": frame.phase_innovation_modulo_pi_rad,
                "phase_ambiguity_bit": frame.phase_ambiguity_bit,
                "phase_update_applied": frame.phase_update_applied,
                "absolute_cfo_measurement_hz": frame.absolute_cfo_measurement_hz,
                "tracked_absolute_cfo_hz": frame.tracked_absolute_cfo_hz,
                "tracked_doppler_rate_hz_s": frame.tracked_doppler_rate_hz_s,
                "fractional_timing_measurement_samples": (
                    frame.fractional_timing_measurement_samples
                ),
                "tracked_fractional_timing_samples": (frame.tracked_fractional_timing_samples),
            }
            for frame in modulo.frames
        ],
    }


def _plot_primary(result: CaseResult, path: Path) -> None:
    modulo = result.modulo_pi.frames
    ordinary = result.ordinary.frames
    t0 = modulo[0].time_s
    time_ms = np.asarray([(frame.time_s - t0) * 1e3 for frame in modulo])
    supported = np.asarray([frame.measurement_supported for frame in modulo])
    accepted = np.asarray([frame.phase_update_applied for frame in modulo])
    dense_time_s = np.linspace(modulo[0].time_s, modulo[-1].time_s, 400)
    line = result.measured_frequency_line
    line_frequency = line.intercept_at_reference_hz + line.slope_hz_per_s * (
        dense_time_s - line.reference_time_s
    )
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axes = plt.subplots(2, 2, figsize=(15, 9.2), constrained_layout=True)
        cfo_axis, rate_axis, phase_axis, timing_axis = axes.flat
        cfo_axis.scatter(
            time_ms[supported],
            [
                modulo[index].absolute_cfo_measurement_hz / 1e3
                for index in np.flatnonzero(supported)
            ],
            s=15,
            facecolor="none",
            edgecolor="#e28b2d",
            linewidth=0.7,
            label="independent pilot-frame CFO",
        )
        cfo_axis.plot(
            time_ms,
            [frame.tracked_absolute_cfo_hz / 1e3 for frame in modulo],
            color="#247ba0",
            linewidth=1.2,
            label="causal Kalman state",
        )
        cfo_axis.plot(
            (dense_time_s - t0) * 1e3,
            line_frequency / 1e3,
            color="black",
            linewidth=1.0,
            linestyle="--",
            label=f"Huber degree-1: {line.slope_hz_per_s:+.1f} Hz/s",
        )
        cfo_axis.set_title("A · Frequency: measurements, causal state, and one straight line")
        cfo_axis.set_ylabel("baseband CFO (kHz)")
        cfo_axis.legend(fontsize=8)

        rate_axis.plot(
            time_ms,
            [frame.tracked_doppler_rate_hz_s / 1e3 for frame in modulo],
            color="#247ba0",
            linewidth=1.1,
            drawstyle="steps-post",
            label="causal Kalman rate state",
        )
        rate_axis.axhline(
            line.slope_hz_per_s / 1e3,
            color="black",
            linewidth=1.0,
            linestyle="--",
            label="degree-1 measurement slope",
        )
        if result.modulo_pi.rate_bootstrap_frame_index is not None:
            bootstrap = result.modulo_pi.rate_bootstrap_frame_index
            rate_axis.axvline(
                time_ms[bootstrap],
                color="#8d99ae",
                linewidth=0.9,
                linestyle=":",
                label="12-frame robust rate bootstrap",
            )
        rate_axis.set_title("B · Doppler rate state; no order-2/3 frequency model")
        rate_axis.set_ylabel("frequency rate (kHz/s)")
        rate_axis.legend(fontsize=8)

        ordinary_time = np.asarray(
            [(frame.reference_sample / 2_500_000 - t0) * 1e3 for frame in ordinary]
        )
        phase_axis.scatter(
            ordinary_time,
            [frame.phase_innovation_rad for frame in ordinary],
            s=11,
            color="#d95f5f",
            alpha=0.45,
            label="ordinary 2π innovation",
        )
        phase_axis.scatter(
            time_ms[supported],
            [modulo[index].phase_innovation_modulo_pi_rad for index in np.flatnonzero(supported)],
            s=14,
            facecolor="none",
            edgecolor="#2a9d62",
            linewidth=0.7,
            label="modulo-π innovation",
        )
        phase_axis.axhspan(-1.2, 1.2, color="#2a9d62", alpha=0.08)
        phase_axis.axhline(0, color="black", linewidth=0.7)
        phase_axis.set_title("C · The π ambiguity explains the former reset storm")
        phase_axis.set_ylabel("pre-update phase innovation (rad)")
        phase_axis.legend(fontsize=8)

        timing_axis.scatter(
            time_ms[supported],
            [
                modulo[index].fractional_timing_measurement_samples
                for index in np.flatnonzero(supported)
            ],
            s=14,
            facecolor="none",
            edgecolor="#e28b2d",
            linewidth=0.7,
            label="rounding-corrected timing measurement",
        )
        timing_axis.plot(
            time_ms,
            [frame.tracked_fractional_timing_samples for frame in modulo],
            color="#247ba0",
            linewidth=1.1,
            label="timing state",
        )
        bit_indexes = np.flatnonzero(supported & accepted)
        timing_axis.scatter(
            time_ms[bit_indexes],
            [0.32 if modulo[index].phase_ambiguity_bit else 0.24 for index in bit_indexes],
            marker="|",
            s=50,
            color="#7b2cbf",
            label="observed binary π state (two rows)",
        )
        timing_axis.set_title("D · Receiver-relative timing and observed binary state")
        timing_axis.set_ylabel("fractional timing (samples)")
        timing_axis.legend(fontsize=8)
        for axis in axes.flat:
            axis.set_xlabel("time from first analyzed frame (ms)")
        figure.suptitle(
            "Pilot-only five-state Kalman · verified measured IQ · post-hoc mechanism case\n"
            "carrier phase is tracked modulo π; absolute sign is not predicted",
            fontsize=14,
        )
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def _plot_holdouts(results: tuple[CaseResult, ...], path: Path) -> None:
    labels = [item.case.label for item in results]
    positions = np.arange(len(results))
    width = 0.34
    uniform_modulo_pi_rms = math.pi / math.sqrt(12)
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axes = plt.subplots(2, 2, figsize=(15, 9.2), constrained_layout=True)
        acceptance, innovation, rate, control = axes.flat
        acceptance.bar(
            positions - width / 2,
            [item.modulo_phase_acceptance for item in results],
            width,
            color="#2a9d62",
            label="modulo-π",
        )
        acceptance.bar(
            positions + width / 2,
            [item.ordinary_phase_acceptance for item in results],
            width,
            color="#d95f5f",
            label="ordinary 2π",
        )
        acceptance.set_title("A · Phase-update fraction among supported pilot frames")
        acceptance.set_ylabel("fraction")
        acceptance.set_ylim(0, 1.05)
        acceptance.legend()

        innovation.bar(
            positions,
            [item.modulo_supported_innovation_rms_rad for item in results],
            color=[
                "#2a9d62" if item.modulo_pi.phase_lock_qualified else "#8d99ae" for item in results
            ],
        )
        innovation.axhline(
            0.5,
            color="#2a9d62",
            linestyle=":",
            linewidth=1.0,
            label="declared lock threshold",
        )
        innovation.axhline(
            uniform_modulo_pi_rms,
            color="black",
            linestyle="--",
            linewidth=1.0,
            label="uniform modulo-π RMS",
        )
        innovation.set_title("B · Pre-update modulo-π innovation RMS")
        innovation.set_ylabel("radians")
        innovation.legend()

        rate.scatter(
            positions,
            [item.measured_frequency_line.slope_hz_per_s / 1e3 for item in results],
            s=48,
            facecolor="none",
            edgecolor="#e28b2d",
            label="independent frame-CFO degree-1 line",
        )
        qualified = np.asarray([item.modulo_pi.phase_lock_qualified for item in results])
        rate.scatter(
            positions[qualified],
            [
                item.modulo_pi.frames[-1].tracked_doppler_rate_hz_s / 1e3
                for item in results
                if item.modulo_pi.phase_lock_qualified
            ],
            s=34,
            color="#247ba0",
            label="final Kalman rate: qualified phase lock",
        )
        rate.scatter(
            positions[~qualified],
            [
                item.modulo_pi.frames[-1].tracked_doppler_rate_hz_s / 1e3
                for item in results
                if not item.modulo_pi.phase_lock_qualified
            ],
            s=42,
            marker="x",
            color="#8d99ae",
            label="unqualified state: do not interpret",
        )
        rate.scatter(
            positions,
            [
                item.case.standard_degree_one_rate_hz_s / 1e3
                if item.case.standard_degree_one_rate_hz_s is not None
                else np.nan
                for item in results
            ],
            s=42,
            marker="x",
            color="black",
            label="nearest sealed Standard degree-1 track (not an ID)",
        )
        rate.set_title("C · Only qualified locks yield an interpretable Kalman rate")
        rate.set_ylabel("frequency rate (kHz/s)")
        rate.legend(fontsize=8)

        control.bar(
            positions - width / 2,
            [item.modulo_pi.supported_frame_count for item in results],
            width,
            color="#2a9d62",
            label="exact Qin pilot",
        )
        control.bar(
            positions + width / 2,
            [item.rolled.supported_frame_count for item in results],
            width,
            color="#8d99ae",
            label="17-symbol-rolled control",
        )
        control.set_title("D · Exact pilot support versus matched rolled control")
        control.set_ylabel("supported frames / 100 ms")
        control.legend()
        for axis in axes.flat:
            axis.set_xticks(positions, labels)
            axis.set_xlabel("later sealed-dwell holdout window")
        figure.suptitle(
            "Predeclared holdout selection: top persisted QAM windows, separated by ≥150 ms\n"
            "cap-20260822T143411-4e2a0c111a30 · stream-0/RX1",
            fontsize=14,
        )
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def main() -> int:
    args = _arguments()
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)
    cases = (_primary_case(args.bulk_root), *_holdout_cases(args.bulk_root, args.holdout_count))
    by_session: dict[str, list[Case]] = {}
    for case in cases:
        by_session.setdefault(case.session_id, []).append(case)
    results: list[CaseResult] = []
    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        for session_id, session_cases in by_session.items():
            bundle = store.inspect(session_id)
            readers = {
                case.stream: store.reader(bundle, case.stream, verify=True)
                for case in session_cases
            }
            results.extend(_analyze_case(readers[case.stream], case) for case in session_cases)
    finally:
        store.close()
    results.sort(key=lambda item: (item.case.label != "P0", item.case.label))
    primary = next(item for item in results if item.case.label == "P0")
    holdouts = tuple(item for item in results if item.case.label != "P0")
    primary_path = output / "pilot-pnt-kalman-primary.png"
    holdout_path = output / "pilot-pnt-kalman-holdouts.png"
    _plot_primary(primary, primary_path)
    _plot_holdouts(holdouts, holdout_path)
    document = {
        "schema_version": 1,
        "algorithm": "pilot-pnt-kalman-modulo-pi-v1",
        "candidate_only": True,
        "known_pilots_only": True,
        "absolute_carrier_phase_resolved": False,
        "pseudorange_claimed": False,
        "frequency_trajectory_orders": [1],
        "analysis_config": asdict(PilotPntKalmanConfig()),
        "window_s": WINDOW_S,
        "selection": {
            "primary": "frozen post-hoc 34.725 s mechanism case from the prior modulo-pi audit",
            "holdout": (
                "top persisted QAM candidates in the later sealed dwell, GLRT margin >= 0.05, "
                "greedily separated by at least 150 ms; no phase-continuity metric used"
            ),
        },
        "integrity": {
            PRIMARY_SESSION: {
                "recording_manifest_digest": (
                    "sha256:d45409ea3620eccb705eac024a4d814b5c2779f13bcee974311c9f09477adb75"
                ),
                "analysis_run": PRIMARY_RUN,
                "verified_reader": True,
            },
            HOLDOUT_SESSION: {
                "recording_manifest_digest": (
                    "sha256:fffd89c8e2afa0d33dc8b5bc3b1f19c13f3dc2f28d2b0e242f498c72ff3325ab"
                ),
                "analysis_run": HOLDOUT_RUN,
                "verified_reader": True,
            },
        },
        "current_baseline_reproduction": {
            "standard_kalman_product_content_digest": (
                "sha256:8bf7e7a962255af43f12a64a119b4aa39f023a994608771f2582a8c6bc35cfa4"
            ),
            "standard_kalman_processed_frames": 10_944,
            "edge_pilot_offline_quality_frames": 60,
            "edge_pilot_offline_frequency_fit_rms_hz": 17.799514022398373,
            "edge_pilot_offline_modulo_pi_phase_rms_rad": 0.15130571755250766,
        },
        "cases": [_serialize_result(item) for item in results],
        "figures": [primary_path.name, holdout_path.name],
    }
    (output / "pilot-pnt-kalman-results.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_root": str(output),
                "primary_supported": primary.modulo_pi.supported_frame_count,
                "primary_phase_updates": primary.modulo_pi.phase_update_count,
                "primary_modulo_pi_rms_rad": primary.modulo_supported_innovation_rms_rad,
                "holdout_count": len(holdouts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
