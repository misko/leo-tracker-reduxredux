from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from leo.analysis.starlink.adaptive_dual_rx_geometry_phase import SPEED_OF_LIGHT_M_S
from leo.application.adaptive_dual_rx_geometry_v2 import reconstruct_product_geometry
from leo.contracts.digests import canonical_digest
from leo.scanner.adaptive_dual_rx_geometry_input_v1 import (
    AdaptiveDualRxChainCalibrationV1,
    AdaptiveDualRxDirectionRowV1,
    AdaptiveDualRxFixturePoseV1,
    AdaptiveDualRxGeometryInputV1,
    AdaptiveDualRxPhaseCenterPathV1,
    AdaptiveDualRxPhaseCenterRefinementV1,
)
from leo.station.geometry import (
    AdaptiveReceiverGeometryBindingV1,
    CartesianVectorMetersV1,
    RadioReceiverGeometryV1,
    ReceiverFixtureDefinitionV1,
    ReceiverFixtureSlotV1,
    ReceiverSlotAssignmentV1,
    StationReceiverGeometryV1,
    UnitVectorV1,
)
from tests.storage.test_adaptive_dual_rx_phase_v2_store import digest, visit


def _unit(x: float, y: float, z: float) -> UnitVectorV1:
    return UnitVectorV1(x=x, y=y, z=z)


def _binding() -> AdaptiveReceiverGeometryBindingV1:
    slots = tuple(
        ReceiverFixtureSlotV1(
            slot_id=slot_id,
            mount_reference_position_m=CartesianVectorMetersV1(x=x, y=0, z=0),
            mount_axis_unit=_unit(0, 0, 1),
            rf_phase_center_position_m=None,
            rf_boresight_unit=_unit(0, 0, 1),
        )
        for slot_id, x in (("left", -0.04), ("right", 0.04))
    )
    fixture = ReceiverFixtureDefinitionV1.create(
        fixture_part_id="test-fixture",
        geometry_revision="surveyed-v1",
        slots=slots,
        design_uri="fixture.json",
        design_sha256=digest("3"),
        mesh_uri="fixture.stl",
        mesh_sha256=digest("4"),
    )
    radio = RadioReceiverGeometryV1(
        radio_id="test-radio",
        radio_serial="test-serial",
        fixture_part_id=fixture.fixture_part_id,
        fixture_digest=fixture.fixture_digest,
        assignments=tuple(
            ReceiverSlotAssignmentV1(
                receiver_id=index,
                physical_receiver_id=f"lnb-{index}",
                slot_id=slot,
                mapping_status="provisional",
                mapping_evidence="capture-time receiver order only",
            )
            for index, slot in enumerate(("left", "right"))
        ),
    )
    geometry = StationReceiverGeometryV1.create(
        station_id="test-station",
        geometry_revision="surveyed-v1",
        valid_from_utc_ns=1_700_000_000_000_000_000,
        valid_until_utc_ns=1_900_000_000_000_000_000,
        fixtures=(fixture,),
        radios=(radio,),
    )
    return AdaptiveReceiverGeometryBindingV1.create(
        geometry, radio_id=radio.radio_id, radio_serial=radio.radio_serial
    )


def _inputs(binding: AdaptiveReceiverGeometryBindingV1) -> AdaptiveDualRxGeometryInputV1:
    calibration_values = {
        "valid_from_utc_ns": 1_700_000_000_000_000_000,
        "valid_until_utc_ns": 1_900_000_000_000_000_000,
        "differential_group_delay_s": 3.2e-9,
        "group_delay_standard_error_s": 0.05e-9,
        "residual_double_difference_rad": 0.13,
        "residual_standard_error_rad": 0.01,
        "absolute_cycle_referenced": True,
        "measurement_truth_verified": True,
        "evidence_uri": "chain-calibration.json",
        "evidence_sha256": digest("5"),
    }
    calibration = AdaptiveDualRxChainCalibrationV1(
        **calibration_values,
        calibration_digest=canonical_digest({"schema_version": 1, **calibration_values}),
    )
    low_rf_hz = 11_000_000_000.0
    high_rf_hz = 11_000_227_272.727
    direction = AdaptiveDualRxDirectionRowV1(
        visit_index=0,
        hypothesis_index=0,
        low_rx0_tracking_cfo_hz=-90_000,
        high_rx0_tracking_cfo_hz=-60_000,
        low_source_id="source-low",
        high_source_id="source-high",
        low_rf_hz=low_rf_hz,
        high_rf_hz=high_rf_hz,
        low_direction_enu=_unit(0, 0, 1),
        high_direction_enu=_unit(0.1, 0, math.sqrt(0.99)),
        direction_standard_error_rad=1e-5,
        association_method="independent catalogue and RF-frequency association",
        source_identity_verified=True,
        pilot_phase_half_cycle=0,
        pilot_phase_branch_verified=True,
    )
    pose = AdaptiveDualRxFixturePoseV1(
        fixture_x_axis_enu=_unit(1, 0, 0),
        fixture_y_axis_enu=_unit(0, 1, 0),
        fixture_z_axis_enu=_unit(0, 0, 1),
        baseline_standard_error_m=0.0002,
        evidence_uri="fixture-pose.json",
        evidence_sha256=digest("6"),
        measurement_truth_verified=True,
    )
    refinement_values = {
        "valid_from_utc_ns": 1_700_000_000_000_000_000,
        "valid_until_utc_ns": 1_900_000_000_000_000_000,
        "paths": tuple(
            AdaptiveDualRxPhaseCenterPathV1(
                receiver_id=index,
                physical_receiver_id=f"lnb-{index}",
                slot_id=slot,
                phase_center_offset_from_mount_m=CartesianVectorMetersV1(x=0, y=0, z=0),
            ).model_dump(mode="json")
            for index, slot in enumerate(("left", "right"))
        ),
        "evidence_uri": "phase-center-and-cable-survey.json",
        "evidence_sha256": digest("8"),
        "measurement_truth_verified": True,
    }
    refinement = AdaptiveDualRxPhaseCenterRefinementV1(
        **refinement_values,
        refinement_digest=canonical_digest({"schema_version": 1, **refinement_values}),
    )
    values = {
        "session_id": "scan-hop-phase-v2",
        "input_manifest_sha256": digest("1"),
        "glrt_binding_sha256": digest("2"),
        "receiver_geometry_binding_digest": binding.binding_digest,
        "valid_from_utc_ns": 1_700_000_000_000_000_000,
        "valid_until_utc_ns": 1_900_000_000_000_000_000,
        "fixture_pose": pose.model_dump(mode="json"),
        "phase_center_refinement": refinement.model_dump(mode="json"),
        "chain_calibration": calibration.model_dump(mode="json"),
        "direction_evidence_uri": "directions.json",
        "direction_evidence_sha256": digest("7"),
        "directions": (direction.model_dump(mode="json"),),
    }
    return AdaptiveDualRxGeometryInputV1(
        **values,
        input_digest=canonical_digest(
            {"schema_version": 1, "kind": "adaptive_dual_rx_geometry_input", **values}
        ),
    )


