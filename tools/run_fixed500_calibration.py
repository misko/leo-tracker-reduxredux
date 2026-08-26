#!/usr/bin/env python3
"""Execute the frozen fixed500 calibration and true sample-clock experiment."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib
import json
import math
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.doppler_dataset_policy import (  # noqa: E402
    CaptureDisposition,
    finalize_capture_dispositions,
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from leo.analysis.research.fixed500_calibration import (  # noqa: E402
    FrozenCalibrationScenario,
    GroupedConformalQuantile,
    causal_quadratic_rates,
    clock_scale,
    evaluate_resampled_exact_qin_frames,
    grouped_conformal_multiplier,
    inject_resampled_exact_qin,
    load_frozen_scenarios,
    resampled_frame_starts,
    select_spaced_endpoints,
)
from leo.analysis.research.polynomial_injection import (  # noqa: E402
    FrameCfoEvidence,
    fixed_history_rate_estimates,
    truth_at_receiver_time,
)
from leo.analysis.research.polynomial_injection_protocol import (  # noqa: E402
    PolynomialInjectionProtocol,
    load_polynomial_injection_protocol,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402

DEFAULT_POLICY = Path("config/analysis/doppler-experiment-dataset-policy-v1.json")
DEFAULT_BASE_PROTOCOL = Path("config/analysis/polynomial-phase-injection-protocol-v1.json")
DEFAULT_PROTOCOL = Path("config/analysis/fixed500-calibration-protocol-v1.json")
DEFAULT_EXECUTION_AMENDMENT = Path(
    "config/analysis/fixed500-calibration-execution-amendment-v1.json"
)
DEFAULT_SOURCE_LAYOUT_AMENDMENT = Path(
    "config/analysis/fixed500-calibration-source-layout-amendment-v1.json"
)
DEFAULT_CORRECTIVE_ANALYSIS_AMENDMENT = Path(
    "config/analysis/fixed500-calibration-corrective-analysis-amendment-v1.json"
)
DEFAULT_CORRECTIVE_EXECUTION_AUTHORITY = Path(
    "config/analysis/fixed500-calibration-corrective-execution-v1.json"
)
DEFAULT_OUTPUT = Path("reports/figures/2026_08_26_fixed500_calibration")
DEFAULT_REPORT = Path("reports/2026_08_26_fixed500_calibration_results.md")
PROTOCOL_COMMIT = "8e6e98e4a3824723b04ef3c9bcb92df3080a7336"
ORIGINAL_IMPLEMENTATION_COMMIT = "46f93773f4a53c041e64406185247fa4622bedd3"
CORRECTIVE_ANALYSIS_COMMIT = "14b76e6be6a6511f6552eec2f44cf143d6f0ac4f"


def _read_verified_background(binding: object, *, policy: object) -> Any:
    """Reuse the already audited digest-verifying reader without static coupling."""

    module = importlib.import_module("run_polynomial_qin_injection")
    reader = module._read_verified_background
    return reader(binding, policy=policy)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--base-protocol", type=Path, default=DEFAULT_BASE_PROTOCOL)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--execution-amendment", type=Path, default=DEFAULT_EXECUTION_AMENDMENT)
    parser.add_argument(
        "--source-layout-amendment", type=Path, default=DEFAULT_SOURCE_LAYOUT_AMENDMENT
    )
    parser.add_argument(
        "--corrective-analysis-amendment",
        type=Path,
        default=DEFAULT_CORRECTIVE_ANALYSIS_AMENDMENT,
    )
    parser.add_argument(
        "--corrective-execution-authority",
        type=Path,
        default=DEFAULT_CORRECTIVE_EXECUTION_AUTHORITY,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def _verify_execution_authority(
    root: Path,
    protocol_path: Path,
    base_protocol_path: Path,
    policy_path: Path,
    amendment_path: Path,
    source_layout_amendment_path: Path,
    corrective_analysis_path: Path,
    corrective_execution_path: Path,
) -> tuple[dict[str, Any], str, dict[str, object]]:
    head = _git_head(root)
    if not _git_is_ancestor(root, PROTOCOL_COMMIT, head):
        raise ValueError("frozen fixed500 protocol commit is not an ancestor of execution HEAD")
    config = json.loads(protocol_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("fixed500 protocol is not an object")
    authority = config.get("input_authority")
    if not isinstance(authority, dict):
        raise ValueError("fixed500 protocol has no input authority")
    if _sha256_file(policy_path) != authority.get("dataset_policy_sha256"):
        raise ValueError("dataset policy differs from fixed500 freeze")
    if _sha256_file(base_protocol_path) != authority.get("background_binding_source_sha256"):
        raise ValueError("background binding protocol differs from fixed500 freeze")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError("canonical fixed500 execution requires a clean committed worktree")
    if corrective_execution_path.is_file():
        corrective_analysis = json.loads(corrective_analysis_path.read_text(encoding="utf-8"))
        if (
            not isinstance(corrective_analysis, dict)
            or corrective_analysis.get("schema")
            != "org.leo.research.fixed500-calibration-corrective-analysis-amendment/v1"
            or corrective_analysis.get("original_protocol_commit") != PROTOCOL_COMMIT
            or not _git_is_ancestor(root, CORRECTIVE_ANALYSIS_COMMIT, head)
        ):
            raise ValueError("fixed500 corrective analysis amendment identity differs")
        corrective_execution = json.loads(corrective_execution_path.read_text(encoding="utf-8"))
        if (
            not isinstance(corrective_execution, dict)
            or corrective_execution.get("schema")
            != "org.leo.research.fixed500-calibration-corrective-execution/v1"
            or corrective_execution.get("protocol_commit") != PROTOCOL_COMMIT
            or corrective_execution.get("corrective_analysis_amendment_sha256")
            != _sha256_file(corrective_analysis_path)
        ):
            raise ValueError("fixed500 corrective execution authority identity differs")
        implementation_commit = corrective_execution.get("corrected_implementation_commit")
        if not isinstance(implementation_commit, str) or not _git_is_ancestor(
            root, implementation_commit, head
        ):
            raise ValueError("corrective fixed500 implementation is not an ancestor of HEAD")
        hashes = corrective_execution.get("implementation_sha256")
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("fixed500 corrective execution authority has no hashes")
        for relative_path, expected in hashes.items():
            if not isinstance(relative_path, str) or not isinstance(expected, str):
                raise ValueError("fixed500 corrective execution hash binding is malformed")
            if _sha256_file(root / relative_path) != expected:
                raise ValueError(f"fixed500 corrective execution hash differs: {relative_path}")
        execution_authority = {
            "mode": "hash_bound_post_outcome_scientific_correction",
            "corrective_analysis_amendment_path": str(corrective_analysis_path),
            "corrective_analysis_amendment_sha256": _sha256_file(corrective_analysis_path),
            "corrective_execution_authority_path": str(corrective_execution_path),
            "corrective_execution_authority_sha256": _sha256_file(corrective_execution_path),
            "corrected_implementation_commit": implementation_commit,
            "post_outcome_correction": True,
        }
    elif head == ORIGINAL_IMPLEMENTATION_COMMIT:
        execution_authority: dict[str, object] = {
            "mode": "original_implementation_commit",
            "implementation_commit": ORIGINAL_IMPLEMENTATION_COMMIT,
        }
    else:
        amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
        if (
            not isinstance(amendment, dict)
            or amendment.get("schema")
            != "org.leo.research.fixed500-calibration-execution-amendment/v1"
            or amendment.get("protocol_commit") != PROTOCOL_COMMIT
            or amendment.get("failed_execution_commit") != ORIGINAL_IMPLEMENTATION_COMMIT
        ):
            raise ValueError("fixed500 execution amendment identity differs")
        implementation_commit = amendment.get("corrected_implementation_commit")
        if not isinstance(implementation_commit, str) or not _git_is_ancestor(
            root, implementation_commit, head
        ):
            raise ValueError("corrected fixed500 implementation is not an ancestor of HEAD")
        hashes = amendment.get("implementation_sha256")
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("fixed500 execution amendment has no implementation hashes")
        old_hashes_match = True
        for relative_path, expected in hashes.items():
            if not isinstance(relative_path, str) or not isinstance(expected, str):
                raise ValueError("fixed500 execution amendment hash binding is malformed")
            if _sha256_file(root / relative_path) != expected:
                old_hashes_match = False
        if old_hashes_match:
            execution_authority = {
                "mode": "hash_bound_serialization_correction",
                "amendment_path": str(amendment_path),
                "amendment_sha256": _sha256_file(amendment_path),
                "corrected_implementation_commit": implementation_commit,
                "correction_scope": amendment.get("correction_scope"),
            }
        else:
            source_layout = json.loads(source_layout_amendment_path.read_text(encoding="utf-8"))
            if (
                not isinstance(source_layout, dict)
                or source_layout.get("schema")
                != "org.leo.research.fixed500-calibration-source-layout-amendment/v1"
                or source_layout.get("protocol_commit") != PROTOCOL_COMMIT
                or source_layout.get("prior_execution_amendment_sha256")
                != _sha256_file(amendment_path)
            ):
                raise ValueError("fixed500 source-layout amendment identity differs")
            source_layout_commit = source_layout.get("source_layout_commit")
            if not isinstance(source_layout_commit, str) or not _git_is_ancestor(
                root, source_layout_commit, head
            ):
                raise ValueError("fixed500 source-layout commit is not an ancestor of HEAD")
            layout_hashes = source_layout.get("implementation_sha256")
            if not isinstance(layout_hashes, dict) or not layout_hashes:
                raise ValueError("fixed500 source-layout amendment has no implementation hashes")
            for relative_path, expected in layout_hashes.items():
                if not isinstance(relative_path, str) or not isinstance(expected, str):
                    raise ValueError("fixed500 source-layout hash binding is malformed")
                if _sha256_file(root / relative_path) != expected:
                    raise ValueError(f"fixed500 source-layout hash differs: {relative_path}")
            execution_authority = {
                "mode": "hash_bound_source_layout_maintenance",
                "execution_amendment_path": str(amendment_path),
                "execution_amendment_sha256": _sha256_file(amendment_path),
                "source_layout_amendment_path": str(source_layout_amendment_path),
                "source_layout_amendment_sha256": _sha256_file(source_layout_amendment_path),
                "source_layout_commit": source_layout_commit,
                "scientific_change": False,
            }
    return config, head, execution_authority


def _implementation_receipt(root: Path) -> dict[str, str]:
    paths = (
        Path("tools/run_fixed500_calibration.py"),
        Path("src/leo/analysis/research/fixed500_calibration.py"),
        Path("src/leo/analysis/research/polynomial_injection.py"),
        Path("src/leo/analysis/research/adaptive_frame_cfo.py"),
        Path("src/leo/analysis/qam/pilot.py"),
        Path("src/leo/analysis/starlink/templates.py"),
        Path("src/leo/analysis/research/polynomial_injection_protocol.py"),
        Path("src/leo/analysis/research/doppler_dataset_policy.py"),
        Path("tools/run_polynomial_qin_injection.py"),
        Path("config/analysis/fixed500-calibration-corrective-analysis-amendment-v1.json"),
    )
    return {str(path): _sha256_file(root / path) for path in paths}


def _frame_row(
    item: FrameCfoEvidence,
    frozen: FrozenCalibrationScenario,
    alignment: str,
) -> dict[str, object]:
    scenario = frozen.scenario
    return {
        "scenario_id": scenario.scenario_id,
        "row_id": frozen.row_id,
        "split": frozen.split,
        "alignment": alignment,
        "background_session_id": scenario.background_session_id,
        "seed": scenario.seed,
        "rate_hz_s": scenario.rate_hz_s,
        "acceleration_hz_s2": scenario.acceleration_hz_s2,
        "jerk_hz_s3": scenario.jerk_hz_s3,
        "snr_db": scenario.snr_db,
        "frame_occupancy": scenario.frame_occupancy,
        "alias_change_hz": scenario.alias_change_hz,
        "cfo_step_hz": scenario.cfo_step_hz,
        "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
        "frame_index": item.frame_index,
        "local_frame_start_sample": item.local_frame_start_sample,
        "absolute_frame_start_sample": item.absolute_frame_start_sample,
        "reference_time_s": item.reference_time_s,
        "occupied": item.occupied,
        "status": item.status,
        "training_supported": item.training_supported,
        "training_rejection_reasons": ";".join(item.training_rejection_reasons),
        "even_canonical_cfo_hz": item.even_canonical_cfo_hz,
        "odd_canonical_cfo_hz": item.odd_canonical_cfo_hz,
        "even_profile_margin": item.even_profile_margin,
        "odd_profile_margin": item.odd_profile_margin,
        "receiver_truth_cfo_hz": item.receiver_truth_cfo_hz,
        "even_receiver_error_hz": (
            None
            if item.even_canonical_cfo_hz is None
            else item.even_canonical_cfo_hz - item.receiver_truth_cfo_hz
        ),
        "odd_receiver_error_hz": (
            None
            if item.odd_canonical_cfo_hz is None
            else item.odd_canonical_cfo_hz - item.receiver_truth_cfo_hz
        ),
    }


def _summarize_frames(
    evidence: tuple[FrameCfoEvidence, ...],
    frozen: FrozenCalibrationScenario,
    alignment: str,
) -> dict[str, object]:
    occupied = [item for item in evidence if item.occupied]
    supported = [item for item in evidence if item.training_supported]
    supported_occupied = [item for item in occupied if item.training_supported]
    empty = [item for item in evidence if not item.occupied]
    false_support = [item for item in empty if item.training_supported]
    reasons = Counter(reason for item in evidence for reason in item.training_rejection_reasons)
    even_errors = np.asarray(
        [
            float(item.even_canonical_cfo_hz - item.receiver_truth_cfo_hz)
            for item in supported_occupied
            if item.even_canonical_cfo_hz is not None
        ],
        dtype=float,
    )
    odd_errors = np.asarray(
        [
            float(item.odd_canonical_cfo_hz - item.receiver_truth_cfo_hz)
            for item in supported_occupied
            if item.odd_canonical_cfo_hz is not None
        ],
        dtype=float,
    )
    scenario = frozen.scenario
    return {
        "scenario_id": scenario.scenario_id,
        "row_id": frozen.row_id,
        "split": frozen.split,
        "alignment": alignment,
        "background_session_id": scenario.background_session_id,
        "snr_db": scenario.snr_db,
        "frame_occupancy": scenario.frame_occupancy,
        "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
        "opportunity_count": len(evidence),
        "occupied_count": len(occupied),
        "training_supported_count": len(supported),
        "supported_occupied_count": len(supported_occupied),
        "supported_unoccupied_count": len(false_support),
        "occupied_support_rate": len(supported_occupied) / max(len(occupied), 1),
        "unoccupied_false_support_rate": len(false_support) / max(len(empty), 1),
        "even_cfo_rmse_hz": (float(np.sqrt(np.mean(even_errors**2))) if even_errors.size else None),
        "odd_cfo_rmse_hz": (float(np.sqrt(np.mean(odd_errors**2))) if odd_errors.size else None),
        "rejection_reason_counts": json.dumps(dict(sorted(reasons.items())), sort_keys=True),
    }


def _endpoint_rows(
    evidence: tuple[FrameCfoEvidence, ...],
    frozen: FrozenCalibrationScenario,
    protocol: PolynomialInjectionProtocol,
    alignment: str,
    *,
    step_transition_exclusion_s: float,
) -> list[dict[str, object]]:
    scenario = frozen.scenario
    supported = tuple(
        item
        for item in evidence
        if item.training_supported and item.even_canonical_cfo_hz is not None
    )
    target_times = (0.5, 1.0, 1.5)
    endpoint_starts = (
        select_spaced_endpoints(
            [item.absolute_frame_start_sample for item in supported],
            [item.reference_time_s for item in supported],
            targets_s=target_times,
        )
        if supported
        else ()
    )
    endpoint_by_index: dict[int, int] = {}
    for target_index, target in enumerate(target_times):
        candidates = [item for item in supported if item.reference_time_s >= target - 1e-12]
        if candidates:
            endpoint_by_index[target_index] = candidates[0].absolute_frame_start_sample
    if tuple(endpoint_by_index.values()) != endpoint_starts:
        raise ValueError("component endpoint selector disagrees with frozen target mapping")
    histories = fixed_history_rate_estimates(evidence, scenario, protocol)
    history_maps = {
        method: {
            item.frame_start_sample: item
            for item in histories
            if item.estimator == method and item.frame_start_sample >= 0
        }
        for method in ("fixed_125ms_linear", "fixed_500ms_linear")
    }
    quadratic_map = {item.frame_start_sample: item for item in causal_quadratic_rates(evidence)}
    evidence_map = {item.absolute_frame_start_sample: item for item in evidence}
    rows: list[dict[str, object]] = []
    for target_index, frame_start in endpoint_by_index.items():
        evidence_item = evidence_map[frame_start]
        truth = truth_at_receiver_time(
            scenario,
            evidence_item.reference_time_s,
            carrier_origin_hz=protocol.carrier_origin_hz,
            reference_time_s=protocol.reference_time_s,
            alias_change_time_s=protocol.alias_change_time_s,
            cfo_step_time_s=protocol.cfo_step_time_s,
        )
        for method in ("fixed_125ms_linear", "fixed_500ms_linear"):
            estimate = history_maps[method].get(frame_start)
            point = None if estimate is None else estimate.estimate_rate_hz_s
            sigma = None if estimate is None else estimate.rate_sigma_hz_s
            rows.append(
                _endpoint_row(
                    frozen,
                    alignment,
                    target_index,
                    evidence_item,
                    method,
                    point,
                    sigma,
                    truth.receiver_rate_hz_s,
                    truth.physical_rate_hz_s,
                    endpoint_target_time_s=target_times[target_index],
                    cfo_step_time_s=protocol.cfo_step_time_s,
                    step_transition_exclusion_s=step_transition_exclusion_s,
                )
            )
        quadratic = quadratic_map.get(frame_start)
        rows.append(
            _endpoint_row(
                frozen,
                alignment,
                target_index,
                evidence_item,
                "lean_curvature_500ms",
                None if quadratic is None else quadratic.rate_hz_s,
                None if quadratic is None else quadratic.rate_sigma_hz_s,
                truth.receiver_rate_hz_s,
                truth.physical_rate_hz_s,
                endpoint_target_time_s=target_times[target_index],
                cfo_step_time_s=protocol.cfo_step_time_s,
                step_transition_exclusion_s=step_transition_exclusion_s,
            )
        )
    missing_endpoint_indexes = sorted(set(range(len(target_times))) - set(endpoint_by_index))
    for target_index in missing_endpoint_indexes:
        for method in (
            "fixed_125ms_linear",
            "fixed_500ms_linear",
            "lean_curvature_500ms",
        ):
            rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "row_id": frozen.row_id,
                    "split": frozen.split,
                    "alignment": alignment,
                    "background_session_id": scenario.background_session_id,
                    "snr_db": scenario.snr_db,
                    "frame_occupancy": scenario.frame_occupancy,
                    "acceleration_hz_s2": scenario.acceleration_hz_s2,
                    "jerk_hz_s3": scenario.jerk_hz_s3,
                    "alias_change_hz": scenario.alias_change_hz,
                    "cfo_step_hz": scenario.cfo_step_hz,
                    "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
                    "endpoint_index": target_index,
                    "endpoint_target_time_s": target_times[target_index],
                    "frame_start_sample": -1,
                    "reference_time_s": None,
                    "step_stratum": _step_stratum(
                        cfo_step_hz=scenario.cfo_step_hz,
                        endpoint_time_s=target_times[target_index],
                        cfo_step_time_s=protocol.cfo_step_time_s,
                        transition_exclusion_s=step_transition_exclusion_s,
                    ),
                    "estimator": method,
                    "status": "no_result",
                    "estimate_rate_hz_s": None,
                    "legacy_sigma_hz_s": None,
                    "interval_half_width_hz_s": None,
                    "receiver_truth_rate_hz_s": None,
                    "physical_truth_rate_hz_s": None,
                    "receiver_error_hz_s": None,
                    "physical_error_hz_s": None,
                    "covered": None,
                    "failure": None,
                    "odd_heldout_cfo_error_hz": None,
                }
            )
    return rows


def _endpoint_row(
    frozen: FrozenCalibrationScenario,
    alignment: str,
    endpoint_index: int,
    evidence: FrameCfoEvidence,
    estimator: str,
    estimate_rate_hz_s: float | None,
    sigma_hz_s: float | None,
    receiver_truth_rate_hz_s: float,
    physical_truth_rate_hz_s: float,
    *,
    endpoint_target_time_s: float,
    cfo_step_time_s: float,
    step_transition_exclusion_s: float,
) -> dict[str, object]:
    scenario = frozen.scenario
    receiver_error = (
        None if estimate_rate_hz_s is None else float(estimate_rate_hz_s - receiver_truth_rate_hz_s)
    )
    scale = clock_scale(scenario.sample_clock_offset_ppm)
    physical_estimate = None if estimate_rate_hz_s is None else estimate_rate_hz_s * scale**2
    physical_error = (
        None if physical_estimate is None else float(physical_estimate - physical_truth_rate_hz_s)
    )
    half_width = None if sigma_hz_s is None else 1.96 * sigma_hz_s
    return {
        "scenario_id": scenario.scenario_id,
        "row_id": frozen.row_id,
        "split": frozen.split,
        "alignment": alignment,
        "background_session_id": scenario.background_session_id,
        "snr_db": scenario.snr_db,
        "frame_occupancy": scenario.frame_occupancy,
        "acceleration_hz_s2": scenario.acceleration_hz_s2,
        "jerk_hz_s3": scenario.jerk_hz_s3,
        "alias_change_hz": scenario.alias_change_hz,
        "cfo_step_hz": scenario.cfo_step_hz,
        "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
        "endpoint_index": endpoint_index,
        "endpoint_target_time_s": endpoint_target_time_s,
        "frame_start_sample": evidence.absolute_frame_start_sample,
        "reference_time_s": evidence.reference_time_s,
        "step_stratum": _step_stratum(
            cfo_step_hz=scenario.cfo_step_hz,
            endpoint_time_s=evidence.reference_time_s,
            cfo_step_time_s=cfo_step_time_s,
            transition_exclusion_s=step_transition_exclusion_s,
        ),
        "estimator": estimator,
        "status": "complete"
        if receiver_error is not None and half_width is not None
        else "no_result",
        "estimate_rate_hz_s": estimate_rate_hz_s,
        "legacy_sigma_hz_s": sigma_hz_s,
        "interval_half_width_hz_s": half_width,
        "receiver_truth_rate_hz_s": receiver_truth_rate_hz_s,
        "physical_truth_rate_hz_s": physical_truth_rate_hz_s,
        "receiver_error_hz_s": receiver_error,
        "physical_error_hz_s": physical_error,
        "covered": (
            None
            if receiver_error is None or half_width is None
            else abs(receiver_error) <= half_width
        ),
        "failure": None if receiver_error is None else abs(receiver_error) > 500.0,
        "odd_heldout_cfo_error_hz": (
            None
            if evidence.odd_canonical_cfo_hz is None
            else evidence.odd_canonical_cfo_hz - evidence.receiver_truth_cfo_hz
        ),
    }


def _step_stratum(
    *,
    cfo_step_hz: float,
    endpoint_time_s: float,
    cfo_step_time_s: float,
    transition_exclusion_s: float,
) -> str:
    if cfo_step_hz == 0.0:
        return "no_step"
    if endpoint_time_s < cfo_step_time_s:
        return "pre_step"
    if endpoint_time_s <= cfo_step_time_s + transition_exclusion_s:
        return "transition_excluded"
    return "post_exclusion"


def _calibrate_intervals(
    rows: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    GroupedConformalQuantile,
]:
    calibration_rows = [
        row
        for row in rows
        if row["alignment"] == "oracle_true_resampled_lattice"
        and row["split"] == "calibration"
        and row["estimator"] == "fixed_500ms_linear"
        and float(row["cfo_step_hz"]) == 0.0
        and row["status"] == "complete"
    ]
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in calibration_rows:
        grouped[str(row["scenario_id"])].append(row)
    scores: list[dict[str, object]] = []
    for scenario_id, selected in sorted(grouped.items()):
        if len(selected) < 2:
            continue
        standardized = [
            abs(float(row["receiver_error_hz_s"])) / max(float(row["legacy_sigma_hz_s"]), 1.0)
            for row in selected
        ]
        scores.append(
            {
                "scenario_id": scenario_id,
                "background_session_id": selected[0]["background_session_id"],
                "endpoint_count": len(selected),
                "maximum_standardized_error": max(standardized),
            }
        )
    quantile = grouped_conformal_multiplier(
        [float(row["maximum_standardized_error"]) for row in scores]
    )
    diagnostic: list[dict[str, object]] = []
    for row in rows:
        if row["estimator"] != "fixed_500ms_linear":
            continue
        updated = dict(row)
        updated["estimator"] = "fixed_500ms_max_score_diagnostic"
        if row["status"] == "complete":
            half_width = quantile.diagnostic_max_multiplier * float(row["legacy_sigma_hz_s"])
            error = float(row["receiver_error_hz_s"])
            updated["interval_half_width_hz_s"] = half_width
            updated["covered"] = abs(error) <= half_width
        diagnostic.append(updated)
    return rows + diagnostic, scores, quantile


def _scenario_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["scenario_id"]), str(row["alignment"]), str(row["estimator"]))].append(row)
    output: list[dict[str, object]] = []
    for (scenario_id, alignment, estimator), selected in sorted(groups.items()):
        base = selected[0]
        complete = [item for item in selected if item["status"] == "complete"]
        errors = np.asarray([float(item["receiver_error_hz_s"]) for item in complete])
        interval_complete = [
            item
            for item in complete
            if item["covered"] is not None and item["interval_half_width_hz_s"] is not None
        ]
        coverage = np.asarray([bool(item["covered"]) for item in interval_complete])
        half_widths = np.asarray(
            [float(item["interval_half_width_hz_s"]) for item in interval_complete]
        )
        output.append(
            {
                "scenario_id": scenario_id,
                "row_id": base["row_id"],
                "split": base["split"],
                "alignment": alignment,
                "estimator": estimator,
                "background_session_id": base["background_session_id"],
                "snr_db": base["snr_db"],
                "frame_occupancy": base["frame_occupancy"],
                "acceleration_hz_s2": base["acceleration_hz_s2"],
                "jerk_hz_s3": base["jerk_hz_s3"],
                "alias_change_hz": base["alias_change_hz"],
                "cfo_step_hz": base["cfo_step_hz"],
                "sample_clock_offset_ppm": base["sample_clock_offset_ppm"],
                "expected_endpoint_count": 3,
                "complete_endpoint_count": len(complete),
                "evaluable": len(complete) == 3,
                "interval_evaluable": len(interval_complete) == 3,
                "bias_hz_s": float(np.mean(errors)) if errors.size else None,
                "mse_hz2_s2": float(np.mean(errors**2)) if errors.size else None,
                "rmse_hz_s": float(np.sqrt(np.mean(errors**2))) if errors.size else None,
                "median_absolute_error_hz_s": (
                    float(np.median(np.abs(errors))) if errors.size else None
                ),
                "failure_rate": (float(np.mean(np.abs(errors) > 500.0)) if errors.size else None),
                "endpoint_coverage": float(np.mean(coverage)) if coverage.size else None,
                "scenario_simultaneous_coverage": (
                    bool(np.all(coverage)) if coverage.size == 3 else None
                ),
                "median_interval_half_width_hz_s": (
                    float(np.median(half_widths)) if half_widths.size else None
                ),
            }
        )
    return output


def _primary_aggregate(
    scenario_metrics: list[dict[str, object]],
    primary_ids: set[str],
) -> list[dict[str, object]]:
    methods = (
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "fixed_500ms_max_score_diagnostic",
        "lean_curvature_500ms",
    )
    output: list[dict[str, object]] = []
    for method in methods:
        selected = [
            row
            for row in scenario_metrics
            if row["scenario_id"] in primary_ids
            and row["alignment"] == "oracle_true_resampled_lattice"
            and row["estimator"] == method
        ]
        evaluable = [row for row in selected if bool(row["evaluable"])]
        mse = np.asarray([float(row["mse_hz2_s2"]) for row in evaluable])
        output.append(
            {
                "estimator": method,
                "scenario_count": len(selected),
                "evaluable_scenario_count": len(evaluable),
                "background_count": len({row["background_session_id"] for row in evaluable}),
                "bias_hz_s": (
                    float(np.mean([float(row["bias_hz_s"]) for row in evaluable]))
                    if evaluable
                    else None
                ),
                "rmse_hz_s": float(np.sqrt(np.mean(mse))) if mse.size else None,
                "median_absolute_error_hz_s": (
                    float(np.mean([float(row["median_absolute_error_hz_s"]) for row in evaluable]))
                    if evaluable
                    else None
                ),
                "failure_rate": (
                    float(np.mean([float(row["failure_rate"]) for row in evaluable]))
                    if evaluable
                    else None
                ),
                "endpoint_coverage": (
                    float(np.mean([float(row["endpoint_coverage"]) for row in evaluable]))
                    if evaluable
                    else None
                ),
                "scenario_simultaneous_coverage": (
                    float(
                        np.mean(
                            [
                                bool(row["scenario_simultaneous_coverage"])
                                for row in evaluable
                                if row["scenario_simultaneous_coverage"] is not None
                            ]
                        )
                    )
                    if any(row["scenario_simultaneous_coverage"] is not None for row in evaluable)
                    else None
                ),
                "median_interval_half_width_hz_s": (
                    float(
                        np.median(
                            [float(row["median_interval_half_width_hz_s"]) for row in evaluable]
                        )
                    )
                    if evaluable
                    else None
                ),
            }
        )
    return output


def _promotion(
    aggregate: list[dict[str, object]],
    scenario_metrics: list[dict[str, object]],
    endpoint_rows: list[dict[str, object]],
    injection_ledger: list[dict[str, object]],
    primary_ids: set[str],
    gates: dict[str, Any],
    quantile: GroupedConformalQuantile,
) -> dict[str, object]:
    by_method = {str(row["estimator"]): row for row in aggregate}
    fixed = by_method["fixed_500ms_linear"]
    diagnostic = by_method["fixed_500ms_max_score_diagnostic"]
    curvature = by_method["lean_curvature_500ms"]
    fixed_rmse = _required_float(fixed, "rmse_hz_s")
    diagnostic_rmse = _required_float(diagnostic, "rmse_hz_s")
    curvature_rmse = _required_float(curvature, "rmse_hz_s")
    diagnostic_scenarios = [
        row
        for row in scenario_metrics
        if row["scenario_id"] in primary_ids
        and row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] == "fixed_500ms_max_score_diagnostic"
        and bool(row["evaluable"])
    ]
    background_coverage = {
        background: float(
            np.mean(
                [
                    bool(row["scenario_simultaneous_coverage"])
                    for row in diagnostic_scenarios
                    if row["background_session_id"] == background
                ]
            )
        )
        for background in sorted(
            {str(row["background_session_id"]) for row in diagnostic_scenarios}
        )
    }
    resampling_rows = [
        row
        for row in injection_ledger
        if row["scenario_id"] in primary_ids and float(row["sample_clock_offset_ppm"]) != 0.0
    ]
    fixed_scenario_ids = _evaluable_scenario_ids(
        scenario_metrics, primary_ids, "fixed_500ms_linear"
    )
    curvature_scenario_ids = _evaluable_scenario_ids(
        scenario_metrics, primary_ids, "lean_curvature_500ms"
    )
    fixed_endpoint_ids = _complete_endpoint_ids(endpoint_rows, primary_ids, "fixed_500ms_linear")
    curvature_endpoint_ids = _complete_endpoint_ids(
        endpoint_rows, primary_ids, "lean_curvature_500ms"
    )
    exact_diagnostic_clones = _diagnostic_points_are_exact_clones(endpoint_rows)
    checks = {
        "minimum_primary_evaluation_scenarios": int(diagnostic["evaluable_scenario_count"])
        >= int(gates["minimum_primary_evaluation_scenarios"]),
        "minimum_primary_scenarios_per_background": all(
            sum(row["background_session_id"] == background for row in diagnostic_scenarios)
            >= int(gates["minimum_primary_scenarios_per_background"])
            for background in background_coverage
        ),
        "all_three_backgrounds": int(diagnostic["background_count"]) == 3,
        "unchanged_fixed500_point_rmse": fixed_rmse
        <= float(gates["unchanged_fixed500_point_rmse_hz_s_max"]),
        "diagnostic_point_rmse_is_unchanged": diagnostic_rmse / fixed_rmse
        <= float(gates["calibrated_fixed500_point_rmse_ratio_to_unchanged_max"]),
        "diagnostic_point_rows_are_exact_clones": exact_diagnostic_clones,
        "finite_sample_95_interval_available": quantile.finite_sample_available,
        "descriptive_max_score_scenario_simultaneous_coverage": _required_float(
            diagnostic, "scenario_simultaneous_coverage"
        )
        >= float(gates["calibrated_scenario_simultaneous_coverage_min"]),
        "descriptive_max_score_each_background_coverage": len(background_coverage) == 3
        and all(
            value >= float(gates["calibrated_scenario_simultaneous_coverage_each_background_min"])
            for value in background_coverage.values()
        ),
        "descriptive_max_score_endpoint_coverage_lower": _required_float(
            diagnostic, "endpoint_coverage"
        )
        >= float(gates["calibrated_endpoint_coverage_min"]),
        "descriptive_max_score_endpoint_coverage_upper": _required_float(
            diagnostic, "endpoint_coverage"
        )
        <= float(gates["calibrated_endpoint_coverage_max"]),
        "descriptive_max_score_interval_half_width": _required_float(
            diagnostic, "median_interval_half_width_hz_s"
        )
        <= float(gates["calibrated_median_interval_half_width_hz_s_max"]),
        "true_sample_clock_primary_support": bool(resampling_rows)
        and all(
            bool(row["waveform_resampled"]) and int(row["accumulated_lattice_shift_samples"]) != 0
            for row in resampling_rows
        ),
    }
    curvature_ratio = curvature_rmse / fixed_rmse
    curvature_identity_checks = {
        "identical_evaluable_scenario_ids": fixed_scenario_ids == curvature_scenario_ids,
        "identical_complete_endpoint_ids": fixed_endpoint_ids == curvature_endpoint_ids,
    }
    curvature_pass = curvature_ratio <= float(
        gates["lean_curvature_point_rmse_ratio_to_unchanged_max_for_promotion"]
    ) and all(curvature_identity_checks.values())
    return {
        "fixed500_interval_status": "pass" if all(checks.values()) else "fail",
        "formal_95_interval_status": (
            "available"
            if quantile.finite_sample_available
            else "abstain_insufficient_calibration_groups"
        ),
        "fixed500_checks": checks,
        "curvature_status": "pass" if curvature_pass else "fail",
        "curvature_rmse_ratio": curvature_ratio,
        "curvature_identity_checks": curvature_identity_checks,
        "curvature_evaluable_scenario_ids": sorted(curvature_scenario_ids),
        "curvature_complete_endpoint_ids": [list(item) for item in sorted(curvature_endpoint_ids)],
        "descriptive_background_scenario_simultaneous_coverage": background_coverage,
        "fixed500_point_rmse_ratio_diagnostic_to_unchanged": diagnostic_rmse / fixed_rmse,
        "post_outcome_correction": True,
    }


def _evaluable_scenario_ids(
    scenario_metrics: list[dict[str, object]],
    primary_ids: set[str],
    estimator: str,
) -> set[str]:
    return {
        str(row["scenario_id"])
        for row in scenario_metrics
        if row["scenario_id"] in primary_ids
        and row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] == estimator
        and bool(row["evaluable"])
    }


def _complete_endpoint_ids(
    endpoint_rows: list[dict[str, object]],
    primary_ids: set[str],
    estimator: str,
) -> set[tuple[str, int, int]]:
    return {
        (
            str(row["scenario_id"]),
            int(row["endpoint_index"]),
            int(row["frame_start_sample"]),
        )
        for row in endpoint_rows
        if row["scenario_id"] in primary_ids
        and row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] == estimator
        and row["status"] == "complete"
    }


def _diagnostic_points_are_exact_clones(endpoint_rows: list[dict[str, object]]) -> bool:
    mutable_interval_fields = {"estimator", "interval_half_width_hz_s", "covered"}
    fixed = {
        (
            str(row["scenario_id"]),
            str(row["alignment"]),
            int(row["endpoint_index"]),
        ): row
        for row in endpoint_rows
        if row["estimator"] == "fixed_500ms_linear"
    }
    diagnostic = {
        (
            str(row["scenario_id"]),
            str(row["alignment"]),
            int(row["endpoint_index"]),
        ): row
        for row in endpoint_rows
        if row["estimator"] == "fixed_500ms_max_score_diagnostic"
    }
    if fixed.keys() != diagnostic.keys():
        return False
    return all(
        {key: value for key, value in fixed[identity].items() if key not in mutable_interval_fields}
        == {
            key: value
            for key, value in diagnostic[identity].items()
            if key not in mutable_interval_fields
        }
        for identity in fixed
    )


def _scenario_equal_rate_summary(
    scenario_metrics: list[dict[str, object]],
    *,
    predicate: Any,
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for estimator in (
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "lean_curvature_500ms",
    ):
        frozen = [
            row
            for row in scenario_metrics
            if row["alignment"] == "oracle_true_resampled_lattice"
            and row["estimator"] == estimator
            and predicate(row)
        ]
        evaluable = [row for row in frozen if bool(row["evaluable"])]
        output[estimator] = {
            "frozen_scenario_count": len(frozen),
            "evaluable_scenario_count": len(evaluable),
            "rmse_hz_s": (
                float(np.sqrt(np.mean([float(row["mse_hz2_s2"]) for row in evaluable])))
                if evaluable
                else None
            ),
        }
    return output


def _step_diagnostics(endpoint_rows: list[dict[str, object]]) -> dict[str, object]:
    methods = (
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "lean_curvature_500ms",
    )
    strata: dict[str, dict[str, dict[str, object]]] = {}
    for stratum in ("pre_step", "transition_excluded", "post_exclusion"):
        strata[stratum] = {}
        for estimator in methods:
            selected = [
                row
                for row in endpoint_rows
                if row["alignment"] == "oracle_true_resampled_lattice"
                and row["estimator"] == estimator
                and float(row["cfo_step_hz"]) != 0.0
                and row["step_stratum"] == stratum
            ]
            grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
            for row in selected:
                grouped[str(row["scenario_id"])].append(row)
            scenario_mse: list[float] = []
            for rows in grouped.values():
                if rows and all(row["status"] == "complete" for row in rows):
                    scenario_mse.append(
                        float(np.mean([float(row["receiver_error_hz_s"]) ** 2 for row in rows]))
                    )
            strata[stratum][estimator] = {
                "frozen_scenario_count": len(grouped),
                "evaluable_scenario_count": len(scenario_mse),
                "endpoint_row_count": len(selected),
                "rmse_hz_s": (float(np.sqrt(np.mean(scenario_mse))) if scenario_mse else None),
            }
    return {
        "step_time_s": 1.1,
        "transition_exclusion_s": 0.5,
        "frozen_endpoint_targets_s": [0.5, 1.0, 1.5],
        "target_strata": ["pre_step", "pre_step", "transition_excluded"],
        "post_exclusion_endpoint_available": any(
            strata["post_exclusion"][method]["endpoint_row_count"] for method in methods
        ),
        "scenario_equal_by_stratum": strata,
    }


def _plot_summary(aggregate: list[dict[str, object]], path: Path) -> None:
    labels = ("125 ms", "500 ms", "500 ms max-score\ndiagnostic", "500 ms quadratic")
    methods = (
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "fixed_500ms_max_score_diagnostic",
        "lean_curvature_500ms",
    )
    lookup = {str(row["estimator"]): row for row in aggregate}
    figure = Figure(figsize=(15.5, 8.2), constrained_layout=True)
    axes = figure.subplots(2, 2)
    x = np.arange(len(methods))
    colors = ("#6b7280", "#2563eb", "#059669", "#7c3aed")
    fields = (
        ("rmse_hz_s", "Rate RMSE (Hz/s)", None),
        ("endpoint_coverage", "Endpoint interval coverage", 0.95),
        ("scenario_simultaneous_coverage", "Scenario-simultaneous coverage", 0.80),
        ("median_interval_half_width_hz_s", "Median half-width (Hz/s)", 600.0),
    )
    for axis, (field, ylabel, reference) in zip(axes.flat, fields, strict=True):
        axis.bar(x, [_required_float(lookup[item], field) for item in methods], color=colors)
        if reference is not None:
            axis.axhline(reference, color="black", linestyle="--", linewidth=1)
        axis.set_xticks(x, labels, rotation=15, ha="right")
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25, axis="y")
    axes[0, 0].set_title("A · Known-truth endpoint accuracy", loc="left")
    axes[0, 1].set_title("B · Displayed interval coverage (descriptive)", loc="left")
    axes[1, 0].set_title("C · Scenario coverage (descriptive)", loc="left")
    axes[1, 1].set_title("D · Displayed half-width (descriptive)", loc="left")
    figure.suptitle(
        "No finite-sample 95% conformal interval is available from 12 groups; "
        "green is max-score diagnostic only",
        fontsize=12,
    )
    figure.savefig(path, dpi=170)


def _plot_intervals(
    endpoint_rows: list[dict[str, object]], primary_ids: set[str], path: Path
) -> None:
    selected = [
        row
        for row in endpoint_rows
        if row["scenario_id"] in primary_ids
        and row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] in {"fixed_500ms_linear", "fixed_500ms_max_score_diagnostic"}
        and row["status"] == "complete"
    ]
    figure = Figure(figsize=(15.5, 7.0), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True)
    for axis, method, color, title in (
        (axes[0], "fixed_500ms_linear", "#6b7280", "A · Legacy conditional covariance"),
        (
            axes[1],
            "fixed_500ms_max_score_diagnostic",
            "#059669",
            "B · Maximum calibration-score diagnostic (not conformal 95%)",
        ),
    ):
        rows = [row for row in selected if row["estimator"] == method]
        x = np.arange(len(rows))
        errors = np.asarray([float(row["receiver_error_hz_s"]) for row in rows])
        widths = np.asarray([float(row["interval_half_width_hz_s"]) for row in rows])
        axis.errorbar(x, errors, yerr=widths, fmt="o", markersize=3, color=color, ecolor=color)
        axis.axhline(0.0, color="black", linewidth=1)
        axis.set_ylabel("Rate error ± interval (Hz/s)")
        axis.set_title(title, loc="left")
        axis.grid(alpha=0.2)
    axes[1].set_xlabel("Frozen scenario endpoints (three per scenario)")
    figure.savefig(path, dpi=170)


def _plot_sample_clock(frame_summary: list[dict[str, object]], path: Path) -> None:
    figure = Figure(figsize=(14.5, 5.2), constrained_layout=True)
    axes = figure.subplots(1, 2)
    for ppm, color in ((-50.0, "#dc2626"), (0.0, "#111827"), (50.0, "#2563eb")):
        starts = resampled_frame_starts(
            frame_count=1_500,
            sample_rate_hz=2_500_000,
            sample_clock_offset_ppm=ppm,
        )
        nominal = resampled_frame_starts(
            frame_count=1_500,
            sample_rate_hz=2_500_000,
            sample_clock_offset_ppm=0.0,
        )
        axes[0].plot(starts / 2_500_000, starts - nominal, color=color, label=f"{ppm:+.0f} ppm")
    axes[0].set(xlabel="Receiver time (s)", ylabel="Frame-lattice shift (samples)")
    axes[0].set_title("A · True sample-clock lattice accumulation", loc="left")
    axes[0].legend()
    diagnostic = [
        row
        for row in frame_summary
        if row["split"] == "evaluation" and float(row["sample_clock_offset_ppm"]) != 0.0
    ]
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in diagnostic:
        grouped[str(row["alignment"])].append(float(row["occupied_support_rate"]))
    labels = ("truth lattice", "nominal lattice")
    keys = ("oracle_true_resampled_lattice", "nominal_fixed_lattice")
    axes[1].bar(
        np.arange(2),
        [float(np.mean(grouped[key])) if grouped[key] else np.nan for key in keys],
        color=("#059669", "#d97706"),
    )
    axes[1].set_xticks(np.arange(2), labels)
    axes[1].set_ylabel("Mean occupied-frame support")
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_title("B · Alignment sensitivity, nonzero-ppm evaluation", loc="left")
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.savefig(path, dpi=170)


def _plot_curvature(
    scenario_metrics: list[dict[str, object]], primary_ids: set[str], path: Path
) -> None:
    selected = [
        row
        for row in scenario_metrics
        if row["scenario_id"] in primary_ids
        and row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] in {"fixed_500ms_linear", "lean_curvature_500ms"}
        and bool(row["evaluable"])
    ]
    figure = Figure(figsize=(14.5, 5.2), constrained_layout=True)
    axes = figure.subplots(1, 2)
    for method, label, marker, color in (
        ("fixed_500ms_linear", "linear 500 ms", "o", "#2563eb"),
        ("lean_curvature_500ms", "quadratic 500 ms", "s", "#7c3aed"),
    ):
        rows = [row for row in selected if row["estimator"] == method]
        axes[0].scatter(
            [float(row["acceleration_hz_s2"]) for row in rows],
            [float(row["rmse_hz_s"]) for row in rows],
            label=label,
            marker=marker,
            color=color,
        )
        axes[1].scatter(
            [float(row["jerk_hz_s3"]) for row in rows],
            [float(row["rmse_hz_s"]) for row in rows],
            label=label,
            marker=marker,
            color=color,
        )
    axes[0].set(xlabel="Injected acceleration (Hz/s²)", ylabel="Scenario rate RMSE (Hz/s)")
    axes[1].set(xlabel="Injected jerk (Hz/s³)", ylabel="Scenario rate RMSE (Hz/s)")
    axes[0].set_title("A · Acceleration and trailing-window lag", loc="left")
    axes[1].set_title("B · Jerk and derivative model", loc="left")
    axes[0].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.savefig(path, dpi=170)


def _write_csv(path: Path, rows: list[dict[str, object]], *, compressed: bool = False) -> None:
    if not rows:
        raise ValueError(f"cannot write empty evidence ledger: {path.name}")
    fields = list(rows[0])
    if any(set(row) != set(fields) for row in rows):
        raise ValueError(f"inconsistent evidence fields: {path.name}")
    if compressed:
        with gzip.open(path, mode="wt", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    else:
        with path.open(mode="w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(stable_measurement_floats(value), allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _required_float(row: dict[str, object], field: str) -> float:
    value = row.get(field)
    if value is None:
        raise ValueError(f"required metric is absent: {field}")
    return float(value)


def _fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    output = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    output.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(output)


def _write_report(
    path: Path,
    *,
    evidence: dict[str, Any],
    aggregate: list[dict[str, object]],
    scenario_metrics: list[dict[str, object]],
    frame_summary: list[dict[str, object]],
    figures: dict[str, Path],
) -> None:
    by_method = {str(row["estimator"]): row for row in aggregate}
    labels = (
        ("fixed_125ms_linear", "Fixed 125 ms"),
        ("fixed_500ms_linear", "Unchanged fixed 500 ms"),
        (
            "fixed_500ms_max_score_diagnostic",
            "Fixed 500 ms + max-score diagnostic",
        ),
        ("lean_curvature_500ms", "Strict-past quadratic 500 ms"),
    )
    result_rows = []
    for method, label in labels:
        row = by_method[method]
        result_rows.append(
            (
                label,
                f"{row['evaluable_scenario_count']}/{row['scenario_count']}",
                _fmt(row["bias_hz_s"]),
                _fmt(row["rmse_hz_s"]),
                _fmt(100 * _required_float(row, "endpoint_coverage"), 1) + "%",
                _fmt(100 * _required_float(row, "scenario_simultaneous_coverage"), 1) + "%",
                _fmt(row["median_interval_half_width_hz_s"]),
            )
        )
    promotion = evidence["promotion"]
    failed = [name for name, passed in promotion["fixed500_checks"].items() if not passed]
    calibration = evidence["interval_calibration"]
    nominal = [
        row
        for row in frame_summary
        if row["alignment"] == "nominal_fixed_lattice" and row["split"] == "evaluation"
    ]
    oracle = [
        row
        for row in frame_summary
        if row["alignment"] == "oracle_true_resampled_lattice"
        and row["split"] == "evaluation"
        and float(row["sample_clock_offset_ppm"]) != 0.0
    ]
    nominal_support = float(np.mean([float(row["occupied_support_rate"]) for row in nominal]))
    oracle_support = float(np.mean([float(row["occupied_support_rate"]) for row in oracle]))
    relative = {name: figure.relative_to(path.parent) for name, figure in figures.items()}
    primary_rows = [
        row
        for row in scenario_metrics
        if row["alignment"] == "oracle_true_resampled_lattice"
        and row["estimator"] == "fixed_500ms_max_score_diagnostic"
        and row["split"] == "evaluation"
        and float(row["cfo_step_hz"]) == 0.0
        and float(row["snr_db"]) >= -12.0
        and float(row["frame_occupancy"]) >= 0.70
    ]
    background_rows = []
    for background in sorted({str(row["background_session_id"]) for row in primary_rows}):
        selected = [row for row in primary_rows if row["background_session_id"] == background]
        background_rows.append(
            (
                background,
                f"{sum(bool(row['evaluable']) for row in selected)}/{len(selected)}",
                _fmt(math.sqrt(float(np.mean([float(row["mse_hz2_s2"]) for row in selected])))),
                _fmt(
                    100
                    * float(
                        np.mean([bool(row["scenario_simultaneous_coverage"]) for row in selected])
                    ),
                    1,
                )
                + "%",
            )
        )
    stress_scopes = {
        "Primary evaluation: strong, smooth": _scenario_equal_rate_summary(
            scenario_metrics,
            predicate=lambda row: (
                row["split"] == "evaluation"
                and float(row["cfo_step_hz"]) == 0.0
                and float(row["snr_db"]) >= -12.0
                and float(row["frame_occupancy"]) >= 0.70
            ),
        ),
        "Strong, smooth; both splits": _scenario_equal_rate_summary(
            scenario_metrics,
            predicate=lambda row: (
                float(row["cfo_step_hz"]) == 0.0
                and float(row["snr_db"]) >= -12.0
                and float(row["frame_occupancy"]) >= 0.70
            ),
        ),
        "All smooth, including weak": _scenario_equal_rate_summary(
            scenario_metrics,
            predicate=lambda row: float(row["cfo_step_hz"]) == 0.0,
        ),
        "Mixed pre-step/transition diagnostic": _scenario_equal_rate_summary(
            scenario_metrics,
            predicate=lambda row: float(row["cfo_step_hz"]) != 0.0,
        ),
        "Weak -20 dB injection": _scenario_equal_rate_summary(
            scenario_metrics,
            predicate=lambda row: float(row["snr_db"]) == -20.0,
        ),
    }
    stress_rows: list[tuple[object, ...]] = []
    for scope, values in stress_scopes.items():
        row: list[object] = [scope]
        for method in (
            "fixed_125ms_linear",
            "fixed_500ms_linear",
            "lean_curvature_500ms",
        ):
            item = values[method]
            row.append(
                f"{item['evaluable_scenario_count']}/{item['frozen_scenario_count']}; "
                f"{_fmt(item['rmse_hz_s'])}"
            )
        stress_rows.append(tuple(row))
    step = evidence["step_diagnostics"]
    step_rows: list[tuple[object, ...]] = []
    for stratum, label in (
        ("pre_step", "Pre-step (two targets)"),
        ("transition_excluded", "Transition/excluded (one target)"),
        ("post_exclusion", "Post-exclusion recovery"),
    ):
        row = [label]
        for method in (
            "fixed_125ms_linear",
            "fixed_500ms_linear",
            "lean_curvature_500ms",
        ):
            item = step["scenario_equal_by_stratum"][stratum][method]
            row.append(
                f"{item['evaluable_scenario_count']}/{item['frozen_scenario_count']}; "
                f"{_fmt(item['rmse_hz_s'])}"
            )
        step_rows.append(tuple(row))
    path.write_text(
        f"""# Fixed-500-ms uncertainty calibration with true sample-clock resampling

