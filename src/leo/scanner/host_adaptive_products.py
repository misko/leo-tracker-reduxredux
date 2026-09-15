"""Closed native-10M adaptive analysis bindings, checkpoints and metrics."""

from typing import Annotated, ClassVar, Literal

from pydantic import Field

from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
)
from leo.scanner.host_adaptive import HostAdaptiveHopReceiptV2, HostAdaptiveHopReceiptV3
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
    receipt: HostAdaptiveHopReceiptV3
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
    wide = isinstance(receipt, HostAdaptiveHopReceiptV3)
    host = isinstance(receipt, HostAdaptiveHopReceiptV2)
    configuration_model: type[AdaptiveHopAnalysisConfigurationV1] = (
        HostAdaptiveAnalysisConfigurationV3
        if wide
        else HostAdaptiveAnalysisConfigurationV2
        if host
        else AdaptiveHopAnalysisConfigurationV1
    )
    binding_model: type[AdaptiveHopAnalysisBindingV1] = (
        HostAdaptiveAnalysisBindingV3
        if wide
        else HostAdaptiveAnalysisBindingV2
        if host
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
