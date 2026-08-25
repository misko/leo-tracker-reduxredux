"""Fail-closed input authority for the reviewed Doppler research program."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "org.leo.research.doppler-experiment-dataset-policy/v1"

_POLICY_KEYS = {"schema", "authority", "global_denials", "roles", "captures"}
_AUTHORITY_KEYS = {
    "deny_by_default",
    "dynamic_capture_discovery_forbidden",
    "new_or_in_progress_capture_use_forbidden",
    "inventory_repository_commit",
    "inventory_path",
    "inventory_sha256",
    "inventory_capture_count",
    "pre_inventory_capture_ids",
    "latest_permitted_session_id",
    "policy_basis_repository_commit",
}
_ROLE_KEYS = {
    "purpose",
    "expected_capture_count",
    "minimum_evaluable_capture_count",
    "raw_iq_read_allowed",
    "capture_ids",
    "selection_constraints",
}
_CAPTURE_KEYS = {
    "recording_manifest_sha256",
    "analysis_run_id",
    "analysis_manifest_sha256",
    "pipeline_lane",
    "provenance_status",
}
_EXPECTED_ROLES = {
    "holdout_foundation",
    "rate_development",
    "polynomial_injection",
    "multi_radio",
    "v3_v4_canary",
}
_ALLOWED_PROVENANCE = {
    "post_fix_counter_authoritative_opened",
    "post_fix_counter_authoritative_opened_hard_null",
    "post_fix_counter_authoritative_protocol_unopened",
}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_SESSION_RE = re.compile(r"cap-(?P<stamp>[0-9]{8}T[0-9]{6})-[0-9a-f]{12}\Z")
_RUN_RE = re.compile(r"capture-[0-9a-f]{32}\Z")


@dataclass(frozen=True, slots=True)
class CaptureBinding:
    """One exact capture and sealed Standard analysis binding."""

    session_id: str
    recording_manifest_sha256: str
    analysis_run_id: str
    analysis_manifest_sha256: str
    provenance_status: str


@dataclass(frozen=True, slots=True)
class RolePolicy:
    """Captures and restrictions granted to one experiment role."""

    name: str
    purpose: str
    minimum_evaluable_capture_count: int
    raw_iq_read_allowed: bool
    capture_ids: tuple[str, ...]
    selection_constraints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaptureDisposition:
    """One authorized capture's protocol outcome."""

    capture: CaptureBinding
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class DopplerDatasetPolicy:
    """Validated deny-by-default dataset authority."""

    inventory_repository_commit: str
    inventory_path: str
    inventory_sha256: str
    inventory_capture_count: int
    pre_inventory_capture_ids: tuple[str, ...]
    latest_permitted_session_id: str
    policy_basis_repository_commit: str
    global_denials: tuple[str, ...]
    roles: tuple[RolePolicy, ...]
    captures: tuple[CaptureBinding, ...]

    def role(self, name: str) -> RolePolicy:
        for role in self.roles:
            if role.name == name:
                return role
        raise ValueError(f"experiment role is not authorized: {name}")

    def capture(self, session_id: str) -> CaptureBinding:
        for capture in self.captures:
            if capture.session_id == session_id:
                return capture
        raise ValueError(f"capture is not present in the policy: {session_id}")


