#!/usr/bin/env python3
"""Build the sealed DS1/DS3 scientific-method registry.

The numbered-iteration matrix remains the execution ledger.  This registry is
the publication identity layer: one stable ``method_id`` per scientific arm,
including unnumbered controls, diagnostics, and explicitly superseded or
nonportable methods.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = (
    ROOT / "reports/2026_09_25_ds3_all_iterations_backfill/paired-completion-matrix-v4.json"
)
DEFAULT_OUTPUT = HERE / "method-registry.json"

CLASSIFICATIONS = {
    "position_method",
    "diagnostic",
    "preflight",
    "superseded",
    "nonportable",
    "missing_history",
}
TERMINAL_ACCOUNTING = {
    "missing_historical_artifact",
    "not_portable_legacy",
    "superseded_no_replay",
}


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def sidecar_matches(path: Path, actual: str) -> bool:
    if not path.is_file():
        return False
    words = path.read_text().strip().split(maxsplit=1)
    return bool(words) and words[0].removeprefix("sha256:") == actual.removeprefix("sha256:")


def verify_seal(path: Path) -> str:
    actual = digest(path)
    sidecars = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(sidecar_matches(item, actual) for item in sidecars):
        raise ValueError(f"unsealed artifact: {path}")
    return actual


def write(path: Path, value: dict[str, Any]) -> None:
    text = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def iteration(number: int, *, require_execution: bool = False, label: str | None = None) -> dict:
    result: dict[str, Any] = {"kind": "iteration", "iteration": number}
    if require_execution:
        result["require_ds3_execution"] = True
    if label:
        result["estimate_label"] = label
    return result


def pending(reason: str) -> dict:
    return {"kind": "pending", "reason": reason}


def accounting(status: str, reason: str) -> dict:
    if status not in TERMINAL_ACCOUNTING:
        raise ValueError(status)
    return {"kind": "accounting", "terminal_status": status, "reason": reason}


def artifact(
    path: str,
    status: str,
    *,
    selector: dict[str, str] | None = None,
) -> dict:
    source = ROOT / path
    result: dict[str, Any] = {
        "kind": "artifact",
        "artifact": {"path": path, "sha256": verify_seal(source)},
        "terminal_status": status,
    }
    if selector:
        result["selector"] = selector
    return result


def historical_evaluation(path: str, method: str) -> dict[str, Any]:
    """Bind a sealed DS1 multi-case evaluation to one exact method arm.

    This records historical coverage only.  It is deliberately separate from
    a DS1 qualification claim: the old evaluations are development suites
    with several views, rather than one sealed, ranking-eligible aggregate.
    """
    return {
        "kind": "sealed_method_rows",
        "artifact": {"path": path, "sha256": verify_seal(ROOT / path)},
        "selector": {"method": method},
    }


def entry(
    method_id: str,
    name: str,
    *,
    iteration_number: int | None,
    arm: str,
    classification: str,
    ds1_report_dir: str | None,
    ds3_binding: dict,
    ds1_evidence: dict[str, Any] | None = None,
    superseded_by: str | None = None,
    aliases: list[str] | None = None,
) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", method_id):
        raise ValueError(f"invalid method_id: {method_id}")
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"invalid classification: {classification}")
    row: dict[str, Any] = {
        "method_id": method_id,
        "name": name,
        "iteration": iteration_number,
        "arm": arm,
        "classification": classification,
        "required_for_publication": True,
        "ds1": {
            "report_dir": ds1_report_dir,
            "terminal_status": (
                "missing_historical_artifact"
                if classification == "missing_history"
                else "historical_terminal"
            ),
        },
        "ds3_binding": ds3_binding,
    }
    if superseded_by:
        row["superseded_by"] = superseded_by
    if aliases:
        row["registry_aliases"] = aliases
    if ds1_evidence is not None:
        row["ds1"]["historical_evidence"] = ds1_evidence
    return row


def build(ledger_path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    ledger_path = ledger_path.resolve()
    ledger_sha = verify_seal(ledger_path)
    ledger = json.loads(ledger_path.read_text())
    if {row.get("iteration") for row in ledger.get("rows", [])} != set(range(1, 32)):
        raise ValueError("iteration ledger must contain exactly iterations 1--31")

    batch_c = (
        "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/"
        "runner-family-output/exact-method-arms"
    )
    batch_d_geometry = "reports/2026_09_25_ds3_all_iterations_backfill/batch-d/output/geometry"
    one_hour_evaluation = (
        "reports/2026_09_24_ds1_train_full/post-seal-evaluation/"
        "one-hour-post-seal-evaluation.json"
    )
    iteration2_evaluation = (
        "reports/2026_09_24_ds1_iteration2/post-seal-evaluation/"
        "iteration2-post-seal-evaluation.json"
    )
    methods = [
        entry(
            "baseline-doppler",
            "Baseline Doppler",
            iteration_number=None,
            arm="baseline",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full",
            ds1_evidence=historical_evaluation(one_hour_evaluation, "baseline"),
            ds3_binding=artifact(f"{batch_c}/baseline.json", "terminal_control"),
        ),
        entry(
            "global-time",
            "Shared global receive time",
            iteration_number=None,
            arm="shared_global_tau",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full_timing",
            ds1_evidence=historical_evaluation(one_hour_evaluation, "global_time"),
            ds3_binding=artifact(f"{batch_c}/global_time.json", "terminal_control"),
        ),
        entry(
            "regularized-per-scan-time",
            "Regularized per-scan receive time",
            iteration_number=None,
            arm="regularized_per_scan_tau",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full_timing",
            ds1_evidence=historical_evaluation(one_hour_evaluation, "per_scan_time"),
            ds3_binding=artifact(f"{batch_c}/per_scan_time.json", "terminal_control"),
        ),
        entry(
            "i01-unknown-history",
            "Iteration 1 unknown historical method",
            iteration_number=1,
            arm="unknown",
            classification="missing_history",
            ds1_report_dir=None,
            ds3_binding=accounting(
                "missing_historical_artifact", "Historical method identity is unavailable."
            ),
        ),
        entry(
            "i02-shared-global-time",
            "Iteration 2 shared global receive time",
            iteration_number=2,
            arm="shared_global_tau",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_iteration2",
            ds1_evidence=historical_evaluation(iteration2_evaluation, "global_time"),
            ds3_binding=iteration(2, label="shared_global_tau"),
        ),
        entry(
            "i02-regularized-per-scan-time",
            "Iteration 2 regularized per-scan receive time",
            iteration_number=2,
            arm="regularized_per_scan_tau",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_iteration2",
            ds1_evidence=historical_evaluation(iteration2_evaluation, "per_scan_time"),
            ds3_binding=iteration(2, label="regularized_per_scan_tau"),
        ),
        entry(
            "independent-per-track-time",
            "Independent per-track receive time",
            iteration_number=None,
            arm="independent_per_track_tau",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_timing_ablations",
            ds1_evidence=historical_evaluation(
                one_hour_evaluation, "independent_per_track_time"
            ),
            ds3_binding=artifact(f"{batch_c}/independent_per_track_time.json", "terminal_control"),
        ),
        entry(
            "global-time-plus-per-norad-orbit-rate",
            "Shared global receive time plus causal per-NORAD rate",
            iteration_number=None,
            arm="global_tau_per_norad_orbit_rate",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full_orbit_soft",
            ds1_evidence=historical_evaluation(
                one_hour_evaluation, "global_time_plus_per_norad_orbit_rate"
            ),
            ds3_binding=artifact(
                f"{batch_c}/global_time_plus_per_norad_orbit_rate.json", "terminal_control"
            ),
        ),
        entry(
            "causal-per-norad-orbit-rate",
            "Causal per-NORAD orbit-rate correction",
            iteration_number=None,
            arm="causal_per_norad_orbit_rate",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_orbit_arm",
            ds1_evidence=historical_evaluation(
                one_hour_evaluation, "causal_per_norad_orbit_rate"
            ),
            ds3_binding=pending("No sealed standalone DS3/all56 causal-rate arm exists."),
        ),
        entry(
            "i03-global-time-plus-orbit-rate-screen",
            "Iteration 3 global time plus per-NORAD rate geographic screen",
            iteration_number=3,
            arm="global_time_plus_per_norad_orbit_rate",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending(
                "The ledger's I3 diagnostic is not the canonical position-producing I3 method."
            ),
            aliases=["rate_aware_joint_geographic_screen"],
        ),
        entry(
            "i04-seed-union-exact-selection",
            "Iteration 4 seed-union exact selection",
            iteration_number=4,
            arm="seed_union_exact_selection",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending(
                "The ledger's I4 diagnostic is not the canonical position-producing I4 method."
            ),
        ),
        entry(
            "i05-common-grid-timing-refinement",
            "Iteration 5 frozen-spatial common-grid timing refinement",
            iteration_number=5,
            arm="common_grid_timing_refinement",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending("Canonical position-producing I5 has no DS3 terminal artifact."),
        ),
        entry(
            "i06-matched-cap300-cap800",
            "Iteration 6 matched cap-300 proposal / cap-800 exact rank",
            iteration_number=6,
            arm="matched_cap300_cap800",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending("Canonical position-producing I6 has no DS3 terminal artifact."),
        ),
        entry(
            "i06b-legacy-session-scale",
            "Iteration 6B legacy joint session-scale L-BFGS-B",
            iteration_number=6,
            arm="legacy_session_scale_lbfgsb",
            classification="nonportable",
            ds1_report_dir="reports/2026_09_24_ds1_iteration6b_session_scale",
            ds3_binding=accounting(
                "not_portable_legacy",
                "Rejected legacy optimizer; superseded by block-coordinate I12.",
            ),
            superseded_by="i12-regularized-session-scale",
        ),
        entry(
            "i07-independent-gaussian-rerank",
            "Iteration 7 independent-Gaussian residual rerank",
            iteration_number=7,
            arm="independent_gaussian",
            classification="diagnostic",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending("Canonical I7 Gaussian rerank has no DS3 terminal diagnostic."),
        ),
        entry(
            "i07-ar1-student-t-rerank",
            "Iteration 7 AR(1)+Student-t residual rerank",
            iteration_number=7,
            arm="ar1_student_t",
            classification="diagnostic",
            ds1_report_dir="reports/2026_09_24_ds1_joint_rate_search",
            ds3_binding=pending("Canonical I7 robust rerank has no DS3 terminal diagnostic."),
        ),
        entry(
            "soft-association",
            "Soft identity mixture",
            iteration_number=None,
            arm="soft_association",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full",
            ds1_evidence=historical_evaluation(one_hour_evaluation, "soft_association"),
            ds3_binding=pending(
                "The available DS3 soft artifact is unsealed and cannot be consumed."
            ),
        ),
        entry(
            "soft-association-plus-global-time",
            "Soft identity mixture plus global receive time",
            iteration_number=None,
            arm="soft_association_plus_global_time",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_train_full",
            ds1_evidence=historical_evaluation(
                one_hour_evaluation, "soft_association_plus_global_time"
            ),
            ds3_binding=artifact(
                f"{batch_c}/soft_association_plus_global_time.json", "terminal_control"
            ),
        ),
    ]

    numbered = {
        8: ("equal-weight-joint-multiscan", "Equal-weight joint multiscan position", "joint"),
        9: ("symmetric-joint-refinement", "Symmetric shared-coordinate refinement", "joint"),
        10: ("three-level-shared-refinement", "Three-level symmetric shared refinement", "joint"),
        11: ("fine-symmetric-confirmation", "Fine symmetric confirmation", "joint"),
        13: ("basin-closure", "Basin closure", "basin"),
        14: ("cap800-basin", "Cap-800 basin search", "basin"),
        15: ("information-weighted", "Information-weighted search", "information_weighted"),
        16: ("dynamic-association", "Dynamic association", "dynamic_association"),
        17: ("reacquire-then-freeze", "Reacquire then freeze", "reacquire_then_freeze"),
        18: ("timing-refresh", "Timing refresh", "timing_refresh"),
        19: ("rate-bound-audit", "Corrected rate-bound audit", "rate_bound_audit"),
        20: ("session-predictive", "Session-predictive search", "session_predictive"),
        21: ("session-balanced-closure", "Session-balanced closure", "session_balanced"),
        27: ("phase-cache", "Exact phase-cache atlas", "phase_cache"),
        28: ("basin-search", "Phase-atlas basin search", "phase_basin"),
        29: ("resolution-safe-search", "Resolution-safe search", "resolution_safe"),
        30: ("fixed-topk-soft-preflight", "Fixed top-K soft-association preflight", "fixed_topk"),
        31: ("exact-state-soft-preflight", "Exact candidate-state soft preflight", "exact_state"),
    }
    report_dirs = {
        number: next(
            row["ds1"]["report_dir"] for row in ledger["rows"] if row["iteration"] == number
        )
        for number in numbered
    }
    for number, (slug, name, arm) in numbered.items():
        classification = "preflight" if number in {30, 31} else "position_method"
        methods.append(
            entry(
                f"i{number:02d}-{slug}",
                f"Iteration {number} {name}",
                iteration_number=number,
                arm=arm,
                classification=("superseded" if number == 15 else classification),
                ds1_report_dir=report_dirs[number],
                ds3_binding=iteration(number),
                superseded_by="i19-rate-bound-audit" if number == 15 else None,
            )
        )

    methods.extend(
        [
            entry(
                "i12-expanded-exact-rate-only",
                "Iteration 12 expanded exact rate-only",
            iteration_number=12,
            arm="expanded_exact_rate_only",
            classification="position_method",
            ds1_report_dir="reports/2026_09_24_ds1_iteration12_comparison",
            ds3_binding=artifact(
                "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/"
                "i12-method-arm-output/expanded-exact-rate-only.json",
                "unqualified_boundary",
            ),
            ),
            entry(
                "i12-regularized-session-scale",
                "Iteration 12 regularized common plus session scale",
                iteration_number=12,
                arm="regularized_common_plus_session_scale",
                classification="position_method",
                ds1_report_dir="reports/2026_09_24_ds1_iteration12_session_scale",
                ds3_binding=iteration(12),
            ),
            entry(
                "i12-shared-norad-rate",
                "Iteration 12 shared-NORAD rate control",
            iteration_number=12,
            arm="shared_norad_rate",
            classification="diagnostic",
            ds1_report_dir="reports/2026_09_24_ds1_iteration12_shared_norad",
            ds3_binding=artifact(
                "reports/2026_09_25_ds3_all_iterations_backfill/batch-c/"
                "i12-method-arm-output/shared-norad-rate.json",
                "no_position_diagnostic",
            ),
            ),
            entry(
                "i12-consistent-cap800",
                "Iteration 12 consistent cap-800 joint objective",
                iteration_number=12,
                arm="consistent_cap800",
                classification="position_method",
                ds1_report_dir="reports/2026_09_24_ds1_iteration12_consistent_objective",
                ds3_binding=artifact(
                    "reports/2026_09_24_ds3_all_captures/output/followups-v2/consistent-cap800.json",
                    "terminal_control",
                ),
            ),
            entry(
                "learned-pointing-cone-quantiles",
                "Learned pointing-cone quantiles",
                iteration_number=None,
                arm="learned_pointing_cone_quantiles",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_23_train_pointing_cone",
                ds3_binding=artifact(
                    f"{batch_d_geometry}/learned_pointing_cone_quantiles.json",
                    "no_position_diagnostic",
                ),
            ),
            entry(
                "fixed-hard-cone-orientation",
                "Fixed hard cone orientation",
                iteration_number=None,
                arm="fixed_hard_cone_orientation",
                classification="position_method",
                ds1_report_dir="reports/2026_09_23_train_fixed_cone",
                ds3_binding=artifact(
                    f"{batch_d_geometry}/fixed_hard_cone_orientation.json", "qualified"
                ),
            ),
            entry(
                "staged-full-fov-cone-sweep",
                "Staged full-FOV cone sweep",
                iteration_number=None,
                arm="staged_full_fov_cone_sweep",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_23_staged_cone_width_sweep",
                ds3_binding=artifact(
                    f"{batch_d_geometry}/staged_full_fov_cone_sweep.json",
                    "no_position_diagnostic",
                ),
            ),
            entry(
                "local-fitted-full-fov-cone-position",
                "Local fitted full-FOV cone position",
                iteration_number=None,
                arm="local_fitted_full_fov_cone_position",
                classification="position_method",
                ds1_report_dir="reports/2026_09_24_local_cone_grid",
                ds3_binding=artifact(
                    f"{batch_d_geometry}/local_fitted_full_fov_cone_position.json",
                    "qualified",
                ),
            ),
            entry(
                "i22-randomized-time-predictive",
                "Iteration 22 randomized-time predictive diagnostic",
                iteration_number=22,
                arm="randomized_time_predictive",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_25_ds1_iteration22_randomized_time_predictive",
                ds3_binding=iteration(22, require_execution=True),
            ),
            entry(
                "i23-widened-rate",
                "Iteration 23 widened-rate diagnostic",
                iteration_number=23,
                arm="widened_rate",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_25_ds1_iteration23_widened_rate",
                ds3_binding=iteration(23, require_execution=True),
            ),
            entry(
                "i24-crossfit-rate",
                "Iteration 24 cross-fit rate diagnostic",
                iteration_number=24,
                arm="crossfit_rate",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_25_ds1_iteration24_crossfit_rate",
                ds3_binding=iteration(24, require_execution=True),
            ),
            entry(
                "i25-source-admission",
                "Iteration 25 source-admission diagnostic",
                iteration_number=25,
                arm="source_admission",
                classification="diagnostic",
                ds1_report_dir="reports/2026_09_25_ds1_iteration25_source_admission",
                ds3_binding=iteration(25, require_execution=True),
            ),
            entry(
                "i26-quartic-rate-marginal",
                "Iteration 26 quartic rate-marginal surrogate",
                iteration_number=26,
                arm="quartic_rate_marginal",
                classification="nonportable",
                ds1_report_dir="reports/2026_09_25_ds1_iteration26_rate_marginal",
                ds3_binding=accounting(
                    "not_portable_legacy",
                    "Numerically prohibited surrogate; superseded by the exact I27 phase atlas.",
                ),
                superseded_by="i27-phase-cache",
            ),
        ]
    )

    ids = [row["method_id"] for row in methods]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate method_id")
    known = set(ids)
    for row in methods:
        successor = row.get("superseded_by")
        if successor and successor not in known:
            raise ValueError(f"unknown superseding method: {successor}")

    return {
        "schema": "ds1-ds3-method-registry/v1",
        "iteration_ledger": {
            "path": display_path(ledger_path),
            "sha256": ledger_sha,
            "identity_role": "execution provenance only; integer iteration is not method identity",
        },
        "source_registries": [
            "reports/2026_09_24_ds1_train_full/runner_registry.json",
            "reports/2026_09_24_ds1_ds2_final_comparison/REPORT.md",
            "reports/2026_09_24_ds1_iterative_subkm/REPORT.md",
        ],
        "counts": {
            "method_arms": len(methods),
            "required_for_publication": sum(
                bool(row["required_for_publication"]) for row in methods
            ),
        },
        "methods": sorted(methods, key=lambda row: row["method_id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write(args.output, build(args.ledger))


if __name__ == "__main__":
    main()
