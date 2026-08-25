#!/usr/bin/env python3
# ruff: noqa: E501
"""Aggregate the frozen pilot-filter benchmark across five untouched dwells.

The raw-IQ replay is intentionally performed by
``extract_five_dwell_pilot_filter_benchmark.py``.  This tool is read-only with
respect to the recording corpus: it consumes the sealed per-dwell NPZ and JSON
products, evaluates the already-frozen filters, and emits machine evidence,
static Matplotlib figures, and a Markdown report.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from types import ModuleType
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")


SOURCE_SCHEMA = "org.leo.research.five-dwell-filter-benchmark-source/v1"
PARITY_SCHEMA = "org.leo.research.five-dwell-filter-source-parity/v1"
EVIDENCE_SCHEMA = "org.leo.research.five-dwell-pilot-filter-prototypes/v1"
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_five_dwell_pilot_filter_prototypes")
DEFAULT_REPORT = Path("reports/2026_08_25_five_dwell_pilot_filter_prototypes.md")
DEFAULT_SOURCE_ROOT = Path("reports/figures/2026_08_25_five_dwell_pilot_filter_benchmark/source")

# The cohort was frozen as every same-release continuity-v2 campaign dwell that
# had not been used for D3 prototype development.  Keeping this list here makes
# the default command fail closed if discovery accidentally includes D3 or a
# later capture.
PRIMARY_SESSION_IDS = (
    "cap-20260824T192019-9023840c8e9f",
    "cap-20260824T192252-9981b9c27853",
    "cap-20260824T193733-1454b499b8bb",
    "cap-20260824T194009-34ae34f129bc",
    "cap-20260824T194245-1dfbc879df2b",
)
D3_DEVELOPMENT_SESSION_ID = "cap-20260824T192531-491832825b97"

CAUSAL_MODELS = (
    "trailing_20ms",
    "current_v2",
    "robust_jump_filter",
    "phase_gated_jump_filter",
)
MODEL_LABELS = {
    "trailing_20ms": "20 ms robust line",
    "trailing_50ms": "50 ms robust line",
    "current_v2": "current PNT V2",
    "robust_jump_filter": "robust jump filter",
    "phase_gated_jump_filter": "phase-gated jump filter",
    "block_60_40_holdout": "frozen 60/40 robust line",
    "offline_block_smoother": "offline block smoother",
}
MODEL_COLORS = {
    "trailing_20ms": "#1b9e77",
    "trailing_50ms": "#66a61e",
    "current_v2": "#d95f02",
    "robust_jump_filter": "#6a3d9a",
    "phase_gated_jump_filter": "#7570b3",
    "block_60_40_holdout": "#a6761d",
    "offline_block_smoother": "#666666",
}
PRIMARY_COMPARISONS = (
    ("robust_jump_filter", "current_v2"),
    ("robust_jump_filter", "trailing_20ms"),
)


@dataclass(frozen=True, slots=True)
class DwellSource:
    label: str
    session_id: str
    summary_path: Path
    npz_path: Path
    summary: dict[str, Any]
    release_sha: str
    pnt_source_path: Path
    pnt_source_sha256: str
    source_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DwellEvaluation:
    evidence: dict[str, Any]
    plotting: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ValidatedParityAttestation:
    path: Path
    sha256: str
    document: dict[str, Any]


_D3_MODULE: ModuleType | None = None


def _d3_tool() -> ModuleType:
    """Load the frozen single-dwell implementation without making it a package API."""

    global _D3_MODULE
    if _D3_MODULE is not None:
        return _D3_MODULE
    path = Path(__file__).with_name("report_d3_pilot_filter_prototypes.py")
    name = "_leo_five_dwell_d3_filter_report"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen D3 evaluator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _D3_MODULE = module
    return module


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="directory containing per-dwell *-filter-benchmark-summary.json files",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        action="append",
        default=[],
        help="explicit per-dwell summary (repeat five times; overrides discovery)",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--parity-attestation",
        type=Path,
        default=None,
        help=(
            "independent source-replay parity document (default: "
            "<source-root>/../source-replay-parity-attestation.json)"
        ),
    )
    parser.add_argument(
        "--allow-nonprimary-cohort",
        action="store_true",
        help="allow an exploratory cohort other than the five frozen untouched dwells",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _resolve_archived_path(
    summary_path: Path,
    summary: Mapping[str, Any],
    *,
    relative_keys: Sequence[str],
    path_keys: Sequence[str],
    derived: Path | None = None,
) -> Path | None:
    candidates: list[Path] = []
    for key in relative_keys:
        value = summary.get(key)
        if value:
            candidates.append(summary_path.parent / Path(str(value)))
    if derived is not None:
        candidates.append(derived)
    for key in path_keys:
        value = summary.get(key)
        if not value:
            continue
        path = Path(str(value))
        candidates.append(path if path.is_absolute() else summary_path.parent / path)
        if not path.is_absolute():
            candidates.append(path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _summary_digest(summary: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = summary.get(key)
        if value:
            return str(value)
    return None


def _load_source(summary_path: Path) -> DwellSource:
    summary_path = summary_path.resolve()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema") != SOURCE_SCHEMA:
        raise ValueError(
            f"{summary_path}: expected source schema {SOURCE_SCHEMA!r}, "
            f"got {summary.get('schema')!r}"
        )
    session_id = str(summary.get("session_id", ""))
    if not session_id:
        raise ValueError(f"{summary_path}: missing session_id")
    derived_npz = summary_path.with_name(summary_path.name.replace("-summary.json", ".npz"))
    npz_path = _resolve_archived_path(
        summary_path,
        summary,
        relative_keys=("npz_relative_path",),
        path_keys=("npz_path", "output_path"),
        derived=derived_npz,
    )
    if npz_path is None:
        raise ValueError(f"{summary_path}: cannot resolve the archived replay NPZ")
    expected_npz_sha = _summary_digest(summary, "npz_sha256", "output_sha256")
    if expected_npz_sha is None:
        raise ValueError(f"{summary_path}: missing archived replay NPZ SHA-256")
    if _sha256(npz_path) != expected_npz_sha:
        raise ValueError(f"{summary_path}: replay NPZ SHA-256 mismatch")

    release_sha = str(
        summary.get("capture_release_sha")
        or summary.get("pipeline_release_id")
        or summary.get("release_sha")
        or summary.get("software_release_sha")
        or ""
    )
    if not release_sha:
        raise ValueError(f"{summary_path}: missing capture release SHA")
    label = str(summary.get("dwell_label") or summary.get("label") or session_id)

    pnt_source_sha256 = str(summary.get("pnt_source_sha256") or "")
    if not pnt_source_sha256:
        raise ValueError(f"{summary_path}: missing PNT implementation SHA-256")
    pnt_source_path = _resolve_archived_path(
        summary_path,
        summary,
        relative_keys=("pnt_source_relative_path",),
        path_keys=("pnt_source_path",),
    )
    if pnt_source_path is None:
        raise ValueError(f"{summary_path}: cannot resolve the replayed PNT implementation")
    if _sha256(pnt_source_path) != pnt_source_sha256:
        raise ValueError(f"{summary_path}: replayed PNT implementation SHA-256 mismatch")

    source_paths: list[Path] = []
    seed_path = _resolve_archived_path(
        summary_path,
        summary,
        relative_keys=("seed_relative_path",),
        path_keys=("seed_path",),
    )
    if seed_path is None:
        raise ValueError(f"{summary_path}: cannot resolve the archived seed document")
    expected_seed_sha = _summary_digest(summary, "seed_sha256")
    if expected_seed_sha is None:
        raise ValueError(f"{summary_path}: missing archived seed SHA-256")
    if _sha256(seed_path) != expected_seed_sha:
        raise ValueError(f"{summary_path}: archived seed SHA-256 mismatch")
    source_paths.append(seed_path)
    selection_source = _resolve_archived_path(
        summary_path,
        summary,
        relative_keys=("source_relative_path",),
        path_keys=("source_path",),
    )
    if selection_source is not None:
        expected_source_sha = _summary_digest(summary, "source_sha256")
        if expected_source_sha is not None and _sha256(selection_source) != expected_source_sha:
            raise ValueError(f"{summary_path}: sealed selection source SHA-256 mismatch")
        source_paths.append(selection_source)
    return DwellSource(
        label=label,
        session_id=session_id,
        summary_path=summary_path,
        npz_path=npz_path,
        summary=summary,
        release_sha=release_sha,
        pnt_source_path=pnt_source_path,
        pnt_source_sha256=pnt_source_sha256,
        source_paths=tuple(source_paths),
    )


def discover_sources(
    source_root: Path,
    explicit_summaries: Sequence[Path] = (),
    *,
    enforce_primary: bool = True,
) -> tuple[DwellSource, ...]:
    paths = (
        tuple(explicit_summaries)
        if explicit_summaries
        else tuple(sorted(source_root.glob("*-filter-benchmark-summary.json")))
    )
    if len(paths) != 5:
        raise ValueError(f"expected exactly five per-dwell summaries, found {len(paths)}")
    sources = tuple(_load_source(path) for path in paths)
    sessions = tuple(source.session_id for source in sources)
    if len(set(sessions)) != len(sessions):
        raise ValueError("five-dwell cohort contains duplicate session IDs")
    release_shas = {source.release_sha for source in sources}
    if len(release_shas) != 1:
        raise ValueError(f"five-dwell cohort spans capture releases: {sorted(release_shas)}")
    pnt_source_shas = {source.pnt_source_sha256 for source in sources}
    if len(pnt_source_shas) != 1:
        raise ValueError(
            "five-dwell cohort was replayed with different PNT implementations: "
            f"{sorted(pnt_source_shas)}"
        )
    if enforce_primary:
        if set(sessions) != set(PRIMARY_SESSION_IDS):
            raise ValueError(
                "default report requires the frozen five untouched sessions; "
                f"got {sorted(sessions)}"
            )
        if D3_DEVELOPMENT_SESSION_ID in sessions:
            raise ValueError("D3 development dwell must not enter the untouched cohort")
    order = {session_id: index for index, session_id in enumerate(PRIMARY_SESSION_IDS)}
    return tuple(
        sorted(
            sources,
            key=lambda source: (order.get(source.session_id, len(order)), source.session_id),
        )
    )


def _validated_sha256(value: Any, field: str) -> str:
    digest = str(value or "").lower()
    if len(digest) != 64:
        raise ValueError(f"{field} is not a SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ValueError(f"{field} is not a SHA-256 digest") from error
    return digest


def validate_parity_attestation(
    path: Path,
    sources: Sequence[DwellSource],
) -> ValidatedParityAttestation:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"source-replay parity attestation is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"source-replay parity attestation is not readable JSON: {path}"
        ) from error
    if not isinstance(document, dict):
        raise ValueError("source-replay parity attestation must be a JSON object")
    if document.get("schema") != PARITY_SCHEMA:
        raise ValueError(f"source-replay parity schema mismatch: {document.get('schema')!r}")
    if document.get("all_seed_json_identical") is not True:
        raise ValueError("source-replay parity does not attest all seed JSON as identical")
    if document.get("all_npz_identical") is not True:
        raise ValueError("source-replay parity does not attest all NPZ arrays as identical")

    source_by_label = {source.label: source for source in sources}
    if len(source_by_label) != 5:
        raise ValueError("source-replay parity validation requires five unique source labels")
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("source-replay parity must contain exactly five rows")
    row_by_label: dict[str, dict[str, Any]] = {}
    for offset, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"source-replay parity row {offset} is not an object")
        label = str(row.get("label", ""))
        if not label or label in row_by_label:
            raise ValueError("source-replay parity row labels must be nonempty and unique")
        row_by_label[label] = row
    if set(row_by_label) != set(source_by_label):
        raise ValueError("source-replay parity labels do not exactly match the five loaded dwells")

    for label, source in source_by_label.items():
        row = row_by_label[label]
        if row.get("seed_json_identical") is not True:
            raise ValueError(f"{label}: seed JSON parity row is not identical")
        if row.get("npz_identical") is not True:
            raise ValueError(f"{label}: NPZ parity row is not identical")
        row_seed_sha = _validated_sha256(row.get("seed_sha256"), f"{label} seed_sha256")
        row_npz_sha = _validated_sha256(row.get("npz_sha256"), f"{label} npz_sha256")
        summary_seed_sha = _validated_sha256(
            source.summary.get("seed_sha256"), f"{label} summary seed_sha256"
        )
        summary_npz_sha = _validated_sha256(
            source.summary.get("npz_sha256"), f"{label} summary npz_sha256"
        )
        actual_seed_sha = _sha256(source.source_paths[0])
        actual_npz_sha = _sha256(source.npz_path)
        if len({row_seed_sha, summary_seed_sha, actual_seed_sha}) != 1:
            raise ValueError(f"{label}: parity seed digest disagrees with loaded summary or file")
        if len({row_npz_sha, summary_npz_sha, actual_npz_sha}) != 1:
            raise ValueError(f"{label}: parity NPZ digest disagrees with loaded summary or file")

    executed_pnt_sha = _validated_sha256(
        document.get("executed_pnt_source_sha256"),
        "executed_pnt_source_sha256",
    )
    cohort_pnt_shas = {source.pnt_source_sha256 for source in sources}
    if cohort_pnt_shas != {executed_pnt_sha}:
        raise ValueError(
            "source-replay parity executed PNT digest disagrees with the loaded cohort"
        )
    return ValidatedParityAttestation(
        path=path,
        sha256=_sha256(path),
        document=document,
    )


def _merge_model_parts(parts: Iterable[Any], name: str) -> Any:
    return _d3_tool()._merge_series(parts, name)


def _build_models(windows: Sequence[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    d3 = _d3_tool()
    parts: dict[str, list[Any]] = {
        "trailing_20ms": [],
        "trailing_50ms": [],
        "current_v2": [],
        "robust_jump_filter": [],
        "phase_gated_jump_filter": [],
        "block_60_40_holdout": [],
        "offline_block_smoother": [],
    }
    jump_results = []
    phase_jump_results = []
    offline_degrees = []
    for window in windows:
        parts["trailing_20ms"].append(d3.trailing_line_predictions(window, history_s=0.020))
        parts["trailing_50ms"].append(d3.trailing_line_predictions(window, history_s=0.050))
        parts["current_v2"].append(d3.v2_predictions(window))
        jump, jump_result = d3.jump_filter_predictions(window)
        parts["robust_jump_filter"].append(jump)
        jump_results.append(jump_result)
        phase_jump, phase_result = d3.jump_filter_predictions(window, phase_gated=True)
        parts["phase_gated_jump_filter"].append(phase_jump)
        phase_jump_results.append(phase_result)
        parts["block_60_40_holdout"].append(d3.frozen_block_holdout(window))
        offline, degree = d3.offline_block_smoother(window)
        parts["offline_block_smoother"].append(offline)
        if degree is not None:
            offline_degrees.append(int(degree))
    models = {name: _merge_model_parts(rows, name) for name, rows in parts.items()}
    auxiliary = {
        "jump_results": jump_results,
        "phase_jump_results": phase_jump_results,
        "offline_degrees": offline_degrees,
    }
    return models, auxiliary


def recording_block_equal_statistics(
    residual_by_key: Mapping[tuple[int, int], float],
    key_time_s: Mapping[tuple[int, int], float],
    *,
    keys: Iterable[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    selected_keys = tuple(residual_by_key) if keys is None else tuple(keys)
    selected_keys = tuple(key for key in selected_keys if key in residual_by_key)
    if not selected_keys:
        raise ValueError("block-equal statistic has no prediction frames")
    blocks: dict[int, list[float]] = {}
    for key in selected_keys:
        if key not in key_time_s:
            raise ValueError(f"missing recording time for frame key {key}")
        block = int(math.floor(float(key_time_s[key])))
        blocks.setdefault(block, []).append(float(residual_by_key[key]))
    block_mse = np.asarray(
        [np.mean(np.square(blocks[block])) for block in sorted(blocks)], dtype=float
    )
    return {
        "frame_count": len(selected_keys),
        "recording_anchored_one_second_block_count": len(blocks),
        "block_equal_rms_hz": float(np.sqrt(np.mean(block_mse))),
        "block_equal_mean_absolute_error_hz": float(
            np.mean([np.mean(np.abs(blocks[block])) for block in sorted(blocks)])
        ),
        "recording_second_indices": sorted(blocks),
    }


def pairwise_block_comparison(
    candidate: Any,
    baseline: Any,
    key_time_s: Mapping[tuple[int, int], float],
) -> dict[str, Any]:
    common = tuple(
        sorted(
            set(candidate.residual_by_key) & set(baseline.residual_by_key),
            key=lambda key: (key_time_s[key], key),
        )
    )
    if not common:
        raise ValueError(f"{candidate.name} versus {baseline.name} has no common prediction frames")
    candidate_stats = recording_block_equal_statistics(
        candidate.residual_by_key, key_time_s, keys=common
    )
    baseline_stats = recording_block_equal_statistics(
        baseline.residual_by_key, key_time_s, keys=common
    )
    candidate_rms = float(candidate_stats["block_equal_rms_hz"])
    baseline_rms = float(baseline_stats["block_equal_rms_hz"])
    if not math.isfinite(candidate_rms) or not math.isfinite(baseline_rms):
        raise ValueError("paired block RMS is non-finite")
    if candidate_rms <= 0.0 or baseline_rms <= 0.0:
        raise ValueError("paired block RMS must be positive for a ratio comparison")
    return {
        "candidate": candidate.name,
        "baseline": baseline.name,
        "common_frame_count": len(common),
        "recording_anchored_one_second_block_count": candidate_stats[
            "recording_anchored_one_second_block_count"
        ],
        "candidate_block_equal_rms_hz": candidate_rms,
        "baseline_block_equal_rms_hz": baseline_rms,
        "candidate_to_baseline_rms_ratio": candidate_rms / baseline_rms,
        "fractional_rms_improvement": 1.0 - candidate_rms / baseline_rms,
        "mask_definition": "intersection of the two methods' available frame keys",
    }


def _qualified_interval_components(rows: Sequence[Mapping[str, Any]]) -> int:
    times = sorted(float(row["center_time_s"]) for row in rows if row.get("qualified"))
    components = 0
    previous: float | None = None
    for time_s in times:
        if previous is None or time_s - previous >= 0.1:
            components += 1
        previous = time_s
    return components


def _phase_evidence(windows: Sequence[Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    d3 = _d3_tool()
    arcs = [
        (window, arc)
        for window in windows
        for arc in d3.phase_arcs(window)
        if arc[1] - arc[0] + 1 >= d3.PHASE_ARC_MINIMUM_FRAMES
    ]
    durations_ms = [(end - start + 1) / d3.FRAME_RATE_HZ * 1_000.0 for _, (start, end) in arcs]
    arc_windows = {int(window.index) for window, _ in arcs}
    arc_blocks = {
        int(math.floor(float(window.absolute_time_s[start]))) for window, (start, _) in arcs
    }
    exact_windows = tuple(summary.get("exact_windows", ()))
    rolled_windows = tuple(summary.get("rolled_windows", ()))
    exact = summary.get("exact", {})
    rolled = summary.get("rolled", {})
    window_count = int(summary["window_count"])
    if len(exact_windows) != window_count or len(rolled_windows) != window_count:
        raise ValueError("matched exact/rolled window summaries must preserve every seed bin")
    return {
        "seed_window_count": window_count,
        "exact_qualified_windows": int(exact.get("qualified_count", 0)),
        "exact_qualified_fraction": int(exact.get("qualified_count", 0)) / window_count,
        "exact_supported_frames": int(exact.get("supported_frames", 0)),
        "exact_qualified_interval_component_count": _qualified_interval_components(exact_windows),
        "rolled_qin_qualified_windows": int(rolled.get("qualified_count", 0)),
        "rolled_qin_qualified_fraction": int(rolled.get("qualified_count", 0)) / window_count,
        "rolled_qin_supported_frames": int(rolled.get("supported_frames", 0)),
        "explicit_no_reacquisition_phase_arc_count": len(arcs),
        "explicit_phase_arc_window_count": len(arc_windows),
        "explicit_phase_arc_one_second_block_count": len(arc_blocks),
        "explicit_phase_arc_total_duration_ms": float(sum(durations_ms)),
        "explicit_phase_arc_median_duration_ms": (
            float(np.median(durations_ms)) if durations_ms else None
        ),
        "explicit_phase_arc_maximum_duration_ms": (
            float(np.max(durations_ms)) if durations_ms else None
        ),
        "interpretation": (
            "local modulo-pi consistency only; no absolute carrier phase, code phase, "
            "pseudorange, or cross-window phase continuity"
        ),
    }


def evaluate_dwell(source: DwellSource) -> DwellEvaluation:
    d3 = _d3_tool()
    windows = tuple(d3._load_windows(source.npz_path))
    if not windows:
        raise ValueError(f"{source.session_id}: replay NPZ contains no frame rows")
    for window in windows:
        if bool(window.raw_disjoint) != (int(window.index) % 2 == 0):
            raise ValueError(
                f"{source.session_id}: raw-disjoint mask is not the frozen even-bin rule"
            )
    selected = tuple(window for window in windows if window.raw_disjoint)
    planned_even = int(source.summary["raw_disjoint_window_count"])
    if planned_even <= 0:
        raise ValueError(f"{source.session_id}: no planned even seed bins")
    if len(selected) > planned_even:
        raise ValueError(f"{source.session_id}: emitted more even bins than were planned")
    key_time_s = {
        window.key(offset): float(window.absolute_time_s[offset])
        for window in selected
        for offset in range(len(window.absolute_time_s))
    }
    supported_denominator = sum(int(np.count_nonzero(window.supported)) for window in selected)
    if supported_denominator <= 0:
        raise ValueError(f"{source.session_id}: even-bin replay has no supported frames")

    models, auxiliary = _build_models(selected)
    marginal = {
        name: d3._series_statistics(model, key_time_s, denominator=supported_denominator)
        for name, model in models.items()
    }
    marginal["current_v2"]["rate_bound_hit_count"] = sum(
        int(np.count_nonzero(np.abs(window.tracked_rate_hz_s) >= 14_999.0)) for window in selected
    )
    for name, results in (
        ("robust_jump_filter", auxiliary["jump_results"]),
        ("phase_gated_jump_filter", auxiliary["phase_jump_results"]),
    ):
        locklets = [locklet for result in results for locklet in result.locklets]
        durations_ms = [
            (locklet.end_s - locklet.start_s + 1.0 / d3.FRAME_RATE_HZ) * 1_000.0
            for locklet in locklets
        ]
        marginal[name].update(
            {
                "locklet_count": len(locklets),
                "median_locklet_duration_ms": (
                    float(np.median(durations_ms)) if durations_ms else None
                ),
                "maximum_locklet_duration_ms": (
                    float(np.max(durations_ms)) if durations_ms else None
                ),
                "reacquisition_count": sum(result.reacquisition_count for result in results),
                "change_point_count": sum(result.change_point_count for result in results),
            }
        )

    all_common_keys = set(models[CAUSAL_MODELS[0]].residual_by_key)
    for name in CAUSAL_MODELS[1:]:
        all_common_keys &= set(models[name].residual_by_key)
    all_common = tuple(sorted(all_common_keys, key=lambda key: (key_time_s[key], key)))
    if all_common:
        all_common_stats = {
            name: recording_block_equal_statistics(
                models[name].residual_by_key, key_time_s, keys=all_common
            )
            for name in CAUSAL_MODELS
        }
        all_common_evidence = {
            "status": "estimable",
            "models": list(CAUSAL_MODELS),
            "common_frame_count": len(all_common),
            "recording_anchored_one_second_block_count": all_common_stats[CAUSAL_MODELS[0]][
                "recording_anchored_one_second_block_count"
            ],
            "model_statistics": all_common_stats,
        }
        estimability = {
            "status": "estimable",
            "criterion": "non-empty common prediction mask across all four causal models",
            "reason": None,
        }
    else:
        reason = (
            "no common prediction frames across all four causal models on the fixed even-bin lane"
        )
        all_common_evidence = {
            "status": "not_estimable",
            "models": list(CAUSAL_MODELS),
            "common_frame_count": 0,
            "recording_anchored_one_second_block_count": 0,
            "model_statistics": {},
            "reason": reason,
        }
        estimability = {
            "status": "not_estimable",
            "criterion": "non-empty common prediction mask across all four causal models",
            "reason": reason,
        }
    pairwise = {}
    for left, right in combinations(CAUSAL_MODELS, 2):
        for candidate, baseline in ((left, right), (right, left)):
            key = f"{candidate}_vs_{baseline}"
            try:
                comparison = pairwise_block_comparison(
                    models[candidate], models[baseline], key_time_s
                )
                comparison["status"] = "estimable"
                pairwise[key] = comparison
            except ValueError as error:
                pairwise[key] = {
                    "status": "not_estimable",
                    "candidate": candidate,
                    "baseline": baseline,
                    "common_frame_count": len(
                        set(models[candidate].residual_by_key)
                        & set(models[baseline].residual_by_key)
                    ),
                    "reason": str(error),
                    "mask_definition": "intersection of the two methods' available frame keys",
                }
    phase = _phase_evidence(windows, source.summary)
    evidence = {
        "label": source.label,
        "session_id": source.session_id,
        "stream_id": source.summary.get("stream_id"),
        "receiver_id": source.summary.get("receiver_id"),
        "edge": source.summary.get("edge"),
        "capture_release_sha": source.release_sha,
        "selection": source.summary.get("selection"),
        "estimability": estimability,
        "corpus": {
            "planned_seed_window_count": int(source.summary["window_count"]),
            "planned_even_raw_disjoint_window_count": planned_even,
            "emitted_even_raw_disjoint_window_count": len(selected),
            "even_raw_disjoint_bins_without_frame_rows": planned_even - len(selected),
            "even_raw_disjoint_supported_frame_count": supported_denominator,
            "all_replay_frame_count": int(source.summary.get("frame_count", 0)),
            "inference_block_anchor": "floor(recording-relative absolute_time_s)",
            "filter_initialization_scope": "independent restart in each 100 ms seed window",
        },
        "all_causal_common_mask": all_common_evidence,
        "pairwise_common_masks": pairwise,
        "marginal_own_available_prediction_statistics": marginal,
        "phase_lock": phase,
        "offline_model_degree_counts": {
            str(degree): auxiliary["offline_degrees"].count(degree) for degree in (1, 2, 3)
        },
    }
    plotting = {
        "label": source.label,
        "session_id": source.session_id,
        "summary": source.summary,
        "all_windows": windows,
        "selected_windows": selected,
        "models": models,
        "key_time_s": key_time_s,
        "all_common_keys": all_common,
    }
    return DwellEvaluation(evidence=evidence, plotting=plotting)


def exact_two_sided_sign_test(ratios: Sequence[float]) -> dict[str, Any]:
    wins = sum(value < 1.0 for value in ratios)
    losses = sum(value > 1.0 for value in ratios)
    ties = len(ratios) - wins - losses
    trials = wins + losses
    if trials == 0:
        probability = 1.0
        win_fraction = None
    else:
        tail = sum(math.comb(trials, index) for index in range(min(wins, losses) + 1))
        probability = min(1.0, 2.0 * tail / (2**trials))
        win_fraction = wins / trials
    return {
        "candidate_better_dwell_count": wins,
        "candidate_worse_dwell_count": losses,
        "tied_dwell_count": ties,
        "non_tied_dwell_count": trials,
        "candidate_better_fraction_of_non_ties": win_fraction,
        "exact_two_sided_sign_probability": probability,
        "null": "each non-tied dwell is equally likely to favor either method",
    }


def _geometric_mean(values: Sequence[float]) -> float:
    array: NDArray[np.float64] = np.asarray(values, dtype=float)
    if not len(array) or np.any(~np.isfinite(array)) or np.any(array <= 0.0):
        raise ValueError("geometric mean requires finite positive values")
    return float(np.exp(np.mean(np.log(array))))


def _aggregate_complete_cases(
    evaluations: Sequence[DwellEvaluation],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not evaluations:
        raise ValueError("complete-case aggregation requires at least one estimable dwell")
    labels = [row.evidence["label"] for row in evaluations]
    aggregate_comparisons = {}
    comparison_names = sorted(evaluations[0].evidence["pairwise_common_masks"])
    for name in comparison_names:
        rows = [row.evidence["pairwise_common_masks"][name] for row in evaluations]
        if any(row.get("status") != "estimable" for row in rows):
            aggregate_comparisons[name] = {
                "status": "not_estimable",
                "candidate": rows[0]["candidate"],
                "baseline": rows[0]["baseline"],
                "reason": "one or more all-causal complete cases lacks this pairwise mask",
                "estimable_dwell_labels": [
                    label
                    for label, row in zip(labels, rows, strict=True)
                    if row.get("status") == "estimable"
                ],
            }
            continue
        ratios = [float(item["candidate_to_baseline_rms_ratio"]) for item in rows]
        leave_one_out = (
            [
                _geometric_mean([value for index, value in enumerate(ratios) if index != omitted])
                for omitted in range(len(ratios))
            ]
            if len(ratios) > 1
            else ratios
        )
        geometric_ratio = _geometric_mean(ratios)
        aggregate_comparisons[name] = {
            "status": "estimable_complete_case_sensitivity",
            "candidate": rows[0]["candidate"],
            "baseline": rows[0]["baseline"],
            "dwell_count": len(rows),
            "per_dwell": [
                {
                    "label": label,
                    "candidate_to_baseline_rms_ratio": ratio,
                    "fractional_rms_improvement": 1.0 - ratio,
                    "common_frame_count": row["common_frame_count"],
                    "recording_anchored_one_second_block_count": row[
                        "recording_anchored_one_second_block_count"
                    ],
                }
                for label, ratio, row in zip(labels, ratios, rows, strict=True)
            ],
            "equal_dwell_geometric_mean_rms_ratio": geometric_ratio,
            "equal_dwell_fractional_rms_improvement": 1.0 - geometric_ratio,
            "leave_one_dwell_out_geometric_mean_ratio_min": min(leave_one_out),
            "leave_one_dwell_out_geometric_mean_ratio_max": max(leave_one_out),
            "leave_one_dwell_out_range_is_descriptive_not_a_confidence_interval": True,
            "sign_test": exact_two_sided_sign_test(ratios),
            "inference_unit": "dwell",
            "frame_level_resampling_performed": False,
        }

    all_common_models = {}
    for name in CAUSAL_MODELS:
        rms = [
            float(
                row.evidence["all_causal_common_mask"]["model_statistics"][name][
                    "block_equal_rms_hz"
                ]
            )
            for row in evaluations
        ]
        all_common_models[name] = {
            "per_dwell_block_equal_rms_hz": dict(zip(labels, rms, strict=True)),
            "equal_dwell_geometric_mean_block_equal_rms_hz": _geometric_mean(rms),
        }
    return all_common_models, aggregate_comparisons


def aggregate_evaluations(evaluations: Sequence[DwellEvaluation]) -> dict[str, Any]:
    if len(evaluations) != 5:
        raise ValueError(f"expected five independently evaluated dwells, got {len(evaluations)}")
    labels = [row.evidence["label"] for row in evaluations]
    if len(set(labels)) != len(labels):
        raise ValueError("dwell labels must be unique")
    estimable = tuple(
        row for row in evaluations if row.evidence["estimability"]["status"] == "estimable"
    )
    not_estimable = tuple(
        row for row in evaluations if row.evidence["estimability"]["status"] != "estimable"
    )
    all_common_models, aggregate_comparisons = _aggregate_complete_cases(estimable)
    primary_status = "estimable" if not not_estimable else "not_estimable"
    primary = {
        "status": primary_status,
        "required_dwell_count": 5,
        "estimable_dwell_count": len(estimable),
        "not_estimable_dwell_count": len(not_estimable),
        "not_estimable_dwells": [
            {
                "label": row.evidence["label"],
                "session_id": row.evidence["session_id"],
                "reason": row.evidence["estimability"]["reason"],
                "even_raw_disjoint_supported_frame_count": row.evidence["corpus"][
                    "even_raw_disjoint_supported_frame_count"
                ],
            }
            for row in not_estimable
        ],
        "five_dwell_effect_statistics_available": not not_estimable,
        "reason": (
            None
            if not not_estimable
            else "at least one predeclared dwell has no all-causal common scoring mask"
        ),
    }
    complete_case = {
        "status": ("same_as_primary" if not not_estimable else "post_observation_sensitivity_only"),
        "estimable_dwell_count": len(estimable),
        "estimable_dwell_labels": [row.evidence["label"] for row in estimable],
        "omitted_dwell_labels": [row.evidence["label"] for row in not_estimable],
        "omission_is_explicit_completeness_failure": bool(not_estimable),
        "all_causal_common_mask": {
            "models": all_common_models,
            "mask_is_recomputed_within_each_dwell": True,
            "dwells_have_equal_weight": True,
        },
        "pairwise_common_masks": aggregate_comparisons,
    }

    marginal_models = {}
    model_names = tuple(evaluations[0].evidence["marginal_own_available_prediction_statistics"])
    for name in model_names:
        rows = [
            row.evidence["marginal_own_available_prediction_statistics"][name]
            for row in evaluations
        ]
        available_rms = [float(item["rms_hz"]) for item in rows if item["rms_hz"] is not None]
        marginal_models[name] = {
            "equal_dwell_mean_prediction_coverage_fraction": float(
                np.mean([item["prediction_coverage_fraction"] for item in rows])
            ),
            "per_dwell_prediction_coverage_fraction": dict(
                zip(labels, [item["prediction_coverage_fraction"] for item in rows], strict=True)
            ),
            "per_dwell_own_available_rms_hz": dict(
                zip(labels, [item["rms_hz"] for item in rows], strict=True)
            ),
            "own_available_rms_estimable_dwell_count": len(available_rms),
            "equal_dwell_geometric_mean_own_available_rms_hz": (
                _geometric_mean(available_rms) if available_rms else None
            ),
        }
        for key in (
            "one_sigma_coverage",
            "two_sigma_coverage",
            "three_sigma_coverage",
        ):
            values = [float(item[key]) for item in rows if item.get(key) is not None]
            marginal_models[name][f"equal_dwell_mean_{key}"] = (
                float(np.mean(values)) if values else None
            )
            marginal_models[name][f"per_dwell_{key}"] = dict(
                zip(labels, [item.get(key) for item in rows], strict=True)
            )

    phase_rows = [row.evidence["phase_lock"] for row in evaluations]
    return {
        "primary_five_dwell": primary,
        "complete_case_sensitivity": complete_case,
        # Convenience aliases used by plots/report.  Their status is always
        # carried by complete_case_sensitivity and must not be mistaken for a
        # primary five-dwell estimate when any dwell is unestimable.
        "all_causal_common_mask": complete_case["all_causal_common_mask"],
        "pairwise_common_masks": complete_case["pairwise_common_masks"],
        "marginal_own_available_prediction_statistics": marginal_models,
        "phase_lock": {
            "exact_qualified_windows": sum(item["exact_qualified_windows"] for item in phase_rows),
            "rolled_qin_qualified_windows": sum(
                item["rolled_qin_qualified_windows"] for item in phase_rows
            ),
            "seed_window_count": sum(item["seed_window_count"] for item in phase_rows),
            "equal_dwell_mean_exact_qualified_fraction": float(
                np.mean([item["exact_qualified_fraction"] for item in phase_rows])
            ),
            "equal_dwell_mean_rolled_qin_qualified_fraction": float(
                np.mean([item["rolled_qin_qualified_fraction"] for item in phase_rows])
            ),
            "explicit_no_reacquisition_phase_arc_count": sum(
                item["explicit_no_reacquisition_phase_arc_count"] for item in phase_rows
            ),
            "per_dwell": dict(zip(labels, phase_rows, strict=True)),
            "interpretation": phase_rows[0]["interpretation"],
        },
        "missing_even_bins": {
            row.evidence["label"]: row.evidence["corpus"][
                "even_raw_disjoint_bins_without_frame_rows"
            ]
            for row in evaluations
        },
    }


def build_evidence(
    sources: Sequence[DwellSource],
    evaluations: Sequence[DwellEvaluation],
    parity_attestation: ValidatedParityAttestation,
) -> dict[str, Any]:
    release_shas = {source.release_sha for source in sources}
    if len(release_shas) != 1:
        raise ValueError("evaluated dwells do not share one capture release")
    pnt_source_shas = {source.pnt_source_sha256 for source in sources}
    if len(pnt_source_shas) != 1:
        raise ValueError("evaluated dwells do not share one PNT implementation")
    aggregate = aggregate_evaluations(evaluations)
    implementation_paths = {
        "five_dwell_extractor": Path(__file__).with_name(
            "extract_five_dwell_pilot_filter_benchmark.py"
        ),
        "five_dwell_report": Path(__file__).resolve(),
        "frozen_d3_evaluator": Path(__file__).with_name("report_d3_pilot_filter_prototypes.py"),
        "pilot_locklet_prototypes": Path(__file__).parents[1]
        / "src/leo/analysis/research/pilot_locklet_prototypes.py",
        "pilot_pnt_kalman": sources[0].pnt_source_path,
    }
    absent = [name for name, path in implementation_paths.items() if not path.is_file()]
    if absent:
        raise ValueError(f"implementation provenance files are absent: {absent}")
    implementation = {
        name: {"path": str(path.resolve()), "sha256": _sha256(path)}
        for name, path in implementation_paths.items()
    }
    if implementation["pilot_pnt_kalman"]["sha256"] != next(iter(pnt_source_shas)):
        raise ValueError("cohort PNT digest disagrees with implementation provenance")
    return {
        "schema": EVIDENCE_SCHEMA,
        "status": (
            "primary_five_dwell_not_estimable_with_complete_case_sensitivity"
            if aggregate["primary_five_dwell"]["status"] == "not_estimable"
            else "primary_five_dwell_estimable"
        ),
        "cohort": {
            "definition": "all same-release continuity-v2 campaign dwells except D3 development",
            "dwell_count": len(sources),
            "session_ids": [source.session_id for source in sources],
            "d3_development_session_excluded": D3_DEVELOPMENT_SESSION_ID,
            "capture_release_sha": next(iter(release_shas)),
            "pnt_source_sha256": next(iter(pnt_source_shas)),
            "receiver_path": "stream-1 / Radio1 / RX1",
            "selection_rule": "strongest phase-blind frozen GLRT-margin seed in each 100 ms bin",
            "scoring_subset": "fixed even-numbered 100 ms bins",
            "inference_unit": "dwell; recording-anchored one-second blocks are descriptive within-dwell aggregators",
            "primary_completeness_required": True,
        },
        "fixed_configuration": {
            "causal_models": list(CAUSAL_MODELS),
            "trailing_histories_ms": [20.0, 50.0],
            "block_duration_ms": 15.0,
            "phase_arc_gate_rad": _d3_tool().PHASE_ARC_GATE_RAD,
            "phase_arc_minimum_frames": _d3_tool().PHASE_ARC_MINIMUM_FRAMES,
            "filters_restart_per_seed_window": True,
            "prototype_hyperparameters_were_not_refit_per_dwell": True,
            "tle_or_satellite_conditioning": False,
        },
        "implementation_sources": implementation,
        "source_replay_parity_attestation": {
            "path": str(parity_attestation.path),
            "sha256": parity_attestation.sha256,
            "validated_document": parity_attestation.document,
        },
        "per_dwell": [row.evidence for row in evaluations],
        "aggregate_equal_dwell": aggregate,
        "limitations": [
            "Errors are innovations against a noisy extracted frame-CFO estimate; true CFO is unknown.",
            "Causal scores begin after whole-capture-frozen GLRT seed, epoch, and CFO selection; this is not an end-to-end online detector score.",
            "Every filter restarts independently inside each 100 ms seed window; this is not a continuous 60 s filter replay.",
            "Only fixed even-numbered seed bins enter scores. Planned bins with no emitted frame rows remain explicit missing bins and never enter a denominator.",
            "Own-available marginal statistics have different masks and utilization and must not be rank-compared.",
            "Headline ratios give each dwell equal weight. Frames are not pooled as independent trials and no frame-level bootstrap is used.",
            "If any predeclared dwell lacks the all-causal common mask, the primary five-dwell effect is unavailable; any remaining complete-case aggregate is explicitly post-observation sensitivity only.",
            (
                "The exact two-sided sign test has only "
                f"{aggregate['complete_case_sensitivity']['estimable_dwell_count']} "
                "complete-case dwell-level outcomes and correspondingly coarse resolution."
            ),
            "The phase-gated jump filter reuses V2 phase-update evidence; it is a lifecycle wrapper, not an independent raw-phase discriminator.",
            "Phase arcs are local modulo-pi consistency only, independently initialized and overlap-conditioned; they do not establish carrier/code phase, pseudorange, or cross-window continuity.",
            "Rolled Qin is a matched pilot-specificity control on selected RF windows, not a universal false-alarm measurement.",
            "Offline smoother residuals use future data and are an in-sample reference, never a causal forecast.",
            "Prototype hyperparameters were frozen from D3 development rather than nested-cross-validated on these five dwells.",
            "No TLE, orbit, satellite identity, or visibility information enters this benchmark.",
        ],
    }


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _plot_common_mask_rms(path: Path, evidence: Mapping[str, Any]) -> None:
    rows = evidence["per_dwell"]
    sensitivity = evidence["aggregate_equal_dwell"]["complete_case_sensitivity"]
    labels = [row["label"] for row in rows] + [
        f"{sensitivity['estimable_dwell_count']}-dwell complete-case\ngeo. mean"
    ]
    x: NDArray[np.float64] = np.arange(len(labels), dtype=float)
    width = 0.19
    fig, axis = plt.subplots(figsize=(14, 5.2))
    aggregate = evidence["aggregate_equal_dwell"]["all_causal_common_mask"]["models"]
    for index, name in enumerate(CAUSAL_MODELS):
        values = [
            (
                row["all_causal_common_mask"]["model_statistics"][name]["block_equal_rms_hz"]
                if row["all_causal_common_mask"]["status"] == "estimable"
                else np.nan
            )
            for row in rows
        ] + [aggregate[name]["equal_dwell_geometric_mean_block_equal_rms_hz"]]
        axis.bar(
            x + (index - 1.5) * width,
            values,
            width,
            label=MODEL_LABELS[name],
            color=MODEL_COLORS[name],
        )
    axis.set_xticks(x, labels)
    axis.set_ylabel("Recording-block-equal frame-CFO innovation RMS (Hz)")
    axis.set_title(
        "All four causal models on one common frame mask within each dwell\n"
        "D4 is retained as not estimable; aggregate is complete-case sensitivity only"
    )
    axis.legend(frameon=False, ncol=4, loc="upper left")
    axis.text(
        0.995,
        0.98,
        "One-second blocks are recording-anchored; N/E bars are not imputed",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color="#555555",
    )
    for index, row in enumerate(rows):
        if row["all_causal_common_mask"]["status"] != "estimable":
            axis.text(
                index,
                0.02,
                "N/E\nno common mask",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="bottom",
                fontsize=8,
                color="#555555",
            )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _plot_effects(path: Path, evidence: Mapping[str, Any]) -> None:
    aggregate = evidence["aggregate_equal_dwell"]["pairwise_common_masks"]
    aggregate_root = evidence["aggregate_equal_dwell"]
    comparisons = [
        aggregate["robust_jump_filter_vs_current_v2"],
        aggregate["robust_jump_filter_vs_trailing_20ms"],
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), sharey=True)
    for axis, comparison in zip(axes, comparisons, strict=True):
        rows_by_label = {row["label"]: row for row in comparison["per_dwell"]}
        labels = [row["label"] for row in evidence["per_dwell"]]
        y: NDArray[np.float64] = np.arange(len(labels), dtype=float)
        estimable_rows = [
            (row_y, rows_by_label[label])
            for row_y, label in zip(y, labels, strict=True)
            if label in rows_by_label
        ]
        values = [row["candidate_to_baseline_rms_ratio"] for _, row in estimable_rows]
        colors = ["#1b9e77" if value < 1.0 else "#d95f02" for value in values]
        estimable_y = [row_y for row_y, _ in estimable_rows]
        axis.scatter(values, estimable_y, s=54, c=colors, zorder=3)
        for row_y, value in zip(estimable_y, values, strict=True):
            axis.plot([1.0, value], [row_y, row_y], color="#aaaaaa", linewidth=1.0)
        for row_y, label in zip(y, labels, strict=True):
            if label not in rows_by_label:
                axis.text(
                    0.02,
                    row_y,
                    "N/E — no common mask",
                    transform=axis.get_yaxis_transform(),
                    ha="left",
                    va="center",
                    color="#555555",
                    fontsize=8.5,
                )
        aggregate_y = len(labels) + 0.6
        aggregate_ratio = comparison["equal_dwell_geometric_mean_rms_ratio"]
        axis.errorbar(
            aggregate_ratio,
            aggregate_y,
            xerr=np.asarray(
                [
                    [
                        max(
                            0.0,
                            aggregate_ratio
                            - comparison["leave_one_dwell_out_geometric_mean_ratio_min"],
                        )
                    ],
                    [
                        max(
                            0.0,
                            comparison["leave_one_dwell_out_geometric_mean_ratio_max"]
                            - aggregate_ratio,
                        )
                    ],
                ]
            ),
            fmt="D",
            markersize=7,
            color="#222222",
            capsize=4,
            label="equal-dwell geometric mean; whisker = leave-one-dwell-out range",
        )
        axis.axvline(1.0, color="#555555", linewidth=1.0, linestyle="--")
        axis.set_xscale("log")
        finite = values + [
            comparison["leave_one_dwell_out_geometric_mean_ratio_min"],
            comparison["leave_one_dwell_out_geometric_mean_ratio_max"],
        ]
        axis.set_xlim(max(min(finite) * 0.78, 0.05), max(finite) * 1.28)
        axis.set_yticks([*y, aggregate_y], [*labels, "complete-case aggregate"])
        axis.set_xlabel("Candidate / baseline block-equal RMS ratio (log scale)")
        sign = comparison["sign_test"]
        dwell_count = comparison["dwell_count"]
        axis.set_title(
            f"{MODEL_LABELS[comparison['candidate']]} vs {MODEL_LABELS[comparison['baseline']]}\n"
            f"geo. ratio={aggregate_ratio:.3f}; wins={sign['candidate_better_dwell_count']}/{dwell_count}; "
            f"exact two-sided sign p={sign['exact_two_sided_sign_probability']:.3f}"
        )
        axis.legend(frameon=False, loc="lower left")
    sensitivity_count = aggregate_root["complete_case_sensitivity"]["estimable_dwell_count"]
    if aggregate_root["primary_five_dwell"]["status"] == "estimable":
        title = "Primary five-dwell matched-frame effects"
    else:
        title = (
            f"{sensitivity_count}-estimable-dwell complete-case sensitivity; "
            "primary five-dwell effect unavailable"
        )
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _plot_calibration_utilization(path: Path, evidence: Mapping[str, Any]) -> None:
    aggregate = evidence["aggregate_equal_dwell"]["marginal_own_available_prediction_statistics"]
    dwell_labels = [row["label"] for row in evidence["per_dwell"]]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    names = list(CAUSAL_MODELS)
    x: NDArray[np.float64] = np.arange(len(names), dtype=float)
    offsets = np.linspace(-0.18, 0.18, len(dwell_labels))
    for label, offset in zip(dwell_labels, offsets, strict=True):
        values = [
            100.0 * aggregate[name]["per_dwell_prediction_coverage_fraction"][label]
            for name in names
        ]
        axes[0].scatter(x + offset, values, s=24, alpha=0.75, label=label)
    means = [
        100.0 * aggregate[name]["equal_dwell_mean_prediction_coverage_fraction"] for name in names
    ]
    axes[0].scatter(x, means, marker="D", s=70, color="#111111", label="equal-dwell mean")
    axes[0].set_xticks(x, [MODEL_LABELS[name] for name in names], rotation=22, ha="right")
    axes[0].set_ylim(0, 105)
    axes[0].set_ylabel("Supported frames predicted (%)")
    axes[0].set_title("Marginal utilization (own masks)")

    sigma_keys = ("one_sigma_coverage", "two_sigma_coverage", "three_sigma_coverage")
    sx: NDArray[np.float64] = np.arange(3, dtype=float)
    for label, offset in zip(dwell_labels, offsets, strict=True):
        values = [
            (
                aggregate["robust_jump_filter"][f"per_dwell_{key}"][label]
                if aggregate["robust_jump_filter"][f"per_dwell_{key}"][label] is not None
                else np.nan
            )
            for key in sigma_keys
        ]
        axes[1].scatter(sx + offset, values, s=24, alpha=0.75)
    means = [aggregate["robust_jump_filter"][f"equal_dwell_mean_{key}"] for key in sigma_keys]
    axes[1].plot(sx, [0.6827, 0.9545, 0.9973], "o--", color="#777777", label="Gaussian target")
    axes[1].scatter(sx, means, marker="D", s=70, color="#6a3d9a", label="equal-dwell mean")
    axes[1].set_xticks(sx, ["1σ", "2σ", "3σ"])
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("Normalized-innovation coverage")
    axes[1].set_title("Robust-jump calibration")
    axes[1].legend(frameon=False)

    rows = evidence["per_dwell"]
    planned = np.asarray(
        [row["corpus"]["planned_even_raw_disjoint_window_count"] for row in rows],
        dtype=float,
    )
    emitted = np.asarray(
        [row["corpus"]["emitted_even_raw_disjoint_window_count"] for row in rows],
        dtype=float,
    )
    missing = planned - emitted
    bx: NDArray[np.float64] = np.arange(len(rows), dtype=float)
    axes[2].bar(bx, emitted, color="#377eb8", label="bins with frame rows")
    axes[2].bar(bx, missing, bottom=emitted, color="#bdbdbd", label="bins without frame rows")
    axes[2].set_xticks(bx, dwell_labels, rotation=22, ha="right")
    axes[2].set_ylabel("Planned even 100 ms bins")
    axes[2].set_title("Scoring-corpus availability")
    axes[2].legend(frameon=False)
    axes[0].legend(frameon=False, fontsize=7, ncol=2)
    fig.suptitle("Marginal behavior is descriptive and separate from matched-mask ranking")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _plot_phase_control(path: Path, evidence: Mapping[str, Any]) -> None:
    rows = evidence["per_dwell"]
    labels = [row["label"] for row in rows]
    phase = [row["phase_lock"] for row in rows]
    x: NDArray[np.float64] = np.arange(len(rows), dtype=float)
    width = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
    exact = [100.0 * row["exact_qualified_fraction"] for row in phase]
    rolled = [100.0 * row["rolled_qin_qualified_fraction"] for row in phase]
    axes[0].bar(x - width / 2, exact, width, color="#377eb8", label="exact Qin")
    axes[0].bar(x + width / 2, rolled, width, color="#e41a1c", label="17-symbol rolled Qin")
    axes[0].set_xticks(x, labels, rotation=22, ha="right")
    axes[0].set_ylabel("Independently initialized windows qualified (%)")
    axes[0].set_title("Matched pilot-specificity control")
    axes[0].legend(frameon=False)

    arc_counts = [row["explicit_no_reacquisition_phase_arc_count"] for row in phase]
    medians = [row["explicit_phase_arc_median_duration_ms"] for row in phase]
    axes[1].bar(x, arc_counts, color="#1b9e77", alpha=0.75, label="qualified local arcs")
    axes[1].set_xticks(x, labels, rotation=22, ha="right")
    axes[1].set_ylabel("Local no-reacquisition arc count")
    twin = axes[1].twinx()
    valid = [(index, value) for index, value in enumerate(medians) if value is not None]
    if valid:
        twin.scatter(
            [index for index, _ in valid],
            [value for _, value in valid],
            marker="D",
            color="#6a3d9a",
            label="median duration",
        )
    twin.set_ylabel("Median local arc duration (ms)")
    axes[1].set_title("Descriptive modulo-π arcs")
    handles, legend_labels = axes[1].get_legend_handles_labels()
    twin_handles, twin_labels = twin.get_legend_handles_labels()
    axes[1].legend(handles + twin_handles, legend_labels + twin_labels, frameon=False)
    fig.suptitle("Phase evidence is local to each 100 ms initialization, not dwell-long lock")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _qin_confidence(
    exact: np.ndarray,
    control: np.ndarray,
    *,
    exact_scale: float,
    margin_scale: float,
) -> np.ndarray:
    positive_margin = np.maximum(exact - control, 0.0)
    return np.sqrt(
        np.clip(exact / max(exact_scale, 1e-12), 0.0, 1.0)
        * np.clip(positive_margin / max(margin_scale, 1e-12), 0.0, 1.0)
    )


def _plot_timelines(path: Path, evaluations: Sequence[DwellEvaluation]) -> None:
    all_exact = np.concatenate(
        [
            window.exact_coherence
            for evaluation in evaluations
            for window in evaluation.plotting["selected_windows"]
        ]
    )
    all_control = np.concatenate(
        [
            window.control_coherence
            for evaluation in evaluations
            for window in evaluation.plotting["selected_windows"]
        ]
    )
    exact_scale = max(float(np.quantile(all_exact, 0.95)), 1e-12)
    margin_scale = max(float(np.quantile(np.maximum(all_exact - all_control, 0.0), 0.95)), 1e-12)
    fig, axes = plt.subplots(len(evaluations), 1, figsize=(15, 12), sharex=True)
    for row_index, (axis, evaluation) in enumerate(zip(axes, evaluations, strict=True)):
        plotting = evaluation.plotting
        windows = plotting["selected_windows"]
        time_s = np.concatenate([window.absolute_time_s for window in windows])
        cfo_khz = np.concatenate([window.cfo_hz for window in windows]) / 1_000.0
        exact = np.concatenate([window.exact_coherence for window in windows])
        control = np.concatenate([window.control_coherence for window in windows])
        confidence = _qin_confidence(
            exact,
            control,
            exact_scale=exact_scale,
            margin_scale=margin_scale,
        )
        colors: NDArray[np.float64] = np.zeros((len(time_s), 4), dtype=float)
        colors[:, :3] = (0.16, 0.46, 0.70)
        colors[:, 3] = 0.02 + 0.55 * confidence**1.25
        axis.scatter(
            time_s,
            cfo_khz,
            s=3,
            c=colors,
            linewidths=0,
            rasterized=True,
            label="frame CFO; opacity ∝ Qin confidence" if row_index == 0 else None,
        )
        for name, size in (("trailing_20ms", 6.0), ("robust_jump_filter", 6.0)):
            model = plotting["models"][name]
            keys = sorted(model.prediction_by_key, key=lambda key: plotting["key_time_s"][key])
            keys = keys[::4]
            axis.scatter(
                [plotting["key_time_s"][key] for key in keys],
                [model.prediction_by_key[key] / 1_000.0 for key in keys],
                s=size,
                color=MODEL_COLORS[name],
                alpha=0.65,
                linewidths=0,
                rasterized=True,
                label=MODEL_LABELS[name] if row_index == 0 else None,
            )
        axis.set_ylabel(f"{evaluation.evidence['label']}\nCFO (kHz)")
        axis.set_xlim(0.0, 60.0)
        if len(time_s):
            last_time = float(np.max(time_s))
            if last_time < 60.0:
                axis.axvspan(last_time, 60.0, color="#eeeeee", alpha=0.55, linewidth=0)
        if row_index == 0:
            axis.legend(frameon=False, ncol=3, loc="upper left")
    axes[-1].set_xlabel("Recording-relative capture time (s)")
    fig.suptitle(
        "Five untouched dwells: fixed even-bin frame CFO and post-seed causal predictions\n"
        "Every model restarts in each selected 100 ms window; lines are not dwell-continuous tracks"
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return f"{float(value):.{digits}f}"


def _comparison_sentence(comparison: Mapping[str, Any]) -> str:
    ratio = comparison["equal_dwell_geometric_mean_rms_ratio"]
    direction = "lower" if ratio < 1.0 else "higher"
    magnitude = abs(100.0 * (ratio - 1.0))
    sign = comparison["sign_test"]
    dwell_count = int(comparison["dwell_count"])
    return (
        f"{MODEL_LABELS[comparison['candidate']]} has {magnitude:.1f}% {direction} "
        f"matched block-equal RMS than {MODEL_LABELS[comparison['baseline']]} by the "
        f"equal-dwell geometric mean (ratio {ratio:.3f}); it wins "
        f"{sign['candidate_better_dwell_count']}/{dwell_count} complete-case dwells and the exact two-sided sign "
        f"probability is {sign['exact_two_sided_sign_probability']:.3f}."
    )


def _write_report(path: Path, evidence: Mapping[str, Any], figures: Mapping[str, str]) -> None:
    rows = evidence["per_dwell"]
    aggregate = evidence["aggregate_equal_dwell"]
    primary = aggregate["primary_five_dwell"]
    sensitivity = aggregate["complete_case_sensitivity"]
    jump_v2 = aggregate["pairwise_common_masks"]["robust_jump_filter_vs_current_v2"]
    jump_line = aggregate["pairwise_common_masks"]["robust_jump_filter_vs_trailing_20ms"]
    parity = evidence["source_replay_parity_attestation"]
    parity_link = os.path.relpath(Path(parity["path"]), path.parent)
    common_rows = []
    for row in rows:
        stats = row["all_causal_common_mask"]
        if stats["status"] != "estimable":
            common_rows.append(
                f"| **{row['label']} — not estimable** | 0 | 0 | n/a | n/a | n/a | n/a |"
            )
            continue
        common_rows.append(
            "| "
            + row["label"]
            + f" | {_fmt(stats['common_frame_count'], 0)} | {_fmt(stats['recording_anchored_one_second_block_count'], 0)} | "
            + " | ".join(
                _fmt(stats["model_statistics"][name]["block_equal_rms_hz"])
                for name in CAUSAL_MODELS
            )
            + " |"
        )
    geo = aggregate["all_causal_common_mask"]["models"]
    common_rows.append(
        f"| **{sensitivity['estimable_dwell_count']}-dwell complete-case geometric mean** | — | — | "
        + " | ".join(
            f"**{_fmt(geo[name]['equal_dwell_geometric_mean_block_equal_rms_hz'])}**"
            for name in CAUSAL_MODELS
        )
        + " |"
    )

    comparison_rows = []
    for comparison in (jump_v2, jump_line):
        sign = comparison["sign_test"]
        dwell_count = int(comparison["dwell_count"])
        comparison_rows.append(
            f"| {MODEL_LABELS[comparison['candidate']]} | {MODEL_LABELS[comparison['baseline']]} | "
            f"{comparison['equal_dwell_geometric_mean_rms_ratio']:.3f} | "
            f"{100 * comparison['equal_dwell_fractional_rms_improvement']:.1f}% | "
            f"{sign['candidate_better_dwell_count']}/{dwell_count} | "
            f"{sign['exact_two_sided_sign_probability']:.3f} | "
            f"{comparison['leave_one_dwell_out_geometric_mean_ratio_min']:.3f}–"
            f"{comparison['leave_one_dwell_out_geometric_mean_ratio_max']:.3f} |"
        )

    marginal_rows = []
    marginal = aggregate["marginal_own_available_prediction_statistics"]
    for name in MODEL_LABELS:
        if name not in marginal:
            continue
        marginal_rows.append(
            f"| {MODEL_LABELS[name]} | "
            f"{100 * marginal[name]['equal_dwell_mean_prediction_coverage_fraction']:.1f}% | "
            f"{_fmt(marginal[name]['equal_dwell_geometric_mean_own_available_rms_hz'])} | "
            f"{marginal[name]['own_available_rms_estimable_dwell_count']}/5 |"
        )

    phase_rows = []
    for row in rows:
        phase = row["phase_lock"]
        phase_rows.append(
            f"| {row['label']} | {phase['exact_qualified_windows']}/{phase['seed_window_count']} | "
            f"{phase['rolled_qin_qualified_windows']}/{phase['seed_window_count']} | "
            f"{phase['explicit_no_reacquisition_phase_arc_count']} | "
            f"{_fmt(phase['explicit_phase_arc_median_duration_ms'])} / "
            f"{_fmt(phase['explicit_phase_arc_maximum_duration_ms'])} ms |"
        )

    failed_rows = primary["not_estimable_dwells"]
    failed_text = "; ".join(
        f"{row['label']} ({row['even_raw_disjoint_supported_frame_count']} supported even-lane frames: {row['reason']})"
        for row in failed_rows
    )
    primary_result = (
        "The predeclared primary five-dwell effect is estimable."
        if primary["status"] == "estimable"
        else (
            "**The predeclared primary five-dwell effect is unavailable.** "
            f"Completeness failed for {failed_text}. This dwell remains in every corpus, "
            "marginal, phase-control, and timeline accounting; no error or zero is imputed."
        )
    )
    text = f"""# Five untouched dwells: robust pilot-filter benchmark