def load_doppler_dataset_policy(path: Path) -> DopplerDatasetPolicy:
    """Load and strictly validate a v1 Doppler dataset policy."""

    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    root = _mapping(document, "policy")
    _exact_keys(root, _POLICY_KEYS, "policy")
    if root["schema"] != SCHEMA:
        raise ValueError("unsupported Doppler dataset policy schema")

    authority = _mapping(root["authority"], "authority")
    _exact_keys(authority, _AUTHORITY_KEYS, "authority")
    for field in (
        "deny_by_default",
        "dynamic_capture_discovery_forbidden",
        "new_or_in_progress_capture_use_forbidden",
    ):
        if authority[field] is not True:
            raise ValueError(f"authority.{field} must be true")
    inventory_repository_commit = _matching_string(
        authority["inventory_repository_commit"], _COMMIT_RE, "inventory_repository_commit"
    )
    policy_basis_repository_commit = _matching_string(
        authority["policy_basis_repository_commit"],
        _COMMIT_RE,
        "policy_basis_repository_commit",
    )
    inventory_path = _nonempty_string(authority["inventory_path"], "inventory_path")
    if Path(inventory_path).is_absolute() or ".." in Path(inventory_path).parts:
        raise ValueError("inventory_path must be a repository-relative path")
    inventory_sha256 = _matching_string(
        authority["inventory_sha256"], _SHA256_RE, "inventory_sha256"
    )
    inventory_capture_count = _nonnegative_int(
        authority["inventory_capture_count"], "inventory_capture_count"
    )
    pre_inventory_capture_ids = tuple(
        _session_id(item, "pre_inventory_capture_ids")
        for item in _unique_string_sequence(
            authority["pre_inventory_capture_ids"], "pre_inventory_capture_ids"
        )
    )
    latest_permitted_session_id = _session_id(
        authority["latest_permitted_session_id"], "latest_permitted_session_id"
    )

    denials = _unique_string_sequence(root["global_denials"], "global_denials")
    if not denials:
        raise ValueError("global_denials cannot be empty")

    capture_documents = _mapping(root["captures"], "captures")
    captures: list[CaptureBinding] = []
    latest_stamp = _session_stamp(latest_permitted_session_id)
    for session_id, value in capture_documents.items():
        checked_session_id = _session_id(session_id, "capture session id")
        if _session_stamp(checked_session_id) > latest_stamp:
            raise ValueError(f"capture is newer than the policy cutoff: {checked_session_id}")
        capture = _mapping(value, f"captures.{checked_session_id}")
        _exact_keys(capture, _CAPTURE_KEYS, f"captures.{checked_session_id}")
        if capture["pipeline_lane"] != "standard":
            raise ValueError(f"capture is not bound to the Standard lane: {checked_session_id}")
        provenance = _nonempty_string(
            capture["provenance_status"], f"captures.{checked_session_id}.provenance_status"
        )
        if provenance not in _ALLOWED_PROVENANCE:
            raise ValueError(f"unsupported capture provenance: {checked_session_id}")
        captures.append(
            CaptureBinding(
                session_id=checked_session_id,
                recording_manifest_sha256=_matching_string(
                    capture["recording_manifest_sha256"],
                    _SHA256_RE,
                    f"captures.{checked_session_id}.recording_manifest_sha256",
                ),
                analysis_run_id=_matching_string(
                    capture["analysis_run_id"],
                    _RUN_RE,
                    f"captures.{checked_session_id}.analysis_run_id",
                ),
                analysis_manifest_sha256=_matching_string(
                    capture["analysis_manifest_sha256"],
                    _SHA256_RE,
                    f"captures.{checked_session_id}.analysis_manifest_sha256",
                ),
                provenance_status=provenance,
            )
        )
    if inventory_capture_count < len(captures):
        raise ValueError("policy binds more captures than its frozen inventory")

    role_documents = _mapping(root["roles"], "roles")
    if set(role_documents) != _EXPECTED_ROLES:
        raise ValueError("policy roles do not match the reviewed experiment roles")
    known_capture_ids = set(capture_documents)
    referenced_capture_ids: set[str] = set()
    roles: list[RolePolicy] = []
    for name, value in role_documents.items():
        role = _mapping(value, f"roles.{name}")
        _exact_keys(role, _ROLE_KEYS, f"roles.{name}")
        capture_ids = tuple(
            _session_id(item, f"roles.{name}.capture_ids")
            for item in _unique_string_sequence(role["capture_ids"], f"roles.{name}.capture_ids")
        )
        expected_count = _nonnegative_int(
            role["expected_capture_count"], f"roles.{name}.expected_capture_count"
        )
        if len(capture_ids) != expected_count:
            raise ValueError(f"roles.{name} does not contain its expected capture count")
        unknown = set(capture_ids) - known_capture_ids
        if unknown:
            raise ValueError(f"roles.{name} references unbound captures: {sorted(unknown)}")
        minimum = _nonnegative_int(
            role["minimum_evaluable_capture_count"],
            f"roles.{name}.minimum_evaluable_capture_count",
        )
        if minimum > expected_count:
            raise ValueError(f"roles.{name} minimum exceeds its capture count")
        raw_iq_read_allowed = role["raw_iq_read_allowed"]
        if not isinstance(raw_iq_read_allowed, bool):
            raise ValueError(f"roles.{name}.raw_iq_read_allowed must be boolean")
        roles.append(
            RolePolicy(
                name=name,
                purpose=_nonempty_string(role["purpose"], f"roles.{name}.purpose"),
                minimum_evaluable_capture_count=minimum,
                raw_iq_read_allowed=raw_iq_read_allowed,
                capture_ids=capture_ids,
                selection_constraints=_unique_string_sequence(
                    role["selection_constraints"], f"roles.{name}.selection_constraints"
                ),
            )
        )
        referenced_capture_ids.update(capture_ids)
    if referenced_capture_ids != known_capture_ids:
        raise ValueError("every policy capture must be granted to at least one role")
    if not set(pre_inventory_capture_ids) <= known_capture_ids:
        raise ValueError("pre-inventory capture list references an unbound capture")

    role_by_name = {item.name: item for item in roles}
    holdout_ids = set(role_by_name["holdout_foundation"].capture_ids)
    non_holdout_ids = {
        session_id
        for name, role in role_by_name.items()
        if name != "holdout_foundation"
        for session_id in role.capture_ids
    }
    if holdout_ids & non_holdout_ids:
        raise ValueError("holdout-foundation captures cannot be granted to another role")
    capture_by_id = {item.session_id: item for item in captures}
    if {capture_by_id[session_id].provenance_status for session_id in holdout_ids} != {
        "post_fix_counter_authoritative_protocol_unopened"
    }:
        raise ValueError("holdout captures must retain protocol-unopened provenance")
    injection_ids = role_by_name["polynomial_injection"].capture_ids
    if {capture_by_id[session_id].provenance_status for session_id in injection_ids} != {
        "post_fix_counter_authoritative_opened_hard_null"
    }:
        raise ValueError("polynomial injection is restricted to opened hard-null captures")
    for role_name in ("rate_development", "multi_radio", "v3_v4_canary"):
        role_capture_ids = role_by_name[role_name].capture_ids
        if {capture_by_id[session_id].provenance_status for session_id in role_capture_ids} != {
            "post_fix_counter_authoritative_opened"
        }:
            raise ValueError(f"{role_name} is restricted to previously opened captures")
    if not set(pre_inventory_capture_ids) <= set(role_by_name["rate_development"].capture_ids):
        raise ValueError("pre-inventory captures are restricted to rate development")

    return DopplerDatasetPolicy(
        inventory_repository_commit=inventory_repository_commit,
        inventory_path=inventory_path,
        inventory_sha256=inventory_sha256,
        inventory_capture_count=inventory_capture_count,
        pre_inventory_capture_ids=pre_inventory_capture_ids,
        latest_permitted_session_id=latest_permitted_session_id,
        policy_basis_repository_commit=policy_basis_repository_commit,
        global_denials=denials,
        roles=tuple(roles),
        captures=tuple(captures),
    )


