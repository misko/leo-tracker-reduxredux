"""Additive read-model contracts for published persistent-hop sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import Field, model_validator

from leo.scanner.models import ScannerModel
from leo.scanner.persistent_hop import (
    PersistentHopCaptureOutcome,
    PersistentHopTargetCoverageV1,
    PersistentHopTerminalReason,
)


class PersistentHopHistoryItemV1(ScannerModel):
    """One immutable capture summary without inventing legacy scanner analysis."""

    schema_version: Literal[1] = 1
    captured_at: datetime
    finalized_at: datetime
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    nominal_duration_seconds: Literal[300] = 300
    valid_visit_ms: Literal[120] = 120
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    bandwidth_hz: Literal[2_500_000, 5_000_000]
    visit_count: Annotated[int, Field(ge=0, le=2_500)]
    target_coverage: Annotated[
        tuple[PersistentHopTargetCoverageV1, ...], Field(min_length=8, max_length=8)
    ]
    capture_outcome: PersistentHopCaptureOutcome
    terminal_state: Literal["completed", "cancelled", "failed"]
    terminal_reason: PersistentHopTerminalReason
    valid_duty_ppm: Annotated[int, Field(ge=0, le=1_000_000)]
    continuity_attested: bool
    restoration_status: Literal["restored", "failed"]
    qualified: bool
    analysis_state: Literal["pending_backpressure"] = "pending_backpressure"
    analysis_reason: Literal[
        "Full GLRT/CFO analysis awaits a bounded backpressure-aware worker."
    ] = "Full GLRT/CFO analysis awaits a bounded backpressure-aware worker."

    @model_validator(mode="after")
    def _summary_is_truthful(self) -> PersistentHopHistoryItemV1:
        if self.finalized_at < self.captured_at:
            raise ValueError("persistent-hop history finalization precedes capture")
        if self.bandwidth_hz != self.sample_rate_hz:
            raise ValueError("persistent-hop history bandwidth disagrees with sample rate")
        if tuple(item.target_index for item in self.target_coverage) != tuple(range(8)):
            raise ValueError("persistent-hop history coverage is not in target order")
        if sum(item.visit_count for item in self.target_coverage) != self.visit_count:
            raise ValueError("persistent-hop history coverage disagrees with visit count")
        if self.qualified and (
            self.capture_outcome != "complete"
            or self.terminal_state != "completed"
            or not self.continuity_attested
            or self.restoration_status != "restored"
        ):
            raise ValueError("qualified persistent-hop history lacks terminal evidence")
        return self


class PersistentHopHistoryPageV1(ScannerModel):
    """A bounded newest-publication-first persistent-hop history page."""

    schema_version: Literal[1] = 1
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=20)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[PersistentHopHistoryItemV1, ...]


class PersistentHopHistoryReader(Protocol):
    """Narrow API port for immutable persistent-hop capture summaries."""

    def page(self, *, cursor: int, limit: int) -> PersistentHopHistoryPageV1: ...
