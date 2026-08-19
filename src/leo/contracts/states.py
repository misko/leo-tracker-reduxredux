"""Finite state and vocabulary contracts shared across acquisition modules."""

from __future__ import annotations

from enum import StrEnum


class CaptureState(StrEnum):
    PLANNED = "planned"
    PREPARING = "preparing"
    READY = "ready"
    CAPTURING = "capturing"
    FINALIZING = "finalizing"
    COMMITTED = "committed"
    DEGRADED = "degraded"
    FAILED = "failed"


class StreamState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceType(StrEnum):
    LIVE = "live"
    TEST = "test"
    IMPORT = "import"


class SynchronizationMode(StrEnum):
    NONE = "none"
    BEST_EFFORT = "best_effort"


class SynchronizationGrade(StrEnum):
    NOT_REQUESTED = "not_requested"
    BEST_EFFORT_OBSERVED = "best_effort_observed"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class PeerFailurePolicy(StrEnum):
    KEEP_SURVIVOR = "keep_survivor"
    FAIL_SESSION = "fail_session"


class ContinuityPolicy(StrEnum):
    REQUIRE_CONTIGUOUS = "require_contiguous"
    ALLOW_SEGMENTS = "allow_segments"


class StarlinkEdge(StrEnum):
    LOWER = "lower"
    UPPER = "upper"


class TimingMethod(StrEnum):
    HOST_BRACKET = "host_bracket"
    HOST_BARRIER = "host_barrier"
    DEVICE_COUNTER_ANCHORED = "device_counter_anchored"
    IMPORTED = "imported"


class GainMode(StrEnum):
    MANUAL = "manual"
    SLOW_ATTACK = "slow_attack"
    FAST_ATTACK = "fast_attack"
    HYBRID = "hybrid"


class RadioTransport(StrEnum):
    FAKE = "fake"
    IIO_IP = "iio_ip"
    DIRECT_IP = "direct_ip"
    IMPORTED = "imported"


class SampleFormat(StrEnum):
    CI16_LE = "ci16_le"


class SampleLayout(StrEnum):
    SAMPLE_RECEIVER_IQ = "sample_receiver_iq"


class ContinuityStatus(StrEnum):
    UNKNOWN = "unknown"
    CONTIGUOUS = "contiguous"
    GAP_BEFORE = "gap_before"
    OVERFLOW = "overflow"
