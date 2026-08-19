"""Recording-store failures with actionable, narrow meanings."""

from __future__ import annotations


class RecordingStoreError(RuntimeError):
    pass


class BundleStateError(RecordingStoreError):
    pass


class BundleNotFoundError(RecordingStoreError):
    pass


class BundleCorruptionError(RecordingStoreError):
    pass


class PathConfinementError(RecordingStoreError):
    pass