def test_bound_geometry_path_recovers_injected_curve_after_hardware_offset() -> None:
    binding = _binding()
    inputs = _inputs(binding)
    row = inputs.directions[0]
    predicted = 2 * math.pi * 0.08 * row.high_rf_hz * 0.1 / SPEED_OF_LIGHT_M_S
    hardware = 2 * math.pi * 3.2e-9 * (row.high_rf_hz - row.low_rf_hz) + 0.13
    measured = math.atan2(math.sin(predicted + hardware), math.cos(predicted + hardware))
    phase_visit = visit(0).model_copy(
        update={
            "hypotheses": (
                visit(0).hypotheses[0].model_copy(update={"wrapped_high_minus_low_rad": measured}),
            )
        }
    )
    capture = SimpleNamespace(
        receipt=SimpleNamespace(session_id="scan-hop-phase-v2"),
        created_utc_ns=1_799_999_999_000_000_000,
        finalized_utc_ns=1_800_000_100_000_000_000,
        receiver_geometry=binding,
        timing=SimpleNamespace(
            qualified=True,
            first_sample_estimate_utc_ns=1_800_000_000_000_000_000,
        ),
    )

    result = reconstruct_product_geometry(capture, (phase_visit,), inputs)

    assert result.state == "available"
    assert result.ambiguity_state == "conditionally_unique"
    assert result.points[0].ambiguity_candidates[0].residual_rad == pytest.approx(0, abs=1e-12)


def test_geometry_input_cannot_retarget_a_phase_hypothesis() -> None:
    binding = _binding()
    inputs = _inputs(binding)
    changed = inputs.directions[0].model_copy(update={"low_rx0_tracking_cfo_hz": -91_000})
    retargeted = inputs.model_copy(update={"directions": (changed,)})
    capture = SimpleNamespace(
        receipt=SimpleNamespace(session_id="scan-hop-phase-v2"),
        created_utc_ns=1_799_999_999_000_000_000,
        finalized_utc_ns=1_800_000_100_000_000_000,
        receiver_geometry=binding,
        timing=SimpleNamespace(
            qualified=True, first_sample_estimate_utc_ns=1_800_000_000_000_000_000
        ),
    )
    with pytest.raises(ValueError, match="changed the phase hypothesis frequencies"):
        reconstruct_product_geometry(capture, (visit(0),), retargeted)


@pytest.mark.parametrize("change", ["missing", "conflicting"])
def test_retrospective_phase_center_refinement_fails_closed(change: str) -> None:
    binding = _binding()
    inputs = _inputs(binding)
    if change == "missing":
        inputs = inputs.model_copy(update={"phase_center_refinement": None})
    else:
        assert inputs.phase_center_refinement is not None
        paths = list(inputs.phase_center_refinement.paths)
        paths[0] = paths[0].model_copy(update={"physical_receiver_id": "different-lnb"})
        inputs = inputs.model_copy(
            update={
                "phase_center_refinement": inputs.phase_center_refinement.model_copy(
                    update={"paths": tuple(paths)}
                )
            }
        )
    capture = SimpleNamespace(
        receipt=SimpleNamespace(session_id="scan-hop-phase-v2"),
        created_utc_ns=1_799_999_999_000_000_000,
        finalized_utc_ns=1_800_000_100_000_000_000,
        receiver_geometry=binding,
        timing=SimpleNamespace(
            qualified=True,
            first_sample_estimate_utc_ns=1_800_000_000_000_000_000,
        ),
    )

    result = reconstruct_product_geometry(capture, (visit(0),), inputs)

    assert result.state == "unavailable"
    assert "receiver_mapping_unverified" in result.reasons
    assert "rf_phase_centers_unverified" in result.reasons
