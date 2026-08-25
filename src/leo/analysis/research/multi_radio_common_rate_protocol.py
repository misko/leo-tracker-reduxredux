"""Fail-closed preregistration for the multi-radio common-rate experiment."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy

SCHEMA = "org.leo.research.multi-radio-common-rate-protocol/v1"

_ROOT_KEYS = {
    "schema",
    "authority",
    "selection",
    "frequency_coordinate",
    "measurement",
    "models",
    "evaluation",
    "failure_policy",
    "captures",
}
_CAPTURE_KEYS = {
    "capture_session_id",
    "analysis_run_id",
    "recording_manifest_logical_uri",
    "recording_manifest_sha256",
    "analysis_manifest_logical_uri",
    "analysis_manifest_sha256",
    "screen_category",
    "screen_band_relationship",
    "screen_full_common_overlap_s",
    "reconstructed_full_overlap_start_utc_ns",
    "reconstructed_full_overlap_stop_utc_ns",
    "episode_start_utc_ns",
    "episode_stop_utc_ns",
    "episode_duration_s",
    "paths",
    "preregistered_disposition",
}
_PATH_KEYS = {
    "path_id",
    "stream_id",
    "physical_radio_id",
    "radio_serial",
    "receiver_id",
    "edge",
    "scope_id",
    "first_sample_estimate_utc_ns",
    "nominal_if_center_hz",
    "nominal_sky_frequency_hz",
    "source_branch_id",
    "trajectory_id",
    "trajectory_alias_index",
    "trajectory_reference_time_s",
    "trajectory_absolute_coefficients_hz",
    "trajectory_start_s",
    "trajectory_stop_s",
    "analysis_start_s",
    "analysis_stop_s",
    "products",
    "frozen_source",
}
_SOURCE_KEYS = {
    "source_observation_id",
    "sample_start",
    "detection_time_s",
    "candidate_rank",
    "local_epoch_sample",
    "source_alias_index",
    "tracking_cfo_hz",
    "exact_score",
    "control_score",
    "margin",
}
_PRODUCT_KEYS = {
    "path_report",
    "pilot_scan",
    "dealiased_trajectory_bank",
    "final_trajectory_bank",
}
_PRODUCT_BINDING_KEYS = {"logical_uri", "sha256"}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCOPE_RE = _SHA256_RE
_SESSION_RE = re.compile(r"cap-[0-9]{8}T[0-9]{6}-[0-9a-f]{12}\Z")
_RUN_RE = re.compile(r"capture-[0-9a-f]{32}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_STREAM_RE = re.compile(r"stream-[01]\Z")
_RADIO_RE = re.compile(r"radio_pluto_[0-9a-f]{4}\Z")
_SERIAL_RE = re.compile(r"[0-9a-f]{34}\Z")


@dataclass(frozen=True, slots=True)
class MultiRadioPathBinding:
    """One immutable receiver path and its response-blind raw source seed."""

    path_id: str
    stream_id: str
    physical_radio_id: str
    receiver_id: int
    edge: str
    scope_id: str
    branch_id: str
    trajectory_id: str
    trajectory_alias_index: int
    analysis_start_s: float
    analysis_stop_s: float
    first_sample_estimate_utc_ns: int
    nominal_sky_frequency_hz: int
    source_observation_id: str
    source_sample_start: int
    source_local_epoch_sample: int
    product_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MultiRadioCaptureBinding:
    """One frozen simultaneous episode spanning at least two physical radios."""

    session_id: str
    analysis_run_id: str
    recording_manifest_sha256: str
    analysis_manifest_sha256: str
    episode_start_utc_ns: int
    episode_stop_utc_ns: int
    paths: tuple[MultiRadioPathBinding, ...]


@dataclass(frozen=True, slots=True)
class MultiRadioCommonRateProtocol:
    """Validated closed protocol consumed by the bounded experiment runner."""

    path: Path
    sha256: str
    captures: tuple[MultiRadioCaptureBinding, ...]
    document: Mapping[str, Any]


def load_multi_radio_common_rate_protocol(
    path: Path,
    *,
    repository_root: Path | None = None,
) -> MultiRadioCommonRateProtocol:
    """Load the v1 protocol and reject any policy, identity, or geometry drift."""

    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    root = _mapping(document, "protocol")
    _exact_keys(root, _ROOT_KEYS, "protocol")
    if root["schema"] != SCHEMA:
        raise ValueError("unsupported multi-radio protocol schema")
    authority = _mapping(root["authority"], "authority")
    expected_authority_keys = {
        "dataset_policy_path",
        "dataset_policy_sha256",
        "required_policy_role",
        "required_capture_ids",
        "dynamic_discovery_forbidden",
        "substitution_forbidden",
        "holdout_foundation_forbidden",
        "raw_iq_scored_before_protocol_freeze",
        "protocol_basis_repository_commit",
        "retrospective_inventory_path",
        "retrospective_inventory_sha256",
    }
    _exact_keys(authority, expected_authority_keys, "authority")
    for field in (
        "dynamic_discovery_forbidden",
        "substitution_forbidden",
        "holdout_foundation_forbidden",
    ):
        if authority[field] is not True:
            raise ValueError(f"authority.{field} must be true")
    if authority["raw_iq_scored_before_protocol_freeze"] is not False:
        raise ValueError("protocol freeze must precede new raw-IQ scoring")
    if authority["required_policy_role"] != "multi_radio":
        raise ValueError("multi-radio protocol requires the multi_radio policy role")
    _matching_string(
        authority["protocol_basis_repository_commit"],
        _COMMIT_RE,
        "protocol basis commit",
    )
    repo = repository_root or path.resolve().parents[2]
    policy_path = _repository_path(repo, authority["dataset_policy_path"], "dataset policy")
    inventory_path = _repository_path(
        repo,
        authority["retrospective_inventory_path"],
        "retrospective inventory",
    )
    _verify_digest(policy_path, authority["dataset_policy_sha256"], "dataset policy")
    _verify_digest(
        inventory_path,
        authority["retrospective_inventory_sha256"],
        "retrospective inventory",
    )
    policy = load_doppler_dataset_policy(policy_path)
    role = policy.role("multi_radio")
    required_ids = tuple(
        _matching_string(value, _SESSION_RE, "required capture ID")
        for value in _sequence(authority["required_capture_ids"], "required capture IDs")
    )
    if required_ids != role.capture_ids:
        raise ValueError("protocol capture order disagrees with dataset policy")
    if set(required_ids) & set(policy.role("holdout_foundation").capture_ids):
        raise ValueError("holdout-foundation capture leaked into multi-radio protocol")

    _validate_frozen_settings(root)
    capture_values = _sequence(root["captures"], "captures")
    if len(capture_values) != len(required_ids):
        raise ValueError("protocol must retain all four authorized captures")
    captures = tuple(
        _capture_binding(value, required_id, policy, root)
        for value, required_id in zip(capture_values, required_ids, strict=True)
    )
    return MultiRadioCommonRateProtocol(
        path=path,
        sha256=_sha256(path),
        captures=captures,
        document=root,
    )


def _validate_frozen_settings(root: Mapping[str, Any]) -> None:
    selection = _mapping(root["selection"], "selection")
    if float(selection.get("episode_duration_s", -1.0)) != 1.5:
        raise ValueError("protocol episode duration must remain 1.5 s")
    coordinate = _mapping(root["frequency_coordinate"], "frequency coordinate")
    if coordinate.get("shared_rate_reference_sky_frequency_hz") != 11_000_000_000:
        raise ValueError("shared rate reference must remain 11 GHz")
    if coordinate.get("nominal_lnb_lo_hz") != 9_750_000_000:
        raise ValueError("nominal LNB LO must remain 9.75 GHz")
    measurement = _mapping(root["measurement"], "measurement")
    expected_measurement = {
        "sample_rate_hz": 2_500_000,
        "frame_rate_hz": 750.0,
        "profile_residual_half_width_hz": 2_000.0,
        "profile_step_hz": 20.0,
        "minimum_even_exact_coherence": 0.02,
        "minimum_even_coherence_margin": 0.0,
        "digest_verification_required": True,
    }
    for field, expected in expected_measurement.items():
        if measurement.get(field) != expected:
            raise ValueError(f"measurement.{field} drifted from the preregistration")
    if measurement.get("fit_symbols") != "even Qin only":
        raise ValueError("fit symbols must remain even Qin only")
    response = measurement.get("response_symbols")
    if not isinstance(response, str) or not response.startswith("odd Qin only"):
        raise ValueError("response symbols must remain odd Qin only")
    models = _mapping(root["models"], "models")
    primary = _mapping(models.get("primary"), "primary model")
    if primary.get("rate_count_per_episode") != 1:
        raise ValueError("primary model must fit exactly one shared episode rate")
    if primary.get("per_radio_or_path_drift_allowed") is not False:
        raise ValueError("primary model cannot admit path-specific drift")
    evaluation = _mapping(root["evaluation"], "evaluation")
    if evaluation.get("chronological_train_fraction") != 0.6:
        raise ValueError("chronological split drifted from 60/40")
    failure = _mapping(root["failure_policy"], "failure policy")
    for field in (
        "retain_all_four_captures",
        "no_replacement",
        "no_threshold_tuning_after_response",
        "fail_closed_on_digest_or_identity_mismatch",
    ):
        if failure.get(field) is not True:
            raise ValueError(f"failure_policy.{field} must be true")


def _capture_binding(
    value: object,
    required_id: str,
    policy: Any,
    root: Mapping[str, Any],
) -> MultiRadioCaptureBinding:
    capture = _mapping(value, f"capture {required_id}")
    _exact_keys(capture, _CAPTURE_KEYS, f"capture {required_id}")
    session_id = _matching_string(capture["capture_session_id"], _SESSION_RE, "session ID")
    if session_id != required_id:
        raise ValueError("protocol capture order or identity drifted")
    policy_capture = policy.capture(session_id)
    run_id = _matching_string(capture["analysis_run_id"], _RUN_RE, "analysis run ID")
    recording_digest = _matching_string(
        capture["recording_manifest_sha256"], _SHA256_RE, "recording digest"
    )
    analysis_digest = _matching_string(
        capture["analysis_manifest_sha256"], _SHA256_RE, "analysis digest"
    )
    if (
        recording_digest,
        run_id,
        analysis_digest,
    ) != (
        policy_capture.recording_manifest_sha256,
        policy_capture.analysis_run_id,
        policy_capture.analysis_manifest_sha256,
    ):
        raise ValueError(f"capture binding disagrees with dataset policy: {session_id}")
    if capture["preregistered_disposition"] != "pending_digest_verification_and_even_qin_support":
        raise ValueError("capture outcome was inserted before protocol execution")
    full_start = _positive_int(
        capture["reconstructed_full_overlap_start_utc_ns"], "full overlap start"
    )
    full_stop = _positive_int(
        capture["reconstructed_full_overlap_stop_utc_ns"], "full overlap stop"
    )
    episode_start = _positive_int(capture["episode_start_utc_ns"], "episode start")
    episode_stop = _positive_int(capture["episode_stop_utc_ns"], "episode stop")
    duration_s = _finite_float(capture["episode_duration_s"], "episode duration")
    if not full_start <= episode_start < episode_stop <= full_stop:
        raise ValueError("episode does not lie inside the frozen full overlap")
    if episode_stop - episode_start != 1_500_000_000 or duration_s != 1.5:
        raise ValueError("episode must be exactly 1.500000000 s")
    paths = tuple(
        _path_binding(item, session_id, run_id, episode_start, episode_stop, root)
        for item in _sequence(capture["paths"], f"{session_id} paths")
    )
    if len(paths) < 3 or len({item.path_id for item in paths}) != len(paths):
        raise ValueError("capture paths must be unique and retain multi-path support")
    if len({item.physical_radio_id for item in paths}) < 2:
        raise ValueError("episode does not span two physical radios")
    return MultiRadioCaptureBinding(
        session_id=session_id,
        analysis_run_id=run_id,
        recording_manifest_sha256=recording_digest,
        analysis_manifest_sha256=analysis_digest,
        episode_start_utc_ns=episode_start,
        episode_stop_utc_ns=episode_stop,
        paths=paths,
    )


def _path_binding(
    value: object,
    session_id: str,
    run_id: str,
    episode_start_utc_ns: int,
    episode_stop_utc_ns: int,
    root: Mapping[str, Any],
) -> MultiRadioPathBinding:
    path = _mapping(value, f"{session_id} path")
    _exact_keys(path, _PATH_KEYS, f"{session_id} path")
    path_id = _nonempty_string(path["path_id"], "path ID")
    stream_id = _matching_string(path["stream_id"], _STREAM_RE, "stream ID")
    radio_id = _matching_string(path["physical_radio_id"], _RADIO_RE, "physical radio ID")
    receiver_id = _nonnegative_int(path["receiver_id"], "receiver ID")
    if receiver_id not in (0, 1) or path_id != f"{stream_id}/{radio_id}/RX{receiver_id}":
        raise ValueError("path identity fields disagree")
    _matching_string(path["radio_serial"], _SERIAL_RE, "radio serial")
    edge = _nonempty_string(path["edge"], "edge")
    if edge not in {"lower", "upper"}:
        raise ValueError("edge must be lower or upper")
    scope_id = _matching_string(path["scope_id"], _SCOPE_RE, "scope ID")
    branch_id = _matching_string(path["source_branch_id"], _SHA256_RE, "branch ID")
    trajectory_id = _matching_string(path["trajectory_id"], _SHA256_RE, "trajectory ID")
    alias = _integer(path["trajectory_alias_index"], "trajectory alias")
    if not -8 <= alias <= 8:
        raise ValueError("trajectory alias lies outside the supported frozen range")
    first_utc_ns = _positive_int(path["first_sample_estimate_utc_ns"], "first-sample UTC estimate")
    analysis_start_s = _finite_float(path["analysis_start_s"], "analysis start")
    analysis_stop_s = _finite_float(path["analysis_stop_s"], "analysis stop")
    if analysis_start_s < 0.0 or analysis_stop_s - analysis_start_s != 1.5:
        raise ValueError("path-local episode must be one positive 1.5 s interval")
    if abs((first_utc_ns + round(analysis_start_s * 1e9)) - episode_start_utc_ns) > 1:
        raise ValueError("path-local start disagrees with absolute episode UTC")
    if abs((first_utc_ns + round(analysis_stop_s * 1e9)) - episode_stop_utc_ns) > 1:
        raise ValueError("path-local stop disagrees with absolute episode UTC")
    trajectory_start = _finite_float(path["trajectory_start_s"], "trajectory start")
    trajectory_stop = _finite_float(path["trajectory_stop_s"], "trajectory stop")
    if not trajectory_start <= analysis_start_s < analysis_stop_s <= trajectory_stop:
        raise ValueError("path episode lies outside the frozen branch")
    coefficients = _sequence(path["trajectory_absolute_coefficients_hz"], "coefficients")
    if len(coefficients) != 2 or any(not math.isfinite(float(item)) for item in coefficients):
        raise ValueError("primary experiment requires one degree-one frozen trajectory")
    _finite_float(path["trajectory_reference_time_s"], "trajectory reference time")
    if_center = _positive_int(path["nominal_if_center_hz"], "nominal IF center")
    sky_frequency = _positive_int(path["nominal_sky_frequency_hz"], "nominal sky frequency")
    lo = int(_mapping(root["frequency_coordinate"], "frequency coordinate")["nominal_lnb_lo_hz"])
    if sky_frequency != if_center + lo:
        raise ValueError("nominal sky frequency does not equal IF plus frozen LNB LO")
    products = _mapping(path["products"], "path products")
    _exact_keys(products, _PRODUCT_KEYS, "path products")
    product_digests = []
    prefix = f"bulk://analysis/{session_id}/{run_id}/scientific/path-standard/{scope_id}/"
    for name, binding_value in products.items():
        binding = _mapping(binding_value, f"product {name}")
        _exact_keys(binding, _PRODUCT_BINDING_KEYS, f"product {name}")
        uri = _nonempty_string(binding["logical_uri"], f"{name} URI")
        if not uri.startswith(prefix):
            raise ValueError("product URI escaped the frozen analysis scope")
        digest = _matching_string(binding["sha256"], _SHA256_RE, f"{name} digest")
        product_digests.append((name, digest))
    source = _mapping(path["frozen_source"], "frozen source")
    _exact_keys(source, _SOURCE_KEYS, "frozen source")
    source_id = _matching_string(
        source["source_observation_id"], _SHA256_RE, "source observation ID"
    )
    source_sample_start = _nonnegative_int(source["sample_start"], "source sample start")
    source_time_s = _finite_float(source["detection_time_s"], "source detection time")
    sample_rate = int(_mapping(root["measurement"], "measurement")["sample_rate_hz"])
    if source_sample_start != round(source_time_s * sample_rate):
        raise ValueError("source time and sample start disagree")
    source_epoch = _nonnegative_int(source["local_epoch_sample"], "source local epoch")
    if source_epoch >= 3_125:
        raise ValueError("source local epoch lies outside one 1.25 ms coarse window")
    _nonnegative_int(source["candidate_rank"], "candidate rank")
    _integer(source["source_alias_index"], "source alias")
    for field in ("tracking_cfo_hz", "exact_score", "control_score", "margin"):
        _finite_float(source[field], field)
    return MultiRadioPathBinding(
        path_id=path_id,
        stream_id=stream_id,
        physical_radio_id=radio_id,
        receiver_id=receiver_id,
        edge=edge,
        scope_id=scope_id,
        branch_id=branch_id,
        trajectory_id=trajectory_id,
        trajectory_alias_index=alias,
        analysis_start_s=analysis_start_s,
        analysis_stop_s=analysis_stop_s,
        first_sample_estimate_utc_ns=first_utc_ns,
        nominal_sky_frequency_hz=sky_frequency,
        source_observation_id=source_id,
        source_sample_start=source_sample_start,
        source_local_epoch_sample=source_epoch,
        product_digests=tuple(sorted(product_digests)),
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} has unsupported fields")


def _matching_string(value: object, pattern: re.Pattern[str], name: str) -> str:
    checked = _nonempty_string(value, name)
    if pattern.fullmatch(checked) is None:
        raise ValueError(f"{name} has invalid format")
    return checked


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _nonnegative_int(value: object, name: str) -> int:
    checked = _integer(value, name)
    if checked < 0:
        raise ValueError(f"{name} must be nonnegative")
    return checked


def _positive_int(value: object, name: str) -> int:
    checked = _integer(value, name)
    if checked <= 0:
        raise ValueError(f"{name} must be positive")
    return checked


def _finite_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    checked = float(value)
    if not math.isfinite(checked):
        raise ValueError(f"{name} must be finite")
    return checked


def _repository_path(root: Path, value: object, name: str) -> Path:
    relative = Path(_nonempty_string(value, name))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{name} must be repository relative")
    return root / relative


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_digest(path: Path, expected: object, name: str) -> None:
    checked = _matching_string(expected, _SHA256_RE, f"{name} digest")
    if _sha256(path) != checked:
        raise ValueError(f"{name} digest mismatch")
