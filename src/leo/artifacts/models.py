"""Versioned immutable analysis-run manifest contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.pipeline_lanes import PipelineDefinitionV1, PipelineLane
from leo.contracts.starlink_frequency import (
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
    starlink_maximum_coverage_if_center_frequency_hz,
)

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


class AnalysisJobReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    job_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    outcome: Annotated[str, StringConstraints(min_length=1, max_length=32)]


class AnalysisProductReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    product_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    role: Literal["scientific", "presentation"]
    status: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(ge=0)]
    coverage: Annotated[float | None, Field(ge=0.0, le=1.0)] = None


class AnalysisRunManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        identities = [(item.stage_key, item.scope_key) for item in value]
        if len(set(identities)) != len(identities):
            raise ValueError("run manifest job identities must be unique")
        if identities != sorted(identities):
            raise ValueError("run manifest jobs must be sorted")
        return value

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        identities = [
            (item.stage_key, item.scope_key, item.kind, item.product_schema_version)
            for item in value
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("run manifest product identities must be unique")
        if identities != sorted(identities):
            raise ValueError("run manifest products must be sorted")
        return value

    @model_validator(mode="after")
    def _products_belong_to_terminal_jobs(self) -> Self:
        jobs = {(item.stage_key, item.scope_key) for item in self.jobs}
        if any((item.stage_key, item.scope_key) not in jobs for item in self.products):
            raise ValueError("run manifest product has no corresponding job")
        return self


class AnalysisRunManifestV2(ContractModel):
    """Sealed run inventory with an explicit independent pipeline lane."""

    schema_version: Literal[2] = 2
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    pipeline_lane: Literal["standard", "research"]
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        return AnalysisRunManifestV1._jobs_are_canonical(value)

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        return AnalysisRunManifestV1._products_are_canonical(value)

    @model_validator(mode="after")
    def _products_belong_to_terminal_jobs(self) -> Self:
        jobs = {(item.stage_key, item.scope_key) for item in self.jobs}
        if any((item.stage_key, item.scope_key) not in jobs for item in self.products):
            raise ValueError("run manifest product has no corresponding job")
        return self


class StandardNativeTerminalProductRefV1(ContractModel):
    """One exact scientific terminal product authorized for promotion."""

    schema_version: Literal[1] = 1
    product_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    role: Literal["scientific"] = "scientific"
    status: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    digest: Sha256Digest


class StandardNativePromotionAuthorityV1(ContractModel):
    """Closed authority required before one native run may become Current."""

    schema_version: Literal[1] = 1
    source_manifest_schema_version: Literal[3] = 3
    source_manifest_digest: Sha256Digest
    pipeline_definition: PipelineDefinitionV1
    pipeline_definition_id: Sha256Digest
    session_id: Identifier
    run_id: Identifier
    input_manifest_digest: Sha256Digest
    pipeline_release_id: Identifier
    expanded_plan_digest: Sha256Digest
    raw_integrity_attestation_digest: Sha256Digest
    release_authority_digest: Sha256Digest
    subject_binding_inventory_digest: Sha256Digest
    terminal_products: Annotated[
        tuple[StandardNativeTerminalProductRefV1, ...],
        Field(min_length=1, max_length=64),
    ]
    terminal_product_inventory_digest: Sha256Digest
    profile_revision_digest: Sha256Digest
    sample_rate_hz: Literal[2_500_000, 3_000_000, 5_000_000, 10_000_000]
    capture_plan_digest: Sha256Digest
    capture_hardware_binding_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _authority_is_closed(self) -> Self:
        definition = self.pipeline_definition
        if (
            self.pipeline_definition_id != definition.definition_id
            or definition.lane is not PipelineLane.STANDARD
            or definition.product_namespace != "standard"
            or not definition.automatic_eligible
            or not definition.promotion_allowed
        ):
            raise ValueError("native promotion requires the exact promotable Standard definition")
        if self.pipeline_release_id != definition.executable_git_sha:
            raise ValueError("native promotion release differs from its pipeline definition")
        if self.source_manifest_digest != self.input_manifest_digest:
            raise ValueError("native promotion source differs from the run input manifest")
        identities = tuple(
            (
                item.stage_key,
                item.scope_key,
                item.kind,
                item.product_schema_version,
            )
            for item in self.terminal_products
        )
        product_ids = tuple(item.product_id for item in self.terminal_products)
        if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
            raise ValueError("native promotion terminal products must be unique and ordered")
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("native promotion terminal product IDs must be unique")
        expected_inventory_digest = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.terminal_products)
        )
        if self.terminal_product_inventory_digest != expected_inventory_digest:
            raise ValueError("native promotion terminal product inventory digest does not match")
        expected_content_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        )
        if self.content_digest != expected_content_digest:
            raise ValueError("native promotion authority content digest does not match")
        return self


class StandardNativeMixedStreamAuthorityV1(ContractModel):
    """One exact per-radio source leg authorized by a mixed native promotion."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    profile_name: Identifier
    profile_revision_digest: Sha256Digest
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: Literal["lower", "upper"]
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000]
    rf_bandwidth_hz: Annotated[int, Field(gt=0)]
    tuned_center_frequency_hz: Annotated[int, Field(gt=0)]
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    validity_inventory_digest: Sha256Digest

    @model_validator(mode="after")
    def _stream_authority_is_closed(self) -> Self:
        expected_center_hz = starlink_maximum_coverage_if_center_frequency_hz(
            self.starlink_channel,
            self.starlink_edge,
            bandwidth_hz=self.rf_bandwidth_hz,
        )
        expected_channel_bounds = starlink_channel_if_bounds_hz(self.starlink_channel)
        if (
            self.rf_bandwidth_hz != self.sample_rate_hz
            or self.pilot_if_center_frequency_hz
            != starlink_edge_if_center_frequency_hz(
                self.starlink_channel,
                self.starlink_edge,
            )
            or (self.channel_if_start_hz, self.channel_if_stop_hz) != expected_channel_bounds
            or self.tuned_center_frequency_hz != expected_center_hz
            or self.captured_if_stop_hz - self.captured_if_start_hz != self.rf_bandwidth_hz
            or self.tuned_center_frequency_hz * 2
            != self.captured_if_start_hz + self.captured_if_stop_hz
            or self.channel_if_stop_hz <= self.channel_if_start_hz
            or self.captured_if_start_hz < self.channel_if_start_hz
            or self.captured_if_stop_hz > self.channel_if_stop_hz
            or not (
                self.captured_if_start_hz
                <= self.pilot_if_center_frequency_hz
                <= self.captured_if_stop_hz
            )
        ):
            raise ValueError("mixed native stream RF/IF authority does not close")
        return self


