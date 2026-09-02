from __future__ import annotations

import pytest

from leo.processing.recording_support import (
    UnsupportedOnlineRecordingManifestError,
    require_online_recording_manifest,
)
from tests.pipeline.test_standard_native_topology import _manifest
from tests.rate_analysis_examples import rate_manifest


def test_online_recording_policy_accepts_recent_v3_manifest() -> None:
    manifest = _manifest("starlink-ch4-lower-5m-60s-device-axis-v3")

    assert require_online_recording_manifest(manifest) is manifest


def test_online_recording_policy_rejects_expired_v2_with_clear_error() -> None:
    manifest = rate_manifest(5_000_000)

    with pytest.raises(
        UnsupportedOnlineRecordingManifestError,
        match=r"schema 2 is unsupported online; supported schemas: 3, 5, 6",
    ):
        require_online_recording_manifest(manifest)