Date: 2026-08-26 UTC

Status: **{str(promotion["fixed500_interval_status"]).upper()}** for the fixed-500 combined gate; **{str(promotion["formal_95_interval_status"]).upper()}** for a finite 95% interval; **{str(promotion["curvature_status"]).upper()}** for the corrected strict-past quadratic component gate.

## Bottom line

The fixed-500 result remains **FAIL** (`{", ".join(failed)}`). Its unchanged point estimate has primary RMSE {_fmt(by_method["fixed_500ms_linear"]["rmse_hz_s"])} Hz/s. A finite-sample 95% grouped interval is **not available**: {calibration["usable_scenario_count"]} calibration groups provide orders 1-{calibration["usable_scenario_count"]}, while the requested order is {calibration["required_order"]}. The formal result therefore abstains rather than capping the quantile.

For continuity with the original analysis, the maximum observed calibration score {_fmt(calibration["diagnostic_max_score_multiplier"], 3)} is retained only as a descriptive diagnostic. It gives {_fmt(100 * _required_float(by_method["fixed_500ms_max_score_diagnostic"], "scenario_simultaneous_coverage"), 1)}% observed evaluation scenario coverage and {_fmt(by_method["fixed_500ms_max_score_diagnostic"]["median_interval_half_width_hz_s"])} Hz/s median half-width. These numbers are not a conformal or distribution-free guarantee. Even under exchangeability, the maximum attainable rank fraction from 12 groups is {_fmt(100 * float(calibration["maximum_attainable_rank_coverage_under_exchangeability"]), 2)}%; this deterministic factor-balanced C/E split does not establish exchangeability.