class StandardNativePromotionAuthorityV2(ContractModel):
    """Closed Current authority for one unequal-rate RecordingManifestV4 run."""

    schema_version: Literal[2] = 2
    source_manifest_schema_version: Literal[4] = 4
    source_manifest_digest: Sha256Digest
    pipeline_definition: PipelineDefinitionV1
    pipeline_definition_id: Sha256Digest
    session_id: Identifier
    run_id: Identifier
    input_manifest_digest: Sha256Digest
    pipeline_release_id: Identifier
    expanded_plan_digest: Sha256Digest
    raw_integrity_attestation_digest: Sha256Digest
    release_authority_digest: Sha256Digest
    subject_binding_inventory_digest: Sha256Digest
    terminal_products: Annotated[
        tuple[StandardNativeTerminalProductRefV1, ...],
        Field(min_length=1, max_length=64),
    ]
    terminal_product_inventory_digest: Sha256Digest
    dwell_class: Literal["mixed_2p5_5", "mixed_2p5_10"]
    stream_authorities: Annotated[
        tuple[StandardNativeMixedStreamAuthorityV1, StandardNativeMixedStreamAuthorityV1],
        Field(min_length=2, max_length=2),
    ]
    capture_plan_digest: Sha256Digest
    capture_hardware_binding_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _authority_is_closed(self) -> Self:
        _validate_native_promotion_common(self)
        identities = tuple((item.stream_id, item.radio_id) for item in self.stream_authorities)
        if identities != tuple(sorted(identities)) or len(set(identities)) != 2:
            raise ValueError("mixed native stream authorities must be unique and ordered")
        expected_rates = {
            "mixed_2p5_5": {2_500_000, 5_000_000},
            "mixed_2p5_10": {2_500_000, 10_000_000},
        }[self.dwell_class]
        if {item.sample_rate_hz for item in self.stream_authorities} != expected_rates:
            raise ValueError("mixed native promotion rate pair disagrees with its dwell class")
        expected_content_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        )
        if self.content_digest != expected_content_digest:
            raise ValueError("mixed native promotion authority content digest does not match")
        return self


