"""Native single-RX history with host computation distinct from policy evidence."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.scanner.adaptive_hop import AdaptiveModel
from leo.scanner.adaptive_hop_history import (
    AdaptiveHopHistoryItemV1,
    AdaptiveHopHistoryPageV1,
    AdaptiveHopSessionDetailV1,
    Seconds,
    VisitCount,
)
from leo.scanner.host_adaptive import HostDecisionConfigurationV1, HostDecisionNumericsV1


class HostFeedbackSummaryV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    complete_visits: VisitCount
    healthy: VisitCount
    degraded: VisitCount
    unknown_feedback: VisitCount
    accepted: VisitCount
    source_ended: VisitCount
    rejected: VisitCount
    not_submitted: VisitCount
    maximum_host_result_age_ms: Seconds | None
    maximum_feedback_call_ms: Seconds | None
    first_feedback_error: Annotated[str, Field(min_length=1, max_length=2048)] | None

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if (
            self.healthy + self.degraded != self.complete_visits
            or self.accepted + self.source_ended + self.rejected + self.not_submitted
            != self.complete_visits
            or self.unknown_feedback > self.complete_visits
            or (self.maximum_host_result_age_ms is not None) != bool(self.complete_visits)
            or (self.maximum_feedback_call_ms is not None)
            != bool(self.complete_visits - self.not_submitted)
            or (self.first_feedback_error is not None) != bool(self.rejected + self.not_submitted)
        ):
            raise ValueError("host feedback summary inventory is inconsistent")
        return self


class HostAdaptiveHistoryItemV2(AdaptiveHopHistoryItemV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    sample_rate_hz: Literal[10_000_000] = 10_000_000  # type: ignore[assignment]
    bandwidth_hz: Literal[10_000_000] = 10_000_000  # type: ignore[assignment]
    analysis_state: Literal["separate_product"] = "separate_product"  # type: ignore[assignment]
    radio_serial: Annotated[str, Field(min_length=1, max_length=128)]
    physical_receiver: Literal[0, 1]
    decision_configuration: HostDecisionConfigurationV1
    host_feedback: HostFeedbackSummaryV1

    @model_validator(mode="after")
    def _host_binding(self) -> Self:
        if self.host_feedback.complete_visits != self.retained_visits:
            raise ValueError("host feedback differs from retained native visits")
        if self.capture_qualified and (
            self.valid_duty_ppm is None or self.valid_duty_ppm < 950_000
        ):
            raise ValueError("native adaptive capture does not meet its qualification duty floor")
        return self


class HostDecisionViewV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    numerics: HostDecisionNumericsV1 | None
    health: Literal["healthy", "queue_overflow", "detector_failure", "expired"]
    failure: Annotated[str, Field(min_length=1, max_length=2048)] | None
    feedback_outcome: Literal["unknown", "detected", "not_detected"]
    feedback_disposition: Literal["accepted", "source_ended", "rejected", "not_submitted"]
    feedback_error: Annotated[str, Field(min_length=1, max_length=2048)] | None
    host_result_age_ms: Seconds
    worker_elapsed_ms: Seconds | None
    feedback_call_ms: Seconds | None


class HostAdaptiveSessionDetailV2(AdaptiveHopSessionDetailV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    capture: HostAdaptiveHistoryItemV2
    host_decisions: Annotated[tuple[HostDecisionViewV1, ...], Field(max_length=2500)]

    @model_validator(mode="after")
    def _decision_inventory(self) -> Self:
        if tuple(d.visit_index for d in self.host_decisions) != tuple(
            range(self.capture.retained_visits)
        ):
            raise ValueError("host decision view must cover every retained visit in order")
        return self


class AdaptiveHistoryPageV2(AdaptiveHopHistoryPageV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    items: Annotated[
        tuple[AdaptiveHopHistoryItemV1 | HostAdaptiveHistoryItemV2, ...], Field(max_length=20)
    ]


class AdaptiveHistoryReaderV2(Protocol):
    def page_v2(self, *, cursor: int, limit: int) -> AdaptiveHistoryPageV2: ...
    def detail_v2(
        self, session_id: str
    ) -> AdaptiveHopSessionDetailV1 | HostAdaptiveSessionDetailV2 | None: ...