The corrected quadratic uses only supported even-Qin frames strictly before each endpoint and evaluates its derivative at the excluded endpoint time. It has RMSE {_fmt(by_method["lean_curvature_500ms"]["rmse_hz_s"])} Hz/s, ratio {_fmt(promotion["curvature_rmse_ratio"], 3)} to the unchanged line, and passes the original 0.95 threshold. Both newly explicit identity gates pass: identical evaluable scenario IDs and identical complete endpoint IDs.

These are component-test results conditional on truth-quantized carrier acquisition and oracle knowledge of the **resampled** frame lattice. They do not establish satellite acquisition yield or separate LNB/transmitter/sample-clock/geometric nuisances.

## Authority and provenance

The [original preregistration](2026_08_26_fixed500_calibration_preregistration.md) was committed at `{PROTOCOL_COMMIT}` before the original IQ read. Independent audit then found three claim/implementation defects after all original outcomes were visible. The [post-outcome corrective amendment](../config/analysis/fixed500-calibration-corrective-analysis-amendment-v1.json), committed at `{CORRECTIVE_ANALYSIS_COMMIT}`, records that knowledge and froze these repairs before this rerun. This is a transparent correction, **not** an independent preregistered confirmation or a new holdout result.

The rerun inherits the exact three-span bindings from the [original polynomial-injection protocol](../config/analysis/polynomial-phase-injection-protocol-v1.json) and the deny-by-default [dataset policy](../config/analysis/doppler-experiment-dataset-policy-v1.json). No new, newer, PRE-FIX, holdout-foundation, 3/5-MS/s, dynamically discovered, or substituted capture was read. The separate hash-bound [corrective execution authority](../config/analysis/fixed500-calibration-corrective-execution-v1.json) binds the repaired implementation.

