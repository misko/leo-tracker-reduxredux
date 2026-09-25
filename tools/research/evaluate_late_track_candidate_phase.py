"""Evaluate pilot phase advances against frozen TLE candidates on five late tracks.

The source/track/TLE banks are inherited from a phase-blind frozen selection.
Whole visits receive a seeded random train/held assignment. Candidate and
frequency-bias selection use even-symbol phase on training visits; odd-symbol
phase on held visits is the untouched primary response.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.persistent_hop_trajectory import (  # noqa: E402
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.qam.pilot import estimate_edge_pilot_frame_complex_split  # noqa: E402
from leo.analysis.research.candidate_phase_validation import (  # noqa: E402
    CandidatePhaseEvidence,
    score_candidate_integrated_phase,
    seeded_group_split,
)
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S  # noqa: E402
from leo.application.scanner_trajectory import project_scanner_candidates  # noqa: E402
from leo.contracts.sky import ObserverSiteV1  # noqa: E402
from leo.sky.doppler import doppler_shift_hz  # noqa: E402
from leo.sky.frames import (  # noqa: E402
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import (  # noqa: E402
    find_element_set_record,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid  # noqa: E402
from leo.sky.screening import observe_grid  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import (  # noqa: E402
    AdaptiveHopAnalysisInputStore,
)
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = (
    ROOT / "reports/figures/2026_09_24_late_dual_rx_track_phase/selection.json"
)
DEFAULT_OUTPUT = ROOT / "reports/figures/2026_09_24_phase_satellite_association"
DEFAULT_PHASE_ROOT = ROOT / "reports/figures/2026_09_24_dual_capture_phase_random/rows"
SPLIT_SEED = 2_026_092_420
SENSITIVITY_SEED_BASE = 2_026_092_500
SENSITIVITY_SPLIT_COUNT = 32
BIAS_PERIOD_HZ = 375.0
MINIMUM_IDENTIFIABLE_CONTRAST_RAD = 0.10
SPEED_OF_LIGHT_M_S = 299_792_458.0
MECHANICAL_BASELINE_M = 0.08
NOMINAL_BASELINE_AZIMUTH_DEG = 79
CHANNEL_COLOURS = {
    1: "#0072B2",
    2: "#E69F00",
    3: "#009E73",
    4: "#CC79A7",
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def serial(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return [value.real, value.imag]
    return value


def wrap_pi(value: np.ndarray) -> np.ndarray:
    return (np.asarray(value) + np.pi / 2) % np.pi - np.pi / 2


def fit_baseline_orientation(
    measured_hz: np.ndarray,
    candidate_predictions_hz: np.ndarray,
    training_indices: np.ndarray,
    held_indices: np.ndarray,
    catalog_numbers: list[int],
) -> dict[str, Any]:
    """Fit candidate-specific azimuth and CFO intercept on random training visits."""
    models = []
    for catalog, prediction in zip(
        catalog_numbers, candidate_predictions_hz, strict=True
    ):
        offsets = np.mean(
            measured_hz[training_indices, None] - prediction[:, training_indices].T,
            axis=0,
        )
        training_residual = (
            measured_hz[training_indices, None]
            - prediction[:, training_indices].T
            - offsets
        )
        azimuth_index = int(np.argmin(np.mean(training_residual**2, axis=0)))
        held_prediction = prediction[azimuth_index, held_indices] + offsets[azimuth_index]
        held_residual = measured_hz[held_indices] - held_prediction
        held_r = (
            float(np.corrcoef(measured_hz[held_indices], held_prediction)[0, 1])
            if len(held_indices) >= 3
            and np.std(measured_hz[held_indices]) > 0
            and np.std(held_prediction) > 0
            else math.nan
        )
        models.append(
            {
                "catalog_number": catalog,
                "training_fitted_azimuth_deg": azimuth_index,
                "training_fitted_receiver_cfo_hz": float(offsets[azimuth_index]),
                "training_rms_hz": float(
                    np.sqrt(np.mean(training_residual[:, azimuth_index] ** 2))
                ),
                "held_rms_hz": float(np.sqrt(np.mean(held_residual**2))),
                "held_pearson_r": held_r,
            }
        )
    selected = min(models, key=lambda row: row["training_rms_hz"])
    held_best = min(models, key=lambda row: row["held_rms_hz"])
    constant_offset = float(np.mean(measured_hz[training_indices]))
    constant_rms = float(
        np.sqrt(np.mean((measured_hz[held_indices] - constant_offset) ** 2))
    )
    maximum_geometry_span = float(
        np.max(candidate_predictions_hz) - np.min(candidate_predictions_hz)
    )
    observed_standard_deviation = float(np.std(measured_hz))
    return {
        "claim_status": "feasibility-only; electrical baseline orientation not identified",
        "orientation_grid_deg": [0, 359, 1],
        "nominal_axis_hypotheses_deg": [
            NOMINAL_BASELINE_AZIMUTH_DEG,
            NOMINAL_BASELINE_AZIMUTH_DEG + 180,
        ],
        "training_selected_catalog_number": selected["catalog_number"],
        "held_diagnostic_best_catalog_number": held_best["catalog_number"],
        "training_selected_held_rms_hz": selected["held_rms_hz"],
        "training_selected_beats_constant": selected["held_rms_hz"] < constant_rms,
        "constant_control_held_rms_hz": constant_rms,
        "maximum_candidate_geometry_span_hz": maximum_geometry_span,
        "observed_relative_cfo_standard_deviation_hz": observed_standard_deviation,
        "geometry_span_to_observed_standard_deviation_ratio": (
            maximum_geometry_span / observed_standard_deviation
        ),
        "models": models,
    }


def glrt_timeline_rows(source: Any) -> list[dict[str, Any]]:
    """Flatten every published fractional GLRT candidate onto the scan clock."""
    if source.timing is None:
        raise ValueError("GLRT timeline requires qualified device-counter timing")
    rows = []
    for probe in source.probes:
        elapsed_s = (
            probe.valid_start_counter
            - source.timing.session_start_device_sample_counter
        ) / source.sample_rate_hz + probe.probe_start_ms / 1000
        for candidate in probe.candidates:
            rows.append(
                {
                    "session_id": source.session_id,
                    "visit_index": probe.visit_index,
                    "receiver_id": probe.receiver_id,
                    "channel": probe.channel,
                    "edge": probe.edge,
                    "time_s": elapsed_s,
                    "candidate_rank": candidate.candidate_rank,
                    "fractional_margin": candidate.fractional_margin,
                    "fractional_tracking_cfo_hz": (
                        candidate.fractional_tracking_cfo_hz
                    ),
                    "passed_fractional_margin_gate": (
                        candidate.passed_fractional_margin_gate
                    ),
                }
            )
    return rows


def selected_track_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse interval evidence to one measured GLRT track point per visit/RX."""
    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["session_id"], row["visit_index"], row["receiver_id"])
        grouped.setdefault(key, []).append(row)
    points = []
    for (session_id, visit_index, receiver_id), members in grouped.items():
        cfo = {
            float(row["source_tracking_dealiased_cfo_hz"]) for row in members
        }
        channels = {int(row["channel"]) for row in members}
        if len(cfo) != 1 or len(channels) != 1:
            raise ValueError("one visit/RX track point has inconsistent source evidence")
        points.append(
            {
                "session_id": session_id,
                "visit_index": visit_index,
                "receiver_id": receiver_id,
                "channel": channels.pop(),
                "scan_elapsed_s": float(
                    np.mean([row["scan_elapsed_s"] for row in members])
                ),
                "tracking_cfo_hz": cfo.pop(),
            }
        )
    return sorted(
        points,
        key=lambda row: (
            row["session_id"],
            row["receiver_id"],
            row["scan_elapsed_s"],
        ),
    )


