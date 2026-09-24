"""Bind calibrated geometry authority to one completed adaptive phase product."""

from __future__ import annotations

import math

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_geometry_phase import (
    CalibratedPhaseGeometry,
    GeometryPhaseObservation,
    GeometryPhaseReconstruction,
    ReceiverChainCalibration,
    reconstruct_geometry_phase,
)
from leo.contracts.digests import canonical_digest
from leo.scanner.adaptive_dual_rx_geometry_input_v1 import AdaptiveDualRxGeometryInputV1
from leo.scanner.adaptive_dual_rx_phase_product_v2 import AdaptiveDualRxPhaseVisitV2
from leo.station.geometry import AdaptiveReceiverGeometryBindingV1
from leo.storage.adaptive_hop import GeometryBoundAdaptiveHopIqManifestV6


def _fixture_to_enu(inputs: AdaptiveDualRxGeometryInputV1) -> np.ndarray:
    axes = (
        inputs.fixture_pose.fixture_x_axis_enu,
        inputs.fixture_pose.fixture_y_axis_enu,
        inputs.fixture_pose.fixture_z_axis_enu,
    )
    return np.column_stack([(axis.x, axis.y, axis.z) for axis in axes])


def _calibrated_geometry(
    binding: AdaptiveReceiverGeometryBindingV1,
    inputs: AdaptiveDualRxGeometryInputV1,
) -> CalibratedPhaseGeometry:
    assignments = {item.receiver_id: item for item in binding.radio.assignments}
    slots = {item.slot_id: item for item in binding.fixture.slots}
    refinement = inputs.phase_center_refinement
    refined = {} if refinement is None else {item.receiver_id: item for item in refinement.paths}
    refinement_matches = refinement is not None and all(
        refined[receiver_id].physical_receiver_id == assignments[receiver_id].physical_receiver_id
        and refined[receiver_id].slot_id == assignments[receiver_id].slot_id
        for receiver_id in (0, 1)
    )
    centers = []
    for receiver_id in (0, 1):
        slot = slots[assignments[receiver_id].slot_id]
        center = slot.rf_phase_center_position_m
        if refinement_matches:
            mount = slot.mount_reference_position_m
            offset = refined[receiver_id].phase_center_offset_from_mount_m
            centers.append(
                np.asarray(
                    (mount.x + offset.x, mount.y + offset.y, mount.z + offset.z),
                    dtype=float,
                )
            )
        elif center is None:
            centers.append(None)
        else:
            centers.append(np.asarray((center.x, center.y, center.z), dtype=float))
    baseline = None
    if centers[0] is not None and centers[1] is not None:
        baseline = _fixture_to_enu(inputs) @ (centers[1] - centers[0])
    digest = canonical_digest(
        {
            "receiver_geometry_binding_digest": binding.binding_digest,
            "fixture_pose_evidence_sha256": inputs.fixture_pose.evidence_sha256,
            "phase_center_refinement_digest": (
                None if refinement is None else refinement.refinement_digest
            ),
        }
    )
    return CalibratedPhaseGeometry(
        baseline_enu_m=None if baseline is None else tuple(map(float, baseline)),
        baseline_standard_error_m=inputs.fixture_pose.baseline_standard_error_m,
        geometry_digest=digest,
        receiver_mapping_verified=(
            refinement_matches
            if refinement is not None
            else all(item.mapping_status == "verified" for item in binding.radio.assignments)
        ),
        phase_centers_verified=(
            refinement_matches and refinement.measurement_truth_verified
            if refinement is not None
            else all(center is not None for center in centers)
        ),
        enu_pose_verified=inputs.fixture_pose.measurement_truth_verified,
    )