## Result

{primary_result}

As a clearly labeled **{sensitivity["estimable_dwell_count"]}-dwell complete-case sensitivity only**, {_comparison_sentence(jump_v2)} {_comparison_sentence(jump_line)} This subset was determined after observing the completeness failure and is not a replacement for the unavailable primary result. With only {sensitivity["estimable_dwell_count"]} dwell-level outcomes, the sign test is deliberately coarse; these numbers show direction and effect size, not a high-power confirmatory claim.

This uses the D3-frozen filter settings and scoring logic on every same-release campaign dwell except the D3 development dwell, with the predeclared sealed-Standard 100 ms seed protocol. It is a retrospective filter benchmark, not satellite identification. True CFO is unknown, so every error below is an innovation against the noisy 1.3 ms frame-CFO estimator.

## One all-causal common mask per dwell

| Dwell | Common frames | Recording 1 s blocks | 20 ms line RMS (Hz) | Current V2 RMS (Hz) | Robust jump RMS (Hz) | Phase-gated jump RMS (Hz) |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(common_rows)}

Each dwell constructs its own intersection of all four causal methods. A frame never crosses dwells, and each occupied recording-anchored one-second block receives equal weight inside its dwell. D4 has no such intersection and is displayed as not estimable. The final row is the geometric mean of only the {sensitivity["estimable_dwell_count"]} explicit complete cases; it does not flatten frames into one pseudo-sample and must not be read as the primary five-dwell result.