All three recording manifests, analysis manifests, compressed chunks, uncompressed chunks, and extracted spans were digest verified before injection. The run retained all 36 scenarios and finished in {_fmt(evidence["runtime_seconds"], 1)} seconds, below the frozen 20-minute bound. Exact implementation, authority, input, and artifact hashes are in [`metrics.json`]({relative["metrics"]}). The historical polynomial-injection kernel remains byte-identical to its sealed result.

## Primary evaluation

The primary mask contains 12 smooth strong evaluation scenarios (`SNR ≥ −12 dB`, occupancy ≥0.70), four per background. Each scenario contributes three non-overlapping endpoints; a scenario counts as simultaneously covered only if all three truth rates fall in their intervals.

{_table(("Estimator", "Scenarios", "Bias Hz/s", "RMSE Hz/s", "Displayed endpoint cov.", "Displayed scenario cov.", "Median half-width"), result_rows)}

![Primary accuracy and calibration]({relative["summary"]})

{_table(("Background", "Evaluable", "Fixed500 RMSE Hz/s", "Max-score diagnostic coverage"), background_rows)}

The green row and lower interval panel show the maximum-score diagnostic only. Fixed 125 ms, unchanged fixed 500 ms, and the quadratic retain descriptive legacy conditional covariance. No displayed interval in this report carries a validated 95% marginal or simultaneous coverage guarantee. Point bias and RMSE do not depend on this interval distinction.

