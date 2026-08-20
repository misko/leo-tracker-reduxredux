"""Versioned scanner configuration and report contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leo.contracts.states import GainMode, StarlinkEdge

_CURRENT_RF_CENTERS_HZ = (
    (1, StarlinkEdge.LOWER, 10_709_687_500),
    (1, StarlinkEdge.UPPER, 10_940_312_500),
    (2, StarlinkEdge.LOWER, 10_959_687_500),
    (2, StarlinkEdge.UPPER, 11_190_312_500),
    (3, StarlinkEdge.LOWER, 11_209_687_500),
    (3, StarlinkEdge.UPPER, 11_440_312_500),
    (4, StarlinkEdge.LOWER, 11_459_687_500),
    (4, StarlinkEdge.UPPER, 11_690_312_500),
)


class ScannerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScanTarget(ScannerModel):
    channel: Annotated[int, Field(ge=1)]
    edge: StarlinkEdge
    rf_center_hz: Annotated[int, Field(gt=0)]
    if_center_hz: Annotated[int, Field(gt=0)]


class ScannerConfiguration(ScannerModel):
    schema_version: Literal[1] = 1
    band_plan_id: str = "starlink-low-ch1-ch4-v1"
    lnb_lo_hz: Annotated[int, Field(gt=0)] = 9_750_000_000
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    bandwidth_hz: Annotated[int, Field(gt=0)] = 2_500_000
    dwell_ms: Annotated[int, Field(ge=20, le=5_000, multiple_of=20)] = 80
    probe_ms: Literal[20] = 20
    kernel_buffers: Literal[1] = 1
    receiver_ids: tuple[int, ...] = (0, 1)
    gain_mode: GainMode = GainMode.MANUAL
    gain_db: float = 40.0
    glrt64_margin_gate: Annotated[float, Field(gt=0)] = 0.025
    maximum_acquisition_candidates: Annotated[int, Field(ge=1, le=16)] = 8
    targets: tuple[ScanTarget, ...]

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if self.bandwidth_hz > self.sample_rate_hz:
            raise ValueError("scanner bandwidth cannot exceed sample rate")
        if len(set(self.receiver_ids)) != len(self.receiver_ids) or not self.receiver_ids:
            raise ValueError("scanner receiver IDs must be nonempty and unique")
        if len(set((item.channel, item.edge) for item in self.targets)) != len(self.targets):
            raise ValueError("scanner targets must be unique by channel and edge")
        if tuple(sorted(self.targets, key=lambda item: item.if_center_hz)) != self.targets:
            raise ValueError("scanner targets must be ordered by increasing IF center")
        if not math.isfinite(self.gain_db):
            raise ValueError("scanner gain must be finite")
        return self

    @property
    def dwell_samples(self) -> int:
        return self.sample_rate_hz * self.dwell_ms // 1_000

    @property
    def probe_samples(self) -> int:
        return self.sample_rate_hz * self.probe_ms // 1_000


def current_low_band_targets(lnb_lo_hz: int = 9_750_000_000) -> tuple[ScanTarget, ...]:
    """Return every presently published channel edge reachable by the low LNB."""

    targets = tuple(
        ScanTarget(
            channel=channel,
            edge=edge,
            rf_center_hz=rf_center,
            if_center_hz=rf_center - lnb_lo_hz,
        )
        for channel, edge, rf_center in _CURRENT_RF_CENTERS_HZ
    )
    return tuple(sorted(targets, key=lambda item: item.if_center_hz))


class ScanDecision(StrEnum):
    ACTIVE = "active"
    NO_DETECTION = "no_detection"
    INCONCLUSIVE = "inconclusive"


class Glrt64FirstDetection(ScannerModel):
    receiver_id: int
    probe_index: Annotated[int, Field(ge=0)]
    probe_start_ms: Annotated[int, Field(ge=0)]
    candidate_rank: Annotated[int, Field(ge=0)]
    epoch_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


class ScanEdgeResult(ScannerModel):
    target: ScanTarget
    decision: ScanDecision
    requested_if_center_hz: int
    actual_if_center_hz: int | None
    tune_ms: float | None
    listen_ms: float | None
    iq_sha256: str | None
    first_detection: Glrt64FirstDetection | None = None
    best_margin: float | None = None
    reason: str


class ScannerReport(ScannerModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_scanner_report"] = "starlink_scanner_report"
    scan_id: str
    radio_id: str
    radio_serial: str
    configuration: ScannerConfiguration
    capture_elapsed_ms: float
    analysis_elapsed_ms: float
    results: tuple[ScanEdgeResult, ...]
    candidate_only: Literal[True] = True
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _covers_plan(self) -> Self:
        if tuple(item.target for item in self.results) != self.configuration.targets:
            raise ValueError("scanner report must cover the ordered target plan exactly")
        return self

    @property
    def active_edges(self) -> tuple[ScanTarget, ...]:
        return tuple(item.target for item in self.results if item.decision is ScanDecision.ACTIVE)