## Complete-case matched-pair sensitivity (non-primary)

| Candidate | Baseline | Equal-dwell RMS ratio | Improvement | Dwell wins | Exact two-sided sign p | Leave-one-dwell-out ratio range |
|---|---|---:|---:|---:|---:|---:|
{chr(10).join(comparison_rows)}

Every ratio is recomputed on that pair's common frame mask inside the same {sensitivity["estimable_dwell_count"]} all-causal complete cases. The leave-one-dwell-out range is a sensitivity diagnostic, not a confidence interval. No frame-level bootstrap or IID-frame inference is performed. The primary five-dwell effect remains unavailable.

## Marginal utilization

| Model | Five-dwell mean utilization | Geometric mean own-mask RMS (Hz) | RMS-estimable dwells |
|---|---:|---:|---:|
{chr(10).join(marginal_rows)}

These rows use each model's own available predictions. They reveal utilization and failure modes, but their RMS values must not be rank-compared when masks differ. Planned even bins that emitted no frame rows remain explicit missing bins in the evidence and availability plot; they are never silently counted as zero-error observations or removed from the planned-bin count.

## Phase and rolled-Qin control

| Dwell | Exact qualified | Rolled qualified | Explicit local arcs | Median / max arc duration |
|---|---:|---:|---:|---:|
{chr(10).join(phase_rows)}