![Legacy and grouped intervals]({relative["intervals"]})

## True sample-clock experiment

For nonzero ppm, the complex Qin waveform is interpolated on the scaled physical timebase and physical frame `k` moves to receiver sample `round(Fs × (1+ppm×10⁻⁶) × k/750)`. At ±50 ppm the final two-second frame is shifted by ±250 samples. This is not the earlier phase-coordinate-only warp.

With the true lattice supplied, mean occupied support for nonzero-ppm evaluation rows is {_fmt(100 * oracle_support, 1)}%. Replaying the same resampled waveform on the nominal fixed lattice yields {_fmt(100 * nominal_support, 1)}%. The nominal result is diagnostic only: it measures what a frame-aligner loses if it refuses accumulated delay; it does not enter rate promotion.

![Physical sample-clock lattice and support]({relative["clock"]})

## Curvature, nuisance factors, and controls

![Curvature comparison]({relative["curvature"]})

The strict-past quadratic excludes the current endpoint even-Qin measurement. Odd-Qin CFO and rolled-control responses remain in [`frame-evidence.csv.gz`]({relative["frames"]}) but cannot affect support, endpoints, model choice, multiplier, or gates. Alias changes are known labels and canonicalized. Every no-result endpoint and frame rejection remains in the ledgers.

