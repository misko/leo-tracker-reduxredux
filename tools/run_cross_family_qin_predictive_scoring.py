#!/usr/bin/env python3
"""Score the sealed paired Qin evidence under the frozen predictive design."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from leo.analysis.research.cross_family_qin_predictive_scoring import (
    CrossFamilyQinPredictiveScoringResult,
    load_cross_family_qin_scoring_config,
    score_cross_family_qin_evidence,
)

DEFAULT_CONFIG = Path("config/analysis/satellite-pnt-cross-family-predictive-scoring-v1.json")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="compute and validate the result without writing canonical outputs",
    )
    return parser.parse_args()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _git(repository_root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _report_bytes(result: CrossFamilyQinPredictiveScoringResult) -> bytes:
    diagnostics = {item.case_id: item for item in result.leave_one_pair_out_diagnostics}
    lines = [
        "# Satellite PNT paired cross-family predictive scoring",
        "",
        (
            "Status: opened-development leave-one-background-pair-out diagnostic; no "
            "threshold, posterior odds, satellite identity, correction, or positioning claim."
        ),
        "",
        (
            "The catalogue model is the frozen true causal-TLE curve at `tau=0` plus one "
            "training-only CFO offset. The primary radio model is a training-only line. "
            "Both are scored once on the same usable odd-Qin future rows."
        ),
        "",
        (
            "| Case | Truth | Future rows | Raw catalogue/radio RMS (Hz) | "
            "LOO radio−catalogue NLL | LOO preference | Correct |"
        ),
        "|---|---|---:|---:|---:|---|---|",
    ]
    for case in result.cases:
        primary = case.audit.comparisons[0]
        diagnostic = diagnostics[case.case_id]
        lines.append(
            f"| `{case.case_id}` | {case.truth_model_family} | "
            f"{diagnostic.observation_count} | "
            f"{primary.catalogue.future_residual_rms_hz:.6f}/"
            f"{primary.radio.future_residual_rms_hz:.6f} | "
            f"{diagnostic.radio_minus_catalogue_scaled_predictive_negative_log_likelihood:.6f} | "
            f"{diagnostic.preference} | {str(diagnostic.preference_matches_truth).lower()} |"
        )
    lines.extend(
        (
            "",
            (
                "The leave-one-pair-out family preference matches "
                f"{result.correct_truth_arm_count}/"
                f"{result.truth_arm_count} truth arms "
                f"({100.0 * result.truth_arm_equal_accuracy:.1f}%)."
            ),
            "",
            (
                "Only three independent background pairs are available, below the frozen "
                f"{result.formal_95_percent_rank_minimum_pairs}-pair finite-rank floor. "
                "The result diagnoses current discrimination and covariance scale; it does "
                "not calibrate a decision threshold or normalize full-catalogue multiplicity."
            ),
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _write_outputs(
    *,
    result_path: Path,
    report_path: Path,
    result: CrossFamilyQinPredictiveScoringResult,
    repository_root: Path,
) -> None:
    if result_path.exists() or report_path.exists():
        raise ValueError("canonical predictive-scoring outputs must be absent")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_bytes = _report_bytes(result)
    wrapper: dict[str, Any] = {
        "schema": "org.leo.research.satellite-pnt-cross-family-predictive-result/v1",
        "result": asdict(result),
        "execution": {
            "repository_head": _git(repository_root, "rev-parse", "HEAD"),
            "repository_tree": _git(repository_root, "rev-parse", "HEAD^{tree}"),
            "completed_utc": datetime.now(UTC).isoformat(),
            "input_evidence_sha256": result.evidence_sha256,
            "input_protocol_sha256": result.protocol_sha256,
            "report_sha256": _sha256(report_bytes),
            "new_iq_read": False,
            "new_rf_collection": False,
        },
    }
    result_bytes = _json_bytes(wrapper)
    temporary_result = result_path.with_name(result_path.name + ".staging")
    temporary_report = report_path.with_name(report_path.name + ".staging")
    if temporary_result.exists() or temporary_report.exists():
        raise ValueError("predictive-scoring staging outputs must be absent")
    temporary_result.write_bytes(result_bytes)
    temporary_report.write_bytes(report_bytes)
    temporary_result.replace(result_path)
    temporary_report.replace(report_path)


def main() -> None:
    args = _arguments()
    repository_root = Path.cwd().resolve()
    config = load_cross_family_qin_scoring_config(args.config.resolve())
    evidence_path = repository_root / config.evidence_path
    protocol_path = repository_root / config.protocol_path
    result = score_cross_family_qin_evidence(
        evidence_path.read_bytes(),
        protocol_path.read_bytes(),
        config,
    )
    if args.verify_only:
        print(
            _json_bytes(
                {
                    "result_digest": result.result_digest,
                    "independent_background_pair_count": (result.independent_background_pair_count),
                    "truth_arm_equal_accuracy": result.truth_arm_equal_accuracy,
                    "formal_95_percent_rank_pair_count_sufficient": (
                        result.formal_95_percent_rank_pair_count_sufficient
                    ),
                    "new_iq_read": False,
                }
            ).decode(),
            end="",
        )
        return
    _write_outputs(
        result_path=repository_root / config.result_path,
        report_path=repository_root / config.report_path,
        result=result,
        repository_root=repository_root,
    )


if __name__ == "__main__":
    main()
