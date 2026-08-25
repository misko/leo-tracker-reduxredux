"""Fail-closed loader for the frozen V3/V4 downstream-rate canary."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.analysis.research.doppler_dataset_policy import (
    authorize_capture,
    load_doppler_dataset_policy,
)

SCHEMA = "org.leo.research.v3-v4-downstream-rate-benchmark-protocol/v1"
SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
ROLE = "v3_v4_canary"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROOT_KEYS = {
    "schema",
    "status",
    "dataset_policy",
    "frozen_population",
    "source_bindings",
    "downstream_anchor_selection",
    "measurement",
    "forecast",
    "comparisons",
    "interpretation_gates",
    "claim_limits",
}


@dataclass(frozen=True, slots=True)
class V3V4RateAnchor:
    """One preregistered source-branch anchor."""

    row_index: int
    row_key: str
    row_input_digest: str
    source_branch_id: str
    stream: str
    receiver: int
    source_probe_sample_start: int


@dataclass(frozen=True, slots=True)
class V3V4RateProtocol:
    """Validated protocol plus its exact input documents."""

    path: Path
    digest: str
    document: dict[str, Any]
    frozen_population: dict[str, Any]
    scientific_receipt: dict[str, Any]
    anchors: tuple[V3V4RateAnchor, ...]


def load_v3_v4_rate_protocol(path: Path, *, repository_root: Path) -> V3V4RateProtocol:
    """Load the protocol and verify every repository input before IQ access."""

    root = repository_root.resolve()
    document = _object(path)
    _exact_keys(document, _ROOT_KEYS, "protocol")
    if document["schema"] != SCHEMA:
        raise ValueError("unsupported V3/V4 downstream-rate protocol schema")
    if document["status"] != "preregistered_before_downstream_iq_scoring":
        raise ValueError("V3/V4 downstream-rate protocol is not preregistered")

    policy_binding = _mapping(document["dataset_policy"], "dataset_policy")
    _exact_keys(
        policy_binding,
        {
            "path",
            "sha256",
            "role",
            "session_id",
            "recording_manifest_sha256",
            "forbidden_roles",
            "dynamic_capture_discovery_forbidden",
            "newer_capture_use_forbidden",
        },
        "dataset_policy",
    )
    if policy_binding["role"] != ROLE or policy_binding["session_id"] != SESSION_ID:
        raise ValueError("protocol is not bound to the exact V3/V4 canary role and capture")
    if policy_binding["dynamic_capture_discovery_forbidden"] is not True or (
        policy_binding["newer_capture_use_forbidden"] is not True
    ):
        raise ValueError("protocol must deny dynamic and newer capture discovery")
    if policy_binding["forbidden_roles"] != [
        "holdout_foundation",
        "multi_radio",
        "polynomial_injection",
    ]:
        raise ValueError("protocol forbidden-role list changed")
    policy_path = _repository_file(root, policy_binding["path"])
    _verify_digest(policy_path, policy_binding["sha256"], "dataset policy")
    policy = load_doppler_dataset_policy(policy_path)
    capture = policy.capture(SESSION_ID)
    authorize_capture(
        policy,
        experiment_role=ROLE,
        session_id=SESSION_ID,
        recording_manifest_sha256=str(policy_binding["recording_manifest_sha256"]),
        analysis_run_id=capture.analysis_run_id,
        analysis_manifest_sha256=capture.analysis_manifest_sha256,
    )

    population_binding = _mapping(document["frozen_population"], "frozen_population")
    _exact_keys(
        population_binding,
        {
            "path",
            "sha256",
            "row_count",
            "selection",
            "existing_scientific_receipt_path",
            "existing_scientific_receipt_sha256",
            "existing_canary_results_path",
            "existing_canary_results_sha256",
            "yield_source",
        },
        "frozen_population",
    )
    if population_binding["row_count"] != 537 or population_binding["selection"] != (
        "all rows; no row may be dropped or replaced"
    ):
        raise ValueError("frozen 537-row population binding changed")
    population_path = _repository_file(root, population_binding["path"])
    _verify_digest(population_path, population_binding["sha256"], "frozen population")
    population = _object(population_path)
    windows = population.get("windows")
    if (
        population.get("session_id") != SESSION_ID
        or not isinstance(windows, list)
        or len(windows) != 537
    ):
        raise ValueError("frozen population identity or row count changed")

    receipt_path = _repository_file(root, population_binding["existing_scientific_receipt_path"])
    _verify_digest(
        receipt_path,
        population_binding["existing_scientific_receipt_sha256"],
        "scientific receipt",
    )
    receipt = _object(receipt_path)
    if receipt.get("session_id") != SESSION_ID or len(receipt.get("rows", [])) != 537:
        raise ValueError("existing scientific receipt identity or row count changed")
    canary_path = _repository_file(root, population_binding["existing_canary_results_path"])
    _verify_digest(
        canary_path,
        population_binding["existing_canary_results_sha256"],
        "canary result",
    )
    if _object(canary_path).get("session_id") != SESSION_ID:
        raise ValueError("existing canary result session changed")

    source_bindings = _mapping(document["source_bindings"], "source_bindings")
    _exact_keys(
        source_bindings,
        {"v3_sha256", "v4_sha256", "frame_cfo_sha256", "v4_delegates_continuous_tracking_to_v3"},
        "source_bindings",
    )
    if source_bindings["v4_delegates_continuous_tracking_to_v3"] is not True:
        raise ValueError("V4 delegation disclosure cannot be removed")
    source_paths = {
        "v3_sha256": "src/leo/analysis/qam/pilot_pnt_kalman.py",
        "v4_sha256": "src/leo/analysis/qam/pilot_pnt_kalman_v4.py",
        "frame_cfo_sha256": "src/leo/analysis/qam/pilot.py",
    }
    for field, relative in source_paths.items():
        _verify_digest(_repository_file(root, relative), source_bindings[field], relative)

    anchor_binding = _mapping(document["downstream_anchor_selection"], "anchor selection")
    _exact_keys(
        anchor_binding,
        {
            "rule",
            "selected_before_downstream_iq_read",
            "anchor_count",
            "segment_duration_ms",
            "anchors",
        },
        "downstream_anchor_selection",
    )
    if (
        anchor_binding["selected_before_downstream_iq_read"] is not True
        or anchor_binding["anchor_count"] != 20
        or anchor_binding["segment_duration_ms"] != 1000
    ):
        raise ValueError("frozen downstream anchor count or duration changed")
    anchors = _anchors(anchor_binding["anchors"])
    expected_anchors = _expected_anchors(windows)
    if anchors != expected_anchors:
        raise ValueError("committed anchors are not the first frozen row per source branch")

    _validate_analysis_settings(document)
    return V3V4RateProtocol(
        path=path.resolve(),
        digest=_digest(path),
        document=document,
        frozen_population=population,
        scientific_receipt=receipt,
        anchors=anchors,
    )


def _validate_analysis_settings(document: dict[str, Any]) -> None:
    measurement = _mapping(document["measurement"], "measurement")
    required_measurement = {
        "sample_rate_hz": 2_500_000,
        "frame_rate_hz": 750,
        "frame_cfo_api": "estimate_edge_pilot_frame_cfo_split_validation",
        "residual_half_width_hz": 2_000,
        "minimum_even_exact_coherence": 0.02,
        "minimum_even_exact_minus_control_margin": 0.0,
        "even_search_boundary_rejected": True,
        "training_symbols": "even Qin only",
        "response_symbols": "future odd Qin only",
        "odd_may_select_mask_or_fit": False,
        "nco_rate_source": (
            "frozen standard_v1_local_rate_hz_s; zero only when source field is absent"
        ),
    }
    if any(measurement.get(key) != value for key, value in required_measurement.items()):
        raise ValueError("frozen parity-split measurement settings changed")
    if set(measurement) != {*required_measurement, "frame_lattice"}:
        raise ValueError("measurement fields are not closed")

    forecast = _mapping(document["forecast"], "forecast")
    if forecast.get("methods") != ["fixed_20ms", "fixed_500ms"]:
        raise ValueError("forecast methods changed")
    if forecast.get("forecast_horizon_ms") != 125 or forecast.get("target_offsets_ms") != list(
        range(625, 1_000, 25)
    ):
        raise ValueError("forecast targets changed")
    if forecast.get("fixed_20ms") != {"minimum_frames": 10, "minimum_span_ms": 16}:
        raise ValueError("fixed-20-ms support gate changed")
    if forecast.get("fixed_500ms") != {"minimum_frames": 300, "minimum_span_ms": 450}:
        raise ValueError("fixed-500-ms support gate changed")
    if forecast.get("history_is_trailing_and_past_only") is not True:
        raise ValueError("forecast history must remain trailing and causal")
    if forecast.get("fit") != "deterministic Huber degree-one IRLS":
        raise ValueError("forecast fit changed")

    comparisons = _mapping(document["comparisons"], "comparisons")
    if comparisons.get("failures_retained") is not True:
        raise ValueError("failure-ledger requirement cannot be disabled")
    gates = _mapping(document["interpretation_gates"], "interpretation_gates")
    if gates != {
        "minimum_common_anchors": 8,
        "minimum_common_fixed_500_predictions": 40,
        "v4_yield_must_not_be_lower_than_v3": True,
        "common_fixed_500_noninferiority_ratio": 1.05,
        "material_common_fixed_500_improvement_ratio": 0.95,
        "no_standard_promotion": True,
    }:
        raise ValueError("interpretation gates changed")
    limits = document["claim_limits"]
    if (
        not isinstance(limits, list)
        or len(limits) < 6
        or any(not isinstance(item, str) or not item for item in limits)
    ):
        raise ValueError("claim limits are missing")


def _anchors(value: object) -> tuple[V3V4RateAnchor, ...]:
    if not isinstance(value, list):
        raise ValueError("anchors must be a list")
    fields = {
        "row_index",
        "row_key",
        "row_input_digest",
        "source_branch_id",
        "stream",
        "receiver",
        "source_probe_sample_start",
    }
    output = []
    for row in value:
        item = _mapping(row, "anchor")
        _exact_keys(item, fields, "anchor")
        for field in ("row_key", "row_input_digest", "source_branch_id"):
            _sha(item[field], f"anchor.{field}")
        output.append(
            V3V4RateAnchor(
                row_index=_nonnegative_int(item["row_index"], "anchor.row_index"),
                row_key=str(item["row_key"]),
                row_input_digest=str(item["row_input_digest"]),
                source_branch_id=str(item["source_branch_id"]),
                stream=str(item["stream"]),
                receiver=_nonnegative_int(item["receiver"], "anchor.receiver"),
                source_probe_sample_start=_nonnegative_int(
                    item["source_probe_sample_start"], "anchor.source_probe_sample_start"
                ),
            )
        )
    if len(output) != 20 or len({item.source_branch_id for item in output}) != 20:
        raise ValueError("anchors must bind exactly 20 unique source branches")
    return tuple(output)


def _expected_anchors(windows: list[object]) -> tuple[V3V4RateAnchor, ...]:
    selected: dict[str, tuple[int, dict[str, Any], str, str]] = {}
    for index, raw in enumerate(windows):
        row = _mapping(raw, f"window {index}")
        branch = str(row["source_branch_id"])
        identity = {
            "scope": row["scope"],
            "source_trajectory_id": row["source_trajectory_id"],
            "source_probe_sample_start": int(row["source_probe_sample_start"]),
            "segment_index": int(row["segment_index"]),
            "candidate_rank": int(row["candidate_rank"]),
            "stream": row["stream"],
            "receiver": int(row["receiver"]),
        }
        row_key = _value_digest(identity)
        row_digest = _value_digest(row)
        candidate = (int(row["source_probe_sample_start"]), row_key)
        previous = selected.get(branch)
        if previous is None or candidate < (previous[0], previous[2]):
            selected[branch] = (candidate[0], row, row_key, row_digest)
    ordered = sorted(
        selected.items(),
        key=lambda item: (
            str(item[1][1]["stream"]),
            int(item[1][1]["receiver"]),
            int(item[1][1]["source_probe_sample_start"]),
            item[0],
        ),
    )
    result = []
    for branch, (sample_start, row, row_key, row_digest) in ordered:
        index = windows.index(row)
        result.append(
            V3V4RateAnchor(
                row_index=index,
                row_key=row_key,
                row_input_digest=row_digest,
                source_branch_id=branch,
                stream=str(row["stream"]),
                receiver=int(row["receiver"]),
                source_probe_sample_start=sample_start,
            )
        )
    return tuple(result)


def _repository_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("repository path must be a nonempty string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("repository path escapes the repository root")
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"bound repository file is missing: {value}")
    return path


def _verify_digest(path: Path, value: object, label: str) -> None:
    expected = _sha(value, label)
    if _digest(path) != expected:
        raise ValueError(f"{label} digest changed")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _value_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return _mapping(value, str(path))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are not closed")


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