{_table(("Scope", "Fixed 125 ms", "Fixed 500 ms", "Strict-past quadratic"), stress_rows)}

The nonzero-step aggregate above is explicitly a **mixed pre-step/transition diagnostic**, not recovery evidence. Applying the frozen 0.5 s exclusion to the 1.1 s step classifies targets 0.5 and 1.0 s as pre-step and 1.5 s as transition/excluded. There is no endpoint after 1.6 s.

{_table(("Step stratum", "Fixed 125 ms", "Fixed 500 ms", "Strict-past quadratic"), step_rows)}

Accordingly, this experiment supports no claim about post-step recovery. The transition-only quadratic error is expectedly large because a smooth polynomial extrapolator encounters a discontinuity. Any recovery study needs prospectively frozen endpoints after the exclusion window.

This experiment makes sample-clock timing observable only because injected truth supplies the physical clock map. In retrospective satellite data, sample clock, frame epoch, receiver/LNB drift, transmitter drift, and geometric Doppler still require a downstream nuisance model. Neither the descriptive max-score interval nor the quadratic component result is a satellite identity claim.

## Evidence artifacts

- [`frame-evidence.csv.gz`]({relative["frames"]}): every frame opportunity, parity response, rolled-control margin, and failure reason for oracle and nominal diagnostic alignments.
- [`frame-summary.csv`]({relative["frame_summary"]}): scenario/alignment support and false-support accounting.
- [`endpoint-estimates.csv`]({relative["endpoints"]}): all frozen endpoints, no-results, truth, errors, intervals, and odd-Qin held-out error.
- [`scenario-metrics.csv`]({relative["scenario_metrics"]}): scenario-equal point and coverage metrics.
- [`calibration-scores.csv`]({relative["scores"]}): whole-scenario maximum standardized calibration scores.
- [`injection-ledger.csv`]({relative["injections"]}): clock scale, waveform length, accumulated lattice shift, occupancy, and background provenance.