def reconstruct_product_geometry(
    capture: GeometryBoundAdaptiveHopIqManifestV6,
    visits: tuple[AdaptiveDualRxPhaseVisitV2, ...],
    inputs: AdaptiveDualRxGeometryInputV1,
) -> GeometryPhaseReconstruction:
    """Validate every authority binding, then compare measured and geometric phase."""
    if (
        inputs.session_id != capture.receipt.session_id
        or inputs.input_manifest_sha256 != visits[0].input_manifest_sha256
        or inputs.glrt_binding_sha256 != visits[0].glrt_binding_sha256
        or inputs.receiver_geometry_binding_digest != capture.receiver_geometry.binding_digest
    ):
        raise ValueError("geometry input is bound to another capture or GLRT analysis")
    if not (
        inputs.valid_from_utc_ns <= capture.created_utc_ns
        and capture.finalized_utc_ns <= inputs.valid_until_utc_ns
        and inputs.chain_calibration.valid_from_utc_ns <= capture.created_utc_ns
        and capture.finalized_utc_ns <= inputs.chain_calibration.valid_until_utc_ns
        and (
            inputs.phase_center_refinement is None
            or (
                inputs.phase_center_refinement.valid_from_utc_ns <= capture.created_utc_ns
                and capture.finalized_utc_ns <= inputs.phase_center_refinement.valid_until_utc_ns
            )
        )
    ):
        raise ValueError("geometry or chain calibration validity does not cover capture")
    timing = capture.timing
    if timing is None or not timing.qualified:
        raise ValueError("geometry phase requires qualified capture UTC timing")
    hypotheses = {
        (visit.visit_index, item.hypothesis_index): item
        for visit in visits
        for item in visit.hypotheses
    }
    rows = {(row.visit_index, row.hypothesis_index): row for row in inputs.directions}
    if not set(rows) <= set(hypotheses):
        raise ValueError("direction evidence refers to an unpublished phase hypothesis")
    observations = []
    for key, row in rows.items():
        item = hypotheses[key]
        if not (
            math.isclose(
                row.low_rx0_tracking_cfo_hz,
                item.low_rx0_tracking_cfo_hz,
                rel_tol=0,
                abs_tol=1e-6,
            )
            and math.isclose(
                row.high_rx0_tracking_cfo_hz,
                item.high_rx0_tracking_cfo_hz,
                rel_tol=0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("direction evidence changed the phase hypothesis frequencies")
        utc_ns = timing.first_sample_estimate_utc_ns + round(item.common_session_time_s * 1e9)
        if not inputs.valid_from_utc_ns <= utc_ns <= inputs.valid_until_utc_ns:
            raise ValueError("direction evidence time falls outside its validity")
        observations.append(
            GeometryPhaseObservation(
                utc_ns=utc_ns,
                wrapped_double_difference_rad=(
                    item.wrapped_high_minus_low_rad + math.pi * row.pilot_phase_half_cycle
                ),
                measurement_standard_error_rad=item.standard_error_rad,
                low_rf_hz=row.low_rf_hz,
                high_rf_hz=row.high_rf_hz,
                low_direction_enu=(
                    row.low_direction_enu.x,
                    row.low_direction_enu.y,
                    row.low_direction_enu.z,
                ),
                high_direction_enu=(
                    row.high_direction_enu.x,
                    row.high_direction_enu.y,
                    row.high_direction_enu.z,
                ),
                direction_standard_error_rad=row.direction_standard_error_rad,
                low_frame_utc_ns=utc_ns,
                high_frame_utc_ns=utc_ns,
                common_mode_rate_rad_s=None,
                common_mode_rate_standard_error_rad_s=None,
                direction_track_verified=row.source_identity_verified,
                association_uses_phase=row.association_uses_phase,
            )
        )
    calibration = inputs.chain_calibration
    return reconstruct_geometry_phase(
        _calibrated_geometry(capture.receiver_geometry, inputs),
        ReceiverChainCalibration(
            differential_group_delay_s=calibration.differential_group_delay_s,
            group_delay_standard_error_s=calibration.group_delay_standard_error_s,
            residual_double_difference_rad=calibration.residual_double_difference_rad,
            residual_standard_error_rad=calibration.residual_standard_error_rad,
            calibration_digest=calibration.calibration_digest,
            measurement_truth_verified=calibration.measurement_truth_verified,
            absolute_cycle_referenced=calibration.absolute_cycle_referenced,
        ),
        tuple(observations),
    )
