#!/usr/bin/env python3
"""Replay RX0 at the pinned RX1 long-branch anchors in existing Aug-25 IQ.

This bounded, read-only experiment searches one complete 750 Hz timing period
and a local CFO neighborhood independently on RX0.  A first-60%-UTC calibration
fold estimates the RX0/RX1 integer group-delay offset from strong exact-versus-
rolled Qin alignments.  The frozen offset then binds both calibration and final
40% evaluated anchors before frame-local CFO estimation.  It creates research
artifacts only; no Standard contract or stored analysis product is changed.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.continuous_frame_recovery import (
    FrameOpportunityOutcome,
    FrameRecoveryAnchor,
    FrameRecoveryConfig,
    recover_contiguous_frames,
)
from leo.analysis.starlink.acquisition import NumericalStatus, align_known_pilot_frames
from leo.analysis.starlink.templates import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
RUN_ID = "capture-a5d45dd7752c4fc7833cd017a289f8d7"
STREAM_ID = "stream-1"
RX0_SCOPE = "sha256:f96018dcb38c192b83c28cc99040e43254a0b287d1c9a374dc5677736e49ee80"
RX0_BRANCH_ID = "sha256:d9fe5a2c5028f3d8f35d44f21e06ca88cd3af5d8818fc477eb96518823846470"
RX0_TRAJECTORY_ID = "sha256:4bc2bfb418476bf2fc6365c3ec1eb18b78f2b8331af5b198ad5960389c3cc920"
RX1_TRAJECTORY_ID = "sha256:92955a7dc86076490a7150b7f233ef64519fb7c0999bba1e62d94dfa531b5d8c"

SAMPLE_RATE_HZ = 2_500_000
PROBE_SAMPLES = 50_000
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750.0
COMMON_START_S = 43.6
COMMON_STOP_S = 51.35
SPLIT_TIME_S = COMMON_START_S + 0.60 * (COMMON_STOP_S - COMMON_START_S)
LOCAL_CFO_RADIUS_HZ = 2_500.0
LOCAL_CFO_STEP_HZ = 250.0
MINIMUM_TARGET_EXACT_SCORE = 0.10
MINIMUM_CALIBRATION_MARGIN = 0.05
MAXIMUM_DELAY_RESIDUAL_SAMPLES = 4.0
ALIAS_SPACING_HZ = SAMPLE_RATE_HZ / 11.0

EXPECTED_INPUT_SHA256 = {
    "recording_manifest": "ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e",
    "rx0_dealiased_bank": "95350c2c6878fabe11fccc03e7017c97cd3beaa9807f581f9c86c52c76026e14",
    "rx0_final_bank": "1c1536cb7336779c1ba028609bd54afef962c5c5890267e69fca5af581e4fd0a",
    "rx1_long_evidence": "619a715143c20801efbe8be3dee012b1a83e3fc730d588bb3a2c6cd2382de579",
    "rx1_long_frame_rows_gzip": (
        "38beb847c417e4b69f8c8ed64acda1d24116ad47531dc2ee3e601d61cd3bda0f"
    ),
    "rx1_long_frame_rows_decompressed": (
        "2d40f818bb76723629227704066137c0947a9523742f60fdd1cfad3a79842fd4"
    ),
}
# Filled from the canonical JSON returned by scientific_config().  The tool
# refuses to run if a scientific setting changes without explicit review.
EXPECTED_CONFIG_SHA256 = "c04640173c07dd8c5933c58b84ae3c21b25356e21680f480b3838069682406f2"

RECORDING_ROOT = Path("/srv/bulk/leo/recordings/2026/08/25") / SESSION_ID
RECORDING_MANIFEST = RECORDING_ROOT / "manifest.json"
ANALYSIS_ROOT = Path("/srv/bulk/leo/analysis") / SESSION_ID / RUN_ID
RX0_ROOT = ANALYSIS_ROOT / "scientific/path-standard" / RX0_SCOPE
RX0_DEALIASED_BANK = RX0_ROOT / "standard.dealiased-trajectory-bank.v4.json"
RX0_FINAL_BANK = RX0_ROOT / "standard.final-trajectory-bank.v3.json"
RX1_EVIDENCE = Path(
    "reports/figures/2026_08_25_counter_continuous_frame_timing/long-track-evidence.json"
)
RX1_ROWS = Path(
    "reports/figures/2026_08_25_counter_continuous_frame_timing/long-track-frame-rows.jsonl.gz"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_rx0_cross_receiver_anchor_replay")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def decompressed_gzip_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def scientific_config() -> dict[str, Any]:
    """Return every setting that can change the scientific row membership."""

    return {
        "schema": "org.leo.research.rx0-cross-receiver-anchor-replay-config/v1",
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "stream_id": STREAM_ID,
        "receiver_id": 0,
        "edge": StarlinkEdge.UPPER.value,
        "rx0_scope": RX0_SCOPE,
        "rx0_branch_id": RX0_BRANCH_ID,
        "rx0_trajectory_id": RX0_TRAJECTORY_ID,
        "rx1_trajectory_id": RX1_TRAJECTORY_ID,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "probe_samples": PROBE_SAMPLES,
        "common_interval_s": [COMMON_START_S, COMMON_STOP_S],
        "split_fraction": 0.60,
        "split_time_s": SPLIT_TIME_S,
        "local_cfo_radius_hz": LOCAL_CFO_RADIUS_HZ,
        "local_cfo_step_hz": LOCAL_CFO_STEP_HZ,
        "minimum_target_exact_score": MINIMUM_TARGET_EXACT_SCORE,
        "minimum_calibration_margin": MINIMUM_CALIBRATION_MARGIN,
        "maximum_delay_residual_samples": MAXIMUM_DELAY_RESIDUAL_SAMPLES,
        "frame_recovery_config": {
            "maximum_coast_frames": 2,
            "frequency_innovation_gate_sigma": 6.0,
            "frequency_noise_floor_hz": 25.0,
            "initial_rate_sigma_hz_s": 5_000.0,
            "rate_process_sigma_hz_s_sqrt_s": 750.0,
            "maximum_anchor_epoch_error_samples": 1,
            "maximum_anchor_cfo_difference_hz": 10_000.0,
            "pilot": {
                "residual_half_width_hz": 2_000.0,
                "minimum_exact_coherence": 0.02,
                "minimum_coherence_margin": 0.0,
                "maximum_even_odd_disagreement_hz": 100.0,
                "maximum_timing_spread_hz": 50.0,
                "maximum_half_frame_z": 4.0,
                "maximum_tone_deletion_shift_hz": 75.0,
            },
        },
    }


def canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def frozen_input_sha256() -> dict[str, str]:
    return {
        "recording_manifest": sha256(RECORDING_MANIFEST),
        "rx0_dealiased_bank": sha256(RX0_DEALIASED_BANK),
        "rx0_final_bank": sha256(RX0_FINAL_BANK),
        "rx1_long_evidence": sha256(RX1_EVIDENCE),
        "rx1_long_frame_rows_gzip": sha256(RX1_ROWS),
        "rx1_long_frame_rows_decompressed": decompressed_gzip_sha256(RX1_ROWS),
    }


def verify_frozen_provenance() -> dict[str, str]:
    actual = frozen_input_sha256()
    if actual != EXPECTED_INPUT_SHA256:
        raise ValueError(f"frozen RX0 replay input digest mismatch: {actual}")
    config_sha256 = canonical_sha256(scientific_config())
    if config_sha256 != EXPECTED_CONFIG_SHA256:
        raise ValueError(f"frozen RX0 replay config digest mismatch: {config_sha256}")
    evidence = load_object(RX1_EVIDENCE)
    linked = str(evidence["artifacts"]["frame_rows_sha256"])
    if linked != actual["rx1_long_frame_rows_decompressed"]:
        raise ValueError("RX1 evidence does not bind the decompressed tracked frame rows")
    return actual


def circular_epoch_difference(found: int, nominal: int) -> float:
    """Return the shortest signed timing difference on the 750 Hz lattice."""

    raw = float(found - nominal)
    return float(
        (raw + 0.5 * FRAME_PERIOD_SAMPLES) % FRAME_PERIOD_SAMPLES - 0.5 * FRAME_PERIOD_SAMPLES
    )


def estimate_receiver_delay(searches: list[dict[str, Any]]) -> float:
    """Estimate a frozen channel delay from strong first-60%-UTC alignments."""

    calibration = [
        float(value["circular_epoch_offset_samples"])
        for value in searches
        if float(value["anchor_time_s"]) < SPLIT_TIME_S
        and value["alignment_status"] == NumericalStatus.COMPLETE.value
        and float(value["exact_score"]) >= MINIMUM_TARGET_EXACT_SCORE
        and float(value["exact_minus_control_margin"]) >= MINIMUM_CALIBRATION_MARGIN
    ]
    if len(calibration) < 3:
        raise ValueError("fewer than three strong training anchors calibrate receiver delay")
    delay = float(statistics.median(calibration))
    if max(abs(value - delay) for value in calibration) > MAXIMUM_DELAY_RESIDUAL_SAMPLES:
        raise ValueError("strong training anchors do not share one receiver-delay mode")
    return delay


def target_bound(search: dict[str, Any], *, receiver_delay_samples: float) -> bool:
    """Apply the frozen target-binding gate after the local blind search."""

    return bool(
        search["alignment_status"] == NumericalStatus.COMPLETE.value
        and float(search["exact_score"]) >= MINIMUM_TARGET_EXACT_SCORE
        and float(search["exact_minus_control_margin"]) > 0.0
        and abs(float(search["circular_epoch_offset_samples"]) - receiver_delay_samples)
        <= MAXIMUM_DELAY_RESIDUAL_SAMPLES
    )


def fit_line(
    rows: list[dict[str, Any]],
    *,
    origin_s: float = COMMON_START_S,
    cfo_key: str = "even_absolute_cfo_hz",
) -> dict[str, Any]:
    if len(rows) < 2:
        raise ValueError("a line fit requires at least two rows")
    times = np.asarray([float(value["reference_time_s"]) - origin_s for value in rows])
    cfo = np.asarray([float(value[cfo_key]) for value in rows])
    slope, intercept = np.polyfit(times, cfo, 1)
    residual = cfo - (slope * times + intercept)
    return {
        "observation_count": len(rows),
        "origin_time_s": origin_s,
        "slope_hz_s": float(slope),
        "intercept_hz": float(intercept),
        "residual_rms_hz": float(np.sqrt(np.mean(np.square(residual)))),
        "residual_median_absolute_hz": float(np.median(np.abs(residual))),
        "time_start_s": float(np.min(times) + origin_s),
        "time_stop_s": float(np.max(times) + origin_s),
    }


def prediction_rms(
    rows: list[dict[str, Any]],
    model: dict[str, Any],
    *,
    cfo_key: str = "even_absolute_cfo_hz",
) -> float:
    values = []
    for row in rows:
        elapsed = float(row["reference_time_s"]) - float(model["origin_time_s"])
        predicted = float(model["intercept_hz"]) + float(model["slope_hz_s"]) * elapsed
        values.append(float(row[cfo_key]) - predicted)
    if not values:
        raise ValueError("prediction RMS requires at least one row")
    return float(np.sqrt(np.mean(np.square(values))))


def anchor_medians(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["anchor_id"])].append(row)
    return [
        {
            "anchor_id": anchor_id,
            "reference_time_s": float(
                statistics.median(float(value["reference_time_s"]) for value in values)
            ),
            "even_absolute_cfo_hz": float(
                statistics.median(float(value["even_absolute_cfo_hz"]) for value in values)
            ),
            "frame_count": len(values),
        }
        for anchor_id, values in sorted(grouped.items())
    ]


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("unexpected one-receiver CI16 geometry")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 2**15


def _alignment_document(
    anchor: dict[str, Any], alignment: Any, seed_cfo_hz: float
) -> dict[str, Any]:
    found = alignment.epoch_sample
    nominal = int(anchor["local_epoch_sample"])
    return {
        "anchor_id": str(anchor["anchor_id"]),
        "anchor_time_s": int(anchor["acquisition_start_sample"]) / SAMPLE_RATE_HZ,
        "acquisition_start_sample": int(anchor["acquisition_start_sample"]),
        "rx1_nominal_local_epoch_sample": nominal,
        "rx0_seed_cfo_hz": seed_cfo_hz,
        "alignment_status": alignment.status.value,
        "rx0_local_epoch_sample": found,
        "circular_epoch_offset_samples": (
            None if found is None else circular_epoch_difference(int(found), nominal)
        ),
        "rx0_aligned_cfo_hz": alignment.absolute_cfo_hz,
        "cfo_offset_from_seed_hz": alignment.cfo_offset_from_nominal_hz,
        "exact_score": alignment.exact_score,
        "control_score": alignment.control_score,
        "exact_minus_control_margin": alignment.exact_minus_control_margin,
        "control_epoch_sample": alignment.control_epoch_sample,
        "control_absolute_cfo_hz": alignment.control_absolute_cfo_hz,
        "frame_support": alignment.frame_support,
        "searched_epoch_count": alignment.searched_epoch_count,
        "searched_cfo_count": alignment.searched_cfo_count,
        "reason": alignment.reason,
    }


def _frame_document(anchor_id: str, frame: Any) -> dict[str, Any]:
    split = frame.split_validation
    primary = frame.primary
    return {
        "anchor_id": anchor_id,
        "frame_start_sample": int(frame.frame_start_sample),
        "reference_sample": float(frame.reference_sample),
        "reference_time_s": float(frame.reference_sample / SAMPLE_RATE_HZ),
        "outcome": frame.outcome.value,
        "filter_accepted": bool(frame.filter_accepted),
        "rejection_reasons": list(frame.rejection_reasons),
        "even_absolute_cfo_hz": None if split is None else split.even_absolute_cfo_hz,
        "odd_absolute_cfo_hz": None if split is None else split.odd_absolute_cfo_hz,
        "even_frequency_uncertainty_hz": (
            None if split is None else split.even_frequency_uncertainty_hz
        ),
        "odd_frequency_uncertainty_hz": (
            None if split is None else split.odd_frequency_uncertainty_hz
        ),
        "even_exact_coherence": None if split is None else split.even_exact_coherence,
        "even_control_coherence": None if split is None else split.even_control_coherence,
        "even_coherence_margin": None if split is None else split.even_coherence_margin,
        "even_search_boundary": None if split is None else split.even_search_boundary,
        "odd_search_boundary": None if split is None else split.odd_search_boundary,
        "training_supported": None if split is None else split.training_supported,
        "primary_supported": None if primary is None else primary.measurement_supported,
        "primary_rejection_reasons": (None if primary is None else list(primary.rejection_reasons)),
        "primary_absolute_cfo_hz": None if primary is None else primary.absolute_cfo_hz,
        "primary_exact_coherence": None if primary is None else primary.exact_coherence,
        "primary_control_coherence": None if primary is None else primary.control_coherence,
        "primary_coherence_margin": None if primary is None else primary.coherence_margin,
    }


def _load_rx1_rows() -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    with gzip.open(RX1_ROWS, "rt", encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            if value["outcome"] == FrameOpportunityOutcome.SUPPORTED.value:
                output[int(value["frame_start_sample"])] = value
    return output


def _cross_receiver_summary(
    research_supported: list[dict[str, Any]], rx1_by_start: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    matched = []
    exact_match_count = 0
    rx1_starts = sorted(rx1_by_start)
    for row in research_supported:
        rx0_start = int(row["frame_start_sample"])
        exact = rx1_by_start.get(rx0_start)
        if exact is not None:
            exact_match_count += 1
        index = bisect.bisect_left(rx1_starts, rx0_start)
        candidates = rx1_starts[max(0, index - 1) : index + 1]
        if not candidates:
            continue
        rx1_start = min(candidates, key=lambda value: (abs(value - rx0_start), value))
        if abs(rx1_start - rx0_start) > 2:
            continue
        rx1 = rx1_by_start[rx1_start]
        matched.append(
            {
                "reference_time_s": row["reference_time_s"],
                "frame_start_offset_samples": rx1_start - rx0_start,
                "even_absolute_cfo_hz": row["even_absolute_cfo_hz"],
                "rx1_even_absolute_cfo_hz": float(rx1["even_absolute_cfo_hz"]),
                "difference_hz": float(row["even_absolute_cfo_hz"])
                - float(rx1["even_absolute_cfo_hz"]),
            }
        )
    if len(matched) < 2:
        raise ValueError("too few exact-frame RX0/RX1 matches")
    rx1_fit_rows = [
        {
            "reference_time_s": value["reference_time_s"],
            "even_absolute_cfo_hz": value["rx1_even_absolute_cfo_hz"],
        }
        for value in matched
    ]
    difference_rows = [
        {
            "reference_time_s": value["reference_time_s"],
            "even_absolute_cfo_hz": value["difference_hz"],
        }
        for value in matched
    ]
    difference_fit = fit_line(difference_rows)
    differences = np.asarray([float(value["difference_hz"]) for value in matched])
    sample_offsets = np.asarray([int(value["frame_start_offset_samples"]) for value in matched])
    return {
        "row_basis": "even_fold_research_supported",
        "exact_frame_start_match_count": exact_match_count,
        "within_two_sample_frame_match_count": len(matched),
        "maximum_absolute_frame_start_offset_samples": int(np.max(np.abs(sample_offsets))),
        "frame_start_offset_counts": dict(
            sorted(Counter(int(value) for value in sample_offsets).items())
        ),
        "rx1_matched_frame_fit": fit_line(rx1_fit_rows),
        "rx0_minus_rx1_fit": difference_fit,
        "rx0_minus_rx1_median_hz": float(np.median(differences)),
        "rx0_minus_rx1_standard_deviation_hz": float(np.std(differences)),
    }


def main() -> None:
    args = arguments()
    tool_path = Path(__file__).resolve()
    tool_sha256_at_start = sha256(tool_path)
    config_sha256 = canonical_sha256(scientific_config())
    input_sha256_at_start = verify_frozen_provenance()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output root is nonempty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    rx1_evidence = load_object(RX1_EVIDENCE)
    dealiased = load_object(RX0_DEALIASED_BANK)
    final = load_object(RX0_FINAL_BANK)
    if rx1_evidence["trajectory"]["trajectory_id"] != RX1_TRAJECTORY_ID:
        raise ValueError("RX1 evidence trajectory changed")
    branch = next(value for value in dealiased["branches"] if value["branch_id"] == RX0_BRANCH_ID)
    trajectory = next(
        value for value in final["trajectories"] if value["trajectory_id"] == RX0_TRAJECTORY_ID
    )
    if not (
        int(trajectory["alias_index"]) == 2
        and int(trajectory["polynomial_degree"]) == 1
        and trajectory["branch_id"] == RX0_BRANCH_ID
        and len(branch["observation_ids"]) == 67
    ):
        raise ValueError("RX0 source branch geometry changed")
    slope, at_reference = (float(value) for value in trajectory["absolute_coefficients_hz"])
    reference_time_s = float(trajectory["reference_time_s"])

    anchors = [
        value
        for value in rx1_evidence["anchors"]
        if COMMON_START_S
        <= int(value["acquisition_start_sample"]) / SAMPLE_RATE_HZ
        <= COMMON_STOP_S
    ]
    if len(anchors) != 15:
        raise ValueError("expected 15 RX1 primary anchors in the common interval")

    searches: list[dict[str, Any]] = []
    iq_by_anchor: dict[str, np.ndarray] = {}
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(Path("/srv/bulk/leo")))
        reader = store.reader(store.inspect(SESSION_ID), STREAM_ID, verify=True)
        continuity = next(
            value
            for value in load_object(RECORDING_MANIFEST)["streams"]
            if value["stream_id"] == STREAM_ID
        )["continuity"]
        if not (
            reader.sample_rate_hz == SAMPLE_RATE_HZ
            and 0 in reader.receiver_ids
            and continuity["sample_loss_observable"]
            and continuity["gap_count"] == 0
            and continuity["missing_sample_count"] == 0
            and continuity["overflow_count"] == 0
            and continuity["device_span_sample_count"] == continuity["observed_sample_count"]
        ):
            raise ValueError("RX0 recording is not counter-authoritatively contiguous")
        if reader.gap_map().boundaries:
            raise ValueError("RX0 recording unexpectedly has a gap-map boundary")
        timeline = tuple(reader.iter_timeline_metadata())
        refill_markers = tuple(value.session_sample_start for value in timeline[1:])

        for anchor in anchors:
            start = int(anchor["acquisition_start_sample"])
            raw = reader.read(start, PROBE_SAMPLES, receiver_ids=(0,))
            iq = _complex_receiver(raw)
            anchor_id = str(anchor["anchor_id"])
            iq_by_anchor[anchor_id] = iq
            anchor_time_s = start / SAMPLE_RATE_HZ
            seed = at_reference + slope * (anchor_time_s - reference_time_s)
            alignment = align_known_pilot_frames(
                iq,
                SAMPLE_RATE_HZ,
                absolute_cfo_hz=seed,
                edge=StarlinkEdge.UPPER,
                nominal_epoch_sample=int(anchor["local_epoch_sample"]),
                cfo_search_radius_hz=LOCAL_CFO_RADIUS_HZ,
                cfo_search_step_hz=LOCAL_CFO_STEP_HZ,
                minimum_exact_score=0.02,
                minimum_exact_minus_control_margin=0.0,
                minimum_frame_support=2,
                retained_candidate_count=8,
                candidate_epoch_separation_samples=20,
                candidate_cfo_separation_hz=500.0,
            )
            searches.append(_alignment_document(anchor, alignment, seed))
    finally:
        if store is not None:
            store.close()

    receiver_delay = estimate_receiver_delay(searches)
    by_search = {str(value["anchor_id"]): value for value in searches}
    ledger_rows: list[dict[str, Any]] = []
    accepted_anchors = []
    for anchor in anchors:
        anchor_id = str(anchor["anchor_id"])
        search = by_search[anchor_id]
        accepted = target_bound(search, receiver_delay_samples=receiver_delay)
        search["target_bound"] = accepted
        search["split"] = (
            "first_60_percent"
            if float(search["anchor_time_s"]) < SPLIT_TIME_S
            else "final_40_percent"
        )
        if not accepted:
            continue
        accepted_anchors.append(anchor_id)
        start = int(anchor["acquisition_start_sample"])
        rx0_anchor = FrameRecoveryAnchor(
            anchor_id=anchor_id,
            sample_source_id=f"{SESSION_ID}:{STREAM_ID}:receiver-0",
            canonical_observation_id=RX0_TRAJECTORY_ID,
            source_observation_id=f"rx1-primary:{anchor_id}",
            continuity_source_id=RX0_BRANCH_ID,
            edge=StarlinkEdge.UPPER,
            cfo_alias_index=2,
            epoch_sample=start + int(search["rx0_local_epoch_sample"]),
            acquisition_absolute_cfo_hz=float(search["rx0_aligned_cfo_hz"]),
            ownership_start_sample=start,
            ownership_stop_sample=start + PROBE_SAMPLES,
        )
        result = recover_contiguous_frames(
            iq_by_anchor[anchor_id],
            sample_start=start,
            sample_rate_hz=SAMPLE_RATE_HZ,
            anchors=(rx0_anchor,),
            refill_boundaries=(),
            config=FrameRecoveryConfig(),
        )
        ledger_rows.extend(_frame_document(anchor_id, value) for value in result.frames)

    research_supported = [
        value
        for value in ledger_rows
        if value["outcome"] == FrameOpportunityOutcome.SUPPORTED.value
        and value["training_supported"] is True
        and value["even_absolute_cfo_hz"] is not None
    ]
    research_calibration = [
        value for value in research_supported if float(value["reference_time_s"]) < SPLIT_TIME_S
    ]
    research_evaluated = [
        value for value in research_supported if float(value["reference_time_s"]) >= SPLIT_TIME_S
    ]
    research_calibration_fit = fit_line(research_calibration)
    medians = anchor_medians(research_supported)
    median_train = [value for value in medians if float(value["reference_time_s"]) < SPLIT_TIME_S]
    median_evaluated = [
        value for value in medians if float(value["reference_time_s"]) >= SPLIT_TIME_S
    ]
    median_train_fit = fit_line(median_train)
    primary_supported = [
        value
        for value in ledger_rows
        if value["primary_supported"] is True and value["primary_absolute_cfo_hz"] is not None
    ]
    primary_calibration = [
        value for value in primary_supported if float(value["reference_time_s"]) < SPLIT_TIME_S
    ]
    primary_evaluated = [
        value for value in primary_supported if float(value["reference_time_s"]) >= SPLIT_TIME_S
    ]
    primary_rejected = [
        value
        for value in ledger_rows
        if value["outcome"] == FrameOpportunityOutcome.SUPPORTED.value
        and value["primary_supported"] is False
    ]
    primary_rejection_reason_counts = Counter(
        reason for value in primary_rejected for reason in value["primary_rejection_reasons"]
    )
    primary_calibration_fit = fit_line(primary_calibration, cfo_key="primary_absolute_cfo_hz")
    expected_counts = (
        len(research_supported),
        len(research_calibration),
        len(research_evaluated),
        len(primary_supported),
        len(primary_calibration),
        len(primary_evaluated),
        len(primary_rejected),
    )
    if expected_counts != (126, 70, 56, 117, 66, 51, 9):
        raise ValueError(f"frozen RX0 replay support counts changed: {expected_counts}")

    crossing_windows = sum(
        any(
            int(anchor["acquisition_start_sample"])
            < marker
            < int(anchor["acquisition_start_sample"]) + PROBE_SAMPLES
            for marker in refill_markers
        )
        for anchor in anchors
    )
    summary = {
        "schema": "org.leo.research.rx0-cross-receiver-anchor-replay/v1",
        "candidate_only": True,
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "stream_id": STREAM_ID,
        "receiver_id": 0,
        "edge": StarlinkEdge.UPPER.value,
        "common_interval_s": [COMMON_START_S, COMMON_STOP_S],
        "utc_split_time_s": SPLIT_TIME_S,
        "selection": {
            "primary_rx1_anchor_count": len(anchors),
            "accepted_anchor_count": len(accepted_anchors),
            "accepted_first_60_percent_count": sum(
                float(by_search[value]["anchor_time_s"]) < SPLIT_TIME_S
                for value in accepted_anchors
            ),
            "accepted_final_40_percent_count": sum(
                float(by_search[value]["anchor_time_s"]) >= SPLIT_TIME_S
                for value in accepted_anchors
            ),
            "calibrated_rx0_minus_rx1_epoch_samples": receiver_delay,
            "target_minimum_exact_score": MINIMUM_TARGET_EXACT_SCORE,
            "calibration_minimum_exact_minus_control_margin": MINIMUM_CALIBRATION_MARGIN,
            "target_required_exact_minus_control_positive": True,
            "maximum_delay_residual_samples": MAXIMUM_DELAY_RESIDUAL_SAMPLES,
            "full_frame_epoch_hypothesis_count": math.ceil(FRAME_PERIOD_SAMPLES),
            "local_cfo_radius_hz": LOCAL_CFO_RADIUS_HZ,
            "local_cfo_step_hz": LOCAL_CFO_STEP_HZ,
            "searches": searches,
        },
        "frame_replay": {
            "opportunity_count": len(ledger_rows),
            "outcome_counts": dict(
                sorted(Counter(value["outcome"] for value in ledger_rows).items())
            ),
            "even_fold_research_support": {
                "frame_count": len(research_supported),
                "first_60_percent_calibration_count": len(research_calibration),
                "final_40_percent_evaluated_conditional_count": len(research_evaluated),
                "fit_all": fit_line(research_supported),
                "fit_first_60_percent": research_calibration_fit,
                "final_40_percent_evaluated_conditional_prediction_rms_hz": (
                    prediction_rms(research_evaluated, research_calibration_fit)
                ),
                "anchor_median_fit_all": fit_line(medians),
                "anchor_median_fit_first_60_percent": median_train_fit,
                "anchor_median_final_40_percent_evaluated_conditional_prediction_rms_hz": (
                    prediction_rms(median_evaluated, median_train_fit)
                ),
                "anchor_medians": medians,
                "status": (
                    "even-Qin membership and filter support in a research companion; "
                    "not the primary frame-CFO contract"
                ),
            },
            "primary_contract_support": {
                "frame_count": len(primary_supported),
                "first_60_percent_calibration_count": len(primary_calibration),
                "final_40_percent_evaluated_conditional_count": len(primary_evaluated),
                "rejected_research_supported_frame_count": len(primary_rejected),
                "rejection_reason_counts": dict(sorted(primary_rejection_reason_counts.items())),
                "fit_all": fit_line(primary_supported, cfo_key="primary_absolute_cfo_hz"),
                "fit_first_60_percent": primary_calibration_fit,
                "final_40_percent_evaluated_conditional_prediction_rms_hz": (
                    prediction_rms(
                        primary_evaluated,
                        primary_calibration_fit,
                        cfo_key="primary_absolute_cfo_hz",
                    )
                ),
            },
        },
        "existing_rx0_branch": {
            "branch_id": RX0_BRANCH_ID,
            "trajectory_id": RX0_TRAJECTORY_ID,
            "observation_count": len(branch["observation_ids"]),
            "time_start_s": float(branch["start_s"]),
            "time_stop_s": float(branch["end_s"]),
            "slope_hz_s": float(branch["model"]["coefficients_hz"][0]),
            "residual_rms_hz": float(branch["model"]["residual_rms_hz"]),
            "observed_alias_indices": list(branch["observed_alias_indices"]),
            "final_alias_index": int(trajectory["alias_index"]),
            "alias_spacing_hz": ALIAS_SPACING_HZ,
            "reconstruction_rule": "component_cfo_hz + final_alias_index * (sample_rate_hz / 11)",
        },
        "cross_receiver": _cross_receiver_summary(research_supported, _load_rx1_rows()),
        "counter_continuity": {
            **{
                key: continuity[key]
                for key in (
                    "sample_loss_observable",
                    "observed_sample_count",
                    "device_span_sample_count",
                    "gap_count",
                    "missing_sample_count",
                    "overflow_count",
                    "clipped_sample_count",
                    "constant_iq_refill_count",
                    "refill_count",
                )
            },
            "gap_map_boundary_count": 0,
            "primary_windows_crossing_counter_contiguous_refill_markers": crossing_windows,
            "refill_interpretation": (
                "audit markers only; counter continuity authorizes no analysis reset"
            ),
        },
        "provenance": {
            "tool_sha256": tool_sha256_at_start,
            "scientific_config_sha256": config_sha256,
            "input_sha256": input_sha256_at_start,
            "rx1_evidence_to_rows_linkage": {
                "evidence_declared_decompressed_rows_sha256": rx1_evidence["artifacts"][
                    "frame_rows_sha256"
                ],
                "verified_decompressed_rows_sha256": input_sha256_at_start[
                    "rx1_long_frame_rows_decompressed"
                ],
            },
        },
        "interpretation_limits": [
            (
                "126 even-fold research-supported rows are clustered inside nine 20 ms "
                "anchors and are not 126 independent epochs"
            ),
            (
                "117 rows pass the stricter primary frame-CFO contract; primary support "
                "is authoritative for ordinary qualified-point claims"
            ),
            (
                "the replay improves conditional frame-CFO precision and exact-frame "
                "cross-receiver registration, not independent temporal coverage"
            ),
            (
                "local alignment and frame membership use Qin symbols; this is not an "
                "untouched end-to-end validation fold"
            ),
            "the source/alias branch is candidate-only and does not establish a satellite identity",
            "RX0 and RX1 share one Pluto sample counter/LO domain and are not independent clocks",
        ],
    }

    rows_path = output_root / "rx0-frame-ledger.jsonl"
    with rows_path.open("w", encoding="utf-8") as destination:
        for value in ledger_rows:
            destination.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    summary["artifacts"] = {
        "rx0_frame_ledger": rows_path.name,
        "rx0_frame_ledger_sha256": sha256(rows_path),
    }
    summary_path = output_root / "rx0-cross-receiver-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        summary_path.name: {"sha256": sha256(summary_path), "bytes": summary_path.stat().st_size},
        rows_path.name: {"sha256": sha256(rows_path), "bytes": rows_path.stat().st_size},
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if verify_frozen_provenance() != input_sha256_at_start:
        raise ValueError("frozen input digests changed during RX0 replay")
    if sha256(tool_path) != tool_sha256_at_start:
        raise ValueError("RX0 replay tool changed during execution")
    runtime_s = time.perf_counter() - started
    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "accepted_anchor_count": len(accepted_anchors),
                "even_fold_research_supported_frame_count": len(research_supported),
                "primary_contract_supported_frame_count": len(primary_supported),
                "primary_contract_fit_all": summary["frame_replay"]["primary_contract_support"][
                    "fit_all"
                ],
                "cross_receiver": summary["cross_receiver"],
                "runtime_s": runtime_s,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