The exact and 17-symbol-rolled Qin results use the same frozen RF seed windows. Rolled Qin therefore tests pilot specificity on this selected corpus, not a universal false-alarm rate. The explicit arcs are a separate V2-derived local modulo-π criterion. Independently initialized overlapping arcs are not physical-emitter counts and do not establish absolute carrier phase, code phase, pseudorange, or continuity between 100 ms windows.

## Figures

![All-causal common-mask RMS]({figures["common_rms"]})

![Matched per-dwell effects]({figures["effects"]})

![Calibration and utilization]({figures["calibration"]})

![Phase and rolled-Qin control]({figures["phase"]})

![Five dwell Qin-opacity timelines]({figures["timelines"]})

## Scientific boundary

- “Causal” begins only after the strongest whole-capture-frozen GLRT seed, epoch, and initial CFO were selected. This is not an end-to-end online detector evaluation.
- Every filter restarts inside each selected 100 ms window. The timeline overlays are short post-seed predictions, not continuous 60 s tracks.
- The robust-jump covariance calibration is descriptive; framewise normalized innovations are serially dependent and source conditioned.
- The phase-gated jump filter reuses V2 phase-update decisions and is not an independent raw-phase discriminator.
- The offline smoother sees future samples and remains an in-sample floor/reference, never a causal competitor.
- Hyperparameters were frozen after D3 development and were not nested-cross-validated on this five-dwell cohort.
- A predeclared dwell with no all-causal common mask makes the primary five-dwell effect unavailable. The {sensitivity["estimable_dwell_count"]}-dwell complete-case aggregate is post-observation sensitivity only and does not silently exclude the failed dwell.
- No TLE, orbit, satellite visibility, or satellite identity enters selection, filtering, or scoring.

