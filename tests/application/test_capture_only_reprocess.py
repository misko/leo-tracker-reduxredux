from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from leo.application.research_reprocess import ResearchReprocessService
from leo.application.standard_reprocess import StandardReprocessError, StandardReprocessService
from leo.catalog import CatalogRepository
from leo.processing import ProcessingService
from leo.storage import RecordingStore

_RELEASE = "1" * 40
_DIGEST = "sha256:" + "2" * 64


class _Catalog:
    def presentation_snapshot(self, session_id: str):
        assert session_id == "capture-only-session"
        return SimpleNamespace(bundle_uri="bulk://capture-only-session", manifest_digest=_DIGEST)

    def active_run_id(self, _session_id: str, *_args: Any):
        return None


class _Recordings:
    def inspect_uri(self, uri: str):
        assert uri == "bulk://capture-only-session"
        return SimpleNamespace(
            manifest_sha256=_DIGEST,
            manifest=SimpleNamespace(tags=("CAPTURE_ONLY", "LIVE")),
        )

    def verify(self, _bundle: object) -> None:
        return None


@pytest.mark.parametrize("service_type", (StandardReprocessService, ResearchReprocessService))
def test_capture_only_recording_cannot_enter_frozen_standard_graph(service_type: type) -> None:
    service = service_type(
        catalog=cast(CatalogRepository, _Catalog()),
        recordings=cast(RecordingStore, _Recordings()),
        processing=cast(ProcessingService, SimpleNamespace()),
        pipeline_release_id=_RELEASE,
    )

    with pytest.raises(StandardReprocessError, match="separately versioned scientific pipeline"):
        service.queue("capture-only-session")
