"""Backward-compatible acquisition import for the shared continuity validator."""

from leo.domain.continuity import ContinuityChainValidator, ContinuityValidationError

__all__ = ["ContinuityChainValidator", "ContinuityValidationError"]
