"""Read-only presentation port for registered native refinement episodes."""

from __future__ import annotations

from typing import Literal, Protocol

from leo.contracts.base import ContractModel
from leo.contracts.native_journal_recording import Digest, NativeJournalMeasurementV1


class NativeRecordingSummaryV1(ContractModel):
    bundle_id: Digest
    serial: str
    boot_id: str
    fit_sha256: Digest
    visit: int
    epoch: int
    episode_index: int
    runtime_result: int
    owner_status: str
    source_rate_hz: Literal[60000000] = 60000000
    pilot_samples: Literal[79200] = 79200
    head_count: int
    supported_count: int
    rejected_count: int
    observed_start_span_s: float | None
    supported_cfo_min_hz: float | None
    supported_cfo_max_hz: float | None
    frequency_reference: Literal["receiver_relative_uncalibrated"]
    evidence_mode: Literal["retrospective_retained_owner_correspondence"]
    acquisition_verified: Literal[False] = False
    original_native_iq_verified: Literal[False] = False
    physical_precision_qualified: Literal[False] = False


class NativeRecordingEntryV1(ContractModel):
    bundle_id: Digest
    summary: NativeRecordingSummaryV1 | None
    error: Literal["integrity_unavailable"] | None


class NativeRecordingListV1(ContractModel):
    schema_version: Literal[1] = 1
    total: int
    next_cursor: int | None
    items: tuple[NativeRecordingEntryV1, ...]


class NativeRecordingRowV1(ContractModel):
    measurement: NativeJournalMeasurementV1
    coarse_relative_scheduled_start_s: float
    coarse_relative_refined_start_s: float


class NativeRecordingDetailV1(ContractModel):
    schema_version: Literal[1] = 1
    summary: NativeRecordingSummaryV1
    cursor: int
    next_cursor: int | None
    rows: tuple[NativeRecordingRowV1, ...]


class NativeRecordingUnavailable(ValueError):
    """A registered episode no longer matches its pinned publication."""


class NativeRecordingReader(Protocol):
    def list_recordings(self, *, cursor: int, limit: int) -> NativeRecordingListV1: ...

    def get_recording(
        self, bundle_id: str, *, cursor: int, limit: int
    ) -> NativeRecordingDetailV1: ...
