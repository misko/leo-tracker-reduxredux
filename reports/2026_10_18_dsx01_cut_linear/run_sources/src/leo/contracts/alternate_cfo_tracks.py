"""Immutable candidate-only alternate CFO line-finder products."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class AlternateCfoLineFinderConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm: Literal["weighted_alias_aware_hough"] = "weighted_alias_aware_hough"
    alias_spacing_hz: Annotated[float, Field(gt=0)]
    minimum_slope_hz_per_s: float
    maximum_slope_hz_per_s: float
    residual_gate_hz: Annotated[float, Field(gt=0)]
    maximum_gap_s: Annotated[float, Field(gt=0)]
    minimum_span_s: Annotated[float, Field(gt=0)]
    minimum_support: Annotated[int, Field(ge=2, le=256)]
    minimum_point_weight: Annotated[float, Field(ge=0, le=16)]
    slope_bins: Annotated[int, Field(ge=3, le=257)]
    intercept_bins: Annotated[int, Field(ge=16, le=1024)]
    peak_candidates: Annotated[int, Field(ge=1, le=64)]
    maximum_detected_tracks: Annotated[int, Field(ge=1, le=32)]
    maximum_published_tracks: Annotated[int, Field(ge=1, le=16)]
    maximum_input_points: Annotated[int, Field(ge=1, le=25_000)]

    @field_validator(
        "alias_spacing_hz",
        "minimum_slope_hz_per_s",
        "maximum_slope_hz_per_s",
        "residual_gate_hz",
        "maximum_gap_s",
        "minimum_span_s",
        "minimum_point_weight",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("line-finder configuration must be finite")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.minimum_slope_hz_per_s >= self.maximum_slope_hz_per_s:
            raise ValueError("line-finder slope bounds are not ordered")
        if self.maximum_published_tracks > self.maximum_detected_tracks:
            raise ValueError("published track bound exceeds detector bound")
        if self.residual_gate_hz >= self.alias_spacing_hz / 2:
            raise ValueError("residual gate must be below half the alias spacing")
        return self


class AlternateCfoTrackV1(ContractModel):
    schema_version: Literal[1] = 1
    track_id: Sha256Digest
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    span_s: Annotated[float, Field(ge=0)]
    support_count: Annotated[int, Field(ge=2, le=25_000)]
    weighted_support: Annotated[float, Field(ge=0)]
    slope_hz_per_s: float
    acceleration_hz_per_s2: Annotated[float, Field(ge=0, le=0)] = 0.0
    intercept_mod_alias_hz: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    maximum_gap_s: Annotated[float, Field(ge=0)]
    confidence: Literal["strong_geometry", "candidate_geometry"]
    status: Literal["research_only"] = "research_only"

    @field_validator(
        "start_s",
        "end_s",
        "span_s",
        "weighted_support",
        "slope_hz_per_s",
        "intercept_mod_alias_hz",
        "residual_rms_hz",
        "residual_max_hz",
        "maximum_gap_s",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("alternate track values must be finite")
        return value

    @model_validator(mode="after")
    def _geometry(self) -> Self:
        if self.end_s < self.start_s or not math.isclose(
            self.span_s, self.end_s - self.start_s, abs_tol=1e-9
        ):
            raise ValueError("alternate track span is inconsistent")
        if self.residual_rms_hz > self.residual_max_hz:
            raise ValueError("alternate track residual bounds are inconsistent")
        return self


class AlternateCfoTrackBankV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["alternate-cfo-hough-v1"] = "alternate-cfo-hough-v1"
    pilot_scan_content_digest: Sha256Digest
    configuration_digest: Sha256Digest
    configuration: AlternateCfoLineFinderConfigV1
    source_point_count: Annotated[int, Field(ge=0, le=25_000)]
    detected_track_count: Annotated[int, Field(ge=0, le=32)]
    returned_track_count: Annotated[int, Field(ge=0, le=16)]
    truncated_track_count: Annotated[int, Field(ge=0, le=32)]
    tracks: tuple[AlternateCfoTrackV1, ...] = Field(max_length=16)
    frequency_coordinate: Literal["baseband_cfo_hz"] = "baseband_cfo_hz"
    candidate_only: Literal[True] = True
    automatic_use_allowed: Literal[False] = False
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if self.configuration_digest != canonical_digest(
            self.configuration.model_dump(mode="json")
        ):
            raise ValueError("alternate-track configuration digest disagrees with configuration")
        if self.returned_track_count != len(self.tracks):
            raise ValueError("returned alternate-track count disagrees with rows")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("alternate-track truncation accounting is inconsistent")
        if self.source_point_count > self.configuration.maximum_input_points:
            raise ValueError("alternate-track source inventory exceeds configured bound")
        if self.detected_track_count > self.configuration.maximum_detected_tracks:
            raise ValueError("alternate-track detector inventory exceeds configured bound")
        if self.returned_track_count > self.configuration.maximum_published_tracks:
            raise ValueError("alternate-track output inventory exceeds configured bound")
        ids = tuple(item.track_id for item in self.tracks)
        if len(ids) != len(set(ids)):
            raise ValueError("alternate track identifiers must be unique")
        return self


class ResidualHoughSegmentationConfigV2(ContractModel):
    """Versioned policy for refining each initial Hough parent in residual space."""

    schema_version: Literal[2] = 2
    algorithm: Literal["split_penalized_residual_hough"] = "split_penalized_residual_hough"
    initial_hough: AlternateCfoLineFinderConfigV1
    minimum_split_gain: Annotated[float, Field(ge=0)] = 200.0
    maximum_proposals_per_parent: Annotated[int, Field(ge=1, le=8)] = 8
    maximum_parent_support: Annotated[int, Field(ge=2, le=5_000)] = 2_000
    maximum_input_points: Annotated[int, Field(ge=1, le=100_000)] = 50_000
    residual_gate_rule: Literal["half_intercept_bin"] = "half_intercept_bin"
    selection_criterion: Literal["theil_sen_l1_mdl_plus_split_gain"] = (
        "theil_sen_l1_mdl_plus_split_gain"
    )

    @field_validator("minimum_split_gain")
    @classmethod
    def _finite_split_gain(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("minimum split gain must be finite")
        return value


class RankedCandidateResidualHoughConfigV3(ContractModel):
    """Dense-evidence policy with an explicit bounded segmentation handoff."""

    schema_version: Literal[3] = 3
    algorithm: Literal["ranked-candidate-split-penalized-residual-hough"] = (
        "ranked-candidate-split-penalized-residual-hough"
    )
    segmentation: ResidualHoughSegmentationConfigV2
    maximum_candidates_per_probe: Annotated[int, Field(ge=1, le=32)]
    selection_rule: Literal["lowest-rank-prefix-per-independent-probe"] = (
        "lowest-rank-prefix-per-independent-probe"
    )


class ResidualHoughParentSelectionV2(ContractModel):
    schema_version: Literal[2] = 2
    parent_track_id: Sha256Digest
    parent_support_count: Annotated[int, Field(ge=2, le=25_000)]
    residual_gate_hz: Annotated[float, Field(gt=0)]
    detected_proposal_count: Annotated[int, Field(ge=0, le=32)]
    considered_proposal_count: Annotated[int, Field(ge=0, le=8)]
    assigned_point_count: Annotated[int, Field(ge=0, le=25_000)]
    unassigned_point_count: Annotated[int, Field(ge=0, le=25_000)]
    admissible_partition_count: Annotated[int, Field(ge=0, le=4_140)]
    selected_line_count: Annotated[int, Field(ge=0, le=8)]
    robust_mdl: float
    adjusted_robust_mdl: float
    gaussian_bic: float
    adjusted_gaussian_bic: float
    gaussian_selected_line_count: Annotated[int, Field(ge=0, le=8)]

    @field_validator(
        "residual_gate_hz",
        "robust_mdl",
        "adjusted_robust_mdl",
        "gaussian_bic",
        "adjusted_gaussian_bic",
    )
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("residual-Hough selection values must be finite")
        return value

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if self.assigned_point_count + self.unassigned_point_count != self.parent_support_count:
            raise ValueError("residual-Hough parent support accounting is inconsistent")
        if self.considered_proposal_count > self.detected_proposal_count:
            raise ValueError("considered residual proposals exceed detected proposals")
        return self


class AlternateCfoTrackV2(ContractModel):
    """One linear output of a split-penalized residual-Hough parent refinement."""

    schema_version: Literal[2] = 2
    track_id: Sha256Digest
    source_parent_track_id: Sha256Digest
    source_residual_proposal_numbers: tuple[Annotated[int, Field(ge=1, le=8)], ...] = Field(
        min_length=1, max_length=8
    )
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    span_s: Annotated[float, Field(ge=0)]
    support_count: Annotated[int, Field(ge=2, le=25_000)]
    weighted_support: Annotated[float, Field(ge=0)]
    slope_hz_per_s: float
    acceleration_hz_per_s2: Annotated[float, Field(ge=0, le=0)] = 0.0
    intercept_mod_alias_hz: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    median_absolute_residual_hz: Annotated[float, Field(ge=0)]
    maximum_gap_s: Annotated[float, Field(ge=0)]
    confidence: Literal["strong_geometry", "candidate_geometry"]
    status: Literal["research_only"] = "research_only"

    @field_validator(
        "start_s",
        "end_s",
        "span_s",
        "weighted_support",
        "slope_hz_per_s",
        "intercept_mod_alias_hz",
        "residual_rms_hz",
        "residual_max_hz",
        "median_absolute_residual_hz",
        "maximum_gap_s",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("alternate track values must be finite")
        return value

    @model_validator(mode="after")
    def _geometry(self) -> Self:
        if self.end_s < self.start_s or not math.isclose(
            self.span_s, self.end_s - self.start_s, abs_tol=1e-9
        ):
            raise ValueError("alternate track span is inconsistent")
        if self.residual_rms_hz > self.residual_max_hz:
            raise ValueError("alternate track residual bounds are inconsistent")
        if len(set(self.source_residual_proposal_numbers)) != len(
            self.source_residual_proposal_numbers
        ):
            raise ValueError("residual proposal provenance must be unique")
        return self


class AlternateCfoTrackBankV2(ContractModel):
    schema_version: Literal[2] = 2
    algorithm_version: Literal["alternate-cfo-residual-hough-v2"] = (
        "alternate-cfo-residual-hough-v2"
    )
    pilot_scan_content_digest: Sha256Digest
    configuration_digest: Sha256Digest
    configuration: ResidualHoughSegmentationConfigV2
    source_point_count: Annotated[int, Field(ge=0, le=100_000)]
    initial_track_count: Annotated[int, Field(ge=0, le=32)]
    refined_parent_count: Annotated[int, Field(ge=0, le=32)]
    detected_track_count: Annotated[int, Field(ge=0, le=256)]
    returned_track_count: Annotated[int, Field(ge=0, le=16)]
    truncated_track_count: Annotated[int, Field(ge=0, le=256)]
    parent_selections: tuple[ResidualHoughParentSelectionV2, ...] = Field(max_length=32)
    tracks: tuple[AlternateCfoTrackV2, ...] = Field(max_length=16)
    frequency_coordinate: Literal["baseband_cfo_hz"] = "baseband_cfo_hz"
    candidate_only: Literal[True] = True
    automatic_use_allowed: Literal[False] = False
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if self.configuration_digest != canonical_digest(
            self.configuration.model_dump(mode="json")
        ):
            raise ValueError("alternate-track configuration digest disagrees with configuration")
        if self.refined_parent_count != len(self.parent_selections):
            raise ValueError("refined parent count disagrees with selection rows")
        if self.refined_parent_count > self.initial_track_count:
            raise ValueError("refined parent count exceeds initial Hough inventory")
        if self.returned_track_count != len(self.tracks):
            raise ValueError("returned alternate-track count disagrees with rows")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("alternate-track truncation accounting is inconsistent")
        initial = self.configuration.initial_hough
        if self.source_point_count > self.configuration.maximum_input_points:
            raise ValueError("alternate-track source inventory exceeds configured bound")
        if self.initial_track_count > initial.maximum_detected_tracks:
            raise ValueError("initial Hough inventory exceeds configured bound")
        if self.returned_track_count > initial.maximum_published_tracks:
            raise ValueError("alternate-track output inventory exceeds configured bound")
        ids = tuple(item.track_id for item in self.tracks)
        if len(ids) != len(set(ids)):
            raise ValueError("alternate track identifiers must be unique")
        parent_ids = tuple(item.parent_track_id for item in self.parent_selections)
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("residual-Hough parent identifiers must be unique")
        if any(item.source_parent_track_id not in parent_ids for item in self.tracks):
            raise ValueError("alternate track references an unknown Hough parent")
        return self


class AlternateCfoTrackBankV3(ContractModel):
    """Residual-Hough results with explicit dense-to-bounded point provenance."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["alternate-cfo-residual-hough-v3"] = (
        "alternate-cfo-residual-hough-v3"
    )
    pilot_scan_content_digest: Sha256Digest
    configuration_digest: Sha256Digest
    configuration: RankedCandidateResidualHoughConfigV3
    source_point_count: Annotated[int, Field(ge=0, le=250_000)]
    selected_point_count: Annotated[int, Field(ge=0, le=25_000)]
    omitted_point_count: Annotated[int, Field(ge=0, le=250_000)]
    initial_track_count: Annotated[int, Field(ge=0, le=32)]
    refined_parent_count: Annotated[int, Field(ge=0, le=32)]
    detected_track_count: Annotated[int, Field(ge=0, le=256)]
    returned_track_count: Annotated[int, Field(ge=0, le=16)]
    truncated_track_count: Annotated[int, Field(ge=0, le=256)]
    parent_selections: tuple[ResidualHoughParentSelectionV2, ...] = Field(max_length=32)
    tracks: tuple[AlternateCfoTrackV2, ...] = Field(max_length=16)
    frequency_coordinate: Literal["baseband_cfo_hz"] = "baseband_cfo_hz"
    candidate_only: Literal[True] = True
    automatic_use_allowed: Literal[False] = False
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if self.configuration_digest != canonical_digest(
            self.configuration.model_dump(mode="json")
        ):
            raise ValueError("alternate-track configuration digest disagrees with configuration")
        if self.source_point_count != self.selected_point_count + self.omitted_point_count:
            raise ValueError("alternate-track point selection accounting is inconsistent")
        segmentation = self.configuration.segmentation
        if self.selected_point_count > min(
            segmentation.maximum_input_points,
            segmentation.initial_hough.maximum_input_points,
        ):
            raise ValueError("selected alternate-track inventory exceeds Hough bound")
        if self.refined_parent_count != len(self.parent_selections):
            raise ValueError("refined parent count disagrees with selection rows")
        if self.refined_parent_count > self.initial_track_count:
            raise ValueError("refined parent count exceeds initial Hough inventory")
        if self.returned_track_count != len(self.tracks):
            raise ValueError("returned alternate-track count disagrees with rows")
        if self.detected_track_count != self.returned_track_count + self.truncated_track_count:
            raise ValueError("alternate-track truncation accounting is inconsistent")
        initial = segmentation.initial_hough
        if self.initial_track_count > initial.maximum_detected_tracks:
            raise ValueError("initial Hough inventory exceeds configured bound")
        if self.returned_track_count > initial.maximum_published_tracks:
            raise ValueError("alternate-track output inventory exceeds configured bound")
        ids = tuple(item.track_id for item in self.tracks)
        if len(ids) != len(set(ids)):
            raise ValueError("alternate track identifiers must be unique")
        parent_ids = tuple(item.parent_track_id for item in self.parent_selections)
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("residual-Hough parent identifiers must be unique")
        if any(item.source_parent_track_id not in parent_ids for item in self.tracks):
            raise ValueError("alternate track references an unknown Hough parent")
        return self