## Provenance

- Evidence schema: `{evidence["schema"]}`.
- Capture release: `{evidence["cohort"]["capture_release_sha"]}`.
- Frozen PNT implementation: `{evidence["cohort"]["pnt_source_sha256"]}` (identical in all five replay summaries).
- Independent replay parity: [source-replay-parity-attestation.json]({parity_link}), SHA-256 `{parity["sha256"]}`; the validated document attests byte-identical seed JSON and NPZ products for all five labels under the cohort PNT source.
- Receiver path: `{evidence["cohort"]["receiver_path"]}`.
- Cohort: `{", ".join(evidence["cohort"]["session_ids"])}`.
- Scoring: fixed even-numbered 100 ms bins and recording-anchored one-second block aggregation within dwell. Five-dwell completeness is required for the primary effect; the displayed {sensitivity["estimable_dwell_count"]}-dwell geometric aggregate is explicitly non-primary sensitivity.
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    sources = discover_sources(
        arguments.source_root,
        arguments.summary,
        enforce_primary=not arguments.allow_nonprimary_cohort,
    )
    parity_path = (
        arguments.parity_attestation
        if arguments.parity_attestation is not None
        else arguments.source_root.parent / "source-replay-parity-attestation.json"
    )
    parity_attestation = validate_parity_attestation(parity_path, sources)
    evaluations = tuple(evaluate_dwell(source) for source in sources)
    evidence = build_evidence(sources, evaluations, parity_attestation)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    _style()
    figure_paths = {
        "common_rms": arguments.output_root / "01-five-dwell-common-mask-rms.png",
        "effects": arguments.output_root / "02-five-dwell-matched-effects.png",
        "calibration": arguments.output_root / "03-five-dwell-calibration-utilization.png",
        "phase": arguments.output_root / "04-five-dwell-phase-control.png",
        "timelines": arguments.output_root / "05-five-dwell-qin-opacity-timelines.png",
    }
    _plot_common_mask_rms(figure_paths["common_rms"], evidence)
    _plot_effects(figure_paths["effects"], evidence)
    _plot_calibration_utilization(figure_paths["calibration"], evidence)
    _plot_phase_control(figure_paths["phase"], evidence)
    _plot_timelines(figure_paths["timelines"], evaluations)

    evidence["source"] = [
        {
            "label": source.label,
            "session_id": source.session_id,
            "summary_path": str(source.summary_path),
            "summary_sha256": _sha256(source.summary_path),
            "npz_path": str(source.npz_path),
            "npz_sha256": _sha256(source.npz_path),
            "seed_or_selection_sources": [
                {"path": str(path), "sha256": _sha256(path)} for path in source.source_paths
            ],
            "pnt_source_sha256": source.summary.get("pnt_source_sha256"),
            "pnt_source_path": str(source.pnt_source_path),
            "recording_manifest_sha256": source.summary.get("recording_manifest_sha256"),
        }
        for source in sources
    ]
    evidence["figures"] = {
        name: {"path": str(path), "sha256": _sha256(path)} for name, path in figure_paths.items()
    }
    evidence_path = arguments.output_root / "five-dwell-pilot-filter-prototype-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    relative_figures = {
        name: os.path.relpath(path, arguments.report.parent) for name, path in figure_paths.items()
    }
    _write_report(arguments.report, evidence, relative_figures)
    print(
        json.dumps(
            {
                "evidence": str(evidence_path),
                "report": str(arguments.report),
                "primary_comparisons": {
                    name: evidence["aggregate_equal_dwell"]["pairwise_common_masks"][name]
                    for name in (
                        "robust_jump_filter_vs_current_v2",
                        "robust_jump_filter_vs_trailing_20ms",
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