def frame_opportunities(sample_count: int, rate: int, epoch: int) -> list[tuple[int, int]]:
    """Four adjacent complete frames nearest each phase-blind 20 ms group center."""
    content = round(302 * rate * OFDM_SYMBOL_DURATION_S)
    group_samples = round(rate * 0.02)
    output = []
    for group in range(sample_count // group_samples):
        left, right = group * group_samples, (group + 1) * group_samples
        starts = [epoch + round(offset * rate / 750) for offset in range(-100, 101)]
        starts = [start for start in starts if left <= start - 1 and start + content + 1 <= right]
        if len(starts) < 4:
            raise ValueError("group has fewer than four complete frame opportunities")
        center = (left + right) / 2
        index = min(
            range(len(starts) - 3),
            key=lambda item: abs((starts[item] + starts[item + 3] + content) / 2 - center),
        )
        output.extend((group, start) for start in starts[index : index + 4])
    return output


def equal_group_metrics(
    residual_rad: np.ndarray,
    groups: np.ndarray,
    selected_groups: tuple[int, ...],
    *,
    concentration: float = 4.0,
) -> dict[str, float]:
    """Equal-visit modulo-pi response metrics."""
    phasors, scores, squares = [], [], []
    for group in selected_groups:
        selected = groups == group
        if not np.any(selected):
            raise ValueError("phase group is empty")
        values = residual_rad[selected]
        phasors.append(np.mean(np.exp(2j * values)))
        scores.append(float(np.mean(concentration * np.cos(2 * values))))
        squares.append(float(np.mean(values**2)))
    return {
        "composite_score": float(np.mean(scores)),
        "circular_r_modulo_pi": float(abs(np.mean(phasors))),
        "rms_rad": float(math.sqrt(np.mean(squares))),
    }


def response_metrics(
    measured_rad: np.ndarray,
    predictions_rad: np.ndarray,
    duration_s: np.ndarray,
    groups: np.ndarray,
    selected_groups: tuple[int, ...],
    fitted_bias_hz: np.ndarray,
) -> list[dict[str, float]]:
    output = []
    for prediction, bias in zip(predictions_rad, fitted_bias_hz, strict=True):
        residual = wrap_pi(measured_rad - prediction - 2 * np.pi * bias * duration_s)
        output.append(equal_group_metrics(residual, groups, selected_groups))
    return output


def joint_receiver_result(
    receivers: list[dict[str, Any]], glrt_leader: int
) -> dict[str, Any]:
    """Combine receiver scores with equal receiver weight after separate bias fits."""
    if len(receivers) != 2:
        raise ValueError("joint phase comparison requires exactly two receivers")
    candidate_maps = [
        {
            int(model["catalog_number"]): model
            for model in receiver["models"]
            if model["model_kind"] == "candidate"
        }
        for receiver in receivers
    ]
    common = [catalog for catalog in candidate_maps[0] if catalog in candidate_maps[1]]
    if glrt_leader not in common or len(common) < 2:
        raise ValueError("receiver candidate banks lack a common comparison")
    candidates = []
    for catalog in common:
        models = [candidate_map[catalog] for candidate_map in candidate_maps]
        candidates.append(
            {
                "catalog_number": catalog,
                "receiver_tau_s": [model["selected_tau_s"] for model in models],
                "even_training_composite_score": float(
                    np.mean([model["even_training_composite_score"] for model in models])
                ),
                "odd_held_composite_score": float(
                    np.mean(
                        [model["odd_held_response"]["composite_score"] for model in models]
                    )
                ),
                "odd_held_receiver_r": [
                    model["odd_held_response"]["circular_r_modulo_pi"] for model in models
                ],
                "odd_held_receiver_rms_rad": [
                    model["odd_held_response"]["rms_rad"] for model in models
                ],
            }
        )
    training_winner = int(
        np.argmax([row["even_training_composite_score"] for row in candidates])
    )
    held_winner = int(np.argmax([row["odd_held_composite_score"] for row in candidates]))
    constant_score = float(
        np.mean(
            [
                receiver["models"][-2]["odd_held_response"]["composite_score"]
                for receiver in receivers
            ]
        )
    )
    wrong_time_score = float(
        np.mean(
            [
                receiver["models"][-1]["odd_held_response"]["composite_score"]
                for receiver in receivers
            ]
        )
    )
    selected = candidates[training_winner]
    return {
        "combination": "equal receiver mean after separate train-only frequency biases",
        "candidate_catalog_numbers": common,
        "training_selected_catalog_number": selected["catalog_number"],
        "held_diagnostic_best_catalog_number": candidates[held_winner]["catalog_number"],
        "glrt_leader_selected_on_training": selected["catalog_number"] == glrt_leader,
        "glrt_leader_best_on_held_diagnostic": (
            candidates[held_winner]["catalog_number"] == glrt_leader
        ),
        "training_selected_odd_held_score": selected["odd_held_composite_score"],
        "constant_control_odd_held_score": constant_score,
        "wrong_time_control_odd_held_score": wrong_time_score,
        "training_selected_beats_constant": (
            selected["odd_held_composite_score"] > constant_score
        ),
        "training_selected_beats_wrong_time": (
            selected["odd_held_composite_score"] > wrong_time_score
        ),
        "candidates": candidates,
    }


def _tle_path(tle_root: Path, snapshot: dict[str, Any]) -> Path:
    name = (
        f"{snapshot['collected_utc_ns']}-"
        f"{str(snapshot['digest']).removeprefix('sha256:')}.tle"
    )
    matches = list((tle_root / "archive").rglob(name))
    if len(matches) != 1:
        raise ValueError(f"expected one source TLE snapshot, found {len(matches)}")
    return matches[0]


def _review(manifest: dict[str, Any], tracklet_id: str) -> dict[str, Any]:
    matches = [row for row in manifest["track_reviews"] if row["tracklet_id"] == tracklet_id]
    if len(matches) != 1:
        raise ValueError("exact tracklet lacks one TLE review")
    return matches[0]


def _candidate_catalogue(snapshot_path: Path, candidates: list[dict[str, Any]]):
    text = snapshot_path.read_text(encoding="ascii")
    records = []
    for candidate in candidates:
        record = find_element_set_record(text, int(candidate["catalog_number"]))
        if record is None:
            raise ValueError("review candidate is absent from source TLE snapshot")
        records.append(record)
    return parse_element_sets("".join(record.text for record in records))


def _prediction_bank(
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    catalogue,
    observer: ObserverSiteV1,
    rf_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    midpoint = np.asarray([int(row["midpoint_utc_ns"]) for row in rows], dtype=np.int64)
    duration = np.asarray([float(row["duration_s"]) for row in rows])
    predictions, wrong_predictions = [], []
    mirror_sum = int(midpoint.min()) + int(midpoint.max())
    for index, candidate in enumerate(candidates):
        tau_ns = round(float(candidate["selected_tau_s"]) * 1e9)
        for target, times in (
            (predictions, midpoint + tau_ns),
            (wrong_predictions, mirror_sum - midpoint + tau_ns),
        ):
            grid = SamplingGrid(tuple(map(int, times)), len(times) // 2, 1.0)
            propagated = propagate_grid(catalogue, grid, [index])
            observed = observe_grid(propagated, observer, grid)
            if not bool(observed.usable[0]):
                raise ValueError("candidate propagation failed")
            shift = doppler_shift_hz(rf_hz, observed.range_rate_km_s[0])
            target.append(2 * np.pi * shift * duration)
    return np.asarray(predictions), np.asarray(wrong_predictions)


def _baseline_prediction_bank(
    times_utc_ns: np.ndarray,
    candidates: list[dict[str, Any]],
    catalogue,
    observer: ObserverSiteV1,
    rf_hz: float,
) -> np.ndarray:
    """Return differential CFO for every candidate, azimuth, and visit."""
    observer_ecef = geodetic_to_ecef_km(
        observer.latitude_deg, observer.longitude_deg, observer.altitude_m
    )
    enu = ecef_to_enu_matrix(observer.latitude_deg, observer.longitude_deg)
    azimuth_rad = np.deg2rad(np.arange(360, dtype=float))
    baselines_enu = MECHANICAL_BASELINE_M * np.column_stack(
        (np.sin(azimuth_rad), np.cos(azimuth_rad), np.zeros(360))
    )
    output = []
    for index, candidate in enumerate(candidates):
        tau_ns = round(float(candidate["selected_tau_s"]) * 1e9)
        center = times_utc_ns + tau_ns
        endpoints = np.column_stack((center - 500_000_000, center + 500_000_000)).ravel()
        grid = SamplingGrid(tuple(map(int, endpoints)), len(endpoints) // 2, 1.0)
        propagated = propagate_grid(catalogue, grid, [index])
        if not bool(propagated.usable[0]):
            raise ValueError("candidate propagation failed for baseline orientation")
        jd, fraction = julian_day_from_utc_ns(endpoints)
        gmst = greenwich_mean_sidereal_time_rad(jd, fraction)
        position, _velocity = teme_to_ecef(
            propagated.position_teme_km[0], propagated.velocity_teme_km_s[0], gmst
        )
        line = position - observer_ecef
        unit_ecef = line / np.linalg.norm(line, axis=1)[:, None]
        unit_enu = unit_ecef @ enu.T
        direction_rate = unit_enu.reshape(-1, 2, 3)[:, 1] - unit_enu.reshape(
            -1, 2, 3
        )[:, 0]
        output.append(
            rf_hz
            / SPEED_OF_LIGHT_M_S
            * (baselines_enu @ direction_rate.T)
        )
    return np.asarray(output)


def _relative_cfo_rows(
    phase_root: Path, session_id: str, visit_indices: tuple[int, ...]
) -> np.ndarray:
    values = []
    for visit_index in visit_indices:
        path = phase_root / f"{session_id}-visit-{visit_index:06d}.json.gz"
        with gzip.open(path, "rt", encoding="utf-8") as source:
            row = json.load(source)
        phase = row["random_phase"]
        if row["state"] != "replayed" or not phase["supported"]:
            raise ValueError("frozen baseline-orientation visit is no longer supported")
        values.append(float(phase["relative_cfo_hz"]))
    return np.asarray(values)


def phase_difference_timeline_rows(
    phase_root: Path, session_id: str, source: Any
) -> list[dict[str, Any]]:
    """Place every saved RX1−RX0 held-block phase estimate on the scan clock."""
    if source.timing is None:
        raise ValueError("phase-difference timeline requires qualified timing")
    visit_starts: dict[int, int] = {}
    for probe in source.probes:
        previous = visit_starts.get(probe.visit_index)
        visit_starts[probe.visit_index] = (
            probe.valid_start_counter
            if previous is None
            else min(previous, probe.valid_start_counter)
        )
    output = []
    for path in sorted(phase_root.glob(f"{session_id}-visit-*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            artifact = json.load(handle)
        phase = artifact.get("random_phase")
        if artifact.get("state") != "replayed" or phase is None:
            continue
        visit_index = int(artifact["visit_index"])
        if visit_index not in visit_starts:
            raise ValueError("phase-difference visit is absent from tracking input")
        visit_elapsed_s = (
            visit_starts[visit_index]
            - source.timing.session_start_device_sample_counter
        ) / source.sample_rate_hz
        for row in phase["held_rows"]:
            output.append(
                {
                    "session_id": session_id,
                    "visit_index": visit_index,
                    "channel": int(artifact["channel"]),
                    "edge": str(artifact["edge"]),
                    "time_s": visit_elapsed_s
                    + float(row["center_sample"]) / source.sample_rate_hz,
                    "phase_difference_rad": float(row["a_phase_rad"]),
                    "supported_dwell": bool(phase["supported"]),
                    "group_id": int(row["group_id"]),
                    "block_index": int(row["block_index"]),
                }
            )
    return output


def phase_difference_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize ordinary 2π circular concentration overall and by dwell."""
    if not rows:
        raise ValueError("phase-difference summary requires at least one estimate")

    def metrics(selected: list[dict[str, Any]]) -> dict[str, Any]:
        phases = np.asarray([row["phase_difference_rad"] for row in selected])
        phasor = np.mean(np.exp(1j * phases))
        resultant = float(abs(phasor))
        return {
            "point_count": len(selected),
            "circular_r": resultant,
            "circular_mean_rad": float(np.angle(phasor)),
            "circular_standard_deviation_deg": float(
                math.degrees(math.sqrt(-2.0 * math.log(resultant)))
            ),
        }

    visits = []
    for visit_index in sorted({int(row["visit_index"]) for row in rows}):
        selected = [row for row in rows if int(row["visit_index"]) == visit_index]
        visits.append(
            {
                "visit_index": visit_index,
                "start_time_s": min(float(row["time_s"]) for row in selected),
                "stop_time_s": max(float(row["time_s"]) for row in selected),
                **metrics(selected),
            }
        )
    return {
        "session_id": str(rows[0]["session_id"]),
        "phase_period_rad": 2 * math.pi,
        "interpretation": (
            "conditional same-block A-band RX1-minus-RX0 phase; pooled R mixes "
            "independently normalized retuned dwells"
        ),
        **metrics(rows),
        "dwell_count": len(visits),
        "median_dwell_circular_r": float(
            np.median([row["circular_r"] for row in visits])
        ),
        "visits": visits,
    }


def _extract_receiver_pairs(
    iq: np.ndarray,
    receiver_id: int,
    rate: int,
    edge: str,
    epoch: int,
    cfo_hz: float,
    visit_start_utc_ns: int,
) -> list[dict[str, Any]]:
    content = round(302 * rate * OFDM_SYMBOL_DURATION_S)
    frames: dict[int, list[Any]] = {}
    for group, start in frame_opportunities(len(iq), rate, epoch):
        measured = estimate_edge_pilot_frame_complex_split(
            iq[start - 1 : start + content + 1, receiver_id],
            rate,
            frame_start_sample=start,
            acquisition_absolute_cfo_hz=cfo_hz,
            edge=edge,
        )
        frames.setdefault(group, []).append(measured)
    output = []
    for group, values in sorted(frames.items()):
        pairs = ((values[0], values[1]), (values[2], values[3]))
        for pair_index, (left, right) in enumerate(pairs):
            if not left.training_supported or not right.training_supported:
                continue
            folds = {}
            for name in ("even", "odd"):
                first, second = getattr(left, name), getattr(right, name)
                if (
                    first is None
                    or second is None
                    or first.search_boundary
                    or second.search_boundary
                ):
                    break
                left_vector = np.asarray(first.channel_vector, dtype=complex)
                right_vector = np.asarray(second.channel_vector, dtype=complex)
                cross = np.vdot(left_vector, right_vector)
                if abs(cross) == 0:
                    break
                folds[name] = float(np.angle(cross))
            if set(folds) != {"even", "odd"}:
                continue
            duration = (right.reference_sample - left.reference_sample) / rate
            midpoint_sample = (left.reference_sample + right.reference_sample) / 2
            output.append(
                {
                    "local_group_id": group,
                    "pair_index": pair_index,
                    "endpoint_frame_ids": [
                        f"{receiver_id}:{left.reference_sample}",
                        f"{receiver_id}:{right.reference_sample}",
                    ],
                    "duration_s": duration,
                    "midpoint_utc_ns": visit_start_utc_ns
                    + round(midpoint_sample * 1e9 / rate),
                    "even_phase_advance_rad": folds["even"],
                    "odd_phase_advance_rad": folds["odd"],
                }
            )
    return output


def _score_receiver(
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    predictions: np.ndarray,
    wrong_predictions: np.ndarray,
    training_visits: tuple[int, ...],
    held_visits: tuple[int, ...],
    split_seed: int,
) -> dict[str, Any]:
    groups = np.asarray([row["visit_index"] for row in rows])
    observed_visits = set(groups.tolist())
    available_training = tuple(value for value in training_visits if value in observed_visits)
    available_held = tuple(value for value in held_visits if value in observed_visits)
    if len(available_training) < 2 or len(available_held) < 2:
        raise ValueError("phase replay leaves fewer than two visits in a random partition")
    duration = np.asarray([row["duration_s"] for row in rows])
    endpoints = np.asarray([row["endpoint_frame_ids"] for row in rows])
    even = np.asarray([row["even_phase_advance_rad"] for row in rows])
    odd = np.asarray([row["odd_phase_advance_rad"] for row in rows])
    candidate_ids = tuple(
        f"NORAD-{row['catalog_number']}-tau-{float(row['selected_tau_s']):+.0f}s"
        for row in candidates
    )
    controls = np.vstack([np.zeros(len(rows)), wrong_predictions[0]])
    all_predictions = np.vstack([predictions, controls])
    all_ids = (*candidate_ids, "constant-frequency", f"{candidate_ids[0]}-wrong-time")
    evidence = CandidatePhaseEvidence(
        measured_phase_advance_rad=even,
        interval_duration_s=duration,
        group_id=groups,
        training_group_ids=available_training,
        candidate_integrated_phase_rad=all_predictions,
        candidate_ids=all_ids,
        split_seed=split_seed,
        endpoint_frame_ids=endpoints,
    )
    fit = score_candidate_integrated_phase(
        evidence,
        bias_period_hz=BIAS_PERIOD_HZ,
        minimum_identifiable_contrast_rad=MINIMUM_IDENTIFIABLE_CONTRAST_RAD,
    )
    odd_held = response_metrics(
        odd,
        all_predictions,
        duration,
        groups,
        available_held,
        fit.fitted_bias_hz,
    )
    real_count = len(candidates)
    training_winner = int(np.argmax(fit.training_composite_score[:real_count]))
    held_diagnostic_winner = int(
        np.argmax([row["composite_score"] for row in odd_held[:real_count]])
    )
    models = []
    for index, model_id in enumerate(all_ids):
        models.append(
            {
                "model_id": model_id,
                "model_kind": (
                    "candidate"
                    if index < real_count
                    else "constant_control"
                    if index == real_count
                    else "wrong_time_control"
                ),
                "catalog_number": (
                    int(candidates[index]["catalog_number"]) if index < real_count else None
                ),
                "selected_tau_s": (
                    float(candidates[index]["selected_tau_s"]) if index < real_count else None
                ),
                "fitted_bias_hz_from_even_training": float(fit.fitted_bias_hz[index]),
                "even_training_composite_score": float(fit.training_composite_score[index]),
                "even_held_diagnostic_score": float(fit.heldout_composite_score[index]),
                "odd_held_response": odd_held[index],
            }
        )
    return {
        "candidate_ids": list(candidate_ids),
        "assigned_training_visit_indices": list(training_visits),
        "assigned_held_visit_indices": list(held_visits),
        "available_training_visit_indices": list(available_training),
        "available_held_visit_indices": list(available_held),
        "abstained_visit_indices": sorted(
            (set(training_visits) | set(held_visits)) - observed_visits
        ),
        "interval_count": len(rows),
        "training_selected_candidate_index": training_winner,
        "training_selected_candidate": candidate_ids[training_winner],
        "held_diagnostic_best_candidate_index": held_diagnostic_winner,
        "held_diagnostic_best_candidate": candidate_ids[held_diagnostic_winner],
        "glrt_leader_selected_on_training": training_winner == 0,
        "glrt_leader_best_on_held_diagnostic": held_diagnostic_winner == 0,
        "maximum_candidate_contrast_rad": float(
            np.max(fit.candidate_contrast_rms_rad[:real_count, :real_count])
        ),
        "identifiable_after_nuisance": bool(
            np.max(fit.candidate_contrast_rms_rad[:real_count, :real_count])
            >= MINIMUM_IDENTIFIABLE_CONTRAST_RAD
        ),
        "candidate_contrast_rms_rad": fit.candidate_contrast_rms_rad[
            :real_count, :real_count
        ].tolist(),
        "models": models,
    }


def run(
    selection_path: Path,
    output: Path,
    bulk_root: Path,
    tle_root: Path,
    phase_root: Path = DEFAULT_PHASE_ROOT,
) -> dict[str, Any]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    tracking_store = ScannerTrackingInputStore(bulk_root)
    iq_store = AdaptiveHopIqStore(bulk_root, read_only=True)
    tracks = []
    evidence_rows = []
    glrt_rows = []
    phase_difference_rows = []
    try:
        for chosen in selection["tracks"]:
            session_id = str(chosen["session_id"])
            manifest_path = bulk_root / "scanner-shared-tracking-v14" / session_id / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["document"]
            source = tracking_store.load(session_id)
            if source.timing is None:
                raise ValueError("phase transport requires qualified UTC")
            glrt_rows.extend(glrt_timeline_rows(source))
            phase_difference_rows.extend(
                phase_difference_timeline_rows(phase_root, session_id, source)
            )
            projected = project_scanner_candidates(source)
            by_candidate = {row.candidate_id: row for row in projected}
            trajectory = reconstruct_persistent_hop_trajectories(
                projected, config=PersistentHopTrajectoryConfig()
            )
            tracklets = {row.tracklet_id: row for row in trajectory.tracklets}
            track_points = []
            track_dealiased_cfo = []
            reviews = []
            for _receiver_id, key in ((0, "rx0_tracklet_id"), (1, "rx1_tracklet_id")):
                tracklet_id = str(chosen[key])
                tracklet = tracklets[tracklet_id]
                points = {
                    by_candidate[point.candidate_id].visit_index: by_candidate[point.candidate_id]
                    for point in tracklet.points
                }
                track_points.append(points)
                track_dealiased_cfo.append(
                    {
                        by_candidate[point.candidate_id].visit_index: (
                            point.normalized_dealiased_cfo_hz
                        )
                        for point in tracklet.points
                    }
                )
                reviews.append(_review(manifest, tracklet_id))
            visit_indices = tuple(map(int, chosen["phase_selected_visit_indices"]))
            training_visits, held_visits = seeded_group_split(
                visit_indices, seed=SPLIT_SEED + int(chosen["rank"])
            )
            snapshot_path = _tle_path(tle_root, manifest["original_tle_snapshot"])
            observer = ObserverSiteV1.model_validate(manifest["observer_site"])
            receiver_rows = [[], []]
            with AdaptiveHopAnalysisInputStore(iq_store).source(session_id) as iq_source:
                ordinal_by_visit = {
                    value.event.visit_index: index for index, value in enumerate(iq_source.visits)
                }
                for visit_index in visit_indices:
                    iq = iq_source.read_visit(ordinal_by_visit[visit_index])
                    for receiver_id in (0, 1):
                        point = track_points[receiver_id][visit_index]
                        probe = next(
                            row
                            for row in source.probes
                            if row.visit_index == visit_index
                            and row.receiver_id == receiver_id
                            and row.probe_index == point.probe_index
                        )
                        candidate = next(
                            row
                            for row in probe.candidates
                            if row.candidate_rank == point.candidate_rank
                        )
                        epoch = (
                            round(probe.probe_start_ms * source.sample_rate_hz / 1000)
                            + candidate.integer_epoch_sample
                        )
                        visit_start_utc_ns = source.timing.first_sample_estimate_utc_ns + round(
                            (
                                probe.valid_start_counter
                                - source.timing.session_start_device_sample_counter
                            )
                            * 1e9
                            / source.sample_rate_hz
                        )
                        rows = _extract_receiver_pairs(
                            iq,
                            receiver_id,
                            source.sample_rate_hz,
                            point.edge.value,
                            epoch,
                            candidate.fractional_tracking_cfo_hz,
                            visit_start_utc_ns,
                        )
                        for row in rows:
                            row.update(
                                {
                                    "track_rank": int(chosen["rank"]),
                                    "session_id": session_id,
                                    "visit_index": visit_index,
                                    "receiver_id": receiver_id,
                                    "channel": int(chosen["channel"]),
                                    "edge": str(chosen["edge"]),
                                    "scan_elapsed_s": (
                                        (
                                            int(row["midpoint_utc_ns"])
                                            - source.timing.first_sample_estimate_utc_ns
                                        )
                                        / 1e9
                                    ),
                                    "source_candidate_id": point.candidate_id,
                                    "source_probe_index": point.probe_index,
                                    "source_candidate_rank": point.candidate_rank,
                                    "source_tracking_cfo_hz": point.measured_cfo_hz,
                                    "source_tracking_dealiased_cfo_hz": (
                                        track_dealiased_cfo[receiver_id][visit_index]
                                    ),
                                }
                            )
                        receiver_rows[receiver_id].extend(rows)
            receiver_results = []
            scoring_inputs = []
            for receiver_id in (0, 1):
                candidates = list(reviews[receiver_id]["candidates"][:5])
                catalogue = _candidate_catalogue(snapshot_path, candidates)
                predictions, wrong = _prediction_bank(
                    receiver_rows[receiver_id],
                    candidates,
                    catalogue,
                    observer,
                    float(chosen["actual_rf_hz"]),
                )
                scoring_inputs.append((candidates, predictions, wrong))
                result = _score_receiver(
                    receiver_rows[receiver_id],
                    candidates,
                    predictions,
                    wrong,
                    tuple(map(int, training_visits)),
                    tuple(map(int, held_visits)),
                    SPLIT_SEED + int(chosen["rank"]),
                )
                result.update(
                    {
                        "receiver_id": receiver_id,
                        "tracklet_id": str(
                            chosen["rx0_tracklet_id"]
                            if receiver_id == 0
                            else chosen["rx1_tracklet_id"]
                        ),
                        "review_artifact": chosen["candidate_association"][
                            "rx0_tle_review" if receiver_id == 0 else "rx1_tle_review"
                        ],
                    }
                )
                receiver_results.append(result)
                evidence_rows.extend(receiver_rows[receiver_id])
            glrt_leader = int(
                chosen["candidate_association"]["leading_norad_catalog_number"]
            )
            joint = joint_receiver_result(receiver_results, glrt_leader)
            common_catalogs = set(joint["candidate_catalog_numbers"])
            baseline_candidates = [
                row
                for row in reviews[0]["candidates"][:5]
                if int(row["catalog_number"]) in common_catalogs
            ]
            baseline_catalogue = _candidate_catalogue(
                snapshot_path, baseline_candidates
            )
            center_times = np.asarray(
                [
                    round(
                        (
                            track_points[0][visit].support_center_utc_ns
                            + track_points[1][visit].support_center_utc_ns
                        )
                        / 2
                    )
                    for visit in visit_indices
                ],
                dtype=np.int64,
            )
            baseline_predictions = _baseline_prediction_bank(
                center_times,
                baseline_candidates,
                baseline_catalogue,
                observer,
                float(chosen["actual_rf_hz"]),
            )
            measured_relative_cfo = _relative_cfo_rows(
                phase_root, session_id, visit_indices
            )
            training_indices = np.flatnonzero(np.isin(visit_indices, training_visits))
            held_indices = np.flatnonzero(np.isin(visit_indices, held_visits))
            baseline_orientation = fit_baseline_orientation(
                measured_relative_cfo,
                baseline_predictions,
                training_indices,
                held_indices,
                [int(row["catalog_number"]) for row in baseline_candidates],
            )
            baseline_orientation["measured_relative_cfo_hz"] = (
                measured_relative_cfo.tolist()
            )
            sensitivity = []
            for split_index in range(SENSITIVITY_SPLIT_COUNT):
                seed = (
                    SENSITIVITY_SEED_BASE
                    + int(chosen["rank"]) * SENSITIVITY_SPLIT_COUNT
                    + split_index
                )
                sensitivity_training, sensitivity_held = seeded_group_split(
                    visit_indices, seed=seed
                )
                split_receivers = []
                try:
                    for receiver_id, (candidates, predictions, wrong) in enumerate(
                        scoring_inputs
                    ):
                        split_receivers.append(
                            _score_receiver(
                                receiver_rows[receiver_id],
                                candidates,
                                predictions,
                                wrong,
                                tuple(map(int, sensitivity_training)),
                                tuple(map(int, sensitivity_held)),
                                seed,
                            )
                        )
                    split_joint = joint_receiver_result(split_receivers, glrt_leader)
                except ValueError:
                    continue
                sensitivity.append(
                    {
                        "seed": seed,
                        "training_selected_catalog_number": split_joint[
                            "training_selected_catalog_number"
                        ],
                        "held_diagnostic_best_catalog_number": split_joint[
                            "held_diagnostic_best_catalog_number"
                        ],
                        "glrt_leader_selected_on_training": split_joint[
                            "glrt_leader_selected_on_training"
                        ],
                        "glrt_leader_best_on_held_diagnostic": split_joint[
                            "glrt_leader_best_on_held_diagnostic"
                        ],
                        "training_selected_beats_constant": split_joint[
                            "training_selected_beats_constant"
                        ],
                        "training_selected_beats_wrong_time": split_joint[
                            "training_selected_beats_wrong_time"
                        ],
                    }
                )
            tracks.append(
                {
                    "rank": int(chosen["rank"]),
                    "session_id": session_id,
                    "channel": int(chosen["channel"]),
                    "edge": str(chosen["edge"]),
                    "actual_rf_hz": float(chosen["actual_rf_hz"]),
                    "glrt_group_leading_catalog_number": glrt_leader,
                    "training_visit_indices": list(training_visits),
                    "held_visit_indices": list(held_visits),
                    "tle_snapshot": manifest["original_tle_snapshot"],
                    "tle_snapshot_path": str(snapshot_path),
                    "receivers": receiver_results,
                    "joint_receivers": joint,
                    "baseline_orientation": baseline_orientation,
                    "random_split_sensitivity": {
                        "requested_split_count": SENSITIVITY_SPLIT_COUNT,
                        "valid_split_count": len(sensitivity),
                        "glrt_leader_training_selection_fraction": float(
                            np.mean(
                                [row["glrt_leader_selected_on_training"] for row in sensitivity]
                            )
                        ),
                        "glrt_leader_held_best_fraction": float(
                            np.mean(
                                [
                                    row["glrt_leader_best_on_held_diagnostic"]
                                    for row in sensitivity
                                ]
                            )
                        ),
                        "selected_beats_constant_fraction": float(
                            np.mean(
                                [row["training_selected_beats_constant"] for row in sensitivity]
                            )
                        ),
                        "selected_beats_wrong_time_fraction": float(
                            np.mean(
                                [row["training_selected_beats_wrong_time"] for row in sensitivity]
                            )
                        ),
                        "splits": sensitivity,
                    },
                }
            )
    finally:
        tracking_store.close()
        iq_store.close()
    receivers = [receiver for track in tracks for receiver in track["receivers"]]
    selected_models = [
        receiver["models"][receiver["training_selected_candidate_index"]] for receiver in receivers
    ]
    joint_results = [track["joint_receivers"] for track in tracks]
    output_document = {
        "schema": "org.leo.research.late-track-candidate-phase/v1",
        "scope": "conditional candidate comparison; no satellite identity claim",
        "selection_sha256": digest(selection_path),
        "protocol": {
            "split_seed_base": SPLIT_SEED,
            "sensitivity_seed_base": SENSITIVITY_SEED_BASE,
            "sensitivity_split_count": SENSITIVITY_SPLIT_COUNT,
            "outer_split": "seeded random whole visits, shared by both receivers",
            "training_response": "even-symbol adjacent-frame phase advances on training visits",
            "held_response": "odd-symbol adjacent-frame phase advances on held visits",
            "frame_policy": "four IQ-blind adjacent frames nearest each 20 ms group center",
            "candidate_bank": "top five causal-TLE candidates from exact phase-blind track review",
            "candidate_tau": "frozen phase-blind TLE-review tau per candidate",
            "nuisance": "one candidate/track/receiver frequency bias fitted on even training only",
            "phase_period_rad": math.pi,
            "bias_period_hz": BIAS_PERIOD_HZ,
            "minimum_identifiable_contrast_rad": MINIMUM_IDENTIFIABLE_CONTRAST_RAD,
            "fractional_epoch_corrected": False,
            "phase_continuity_across_visits": False,
            "baseline_orientation": (
                "8 cm horizontal RX0-to-RX1 azimuth and one receiver CFO offset fitted "
                "per candidate/scan on random training visits; held visits only evaluate"
            ),
        },
        "track_count": len(tracks),
        "receiver_evaluation_count": len(receivers),
        "interval_count": len(evidence_rows),
        "aggregate": {
            "glrt_leader_selected_on_training_receivers": sum(
                row["glrt_leader_selected_on_training"] for row in receivers
            ),
            "glrt_leader_best_on_held_diagnostic_receivers": sum(
                row["glrt_leader_best_on_held_diagnostic"] for row in receivers
            ),
            "identifiable_after_nuisance_receivers": sum(
                row["identifiable_after_nuisance"] for row in receivers
            ),
            "median_selected_odd_held_r": float(
                np.median(
                    [row["odd_held_response"]["circular_r_modulo_pi"] for row in selected_models]
                )
            ),
            "median_selected_odd_held_rms_rad": float(
                np.median([row["odd_held_response"]["rms_rad"] for row in selected_models])
            ),
            "selected_beats_constant_control_receivers": sum(
                selected["odd_held_response"]["composite_score"]
                > receiver["models"][-2]["odd_held_response"]["composite_score"]
                for receiver, selected in zip(receivers, selected_models, strict=True)
            ),
            "selected_beats_wrong_time_control_receivers": sum(
                selected["odd_held_response"]["composite_score"]
                > receiver["models"][-1]["odd_held_response"]["composite_score"]
                for receiver, selected in zip(receivers, selected_models, strict=True)
            ),
            "joint_glrt_leader_selected_on_training_tracks": sum(
                row["glrt_leader_selected_on_training"] for row in joint_results
            ),
            "joint_glrt_leader_best_on_held_diagnostic_tracks": sum(
                row["glrt_leader_best_on_held_diagnostic"] for row in joint_results
            ),
            "joint_selected_beats_constant_control_tracks": sum(
                row["training_selected_beats_constant"] for row in joint_results
            ),
            "joint_selected_beats_wrong_time_control_tracks": sum(
                row["training_selected_beats_wrong_time"] for row in joint_results
            ),
            "orientation_glrt_leader_selected_on_training_tracks": sum(
                track["baseline_orientation"]["training_selected_catalog_number"]
                == track["glrt_group_leading_catalog_number"]
                for track in tracks
            ),
            "orientation_glrt_leader_best_on_held_diagnostic_tracks": sum(
                track["baseline_orientation"]["held_diagnostic_best_catalog_number"]
                == track["glrt_group_leading_catalog_number"]
                for track in tracks
            ),
            "orientation_selected_beats_constant_tracks": sum(
                track["baseline_orientation"]["training_selected_beats_constant"]
                for track in tracks
            ),
        },
        "tracks": tracks,
        "source_sha256": digest(Path(__file__)),
    }
    with gzip.open(output / "phase-advance-evidence.json.gz", "wt", encoding="utf-8") as target:
        json.dump(serial({"protocol": output_document["protocol"], "rows": evidence_rows}), target)
    with gzip.open(output / "glrt-timeline.json.gz", "wt", encoding="utf-8") as target:
        json.dump(serial({"rows": glrt_rows}), target)
    with gzip.open(
        output / "phase-difference-timeline.json.gz", "wt", encoding="utf-8"
    ) as target:
        json.dump(serial({"rows": phase_difference_rows}), target)
    t1_session_id = str(min(tracks, key=lambda row: int(row["rank"]))["session_id"])
    t1_phase_rows = [
        row for row in phase_difference_rows if row["session_id"] == t1_session_id
    ]
    (output / "t1-phase-difference-summary.json").write_text(
        json.dumps(serial(phase_difference_summary(t1_phase_rows)), indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "summary.json").write_text(
        json.dumps(serial(output_document), indent=2) + "\n", encoding="utf-8"
    )
    render(
        output_document,
        output,
        evidence_rows,
        glrt_rows,
        phase_difference_rows,
    )
    return output_document


def render(
    document: dict[str, Any],
    output: Path,
    evidence_rows: list[dict[str, Any]],
    glrt_rows: list[dict[str, Any]],
    phase_difference_rows: list[dict[str, Any]],
) -> None:
    colours = plt.cm.tab10(np.arange(5))
    fig, axes = plt.subplots(5, 2, figsize=(15, 16), constrained_layout=True)
    for track, colour, row_axes in zip(document["tracks"], colours, axes, strict=True):
        for receiver, axis in zip(track["receivers"], row_axes, strict=True):
            models = receiver["models"]
            labels = [
                str(model["catalog_number"])
                if model["catalog_number"] is not None
                else "constant"
                if model["model_kind"] == "constant_control"
                else "wrong-time"
                for model in models
            ]
            x = np.arange(len(models))
            axis.plot(
                x,
                [model["even_training_composite_score"] for model in models],
                "o-",
                color="#777777",
                label="even training",
            )
            axis.plot(
                x,
                [model["odd_held_response"]["composite_score"] for model in models],
                "s-",
                color=colour,
                label="odd held response",
            )
            axis.axhline(0, color="black", lw=0.7)
            axis.set_xticks(x, labels, rotation=30, ha="right")
            axis.set_ylabel("Equal-visit circular score")
            axis.set_title(
                f"T{track['rank']} RX{receiver['receiver_id']} · "
                f"train chose {receiver['training_selected_candidate']}",
                loc="left",
            )
            axis.grid(axis="y", alpha=0.25)
            axis.spines[["top", "right"]].set_visible(False)
            axis.legend(fontsize=8)
    fig.suptitle(
        "Frozen causal-TLE candidates: even-symbol training versus odd-symbol random-held response"
    )
    fig.savefig(output / "candidate-score-by-track-receiver.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    receivers = [receiver for track in document["tracks"] for receiver in track["receivers"]]
    positions = np.arange(len(receivers))
    labels = [
        f"T{track['rank']} RX{receiver['receiver_id']}"
        for track in document["tracks"]
        for receiver in track["receivers"]
    ]
    selected_r, constant_r, wrong_r, contrast = [], [], [], []
    for receiver in receivers:
        selected = receiver["models"][receiver["training_selected_candidate_index"]]
        selected_r.append(selected["odd_held_response"]["circular_r_modulo_pi"])
        constant_r.append(receiver["models"][-2]["odd_held_response"]["circular_r_modulo_pi"])
        wrong_r.append(receiver["models"][-1]["odd_held_response"]["circular_r_modulo_pi"])
        contrast.append(receiver["maximum_candidate_contrast_rad"])
    width = 0.25
    axes[0].bar(positions - width, selected_r, width, label="training-selected TLE")
    axes[0].bar(positions, constant_r, width, label="constant-frequency control")
    axes[0].bar(positions + width, wrong_r, width, label="wrong-time leader")
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Odd-held circular R (modulo π)")
    axes[0].legend(fontsize=8)
    axes[1].bar(positions, contrast, color="#4c78a8")
    axes[1].axhline(
        MINIMUM_IDENTIFIABLE_CONTRAST_RAD,
        color="black",
        ls="--",
        label="predeclared 0.10 rad gate",
    )
    axes[1].set_ylabel("Maximum held candidate contrast (rad)")
    axes[1].legend(fontsize=8)
    for axis in axes:
        axis.set_xticks(positions, labels, rotation=45, ha="right")
        axis.grid(axis="y", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_title("Phase agreement against candidate and controls")
    axes[1].set_title("Candidate distinguishability after frequency nuisance")
    fig.savefig(output / "held-phase-association-summary.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 5, figsize=(18, 4.5), constrained_layout=True)
    for track, colour, axis in zip(document["tracks"], colours, axes, strict=True):
        joint = track["joint_receivers"]
        candidates = joint["candidates"]
        x = np.arange(len(candidates))
        axis.plot(
            x,
            [row["even_training_composite_score"] for row in candidates],
            "o-",
            color="#777777",
            label="even training",
        )
        axis.plot(
            x,
            [row["odd_held_composite_score"] for row in candidates],
            "s-",
            color=colour,
            label="odd held",
        )
        axis.axhline(joint["constant_control_odd_held_score"], color="#222222", ls="--")
        axis.axhline(joint["wrong_time_control_odd_held_score"], color="#d62728", ls=":")
        axis.set_xticks(
            x,
            [str(row["catalog_number"]) for row in candidates],
            rotation=45,
            ha="right",
        )
        axis.set_title(
            f"T{track['rank']} · train {joint['training_selected_catalog_number']} · "
            f"held {joint['held_diagnostic_best_catalog_number']}"
        )
        axis.grid(axis="y", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Equal-receiver composite score")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Joint dual-receiver candidate comparison · dashed constant · dotted wrong-time"
    )
    fig.savefig(output / "joint-receiver-candidate-score.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    x = np.arange(len(document["tracks"]))
    for track, colour in zip(document["tracks"], colours, strict=True):
        orientation = track["baseline_orientation"]
        models = orientation["models"]
        selected = next(
            row
            for row in models
            if row["catalog_number"]
            == orientation["training_selected_catalog_number"]
        )
        axes[0].scatter(
            track["rank"],
            selected["training_fitted_azimuth_deg"],
            color=colour,
            s=55,
        )
        axes[1].bar(
            track["rank"] - 0.18,
            selected["held_rms_hz"],
            0.36,
            color=colour,
        )
        axes[1].bar(
            track["rank"] + 0.18,
            orientation["constant_control_held_rms_hz"],
            0.36,
            color="#888888",
        )
    axes[0].axhline(79, color="black", ls="--", label="nominal 79°")
    axes[0].axhline(259, color="black", ls=":", label="reversed 259°")
    axes[0].set_ylabel("Train-fitted RX0→RX1 azimuth (degrees)")
    axes[0].legend()
    axes[1].set_ylabel("Random-held relative-CFO RMS (Hz)")
    axes[1].legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color="#4c78a8"),
            plt.Rectangle((0, 0), 1, 1, color="#888888"),
        ],
        labels=["training-selected TLE", "constant-CFO control"],
    )
    for axis in axes:
        axis.set_xticks(x + 1, [f"T{rank}" for rank in x + 1])
        axis.grid(axis="y", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_title("Feasibility-only azimuth fit; orientation is not identified")
    axes[1].set_title("Held geometry-rate test; bars should differ if usable")
    fig.savefig(output / "baseline-orientation-held-test.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(5, 1, figsize=(14, 14), sharex=True, constrained_layout=True)
    receiver_markers = {0: "o", 1: "x"}
    track_markers = {0: "D", 1: "^"}
    track_styles = {0: "-", 1: "--"}
    track_points = selected_track_points(evidence_rows)
    right_axes = []
    for track, axis in zip(document["tracks"], axes, strict=True):
        track_axis = axis.twinx()
        right_axes.append(track_axis)
        rows = [
            row for row in evidence_rows if row["session_id"] == track["session_id"]
        ]
        for receiver_id, marker in receiver_markers.items():
            selected = [row for row in rows if row["receiver_id"] == receiver_id]
            axis.scatter(
                [row["scan_elapsed_s"] for row in selected],
                [
                    math.degrees(float(wrap_pi(row["odd_phase_advance_rad"])))
                    for row in selected
                ],
                s=13,
                marker=marker,
                color=CHANNEL_COLOURS[track["channel"]],
                alpha=0.62,
                linewidths=0.7,
                rasterized=True,
                label=f"RX{receiver_id}" if track["rank"] == 1 else None,
            )
            selected_track = [
                row
                for row in track_points
                if row["session_id"] == track["session_id"]
                and row["receiver_id"] == receiver_id
            ]
            cfo_center_hz = float(
                np.median([row["tracking_cfo_hz"] for row in selected_track])
            )
            track_axis.plot(
                [row["scan_elapsed_s"] for row in selected_track],
                [
                    (row["tracking_cfo_hz"] - cfo_center_hz) / 1000
                    for row in selected_track
                ],
                marker=track_markers[receiver_id],
                linestyle=track_styles[receiver_id],
                color="#30343b" if receiver_id == 0 else "#70757d",
                linewidth=1.15,
                markersize=4.5,
                alpha=0.9,
                label=(
                    f"RX{receiver_id} GLRT track" if track["rank"] == 1 else None
                ),
            )
        axis.set_ylim(-90, 90)
        axis.set_yticks([-90, -45, 0, 45, 90])
        axis.set_ylabel("Phase advance (°)")
        axis.set_title(
            f"T{track['rank']} · {track['session_id']} · CH{track['channel']} {track['edge']}",
            loc="left",
            fontsize=10,
        )
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
        if track["rank"] == 3:
            track_axis.set_ylabel(
                "De-aliased track CFO − RX median (kHz)", color="#4f5660"
            )
        track_axis.tick_params(axis="y", colors="#4f5660")
        track_axis.spines["top"].set_visible(False)
    for channel in sorted({track["channel"] for track in document["tracks"]}):
        axes[0].scatter(
            [],
            [],
            marker="s",
            color=CHANNEL_COLOURS[channel],
            label=f"CH{channel}",
        )
    left_handles, left_labels = axes[0].get_legend_handles_labels()
    right_handles, right_labels = right_axes[0].get_legend_handles_labels()
    axes[0].legend(
        left_handles + right_handles,
        left_labels + right_labels,
        loc="upper right",
        ncol=4,
        fontsize=8,
    )
    axes[-1].set_xlim(0, 300)
    axes[-1].set_xlabel("Elapsed scan time from qualified device-counter timing (seconds)")
    fig.suptitle(
        "Random-held phase and selected GLRT tracks over each 300-second scan\n"
        "Left: modulo-π phase · right: de-aliased track CFO relative to RX median"
    )
    fig.savefig(output / "phase-vs-time-300s.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(5, 1, figsize=(14, 14), sharex=True, constrained_layout=True)
    for track, axis in zip(document["tracks"], axes, strict=True):
        session_rows = [
            row
            for row in phase_difference_rows
            if row["session_id"] == track["session_id"]
        ]
        for channel, colour in CHANNEL_COLOURS.items():
            selected = [row for row in session_rows if row["channel"] == channel]
            if not selected:
                continue
            axis.scatter(
                [row["time_s"] for row in selected],
                [
                    math.degrees(
                        float(
                            np.angle(np.exp(1j * row["phase_difference_rad"]))
                        )
                    )
                    for row in selected
                ],
                s=9,
                color=colour,
                alpha=0.55,
                linewidths=0,
                rasterized=True,
                label=f"CH{channel} (n={len(selected)})",
            )
        axis.set_ylim(-180, 180)
        axis.set_yticks([-180, -90, 0, 90, 180])
        axis.set_ylabel("RX1−RX0 phase (°)")
        axis.set_title(
            f"T{track['rank']} · {track['session_id']} · all saved phase estimates",
            loc="left",
            fontsize=10,
        )
        axis.legend(loc="upper right", ncol=4, fontsize=8)
        axis.grid(alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    axes[-1].set_xlim(0, 300)
    axes[-1].set_xlabel("Elapsed scan time from device sample counter (seconds)")
    fig.suptitle(
        "Every saved conditional RX1−RX0 phase-difference estimate over 300 seconds\n"
        "Colours identify RF channel · wrapped to ±180° · no cross-visit connection"
    )
    fig.savefig(output / "phase-difference-vs-time-300s.png", dpi=170)
    plt.close(fig)

    t1_track = min(document["tracks"], key=lambda row: int(row["rank"]))
    t1_rows = [
        row
        for row in phase_difference_rows
        if row["session_id"] == t1_track["session_id"]
    ]
    t1_summary = phase_difference_summary(t1_rows)
    fig, axis = plt.subplots(figsize=(14, 6.5), constrained_layout=True)
    for channel, colour in CHANNEL_COLOURS.items():
        selected = [row for row in t1_rows if row["channel"] == channel]
        if selected:
            axis.scatter(
                [row["time_s"] for row in selected],
                [math.degrees(float(row["phase_difference_rad"])) for row in selected],
                s=22,
                color=colour,
                alpha=0.65,
                linewidths=0,
                label=f"CH{channel} estimates (n={len(selected)})",
            )
    axis.scatter(
        [0.5 * (row["start_time_s"] + row["stop_time_s"]) for row in t1_summary["visits"]],
        [math.degrees(row["circular_mean_rad"]) for row in t1_summary["visits"]],
        s=58,
        marker="D",
        facecolors="white",
        edgecolors="black",
        linewidths=1.1,
        zorder=3,
        label="Per-dwell circular mean",
    )
    padding_s = 0.25
    axis.set_xlim(
        min(float(row["time_s"]) for row in t1_rows) - padding_s,
        max(float(row["time_s"]) for row in t1_rows) + padding_s,
    )
    axis.set_ylim(-180, 180)
    axis.set_yticks([-180, -90, 0, 90, 180])
    axis.set_xlabel("Elapsed time within the 300-second scan (seconds)")
    axis.set_ylabel("RX1−RX0 phase difference (°)")
    axis.set_title(
        "T1 conditional phase difference · every random-held estimate\n"
        f"ordinary 2π circular R={t1_summary['circular_r']:.3f} overall · "
        f"median per-dwell R={t1_summary['median_dwell_circular_r']:.3f}",
        loc="left",
    )
    axis.legend(loc="upper right")
    axis.grid(alpha=0.2)
    axis.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "t1-phase-difference-vs-time.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(5, 2, figsize=(15, 16), sharex=True, constrained_layout=True)
    for track, row_axes in zip(document["tracks"], axes, strict=True):
        session_rows = [
            row for row in glrt_rows if row["session_id"] == track["session_id"]
        ]
        for receiver_id, axis in enumerate(row_axes):
            receiver_rows = [
                row for row in session_rows if row["receiver_id"] == receiver_id
            ]
            failed = [
                row
                for row in receiver_rows
                if not row["passed_fractional_margin_gate"]
            ]
            axis.scatter(
                [row["time_s"] for row in failed],
                [row["fractional_margin"] for row in failed],
                s=2,
                color="0.75",
                alpha=0.22,
                linewidths=0,
                rasterized=True,
                label="Below gate" if track["rank"] == 1 and receiver_id == 0 else None,
            )
            for channel, colour in CHANNEL_COLOURS.items():
                passed = [
                    row
                    for row in receiver_rows
                    if row["passed_fractional_margin_gate"]
                    and row["channel"] == channel
                ]
                axis.scatter(
                    [row["time_s"] for row in passed],
                    [row["fractional_margin"] for row in passed],
                    s=6,
                    color=colour,
                    alpha=0.58,
                    linewidths=0,
                    rasterized=True,
                    label=(
                        f"CH{channel}"
                        if track["rank"] == 1 and receiver_id == 0
                        else None
                    ),
                )
            axis.axhline(0.025, color="0.3", linewidth=0.8, linestyle="--")
            axis.set_xlim(0, 300)
            axis.set_ylabel("GLRT margin")
            axis.set_title(
                f"T{track['rank']} · RX{receiver_id} · {track['session_id']}",
                loc="left",
                fontsize=9,
            )
            axis.grid(alpha=0.2)
            axis.spines[["top", "right"]].set_visible(False)
    axes[0, 0].legend(ncol=5, fontsize=8, loc="upper center")
    axes[-1, 0].set_xlabel("Elapsed scan time (seconds)")
    axes[-1, 1].set_xlabel("Elapsed scan time (seconds)")
    fig.suptitle(
        "Full fractional-GLRT inventory over each 300-second scan\n"
        "Passed candidates coloured by RF channel · gray below the 0.025 margin gate"
    )
    fig.savefig(output / "glrt-vs-time-300s.png", dpi=170)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--phase-root", type=Path, default=DEFAULT_PHASE_ROOT)
    args = parser.parse_args()
    result = run(
        args.selection, args.output, args.bulk_root, args.tle_root, args.phase_root
    )
    print(json.dumps(result["aggregate"], indent=2))


if __name__ == "__main__":
    main()
