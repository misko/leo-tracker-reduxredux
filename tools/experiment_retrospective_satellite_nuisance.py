#!/usr/bin/env python3
"""Run the frozen retrospective Starlink/nuisance association experiment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from numpy.typing import NDArray

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.satellite_nuisance_association import (
    CandidateFitBank,
    MeasurementTrack,
    chronological_block_mask,
    chronological_mask,
    fit_hierarchical_candidates,
    fit_independent_path_linear_null,
    fit_offset_candidates,
    fit_radio_polynomial_null,
    fit_unregularized_common_affine_candidates,
    permute_fit_response_within_paths,
)
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    ElementSetCatalogue,
    parse_element_set_records,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import MAX_ANGULAR_RATE_DEG_S, SamplingGrid
from leo.sky.screening import observe_grid
from leo.sky.sites import resolve_preset

ROOT = Path(__file__).parents[1]
DEFAULT_PROTOCOL = ROOT / "config/analysis/retrospective-satellite-nuisance-protocol-v1.json"
LATEST_TLE_RECONSTRUCTION = (
    ROOT / "config/analysis/retrospective-satellite-nuisance-latest-tle-reconstruction-v1.json"
)
TLE_DURABILITY_AMENDMENT = (
    ROOT / "config/analysis/retrospective-satellite-nuisance-tle-durability-amendment-v1.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "reports/figures/2026_08_26_retrospective_satellite_nuisance"
SCHEMA = "org.leo.research.retrospective-satellite-nuisance-evidence/v1"
PROTOCOL_SCHEMA = "org.leo.research.retrospective-satellite-nuisance-protocol/v1"
RECONSTRUCTION_SCHEMA = "org.leo.research.retrospective-satellite-nuisance-tle-reconstruction/v1"
TLE_DURABILITY_AMENDMENT_SCHEMA = (
    "org.leo.research.retrospective-satellite-nuisance-tle-durability-amendment/v1"
)
TLE_DURABILITY_AMENDMENT_SHA256 = (
    "sha256:d7048ff6fd17ae0b773a1031ddf37b04930b407e8dfb00e1cb5f655dd61ca404"
)
BIN_NS = 20_000_000
COARSE_SPACING_S = 0.1

_UTC_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d{1,9}))?Z$"
)
_SNAPSHOT_METADATA_KEYS = {
    "catalog_sha256",
    "normalized_object",
    "raw_media_type",
    "raw_object",
    "raw_sha256",
    "retrieved_at",
    "satellite_count",
    "schema",
    "scope",
    "snapshot",
    "source",
    "source_url",
    "tle_epoch_max",
    "tle_epoch_min",
}

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class BoundTrack:
    capture_id: str
    bundle_id: str
    data_kind: str
    track: MeasurementTrack
    utc_ns: IntArray
    rf_frequency_hz: float
    primary: bool


@dataclass(frozen=True, slots=True)
class CandidatePopulation:
    catalogue_indices: IntArray
    norad_ids: IntArray
    names: tuple[str, ...]
    prediction_hz: FloatArray
    minimum_elevation_deg: FloatArray
    maximum_elevation_deg: FloatArray
    coarse_candidate_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{label} is not a canonical SHA-256")
    return value


def _utc_timestamp_ns(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not a canonical UTC timestamp")
    match = _UTC_TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"{label} is not a canonical UTC timestamp")
    parsed = datetime.strptime(match.group("date"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return int(parsed.timestamp()) * 1_000_000_000 + int(fraction or "0")


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    return value, payload


def _validate_snapshot_receipt(
    capture_id: str,
    protocol_binding: dict[str, Any],
    receipt: object,
    raw_cache: dict[tuple[Path, str], tuple[int, int]],
) -> None:
    receipt_keys = {
        "raw_path",
        "raw_sha256",
        "raw_byte_size",
        "snapshot_metadata_path",
        "snapshot_metadata_sha256",
        "retrieved_at",
        "first_measurement_utc_ns",
        "catalog_object_count",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
        raise ValueError(f"durable TLE receipt is malformed for {capture_id}")
    cross_bound_fields = (
        "raw_path",
        "raw_sha256",
        "retrieved_at",
        "first_measurement_utc_ns",
        "catalog_object_count",
    )
    if any(receipt[field] != protocol_binding[field] for field in cross_bound_fields):
        raise ValueError(f"durable TLE receipt disagrees with protocol for {capture_id}")

    raw_path = Path(str(receipt["raw_path"]))
    raw_sha256 = _canonical_sha(receipt["raw_sha256"], f"raw TLE digest for {capture_id}")
    raw_key = (raw_path, raw_sha256)
    cached = raw_cache.get(raw_key)
    if cached is None:
        try:
            raw_bytes = raw_path.read_bytes()
        except OSError as error:
            raise ValueError(f"raw TLE is unavailable for {capture_id}") from error
        if _sha256_bytes(raw_bytes) != raw_sha256:
            raise ValueError(f"raw TLE digest drifted for {capture_id}")
        try:
            raw_text = raw_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError(f"raw TLE is not ASCII for {capture_id}") from error
        raw_cache[raw_key] = (len(raw_bytes), len(parse_element_set_records(raw_text)))
        cached = raw_cache[raw_key]
    if cached[0] != int(receipt["raw_byte_size"]):
        raise ValueError(f"raw TLE byte size drifted for {capture_id}")
    if cached[1] != int(receipt["catalog_object_count"]):
        raise ValueError(f"raw TLE object count drifted for {capture_id}")

    metadata_path = Path(str(receipt["snapshot_metadata_path"]))
    metadata, metadata_bytes = _read_json_object(
        metadata_path, f"immutable TLE snapshot metadata for {capture_id}"
    )
    if _sha256_bytes(metadata_bytes) != _canonical_sha(
        receipt["snapshot_metadata_sha256"], f"TLE metadata digest for {capture_id}"
    ):
        raise ValueError(f"immutable TLE snapshot metadata digest drifted for {capture_id}")
    if set(metadata) != _SNAPSHOT_METADATA_KEYS:
        raise ValueError(f"immutable TLE snapshot metadata schema drifted for {capture_id}")
    digest = raw_sha256.removeprefix("sha256:")
    expected_raw_object = f"raw/space-track/{digest}.tle"
    if (
        metadata.get("schema") != "leo-tracker.catalog-store-snapshot/v1"
        or metadata.get("source") != "space-track"
        or metadata.get("scope") != "starlink"
        or metadata.get("raw_media_type") != "text/plain"
        or metadata.get("raw_sha256") != digest
        or metadata.get("catalog_sha256") != digest
        or metadata.get("raw_object") != expected_raw_object
        or metadata.get("retrieved_at") != receipt["retrieved_at"]
        or int(metadata.get("satellite_count", -1)) != int(receipt["catalog_object_count"])
    ):
        raise ValueError(f"immutable TLE snapshot metadata drifted for {capture_id}")
    snapshot_relative = str(metadata.get("snapshot"))
    if not metadata_path.as_posix().endswith(f"/{snapshot_relative}"):
        raise ValueError(f"immutable TLE snapshot metadata path drifted for {capture_id}")
    if not raw_path.as_posix().endswith(f"/{expected_raw_object}"):
        raise ValueError(f"raw TLE path disagrees with snapshot metadata for {capture_id}")

    retrieved_ns = _utc_timestamp_ns(receipt["retrieved_at"], f"TLE retrieval for {capture_id}")
    first_measurement_utc_ns = int(receipt["first_measurement_utc_ns"])
    if retrieved_ns >= first_measurement_utc_ns:
        raise ValueError(f"TLE does not strictly predate {capture_id}")


def _validate_tle_durability_amendment(
    protocol: dict[str, Any],
    protocol_path: Path,
    amendment: dict[str, Any],
) -> None:
    required_root = {
        "schema",
        "date_utc",
        "chronology",
        "original_protocol",
        "historical_archive_index",
        "frozen_snapshots",
        "latest_causal_tle_reconstruction",
        "sealed_outcome_preservation",
        "permitted_changes",
        "forbidden_changes",
    }
    if set(amendment) != required_root or amendment.get("schema") != (
        TLE_DURABILITY_AMENDMENT_SCHEMA
    ):
        raise ValueError("TLE durability amendment is malformed")

    original = amendment["original_protocol"]
    original_keys = {
        "path",
        "sha256",
        "initial_freeze_commit",
        "final_pre_execution_binding_commit",
    }
    if not isinstance(original, dict) or set(original) != original_keys:
        raise ValueError("TLE durability protocol binding is malformed")
    original_path = ROOT / str(original["path"])
    expected_protocol_sha = _canonical_sha(original["sha256"], "original protocol digest")
    if _sha256(original_path) != expected_protocol_sha or _sha256(protocol_path) != (
        expected_protocol_sha
    ):
        raise ValueError("original satellite nuisance protocol digest drifted")

    historical_index = amendment["historical_archive_index"]
    historical_keys = {
        "path_at_freeze",
        "sha256_at_freeze",
        "role",
        "current_or_historical_index_bytes_required_for_replay",
        "reason",
    }
    tle_inputs = protocol["tle_inputs"]
    if not isinstance(historical_index, dict) or set(historical_index) != historical_keys:
        raise ValueError("historical TLE index receipt is malformed")
    if (
        historical_index.get("role") != "provenance_only"
        or historical_index.get("current_or_historical_index_bytes_required_for_replay")
        is not False
        or historical_index.get("path_at_freeze") != tle_inputs.get("archive_index_path")
        or historical_index.get("sha256_at_freeze")
        != tle_inputs.get("archive_index_sha256_at_freeze")
    ):
        raise ValueError("historical TLE index receipt disagrees with frozen protocol")

    required_ids = tuple(str(item) for item in protocol["authority"]["required_capture_ids"])
    frozen_snapshots = amendment["frozen_snapshots"]
    protocol_snapshots = tle_inputs["snapshots"]
    if (
        not isinstance(frozen_snapshots, dict)
        or set(frozen_snapshots) != set(required_ids)
        or set(protocol_snapshots) != set(required_ids)
    ):
        raise ValueError("durable TLE snapshot receipt set disagrees with capture authority")
    raw_cache: dict[tuple[Path, str], tuple[int, int]] = {}
    for capture_id in required_ids:
        _validate_snapshot_receipt(
            capture_id,
            protocol_snapshots[capture_id],
            frozen_snapshots[capture_id],
            raw_cache,
        )

    latest = amendment["latest_causal_tle_reconstruction"]
    latest_keys = {
        "capture_id",
        "authority_path",
        "authority_sha256",
        "replacement_record_path",
        "replacement_record_sha256",
        "source_collected_at",
        "reconstructed_raw_sha256",
        "catalog_object_count",
        "historical_temporary_raw_path_required_for_replay",
    }
    if not isinstance(latest, dict) or set(latest) != latest_keys:
        raise ValueError("latest-causal TLE durability receipt is malformed")
    capture_id = str(latest["capture_id"])
    sensitivity = tle_inputs["source_sensitivity"].get(capture_id)
    if not isinstance(sensitivity, dict):
        raise ValueError("latest-causal TLE sensitivity binding is missing")
    reconstruction = _latest_tle_reconstruction_document()
    authority_path = ROOT / str(latest["authority_path"])
    replacement_path = ROOT / str(latest["replacement_record_path"])
    if (
        latest.get("historical_temporary_raw_path_required_for_replay") is not False
        or authority_path != LATEST_TLE_RECONSTRUCTION
        or _sha256(authority_path)
        != _canonical_sha(latest["authority_sha256"], "TLE reconstruction authority digest")
        or _sha256(replacement_path)
        != _canonical_sha(latest["replacement_record_sha256"], "replacement TLE digest")
        or latest.get("source_collected_at") != sensitivity.get("collected_at")
        or latest.get("source_collected_at") != reconstruction.get("source_collected_at")
        or latest.get("reconstructed_raw_sha256") != sensitivity.get("raw_sha256")
        or latest.get("reconstructed_raw_sha256") != reconstruction.get("source_raw_sha256")
        or int(latest.get("catalog_object_count", -1))
        != int(sensitivity.get("catalog_object_count", -2))
        or int(latest.get("catalog_object_count", -1))
        != int(reconstruction.get("catalog_object_count", -2))
        or latest.get("replacement_record_path")
        != reconstruction["replacement"].get("replacement_record_path")
        or latest.get("replacement_record_sha256")
        != reconstruction["replacement"].get("replacement_record_sha256")
    ):
        raise ValueError("latest-causal TLE durability receipt drifted")
    collected_ns = _utc_timestamp_ns(latest["source_collected_at"], "latest-causal TLE collection")
    if collected_ns >= int(sensitivity["first_measurement_utc_ns"]):
        raise ValueError("latest-causal TLE sensitivity is not causal")

    sealed = amendment["sealed_outcome_preservation"]
    sealed_keys = {
        "scientific_change",
        "iq_read_or_experiment_rerun_authorized",
        "report_path",
        "report_sha256",
        "evidence_path",
        "evidence_sha256",
        "artifact_manifest_path",
        "artifact_manifest_sha256",
    }
    if (
        not isinstance(sealed, dict)
        or set(sealed) != sealed_keys
        or sealed.get("scientific_change") is not False
        or sealed.get("iq_read_or_experiment_rerun_authorized") is not False
    ):
        raise ValueError("sealed satellite outcome receipt is malformed")
    for label in ("report", "evidence", "artifact_manifest"):
        sealed_path = ROOT / str(sealed[f"{label}_path"])
        if _sha256(sealed_path) != _canonical_sha(
            sealed[f"{label}_sha256"], f"sealed {label} digest"
        ):
            raise ValueError(f"sealed satellite {label} digest drifted")


def _load_tle_durability_amendment(protocol: dict[str, Any], protocol_path: Path) -> dict[str, Any]:
    amendment, payload = _read_json_object(TLE_DURABILITY_AMENDMENT, "TLE durability amendment")
    if _sha256_bytes(payload) != TLE_DURABILITY_AMENDMENT_SHA256:
        raise ValueError("TLE durability amendment digest drifted")
    _validate_tle_durability_amendment(protocol, protocol_path, amendment)
    return amendment


def _iso_utc(utc_ns: int) -> str:
    seconds, nanoseconds = divmod(utc_ns, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _latest_tle_reconstruction_document() -> dict[str, Any]:
    document = json.loads(LATEST_TLE_RECONSTRUCTION.read_text(encoding="utf-8"))
    required = {
        "schema",
        "capture_id",
        "source_collected_at",
        "source_raw_sha256",
        "catalog_object_count",
        "base_raw_sha256",
        "replacement",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("latest-causal TLE reconstruction authority is malformed")
    if document.get("schema") != RECONSTRUCTION_SCHEMA:
        raise ValueError("latest-causal TLE reconstruction schema drifted")
    replacement = document["replacement"]
    replacement_required = {
        "satellite_number",
        "base_record_sha256",
        "replacement_record_path",
        "replacement_record_sha256",
        "reconstruction_rule",
    }
    if not isinstance(replacement, dict) or set(replacement) != replacement_required:
        raise ValueError("latest-causal TLE replacement binding is malformed")
    replacement_path = ROOT / str(replacement["replacement_record_path"])
    if _sha256(replacement_path) != _canonical_sha(
        replacement["replacement_record_sha256"], "replacement TLE record digest"
    ):
        raise ValueError("latest-causal replacement TLE record digest drifted")
    return document


def _latest_causal_tle_text(protocol: dict[str, Any]) -> str:
    """Reconstruct the exact 14:02 catalogue from durable digest-bound inputs."""

    reconstruction = _latest_tle_reconstruction_document()
    capture_id = str(reconstruction["capture_id"])
    sensitivity = protocol["tle_inputs"]["source_sensitivity"][capture_id]
    if (
        sensitivity["raw_sha256"] != reconstruction["source_raw_sha256"]
        or sensitivity["collected_at"] != reconstruction["source_collected_at"]
        or int(sensitivity["catalog_object_count"]) != int(reconstruction["catalog_object_count"])
    ):
        raise ValueError("latest-causal TLE reconstruction disagrees with frozen protocol")
    base_binding = protocol["tle_inputs"]["snapshots"][capture_id]
    if base_binding["raw_sha256"] != reconstruction["base_raw_sha256"]:
        raise ValueError("latest-causal TLE reconstruction base digest drifted")
    base_bytes = Path(str(base_binding["raw_path"])).read_bytes()
    base_text = base_bytes.decode("ascii")
    base_records = {item.satellite_number: item for item in parse_element_set_records(base_text)}
    replacement = reconstruction["replacement"]
    satellite_number = int(replacement["satellite_number"])
    base_record = base_records.get(satellite_number)
    if base_record is None or _sha256_text(base_record.text) != _canonical_sha(
        replacement["base_record_sha256"], "base TLE record digest"
    ):
        raise ValueError("latest-causal TLE reconstruction base record drifted")
    replacement_path = ROOT / str(replacement["replacement_record_path"])
    replacement_text = replacement_path.read_text(encoding="ascii")
    replacement_records = parse_element_set_records(replacement_text)
    if len(replacement_records) != 1 or replacement_records[0].satellite_number != satellite_number:
        raise ValueError("latest-causal TLE replacement record identity drifted")
    newline = b"\r\n" if b"\r\n" in base_bytes else b"\n"
    base_record_bytes = base_record.text.replace("\n", newline.decode("ascii")).encode("ascii")
    replacement_record_bytes = (
        replacement_records[0].text.replace("\n", newline.decode("ascii")).encode("ascii")
    )
    if base_bytes.count(base_record_bytes) != 1:
        raise ValueError("latest-causal TLE base record is not unique")
    reconstructed_bytes = base_bytes.replace(base_record_bytes, replacement_record_bytes, 1)
    if _sha256_bytes(reconstructed_bytes) != _canonical_sha(
        reconstruction["source_raw_sha256"], "reconstructed TLE digest"
    ):
        raise ValueError("latest-causal TLE reconstruction does not match source digest")
    reconstructed = reconstructed_bytes.decode("ascii")
    if len(parse_element_set_records(reconstructed)) != int(reconstruction["catalog_object_count"]):
        raise ValueError("latest-causal reconstructed TLE object count drifted")
    return reconstructed


def _latest_tle_reconstruction_receipt() -> dict[str, Any]:
    reconstruction = _latest_tle_reconstruction_document()
    replacement = reconstruction["replacement"]
    return {
        "authority_path": str(LATEST_TLE_RECONSTRUCTION.relative_to(ROOT)),
        "authority_sha256": _sha256(LATEST_TLE_RECONSTRUCTION),
        "capture_id": reconstruction["capture_id"],
        "source_collected_at": reconstruction["source_collected_at"],
        "base_source_sha256": reconstruction["base_raw_sha256"],
        "catalog_object_count": reconstruction["catalog_object_count"],
        "replacement_norad_id": replacement["satellite_number"],
        "replacement_record_path": replacement["replacement_record_path"],
        "replacement_record_sha256": replacement["replacement_record_sha256"],
        "reconstructed_source_sha256": reconstruction["source_raw_sha256"],
        "historical_tmp_source_required_at_execution": False,
    }


def load_protocol(path: Path) -> dict[str, Any]:
    """Load and re-verify every frozen local authority before evaluation."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unsupported satellite nuisance protocol schema")
    required_root = {
        "schema",
        "authority",
        "measurement_inputs",
        "tle_inputs",
        "observer_and_geometry",
        "measurement_reduction",
        "models",
        "evaluation",
        "promotion_gates",
        "failure_policy",
    }
    if set(document) != required_root:
        raise ValueError("satellite nuisance protocol root keys drifted")
    authority = document["authority"]
    if not isinstance(authority, dict):
        raise ValueError("protocol authority is malformed")
    for field in (
        "holdout_foundation_forbidden",
        "pre_fix_forbidden",
        "newer_or_dynamic_capture_discovery_forbidden",
        "capture_substitution_forbidden",
        "protocol_freeze_precedes_candidate_evaluation",
    ):
        if authority.get(field) is not True:
            raise ValueError(f"authority field {field} must fail closed")
    policy_path = ROOT / str(authority["dataset_policy_path"])
    if _sha256(policy_path) != _canonical_sha(
        authority["dataset_policy_sha256"], "dataset policy digest"
    ):
        raise ValueError("dataset policy digest drifted")
    policy = load_doppler_dataset_policy(policy_path)
    required_ids = tuple(str(item) for item in authority["required_capture_ids"])
    if len(required_ids) != 4 or len(set(required_ids)) != len(required_ids):
        raise ValueError("retrospective capture authority must contain four unique IDs")
    allowed: set[str] = set()
    for role_name in authority["allowed_policy_roles"]:
        allowed.update(policy.role(str(role_name)).capture_ids)
    if not set(required_ids) <= allowed:
        raise ValueError("protocol contains a capture outside its allowed roles")
    if set(required_ids) & set(policy.role("holdout_foundation").capture_ids):
        raise ValueError("holdout-foundation capture entered retrospective association")
    if any(
        not policy.capture(capture_id).provenance_status.endswith("_opened")
        for capture_id in required_ids
    ):
        raise ValueError("retrospective capture authority contains unopened data")

    measurements = document["measurement_inputs"]
    if not isinstance(measurements, dict):
        raise ValueError("measurement input bindings are malformed")
    for name in ("multi_radio_frame_ledger", "long_150802_ledger"):
        binding = measurements[name]
        source = ROOT / str(binding["path"])
        if _sha256(source) != _canonical_sha(binding["sha256"], f"{name} digest"):
            raise ValueError(f"{name} digest drifted")
    frame_binding = measurements["multi_radio_frame_ledger"]
    if tuple(str(item) for item in frame_binding["capture_ids"]) != required_ids:
        raise ValueError("frame-ledger capture order drifted from frozen authority")
    primary_map = measurements["primary_capture_bundle"]
    if set(primary_map) != set(required_ids):
        raise ValueError("primary measurement bundle map drifted from frozen authority")
    if str(measurements["long_150802_ledger"]["capture_id"]) != required_ids[-1]:
        raise ValueError("long-track binding drifted from frozen authority")

    tle_inputs = document["tle_inputs"]
    if not isinstance(tle_inputs, dict):
        raise ValueError("TLE input bindings are malformed")
    _load_tle_durability_amendment(document, path)
    snapshots = tle_inputs["snapshots"]
    if set(snapshots) != set(required_ids):
        raise ValueError("TLE binding set disagrees with capture authority")
    for capture_id, binding in snapshots.items():
        tle_path = Path(str(binding["raw_path"]))
        if _sha256(tle_path) != _canonical_sha(binding["raw_sha256"], "TLE digest"):
            raise ValueError(f"TLE digest drifted for {capture_id}")
        retrieved = datetime.fromisoformat(str(binding["retrieved_at"]).replace("Z", "+00:00"))
        first = datetime.fromtimestamp(int(binding["first_measurement_utc_ns"]) / 1e9, UTC)
        if not retrieved < first:
            raise ValueError(f"TLE does not strictly predate {capture_id}")
    sensitivity = tle_inputs["source_sensitivity"][required_ids[-1]]
    collected = datetime.fromisoformat(str(sensitivity["collected_at"]).replace("Z", "+00:00"))
    first = datetime.fromtimestamp(int(sensitivity["first_measurement_utc_ns"]) / 1e9, UTC)
    if not collected < first:
        raise ValueError("latest-causal 150802 TLE sensitivity is not causal")
    _latest_causal_tle_text(document)
    return document


