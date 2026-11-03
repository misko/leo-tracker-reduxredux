#!/usr/bin/env python3
"""Bounded read-only pilot-CFO precision diagnostic for the frozen DS10 scan."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np


SESSION_ID = "scan-fw-df44e74320bd2718"
INPUT_MANIFEST_SHA256 = "sha256:1cfa5e7197493484aba30c3ac7c850c5678057e6412a88553c064a3c89fd22b6"
ANALYSIS_MANIFEST_SHA256 = "sha256:21eb179037648a0981ed9b9864ca70d2a98ff238143e499ad27e97a46c41593c"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_VISIT_COUNT = 32
DEFAULT_BUDGET_S = 165.0
MAX_BUDGET_S = 165.0
READ_GUARD_S = 15.0
FLUSH_GUARD_S = 3.0
FRAME_RATE_HZ = 750.0
OFDM_SYMBOL_DURATION_S = 4.4e-6
FULL_ALIAS_HZ = 1.0 / OFDM_SYMBOL_DURATION_S
NATIVE_RESIDUAL_BIN_HZ = 1.0 / (512.0 * OFDM_SYMBOL_DURATION_S)
CLASS_ORDER = {"edge": 0, "plus_or_minus_one": 1, "other_nonzero": 2, "zero": 3}


@dataclass(frozen=True, slots=True)
class CandidateProbe:
    visit_index: int
    receiver_id: int
    receiver_axis: int
    probe_index: int
    probe_start_ms: int
    channel: int
    edge: str
    candidate_rank: int
    integer_epoch_sample: int
    integer_session_sample: int
    fractional_epoch_offset_samples: float
    acquired_cfo_hz: float
    native_residual_cfo_hz: float
    persisted_tracking_cfo_hz: float
    fractional_margin: float


def circular_difference_hz(left: float, right: float, alias_hz: float = FULL_ALIAS_HZ) -> float:
    """Return ``left-right`` on the canonical full-OFDM alias interval."""

    if not all(math.isfinite(value) for value in (left, right, alias_hz)) or alias_hz <= 0:
        raise ValueError("CFO values and alias_hz must be finite, with alias_hz positive")
    difference = (left - right + 0.5 * alias_hz) % alias_hz - 0.5 * alias_hz
    if difference == -0.5 * alias_hz and left - right > 0:
        return 0.5 * alias_hz
    return float(difference)


def classify_native_residual(residual_cfo_hz: float) -> str:
    """Describe the persisted native residual bin without treating it as precision."""

    if not math.isfinite(residual_cfo_hz):
        raise ValueError("native residual CFO must be finite")
    if abs(residual_cfo_hz) <= 1e-9:
        return "zero"
    native_bin = int(round(residual_cfo_hz / NATIVE_RESIDUAL_BIN_HZ))
    on_native_bin = math.isclose(
        residual_cfo_hz,
        native_bin * NATIVE_RESIDUAL_BIN_HZ,
        rel_tol=0.0,
        abs_tol=1e-6,
    )
    if on_native_bin and abs(native_bin) == 1:
        return "plus_or_minus_one"
    if on_native_bin and 251 <= abs(native_bin) <= 256:
        return "edge"
    return "other_nonzero"


def _visit_class(probes: Sequence[CandidateProbe]) -> str:
    return min(
        (classify_native_residual(probe.native_residual_cfo_hz) for probe in probes),
        key=CLASS_ORDER.__getitem__,
    )


def select_paired_visits(
    probes: Iterable[CandidateProbe], *, maximum_visits: int = DEFAULT_VISIT_COUNT, time_bins: int = 4
) -> tuple[tuple[CandidateProbe, CandidateProbe], ...]:
    """Select deterministic paired-RX visits across time, channel, and residual class."""

    if not 0 < maximum_visits <= DEFAULT_VISIT_COUNT:
        raise ValueError("maximum_visits must lie in [1, 32]")
    if time_bins < 1:
        raise ValueError("time_bins must be positive")
    by_visit: dict[int, dict[int, CandidateProbe]] = defaultdict(dict)
    for probe in probes:
        receivers = by_visit[probe.visit_index]
        if probe.receiver_id in receivers:
            raise ValueError("duplicate receiver candidate within a visit")
        receivers[probe.receiver_id] = probe
    paired = {
        visit: (receivers[0], receivers[1])
        for visit, receivers in by_visit.items()
        if set(receivers) == {0, 1}
    }
    if not paired:
        raise ValueError("no paired receiver visits are available")
    ordered_visits = sorted(paired)
    time_bin_by_visit = {
        visit: min(time_bins - 1, index * time_bins // len(ordered_visits))
        for index, visit in enumerate(ordered_visits)
    }
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for visit in ordered_visits:
        pair = paired[visit]
        if pair[0].channel != pair[1].channel or pair[0].probe_index != pair[1].probe_index:
            raise ValueError("paired receiver visit metadata differs")
        native_class = _visit_class(pair)
        key = (CLASS_ORDER[native_class], pair[0].channel, time_bin_by_visit[visit])
        buckets[key].append(visit)
    visit_dimensions = {
        visit: (
            _visit_class(paired[visit]),
            paired[visit][0].channel,
            time_bin_by_visit[visit],
        )
        for visit in ordered_visits
    }
    available_dimensions = tuple(
        {dimensions[index] for dimensions in visit_dimensions.values()} for index in range(3)
    )
    covered = [set(), set(), set()]
    selected: list[int] = []
    remaining = set(ordered_visits)
    selection_limit = min(maximum_visits, len(ordered_visits))
    while len(selected) < selection_limit and any(
        covered[index] != available_dimensions[index] for index in range(3)
    ):
        def coverage_key(visit):
            dimensions = visit_dimensions[visit]
            new = tuple(dimensions[index] not in covered[index] for index in range(3))
            return (
                sum(new),
                int(new[0]),
                int(new[1]),
                int(new[2]),
                -CLASS_ORDER[dimensions[0]],
                -visit,
            )

        chosen = max(remaining, key=coverage_key)
        selected.append(chosen)
        remaining.remove(chosen)
        for index, value in enumerate(visit_dimensions[chosen]):
            covered[index].add(value)
    fill_buckets = {
        key: [visit for visit in visits if visit in remaining]
        for key, visits in buckets.items()
    }
    keys = sorted(fill_buckets)
    cursor = 0
    while len(selected) < selection_limit:
        progressed = False
        for key in keys:
            if cursor < len(fill_buckets[key]):
                visit = fill_buckets[key][cursor]
                selected.append(visit)
                remaining.remove(visit)
                progressed = True
                if len(selected) == selection_limit:
                    break
        if not progressed:
            break
        cursor += 1
    return tuple(paired[visit] for visit in sorted(selected))


def _finite(value) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _status_text(value) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _three_frame_windows(probe: CandidateProbe, sample_rate_hz: float, sample_count: int):
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    rounded_offset = int(round(probe.fractional_epoch_offset_samples))
    windows = []
    frame_index = 0
    while True:
        frame_delta = round(frame_index * sample_rate_hz / FRAME_RATE_HZ)
        local_start = probe.integer_epoch_sample + rounded_offset + frame_delta
        if local_start + frame_content >= sample_count:
            break
        if local_start >= 1:
            windows.append(
                (
                    frame_index,
                    local_start,
                    probe.integer_session_sample + rounded_offset + frame_delta,
                    frame_content,
                )
            )
        frame_index += 1
    if not windows:
        return ()
    indexes = tuple(dict.fromkeys((0, len(windows) // 2, len(windows) - 1)))
    return tuple(windows[index] for index in indexes)


def _frame_receipt(estimate, probe: CandidateProbe, frame_index: int, local_start: int) -> dict:
    absolute_cfo_hz = _finite(getattr(estimate, "absolute_cfo_hz", None))
    persisted_difference = (
        None
        if absolute_cfo_hz is None
        else circular_difference_hz(absolute_cfo_hz, probe.persisted_tracking_cfo_hz)
    )
    return {
        "frame_index": int(frame_index),
        "local_integer_frame_start_sample": int(local_start),
        "status": _status_text(getattr(estimate, "status", "unknown")),
        "measurement_supported": bool(getattr(estimate, "measurement_supported", False)),
        "rejection_reasons": list(getattr(estimate, "rejection_reasons", ())),
        "residual_from_persisted_cfo_hz": _finite(getattr(estimate, "residual_cfo_hz", None)),
        "absolute_cfo_hz": absolute_cfo_hz,
        "circular_difference_from_persisted_cfo_hz": persisted_difference,
        "frequency_uncertainty_hz": _finite(
            getattr(estimate, "frequency_uncertainty_hz", None)
        ),
        "exact_coherence": _finite(getattr(estimate, "exact_coherence", None)),
        "control_coherence": _finite(getattr(estimate, "control_coherence", None)),
        "coherence_margin": _finite(getattr(estimate, "coherence_margin", None)),
        "even_residual_cfo_hz": _finite(getattr(estimate, "even_residual_cfo_hz", None)),
        "odd_residual_cfo_hz": _finite(getattr(estimate, "odd_residual_cfo_hz", None)),
        "even_odd_disagreement_hz": _finite(
            getattr(estimate, "even_odd_disagreement_hz", None)
        ),
        "timing_spread_hz": _finite(getattr(estimate, "timing_spread_hz", None)),
        "half_frame_difference_z": _finite(
            getattr(estimate, "half_frame_difference_z", None)
        ),
        "tone_deletion_spread_hz": _finite(
            getattr(estimate, "tone_deletion_spread_hz", None)
        ),
        "search_boundary": bool(getattr(estimate, "search_boundary", False)),
    }


def _median(values: Sequence[float]) -> float | None:
    return None if not values else float(np.median(np.asarray(values, dtype=float)))


def _probe_summary(frames: Sequence[Mapping]) -> dict:
    complete = [frame for frame in frames if frame.get("absolute_cfo_hz") is not None]
    differences = [float(frame["circular_difference_from_persisted_cfo_hz"]) for frame in complete]
    supported = [frame for frame in complete if frame["measurement_supported"]]
    uncertainties = [float(frame["frequency_uncertainty_hz"]) for frame in complete]
    return {
        "requested_frame_count": 3,
        "returned_frame_count": len(frames),
        "complete_frame_count": len(complete),
        "supported_frame_count": len(supported),
        "median_circular_difference_from_persisted_cfo_hz": _median(differences),
        "frame_difference_range_hz": (
            None if not differences else float(max(differences) - min(differences))
        ),
        "median_frequency_uncertainty_hz": _median(uncertainties),
        "median_timing_spread_hz": _median(
            [float(frame["timing_spread_hz"]) for frame in complete]
        ),
        "median_exact_coherence": _median(
            [float(frame["exact_coherence"]) for frame in complete]
        ),
        "median_control_coherence": _median(
            [float(frame["control_coherence"]) for frame in complete]
        ),
        "median_coherence_margin": _median(
            [float(frame["coherence_margin"]) for frame in complete]
        ),
        "median_even_odd_disagreement_hz": _median(
            [float(frame["even_odd_disagreement_hz"]) for frame in complete]
        ),
        "median_half_frame_difference_z": _median(
            [float(frame["half_frame_difference_z"]) for frame in complete]
        ),
    }


def _probe_base(probe: CandidateProbe) -> dict:
    native_bin = int(round(probe.native_residual_cfo_hz / NATIVE_RESIDUAL_BIN_HZ))
    rounded_offset = int(round(probe.fractional_epoch_offset_samples))
    return {
        **asdict(probe),
        "native_residual_class": classify_native_residual(probe.native_residual_cfo_hz),
        "native_residual_bin": native_bin,
        "native_residual_bin_hz_for_classification_only": NATIVE_RESIDUAL_BIN_HZ,
        "persisted_cfo_closure_error_hz": (
            probe.acquired_cfo_hz
            + probe.native_residual_cfo_hz
            - probe.persisted_tracking_cfo_hz
        ),
        "rounded_fractional_epoch_offset_samples": rounded_offset,
        "fractional_epoch_rounding_error_samples": (
            rounded_offset - probe.fractional_epoch_offset_samples
        ),
    }


def _distribution(values: Sequence[float]) -> dict:
    if not values:
        return {"count": 0, "median": None, "robust_rms": None, "p95_absolute": None}
    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    return {
        "count": len(values),
        "median": median,
        "robust_rms": float(np.sqrt(np.median(np.square(array - median)))),
        "p95_absolute": float(np.quantile(np.abs(array), 0.95)),
    }


def _summaries(probe_receipts: Sequence[Mapping]) -> dict:
    processed = [receipt for receipt in probe_receipts if receipt["state"] in ("processed", "partial")]
    complete = [
        receipt
        for receipt in processed
        if receipt.get("summary", {}).get("median_circular_difference_from_persisted_cfo_hz")
        is not None
    ]
    differences = [
        float(receipt["summary"]["median_circular_difference_from_persisted_cfo_hz"])
        for receipt in complete
    ]
    by_class = {}
    for native_class in CLASS_ORDER:
        subset = [
            float(receipt["summary"]["median_circular_difference_from_persisted_cfo_hz"])
            for receipt in complete
            if receipt["native_residual_class"] == native_class
        ]
        by_class[native_class] = _distribution(subset)
    by_receiver = {}
    for receiver in (0, 1):
        subset = [
            float(receipt["summary"]["median_circular_difference_from_persisted_cfo_hz"])
            for receipt in complete
            if receipt["receiver_id"] == receiver
        ]
        by_receiver[str(receiver)] = _distribution(subset)
    by_visit = defaultdict(dict)
    for receipt in complete:
        by_visit[int(receipt["visit_index"])][int(receipt["receiver_id"])] = receipt
    pairs = []
    for visit, receivers in sorted(by_visit.items()):
        if set(receivers) != {0, 1}:
            continue
        left, right = receivers[0], receivers[1]
        left_correction = float(
            left["summary"]["median_circular_difference_from_persisted_cfo_hz"]
        )
        right_correction = float(
            right["summary"]["median_circular_difference_from_persisted_cfo_hz"]
        )
        left_refined = left["persisted_tracking_cfo_hz"] + left_correction
        right_refined = right["persisted_tracking_cfo_hz"] + right_correction
        pairs.append(
            {
                "visit_index": visit,
                "rx1_minus_rx0_correction_hz": circular_difference_hz(
                    right_correction, left_correction
                ),
                "persisted_rx1_minus_rx0_cfo_hz_modulo_full_alias": circular_difference_hz(
                    right["persisted_tracking_cfo_hz"], left["persisted_tracking_cfo_hz"]
                ),
                "refined_rx1_minus_rx0_cfo_hz_modulo_full_alias": circular_difference_hz(
                    right_refined, left_refined
                ),
            }
        )
    return {
        "all_probe_corrections_hz": _distribution(differences),
        "by_native_residual_class": by_class,
        "by_receiver": by_receiver,
        "paired_receiver_count": len(pairs),
        "paired_receiver_diagnostics": pairs,
    }


def run_selected_diagnostic(
    selected_pairs: Sequence[tuple[CandidateProbe, CandidateProbe]],
    *,
    sample_rate_hz: float,
    probe_ms: int,
    read_visit: Callable[[int], np.ndarray],
    estimator: Callable[..., object],
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
    checkpoint: Callable[[dict], None] | None = None,
    read_guard_s: float = READ_GUARD_S,
    flush_guard_s: float = FLUSH_GUARD_S,
) -> dict:
    """Read and evaluate selected visits cooperatively, retaining every request."""

    requested = [probe for pair in selected_pairs for probe in pair]
    receipts: dict[tuple[int, int], dict] = {
        (probe.visit_index, probe.receiver_id): {
            **_probe_base(probe),
            "state": "unprocessed",
            "reason": "not_dispatched",
            "frames": [],
        }
        for probe in requested
    }
    visit_reads = []
    failures = []
    actual_iq_bytes = 0
    stopped_reason = None

    def snapshot() -> dict:
        ordered = [receipts[(probe.visit_index, probe.receiver_id)] for probe in requested]
        return {
            "requested_visit_count": len(selected_pairs),
            "requested_probe_count": len(requested),
            "read_visit_count": len(visit_reads),
            "processed_probe_count": sum(row["state"] == "processed" for row in ordered),
            "partial_probe_count": sum(row["state"] == "partial" for row in ordered),
            "unprocessed_probe_count": sum(row["state"] == "unprocessed" for row in ordered),
            "actual_iq_bytes": actual_iq_bytes,
            "stopped_reason": stopped_reason,
            "visit_reads": list(visit_reads),
            "failures": list(failures),
            "probes": ordered,
            "summaries": _summaries(ordered),
        }

    if checkpoint is not None:
        checkpoint(snapshot())
    probe_samples = round(probe_ms * sample_rate_hz / 1000.0)
    for pair in selected_pairs:
        visit_index = pair[0].visit_index
        remaining = deadline - clock()
        if remaining <= read_guard_s:
            stopped_reason = "deadline_guard_before_visit_read"
            for remaining_pair in selected_pairs[selected_pairs.index(pair) :]:
                for probe in remaining_pair:
                    row = receipts[(probe.visit_index, probe.receiver_id)]
                    row["reason"] = stopped_reason
            break
        try:
            ci16 = np.asarray(read_visit(visit_index))
            if ci16.ndim != 3 or ci16.shape[2] != 2:
                raise ValueError("visit IQ must have shape (samples, receivers, 2)")
            actual_iq_bytes += int(ci16.nbytes)
            visit_reads.append(
                {
                    "visit_index": visit_index,
                    "iq_bytes": int(ci16.nbytes),
                    "remaining_before_read_s": float(remaining),
                    "remaining_after_read_s": float(deadline - clock()),
                }
            )
        except Exception as error:
            reason = f"visit_read_failed:{type(error).__name__}:{error}"
            failures.append({"visit_index": visit_index, "stage": "read", "reason": reason})
            for probe in pair:
                receipts[(probe.visit_index, probe.receiver_id)]["reason"] = reason
            if checkpoint is not None:
                checkpoint(snapshot())
            continue
        for probe in pair:
            row = receipts[(probe.visit_index, probe.receiver_id)]
            probe_start = round(probe.probe_start_ms * sample_rate_hz / 1000.0)
            probe_stop = probe_start + probe_samples
            if probe.receiver_axis >= ci16.shape[1] or probe_stop > ci16.shape[0]:
                reason = "probe_slice_outside_visit"
                row["reason"] = reason
                failures.append(
                    {
                        "visit_index": visit_index,
                        "receiver_id": probe.receiver_id,
                        "stage": "slice",
                        "reason": reason,
                    }
                )
                continue
            packed = ci16[probe_start:probe_stop, probe.receiver_axis]
            samples = packed[:, 0].astype(float) + 1j * packed[:, 1].astype(float)
            windows = _three_frame_windows(probe, sample_rate_hz, samples.size)
            row["available_complete_frame_count"] = len(windows)
            if len(windows) != 3:
                row["state"] = "partial"
                row["reason"] = "fewer_than_three_complete_frames"
            else:
                row["state"] = "processed"
                row["reason"] = None
            for frame_index, local_start, absolute_start, frame_content in windows:
                if deadline - clock() <= flush_guard_s:
                    row["state"] = "partial"
                    row["reason"] = "deadline_guard_before_frame_evaluation"
                    stopped_reason = row["reason"]
                    break
                compact = samples[local_start - 1 : local_start + frame_content + 1]
                try:
                    estimate = estimator(
                        compact,
                        sample_rate_hz,
                        frame_start_sample=int(absolute_start),
                        acquisition_absolute_cfo_hz=probe.persisted_tracking_cfo_hz,
                        edge=probe.edge,
                    )
                    row["frames"].append(
                        _frame_receipt(estimate, probe, frame_index, local_start)
                    )
                except Exception as error:
                    reason = f"frame_estimation_failed:{type(error).__name__}:{error}"
                    row["state"] = "partial"
                    row["reason"] = reason
                    failures.append(
                        {
                            "visit_index": visit_index,
                            "receiver_id": probe.receiver_id,
                            "frame_index": frame_index,
                            "stage": "estimate",
                            "reason": reason,
                        }
                    )
            row["summary"] = _probe_summary(row["frames"])
            if stopped_reason is not None:
                break
        if checkpoint is not None:
            checkpoint(snapshot())
        if stopped_reason is not None:
            remaining_visits = False
            for later_pair in selected_pairs:
                if later_pair[0].visit_index <= visit_index:
                    continue
                remaining_visits = True
                for probe in later_pair:
                    receipts[(probe.visit_index, probe.receiver_id)]["reason"] = stopped_reason
            if remaining_visits:
                break
    return snapshot()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _selection_accounting(pairs: Sequence[tuple[CandidateProbe, CandidateProbe]]) -> dict:
    probes = [probe for pair in pairs for probe in pair]
    return {
        "visit_indices": [pair[0].visit_index for pair in pairs],
        "probe_count": len(probes),
        "by_channel": dict(sorted(Counter(probe.channel for probe in probes).items())),
        "by_receiver": dict(sorted(Counter(probe.receiver_id for probe in probes).items())),
        "by_native_residual_class": dict(
            sorted(Counter(classify_native_residual(probe.native_residual_cfo_hz) for probe in probes).items())
        ),
    }


def _runtime_inventory(root: Path):
    from leo.contracts.digests import canonical_digest
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

    iq_store = AdaptiveHopIqStore(root, read_only=True)
    published = iq_store.inspect(SESSION_ID)
    if published.manifest_sha256 != INPUT_MANIFEST_SHA256:
        iq_store.close()
        raise ValueError("DS10 input manifest differs from the frozen bundle")
    receipt = published.manifest.receipt
    binding = bind_actual_visit_analysis(
        receipt,
        input_manifest_sha256=published.manifest_sha256,
        probe_stride_ms=120,
    )
    analysis_store = AdaptiveHopAnalysisStore(root, read_only=True)
    probes = []
    try:
        with analysis_store.job(binding) as job:
            manifest = job.manifest()
            if manifest is None:
                raise ValueError("DS10 analysis manifest is unavailable")
            analysis_digest = canonical_digest(manifest.model_dump(mode="json"))
            if analysis_digest != ANALYSIS_MANIFEST_SHA256:
                raise ValueError("DS10 analysis manifest differs from the frozen bundle")
            receiver_ids = tuple(receipt.plan.geometry.receiver_ids)
            receiver_axis = {receiver: axis for axis, receiver in enumerate(receiver_ids)}
            for product in job.published_visits():
                for probe in product.probes:
                    matches = [
                        candidate
                        for candidate in probe.candidates
                        if candidate.candidate_rank == 0
                        and candidate.passed_fractional_margin_gate
                    ]
                    if len(matches) != 1:
                        continue
                    candidate = matches[0]
                    probes.append(
                        CandidateProbe(
                            visit_index=int(product.visit_index),
                            receiver_id=int(probe.receiver_id),
                            receiver_axis=int(receiver_axis[probe.receiver_id]),
                            probe_index=int(probe.probe_index),
                            probe_start_ms=int(probe.probe_start_ms),
                            channel=int(product.target.channel),
                            edge=str(getattr(product.target.edge, "value", product.target.edge)),
                            candidate_rank=int(candidate.candidate_rank),
                            integer_epoch_sample=int(candidate.integer_epoch_sample),
                            integer_session_sample=int(candidate.integer_session_sample),
                            fractional_epoch_offset_samples=float(
                                candidate.fractional_epoch_offset_samples
                            ),
                            acquired_cfo_hz=float(candidate.acquired_cfo_hz),
                            native_residual_cfo_hz=float(
                                candidate.fractional_residual_cfo_hz
                            ),
                            persisted_tracking_cfo_hz=float(
                                candidate.fractional_tracking_cfo_hz
                            ),
                            fractional_margin=float(candidate.fractional_margin),
                        )
                    )
    finally:
        analysis_store.close()
    return iq_store, published, tuple(probes), int(receipt.plan.geometry.sample_rate_hz), 20


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial-output", type=Path)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    parser.add_argument("--visits", type=int, default=DEFAULT_VISIT_COUNT)
    args = parser.parse_args()
    if not math.isfinite(args.budget_s) or not 0 < args.budget_s <= MAX_BUDGET_S:
        raise ValueError("budget-s must lie in (0, 165]")
    if args.output.exists():
        raise FileExistsError(args.output)
    partial = args.partial_output or args.output.with_name(args.output.stem + ".partial.json")
    started = time.monotonic()
    deadline = started + args.budget_s
    module_path = Path(__file__).resolve()
    current_estimator_path = module_path.parents[2] / "src/leo/analysis/qam/pilot.py"

    from leo.analysis.qam.pilot import estimate_edge_pilot_frame_cfo

    runtime_estimator_path = Path(sys.modules[estimate_edge_pilot_frame_cfo.__module__].__file__).resolve()
    runtime_storage_path = Path(sys.modules["leo.storage.adaptive_hop"].__file__).resolve() if "leo.storage.adaptive_hop" in sys.modules else None
    sources_before = {
        str(module_path): _sha256(module_path),
        str(current_estimator_path): _sha256(current_estimator_path),
        str(runtime_estimator_path): _sha256(runtime_estimator_path),
    }
    iq_store = None
    reader = None
    receipt = None
    try:
        iq_store, published, inventory, sample_rate_hz, probe_ms = _runtime_inventory(
            args.bulk_root
        )
        if runtime_storage_path is None:
            runtime_storage_path = Path(sys.modules["leo.storage.adaptive_hop"].__file__).resolve()
            sources_before[str(runtime_storage_path)] = _sha256(runtime_storage_path)
        selected = select_paired_visits(inventory, maximum_visits=args.visits)
        selection = _selection_accounting(selected)
        reader = iq_store.reader(SESSION_ID, expected=published)

        def read_visit(visit_index: int) -> np.ndarray:
            _, values = reader.read_visit_ci16(visit_index)
            return values

        def checkpoint(progress: dict) -> None:
            _atomic_json(
                partial,
                {
                    "schema": "pilot-cfo-precision-diagnostic-partial/v1",
                    "session_id": SESSION_ID,
                    "input_manifest_sha256": INPUT_MANIFEST_SHA256,
                    "analysis_manifest_sha256": ANALYSIS_MANIFEST_SHA256,
                    "selection": selection,
                    "progress": progress,
                    "elapsed_s": float(time.monotonic() - started),
                    "sealed": False,
                },
            )

        progress = run_selected_diagnostic(
            selected,
            sample_rate_hz=sample_rate_hz,
            probe_ms=probe_ms,
            read_visit=read_visit,
            estimator=estimate_edge_pilot_frame_cfo,
            deadline=deadline,
            checkpoint=checkpoint,
        )
        reader.close()
        reader = None
        manifest_after = iq_store.inspect(SESSION_ID).manifest_sha256
        sources_after = {path: _sha256(Path(path)) for path in sources_before}
        receipt = {
            "schema": "pilot-cfo-precision-diagnostic/v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "session_id": SESSION_ID,
            "input_manifest_sha256": INPUT_MANIFEST_SHA256,
            "input_manifest_sha256_after": manifest_after,
            "analysis_manifest_sha256": ANALYSIS_MANIFEST_SHA256,
            "selection_policy": (
                "Gate-passing rank-0 candidates only; require paired receivers for one visit/probe; "
                "round-robin deterministic strata over native residual class, channel, and four "
                "chronological bins. No truth, TLE, satellite prediction, fit error, or geographic "
                "result participates."
            ),
            "selection": selection,
            "configuration": {
                "requested_visit_limit": args.visits,
                "frames_per_probe": 3,
                "frame_positions": "first, middle, last complete rounded-epoch frame",
                "estimator_center": "persisted fractional tracking CFO",
                "full_alias_hz": FULL_ALIAS_HZ,
                "native_residual_bin_hz_for_classification_only": NATIVE_RESIDUAL_BIN_HZ,
                "cooperative_budget_s": args.budget_s,
                "external_wall_limit_required_s": 180,
                "read_guard_s": READ_GUARD_S,
                "flush_guard_s": FLUSH_GUARD_S,
            },
            "progress": progress,
            "elapsed_s": float(time.monotonic() - started),
            "provenance": {
                "sources_before_sha256": sources_before,
                "sources_after_sha256": sources_after,
                "sources_unchanged": sources_before == sources_after,
                "python_executable": sys.executable,
                "runtime_estimator_path": str(runtime_estimator_path),
                "current_repo_estimator_path": str(current_estimator_path),
                "runtime_estimator_matches_current_repo": (
                    sources_before[str(runtime_estimator_path)]
                    == sources_before[str(current_estimator_path)]
                ),
                "runtime_storage_path": str(runtime_storage_path),
                "python_runtime_provenance_qualified": False,
                "native_geometry_reexecuted": False,
            },
            "scientific_scope": {
                "read_only_existing_iq": True,
                "rf_collection_performed": False,
                "truth_accessed": False,
                "tle_accessed": False,
                "satellite_predictions_accessed": False,
                "geographic_fit_accessed": False,
                "calibration_claimed": False,
                "precision_floor_claimed": False,
                "interpretation": (
                    "Observable agreement and dispersion of an acquisition-bound known-pilot CFO "
                    "estimator around persisted candidates. Native residual bins and the 100 Hz "
                    "conditioned search are recorded as algorithm geometry, not measurement floors."
                ),
            },
            "sealed": True,
        }
        if manifest_after != INPUT_MANIFEST_SHA256:
            raise RuntimeError("input manifest changed during the diagnostic")
        if sources_before != sources_after:
            raise RuntimeError("diagnostic source changed before seal")
        with args.output.open("x") as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.write("\n")
        _atomic_json(partial, receipt)
    finally:
        if reader is not None:
            reader.close()
        if iq_store is not None:
            iq_store.close()
    if receipt is None:
        raise RuntimeError("diagnostic did not produce a receipt")
    print(json.dumps({
        "output": str(args.output),
        "elapsed_s": receipt["elapsed_s"],
        "requested_probes": receipt["progress"]["requested_probe_count"],
        "processed_probes": receipt["progress"]["processed_probe_count"],
        "partial_probes": receipt["progress"]["partial_probe_count"],
        "stopped_reason": receipt["progress"]["stopped_reason"],
    }, allow_nan=False))


if __name__ == "__main__":
    main()
