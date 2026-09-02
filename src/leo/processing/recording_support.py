"""Online recording-format policy for processing and re-analysis."""

from __future__ import annotations

from typing import cast

from leo.contracts.recording import (
    RecordingManifestContract,
    RecordingManifestV3,
    RecordingManifestV5,
    RecordingManifestV6,
)

ONLINE_RECORDING_MANIFEST_SCHEMA_VERSIONS = (3, 5, 6)

type OnlineRecordingManifest = RecordingManifestV3 | RecordingManifestV5 | RecordingManifestV6


class UnsupportedOnlineRecordingManifestError(ValueError):
    """A persisted manifest remains readable but is no longer routed online."""


def require_online_recording_manifest(
    manifest: RecordingManifestContract,
) -> OnlineRecordingManifest:
    """Return a currently routed manifest or fail with an explicit policy error."""

    if manifest.schema_version not in ONLINE_RECORDING_MANIFEST_SCHEMA_VERSIONS:
        supported = ", ".join(str(item) for item in ONLINE_RECORDING_MANIFEST_SCHEMA_VERSIONS)
        raise UnsupportedOnlineRecordingManifestError(
            f"recording manifest schema {manifest.schema_version} is unsupported online; "
            f"supported schemas: {supported}"
        )
    return cast(OnlineRecordingManifest, manifest)