## Decision

The fixed 500-ms line remains a benchmark and remains **FAIL**. The 12-group experiment formally abstains on a finite 95% interval; the max-score display is diagnostic only. The corrected strict-past quadratic passes its component RMSE and identical-ID gates, but because the correction was specified after the original outcomes were known, it remains a promising challenger requiring independently frozen retrospective validation. No result here authorizes production promotion or opening the sealed satellite holdout.
""",
        encoding="utf-8",
    )


def main() -> None:
    args = _arguments()
    root = Path.cwd().resolve()
    config, execution_head, execution_authority = _verify_execution_authority(
        root,
        args.protocol,
        args.base_protocol,
        args.policy,
        args.execution_amendment,
        args.source_layout_amendment,
        args.corrective_analysis_amendment,
        args.corrective_execution_authority,
    )
    maximum_minutes = float(config["execution_bound"]["maximum_wall_clock_minutes"])
    started = time.monotonic()
    started_utc = datetime.now(UTC).isoformat()
    policy = load_doppler_dataset_policy(args.policy)
    inventory_path = verify_policy_inventory(policy, root)
    base_protocol = load_polynomial_injection_protocol(
        args.base_protocol, dataset_policy=policy, repository_root=root
    )
    frozen_scenarios = load_frozen_scenarios(args.protocol, protocol=base_protocol)
    estimator_config = config.get("estimators")
    if not isinstance(estimator_config, dict):
        raise ValueError("fixed500 estimator config is absent")
    step_transition_exclusion_s = float(estimator_config["step_transition_exclusion_s"])
    backgrounds: dict[str, Any] = {}
    dispositions: list[CaptureDisposition] = []
    for binding in base_protocol.backgrounds:
        verified = _read_verified_background(binding, policy=policy)
        backgrounds[binding.session_id] = verified
        dispositions.append(
            CaptureDisposition(
                capture=policy.capture(binding.session_id),
                status="evaluable",
                reason="exact manifest/chunk/span digest verified",
            )
        )
        print(f"verified {binding.session_id} {verified.span_sha256}", flush=True)
    finalize_capture_dispositions(
        policy, experiment_role="polynomial_injection", dispositions=dispositions
    )

    frame_rows: list[dict[str, object]] = []
    frame_summary: list[dict[str, object]] = []
    endpoint_rows: list[dict[str, object]] = []
    injection_ledger: list[dict[str, object]] = []
    for index, frozen in enumerate(frozen_scenarios, start=1):
        if time.monotonic() - started > maximum_minutes * 60.0:
            raise TimeoutError("fixed500 experiment exceeded its frozen wall-clock bound")
        scenario = frozen.scenario
        background = backgrounds[scenario.background_session_id]
        injected, occupied, true_starts, diagnostics = inject_resampled_exact_qin(
            background.samples, frozen, base_protocol
        )
        true_evidence = evaluate_resampled_exact_qin_frames(
            injected,
            occupied,
            scenario,
            base_protocol,
            absolute_span_start_sample=background.binding.sample_start,
            frame_starts=true_starts,
            reference_offset_scale=diagnostics.clock_scale,
        )
        alignment = "oracle_true_resampled_lattice"
        frame_rows.extend(_frame_row(item, frozen, alignment) for item in true_evidence)
        frame_summary.append(_summarize_frames(true_evidence, frozen, alignment))
        endpoint_rows.extend(
            _endpoint_rows(
                true_evidence,
                frozen,
                base_protocol,
                alignment,
                step_transition_exclusion_s=step_transition_exclusion_s,
            )
        )
        if scenario.sample_clock_offset_ppm != 0.0:
            nominal_starts = resampled_frame_starts(
                frame_count=base_protocol.frame_count,
                sample_rate_hz=background.binding.sample_rate_hz,
                sample_clock_offset_ppm=0.0,
            )
            nominal_evidence = evaluate_resampled_exact_qin_frames(
                injected,
                occupied,
                scenario,
                base_protocol,
                absolute_span_start_sample=background.binding.sample_start,
                frame_starts=nominal_starts,
            )
            nominal_alignment = "nominal_fixed_lattice"
            frame_rows.extend(
                _frame_row(item, frozen, nominal_alignment) for item in nominal_evidence
            )
            frame_summary.append(_summarize_frames(nominal_evidence, frozen, nominal_alignment))
            endpoint_rows.extend(
                _endpoint_rows(
                    nominal_evidence,
                    frozen,
                    base_protocol,
                    nominal_alignment,
                    step_transition_exclusion_s=step_transition_exclusion_s,
                )
            )
        injection_ledger.append(
            {
                "scenario_id": scenario.scenario_id,
                "row_id": frozen.row_id,
                "split": frozen.split,
                "background_session_id": scenario.background_session_id,
                "span_sha256": background.span_sha256,
                "seed": scenario.seed,
                "snr_db": scenario.snr_db,
                "frame_occupancy": scenario.frame_occupancy,
                "sample_clock_offset_ppm": scenario.sample_clock_offset_ppm,
                "clock_scale": diagnostics.clock_scale,
                "waveform_resampled": True,
                "resampled_template_sample_count": diagnostics.resampled_template_sample_count,
                "nominal_last_frame_start_sample": diagnostics.nominal_last_frame_start_sample,
                "resampled_last_frame_start_sample": diagnostics.resampled_last_frame_start_sample,
                "accumulated_lattice_shift_samples": diagnostics.accumulated_lattice_shift_samples,
                "occupied_frame_count": diagnostics.base.occupied_frame_count,
                "complete_occupied_frame_count": diagnostics.complete_occupied_frame_count,
                "amplitude_scale": diagnostics.base.amplitude_scale,
            }
        )
        print(
            f"scenario {index}/36 {scenario.scenario_id}: "
            f"true-support={sum(item.training_supported for item in true_evidence)} "
            f"lattice-shift={diagnostics.accumulated_lattice_shift_samples:+d}",
            flush=True,
        )

    endpoint_rows, calibration_scores, quantile = _calibrate_intervals(endpoint_rows)
    scenario_metrics = _scenario_metrics(endpoint_rows)
    primary_ids = {
        item.scenario.scenario_id
        for item in frozen_scenarios
        if item.split == "evaluation"
        and item.scenario.cfo_step_hz == 0.0
        and item.scenario.snr_db >= -12.0
        and item.scenario.frame_occupancy >= 0.70
    }
    aggregate = _primary_aggregate(scenario_metrics, primary_ids)
    gates = config["promotion_gates"]
    if not isinstance(gates, dict):
        raise ValueError("promotion gates are not an object")
    promotion = _promotion(
        aggregate,
        scenario_metrics,
        endpoint_rows,
        injection_ledger,
        primary_ids,
        gates,
        quantile,
    )
    step_diagnostics = _step_diagnostics(endpoint_rows)
    runtime = time.monotonic() - started
    if runtime > maximum_minutes * 60.0:
        raise TimeoutError("fixed500 experiment completed after its frozen wall-clock bound")

    args.output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "frames": args.output_root / "frame-evidence.csv.gz",
        "frame_summary": args.output_root / "frame-summary.csv",
        "endpoints": args.output_root / "endpoint-estimates.csv",
        "scenario_metrics": args.output_root / "scenario-metrics.csv",
        "scores": args.output_root / "calibration-scores.csv",
        "injections": args.output_root / "injection-ledger.csv",
        "summary": args.output_root / "01-primary-calibration.png",
        "intervals": args.output_root / "02-grouped-intervals.png",
        "clock": args.output_root / "03-true-sample-clock.png",
        "curvature": args.output_root / "04-curvature-comparison.png",
        "metrics": args.output_root / "metrics.json",
    }
    _write_csv(paths["frames"], frame_rows, compressed=True)
    _write_csv(paths["frame_summary"], frame_summary)
    _write_csv(paths["endpoints"], endpoint_rows)
    _write_csv(paths["scenario_metrics"], scenario_metrics)
    _write_csv(paths["scores"], calibration_scores)
    _write_csv(paths["injections"], injection_ledger)
    _plot_summary(aggregate, paths["summary"])
    _plot_intervals(endpoint_rows, primary_ids, paths["intervals"])
    _plot_sample_clock(frame_summary, paths["clock"])
    _plot_curvature(scenario_metrics, primary_ids, paths["curvature"])
    evidence: dict[str, Any] = {
        "schema": "org.leo.research.fixed500-calibration-evidence/v1",
        "repository_head_at_execution": execution_head,
        "execution_authority": execution_authority,
        "protocol_commit": PROTOCOL_COMMIT,
        "protocol_path": str(args.protocol),
        "protocol_sha256": _sha256_file(args.protocol),
        "dataset_policy_path": str(args.policy),
        "dataset_policy_sha256": _sha256_file(args.policy),
        "base_protocol_path": str(args.base_protocol),
        "base_protocol_sha256": _sha256_file(args.base_protocol),
        "inventory_path": str(inventory_path.relative_to(root)),
        "inventory_sha256": _sha256_file(inventory_path),
        "started_utc": started_utc,
        "completed_utc": datetime.now(UTC).isoformat(),
        "runtime_seconds": runtime,
        "scenario_count": len(frozen_scenarios),
        "primary_scenario_ids": sorted(primary_ids),
        "inputs": [
            {
                "session_id": item.binding.session_id,
                "sample_start": item.binding.sample_start,
                "sample_count": item.binding.sample_count,
                "span_sha256": item.span_sha256,
                "background_power": item.background_power,
                "compressed_bytes_read": item.compressed_bytes_read,
                "uncompressed_bytes_verified": item.uncompressed_bytes_verified,
            }
            for item in backgrounds.values()
        ],
        "implementation_sha256": _implementation_receipt(root),
        "interval_calibration": {
            "confidence": quantile.confidence,
            "usable_scenario_count": quantile.calibration_group_count,
            "required_order": quantile.required_order,
            "finite_sample_95_available": quantile.finite_sample_available,
            "formal_multiplier": quantile.multiplier,
            "formal_disposition": (
                "available"
                if quantile.finite_sample_available
                else "abstain_insufficient_calibration_groups"
            ),
            "diagnostic_order": quantile.diagnostic_order,
            "diagnostic_max_score_multiplier": quantile.diagnostic_max_multiplier,
            "maximum_attainable_rank_coverage_under_exchangeability": (
                quantile.maximum_attainable_rank_coverage
            ),
            "exchangeability_established": False,
            "diagnostic_interval_semantics": (
                "descriptive maximum calibration-score scaling only; no conformal or "
                "distribution-free coverage claim"
            ),
        },
        "step_diagnostics": step_diagnostics,
        "primary_aggregate": aggregate,
        "promotion": promotion,
        "artifact_sha256": {
            str(path.resolve().relative_to(root)): _sha256_file(path)
            for name, path in paths.items()
            if name != "metrics"
        },
    }
    paths["metrics"].write_bytes(_json_bytes(evidence))
    figures = {**paths}
    _write_report(
        args.report,
        evidence=evidence,
        aggregate=aggregate,
        scenario_metrics=scenario_metrics,
        frame_summary=frame_summary,
        figures=figures,
    )
    print(
        json.dumps(
            {
                "status": promotion,
                "runtime_seconds": runtime,
                "report": str(args.report),
                "metrics": str(paths["metrics"]),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
