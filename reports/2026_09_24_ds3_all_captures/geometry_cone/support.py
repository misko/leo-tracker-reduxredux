"""Strict DS3 receiver-geometry eligibility and cone-model specifications.

This report-local module deliberately consumes capture manifests rather than
the DS3 manifest's summary geometry flag.  A radio identity is not geometry
authority: every admitted capture must carry its own time-valid binding.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "ds3-lt3d-geometry-cone-plan/v1"
FIXTURE_PART_ID = "LT3D-001A"
FIXTURE_DIGEST = "sha256:6e6f8798e1465691fdb6ad973bc37443651408c4060f091144b1a470fb0817a4"
BINDING_DIGEST = "sha256:55e5a117d885e8ac158a0a41895b66cb5be881d66630d2765fccf5711a21643f"
STATION_GEOMETRY_DIGEST = (
    "sha256:006ff0cbaab43b3700e75b181733c0576d23747d4d37b025061101601e75c0d0"
)
FIXED_HALF_ANGLES_DEG = (10, 15, 20, 30)
FIXED_FULL_FOV_DEG = tuple(2 * angle for angle in FIXED_HALF_ANGLES_DEG)
LEARNED_MAX_TILT_FROM_ZENITH_DEG = 15
PROHIBITED_INPUTS = (
    "relative_receiver_phase",
    "receiver_phase_offset",
    "phase_derived_baseline_or_direction",
)


def _iso_to_ns(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("capture_start_utc must include a timezone")
    return int(parsed.astimezone(UTC).timestamp() * 1_000_000_000)


def _excluded(session_id: str, reason: str) -> dict[str, Any]:
    return {"session_id": session_id, "status": "excluded", "reason": reason}


def evaluate_capture(capture: Mapping[str, Any], envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one capture using only its persisted capture-time binding."""

    session_id = str(capture.get("session_id", ""))
    if capture.get("admission_status") != "included":
        return _excluded(session_id, "capture_not_admitted_to_ds3")
    manifest = envelope.get("manifest")
    if not isinstance(manifest, Mapping):
        return _excluded(session_id, "recording_manifest_payload_absent")
    if manifest.get("session_id") != session_id:
        return _excluded(session_id, "recording_manifest_session_mismatch")
    geometry = manifest.get("receiver_geometry")
    if not isinstance(geometry, Mapping):
        return _excluded(session_id, "capture_time_geometry_absent")

    fixture = geometry.get("fixture")
    radio = geometry.get("radio")
    if not isinstance(fixture, Mapping) or not isinstance(radio, Mapping):
        return _excluded(session_id, "capture_time_geometry_incomplete")
    if (
        fixture.get("fixture_part_id") != FIXTURE_PART_ID
        or fixture.get("fixture_digest") != FIXTURE_DIGEST
        or radio.get("fixture_part_id") != FIXTURE_PART_ID
        or radio.get("fixture_digest") != FIXTURE_DIGEST
        or geometry.get("binding_digest") != BINDING_DIGEST
        or geometry.get("station_geometry_digest") != STATION_GEOMETRY_DIGEST
    ):
        return _excluded(session_id, "capture_time_geometry_not_reviewed_lt3d_001a")

    start_ns = _iso_to_ns(str(capture.get("capture_start_utc")))
    valid_from = geometry.get("valid_from_utc_ns")
    valid_until = geometry.get("valid_until_utc_ns")
    if not isinstance(valid_from, int) or not isinstance(valid_until, int):
        return _excluded(session_id, "capture_time_geometry_validity_absent")
    if not valid_from <= start_ns < valid_until:
        return _excluded(session_id, "capture_outside_geometry_validity_interval")

    slots = fixture.get("slots")
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)):
        return _excluded(session_id, "fixture_slots_absent")
    slot_by_id = {
        item.get("slot_id"): item for item in slots if isinstance(item, Mapping)
    }
    if set(slot_by_id) != {"negative-x", "positive-x"}:
        return _excluded(session_id, "fixture_slots_not_reviewed_pair")
    if any(not isinstance(slot_by_id[name].get("mount_axis_unit"), Mapping) for name in slot_by_id):
        return _excluded(session_id, "fixture_mount_axes_absent")

    assignments = radio.get("assignments")
    if not isinstance(assignments, Sequence) or isinstance(assignments, (str, bytes)):
        return _excluded(session_id, "receiver_assignments_absent")
    normalized = {
        int(item["receiver_id"]): str(item["slot_id"])
        for item in assignments
        if isinstance(item, Mapping)
        and isinstance(item.get("receiver_id"), int)
        and isinstance(item.get("slot_id"), str)
    }
    if set(normalized) != {0, 1} or set(normalized.values()) != {"negative-x", "positive-x"}:
        return _excluded(session_id, "receiver_assignments_not_reviewed_pair")

    statuses = {
        str(item.get("mapping_status"))
        for item in assignments
        if isinstance(item, Mapping)
    }
    if statuses == {"provisional"}:
        mapping_treatment = "symmetric_two_mapping_marginalization"
        mapping_hypotheses = [
            {"0": normalized[0], "1": normalized[1]},
            {"0": normalized[1], "1": normalized[0]},
        ]
    elif statuses == {"confirmed"}:
        mapping_treatment = "confirmed_capture_mapping"
        mapping_hypotheses = [{"0": normalized[0], "1": normalized[1]}]
    else:
        return _excluded(session_id, "receiver_mapping_status_unsupported")

    measured_boresight = all(
        isinstance(slot_by_id[name].get("rf_boresight_unit"), Mapping) for name in slot_by_id
    )
    return {
        "session_id": session_id,
        "status": "eligible",
        "reason": None,
        "capture_start_utc": capture["capture_start_utc"],
        "radio_id": capture.get("radio_id"),
        "binding_digest": BINDING_DIGEST,
        "fixture_part_id": FIXTURE_PART_ID,
        "station_geometry_digest": STATION_GEOMETRY_DIGEST,
        "mapping_treatment": mapping_treatment,
        "mapping_hypotheses": mapping_hypotheses,
        "direction_source": (
            "measured_rf_boresight" if measured_boresight else "fixture_nominal_mount_axis_proxy"
        ),
        "rf_boresight_measured": measured_boresight,
        "rf_phase_center_measured": all(
            isinstance(slot_by_id[name].get("rf_phase_center_position_m"), Mapping)
            for name in slot_by_id
        ),
    }