class StandardNativeProductionStreamAuthorityV1(ContractModel):
    """One exact per-radio source leg authorized by the production policy."""

    schema_version: Literal[1] = 1
    stream_id: Identifier
    radio_id: Identifier
    profile_name: Identifier
    profile_revision_digest: Sha256Digest
    receiver_ids: tuple[Literal[0, 1], ...]
    gain_controller_mode: Literal["tandem_hold", "tandem_auto"]
    gain_controller_request_digest: Sha256Digest
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: Literal["lower", "upper"]
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000]
    rf_bandwidth_hz: Annotated[int, Field(gt=0)]
    tuned_center_frequency_hz: Annotated[int, Field(gt=0)]
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]
    logical_sample_count: Annotated[int, Field(gt=0)]
    validity_inventory_digest: Sha256Digest
    timeline_digest: Sha256Digest
    metadata_abi_version: Literal[3]

    @field_validator("receiver_ids")
    @classmethod
    def _receiver_ids_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value not in {(0,), (1,), (0, 1)}:
            raise ValueError("production stream receiver inventory is not canonical")
        return value

    @model_validator(mode="after")
    def _stream_authority_is_closed(self) -> Self:
        expected_center_hz = starlink_maximum_coverage_if_center_frequency_hz(
            self.starlink_channel,
            self.starlink_edge,
            bandwidth_hz=self.rf_bandwidth_hz,
        )
        expected_channel_bounds = starlink_channel_if_bounds_hz(self.starlink_channel)
        if (
            self.rf_bandwidth_hz != self.sample_rate_hz
            or self.pilot_if_center_frequency_hz
            != starlink_edge_if_center_frequency_hz(
                self.starlink_channel,
                self.starlink_edge,
            )
            or (self.channel_if_start_hz, self.channel_if_stop_hz) != expected_channel_bounds
            or self.tuned_center_frequency_hz != expected_center_hz
            or self.captured_if_stop_hz - self.captured_if_start_hz != self.rf_bandwidth_hz
            or self.tuned_center_frequency_hz * 2
            != self.captured_if_start_hz + self.captured_if_stop_hz
            or self.captured_if_start_hz < self.channel_if_start_hz
            or self.captured_if_stop_hz > self.channel_if_stop_hz
            or not (
                self.captured_if_start_hz
                <= self.pilot_if_center_frequency_hz
                <= self.captured_if_stop_hz
            )
        ):
            raise ValueError("production native stream RF/IF authority does not close")
        return self


class StandardNativePromotionAuthorityV3(ContractModel):
    """Closed Current authority for one production RecordingManifestV5 run."""

    schema_version: Literal[3] = 3
    source_manifest_schema_version: Literal[5] = 5
    source_manifest_digest: Sha256Digest
    pipeline_definition: PipelineDefinitionV1
    pipeline_definition_id: Sha256Digest
    session_id: Identifier
    run_id: Identifier
    input_manifest_digest: Sha256Digest
    pipeline_release_id: Identifier
    expanded_plan_digest: Sha256Digest
    raw_integrity_attestation_digest: Sha256Digest
    release_authority_digest: Sha256Digest
    subject_binding_inventory_digest: Sha256Digest
    terminal_products: Annotated[
        tuple[StandardNativeTerminalProductRefV1, ...],
        Field(min_length=1, max_length=64),
    ]
    terminal_product_inventory_digest: Sha256Digest
    dwell_class: Literal[
        "both_2p5",
        "both_5",
        "mixed_2p5_5",
        "mixed_2p5_10",
        "mixed_2p5_15",
        "mixed_2p5_20",
    ]
    tuning_branch: Literal["same", "same_channel_opposite_edge", "independent"]
    scheduled_intent_digest: Sha256Digest
    stream_authorities: Annotated[
        tuple[
            StandardNativeProductionStreamAuthorityV1,
            StandardNativeProductionStreamAuthorityV1,
        ],
        Field(min_length=2, max_length=2),
    ]
    capture_plan_digest: Sha256Digest
    capture_hardware_binding_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _authority_is_closed(self) -> Self:
        _validate_native_promotion_common(self)
        identities = tuple((item.stream_id, item.radio_id) for item in self.stream_authorities)
        if identities != tuple(sorted(identities)) or len(set(identities)) != 2:
            raise ValueError("production native stream authorities must be unique and ordered")
        expected_rates = {
            "both_2p5": [2_500_000, 2_500_000],
            "both_5": [5_000_000, 5_000_000],
            "mixed_2p5_5": [2_500_000, 5_000_000],
            "mixed_2p5_10": [2_500_000, 10_000_000],
            "mixed_2p5_15": [2_500_000, 15_000_000],
            "mixed_2p5_20": [2_500_000, 20_000_000],
        }[self.dwell_class]
        observed_rates = sorted(item.sample_rate_hz for item in self.stream_authorities)
        if observed_rates != expected_rates:
            raise ValueError("production promotion rate pair disagrees with its dwell class")
        mixed = self.dwell_class.startswith("mixed_")
        for item in self.stream_authorities:
            expected_receiver_count = 1 if mixed and item.sample_rate_hz > 5_000_000 else 2
            if len(item.receiver_ids) != expected_receiver_count:
                raise ValueError("production promotion receiver geometry disagrees with rate class")
        if mixed and self.tuning_branch != "same":
            raise ValueError("mixed production promotion requires same-target tuning")
        expected_content_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        )
        if self.content_digest != expected_content_digest:
            raise ValueError("production promotion authority content digest does not match")
        return self


