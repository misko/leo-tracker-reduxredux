"""Stable catalog state vocabularies."""

from __future__ import annotations

from enum import StrEnum


class SessionState(StrEnum):
    COMMITTED = "committed"
    DEGRADED = "degraded"
    FAILED = "failed"
    PURGING = "purging"
    PURGED = "purged"


class AnalysisRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PromotionPolicy(StrEnum):
    """Whether a sealed run may replace the session's presentation baseline."""

    CURRENT = "current"
    EVIDENCE_ONLY = "evidence_only"


class JobState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptState(StrEnum):
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class ProductStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL_COVERAGE = "partial_coverage"
    NO_RESULT = "no_result"
    INSUFFICIENT_DATA = "insufficient_data"


class ProductRole(StrEnum):
    SCIENTIFIC = "scientific"
    PRESENTATION = "presentation"
