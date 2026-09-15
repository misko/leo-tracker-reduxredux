"""Native single-RX metrics/figure publication status, distinct from legacy V1."""

from typing import Annotated, Literal

from pydantic import Field

from leo.scanner.adaptive_hop_presentation import (
    AdaptiveHopAnalysisStatusV1,
    AdaptiveHopOverviewManifestV1,
)
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisConfigurationV2,
    HostAdaptiveAnalysisConfigurationV3,
)


class HostAdaptiveOverviewManifestV2(AdaptiveHopOverviewManifestV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    presentation_id: Literal["host-adaptive-native-10m-overview-v2"] = (  # type: ignore[assignment]
        "host-adaptive-native-10m-overview-v2"  # type: ignore[assignment]
    )
    selected_observation_count: Annotated[int, Field(strict=True, ge=0, le=2500)]


class HostAdaptiveAnalysisStatusV2(AdaptiveHopAnalysisStatusV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    configuration: HostAdaptiveAnalysisConfigurationV2
    overview: HostAdaptiveOverviewManifestV2 | None


class HostAdaptiveOverviewManifestV3(HostAdaptiveOverviewManifestV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    presentation_id: Literal["host-adaptive-native-15m-20m-overview-v3"] = (  # type: ignore[assignment]
        "host-adaptive-native-15m-20m-overview-v3"  # type: ignore[assignment]
    )


class HostAdaptiveAnalysisStatusV3(HostAdaptiveAnalysisStatusV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    configuration: HostAdaptiveAnalysisConfigurationV3
    overview: HostAdaptiveOverviewManifestV3 | None