def model_variants(eligible_session_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Return the closed geometry/cone candidates for the DS3 top-ten comparison."""

    common: dict[str, Any] = {
        "eligible_session_ids": sorted(eligible_session_ids),
        "required_join": "receiver-labelled causal track evidence, joined by session_id",
        "mapping_treatment": "marginalize both mappings unless capture mapping is confirmed",
        "direction_input": "fixture mount axes transformed by a fitted world pose",
        "prohibited_inputs": list(PROHIBITED_INPUTS),
        "selection_partition": "development only",
        "reference_coordinate_use": "postseal evaluation only",
    }
    return [
        {
            **common,
            "model_id": "lt3d_geometry_only",
            "family": "receiver_geometry",
            "fit": {
                "receiver_likelihood": "nearest_transformed_mount_axis",
                "fixture_yaw_deg": "fit over [0,360)",
                "fixture_tilt_from_zenith_deg": "fit over [0,15]",
                "cone_width": None,
            },
        },
        {
            **common,
            "model_id": "lt3d_fixed_up_cone",
            "family": "fixed_cone",
            "fit": {
                "cone_axis": "local zenith",
                "fixed_half_angle_deg": list(FIXED_HALF_ANGLES_DEG),
                "equivalent_full_fov_deg": list(FIXED_FULL_FOV_DEG),
                "choice_rule": "choose on development partition, then freeze",
            },
        },
        {
            **common,
            "model_id": "lt3d_learned_zenith_cone",
            "family": "learned_cone",
            "fit": {
                "fixture_yaw_deg": "fit over [0,360)",
                "fixture_tilt_from_zenith_deg": (
                    f"fit over [0,{LEARNED_MAX_TILT_FROM_ZENITH_DEG}]"
                ),
                "cone_half_angle_deg": "fit on training rows",
            },
        },
        {
            **common,
            "model_id": "global_time_plus_lt3d_cone",
            "family": "global_time_plus_cone",
            "additional_requirements": [
                "qualified UTC timing for every participating capture",
                "one shared global time offset fitted without reference-coordinate access",
            ],
            "fit": {
                "global_time_offset": "shared nuisance parameter",
                "fixture_yaw_deg": "fit over [0,360)",
                "fixture_tilt_from_zenith_deg": (
                    f"fit over [0,{LEARNED_MAX_TILT_FROM_ZENITH_DEG}]"
                ),
                "cone_half_angle_deg": "fit on training rows",
            },
        },
    ]


def build_plan(
    ds3_manifest: Mapping[str, Any],
    load_recording_manifest: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic eligibility plan without reading IQ or model outputs."""

    if ds3_manifest.get("schema") != "ds3-all-captures-admission/v1":
        raise ValueError("unexpected DS3 admission schema")
    captures = ds3_manifest.get("captures")
    if not isinstance(captures, Sequence) or isinstance(captures, (str, bytes)):
        raise ValueError("DS3 captures must be a list")
    evaluations = [
        evaluate_capture(capture, load_recording_manifest(capture))
        for capture in captures
        if isinstance(capture, Mapping)
    ]
    eligible = sorted(
        str(row["session_id"]) for row in evaluations if row["status"] == "eligible"
    )
    return {
        "schema": SCHEMA,
        "source_manifest_schema": ds3_manifest["schema"],
        "source_capture_cutoff_utc": ds3_manifest.get("capture_cutoff_utc"),
        "eligibility_authority": "receiver_geometry embedded in each recording manifest",
        "geometry_is_not_inherited_by_radio_id": True,
        "iq_read": False,
        "reference_used": False,
        "phase_used": False,
        "counts": {
            "captures_evaluated": len(evaluations),
            "geometry_eligible": len(eligible),
            "geometry_excluded": len(evaluations) - len(eligible),
        },
        "eligible_session_ids": eligible,
        "captures": evaluations,
        "models": model_variants(eligible),
        "execution_gate": (
            "Join receiver-labelled causal track evidence; exclude a model/session if any "
            "declared requirement is absent. Do not substitute receiver phase or infer geometry."
        ),
    }


def recording_loader(
    capture_root: Path | None = None,
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Create a read-only JSON loader, optionally rebasing capture paths."""

    import json

    def load(capture: Mapping[str, Any]) -> Mapping[str, Any]:
        if capture_root is None:
            path = Path(str(capture["recording_manifest_path"]))
        else:
            path = capture_root / str(capture["session_id"]) / "manifest.json"
        value = json.loads(path.read_text())
        if not isinstance(value, Mapping):
            raise ValueError(f"recording manifest is not an object: {path}")
        return value

    return load
