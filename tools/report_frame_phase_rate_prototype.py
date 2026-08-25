#!/usr/bin/env python3
"""Evaluate optional iterative frame phase/timing on the pinned CFO dwells."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

import leo.analysis.qam.pilot as pilot_implementation  # noqa: E402
import leo.analysis.research.frame_phase_rate as phase_rate_implementation  # noqa: E402
from leo.analysis.qam import estimate_edge_pilot_frame_complex_split  # noqa: E402
from leo.analysis.research.frame_cfo_dwell_prototype import (  # noqa: E402
    PrototypeProbe,
    PrototypeRegion,
    PrototypeRegionRole,
    frame_opportunities,
)
from leo.analysis.research.frame_phase_rate import (  # noqa: E402
    FramePhaseRateConfig,
    FramePhaseRateObservation,
    FramePhaseRateResult,
    fit_iterative_frame_phase_rate,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

DEFAULT_CFO_ROOT = Path("reports/figures/2026_08_25_frame_cfo_dwell_prototype")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_frame_phase_rate_prototype")
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
GRAY = "#728694"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--frame-cfo-root", type=Path, default=DEFAULT_CFO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--phase", choices=("all", "explore", "confirm"), default="all")
    parser.add_argument("--labels", nargs="*")
    parser.add_argument("--maximum-regions", type=int, default=6)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return np.asarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15),
        dtype=np.complex128,
    )


def _persisted_rows(
    path: Path,
    *,
    expected_phase_by_label: dict[str, str],
) -> dict[tuple[str, str, str, int], dict[str, Any]]:
    output = {}
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            if not isinstance(value, dict) or value.get("schema") != (
                "org.leo.research.frame-cfo-prototype-row/v1"
            ):
                raise ValueError("unsupported frame-CFO prototype row")
            label = str(value["dwell_label"])
            if label not in expected_phase_by_label:
                raise ValueError("frame-CFO row names an undeclared dwell")
            if value.get("phase") != expected_phase_by_label[label]:
                raise ValueError("frame-CFO row phase disagrees with its dwell inventory")
            key = (
                label,
                str(value["trajectory_id"]),
                str(value["region_id"]),
                int(value["frame_start_sample"]),
            )
            if key in output:
                raise ValueError("frame-CFO artifact contains a duplicate row identity")
            output[key] = value
    if not output:
        raise ValueError("frame-CFO artifact contains no rows")
    return output


def _even_only_trajectory_id(
    dwell: dict[str, Any],
    rows: dict[tuple[str, str, str, int], dict[str, Any]],
) -> str:
    """Select the alias without consulting all-symbol or odd-Qin results."""

    label = str(dwell["label"])
    region_ids = {str(item["region_id"]) for item in dwell["regions"]}
    ranked = []
    for hypothesis in dwell.get("hypotheses", ()):
        trajectory_id = str(hypothesis["trajectory_id"])
        selected = [
            value
            for key, value in rows.items()
            if key[0] == label and key[1] == trajectory_id and key[2] in region_ids
        ]
        if not selected:
            raise ValueError("trajectory hypothesis has no persisted frame rows")
        split = [value.get("split_validation") for value in selected]
        split_rows = [value for value in split if isinstance(value, dict)]
        if not split_rows:
            raise ValueError("trajectory hypothesis lacks parity-split validation")
        supported = sum(bool(value.get("training_supported")) for value in split_rows)
        complete = sum(value.get("status") == "complete" for value in split_rows)
        margin_sum = sum(
            max(0.0, float(value["even_coherence_margin"]))
            for value in split_rows
            if value.get("even_coherence_margin") is not None
        )
        if not math.isfinite(margin_sum):
            raise ValueError("even-Qin alias score is nonfinite")
        ranked.append(
            (
                supported,
                complete,
                margin_sum,
                -abs(int(hypothesis["alias_index"])),
                trajectory_id,
            )
        )
    if not ranked:
        raise ValueError("dwell inventory contains no trajectory hypotheses")
    return max(ranked)[-1]


def _region(value: dict[str, Any]) -> PrototypeRegion:
    return PrototypeRegion(
        region_id=str(value["region_id"]),
        role=PrototypeRegionRole(value["role"]),
        probe=PrototypeProbe(**value["probe"]),
        sample_start=int(value["sample_start"]),
        sample_count=int(value["sample_count"]),
        strong_glrt_region=bool(value["strong_glrt_region"]),
        refill_boundary_sample=(
            None
            if value["refill_boundary_sample"] is None
            else int(value["refill_boundary_sample"])
        ),
    )


def _partition_locklets(
    observations: tuple[FramePhaseRateObservation, ...],
    *,
    sample_rate_hz: float,
    maximum_gap_s: float,
) -> tuple[tuple[FramePhaseRateObservation, ...], ...]:
    supported = tuple(
        sorted(
            (item for item in observations if item.training_supported),
            key=lambda item: (item.continuity_segment, item.reference_sample),
        )
    )
    output: list[tuple[FramePhaseRateObservation, ...]] = []
    current: list[FramePhaseRateObservation] = []
    for item in supported:
        split = bool(
            current
            and (
                item.continuity_segment != current[-1].continuity_segment
                or (item.reference_sample - current[-1].reference_sample) / sample_rate_hz
                > maximum_gap_s
            )
        )
        if split:
            output.append(tuple(current))
            current = []
        current.append(item)
    if current:
        output.append(tuple(current))
    return tuple(output)


def _weighted_rms(values: list[float], weights: list[float]) -> float | None:
    if not values:
        return None
    array = np.asarray(values, dtype=float)
    weight = np.asarray(weights, dtype=float)
    return float(math.sqrt(np.sum(weight * array**2) / np.sum(weight)))


def _robust_center(values: np.ndarray, weights: np.ndarray) -> float:
    center = float(np.median(values))
    for _iteration in range(50):
        residual = values - center
        scale = max(5.0, 1.4826 * float(np.median(np.abs(residual))))
        normalized = np.abs(residual) / (1.345 * scale)
        robust = np.ones(len(values), dtype=float)
        tail = normalized > 1.0
        robust[tail] = 1.0 / normalized[tail]
        combined = weights * robust
        updated = float(np.sum(combined * values) / np.sum(combined))
        if abs(updated - center) < 1e-9:
            return updated
        center = updated
    return center


def _result_document(value: FramePhaseRateResult) -> dict[str, object]:
    document = asdict(value)
    document["status"] = value.status.value
    return document


def _locklet_document(
    *,
    label: str,
    phase: str,
    region: PrototypeRegion,
    locklet_index: int,
    observations: tuple[FramePhaseRateObservation, ...],
    model_cfo_hz: dict[int, float],
    sample_rate_hz: float,
    fixed: FramePhaseRateResult,
    iterative: FramePhaseRateResult,
    config: FramePhaseRateConfig,
) -> dict[str, object]:
    frame_by_start = {item.frame_start_sample: item for item in observations}
    usable = tuple(item for item in iterative.frames if item.odd_frequency_error_hz is not None)
    even = np.asarray(
        [frame_by_start[item.frame_start_sample].even_absolute_cfo_hz for item in usable]
    )
    odd = np.asarray(
        [frame_by_start[item.frame_start_sample].odd_absolute_cfo_hz for item in usable],
        dtype=float,
    )
    model = np.asarray([model_cfo_hz[item.frame_start_sample] for item in usable])
    sigma = np.asarray(
        [frame_by_start[item.frame_start_sample].even_frequency_uncertainty_hz for item in usable]
    )
    coherence = np.asarray(
        [frame_by_start[item.frame_start_sample].even_exact_coherence for item in usable]
    )
    weight = coherence / np.maximum(sigma, config.frequency_sigma_floor_hz) ** 2
    if usable:
        centered_model = model + _robust_center(even - model, weight)
        glrt_error = odd - centered_model
        glrt_rms = _weighted_rms(glrt_error.tolist(), weight.tolist())
    else:
        glrt_rms = None
    return {
        "locklet_id": canonical_digest(
            {
                "dwell": label,
                "region_id": region.region_id,
                "locklet_index": locklet_index,
                "first_frame_start_sample": (
                    None if not observations else observations[0].frame_start_sample
                ),
            }
        ),
        "dwell_label": label,
        "phase": phase,
        "region_id": region.region_id,
        "region_role": region.role.value,
        "continuity_segment": (None if not observations else observations[0].continuity_segment),
        "start_sample": None if not observations else observations[0].frame_start_sample,
        "stop_sample": None if not observations else observations[-1].frame_start_sample,
        "frame_count": len(observations),
        "span_s": (
            0.0
            if len(observations) < 2
            else (observations[-1].reference_sample - observations[0].reference_sample)
            / sample_rate_hz
        ),
        "glrt_recentered_odd_cfo_rms_hz": glrt_rms,
        "phase_timing_fixed": _result_document(fixed),
        "phase_timing_iterative": _result_document(iterative),
        "odd_symbols_influenced_locklet_frame_membership_or_fit": False,
        "region_selection_conditioned_on_upstream_glrt_pilot_score": True,
    }


def _summarize_dwell(label: str, phase: str, locklets: list[dict[str, Any]]) -> dict[str, object]:
    complete = [item for item in locklets if item["phase_timing_iterative"]["status"] == "complete"]
    eligible_frames = sum(int(item["frame_count"]) for item in complete)

    def pooled(path: tuple[str, ...], *, policy: str | None = None) -> float | None:
        errors = []
        weights = []
        for item in complete:
            result = item["phase_timing_iterative"]
            fixed = item["phase_timing_fixed"]
            if path == ("glrt",):
                value = item["glrt_recentered_odd_cfo_rms_hz"]
                count = int(result["validation_frame_count"])
                if value is not None and count:
                    errors.append(float(value))
                    weights.append(count)
                continue
            selected = fixed if policy == "fixed" else result
            if path == ("frequency",):
                value = selected["odd_cfo_rms_hz"]
            elif path == ("phase",):
                value = (
                    selected["phase_candidate_odd_cfo_rms_hz"]
                    if selected["phase_feedback_qualified"]
                    else selected["odd_cfo_rms_hz"]
                )
            elif path == ("candidate",):
                value = selected["phase_candidate_odd_cfo_rms_hz"]
            else:
                raise AssertionError(path)
            count = int(selected["validation_frame_count"])
            if value is not None and count:
                errors.append(float(value))
                weights.append(count)
        if not errors:
            return None
        return float(math.sqrt(np.average(np.asarray(errors) ** 2, weights=weights)))

    timing_rates = [
        float(item["phase_timing_iterative"]["relative_timing_rate_samples_s"])
        for item in complete
        if item["phase_timing_iterative"]["relative_timing_rate_samples_s"] is not None
    ]
    return {
        "label": label,
        "phase": phase,
        "locklet_count": len(locklets),
        "complete_locklet_count": len(complete),
        "eligible_frame_count": eligible_frames,
        "timing_fixed_phase_arc_qualified_locklet_count": sum(
            bool(item["phase_timing_fixed"]["phase_arc_qualified"]) for item in complete
        ),
        "timing_fixed_phase_feedback_candidate_locklet_count": sum(
            bool(item["phase_timing_fixed"]["phase_feedback_qualified"]) for item in complete
        ),
        "iterative_timing_phase_arc_qualified_locklet_count": sum(
            bool(item["phase_timing_iterative"]["phase_arc_qualified"]) for item in complete
        ),
        "iterative_timing_phase_feedback_candidate_locklet_count": sum(
            bool(item["phase_timing_iterative"]["phase_feedback_qualified"]) for item in complete
        ),
        "glrt_recentered_odd_cfo_rms_hz": pooled(("glrt",)),
        "frequency_only_odd_cfo_rms_hz": pooled(("frequency",)),
        "timing_fixed_fit_withheld_selected_odd_cfo_rms_hz": pooled(("phase",), policy="fixed"),
        "iterative_timing_fit_withheld_selected_odd_cfo_rms_hz": pooled(
            ("phase",), policy="iterative"
        ),
        "timing_fixed_phase_candidate_odd_cfo_rms_hz": pooled(("candidate",), policy="fixed"),
        "iterative_timing_phase_candidate_odd_cfo_rms_hz": pooled(
            ("candidate",), policy="iterative"
        ),
        "all_complete_candidate_relative_timing_rate_median_samples_s": (
            None if not timing_rates else float(np.median(timing_rates))
        ),
        "all_complete_candidate_relative_timing_rate_p95_abs_samples_s": (
            None if not timing_rates else float(np.percentile(np.abs(timing_rates), 95))
        ),
    }


def _plot(path: Path, dwells: list[dict[str, Any]]) -> None:
    labels = [f"{item['label']} · {'E' if item['phase'] == 'explore' else 'H'}" for item in dwells]
    glrt = np.asarray([item["glrt_recentered_odd_cfo_rms_hz"] for item in dwells], dtype=float)
    frequency = np.asarray([item["frequency_only_odd_cfo_rms_hz"] for item in dwells], dtype=float)
    fixed = np.asarray(
        [item["timing_fixed_phase_candidate_odd_cfo_rms_hz"] for item in dwells],
        dtype=float,
    )
    timing = np.asarray(
        [item["iterative_timing_phase_candidate_odd_cfo_rms_hz"] for item in dwells],
        dtype=float,
    )
    phase_arcs = np.asarray(
        [item["iterative_timing_phase_arc_qualified_locklet_count"] for item in dwells]
    )
    feedback = np.asarray(
        [item["iterative_timing_phase_feedback_candidate_locklet_count"] for item in dwells]
    )
    complete = np.asarray([item["complete_locklet_count"] for item in dwells])
    timing_rate = np.asarray(
        [item["all_complete_candidate_relative_timing_rate_median_samples_s"] for item in dwells],
        dtype=float,
    )
    x = np.arange(len(dwells))
    figure = Figure(figsize=(11.5, 9.0), constrained_layout=True)
    axes = figure.subplots(3, 1)
    width = 0.2
    normalized = [
        np.divide(
            100.0 * value,
            glrt,
            out=np.full_like(glrt, np.nan),
            where=np.isfinite(glrt) & (glrt > 0.0),
        )
        for value in (glrt, frequency, fixed, timing)
    ]
    axes[0].bar(
        x - 1.5 * width,
        normalized[0],
        width,
        color=GRAY,
        label="20 ms GLRT trend",
    )
    axes[0].bar(
        x - 0.5 * width,
        normalized[1],
        width,
        color=BLUE,
        label="frame CFO only",
    )
    axes[0].bar(
        x + 0.5 * width,
        normalized[2],
        width,
        color=AMBER,
        label="phase candidate; timing fixed (diagnostic)",
    )
    axes[0].bar(
        x + 1.5 * width,
        normalized[3],
        width,
        color=GREEN,
        label="phase + relative timing (diagnostic)",
    )
    axes[0].axhline(100.0, color=GRAY, linewidth=1, linestyle="--")
    axes[0].set_ylabel("RMS / re-centered GLRT RMS (%)")
    axes[0].set_title(
        "A · Post-selection fit-withheld prediction · lower is better",
        loc="left",
        fontweight="bold",
    )
    axes[0].legend(ncols=2, fontsize=8)
    axes[0].grid(axis="y", alpha=0.2)
    axes[1].bar(x, complete, color=GRAY, alpha=0.35, label="complete locklets")
    axes[1].bar(x, phase_arcs, color=GREEN, label="fit-withheld-qualified phase arcs")
    axes[1].bar(
        x,
        feedback,
        color=AMBER,
        label="fit-withheld-selected feedback candidates",
    )
    axes[1].set_ylabel("locklet count")
    axes[1].set_title(
        "B · Feedback still needs a second independent validation lane",
        loc="left",
        fontweight="bold",
    )
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.2)
    axes[2].axhline(0.0, color=GRAY, linewidth=1)
    axes[2].scatter(x, timing_rate, color=GREEN, s=50)
    axes[2].set_ylabel("median relative timing rate (samples/s)")
    axes[2].set_title(
        "C · All complete timing candidates; receiver-relative, not pseudorange",
        loc="left",
        fontweight="bold",
    )
    axes[2].grid(axis="y", alpha=0.2)
    for axis in axes:
        axis.set_xticks(x, labels)
    figure.suptitle(
        "Iterative 1.333 ms frame phase/rate prototype · refill-safe validation",
        fontsize=15,
        fontweight="bold",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170, metadata={"Software": "leo-frame-phase-rate-v1"})


def run_report(
    *,
    bulk_root: Path,
    frame_cfo_root: Path,
    output_root: Path,
    phase: str,
    labels: tuple[str, ...] | None,
    maximum_regions: int,
) -> dict[str, object]:
    if phase not in {"all", "explore", "confirm"}:
        raise ValueError("phase selection is unsupported")
    if not 1 <= maximum_regions <= 6:
        raise ValueError("maximum regions must lie in [1, 6]")
    selected_labels = set(labels or ())
    if len(selected_labels) != len(labels or ()):
        raise ValueError("requested dwell labels must be unique")
    if output_root.resolve() == frame_cfo_root.resolve():
        raise ValueError("phase/rate output root must differ from the frame-CFO input root")
    requested_full_run = phase == "all" and not selected_labels and maximum_regions == 6
    if not requested_full_run and output_root.resolve() == DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("a subset run requires an explicit noncanonical output root")
    cfo_summary_path = frame_cfo_root / "summary.json"
    cfo_rows_path = frame_cfo_root / "frame-cfo-rows.jsonl.gz"
    cfo_manifest_path = frame_cfo_root / "artifact-manifest.json"
    cfo_summary = _load(cfo_summary_path)
    if cfo_summary.get("schema") != "org.leo.research.frame-cfo-prototype/v1":
        raise ValueError("unsupported frame-CFO prototype summary")
    cfo_manifest = _load(cfo_manifest_path)
    if cfo_manifest.get("schema") != "org.leo.research.frame-cfo-prototype-artifacts/v1":
        raise ValueError("unsupported frame-CFO artifact manifest")
    cfo_summary_digest = _sha256(cfo_summary_path)
    cfo_rows_digest = _sha256(cfo_rows_path)
    if cfo_manifest.get("artifacts", {}).get(cfo_summary_path.name) != cfo_summary_digest:
        raise ValueError("frame-CFO summary disagrees with its artifact manifest")
    if cfo_manifest.get("artifacts", {}).get(cfo_rows_path.name) != cfo_rows_digest:
        raise ValueError("frame-CFO rows disagree with their artifact manifest")
    if cfo_summary.get("artifacts", {}).get(cfo_rows_path.name) != cfo_rows_digest:
        raise ValueError("frame-CFO rows disagree with their declaring summary")
    declared_dwells = cfo_summary.get("dwells")
    if not isinstance(declared_dwells, list) or not declared_dwells:
        raise ValueError("frame-CFO prototype declares no dwells")
    expected_phase_by_label: dict[str, str] = {}
    for item in declared_dwells:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str):
            raise ValueError("frame-CFO dwell labels must be strings")
        label = str(item["label"])
        if label in expected_phase_by_label:
            raise ValueError("frame-CFO dwell labels must be unique")
        item_phase = item.get("phase")
        if item_phase not in {"explore", "confirm"}:
            raise ValueError("frame-CFO dwell phase is unsupported")
        expected_phase_by_label[label] = str(item_phase)
    inventory = [
        item
        for item in declared_dwells
        if (phase == "all" or item["phase"] == phase)
        and (not selected_labels or item["label"] in selected_labels)
    ]
    if not inventory:
        raise ValueError("phase/rate prototype selection contains no dwells")
    if selected_labels - {str(item["label"]) for item in inventory}:
        raise ValueError("requested dwell label is absent from selected frame-CFO inputs")
    rows = _persisted_rows(
        cfo_rows_path,
        expected_phase_by_label=expected_phase_by_label,
    )

    config = FramePhaseRateConfig()
    fixed_config = replace(config, enable_relative_timing=False)
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    locklet_documents: list[dict[str, Any]] = []
    dwell_documents = []
    try:
        for dwell in inventory:
            label = str(dwell["label"])
            trajectory_id = _even_only_trajectory_id(dwell, rows)
            frame_cfo_evaluation_trajectory_id = str(dwell["evaluation_trajectory_id"])
            bundle = store.inspect(str(dwell["session_id"]))
            if bundle.manifest_sha256 != dwell["recording_manifest_digest"]:
                raise ValueError("recording digest disagrees with frozen frame-CFO input")
            reader = store.reader(bundle, str(dwell["stream_id"]), verify=True)
            timeline = tuple(reader.iter_timeline_metadata())
            boundaries = tuple(item.session_sample_start for item in timeline[1:])
            dwell_locklets: list[dict[str, Any]] = []
            for region_index, region_value in enumerate(
                dwell["regions"][:maximum_regions], start=1
            ):
                region = _region(region_value)
                print(
                    f"{label}: region {region_index}/{min(maximum_regions, len(dwell['regions']))} "
                    f"{region.role.value}",
                    flush=True,
                )
                persisted = {
                    key[-1]: value
                    for key, value in rows.items()
                    if key[:3] == (label, trajectory_id, region.region_id)
                }
                if not persisted:
                    raise ValueError("quality-leading persisted region rows are absent")
                source_seeds = {float(item["source_bound_seed_hz"]) for item in persisted.values()}
                if len(source_seeds) != 1:
                    raise ValueError("one region contains multiple source-bound CFO seeds")
                seed_hz = source_seeds.pop()
                raw = reader.read(
                    region.sample_start - 1,
                    region.sample_count + 2,
                    receiver_ids=(int(dwell["receiver_id"]),),
                )
                iq = _complex_receiver(raw)
                frame_content = round(302 * reader.sample_rate_hz * OFDM_SYMBOL_DURATION_S)
                observations = []
                model_by_start = {}
                for opportunity in frame_opportunities(
                    region,
                    sample_rate_hz=reader.sample_rate_hz,
                    refill_boundaries=boundaries,
                ):
                    row = persisted.get(opportunity.frame_start_sample)
                    if row is None:
                        raise ValueError("persisted frame opportunity is absent")
                    model_by_start[opportunity.frame_start_sample] = float(
                        row["trajectory_model_cfo_hz"]
                    )
                    if opportunity.crosses_refill_boundary:
                        continue
                    local = opportunity.local_frame_start
                    complex_result = estimate_edge_pilot_frame_complex_split(
                        iq[local : local + frame_content + 2],
                        reader.sample_rate_hz,
                        frame_start_sample=opportunity.frame_start_sample,
                        acquisition_absolute_cfo_hz=seed_hz,
                        edge=StarlinkEdge(dwell["edge"]),
                    )
                    if complex_result.even is None:
                        continue
                    persisted_split = row["split_validation"]
                    if persisted_split is None:
                        raise ValueError("persisted split-validation row is absent")
                    if bool(persisted_split["training_supported"]) != bool(
                        complex_result.training_supported
                    ):
                        raise ValueError("complex-fold membership disagrees with frozen split lane")
                    if (
                        abs(
                            float(persisted_split["even_absolute_cfo_hz"])
                            - complex_result.even.absolute_cfo_hz
                        )
                        > 1e-6
                    ):
                        raise ValueError("complex-fold CFO disagrees with frozen split lane")
                    observations.append(
                        FramePhaseRateObservation(
                            frame_index=opportunity.frame_index,
                            frame_start_sample=opportunity.frame_start_sample,
                            reference_sample=complex_result.reference_sample,
                            continuity_segment=opportunity.continuity_segment,
                            training_supported=complex_result.training_supported,
                            even_absolute_cfo_hz=complex_result.even.absolute_cfo_hz,
                            even_frequency_uncertainty_hz=(
                                complex_result.even.frequency_uncertainty_hz
                            ),
                            even_exact_coherence=complex_result.even.exact_coherence,
                            even_control_coherence=complex_result.even.control_coherence,
                            even_channel_vector=complex_result.even.channel_vector,
                            odd_absolute_cfo_hz=(
                                None
                                if complex_result.odd is None
                                else complex_result.odd.absolute_cfo_hz
                            ),
                            odd_channel_vector=(
                                None
                                if complex_result.odd is None
                                else complex_result.odd.channel_vector
                            ),
                        )
                    )
                locklets = _partition_locklets(
                    tuple(observations),
                    sample_rate_hz=reader.sample_rate_hz,
                    maximum_gap_s=config.maximum_gap_s,
                )
                for locklet_index, locklet in enumerate(locklets, start=1):
                    fixed = fit_iterative_frame_phase_rate(
                        locklet,
                        sample_rate_hz=reader.sample_rate_hz,
                        epoch_sample=region.sample_start,
                        edge=StarlinkEdge(dwell["edge"]),
                        config=fixed_config,
                    )
                    iterative = fit_iterative_frame_phase_rate(
                        locklet,
                        sample_rate_hz=reader.sample_rate_hz,
                        epoch_sample=region.sample_start,
                        edge=StarlinkEdge(dwell["edge"]),
                        config=config,
                    )
                    document = _locklet_document(
                        label=label,
                        phase=str(dwell["phase"]),
                        region=region,
                        locklet_index=locklet_index,
                        observations=locklet,
                        model_cfo_hz=model_by_start,
                        sample_rate_hz=reader.sample_rate_hz,
                        fixed=fixed,
                        iterative=iterative,
                        config=config,
                    )
                    dwell_locklets.append(document)
                    locklet_documents.append(document)
            dwell_document = _summarize_dwell(label, str(dwell["phase"]), dwell_locklets)
            dwell_document.update(
                {
                    "even_only_selected_trajectory_id": trajectory_id,
                    "frame_cfo_evaluation_trajectory_id": frame_cfo_evaluation_trajectory_id,
                    "even_only_selection_agrees_with_frame_cfo_evaluation": (
                        trajectory_id == frame_cfo_evaluation_trajectory_id
                    ),
                }
            )
            dwell_documents.append(dwell_document)
    finally:
        store.close()

    output_root.mkdir(parents=True, exist_ok=True)
    locklets_path = output_root / "locklets.json"
    figure_path = output_root / "frame-phase-rate-prototype.png"
    locklets_path.write_bytes(
        _json_bytes(
            {
                "schema": "org.leo.research.frame-phase-rate-locklets/v1",
                "locklets": locklet_documents,
            }
        )
    )
    _plot(figure_path, dwell_documents)
    upstream_full_run = cfo_summary.get("selection", {}).get("full_frozen_run") is True
    realized_full_inventory = len(inventory) == len(declared_dwells) and all(
        len(item.get("regions", ())) == 6
        and int(item.get("selected_region_count", -1)) == 6
        and int(item.get("full_declared_region_count", -1)) == 6
        for item in inventory
    )
    full_run = requested_full_run and upstream_full_run and realized_full_inventory
    upstream_acceptance_passed = cfo_summary.get("acceptance", {}).get("passed") is True
    total_complete = sum(int(item["complete_locklet_count"]) for item in dwell_documents)
    total_phase_arcs = sum(
        int(item["iterative_timing_phase_arc_qualified_locklet_count"]) for item in dwell_documents
    )
    total_feedback = sum(
        int(item["iterative_timing_phase_feedback_candidate_locklet_count"])
        for item in dwell_documents
    )
    document = stable_measurement_floats(
        {
            "schema": "org.leo.research.frame-phase-rate-prototype/v1",
            "algorithm": "even-cfo-primary-modulo-pi-optional-relative-timing-v1",
            "frame_cfo_summary_digest": cfo_summary_digest,
            "frame_cfo_rows_digest": cfo_rows_digest,
            "frame_cfo_artifact_manifest_digest": _sha256(cfo_manifest_path),
            "implementation_digests": {
                "tool": _sha256(Path(__file__).resolve()),
                "phase_rate_model": _sha256(Path(phase_rate_implementation.__file__).resolve()),
                "complex_fold_estimator": _sha256(Path(pilot_implementation.__file__).resolve()),
            },
            "configuration": asdict(config),
            "selection": {
                "phase": phase,
                "labels": list(labels or ()),
                "maximum_regions": maximum_regions,
                "full_frozen_run": full_run,
                "full_frozen_run_means_coverage_not_acceptance": True,
                "upstream_full_frozen_run": upstream_full_run,
                "realized_full_inventory": realized_full_inventory,
                "upstream_frame_cfo_acceptance_passed": upstream_acceptance_passed,
                "upstream_frame_cfo_acceptance": cfo_summary.get("acceptance"),
                "alias_selected_by_even_qin_only_before_odd_validation": True,
                "all_even_only_alias_selections_agree_with_frame_cfo_evaluation": all(
                    bool(item["even_only_selection_agrees_with_frame_cfo_evaluation"])
                    for item in dwell_documents
                ),
            },
            "dwells": dwell_documents,
            "locklet_count": len(locklet_documents),
            "complete_locklet_count": total_complete,
            "phase_arc_qualified_locklet_count": total_phase_arcs,
            "phase_arc_qualified_fraction": (
                total_phase_arcs / total_complete if total_complete else None
            ),
            "phase_feedback_candidate_locklet_count": total_feedback,
            "phase_feedback_candidate_fraction": (
                total_feedback / total_complete if total_complete else None
            ),
            "artifacts": {
                locklets_path.name: _sha256(locklets_path),
                figure_path.name: _sha256(figure_path),
            },
            "candidate_only": True,
            "known_pilots_only": True,
            "payload_decoded": False,
            "new_rf_collected": False,
            "absolute_carrier_phase_resolved": False,
            "timing_is_receiver_channel_relative": True,
            "unknown_refills_crossed": False,
            "odd_symbols_influenced_fit": False,
            "odd_symbols_influenced_locklet_frame_membership": False,
            "odd_symbols_influenced_alias_selection": False,
            "odd_symbols_may_have_influenced_region_selection": True,
            "odd_validation_is_fully_independent_holdout": False,
            "phase_feedback_applied_to_primary_rate": False,
            "feedback_promotion_requires_second_validation_lane": True,
        }
    )
    summary_path = output_root / "summary.json"
    summary_path.write_bytes(_json_bytes(document))
    manifest = {
        "schema": "org.leo.research.frame-phase-rate-artifacts/v1",
        "artifacts": {
            path.name: _sha256(path) for path in (summary_path, locklets_path, figure_path)
        },
    }
    (output_root / "artifact-manifest.json").write_bytes(_json_bytes(manifest))
    return document


def main() -> None:
    arguments = _arguments()
    document = run_report(
        bulk_root=arguments.bulk_root,
        frame_cfo_root=arguments.frame_cfo_root,
        output_root=arguments.output_root,
        phase=arguments.phase,
        labels=None if arguments.labels is None else tuple(arguments.labels),
        maximum_regions=arguments.maximum_regions,
    )
    print(arguments.output_root / "summary.json")
    print(
        f"{document['complete_locklet_count']} complete locklets; "
        f"{document['phase_arc_qualified_locklet_count']} phase arcs; "
        f"{document['phase_feedback_candidate_locklet_count']} feedback candidates"
    )


if __name__ == "__main__":
    main()