def authorize_capture(
    policy: DopplerDatasetPolicy,
    *,
    experiment_role: str,
    session_id: str,
    recording_manifest_sha256: str,
    analysis_run_id: str,
    analysis_manifest_sha256: str,
) -> CaptureBinding:
    """Authorize one exact input binding or fail without fallback."""

    role = policy.role(experiment_role)
    if not role.raw_iq_read_allowed:
        raise ValueError(f"raw IQ reads are not authorized for role: {experiment_role}")
    if session_id not in role.capture_ids:
        raise ValueError(f"capture is not authorized for role {experiment_role}: {session_id}")
    capture = policy.capture(session_id)
    supplied = (
        recording_manifest_sha256,
        analysis_run_id,
        analysis_manifest_sha256,
    )
    expected = (
        capture.recording_manifest_sha256,
        capture.analysis_run_id,
        capture.analysis_manifest_sha256,
    )
    if supplied != expected:
        raise ValueError(f"capture binding disagrees with policy: {session_id}")
    return capture


def authorize_consumed_inputs(
    policy: DopplerDatasetPolicy,
    *,
    experiment_role: str,
    inputs: Iterable[CaptureBinding],
) -> tuple[CaptureBinding, ...]:
    """Validate a consumed-input ledger against one exact role allowlist."""

    checked: list[CaptureBinding] = []
    seen: set[str] = set()
    for item in inputs:
        if item.session_id in seen:
            raise ValueError(f"duplicate consumed capture: {item.session_id}")
        seen.add(item.session_id)
        checked.append(
            authorize_capture(
                policy,
                experiment_role=experiment_role,
                session_id=item.session_id,
                recording_manifest_sha256=item.recording_manifest_sha256,
                analysis_run_id=item.analysis_run_id,
                analysis_manifest_sha256=item.analysis_manifest_sha256,
            )
        )
    return tuple(checked)


def finalize_capture_dispositions(
    policy: DopplerDatasetPolicy,
    *,
    experiment_role: str,
    dispositions: Iterable[CaptureDisposition],
) -> tuple[CaptureDisposition, ...]:
    """Validate minimum evaluability while retaining the complete failure ledger."""

    role = policy.role(experiment_role)
    checked: list[CaptureDisposition] = []
    seen: set[str] = set()
    evaluable_count = 0
    for disposition in dispositions:
        capture = disposition.capture
        if capture.session_id in seen:
            raise ValueError(f"duplicate capture disposition: {capture.session_id}")
        seen.add(capture.session_id)
        authorized_capture = authorize_capture(
            policy,
            experiment_role=experiment_role,
            session_id=capture.session_id,
            recording_manifest_sha256=capture.recording_manifest_sha256,
            analysis_run_id=capture.analysis_run_id,
            analysis_manifest_sha256=capture.analysis_manifest_sha256,
        )
        if capture != authorized_capture:
            raise ValueError(f"capture disposition binding disagrees: {capture.session_id}")
        if disposition.status == "evaluable":
            evaluable_count += 1
        elif disposition.status == "non_evaluable":
            if not disposition.reason.strip():
                raise ValueError("non-evaluable capture disposition requires a reason")
        else:
            raise ValueError(f"unsupported capture disposition status: {disposition.status}")
        checked.append(disposition)
    if role.minimum_evaluable_capture_count > 0 and seen != set(role.capture_ids):
        raise ValueError(f"role {experiment_role} must retain its complete capture ledger")
    if evaluable_count < role.minimum_evaluable_capture_count:
        raise ValueError(
            f"role {experiment_role} requires at least "
            f"{role.minimum_evaluable_capture_count} evaluable captures"
        )
    return tuple(checked)


