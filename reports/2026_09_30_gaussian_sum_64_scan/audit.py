"""Independent read-only audit of the fixed 64-scan Gaussian-sum replay."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARMS = ("gaussian_sum", "greedy", "prior_only")
TERMINAL_NATIVE = {"complete", "gate_failed", "budget_reached", "error"}
TERMINAL_LAUNCH = {"complete", "timeout", "error"}
SPATIAL_PRIOR = {
    "name": "sacramento_uniform",
    "intended_center_latitude_deg": 38.5816,
    "intended_center_longitude_deg": -121.4944,
    "intended_radius_km": 250.0,
    "intended_density": "uniform_horizontal_disk",
    "prior_point_estimate": "center",
    "radial_rings": 4,
    "angular_sectors": 8,
    "component_count": 32,
    "component_weight": 0.03125,
    "physics_support_radius_km": 489.0,
}


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class AuditSummary:
    valid: bool
    expected_attempts: int
    launch_receipts: int
    native_receipts: int
    launch_status_counts: dict[str, int]
    native_status_counts: dict[str, int]
    issues: tuple[str, ...]


def _load(path: Path, issues: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(f"{path}: unreadable JSON ({type(error).__name__})")
        return None
    if not isinstance(value, dict):
        issues.append(f"{path}: top-level JSON must be an object")
        return None
    return value


def _independent_selection(
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    retained: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for row in sorted(
        evidence["tracks"],
        key=lambda item: (
            item["support_end_utc_ns"],
            item["support_start_utc_ns"],
            item["track_id"],
        ),
    ):
        ids = set(row["physical_observation_ids"])
        conflicts = sorted(ids & consumed)
        if len(row["measured_hz"]) < 3 or conflicts:
            excluded.append(
                {
                    "track_id": row["track_id"],
                    "reason": "same_receiver_source_overlap" if conflicts else "too_short",
                    "conflicting_ids": conflicts,
                }
            )
        else:
            retained.append(row)
            consumed.update(ids)
    return retained, excluded


def _check_bound_file(path_text: str, claimed: object, label: str, issues: list[str]) -> None:
    path = Path(path_text)
    if not path.is_file():
        issues.append(f"{label}: bound file missing: {path}")
    elif claimed != _digest(path):
        issues.append(f"{label}: digest mismatch: {path}")


def _check_native(path: Path, receipt: dict[str, Any], issues: list[str]) -> None:
    label = path.name
    if receipt.get("status") not in TERMINAL_NATIVE:
        issues.append(f"{label}: nonterminal native status {receipt.get('status')!r}")
    for key, claimed in receipt.get("source_sha256", {}).items():
        _check_bound_file(key, claimed, label, issues)
    for key, claimed in receipt.get("inputs", {}).items():
        _check_bound_file(key, claimed, label, issues)
    state = receipt.get("state_artifact", {})
    if state:
        _check_bound_file(str(state.get("path", "")), state.get("sha256"), label, issues)
    seal_path = path.with_suffix(".seal.json")
    seal = _load(seal_path, issues) if seal_path.is_file() else None
    if seal is None:
        issues.append(f"{label}: missing valid seal")
    elif seal.get("prediction_sha256") != _digest(path):
        issues.append(f"{label}: seal does not bind prediction")

    config = receipt.get("config", {})
    encoded = json.dumps(config, sort_keys=True).encode()
    expected_config = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if receipt.get("config_sha256") != expected_config:
        issues.append(f"{label}: config digest mismatch")
    arm = receipt.get("arm")
    filter_config = config.get("filter", {})
    if filter_config.get("greedy") != (arm == "greedy"):
        issues.append(f"{label}: greedy setting disagrees with arm")
    if filter_config.get("max_components") != 32 or filter_config.get("min_weight") != 1e-12:
        issues.append(f"{label}: fixed mixture bounds changed")
    if (
        config.get("prior") != "sacramento_uniform"
        or receipt.get("prior_name") != "sacramento_uniform"
    ):
        issues.append(f"{label}: wrong spatial prior in fixed panel")
    spatial = config.get("spatial_prior", {})
    for field, expected in SPATIAL_PRIOR.items():
        if spatial.get(field) != expected:
            issues.append(f"{label}: spatial prior field {field} changed")
    physics = config.get("physics", {})
    if (
        physics.get("prior_center_lat_deg") != SPATIAL_PRIOR["intended_center_latitude_deg"]
        or physics.get("prior_center_lon_deg") != SPATIAL_PRIOR["intended_center_longitude_deg"]
        or physics.get("support_radius_km") != SPATIAL_PRIOR["physics_support_radius_km"]
    ):
        issues.append(f"{label}: physics center/support disagrees with spatial prior")
    point = receipt.get("prior_point_estimate", {})
    if point != {
        "latitude_deg": SPATIAL_PRIOR["intended_center_latitude_deg"],
        "longitude_deg": SPATIAL_PRIOR["intended_center_longitude_deg"],
        "rule": "center_of_intended_uniform_disk",
    }:
        issues.append(f"{label}: prior point estimate is not the declared disk center")
    reset = receipt.get("initial_state_summary")
    if not isinstance(reset, dict):
        issues.append(f"{label}: missing initial-state nuisance reset summary")
    else:
        if reset.get("component_count") != len(receipt.get("initial_components", [])):
            issues.append(f"{label}: initial component count summary mismatch")
        if reset.get("component_count") != SPATIAL_PRIOR["component_count"]:
            issues.append(f"{label}: uniform approximation does not have 32 components")
        if reset.get("state_dimension") != receipt.get("state_dimension"):
            issues.append(f"{label}: initial state dimension summary mismatch")
        if reset.get("weight_sum") != 1.0 or reset.get("histories_empty") is not True:
            issues.append(f"{label}: initial mixture was not a clean normalized reset")
        for field in (
            "max_abs_tau_s",
            "max_abs_rx_drift_hz_s",
            "max_abs_satellite_epoch_s",
        ):
            if reset.get(field) != 0.0:
                issues.append(f"{label}: nonzero initial nuisance in {field}")

    evidence_paths = [Path(key) for key in receipt.get("inputs", {}) if key.endswith(".json")]
    evidence_path = next(
        (item for item in evidence_paths if item.name == f"{receipt.get('unit_id')}.json"), None
    )
    if evidence_path is None or not evidence_path.is_file():
        issues.append(f"{label}: evidence input cannot be identified")
        return
    evidence = _load(evidence_path, issues)
    if evidence is None:
        return
    retained, exclusions = _independent_selection(evidence)
    selection = receipt.get("selection", {})
    if selection.get("all_tracks") != len(evidence["tracks"]):
        issues.append(f"{label}: all-track count differs from evidence")
    if (
        selection.get("retained_tracks") != len(retained)
        or selection.get("exclusions") != exclusions
    ):
        issues.append(f"{label}: overlap/short-track selection mismatch")

    checkpoints = receipt.get("checkpoints", [])
    if arm == "prior_only":
        if checkpoints or receipt.get("components") != receipt.get("initial_components"):
            issues.append(f"{label}: prior-only arm did not remain at its reset prior")
        return
    previous_support = float("-inf")
    consumed_count = 0
    retained_by_id = {row["track_id"]: row for row in retained}
    for index, checkpoint in enumerate(checkpoints):
        if checkpoint.get("factor") != index:
            issues.append(f"{label}: checkpoint factor sequence is not zero-based chronological")
        track = retained_by_id.get(checkpoint.get("track_id"))
        if track is None or track is not retained[index]:
            issues.append(f"{label}: checkpoint {index} does not match retained track order")
            continue
        support = float(checkpoint.get("elapsed_support_s", float("nan")))
        if support < previous_support:
            issues.append(f"{label}: checkpoint support time decreased")
        previous_support = support
        consumed_count += min(8, len(track["physical_observation_ids"]))
        if checkpoint.get("consumed_samples") != consumed_count:
            issues.append(f"{label}: checkpoint consumed-sample count mismatch")
        for component in checkpoint.get("components", []):
            if len(component.get("identity_history", [])) != index + 1:
                issues.append(f"{label}: component lineage length mismatch at factor {index}")
                break


def audit_panel(
    report_root: Path,
    expected_units: tuple[str, ...] | list[str],
    *,
    require_all_attempts: bool = True,
) -> AuditSummary:
    """Audit expected unit/arm attempts without reading evaluator coordinates."""
    root = Path(report_root)
    units = tuple(expected_units)
    expected = {(unit, arm) for unit in units for arm in ARMS}
    issues: list[str] = []
    launches: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    natives: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for path in sorted(root.rglob("*.launch.json")):
        value = _load(path, issues)
        if value is None:
            continue
        key = (str(value.get("unit_id")), str(value.get("arm")))
        if key in launches:
            issues.append(f"duplicate launch receipt for {key}")
        launches[key] = (path, value)
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith((".launch.json", ".seal.json", ".progress.json")):
            continue
        value = _load(path, issues)
        if value is None or value.get("schema") != "gaussian-sum-single-scan-prediction/v1":
            continue
        key = (str(value.get("unit_id")), str(value.get("arm")))
        if key in natives:
            issues.append(f"duplicate native receipt for {key}")
        natives[key] = (path, value)

    if require_all_attempts:
        for key in sorted(expected - launches.keys()):
            issues.append(f"missing launch receipt for {key}")
    for key in sorted(set(launches) - expected):
        issues.append(f"unexpected launch receipt for {key}")
    for key, (path, launch) in launches.items():
        if launch.get("status") not in TERMINAL_LAUNCH:
            issues.append(f"{path.name}: nonterminal launch status {launch.get('status')!r}")
        prediction_path = Path(str(launch.get("prediction_path", "")))
        native = natives.get(key)
        if launch.get("status") == "complete" and native is None:
            issues.append(f"{path.name}: completed launch lacks native receipt")
        if native is not None and native[0].resolve() != prediction_path.resolve():
            issues.append(f"{path.name}: prediction path does not bind native receipt")
        if native is not None and launch.get("native_status") != native[1].get("status"):
            issues.append(f"{path.name}: launch/native terminal status mismatch")

    code_identity: dict[str, str] | None = None
    physics_identity: dict[str, Any] | None = None
    initial_identity: list[dict[str, Any]] | None = None
    for key, (path, receipt) in natives.items():
        if key not in expected:
            issues.append(f"unexpected native receipt for {key}")
        _check_native(path, receipt, issues)
        sources = receipt.get("source_sha256")
        physics = receipt.get("config", {}).get("physics")
        initial = receipt.get("initial_components")
        if code_identity is None:
            code_identity, physics_identity, initial_identity = sources, physics, initial
        else:
            if sources != code_identity:
                issues.append(f"{path.name}: code/protocol identity differs across panel")
            if physics != physics_identity:
                issues.append(f"{path.name}: physics config differs across panel")
            if initial != initial_identity:
                issues.append(f"{path.name}: initial prior differs; scan reset not demonstrated")

    launch_counts = Counter(value.get("status", "missing") for _, value in launches.values())
    native_counts = Counter(value.get("status", "missing") for _, value in natives.values())
    return AuditSummary(
        valid=not issues,
        expected_attempts=len(expected),
        launch_receipts=len(launches),
        native_receipts=len(natives),
        launch_status_counts=dict(sorted(launch_counts.items())),
        native_status_counts=dict(sorted(native_counts.items())),
        issues=tuple(issues),
    )