def _path_radio(path_id: str) -> str:
    parts = path_id.split("/")
    if len(parts) != 3 or not parts[1].startswith("radio_pluto_"):
        raise ValueError(f"malformed path identity: {path_id}")
    return parts[1]


def _measurement_track(
    rows: list[tuple[int, str, str, float, float]],
) -> tuple[MeasurementTrack, IntArray]:
    if len(rows) < 6:
        raise ValueError("measurement bundle contains too few rows")
    rows.sort(key=lambda item: (item[0], item[1]))
    path_ids = tuple(sorted({item[1] for item in rows}))
    radio_ids = tuple(sorted({item[2] for item in rows}))
    path_lookup = {value: index for index, value in enumerate(path_ids)}
    radio_lookup = {value: index for index, value in enumerate(radio_ids)}
    utc_ns = np.asarray([item[0] for item in rows], dtype=np.int64)
    reference_ns = int(np.median(utc_ns))
    track = MeasurementTrack(
        time_s=(utc_ns.astype(np.float64) - reference_ns) / 1e9,
        fit_cfo_hz=np.asarray([item[3] for item in rows], dtype=np.float64),
        response_cfo_hz=np.asarray([item[4] for item in rows], dtype=np.float64),
        path_index=np.asarray([path_lookup[item[1]] for item in rows], dtype=np.int64),
        radio_index=np.asarray([radio_lookup[item[2]] for item in rows], dtype=np.int64),
        path_ids=path_ids,
        radio_ids=radio_ids,
    )
    return track, utc_ns


