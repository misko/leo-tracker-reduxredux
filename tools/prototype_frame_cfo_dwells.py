#!/usr/bin/env python3
"""Prototype independent 1.333 ms CFO measurements on pinned existing dwells."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.frame_cfo_dwell_prototype import (  # noqa: E402
    FrameCfoDwellPrototypeConfig,
    FrameCfoPrototypeRow,
    PrototypeProbe,
    PrototypeRegion,
    TrajectoryHypothesis,
    analyze_region_hypothesis,
    select_prototype_regions,
    summarize_hypothesis,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.contracts.cfo_dealias import (  # noqa: E402
    DealiasedTrajectoryBankV3,
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV2,
    FinalTrajectoryBankV3,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

DEFAULT_INPUTS = Path("config/analysis/frame-cfo-prototype-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_frame_cfo_dwell_prototype")
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")


@dataclass(frozen=True, slots=True)
class RawSourceCandidate:
    source_observation_id: str
    detection_time_s: float
    detection_sample_start: int
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--phase", choices=("all", "explore", "confirm"), default="all")
    parser.add_argument(
        "--labels",
        nargs="*",
        help="optional exact dwell labels; the frozen order is retained",
    )
    parser.add_argument(
        "--maximum-regions",
        type=int,
        default=6,
        help="operational smoke cap after deterministic six-region selection",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object, *, indent: int | None = 2) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
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


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def _raw_sources(scan: dict[str, Any]) -> dict[str, RawSourceCandidate]:
    if scan.get("schema_version") != 3:
        raise ValueError("frame-CFO prototype requires pilot-scan V3")
    output = {}
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            score = _glrt_score(candidate)
            source_id = canonical_digest(
                {
                    "sample_start": int(detection["sample_start"]),
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            if source_id in output:
                raise ValueError("pilot scan contains a duplicate raw observation identity")
            output[source_id] = RawSourceCandidate(
                source_observation_id=source_id,
                detection_time_s=float(detection["time_s"]),
                detection_sample_start=int(detection["sample_start"]),
                rank=int(candidate["rank"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                tracking_cfo_hz=float(score["tracking_cfo_hz"]),
                exact_score=float(score["exact_score"]),
                control_score=float(score["control_score"]),
                margin=float(score["margin"]),
            )
    return output


def _validate_inputs(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if document.get("schema") != "org.leo.research.frame-cfo-prototype-inputs/v1":
        raise ValueError("unsupported frame-CFO prototype input schema")
    values = document.get("dwells")
    if not isinstance(values, list) or not values:
        raise ValueError("prototype input contains no dwells")
    labels = [item.get("label") for item in values if isinstance(item, dict)]
    if (
        len(labels) != len(values)
        or any(not isinstance(value, str) or not value for value in labels)
        or len(set(labels)) != len(labels)
    ):
        raise ValueError("prototype dwell labels must be unique strings")
    required = {
        "label",
        "phase",
        "session_id",
        "run_id",
        "scope_id",
        "stream_id",
        "receiver_id",
        "edge",
        "branch_id",
        "dealiased_product_version",
        "final_product_version",
        "trajectory_ids",
    }
    output = []
    for item in values:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("prototype dwell input fields are not closed")
        if item["phase"] not in {"explore", "confirm"}:
            raise ValueError("prototype dwell phase must be explore or confirm")
        string_fields = (
            "session_id",
            "run_id",
            "scope_id",
            "stream_id",
            "edge",
            "branch_id",
        )
        if any(not isinstance(item[field], str) or not item[field] for field in string_fields):
            raise ValueError("prototype dwell identities must be nonempty strings")
        if not isinstance(item["receiver_id"], int) or isinstance(item["receiver_id"], bool):
            raise ValueError("prototype receiver ID must be an integer")
        StarlinkEdge(item["edge"])
        trajectory_ids = item["trajectory_ids"]
        if not isinstance(trajectory_ids, list) or not trajectory_ids:
            raise ValueError("prototype dwell must pin at least one trajectory")
        if len(set(trajectory_ids)) != len(trajectory_ids):
            raise ValueError("prototype trajectory IDs must be unique")
        version_pair = (item["dealiased_product_version"], item["final_product_version"])
        if version_pair not in {(3, 2), (4, 3)}:
            raise ValueError("unsupported dealiased/final product version pair")
        output.append(item)
    return tuple(output)


def _products(
    analysis_root: Path,
    item: dict[str, Any],
) -> tuple[object, object, dict[str, Any], dict[str, str]]:
    dealiased_version = int(item["dealiased_product_version"])
    final_version = int(item["final_product_version"])
    scan_path = analysis_root / "standard.pilot-scan.v3.json"
    dealiased_path = analysis_root / f"standard.dealiased-trajectory-bank.v{dealiased_version}.json"
    final_path = analysis_root / f"standard.final-trajectory-bank.v{final_version}.json"
    scan = _load(scan_path)
    dealiased_document = _load(dealiased_path)
    final_document = _load(final_path)
    dealiased = (
        DealiasedTrajectoryBankV3.model_validate(dealiased_document)
        if dealiased_version == 3
        else DealiasedTrajectoryBankV4.model_validate(dealiased_document)
    )
    final = (
        FinalTrajectoryBankV2.model_validate(final_document)
        if final_version == 2
        else FinalTrajectoryBankV3.model_validate(final_document)
    )
    return (
        dealiased,
        final,
        scan,
        {
            "pilot_scan": _sha256(scan_path),
            "dealiased_trajectory_bank": _sha256(dealiased_path),
            "final_trajectory_bank": _sha256(final_path),
        },
    )


def _bound_inputs(
    item: dict[str, Any],
    dealiased: object,
    final: object,
    scan: dict[str, Any],
) -> tuple[tuple[PrototypeProbe, ...], tuple[TrajectoryHypothesis, ...]]:
    branch_matches = [
        branch for branch in dealiased.branches if branch.branch_id == item["branch_id"]
    ]
    if len(branch_matches) != 1:
        raise ValueError("pinned dealiased branch is absent or duplicated")
    branch = branch_matches[0]
    observation_by_id = {value.observation_id: value for value in dealiased.observations}
    source_by_id = _raw_sources(scan)
    probes = []
    for canonical_id in branch.observation_ids:
        observation = observation_by_id.get(canonical_id)
        if observation is None or len(observation.source_observation_ids) != 1:
            raise ValueError("canonical observation lacks one exact raw GLRT source")
        source_id = observation.source_observation_ids[0]
        source = source_by_id.get(source_id)
        if source is None:
            raise ValueError("canonical observation raw source is absent from pilot scan")
        if observation.sample_start != source.detection_sample_start:
            raise ValueError("canonical and raw source sample coordinates disagree")
        if not math.isclose(
            observation.raw_cfo_hz,
            source.tracking_cfo_hz,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("canonical raw CFO disagrees with its exact GLRT source")
        probes.append(
            PrototypeProbe(
                probe_index=len(probes),
                canonical_observation_id=canonical_id,
                source_observation_id=source_id,
                detection_time_s=source.detection_time_s,
                detection_sample_start=source.detection_sample_start,
                local_epoch_sample=source.local_epoch_sample,
                raw_source_cfo_hz=source.tracking_cfo_hz,
                observation_alias_index=observation.alias_index,
                exact_score=source.exact_score,
                control_score=source.control_score,
                margin=source.margin,
            )
        )
    probes = sorted(
        probes,
        key=lambda value: (value.detection_time_s, value.detection_sample_start),
    )
    probes = [
        PrototypeProbe(**{**asdict(value), "probe_index": index})
        for index, value in enumerate(probes)
    ]
    trajectory_by_id = {value.trajectory_id: value for value in final.trajectories}
    branch_trajectories = tuple(
        value for value in final.trajectories if value.branch_id == item["branch_id"]
    )
    pinned_ids = tuple(item["trajectory_ids"])
    if set(pinned_ids) != {value.trajectory_id for value in branch_trajectories}:
        raise ValueError("pinned hypotheses do not exactly cover final branch lifts")
    hypotheses = []
    for trajectory_id in pinned_ids:
        value = trajectory_by_id[trajectory_id]
        if set(value.observation_ids) != set(branch.observation_ids):
            raise ValueError("final hypothesis membership disagrees with its dealiased branch")
        hypotheses.append(
            TrajectoryHypothesis(
                trajectory_id=value.trajectory_id,
                branch_id=value.branch_id,
                alias_index=value.alias_index,
                reference_time_s=value.reference_time_s,
                absolute_coefficients_hz=tuple(value.absolute_coefficients_hz),
                automatic_correction_eligible=value.automatic_correction_eligible,
            )
        )
    aliases = [value.alias_index for value in hypotheses]
    if len(set(aliases)) != len(aliases):
        raise ValueError("pinned final hypotheses merge an alias index")
    return tuple(probes), tuple(hypotheses)


def _region_document(region: PrototypeRegion) -> dict[str, object]:
    return {
        "region_id": region.region_id,
        "role": region.role.value,
        "sample_start": region.sample_start,
        "sample_count": region.sample_count,
        "strong_glrt_region": region.strong_glrt_region,
        "refill_boundary_sample": region.refill_boundary_sample,
        "probe": asdict(region.probe),
    }


def analyze_dwell(
    *,
    store: RecordingStore,
    bulk_root: Path,
    item: dict[str, Any],
    maximum_regions: int,
    config: FrameCfoDwellPrototypeConfig,
) -> tuple[dict[str, Any], tuple[FrameCfoPrototypeRow, ...]]:
    if not 1 <= maximum_regions <= 6:
        raise ValueError("maximum regions must lie in [1, 6]")
    session_id = str(item["session_id"])
    run_id = str(item["run_id"])
    analysis_root = (
        bulk_root
        / "analysis"
        / session_id
        / run_id
        / "scientific"
        / "path-standard"
        / str(item["scope_id"])
    )
    analysis_manifest = bulk_root / "analysis" / session_id / run_id / "manifest.json"
    manifest = _load(analysis_manifest)
    if manifest.get("session_id") != session_id or manifest.get("run_id") != run_id:
        raise ValueError("analysis manifest identity disagrees with pinned dwell")
    if manifest.get("pipeline_lane") != "standard":
        raise ValueError("frame-CFO prototype requires a Standard analysis run")
    dealiased, final, scan, product_digests = _products(analysis_root, item)
    probes, hypotheses = _bound_inputs(item, dealiased, final, scan)
    bundle = store.inspect(session_id)
    reader = store.reader(bundle, str(item["stream_id"]), verify=True)
    if int(item["receiver_id"]) not in reader.receiver_ids:
        raise ValueError("pinned receiver is absent from recording stream")
    timeline = tuple(reader.iter_timeline_metadata())
    if not timeline or timeline[0].session_sample_start != 0:
        raise ValueError("recording timeline does not begin at sample zero")
    if timeline[-1].session_sample_start + timeline[-1].sample_count != reader.sample_count:
        raise ValueError("recording timeline does not cover the stream")
    refill_boundaries = tuple(value.session_sample_start for value in timeline[1:])
    selected = select_prototype_regions(
        probes,
        refill_boundaries=refill_boundaries,
        sample_rate_hz=reader.sample_rate_hz,
        recording_sample_count=reader.sample_count,
        config=config,
    )
    regions = selected[:maximum_regions]
    all_rows = []
    for region_index, region in enumerate(regions, start=1):
        print(
            f"{item['label']}: region {region_index}/{len(regions)} {region.role.value}",
            flush=True,
        )
        raw = reader.read(
            region.sample_start - 1,
            region.sample_count + 2,
            receiver_ids=(int(item["receiver_id"]),),
        )
        iq = _complex_receiver(raw)
        for hypothesis in hypotheses:
            all_rows.extend(
                analyze_region_hypothesis(
                    iq,
                    region=region,
                    hypothesis=hypothesis,
                    edge=StarlinkEdge(item["edge"]),
                    sample_rate_hz=reader.sample_rate_hz,
                    refill_boundaries=refill_boundaries,
                    config=config,
                )
            )
    rows = tuple(all_rows)
    summaries = [
        summarize_hypothesis(
            tuple(value for value in rows if value.trajectory_id == hypothesis.trajectory_id),
            hypothesis,
            config=config,
        )
        for hypothesis in hypotheses
    ]
    evaluation = max(
        summaries,
        key=lambda value: (
            int(value["diagnostic_frame_count"]),
            int(value["supported_frame_count"]),
            -abs(int(value["alias_index"])),
            str(value["trajectory_id"]),
        ),
    )
    return (
        {
            "label": item["label"],
            "phase": item["phase"],
            "session_id": session_id,
            "run_id": run_id,
            "scope_id": item["scope_id"],
            "stream_id": item["stream_id"],
            "receiver_id": item["receiver_id"],
            "edge": item["edge"],
            "branch_id": item["branch_id"],
            "analysis_root": str(analysis_root),
            "analysis_manifest_digest": _sha256(analysis_manifest),
            "recording_manifest_digest": bundle.manifest_sha256,
            "product_digests": product_digests,
            "sample_rate_hz": reader.sample_rate_hz,
            "recording_sample_count": reader.sample_count,
            "refill_count": len(timeline),
            "source_probe_count": len(probes),
            "pinned_hypothesis_count": len(hypotheses),
            "pinned_alias_indices": [value.alias_index for value in hypotheses],
            "evaluation_hypothesis_policy": (
                "maximum exact-Qin diagnostic frame count, then supported frame count, "
                "lower absolute alias index, then trajectory ID; all hypotheses remain persisted"
            ),
            "evaluation_trajectory_id": evaluation["trajectory_id"],
            "selected_region_count": len(regions),
            "full_declared_region_count": len(selected),
            "regions": [_region_document(value) for value in regions],
            "hypotheses": summaries,
        },
        rows,
    )


def _gate(
    name: str,
    observed: object,
    criterion: str,
    passed: bool,
    *,
    dwell: str | None = None,
    trajectory_id: str | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "dwell": dwell,
        "trajectory_id": trajectory_id,
        "observed": observed,
        "criterion": criterion,
        "passed": bool(passed),
    }


def _gates(dwells: list[dict[str, Any]], *, full_run: bool) -> dict[str, object]:
    results = []
    for dwell in dwells:
        label = str(dwell["label"])
        results.append(
            _gate(
                "six_predeclared_regions",
                dwell["selected_region_count"],
                "== 6",
                dwell["selected_region_count"] == 6,
                dwell=label,
            )
        )
        aliases = dwell["pinned_alias_indices"]
        results.append(
            _gate(
                "alias_hypotheses_preserved",
                aliases,
                "all pinned aliases distinct and summarized separately",
                len(aliases) == len(set(aliases)) == len(dwell["hypotheses"]),
                dwell=label,
            )
        )
        matches = [
            value
            for value in dwell["hypotheses"]
            if value["trajectory_id"] == dwell["evaluation_trajectory_id"]
        ]
        if len(matches) != 1:
            raise ValueError("dwell evaluation hypothesis is absent or duplicated")
        hypothesis = matches[0]
        trajectory_id = str(hypothesis["trajectory_id"])
        results.append(
            _gate(
                "quality_leading_hypothesis_supported",
                hypothesis["diagnostic_frame_count"],
                ">= 24 exact-Qin diagnostic frames",
                hypothesis["diagnostic_frame_count"] >= 24,
                dwell=label,
                trajectory_id=trajectory_id,
            )
        )
        checks = (
            (
                "strong_interior_retention",
                hypothesis["strong_interior_retention_fraction"],
                ">= 0.75",
                lambda value: value is not None and value >= 0.75,
            ),
            (
                "even_odd_p95",
                hypothesis["even_odd_p95_hz"],
                "<= 100 Hz",
                lambda value: value is not None and value <= 100.0,
            ),
            (
                "timing_spread_p95",
                hypothesis["timing_spread_p95_hz"],
                "<= 50 Hz",
                lambda value: value is not None and value <= 50.0,
            ),
            (
                "half_frame_difference_p95",
                hypothesis["half_frame_difference_p95_z"],
                "<= 4 sigma",
                lambda value: value is not None and value <= 4.0,
            ),
            (
                "tone_deletion_p95",
                hypothesis["tone_deletion_spread_p95_hz"],
                "<= 75 Hz",
                lambda value: value is not None and value <= 75.0,
            ),
            (
                "strong_search_boundary_fraction",
                hypothesis["strong_search_boundary_fraction"],
                "< 0.05",
                lambda value: value is not None and value < 0.05,
            ),
            (
                "sensitivity_never_substituted",
                hypothesis["sensitivity_substitution_count"],
                "== 0",
                lambda value: value == 0,
            ),
        )
        for name, observed, criterion, predicate in checks:
            results.append(
                _gate(
                    name,
                    observed,
                    criterion,
                    predicate(observed),
                    dwell=label,
                    trajectory_id=trajectory_id,
                )
            )
        validation = hypothesis["heldout_validation"]
        complete = validation["status"] == "complete"
        local_rms = validation.get("local_odd_validation_rms_hz")
        model_rms = validation.get("trajectory_odd_validation_rms_hz")
        results.append(
            _gate(
                "heldout_not_worse",
                None if not complete else local_rms / model_rms,
                "complete and local/model odd-Qin RMS <= 1.05",
                bool(complete and model_rms > 0.0 and local_rms <= 1.05 * model_rms),
                dwell=label,
                trajectory_id=trajectory_id,
            )
        )
        if label == "T06":
            difference = validation.get("rate_difference_hz_s")
            results.append(
                _gate(
                    "t06_no_bias_rate_control",
                    difference,
                    "absolute local-model difference < 500 Hz/s",
                    bool(complete and abs(difference) < 500.0),
                    dwell=label,
                    trajectory_id=trajectory_id,
                )
            )
        if label in {"T01", "T04"}:
            improvement = validation.get("odd_validation_improvement_fraction")
            results.append(
                _gate(
                    "reset_biased_heldout_improvement",
                    improvement,
                    ">= 0.20",
                    bool(complete and improvement is not None and improvement >= 0.20),
                    dwell=label,
                    trajectory_id=trajectory_id,
                )
            )
        if label == "T03":
            sigma = validation.get("local_rate_conditional_sigma_hz_s")
            stable = bool(
                complete
                and sigma is not None
                and sigma <= 1_000.0
                and model_rms > 0.0
                and local_rms <= 1.05 * model_rms
            )
            insufficient = validation["status"] == "insufficient"
            results.append(
                _gate(
                    "t03_fail_closed_or_stable",
                    {"status": validation["status"], "conditional_sigma_hz_s": sigma},
                    "insufficient, or sigma <= 1000 Hz/s and heldout RMS not worse",
                    insufficient or stable,
                    dwell=label,
                    trajectory_id=trajectory_id,
                )
            )
    passed = bool(full_run and results and all(item["passed"] for item in results))
    return {
        "evaluation_scope": "full frozen five-dwell run" if full_run else "bounded smoke only",
        "passed": passed,
        "gate_count": len(results),
        "failed_gate_count": sum(not item["passed"] for item in results),
        "results": results,
        "prior_study_reuse": (
            "T01/T04 improvement and T06 agreement are implementation regression sentinels, "
            "not independent scientific confirmation"
        ),
    }


def _row_sort_key(value: tuple[str, str, FrameCfoPrototypeRow]) -> tuple[object, ...]:
    label, _phase, row = value
    return (
        label,
        row.trajectory_alias_index,
        row.trajectory_id,
        row.region_role.value,
        row.frame_start_sample,
    )


def _write_rows(path: Path, rows: list[tuple[str, str, FrameCfoPrototypeRow]]) -> None:
    payload = b"".join(
        _json_bytes(
            {
                "schema": "org.leo.research.frame-cfo-prototype-row/v1",
                "dwell_label": label,
                "phase": phase,
                **row.document(),
            },
            indent=None,
        )
        for label, phase, row in sorted(rows, key=_row_sort_key)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as destination,
        gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=destination,
            mtime=0,
        ) as compressed,
    ):
        compressed.write(payload)


def _write_csv(path: Path, rows: list[tuple[str, str, FrameCfoPrototypeRow]]) -> None:
    fields = (
        "dwell_label",
        "phase",
        "region_role",
        "trajectory_id",
        "alias_index",
        "frame_start_sample",
        "frame_time_s",
        "strong_interior",
        "crosses_refill",
        "source_seed_hz",
        "primary_absolute_cfo_hz",
        "primary_supported",
        "primary_rejections",
        "sensitivity_absolute_cfo_hz",
        "split_even_absolute_cfo_hz",
        "split_odd_absolute_cfo_hz",
        "split_training_supported",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for label, phase, row in sorted(rows, key=_row_sort_key):
        primary = row.primary
        sensitivity = row.sensitivity
        split = row.split_validation
        writer.writerow(
            {
                "dwell_label": label,
                "phase": phase,
                "region_role": row.region_role.value,
                "trajectory_id": row.trajectory_id,
                "alias_index": row.trajectory_alias_index,
                "frame_start_sample": row.frame_start_sample,
                "frame_time_s": format(row.frame_time_s, ".12g"),
                "strong_interior": int(row.strong_interior_opportunity),
                "crosses_refill": int(row.crosses_refill_boundary),
                "source_seed_hz": format(row.source_bound_seed_hz, ".12g"),
                "primary_absolute_cfo_hz": (
                    ""
                    if primary is None or primary.absolute_cfo_hz is None
                    else format(primary.absolute_cfo_hz, ".12g")
                ),
                "primary_supported": int(bool(primary and primary.measurement_supported)),
                "primary_rejections": (
                    "refill_boundary_crossing"
                    if primary is None
                    else ";".join(primary.rejection_reasons)
                ),
                "sensitivity_absolute_cfo_hz": (
                    ""
                    if sensitivity is None or sensitivity.absolute_cfo_hz is None
                    else format(sensitivity.absolute_cfo_hz, ".12g")
                ),
                "split_even_absolute_cfo_hz": (
                    ""
                    if split is None or split.even_absolute_cfo_hz is None
                    else format(split.even_absolute_cfo_hz, ".12g")
                ),
                "split_odd_absolute_cfo_hz": (
                    ""
                    if split is None or split.odd_absolute_cfo_hz is None
                    else format(split.odd_absolute_cfo_hz, ".12g")
                ),
                "split_training_supported": int(bool(split and split.training_supported)),
            }
        )
    path.write_text(stream.getvalue(), encoding="utf-8")


def _plot(path: Path, rows: list[tuple[str, str, FrameCfoPrototypeRow]]) -> None:
    labels = list(dict.fromkeys(label for label, _phase, _row in rows))
    figure = Figure(figsize=(13.5, 2.8 * len(labels)), constrained_layout=True)
    axes = np.atleast_1d(figure.subplots(len(labels), 1, squeeze=False)[:, 0])
    colors = ("#2f83b7", "#d9881f", "#3f8f67", "#7b65a8")
    for axis, label in zip(axes, labels, strict=True):
        selected = [(phase, row) for row_label, phase, row in rows if row_label == label]
        trajectory_ids = list(dict.fromkeys(row.trajectory_id for _phase, row in selected))
        for index, trajectory_id in enumerate(trajectory_ids):
            members = [row for _phase, row in selected if row.trajectory_id == trajectory_id]
            supported = [
                row
                for row in members
                if row.primary is not None
                and row.primary.measurement_supported
                and row.primary.absolute_cfo_hz is not None
            ]
            rejected = [
                row
                for row in members
                if row.primary is not None
                and not row.primary.measurement_supported
                and row.primary.absolute_cfo_hz is not None
            ]
            alias = members[0].trajectory_alias_index
            color = colors[index % len(colors)]
            axis.scatter(
                [row.frame_time_s for row in supported],
                [row.primary.absolute_cfo_hz / 1_000.0 for row in supported],
                s=8,
                color=color,
                alpha=0.72,
                label=f"alias {alias:+d} supported",
            )
            axis.scatter(
                [row.frame_time_s for row in rejected],
                [row.primary.absolute_cfo_hz / 1_000.0 for row in rejected],
                s=12,
                facecolors="none",
                edgecolors=color,
                alpha=0.65,
                label=f"alias {alias:+d} rejected",
            )
        axis.set_title(f"{label} · independent 1/750 s frames", loc="left", fontweight="bold")
        axis.set_xlabel("recording time (s)")
        axis.set_ylabel("absolute candidate CFO (kHz)")
        axis.grid(alpha=0.18)
        axis.legend(fontsize=7, ncols=2)
    figure.suptitle(
        "Frame-CFO prototype · GLRT-bound aliases, refill-safe independent estimates",
        fontsize=15,
        fontweight="bold",
    )
    figure.savefig(
        path,
        dpi=170,
        metadata={"Software": "leo-frame-cfo-prototype-v1"},
    )


def run_prototype(
    *,
    bulk_root: Path,
    inputs_path: Path,
    output_root: Path,
    phase: str,
    labels: tuple[str, ...] | None,
    maximum_regions: int,
) -> dict[str, Any]:
    inputs = _load(inputs_path)
    inventory = _validate_inputs(inputs)
    selected_labels = set(labels or ())
    if len(selected_labels) != len(labels or ()):
        raise ValueError("requested dwell labels must be unique")
    available = {str(item["label"]) for item in inventory}
    if selected_labels - available:
        raise ValueError("requested dwell label is absent from frozen inputs")
    selected = tuple(
        item
        for item in inventory
        if (phase == "all" or item["phase"] == phase)
        and (not selected_labels or item["label"] in selected_labels)
    )
    if not selected:
        raise ValueError("prototype selection contains no dwells")
    config = FrameCfoDwellPrototypeConfig()
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    dwell_documents = []
    rows: list[tuple[str, str, FrameCfoPrototypeRow]] = []
    try:
        for item in selected:
            dwell, dwell_rows = analyze_dwell(
                store=store,
                bulk_root=bulk_root,
                item=item,
                maximum_regions=maximum_regions,
                config=config,
            )
            dwell_documents.append(dwell)
            rows.extend((str(item["label"]), str(item["phase"]), row) for row in dwell_rows)
    finally:
        store.close()

    output_root.mkdir(parents=True, exist_ok=True)
    rows_path = output_root / "frame-cfo-rows.jsonl.gz"
    csv_path = output_root / "frame-cfo-rows.csv"
    figure_path = output_root / "frame-cfo-prototype.png"
    _write_rows(rows_path, rows)
    _write_csv(csv_path, rows)
    _plot(figure_path, rows)
    full_run = phase == "all" and not selected_labels and maximum_regions == 6
    document = stable_measurement_floats(
        {
            "schema": "org.leo.research.frame-cfo-prototype/v1",
            "algorithm": "glrt-bound-independent-750hz-frame-cfo-v1",
            "inputs_digest": canonical_digest(inputs),
            "configuration": asdict(config),
            "selection": {
                "phase": phase,
                "labels": list(labels or ()),
                "maximum_regions": maximum_regions,
                "full_frozen_run": full_run,
            },
            "dwell_count": len(dwell_documents),
            "row_count": len(rows),
            "dwells": dwell_documents,
            "acceptance": _gates(dwell_documents, full_run=full_run),
            "artifacts": {
                rows_path.name: _sha256(rows_path),
                csv_path.name: _sha256(csv_path),
                figure_path.name: _sha256(figure_path),
            },
            "implementation_digests": {
                "tool": _sha256(Path(__file__)),
                "prototype_module": _sha256(
                    Path(__file__).parents[1]
                    / "src/leo/analysis/research/frame_cfo_dwell_prototype.py"
                ),
                "frame_estimator": _sha256(
                    Path(__file__).parents[1] / "src/leo/analysis/qam/pilot.py"
                ),
            },
            "candidate_only": True,
            "known_pilots_only": True,
            "payload_decoded": False,
            "new_rf_collected": False,
            "phase_continuity_assumed": False,
            "sensitivity_results_substituted": False,
        }
    )
    summary_path = output_root / "summary.json"
    summary_path.write_bytes(_json_bytes(document))
    manifest = {
        "schema": "org.leo.research.frame-cfo-prototype-artifacts/v1",
        "artifacts": {
            path.name: _sha256(path) for path in (rows_path, csv_path, figure_path, summary_path)
        },
    }
    (output_root / "artifact-manifest.json").write_bytes(_json_bytes(manifest))
    return document


def main() -> None:
    arguments = _arguments()
    if arguments.maximum_regions < 1 or arguments.maximum_regions > 6:
        raise SystemExit("--maximum-regions must lie in [1, 6]")
    document = run_prototype(
        bulk_root=arguments.bulk_root,
        inputs_path=arguments.inputs,
        output_root=arguments.output_root,
        phase=arguments.phase,
        labels=None if arguments.labels is None else tuple(arguments.labels),
        maximum_regions=arguments.maximum_regions,
    )
    print(arguments.output_root / "summary.json")
    print(
        f"{document['row_count']} frame rows; acceptance passed={document['acceptance']['passed']}"
    )


if __name__ == "__main__":
    main()