class AnalysisRunManifestV3(ContractModel):
    """Promotion-capable Standard-native run with exact terminal authority."""

    schema_version: Literal[3] = 3
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    pipeline_lane: Literal["standard"] = "standard"
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]
    promotion_authority: StandardNativePromotionAuthorityV1
    content_digest: Sha256Digest

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        return AnalysisRunManifestV1._jobs_are_canonical(value)

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        return AnalysisRunManifestV1._products_are_canonical(value)

    @model_validator(mode="after")
    def _promotion_manifest_is_closed(self) -> Self:
        jobs = {(item.stage_key, item.scope_key) for item in self.jobs}
        if any((item.stage_key, item.scope_key) not in jobs for item in self.products):
            raise ValueError("run manifest product has no corresponding job")
        product_ids = tuple(item.product_id for item in self.products)
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("promotion run manifest product IDs must be unique")
        authority = self.promotion_authority
        outer_identity = (
            self.session_id,
            self.run_id,
            self.input_manifest_digest,
            self.pipeline_release_id,
            self.trigger,
            self.promotion_policy,
            self.processing_status,
        )
        authority_identity = (
            authority.session_id,
            authority.run_id,
            authority.input_manifest_digest,
            authority.pipeline_release_id,
            authority.trigger,
            authority.promotion_policy,
            authority.processing_status,
        )
        if authority_identity != outer_identity:
            raise ValueError("native promotion authority belongs to another run")
        terminal_ids = {item.product_id for item in authority.terminal_products}
        selected_products = tuple(
            (
                item.product_id,
                item.stage_key,
                item.scope_key,
                item.kind,
                item.product_schema_version,
                item.role,
                item.status,
                item.digest,
            )
            for item in self.products
            if item.product_id in terminal_ids
        )
        authorized_products = tuple(
            (
                item.product_id,
                item.stage_key,
                item.scope_key,
                item.kind,
                item.product_schema_version,
                item.role,
                item.status,
                item.digest,
            )
            for item in authority.terminal_products
        )
        if selected_products != authorized_products:
            raise ValueError(
                "native promotion terminal products differ from the sealed run inventory"
            )
        expected_content_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        )
        if self.content_digest != expected_content_digest:
            raise ValueError("promotion run manifest content digest does not match")
        return self


class AnalysisRunManifestV4(ContractModel):
    """Promotion-capable unequal-rate Standard-native run manifest."""

    schema_version: Literal[4] = 4
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    pipeline_lane: Literal["standard"] = "standard"
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]
    promotion_authority: StandardNativePromotionAuthorityV2
    content_digest: Sha256Digest

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        return AnalysisRunManifestV1._jobs_are_canonical(value)

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        return AnalysisRunManifestV1._products_are_canonical(value)

    @model_validator(mode="after")
    def _promotion_manifest_is_closed(self) -> Self:
        _validate_promotion_manifest_common(self, self.promotion_authority)
        return self