def load_bound_tracks(protocol: dict[str, Any]) -> tuple[BoundTrack, ...]:
    """Load frozen rows and reduce multi-radio measurements to 20 ms medians."""

    inputs = protocol["measurement_inputs"]
    frame_binding = inputs["multi_radio_frame_ledger"]
    frame_path = ROOT / str(frame_binding["path"])
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    with gzip.open(frame_path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if (
                row.get("training_supported") is not True
                or row.get("reference_utc_ns") is None
                or row.get("normalized_even_cfo_hz") is None
            ):
                continue
            capture_id = str(row["capture_session_id"])
            path_id = str(row["path_id"])
            utc_ns = int(row["reference_utc_ns"])
            grouped[(capture_id, path_id, utc_ns // BIN_NS)].append(row)
    by_capture: dict[str, list[tuple[int, str, str, float, float]]] = defaultdict(list)
    for (capture_id, path_id, _), frame_values in grouped.items():
        binned_utc_ns = int(
            round(float(np.median([int(item["reference_utc_ns"]) for item in frame_values])))
        )
        even = float(np.median([float(item["normalized_even_cfo_hz"]) for item in frame_values]))
        odd_values = [
            float(item["normalized_odd_cfo_hz"])
            for item in frame_values
            if item.get("normalized_odd_cfo_hz") is not None
        ]
        odd = float(np.median(odd_values)) if odd_values else math.nan
        by_capture[capture_id].append((binned_utc_ns, path_id, _path_radio(path_id), even, odd))

    primary_map = inputs["primary_capture_bundle"]
    tracks: list[BoundTrack] = []
    for capture_id in frame_binding["capture_ids"]:
        track, track_utc_ns = _measurement_track(by_capture[str(capture_id)])
        primary = primary_map[str(capture_id)] == "multi_radio_frame_ledger"
        tracks.append(
            BoundTrack(
                capture_id=str(capture_id),
                bundle_id="multi-radio-frames",
                data_kind="single-frame even/odd Qin CFO",
                track=track,
                utc_ns=track_utc_ns,
                rf_frequency_hz=float(frame_binding["reference_sky_frequency_hz"]),
                primary=primary,
            )
        )

    long_binding = inputs["long_150802_ledger"]
    long_path = ROOT / str(long_binding["path"])
    long_grouped: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for line in long_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        row_utc_ns = int(long_binding["stream_first_sample_utc_ns"]) + round(
            float(row[str(long_binding["measurement_time_field"])]) * 1e9
        )
        long_grouped[row_utc_ns // BIN_NS].append(
            (row_utc_ns, float(row[str(long_binding["response_field"])]))
        )
    path_id = str(long_binding["path_id"])
    radio_id = str(long_binding["physical_radio_id"])
    long_rows: list[tuple[int, str, str, float, float]] = []
    for long_values in long_grouped.values():
        binned_utc_ns = int(round(float(np.median([item[0] for item in long_values]))))
        cfo = float(np.median([item[1] for item in long_values]))
        long_rows.append((binned_utc_ns, path_id, radio_id, cfo, cfo))
    track, track_utc_ns = _measurement_track(long_rows)
    tracks.append(
        BoundTrack(
            capture_id=str(long_binding["capture_id"]),
            bundle_id="long-direct-glrt",
            data_kind="13.8 s direct-GLRT CFO",
            track=track,
            utc_ns=track_utc_ns,
            rf_frequency_hz=float(long_binding["rf_frequency_hz"]),
            primary=True,
        )
    )
    return tuple(tracks)


def _uniform_grid(start_ns: int, stop_ns: int, spacing_s: float) -> SamplingGrid:
    if stop_ns <= start_ns:
        stop_ns = start_ns + 2
    step_ns = max(1, round(spacing_s * 1e9))
    count = max(3, math.ceil((stop_ns - start_ns) / step_ns) + 1)
    values = tuple(start_ns + index * step_ns for index in range(count))
    return SamplingGrid(values, count // 2, step_ns / 1e9)


def _exact_grid(utc_ns: IntArray) -> tuple[SamplingGrid, IntArray]:
    unique, inverse = np.unique(utc_ns, return_inverse=True)
    if unique.size < 3:
        raise ValueError("candidate prediction needs at least three unique UTC bins")
    spacing_s = float(np.median(np.diff(unique)) / 1e9)
    return (
        SamplingGrid(tuple(int(value) for value in unique), unique.size // 2, spacing_s),
        np.asarray(inverse, dtype=np.int64),
    )


def candidate_population(
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    rf_frequency_hz: float,
    observer_name: str,
) -> CandidatePopulation:
    """Build an exact horizon union and CFO bank at actual measurement UTCs."""

    observer = resolve_preset(observer_name)
    coarse_grid = _uniform_grid(int(np.min(utc_ns)), int(np.max(utc_ns)), COARSE_SPACING_S)
    coarse = observe_grid(propagate_grid(catalogue, coarse_grid), observer, coarse_grid)
    margin = MAX_ANGULAR_RATE_DEG_S * coarse_grid.spacing_s / 2.0
    plausible = coarse.usable & (np.min(coarse.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM)
    coarse_indices = np.flatnonzero(plausible & (np.max(coarse.elevation_deg, axis=1) > -margin))
    exact_grid, inverse = _exact_grid(utc_ns)
    exact = observe_grid(
        propagate_grid(catalogue, exact_grid, indices=coarse_indices.tolist()),
        observer,
        exact_grid,
    )
    exact_plausible = exact.usable & (
        np.min(exact.altitude_km, axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    )
    rows = np.flatnonzero(exact_plausible & (np.max(exact.elevation_deg, axis=1) >= 0.0))
    indices = np.asarray(coarse_indices[rows], dtype=np.int64)
    prediction_unique = np.asarray(
        doppler_shift_hz(rf_frequency_hz, exact.range_rate_km_s[rows]),
        dtype=np.float64,
    )
    norad = np.asarray(
        [catalogue.satellite_numbers[int(index)] for index in indices], dtype=np.int64
    )
    return CandidatePopulation(
        catalogue_indices=indices,
        norad_ids=norad,
        names=tuple(catalogue.names[int(index)] for index in indices),
        prediction_hz=prediction_unique[:, inverse],
        minimum_elevation_deg=np.min(exact.elevation_deg[rows], axis=1),
        maximum_elevation_deg=np.max(exact.elevation_deg[rows], axis=1),
        coarse_candidate_count=int(coarse_indices.size),
    )


def _fit_hierarchy(
    track: MeasurementTrack,
    prediction: FloatArray,
    training: BoolArray,
    evaluation: BoolArray,
    model: dict[str, Any],
) -> CandidateFitBank:
    return fit_hierarchical_candidates(
        track,
        prediction,
        training,
        evaluation,
        measurement_scale_hz=float(model["measurement_scale_hz"]),
        rate_prior_sigma_hz_s=float(model["rate_departure_prior_sigma_hz_s"]),
        maximum_rate_hz_s=float(model["rate_departure_hard_bound_hz_s"]),
    )


def _rank_rows(population: CandidatePopulation, fit: CandidateFitBank) -> list[dict[str, Any]]:
    order = np.lexsort((population.norad_ids, fit.penalized_training_rms_hz))
    rows = []
    for rank, row in enumerate(order, start=1):
        rows.append(
            {
                "rank": rank,
                "catalogue_index": int(population.catalogue_indices[row]),
                "norad_id": int(population.norad_ids[row]),
                "name": population.names[row],
                "penalized_training_rms_hz": float(fit.penalized_training_rms_hz[row]),
                "training_rms_hz": float(fit.training_rms_hz[row]),
                "heldout_rms_hz": float(fit.evaluation_rms_hz[row]),
                "full_response_rms_hz": float(fit.full_response_rms_hz[row]),
                "path_offsets_hz": [float(value) for value in fit.path_offsets_hz[row]],
                "radio_rate_departures_hz_s": [
                    float(value) for value in fit.radio_rate_departures_hz_s[row]
                ],
                "minimum_elevation_deg": float(population.minimum_elevation_deg[row]),
                "maximum_elevation_deg": float(population.maximum_elevation_deg[row]),
            }
        )
    return rows


def _minimum_fit_score(
    bound: BoundTrack,
    catalogue: ElementSetCatalogue,
    utc_ns: IntArray,
    observer: str,
    training: BoolArray,
    evaluation: BoolArray,
    model: dict[str, Any],
) -> tuple[float, int, int]:
    population = candidate_population(catalogue, utc_ns, bound.rf_frequency_hz, observer)
    fit = _fit_hierarchy(bound.track, population.prediction_hz, training, evaluation, model)
    selected = int(np.argmin(fit.penalized_training_rms_hz))
    return (
        float(fit.penalized_training_rms_hz[selected]),
        int(population.norad_ids[selected]),
        int(population.norad_ids.size),
    )


def _grid_value_is_interior(value: float, minimum: float, maximum: float, step: float) -> bool:
    return not math.isclose(value, minimum, abs_tol=step / 2.0) and not math.isclose(
        value, maximum, abs_tol=step / 2.0
    )


def _support_disposition(
    bound: BoundTrack,
    reduction: dict[str, Any],
) -> tuple[bool, list[dict[str, int | str]]]:
    track = bound.track
    training = chronological_mask(track.time_s, float(reduction["chronological_training_fraction"]))
    evaluation = ~training & np.isfinite(track.response_cfo_hz)
    support_by_path: list[dict[str, int | str]] = []
    for path, path_id in enumerate(track.path_ids):
        support_by_path.append(
            {
                "path_id": path_id,
                "physical_radio_id": track.radio_ids[
                    int(track.radio_index[np.flatnonzero(track.path_index == path)[0]])
                ],
                "training_bin_count": int(np.count_nonzero(training & (track.path_index == path))),
                "evaluation_bin_count": int(
                    np.count_nonzero(evaluation & (track.path_index == path))
                ),
            }
        )
    if bound.data_kind.startswith("single-frame"):
        support_pass = (
            len(track.path_ids) >= int(reduction["multi_radio_minimum_paths"])
            and len(track.radio_ids) >= int(reduction["multi_radio_minimum_physical_radios"])
            and all(
                int(row["training_bin_count"])
                >= int(reduction["multi_radio_minimum_training_bins_per_path"])
                and int(row["evaluation_bin_count"])
                >= int(reduction["multi_radio_minimum_evaluation_bins_per_path"])
                for row in support_by_path
            )
        )
    else:
        support_pass = track.time_s.size >= int(reduction["long_track_minimum_total_bins"])
    return support_pass, support_by_path


def _input_provenance_gates(
    bound: BoundTrack,
    protocol: dict[str, Any],
) -> dict[str, bool]:
    tle_binding = protocol["tle_inputs"]["snapshots"][bound.capture_id]
    tle_path = Path(str(tle_binding["raw_path"]))
    retrieved = datetime.fromisoformat(str(tle_binding["retrieved_at"]).replace("Z", "+00:00"))
    actual_first = datetime.fromtimestamp(int(np.min(bound.utc_ns)) / 1e9, UTC)
    try:
        resolve_preset(str(protocol["observer_and_geometry"]["observer_preset"]))
        observer_resolves = True
    except KeyError:
        observer_resolves = False
    path_identity_valid = (
        len(set(bound.track.path_ids)) == len(bound.track.path_ids)
        and len(set(bound.track.radio_ids)) == len(bound.track.radio_ids)
        and all(
            _path_radio(path_id)
            == bound.track.radio_ids[
                int(
                    bound.track.radio_index[np.flatnonzero(bound.track.path_index == path_index)[0]]
                )
            ]
            for path_index, path_id in enumerate(bound.track.path_ids)
        )
    )
    return {
        "tle_digest_verified_and_strictly_pre_measurement": (
            _sha256(tle_path) == str(tle_binding["raw_sha256"]) and retrieved < actual_first
        ),
        "observer_preset_binding_resolves": observer_resolves,
        "rf_frequency_finite_and_positive": (
            math.isfinite(bound.rf_frequency_hz) and bound.rf_frequency_hz > 0.0
        ),
        "path_and_radio_identity_valid": path_identity_valid,
    }


def _candidate_fit_bank_is_finite(fit: CandidateFitBank) -> bool:
    return all(
        bool(np.all(np.isfinite(values)))
        for values in (
            fit.penalized_training_rms_hz,
            fit.training_rms_hz,
            fit.evaluation_rms_hz,
            fit.full_response_rms_hz,
            fit.path_offsets_hz,
            fit.radio_rate_departures_hz_s,
        )
    )


def _winner_nuisance_is_interior(winner: dict[str, Any], maximum_rate_hz_s: float) -> bool:
    rates = [float(value) for value in winner["radio_rate_departures_hz_s"]]
    return bool(rates) and all(abs(value) < maximum_rate_hz_s for value in rates)


def evaluate_bundle(
    bound: BoundTrack,
    catalogue: ElementSetCatalogue,
    protocol: dict[str, Any],
    *,
    run_controls: bool,
) -> tuple[dict[str, Any], CandidatePopulation, CandidateFitBank]:
    """Score one fixed bundle under every preregistered model and control."""

    reduction = protocol["measurement_reduction"]
    model = protocol["models"]["primary_hierarchical_receiver_nuisance"]
    evaluation_config = protocol["evaluation"]
    observer = str(protocol["observer_and_geometry"]["observer_preset"])
    track = bound.track
    training = chronological_mask(track.time_s, float(reduction["chronological_training_fraction"]))
    response_available = np.isfinite(track.response_cfo_hz)
    evaluation = ~training & response_available
    support_pass, support_by_path = _support_disposition(bound, reduction)
    if not support_pass:
        raise ValueError(f"frozen support gate failed for {bound.capture_id}/{bound.bundle_id}")
    input_provenance_gates = _input_provenance_gates(bound, protocol)
    if not all(input_provenance_gates.values()):
        raise ValueError(f"input provenance gate failed for {bound.capture_id}/{bound.bundle_id}")

    population = candidate_population(
        catalogue,
        bound.utc_ns,
        bound.rf_frequency_hz,
        observer,
    )
    if population.norad_ids.size < 2:
        raise ValueError("candidate population has fewer than two visible Starlinks")
    baseline = fit_offset_candidates(track, population.prediction_hz, training, evaluation)
    hierarchy = _fit_hierarchy(track, population.prediction_hz, training, evaluation, model)
    baseline_rows = _rank_rows(population, baseline)
    hierarchy_rows = _rank_rows(population, hierarchy)
    winner = hierarchy_rows[0]
    runner = hierarchy_rows[1]
    linear_null = fit_radio_polynomial_null(track, training, evaluation, degree=1)
    quadratic_null = fit_radio_polynomial_null(track, training, evaluation, degree=2)
    affine_diagnostic = fit_unregularized_common_affine_candidates(
        track,
        population.prediction_hz,
        training,
        evaluation,
    )
    winner_index = int(np.flatnonzero(population.norad_ids == int(winner["norad_id"]))[0])
    independent_path_linear = fit_independent_path_linear_null(
        track,
        training,
        evaluation,
    )

    rolling = []
    for item in evaluation_config["rolling_origins"]:
        train_mask = chronological_mask(track.time_s, float(item["training_stop_fraction"]))
        response_mask = (
            chronological_block_mask(
                track.time_s,
                float(item["training_stop_fraction"]),
                float(item["evaluation_stop_fraction"]),
            )
            & response_available
        )
        fit = _fit_hierarchy(track, population.prediction_hz, train_mask, response_mask, model)
        selected = int(np.argmin(fit.penalized_training_rms_hz))
        rolling.append(
            {
                **item,
                "winner_norad_id": int(population.norad_ids[selected]),
                "winner_penalized_training_rms_hz": float(fit.penalized_training_rms_hz[selected]),
                "winner_heldout_rms_hz": float(fit.evaluation_rms_hz[selected]),
            }
        )

    time_control = protocol["models"]["bounded_clock_time_sensitivity"]
    shifts = np.arange(
        float(time_control["minimum_shift_s"]),
        float(time_control["maximum_shift_s"]) + 0.5 * float(time_control["step_s"]),
        float(time_control["step_s"]),
    )
    time_rows = []
    for shift_s in shifts:
        shifted_utc = bound.utc_ns + round(float(shift_s) * 1e9)
        shifted_grid, inverse = _exact_grid(shifted_utc)
        observed = observe_grid(
            propagate_grid(
                catalogue,
                shifted_grid,
                indices=population.catalogue_indices.tolist(),
            ),
            resolve_preset(observer),
            shifted_grid,
        )
        prediction = np.asarray(
            doppler_shift_hz(bound.rf_frequency_hz, observed.range_rate_km_s),
            dtype=np.float64,
        )[:, inverse]
        fit = _fit_hierarchy(track, prediction, training, evaluation, model)
        selected = int(np.argmin(fit.penalized_training_rms_hz))
        time_rows.append(
            {
                "shift_s": float(shift_s),
                "winner_norad_id": int(population.norad_ids[selected]),
                "winner_penalized_training_rms_hz": float(fit.penalized_training_rms_hz[selected]),
                "winner_heldout_rms_hz": float(fit.evaluation_rms_hz[selected]),
            }
        )
    best_time = min(
        time_rows,
        key=lambda item: (
            item["winner_penalized_training_rms_hz"],
            abs(item["shift_s"]),
            item["shift_s"],
        ),
    )

    wrong_time_rows = []
    permutation_rows = []
    wrong_time_p: float | None = None
    permutation_p: float | None = None
    if run_controls:
        for offset_s in evaluation_config["wrong_time_offsets_s"]:
            score, norad, candidate_count = _minimum_fit_score(
                bound,
                catalogue,
                bound.utc_ns + int(offset_s) * 1_000_000_000,
                observer,
                training,
                evaluation,
                model,
            )
            wrong_time_rows.append(
                {
                    "time_offset_s": int(offset_s),
                    "candidate_count": candidate_count,
                    "winner_norad_id": norad,
                    "best_penalized_training_rms_hz": score,
                }
            )
        true_score = float(winner["penalized_training_rms_hz"])
        wrong_time_p = (
            1 + sum(row["best_penalized_training_rms_hz"] <= true_score for row in wrong_time_rows)
        ) / (1 + len(wrong_time_rows))

        rng = np.random.default_rng(int(evaluation_config["permutation_seed"]))
        for index in range(int(evaluation_config["permutation_count"])):
            permuted = permute_fit_response_within_paths(track, training, rng)
            fit = _fit_hierarchy(
                permuted,
                population.prediction_hz,
                training,
                evaluation,
                model,
            )
            selected = int(np.argmin(fit.penalized_training_rms_hz))
            permutation_rows.append(
                {
                    "permutation_index": index,
                    "winner_norad_id": int(population.norad_ids[selected]),
                    "best_penalized_training_rms_hz": float(
                        fit.penalized_training_rms_hz[selected]
                    ),
                }
            )
        permutation_p = (
            1 + sum(row["best_penalized_training_rms_hz"] <= true_score for row in permutation_rows)
        ) / (1 + len(permutation_rows))

    gate_values = {
        "heldout_rms_le_100_hz": float(winner["heldout_rms_hz"]) <= 100.0,
        "quadratic_advantage_ge_20_hz": (
            quadratic_null.evaluation_rms_hz - float(winner["heldout_rms_hz"])
        )
        >= 20.0,
        "training_runner_margin_ge_100_hz": (
            float(runner["penalized_training_rms_hz"]) - float(winner["penalized_training_rms_hz"])
        )
        >= 100.0,
        "heldout_runner_margin_ge_50_hz": (
            float(runner["heldout_rms_hz"]) - float(winner["heldout_rms_hz"])
        )
        >= 50.0,
        "baseline_and_hierarchy_winner_agree": (
            int(baseline_rows[0]["norad_id"]) == int(winner["norad_id"])
        ),
        "rolling_winner_stable": all(
            int(item["winner_norad_id"]) == int(winner["norad_id"]) for item in rolling
        ),
        "bounded_time_winner_stable_and_interior": (
            int(best_time["winner_norad_id"]) == int(winner["norad_id"])
            and _grid_value_is_interior(
                float(best_time["shift_s"]),
                float(time_control["minimum_shift_s"]),
                float(time_control["maximum_shift_s"]),
                float(time_control["step_s"]),
            )
        ),
        "wrong_time_fwer_le_0_05": wrong_time_p is not None and wrong_time_p <= 0.05,
        "permutation_p_le_0_05": permutation_p is not None and permutation_p <= 0.05,
    }
    candidate_evidence_pass = all(gate_values.values())
    baseline_recovered_track = _candidate_fit_bank_is_finite(baseline)
    primary_recovered_track = _candidate_fit_bank_is_finite(hierarchy)
    secure_provenance_gates = {
        **input_provenance_gates,
        "winner_nuisance_rate_strictly_interior": _winner_nuisance_is_interior(
            winner,
            float(model["rate_departure_hard_bound_hz_s"]),
        ),
    }
    result = {
        "capture_id": bound.capture_id,
        "bundle_id": bound.bundle_id,
        "data_kind": bound.data_kind,
        "primary": bound.primary,
        "start_utc_ns": int(np.min(bound.utc_ns)),
        "stop_utc_ns": int(np.max(bound.utc_ns)),
        "start_utc": _iso_utc(int(np.min(bound.utc_ns))),
        "stop_utc": _iso_utc(int(np.max(bound.utc_ns))),
        "duration_s": float((np.max(bound.utc_ns) - np.min(bound.utc_ns)) / 1e9),
        "measurement_bin_count": int(track.time_s.size),
        "path_count": len(track.path_ids),
        "physical_radio_count": len(track.radio_ids),
        "support_by_path": support_by_path,
        "support_gate_pass": support_pass,
        "coarse_candidate_count": population.coarse_candidate_count,
        "visible_candidate_count": int(population.norad_ids.size),
        "baseline_top10": baseline_rows[:10],
        "full_baseline_ranking": baseline_rows,
        "hierarchical_top10": hierarchy_rows[:10],
        "full_hierarchical_ranking": hierarchy_rows,
        "linear_null": asdict(linear_null),
        "quadratic_null": asdict(quadratic_null),
        "diagnostic_overfit_models": {
            "tle_plus_unregularized_common_affine_departure": {
                "candidate_norad_id": int(winner["norad_id"]),
                "candidate_name": str(winner["name"]),
                "training_rms_hz": float(affine_diagnostic.training_rms_hz[winner_index]),
                "heldout_rms_hz": float(affine_diagnostic.evaluation_rms_hz[winner_index]),
                "full_response_rms_hz": float(affine_diagnostic.full_response_rms_hz[winner_index]),
                "path_offsets_hz": [
                    float(value) for value in affine_diagnostic.path_offsets_hz[winner_index]
                ],
                "common_rate_departure_hz_s": float(
                    affine_diagnostic.common_rate_departure_hz_s[winner_index]
                ),
                "promotion_gate": False,
            },
            "independent_path_linear_null": {
                **asdict(independent_path_linear),
                "promotion_gate": False,
            },
        },
        "rolling_origins": rolling,
        "bounded_time_sensitivity": time_rows,
        "bounded_time_best": best_time,
        "wrong_time_controls": wrong_time_rows,
        "wrong_time_familywise_p": wrong_time_p,
        "permutation_controls": permutation_rows,
        "permutation_p": permutation_p,
        "candidate_evidence_gates": gate_values,
        "candidate_evidence_pass": candidate_evidence_pass,
        "baseline_recovered_track": baseline_recovered_track,
        "primary_recovered_track": primary_recovered_track,
        "recovered_track": primary_recovered_track,
        "secure_provenance_gates": secure_provenance_gates,
        "secure_provenance_pass": all(secure_provenance_gates.values()),
    }
    return result, population, hierarchy


def latest_tle_sensitivity(
    bound: BoundTrack,
    primary_catalogue: ElementSetCatalogue,
    latest_catalogue: ElementSetCatalogue,
    primary_result: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Fail if the durable and latest-causal 150802 visible results differ."""

    observer = str(protocol["observer_and_geometry"]["observer_preset"])
    reduction = protocol["measurement_reduction"]
    model = protocol["models"]["primary_hierarchical_receiver_nuisance"]
    training = chronological_mask(
        bound.track.time_s, float(reduction["chronological_training_fraction"])
    )
    evaluation = ~training & np.isfinite(bound.track.response_cfo_hz)
    primary_population = candidate_population(
        primary_catalogue, bound.utc_ns, bound.rf_frequency_hz, observer
    )
    latest_population = candidate_population(
        latest_catalogue, bound.utc_ns, bound.rf_frequency_hz, observer
    )
    primary_ids = [int(value) for value in primary_population.norad_ids]
    latest_ids = [int(value) for value in latest_population.norad_ids]
    visible_equal = primary_ids == latest_ids
    if not visible_equal:
        raise ValueError("latest-causal TLE changes the 150802 visible population")
    primary_fit = _fit_hierarchy(
        bound.track, primary_population.prediction_hz, training, evaluation, model
    )
    latest_fit = _fit_hierarchy(
        bound.track, latest_population.prediction_hz, training, evaluation, model
    )
    hierarchy_training_difference = float(
        np.max(np.abs(primary_fit.penalized_training_rms_hz - latest_fit.penalized_training_rms_hz))
    )
    hierarchy_heldout_difference = float(
        np.max(np.abs(primary_fit.evaluation_rms_hz - latest_fit.evaluation_rms_hz))
    )
    primary_baseline = fit_offset_candidates(
        bound.track, primary_population.prediction_hz, training, evaluation
    )
    latest_baseline = fit_offset_candidates(
        bound.track, latest_population.prediction_hz, training, evaluation
    )
    baseline_training_difference = float(
        np.max(
            np.abs(
                primary_baseline.penalized_training_rms_hz
                - latest_baseline.penalized_training_rms_hz
            )
        )
    )
    baseline_heldout_difference = float(
        np.max(np.abs(primary_baseline.evaluation_rms_hz - latest_baseline.evaluation_rms_hz))
    )
    primary_order = np.lexsort(
        (primary_population.norad_ids, primary_fit.penalized_training_rms_hz)
    )
    latest_order = np.lexsort((latest_population.norad_ids, latest_fit.penalized_training_rms_hz))
    hierarchy_ranking_equal = np.array_equal(
        primary_population.norad_ids[primary_order], latest_population.norad_ids[latest_order]
    )
    primary_baseline_order = np.lexsort(
        (primary_population.norad_ids, primary_baseline.penalized_training_rms_hz)
    )
    latest_baseline_order = np.lexsort(
        (latest_population.norad_ids, latest_baseline.penalized_training_rms_hz)
    )
    baseline_ranking_equal = np.array_equal(
        primary_population.norad_ids[primary_baseline_order],
        latest_population.norad_ids[latest_baseline_order],
    )
    ranking_equal = hierarchy_ranking_equal and baseline_ranking_equal
    metric_equal = all(
        value <= 1e-9
        for value in (
            hierarchy_training_difference,
            hierarchy_heldout_difference,
            baseline_training_difference,
            baseline_heldout_difference,
        )
    )
    expected_winner = int(primary_result["hierarchical_top10"][0]["norad_id"])
    latest_winner = int(latest_population.norad_ids[latest_order[0]])
    if not ranking_equal or not metric_equal or latest_winner != expected_winner:
        raise ValueError("latest-causal TLE changes a 150802 ranking or metric")
    return {
        "visible_population_equal": visible_equal,
        "visible_candidate_count": len(primary_ids),
        "full_ranking_equal": ranking_equal,
        "hierarchical_full_ranking_equal": hierarchy_ranking_equal,
        "baseline_full_ranking_equal": baseline_ranking_equal,
        "maximum_penalized_training_rms_difference_hz": hierarchy_training_difference,
        "maximum_heldout_rms_difference_hz": hierarchy_heldout_difference,
        "maximum_baseline_training_rms_difference_hz": baseline_training_difference,
        "maximum_baseline_heldout_rms_difference_hz": baseline_heldout_difference,
        "winner_norad_id": latest_winner,
        "all_required_metrics_identical": metric_equal,
    }


def _render_results(output_root: Path, evidence: dict[str, Any]) -> list[Path]:
    primary = [item for item in evidence["bundle_results"] if item["primary"]]
    output_root.mkdir(parents=True, exist_ok=True)
    ranking_path = output_root / "candidate-ranking-and-nulls.png"
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    for ax, result in zip(axes.flat, primary, strict=True):
        rows = result["hierarchical_top10"]
        labels = [str(row["norad_id"]) for row in rows]
        values = [row["heldout_rms_hz"] for row in rows]
        ax.bar(np.arange(len(rows)), values, color="tab:blue", alpha=0.75)
        ax.axhline(
            result["quadratic_null"]["evaluation_rms_hz"],
            color="tab:orange",
            linestyle="--",
            label="quadratic radio null",
        )
        ax.axhline(100.0, color="black", linestyle=":", label="100 Hz identity gate")
        ax.set_xticks(np.arange(len(rows)), labels, rotation=45, ha="right")
        ax.set_ylabel("Chronological held-out RMS (Hz)")
        ax.set_title(f"{result['capture_id'][4:19]} · {result['data_kind']}")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Full-catalog training winners scored on future CFO", fontsize=16)
    fig.savefig(ranking_path, dpi=180)
    plt.close(fig)

    controls_path = output_root / "baseline-hierarchy-and-controls.png"
    labels = [item["capture_id"][13:19] for item in primary]
    baseline = [item["baseline_top10"][0]["heldout_rms_hz"] for item in primary]
    hierarchy = [item["hierarchical_top10"][0]["heldout_rms_hz"] for item in primary]
    quadratic = [item["quadratic_null"]["evaluation_rms_hz"] for item in primary]
    affine = [
        item["diagnostic_overfit_models"]["tle_plus_unregularized_common_affine_departure"][
            "heldout_rms_hz"
        ]
        for item in primary
    ]
    independent = [
        item["diagnostic_overfit_models"]["independent_path_linear_null"]["evaluation_rms_hz"]
        for item in primary
    ]
    wrong = [item["wrong_time_familywise_p"] for item in primary]
    permutation = [item["permutation_p"] for item in primary]
    x = np.arange(len(primary))
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    width = 0.16
    axes[0].bar(x - 2 * width, baseline, width, label="fixed-time offset-only")
    axes[0].bar(x - width, hierarchy, width, label="hierarchical receiver nuisance")
    axes[0].bar(x, quadratic, width, label="quadratic radio null")
    axes[0].bar(
        x + width,
        affine,
        width,
        label="TLE + unregularized common affine (diagnostic)",
    )
    axes[0].bar(
        x + 2 * width,
        independent,
        width,
        label="independent path lines (diagnostic)",
    )
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Held-out RMS (Hz)")
    axes[0].set_title("Prediction, not in-sample completion")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].bar(x - width / 2, wrong, width, label="40-field wrong-time FWER")
    axes[1].bar(x + width / 2, permutation, width, label="20-permutation p")
    axes[1].axhline(0.05, color="black", linestyle="--", label="promotion gate")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_ylabel("Empirical p")
    axes[1].set_title("Candidate multiplicity and temporal-structure controls")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.suptitle("Retrospective association baseline and nuisance controls", fontsize=16)
    fig.savefig(controls_path, dpi=180)
    plt.close(fig)

    recovery_path = output_root / "track-recovery-and-gates.png"
    gate_names = list(primary[0]["candidate_evidence_gates"])
    gate_matrix = np.asarray(
        [[bool(item["candidate_evidence_gates"][name]) for name in gate_names] for item in primary],
        dtype=float,
    )
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5), constrained_layout=True)
    counts = evidence["aggregate"]
    axes[0].bar(
        ["baseline\nrecovered", "hierarchy\nrecovered", "candidate\nevidence", "secure\nNORAD"],
        [
            counts["baseline_recovered_track_count"],
            counts["primary_recovered_track_count"],
            counts["candidate_evidence_track_count"],
            counts["secure_norad_count"],
        ],
        color=["0.55", "tab:blue", "tab:orange", "tab:green"],
    )
    axes[0].set_ylim(0, max(4.5, counts["primary_recovered_track_count"] + 0.5))
    axes[0].set_ylabel("Count")
    axes[0].set_title("A ranked track is not a secure identity")
    axes[0].grid(axis="y", alpha=0.25)
    image = axes[1].imshow(gate_matrix, cmap="RdYlGn", vmin=0.0, vmax=1.0, aspect="auto")
    axes[1].set_yticks(np.arange(len(primary)), labels)
    short_names = [
        "RMS",
        "beats quad",
        "train margin",
        "future margin",
        "nuisance stable",
        "rolling stable",
        "time stable",
        "wrong-time",
        "permutation",
    ]
    axes[1].set_xticks(np.arange(len(gate_names)), short_names, rotation=45, ha="right")
    axes[1].set_title("Complete candidate-evidence gate ledger")
    for row in range(gate_matrix.shape[0]):
        for column in range(gate_matrix.shape[1]):
            axes[1].text(
                column,
                row,
                "PASS" if gate_matrix[row, column] else "FAIL",
                ha="center",
                va="center",
                fontsize=7,
            )
    fig.colorbar(image, ax=axes[1], ticks=[0, 1], label="gate result")
    fig.suptitle("Track recovery versus secure Starlink identity", fontsize=16)
    fig.savefig(recovery_path, dpi=180)
    plt.close(fig)
    return [ranking_path, controls_path, recovery_path]


def run(protocol_path: Path, output_root: Path) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    tracks = load_bound_tracks(protocol)
    tle_bindings = protocol["tle_inputs"]["snapshots"]
    catalogue_cache: dict[str, ElementSetCatalogue] = {}
    text_cache: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    populations: dict[tuple[str, str], CandidatePopulation] = {}
    fits: dict[tuple[str, str], CandidateFitBank] = {}
    for bound in tracks:
        binding = tle_bindings[bound.capture_id]
        digest = str(binding["raw_sha256"])
        if digest not in catalogue_cache:
            text = Path(str(binding["raw_path"])).read_text(encoding="ascii")
            text_cache[digest] = text
            catalogue_cache[digest] = parse_element_sets(text)
            if len(catalogue_cache[digest]) != int(binding["catalog_object_count"]):
                raise ValueError(f"TLE object count drifted for {bound.capture_id}")
        support_pass, support_by_path = _support_disposition(
            bound, protocol["measurement_reduction"]
        )
        if not support_pass and not bound.primary:
            results.append(
                {
                    "capture_id": bound.capture_id,
                    "bundle_id": bound.bundle_id,
                    "data_kind": bound.data_kind,
                    "primary": False,
                    "measurement_bin_count": int(bound.track.time_s.size),
                    "path_count": len(bound.track.path_ids),
                    "physical_radio_count": len(bound.track.radio_ids),
                    "support_by_path": support_by_path,
                    "support_gate_pass": False,
                    "baseline_recovered_track": False,
                    "primary_recovered_track": False,
                    "recovered_track": False,
                    "candidate_evidence_pass": False,
                    "secure_provenance_pass": False,
                    "secure_capture_pass": False,
                    "disposition": "diagnostic bundle failed frozen primary support minima",
                }
            )
            continue
        result, population, fit = evaluate_bundle(
            bound,
            catalogue_cache[digest],
            protocol,
            run_controls=bound.primary,
        )
        results.append(result)
        populations[(bound.capture_id, bound.bundle_id)] = population
        fits[(bound.capture_id, bound.bundle_id)] = fit

    primary_results: list[dict[str, Any]] = [item for item in results if item["primary"]]
    primary_by_capture = {item["capture_id"]: item for item in primary_results}
    long_bound = next(
        item
        for item in tracks
        if item.capture_id == "cap-20260825T150802-473cb5bbcbd6"
        and item.bundle_id == "long-direct-glrt"
    )
    primary_binding = tle_bindings[long_bound.capture_id]
    primary_digest = str(primary_binding["raw_sha256"])
    latest_text = _latest_causal_tle_text(protocol)
    latest_catalogue = parse_element_sets(latest_text)
    if len(latest_catalogue) != int(
        protocol["tle_inputs"]["source_sensitivity"][long_bound.capture_id]["catalog_object_count"]
    ):
        raise ValueError("latest-causal reconstructed TLE object count drifted")
    sensitivity = latest_tle_sensitivity(
        long_bound,
        catalogue_cache[primary_digest],
        latest_catalogue,
        primary_by_capture[long_bound.capture_id],
        protocol,
    )
    primary_records = {
        item.satellite_number: item.text
        for item in parse_element_set_records(text_cache[primary_digest])
    }
    latest_records = {
        item.satellite_number: item.text for item in parse_element_set_records(latest_text)
    }
    changed = sorted(
        item
        for item in set(primary_records) | set(latest_records)
        if primary_records.get(item) != latest_records.get(item)
    )
    visible_ids = set(
        int(value) for value in populations[(long_bound.capture_id, long_bound.bundle_id)].norad_ids
    )
    sensitivity["changed_catalogue_norad_ids"] = changed
    sensitivity["changed_visible_norad_ids"] = sorted(visible_ids & set(changed))
    if sensitivity["changed_visible_norad_ids"]:
        raise ValueError("latest-causal TLE changed a visible 150802 element record")
    long_result = primary_by_capture[long_bound.capture_id]
    long_result["secure_provenance_gates"]["latest_causal_tle_source_sensitivity_pass"] = bool(
        sensitivity["all_required_metrics_identical"]
    )
    long_result["secure_provenance_pass"] = all(long_result["secure_provenance_gates"].values())

    passing_by_norad: dict[int, set[str]] = defaultdict(set)
    for result in primary_results:
        result["secure_capture_pass"] = bool(
            result["primary_recovered_track"]
            and result["candidate_evidence_pass"]
            and result["secure_provenance_pass"]
        )
        if result["secure_capture_pass"]:
            passing_by_norad[int(result["hierarchical_top10"][0]["norad_id"])].add(
                str(result["capture_id"])
            )
    secure = sorted(norad for norad, captures in passing_by_norad.items() if len(captures) >= 2)
    recurrence = []
    all_winners = sorted(
        {int(item["hierarchical_top10"][0]["norad_id"]) for item in primary_results}
    )
    for norad in all_winners:
        appearances = [
            {
                "capture_id": item["capture_id"],
                "candidate_evidence_pass": item["candidate_evidence_pass"],
                "secure_provenance_pass": item["secure_provenance_pass"],
                "secure_capture_pass": item["secure_capture_pass"],
            }
            for item in primary_results
            if int(item["hierarchical_top10"][0]["norad_id"]) == norad
        ]
        recurrence.append(
            {
                "norad_id": norad,
                "primary_capture_appearances": appearances,
                "independent_capture_count": len(appearances),
                "passing_capture_count": sum(
                    bool(item["secure_capture_pass"]) for item in appearances
                ),
                "secure_norad": norad in secure,
            }
        )

    baseline_future_rms = np.asarray(
        [float(item["baseline_top10"][0]["heldout_rms_hz"]) for item in primary_results],
        dtype=np.float64,
    )
    hierarchy_future_rms = np.asarray(
        [float(item["hierarchical_top10"][0]["heldout_rms_hz"]) for item in primary_results],
        dtype=np.float64,
    )
    baseline_equal_capture_rms = float(np.sqrt(np.mean(baseline_future_rms**2)))
    hierarchy_equal_capture_rms = float(np.sqrt(np.mean(hierarchy_future_rms**2)))

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "implementation": {
            "repository_head_at_execution": _git_head(),
            "runner_path": str(Path(__file__).resolve().relative_to(ROOT)),
            "runner_sha256": _sha256(Path(__file__).resolve()),
            "core_path": "src/leo/analysis/research/satellite_nuisance_association.py",
            "core_sha256": _sha256(
                ROOT / "src/leo/analysis/research/satellite_nuisance_association.py"
            ),
        },
        "protocol": {
            "path": str(protocol_path.relative_to(ROOT)),
            "sha256": _sha256(protocol_path),
        },
        "source_provenance": {
            "dataset_policy_sha256": protocol["authority"]["dataset_policy_sha256"],
            "measurement_inputs": protocol["measurement_inputs"],
            "tle_inputs": protocol["tle_inputs"],
            "latest_tle_sensitivity_durable_reconstruction": (_latest_tle_reconstruction_receipt()),
            "observer": protocol["observer_and_geometry"],
            "mixed_estimator_cohort": True,
            "new_rf_collected": False,
            "holdout_foundation_opened": False,
        },
        "execution_dispositions": [
            {
                "stage": "first bounded runner attempt",
                "outcome": "stopped before artifact publication at the preregistered "
                "150802 frame-diagnostic support gate",
                "correction": "retain that diagnostic as non-evaluable; keep 30/20 minima, "
                "all four primary inputs, all candidate gates, and all controls unchanged",
                "path_substitution_or_threshold_change": False,
            },
            {
                "stage": "post-outcome bounded-time endpoint audit",
                "implementation_commit": "2ec8c62c55607dc04418675147ebaa87540ea3fe",
                "outcome": "the positive 0.25 s NumPy endpoint serialized as "
                "0.2499999999999999 and a raw strict inequality initially treated it "
                "as interior for 065355 and 130425",
                "correction": "classify a grid point within half a frozen step of either "
                "endpoint as a boundary, as required by the frozen fail-closed policy",
                "candidate_gate_definition_or_threshold_change": False,
                "individual_gate_ledger_change": "bounded-time gate changed from pass to "
                "fail for 065355 and 130425",
                "candidate_evidence_or_secure_count_change": False,
            },
        ],
        "bundle_results": results,
        "latest_causal_150802_tle_sensitivity": sensitivity,
        "recurrence": recurrence,
        "aggregate": {
            "unique_primary_capture_count": len(primary_results),
            "diagnostic_bundle_count": len(results) - len(primary_results),
            "baseline_recovered_track_count": sum(
                bool(item["baseline_recovered_track"]) for item in primary_results
            ),
            "primary_recovered_track_count": sum(
                bool(item["primary_recovered_track"]) for item in primary_results
            ),
            "candidate_evidence_track_count": sum(
                bool(item["candidate_evidence_pass"]) for item in primary_results
            ),
            "secure_norad_ids": secure,
            "secure_norad_count": len(secure),
            "baseline_unique_winner_count": len(
                {int(item["baseline_top10"][0]["norad_id"]) for item in primary_results}
            ),
            "primary_unique_winner_count": len(
                {int(item["hierarchical_top10"][0]["norad_id"]) for item in primary_results}
            ),
            "baseline_equal_capture_future_rms_hz": baseline_equal_capture_rms,
            "hierarchy_equal_capture_future_rms_hz": hierarchy_equal_capture_rms,
            "hierarchy_to_baseline_future_rms_ratio": (
                hierarchy_equal_capture_rms / baseline_equal_capture_rms
            ),
            "hierarchy_future_rms_win_count": int(
                np.count_nonzero(hierarchy_future_rms < baseline_future_rms)
            ),
        },
        "interpretation_limits": [
            "The cohort was already opened; upstream branch selection is not a blind "
            "acquisition test.",
            "Three primary tracks use single-frame even/odd Qin CFO; 150802 uses a "
            "direct-GLRT long arc.",
            "The catalogue is Starlink-only and geometry is conditional on a reviewed site preset.",
            "Receiver rate departures are nuisance parameters, not clock-drift or "
            "physical truth measurements.",
            "A catalog-ranked track is not a secure NORAD identity.",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    evidence_path = output_root / "retrospective-satellite-nuisance-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    figures = _render_results(output_root, evidence)
    manifest = {
        "schema": "org.leo.research.retrospective-satellite-nuisance-artifacts/v1",
        "protocol_sha256": _sha256(protocol_path),
        "artifacts": {
            path.name: {"sha256": _sha256(path), "byte_size": path.stat().st_size}
            for path in [evidence_path, *figures]
        },
    }
    manifest_path = output_root / "artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evidence["artifact_manifest_sha256"] = _sha256(manifest_path)
    return evidence


def main() -> None:
    arguments = _arguments()
    evidence = run(arguments.protocol.resolve(), arguments.output_root.resolve())
    print(json.dumps(evidence["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
