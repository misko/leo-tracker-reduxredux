"""Closed native-10M adaptive analysis bindings, checkpoints and metrics."""

from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field

from leo.scanner.adaptive_hop import (
    AdaptiveHopReceiptV1,
    AdaptiveHopReceiptV2,
    AdaptiveHopReceiptV3,
    AdaptiveHopReceiptV4,
    AdaptiveHopReceiptV5,
    AdaptiveHopReceiptV6,
)
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    DualRx10mAdaptiveHopAnalysisConfigurationV2,
    Feature103AnalysisConfigurationV3,
    Feature104AnalysisConfigurationV4,
    VariableDwellAnalysisConfigurationV5,
)
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
    DualRx10mAdaptiveAnalysisBindingV5,
    EdgeAdaptiveAnalysisBindingV4,
    Feature103AnalysisBindingV6,
    Feature104AnalysisBindingV7,
    VariableDwellAnalysisBindingV8,
)
from leo.scanner.host_adaptive import (
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostAdaptiveHopReceiptV4,
    HostAdaptiveHopReceiptV5,
)
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisConfigurationV2,
    HostAdaptiveAnalysisConfigurationV3,
    HostAdaptiveVisitAnalysisV2,
    HostAdaptiveVisitAnalysisV3,
)


class HostAdaptiveAnalysisBindingV2(AdaptiveHopAnalysisBindingV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    _visit_model: ClassVar[type[HostAdaptiveVisitAnalysisV2]] = HostAdaptiveVisitAnalysisV2
    receipt: HostAdaptiveHopReceiptV2
    configuration: HostAdaptiveAnalysisConfigurationV2


class HostAdaptiveAnalysisBindingV4(HostAdaptiveAnalysisBindingV2):
    """Sparse native-10M receipt binding; retains V2 numerical products."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    receipt: HostAdaptiveHopReceiptV5  # type: ignore[assignment]


class HostAdaptiveVisitReferenceV2(AdaptiveHopVisitReferenceV1):
    schema_version: Literal[2] = 2
    _filename_version: ClassVar[int] = 2
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v2\.json\.zst$")]
    probe_count: Annotated[int, Field(strict=True, ge=1, le=11)]
    candidate_count: Annotated[int, Field(strict=True, ge=0, le=176)]
    fractional_candidate_count: Annotated[int, Field(strict=True, ge=0, le=176)]
    passed_fractional_candidate_count: Annotated[int, Field(strict=True, ge=0, le=176)]


class HostAdaptiveMetricsManifestV2(AdaptiveHopMetricsManifestV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    configuration: HostAdaptiveAnalysisConfigurationV2
    visits: Annotated[tuple[HostAdaptiveVisitReferenceV2, ...], Field(max_length=2500)]


class HostAdaptiveAnalysisBindingV3(HostAdaptiveAnalysisBindingV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    _visit_model: ClassVar[type[HostAdaptiveVisitAnalysisV3]] = HostAdaptiveVisitAnalysisV3
    receipt: HostAdaptiveHopReceiptV3 | HostAdaptiveHopReceiptV4
    configuration: HostAdaptiveAnalysisConfigurationV3


class HostAdaptiveVisitReferenceV3(HostAdaptiveVisitReferenceV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    _filename_version: ClassVar[int] = 3
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v3\.json\.zst$")]


class HostAdaptiveMetricsManifestV3(HostAdaptiveMetricsManifestV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    configuration: HostAdaptiveAnalysisConfigurationV3
    visits: Annotated[tuple[HostAdaptiveVisitReferenceV3, ...], Field(max_length=2500)]


def bind_actual_visit_analysis(
    receipt: AdaptiveHopReceiptV1, *, input_manifest_sha256: str, probe_stride_ms: int = 10
) -> AdaptiveHopAnalysisBindingV1:
    """Resolve the exact persisted major for the supplied native recording."""
    if isinstance(
        receipt,
        (AdaptiveHopReceiptV3, AdaptiveHopReceiptV4, AdaptiveHopReceiptV5, AdaptiveHopReceiptV6),
    ):
        config: Any = (
            VariableDwellAnalysisConfigurationV5
            if isinstance(receipt, AdaptiveHopReceiptV6)
            else Feature104AnalysisConfigurationV4
            if isinstance(receipt, AdaptiveHopReceiptV5)
            else Feature103AnalysisConfigurationV3
            if isinstance(receipt, AdaptiveHopReceiptV4)
            else DualRx10mAdaptiveHopAnalysisConfigurationV2
        )
        model: Any = (
            VariableDwellAnalysisBindingV8
            if isinstance(receipt, AdaptiveHopReceiptV6)
            else Feature104AnalysisBindingV7
            if isinstance(receipt, AdaptiveHopReceiptV5)
            else Feature103AnalysisBindingV6
            if isinstance(receipt, AdaptiveHopReceiptV4)
            else DualRx10mAdaptiveAnalysisBindingV5
        )
        return model(
            receipt=receipt,
            input_manifest_sha256=input_manifest_sha256,
            configuration=config.model_validate(
                dict(
                    sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
                    probe_stride_ms=probe_stride_ms,
                )
            ),
        )
    wide = isinstance(receipt, HostAdaptiveHopReceiptV3)
    host = isinstance(receipt, HostAdaptiveHopReceiptV2)
    edge = isinstance(receipt, AdaptiveHopReceiptV2)
    configuration_model: type[AdaptiveHopAnalysisConfigurationV1] = (
        HostAdaptiveAnalysisConfigurationV3
        if wide
        else HostAdaptiveAnalysisConfigurationV2
        if host
        else AdaptiveHopAnalysisConfigurationV1
    )
    binding_model: type[AdaptiveHopAnalysisBindingV1] = (
        HostAdaptiveAnalysisBindingV4
        if isinstance(receipt, HostAdaptiveHopReceiptV5)
        else HostAdaptiveAnalysisBindingV3
        if wide
        else HostAdaptiveAnalysisBindingV2
        if host
        else EdgeAdaptiveAnalysisBindingV4
        if edge
        else AdaptiveHopAnalysisBindingV1
    )
    return binding_model(
        receipt=receipt,
        input_manifest_sha256=input_manifest_sha256,
        configuration=configuration_model(
            sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
            receiver_ids=receipt.plan.geometry.receiver_ids,
            probe_stride_ms=probe_stride_ms,
        ),
    )