class AnalysisRunManifestV5(ContractModel):
    """Promotion-capable production-policy Standard-native run manifest."""

    schema_version: Literal[5] = 5
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Literal["new_capture", "reprocess"]
    pipeline_lane: Literal["standard"] = "standard"
    promotion_policy: Literal["current"] = "current"
    processing_status: Literal["succeeded"] = "succeeded"
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]
    promotion_authority: StandardNativePromotionAuthorityV3
    content_digest: Sha256Digest

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        return AnalysisRunManifestV1._jobs_are_canonical(value)

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        return AnalysisRunManifestV1._products_are_canonical(value)

    @model_validator(mode="after")
    def _promotion_manifest_is_closed(self) -> Self:
        _validate_promotion_manifest_common(self, self.promotion_authority)
        return self


def _validate_native_promotion_common(
    authority: StandardNativePromotionAuthorityV2 | StandardNativePromotionAuthorityV3,
) -> None:
    definition = authority.pipeline_definition
    if (
        authority.pipeline_definition_id != definition.definition_id
        or definition.lane is not PipelineLane.STANDARD
        or definition.product_namespace != "standard"
        or not definition.automatic_eligible
        or not definition.promotion_allowed
        or authority.pipeline_release_id != definition.executable_git_sha
        or authority.source_manifest_digest != authority.input_manifest_digest
    ):
        raise ValueError("mixed native promotion definition or source authority is invalid")
    identities = tuple(
        (item.stage_key, item.scope_key, item.kind, item.product_schema_version)
        for item in authority.terminal_products
    )
    product_ids = tuple(item.product_id for item in authority.terminal_products)
    if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
        raise ValueError("mixed native terminal products must be unique and ordered")
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("mixed native terminal product IDs must be unique")
    if authority.terminal_product_inventory_digest != canonical_digest(
        tuple(item.model_dump(mode="json") for item in authority.terminal_products)
    ):
        raise ValueError("mixed native terminal inventory digest does not match")


def _validate_promotion_manifest_common(
    manifest: AnalysisRunManifestV4 | AnalysisRunManifestV5,
    authority: StandardNativePromotionAuthorityV2 | StandardNativePromotionAuthorityV3,
) -> None:
    jobs = {(item.stage_key, item.scope_key) for item in manifest.jobs}
    if any((item.stage_key, item.scope_key) not in jobs for item in manifest.products):
        raise ValueError("run manifest product has no corresponding job")
    product_ids = tuple(item.product_id for item in manifest.products)
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("promotion run manifest product IDs must be unique")
    if (
        authority.session_id,
        authority.run_id,
        authority.input_manifest_digest,
        authority.pipeline_release_id,
        authority.trigger,
        authority.promotion_policy,
        authority.processing_status,
    ) != (
        manifest.session_id,
        manifest.run_id,
        manifest.input_manifest_digest,
        manifest.pipeline_release_id,
        manifest.trigger,
        manifest.promotion_policy,
        manifest.processing_status,
    ):
        raise ValueError("mixed native promotion authority belongs to another run")
    terminal_ids = {item.product_id for item in authority.terminal_products}
    selected = tuple(
        (
            item.product_id,
            item.stage_key,
            item.scope_key,
            item.kind,
            item.product_schema_version,
            item.role,
            item.status,
            item.digest,
        )
        for item in manifest.products
        if item.product_id in terminal_ids
    )
    authorized = tuple(
        (
            item.product_id,
            item.stage_key,
            item.scope_key,
            item.kind,
            item.product_schema_version,
            item.role,
            item.status,
            item.digest,
        )
        for item in authority.terminal_products
    )
    if selected != authorized:
        raise ValueError("mixed native terminal products differ from sealed run inventory")
    if manifest.content_digest != canonical_digest(
        manifest.model_dump(mode="json", exclude={"content_digest"})
    ):
        raise ValueError("mixed promotion run manifest content digest does not match")


AnalysisRunManifest = (
    AnalysisRunManifestV1
    | AnalysisRunManifestV2
    | AnalysisRunManifestV3
    | AnalysisRunManifestV4
    | AnalysisRunManifestV5
)


def parse_analysis_run_manifest(document: object) -> AnalysisRunManifest:
    if not isinstance(document, dict):
        raise ValueError("analysis run manifest must be a JSON object")
    version = document.get("schema_version")
    if version == 1:
        return AnalysisRunManifestV1.model_validate(document)
    if version == 2:
        return AnalysisRunManifestV2.model_validate(document)
    if version == 3:
        return AnalysisRunManifestV3.model_validate(document)
    if version == 4:
        return AnalysisRunManifestV4.model_validate(document)
    if version == 5:
        return AnalysisRunManifestV5.model_validate(document)
    raise ValueError("analysis run manifest schema version is unsupported")
