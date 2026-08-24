"""Internal application results that do not become persisted contracts."""

from __future__ import annotations

from dataclasses import dataclass

from leo.contracts.recording import RecordingManifestV1, RecordingManifestV2
from leo.contracts.states import CaptureState
from leo.storage.writer import PublishedBundle


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Host-local operational bounds, independent of capture profiles."""

    release_lead_ns: int = 50_000_000
    readiness_timeout_seconds: float = 10.0
    safety_reserve_bytes: int = 1 * 1024 * 1024 * 1024
    metadata_bytes_per_refill: int = 4096
    consumer_shutdown_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.release_lead_ns < 0:
            raise ValueError("release lead cannot be negative")
        if self.readiness_timeout_seconds <= 0:
            raise ValueError("readiness timeout must be positive")
        if self.safety_reserve_bytes < 0 or self.metadata_bytes_per_refill <= 0:
            raise ValueError("admission reserves are invalid")
        if self.consumer_shutdown_timeout_seconds <= 0:
            raise ValueError("consumer shutdown timeout must be positive")


@dataclass(frozen=True, slots=True)
class AdmissionEstimate:
    raw_iq_bytes: int
    metadata_reserve_bytes: int
    safety_reserve_bytes: int
    required_free_bytes: int
    available_free_bytes: int
    admitted: bool
    storage_used_fraction: float | None = None
    storage_warning: bool = False
    policy_reason: str | None = None


@dataclass(frozen=True, slots=True)
class StorageAdmissionDecision:
    allowed: bool
    used_fraction: float | None = None
    warning: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureSessionResult:
    session_id: str
    state: CaptureState
    admission: AdmissionEstimate
    bundle: PublishedBundle | None = None
    manifest: RecordingManifestV1 | RecordingManifestV2 | None = None
    release_target_monotonic_ns: int | None = None
    errors: tuple[str, ...] = ()
