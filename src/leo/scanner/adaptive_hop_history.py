"""Additive adaptive history views: actual visits, never inferred fixed sweeps."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import AdaptiveMode, AdaptiveModel, ChoiceReason, SessionId
from leo.scanner.models import ScanTarget

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
VisitCount = Annotated[int, Field(strict=True, ge=0, le=2500)]
TargetIndex = Annotated[int, Field(strict=True, ge=0, le=7)]


class AdaptiveHopCoverageV1(AdaptiveModel):
    target_index: TargetIndex
    target: ScanTarget
    retained_visits: VisitCount
    valid_seconds: Seconds
    allocation_ppm: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] | None
    # Complete retained visits only; null means fewer than two observations.
    maximum_revisit_seconds: Seconds | None
    # Includes the beginning and end of the capture, without extrapolation.
    maximum_unobserved_seconds: Seconds | None


class AdaptiveHopHistoryItemV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_history_item"] = "adaptive_hop_history_item"
    session_id: SessionId
    input_manifest_sha256: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    mode: AdaptiveMode
    policy_generation: U64
    recorded_at: datetime
    finalized_at: datetime
    captured_at: datetime | None
    utc_qualified: bool
    utc_bracket_width_ms: Seconds | None
    nominal_duration_seconds: Literal[300] = 300
    valid_visit_ms: Literal[120] = 120
    sample_rate_hz: Literal[2_500_000, 5_000_000]
    bandwidth_hz: Literal[2_500_000, 5_000_000]
    started_visits: VisitCount
    retained_visits: VisitCount
    source_span_attested: bool
    source_span_seconds: Seconds | None
    valid_duty_ppm: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] | None
    capture_qualified: bool
    terminal_state: Literal["completed", "cancelled"]
    restoration_status: Literal["restored"] = "restored"
    fallback_choices: VisitCount
    target_coverage: Annotated[tuple[AdaptiveHopCoverageV1, ...], Field(min_length=8, max_length=8)]
    analysis_state: Literal["not_integrated"] = "not_integrated"

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (
            self.finalized_at < self.recorded_at
            or self.sample_rate_hz != self.bandwidth_hz
            or self.retained_visits > self.started_visits
            or self.retained_visits
            != max(0, self.started_visits - (self.terminal_state == "cancelled"))
            or self.source_span_attested != bool(self.started_visits)
            or self.policy_generation == 0
            or self.fallback_choices > self.started_visits
            or tuple(c.target_index for c in self.target_coverage) != tuple(range(8))
            or sum(c.retained_visits for c in self.target_coverage) != self.retained_visits
            or self.source_span_attested != (self.source_span_seconds is not None)
            or self.source_span_attested != (self.valid_duty_ppm is not None)
            or (self.utc_qualified and self.captured_at is None)
            or (
                self.capture_qualified
                and (not self.source_span_attested or self.terminal_state != "completed")
            )
        ):
            raise ValueError("adaptive history summary disagrees with capture evidence")
        for row in self.target_coverage:
            if (
                row.target.channel != row.target_index % 4 + 1
                or row.target.edge != ("lower" if row.target_index < 4 else "upper")
                or row.valid_seconds
                != row.retained_visits * (self.sample_rate_hz * 120 // 1000) / self.sample_rate_hz
                or row.allocation_ppm
                != (
                    row.retained_visits * 1_000_000 // self.retained_visits
                    if self.retained_visits
                    else None
                )
                or (row.maximum_revisit_seconds is not None) != (row.retained_visits >= 2)
                or (row.maximum_unobserved_seconds is not None) != self.source_span_attested
            ):
                raise ValueError("adaptive coverage disagrees with retained IQ")
        return self


class AdaptiveHopVisitViewV1(AdaptiveModel):
    visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    target_index: TargetIndex
    retained: bool
    invalid_start_seconds: Seconds
    valid_start_seconds: Seconds
    valid_end_seconds: Seconds | None
    valid_start_counter: U64
    valid_end_counter: U64 | None
    decision_counter: U64
    basis_visit: Annotated[int, Field(strict=True, ge=0, lt=2500)] | None
    proposed_target_index: TargetIndex
    reason: ChoiceReason
    active_mask: Annotated[int, Field(strict=True, ge=0, le=255)]
    quiet_mask: Annotated[int, Field(strict=True, ge=0, le=255)]
    # These two fields describe the PROPOSED target, including in shadow mode.
    consecutive_misses: Annotated[int, Field(strict=True, ge=0, le=3)]
    cooldown_remaining_seconds: Seconds

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (
            self.retained != (self.valid_end_counter is not None)
            or self.retained != (self.valid_end_seconds is not None)
            or self.invalid_start_seconds > self.valid_start_seconds
            or (
                self.valid_end_seconds is not None
                and self.valid_end_seconds <= self.valid_start_seconds
            )
            or (
                self.valid_end_counter is not None
                and self.valid_end_counter <= self.valid_start_counter
            )
            or self.decision_counter > self.valid_start_counter
            or self.active_mask & self.quiet_mask
            or (self.basis_visit is not None and self.basis_visit >= self.visit_index)
        ):
            raise ValueError("adaptive visit view has inconsistent source evidence")
        return self


class AdaptiveHopHistoryPageV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_history_page"] = "adaptive_hop_history_page"
    cursor: Annotated[int, Field(strict=True, ge=0)]
    limit: Annotated[int, Field(strict=True, ge=1, le=20)]
    total: Annotated[int, Field(strict=True, ge=0)]
    next_cursor: Annotated[int, Field(strict=True, ge=0)] | None
    items: Annotated[tuple[AdaptiveHopHistoryItemV1, ...], Field(max_length=20)]

    @model_validator(mode="after")
    def _page_bound(self) -> Self:
        if (
            len(self.items) != min(self.limit, max(0, self.total - self.cursor))
            or self.next_cursor
            != (self.cursor + self.limit if self.cursor + self.limit < self.total else None)
            or len({item.session_id for item in self.items}) != len(self.items)
        ):
            raise ValueError("adaptive history page inventory is inconsistent")
        return self


class AdaptiveHopSessionDetailV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_session_detail"] = "adaptive_hop_session_detail"
    capture: AdaptiveHopHistoryItemV1
    source_origin_counter: U64 | None
    visits: Annotated[tuple[AdaptiveHopVisitViewV1, ...], Field(max_length=2500)]

    @model_validator(mode="after")
    def _bound(self) -> Self:
        if (
            self.capture.source_span_attested != (self.source_origin_counter is not None)
            or len(self.visits) != self.capture.started_visits
            or tuple(v.visit_index for v in self.visits) != tuple(range(len(self.visits)))
            or tuple(v.retained for v in self.visits)
            != tuple(i < self.capture.retained_visits for i in range(len(self.visits)))
        ):
            raise ValueError("adaptive detail differs from started/retained inventory")
        if self.source_origin_counter is not None:
            rate = self.capture.sample_rate_hz
            for visit in self.visits:
                if (
                    visit.valid_start_seconds
                    != (visit.valid_start_counter - self.source_origin_counter) / rate
                    or (
                        self.capture.mode == "shadow"
                        and visit.target_index != visit.visit_index % 8
                    )
                    or (
                        self.capture.mode == "adaptive"
                        and visit.target_index != visit.proposed_target_index
                    )
                    or (
                        visit.valid_end_counter is not None
                        and (
                            visit.valid_end_counter - visit.valid_start_counter
                            != rate * 120 // 1000
                            or visit.valid_end_seconds
                            != (visit.valid_end_counter - self.source_origin_counter) / rate
                        )
                    )
                ):
                    raise ValueError("adaptive detail source times or actual targets differ")
            if tuple(
                sum(v.retained and v.target_index == i for v in self.visits) for i in range(8)
            ) != tuple(c.retained_visits for c in self.capture.target_coverage):
                raise ValueError("adaptive detail coverage differs from actual retained visits")
        return self


class AdaptiveHopPresentationReader(Protocol):
    def page(self, *, cursor: int, limit: int) -> AdaptiveHopHistoryPageV1: ...

    def detail(self, session_id: str) -> AdaptiveHopSessionDetailV1 | None: ...
