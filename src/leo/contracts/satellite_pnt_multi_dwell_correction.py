"""Solver-safe satellite calibration conditioned on sequential dwell histories."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_dwell_catalogue import MultiDwellHistoryAssignmentV1
from leo.contracts.satellite_pnt import CalibrationSourceSpanV1, VerifiedTleMemberV1
from leo.contracts.satellite_pnt_joint_calibration import (
    JointCalibratedSatelliteStateV1,
    _validate_covariance,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus


class SequentialHistoryCorrectionModeV1(ContractModel):
    schema_version: Literal[1] = 1
    history_mode_digest: Sha256Digest
    posterior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    assignments: Annotated[tuple[MultiDwellHistoryAssignmentV1, ...], Field(min_length=1)]
    active_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=2)]
    satellite_states: Annotated[tuple[JointCalibratedSatelliteStateV1, ...], Field(max_length=2)]
    frequency_covariance: tuple[tuple[float, ...], ...]
    receiver_frequency_gauge_resolved: bool
    frequency_calibration_evidence_eligible: bool
    calibration_transferable: bool
    future_activity_resolved: Literal[False] = False
    navigation_eligible: Literal[False] = False
    mode_digest: Sha256Digest

    @field_validator("posterior_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("sequential correction probability must be finite")
        return value

    @model_validator(mode="after")
    def _mode_is_closed(self) -> Self:
        assigned = tuple(
            sorted(
                {
                    item.catalog_number
                    for item in self.assignments
                    if item.catalog_number is not None
                }
            )
        )
        if self.active_catalog_numbers != assigned:
            raise ValueError("sequential correction assignments disagree with active catalogues")
        if tuple(item.catalog_number for item in self.satellite_states) != (
            self.active_catalog_numbers
        ):
            raise ValueError("sequential correction states disagree with active catalogues")
        _validate_covariance(
            self.frequency_covariance,
            dimension=2 * len(self.satellite_states),
        )
        for index, state in enumerate(self.satellite_states):
            if not math.isclose(
                self.frequency_covariance[2 * index][2 * index],
                state.frequency.bias_variance_hz2,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ) or not math.isclose(
                self.frequency_covariance[2 * index + 1][2 * index + 1],
                state.frequency.drift_variance_hz2_s2,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("sequential covariance diagonal disagrees with states")
        expected_transferable = bool(self.satellite_states) and (
            self.receiver_frequency_gauge_resolved and self.frequency_calibration_evidence_eligible
        )
        if self.calibration_transferable != expected_transferable:
            raise ValueError("sequential calibration transferability is inconsistent")
        if self.mode_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"mode_digest"})
        ):
            raise ValueError("sequential correction mode digest does not match content")
        return self


class SequentialHistorySatelliteCorrectionProductV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["sequential-history-satellite-correction-product"] = (
        "sequential-history-satellite-correction-product"
    )
    algorithm_version: Literal["known-position-sequential-history-calibration-v1"] = (
        "known-position-sequential-history-calibration-v1"
    )
    calibration_protocol_digest: Sha256Digest
    source_posterior_digest: Sha256Digest
    adapter_result_digest: Sha256Digest
    merged_graph_digest: Sha256Digest
    merged_prediction_bank_digest: Sha256Digest
    frequency_calibration_authority_digest: Sha256Digest
    calibration_site_commitment_digest: Sha256Digest
    source_fingerprint_authority_digest: Sha256Digest
    calibration_source_spans: Annotated[
        tuple[CalibrationSourceSpanV1, ...], Field(min_length=1, max_length=4096)
    ]
    calibration_start_utc_ns: Annotated[int, Field(gt=0)]
    calibration_end_utc_ns: Annotated[int, Field(gt=0)]
    produced_utc_ns: Annotated[int, Field(gt=0)]
    valid_until_utc_ns: Annotated[int, Field(gt=0)]
    tle_snapshot: TleSnapshotRefV1
    tle_membership_authority_digest: Sha256Digest
    verified_tle_members: Annotated[tuple[VerifiedTleMemberV1, ...], Field(max_length=512)]
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    modes: Annotated[
        tuple[SequentialHistoryCorrectionModeV1, ...], Field(min_length=1, max_length=4096)
    ]
    status: Literal[StandardScientificStatus.PARTIAL] = StandardScientificStatus.PARTIAL
    calibration_site_disclosed: Literal[False] = False
    receiver_local_state_excluded: Literal[True] = True
    sequential_history_semantics_preserved: Literal[True] = True
    future_activity_selection_required: Literal[True] = True
    simultaneous_activity_inferred_from_history: Literal[False] = False
    navigation_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False
    navigation_fix_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @field_validator("downlink_frequency_hz")
    @classmethod
    def _finite_rf(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("sequential correction RF must be finite")
        return value

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        if self.calibration_end_utc_ns <= self.calibration_start_utc_ns:
            raise ValueError("sequential calibration interval must be non-empty")
        if self.produced_utc_ns < self.calibration_end_utc_ns:
            raise ValueError("sequential correction predates calibration completion")
        if self.valid_until_utc_ns != self.produced_utc_ns + 30_000_000_000:
            raise ValueError("sequential correction uses the fixed 30-second validity horizon")
        if self.tle_snapshot.collected_utc_ns > self.calibration_start_utc_ns:
            raise ValueError("sequential correction TLE snapshot must be causal")
        if self.produced_utc_ns - self.tle_snapshot.collected_utc_ns > 86_400_000_000_000:
            raise ValueError("sequential correction TLE snapshot exceeds the freshness policy")
        span_keys = tuple(
            (
                item.source_recording_fingerprint,
                item.source_stream_index,
                item.source_sample_start,
                item.source_sample_stop,
            )
            for item in self.calibration_source_spans
        )
        if span_keys != tuple(sorted(set(span_keys))):
            raise ValueError("sequential calibration source spans must be canonical")
        if any(
            item.source_fingerprint_authority_digest != self.source_fingerprint_authority_digest
            for item in self.calibration_source_spans
        ):
            raise ValueError("sequential source spans use the wrong authority")
        if any(
            item.start_utc_ns < self.calibration_start_utc_ns
            or item.end_utc_ns > self.calibration_end_utc_ns
            for item in self.calibration_source_spans
        ):
            raise ValueError("sequential source span lies outside calibration")
        _validate_source_span_chronology(self.calibration_source_spans)
        history_digests = tuple(item.history_mode_digest for item in self.modes)
        if len(set(history_digests)) != len(history_digests):
            raise ValueError("sequential correction repeats a history mode")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("sequential correction modes must be probability ordered")
        if not math.isclose(
            math.fsum(probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("sequential correction probabilities must sum to one")
        used_members = {
            (state.catalog_number, state.selected_element_digest, state.element_epoch_utc_ns)
            for mode in self.modes
            for state in mode.satellite_states
        }
        member_inventory = tuple(
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.verified_tle_members
        )
        if member_inventory != tuple(sorted(set(member_inventory))):
            raise ValueError("sequential verified members must be unique and ordered")
        members = {
            (item.catalog_number, item.selected_element_digest, item.element_epoch_utc_ns)
            for item in self.verified_tle_members
        }
        if used_members != members:
            raise ValueError("sequential verified members do not close over states")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("sequential correction product digest does not match content")
        return self


class KnownPositionSequentialHistoryCalibrationReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    calibration_site: ObserverSiteV1
    calibration_site_authority_digest: Sha256Digest
    full_joint_state_digest: Sha256Digest
    receiver_local_state_digest: Sha256Digest
    correction_product: SequentialHistorySatelliteCorrectionProductV1
    sealed_utc_ns: Annotated[int, Field(gt=0)]
    site_access_policy: Literal["calibration-and-reveal-only-v1"] = "calibration-and-reveal-only-v1"
    receiver_local_state_exported: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_closed(self) -> Self:
        if self.sealed_utc_ns < self.correction_product.produced_utc_ns:
            raise ValueError("sequential receipt predates its correction product")
        expected_site_commitment = canonical_digest(
            {
                "calibration_site": self.calibration_site.model_dump(mode="json"),
                "calibration_site_authority_digest": self.calibration_site_authority_digest,
            }
        )
        if expected_site_commitment != self.correction_product.calibration_site_commitment_digest:
            raise ValueError("sequential receipt site does not match its opaque commitment")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("sequential calibration receipt digest does not match content")
        return self


def _validate_source_span_chronology(
    spans: tuple[CalibrationSourceSpanV1, ...],
) -> None:
    grouped: dict[tuple[str, int], list[CalibrationSourceSpanV1]] = {}
    for span in spans:
        grouped.setdefault(
            (span.source_recording_fingerprint, span.source_stream_index), []
        ).append(span)
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: item.source_sample_start)
        for left, right in zip(ordered, ordered[1:], strict=False):
            if left.source_sample_stop > right.source_sample_start:
                raise ValueError("sequential calibration source spans overlap")
            if left.end_utc_ns > right.start_utc_ns:
                raise ValueError("sequential calibration sample and UTC ordering disagree")