def authorize_manifest_files(
    policy: DopplerDatasetPolicy,
    *,
    experiment_role: str,
    session_id: str,
    analysis_run_id: str,
    recording_manifest_path: Path,
    analysis_manifest_path: Path,
) -> CaptureBinding:
    """Hash the two opened manifests before authorizing their capture binding."""

    return authorize_capture(
        policy,
        experiment_role=experiment_role,
        session_id=session_id,
        recording_manifest_sha256=_file_sha256(recording_manifest_path),
        analysis_run_id=analysis_run_id,
        analysis_manifest_sha256=_file_sha256(analysis_manifest_path),
    )


def verify_policy_inventory(policy: DopplerDatasetPolicy, repository_root: Path) -> Path:
    """Verify the frozen inventory bytes and every inventory-covered binding."""

    root = repository_root.resolve()
    inventory_path = (root / policy.inventory_path).resolve()
    if not inventory_path.is_relative_to(root):
        raise ValueError("policy inventory resolves outside the repository")
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    if f"sha256:{digest}" != policy.inventory_sha256:
        raise ValueError("policy inventory digest does not match")

    with inventory_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != policy.inventory_capture_count:
        raise ValueError("policy inventory capture count does not match")
    if not rows:
        raise ValueError("policy inventory cannot be empty")
    by_session: dict[str, dict[str, str]] = {}
    for inventory_row in rows:
        session_id = inventory_row.get("capture_session_id", "")
        if session_id in by_session:
            raise ValueError(f"duplicate capture in policy inventory: {session_id}")
        by_session[session_id] = inventory_row
    first_inventory_stamp = min(_session_stamp(session_id) for session_id in by_session)
    actual_pre_inventory_ids = {
        capture.session_id
        for capture in policy.captures
        if _session_stamp(capture.session_id) < first_inventory_stamp
    }
    if actual_pre_inventory_ids != set(policy.pre_inventory_capture_ids):
        raise ValueError("pre-inventory capture set does not match the reviewed exception list")
    for capture in policy.captures:
        if _session_stamp(capture.session_id) < first_inventory_stamp:
            continue
        matched_row = by_session.get(capture.session_id)
        if matched_row is None:
            raise ValueError(
                f"policy capture is absent from frozen inventory: {capture.session_id}"
            )
        expected = (
            "committed",
            "succeeded",
            "standard",
            "t",
            capture.recording_manifest_sha256,
            capture.recording_manifest_sha256,
            capture.analysis_run_id,
            capture.analysis_manifest_sha256,
        )
        actual = (
            matched_row.get("capture_state"),
            matched_row.get("analysis_state"),
            matched_row.get("pipeline_lane"),
            matched_row.get("raw_available"),
            matched_row.get("recording_manifest_digest"),
            matched_row.get("input_manifest_digest"),
            matched_row.get("analysis_run_id"),
            matched_row.get("analysis_manifest_digest"),
        )
        if actual != expected:
            raise ValueError(f"frozen inventory binding disagrees: {capture.session_id}")
        if not matched_row.get("analysis_sealed_utc") or not matched_row.get(
            "raw_integrity_attestation_id"
        ):
            raise ValueError(f"frozen inventory is not sealed and attested: {capture.session_id}")
    return inventory_path


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(document: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(document) != expected:
        raise ValueError(f"{label} keys do not match the reviewed schema")


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _matching_string(value: object, pattern: re.Pattern[str], label: str) -> str:
    checked = _nonempty_string(value, label)
    if pattern.fullmatch(checked) is None:
        raise ValueError(f"{label} has an invalid format")
    return checked


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _unique_string_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    checked = tuple(_nonempty_string(item, label) for item in value)
    if len(set(checked)) != len(checked):
        raise ValueError(f"{label} cannot contain duplicates")
    return checked


def _session_id(value: object, label: str) -> str:
    return _matching_string(value, _SESSION_RE, label)


def _session_stamp(session_id: str) -> str:
    match = _SESSION_RE.fullmatch(session_id)
    if match is None:
        raise ValueError(f"invalid capture session id: {session_id}")
    return match.group("stamp")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"
