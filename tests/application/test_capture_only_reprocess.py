from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from leo.application.research_reprocess import ResearchReprocessService
from leo.application.standard_reprocess import StandardReprocessError, StandardReprocessService
from leo.catalog import CatalogRepository
from leo.contracts.digests import canonical_digest
from leo.processing import ProcessingService
from leo.storage import RecordingStore
from tests.pipeline.test_standard_native_topology import _manifest as native_manifest
from tests.rate_analysis_examples import rate_manifest

_RELEASE = "1" * 40
_DIGEST = "sha256:" + "2" * 64


class _Catalog:
    def presentation_snapshot(self, session_id: str):
        assert session_id == "capture-only-session"
        return SimpleNamespace(bundle_uri="bulk://capture-only-session", manifest_digest=_DIGEST)

    def active_run_id(self, _session_id: str, *_args: Any):
        return None


class _Recordings:
    def __init__(self, manifest: object) -> None:
        self._manifest = manifest

    def inspect_uri(self, uri: str):
        assert uri == "bulk://capture-only-session"
        return SimpleNamespace(
            manifest_sha256=_DIGEST,
            manifest=self._manifest,
        )

    def verify(self, _bundle: object) -> None:
        return None


@pytest.mark.parametrize("service_type", (StandardReprocessService, ResearchReprocessService))
def test_expired_recording_cannot_enter_an_online_graph(service_type: type) -> None:
    service = service_type(
        catalog=cast(CatalogRepository, _Catalog()),
        recordings=cast(RecordingStore, _Recordings(rate_manifest(5_000_000))),
        processing=cast(ProcessingService, SimpleNamespace()),
        pipeline_release_id=_RELEASE,
    )

    with pytest.raises(StandardReprocessError, match="schema 2 is unsupported online"):
        service.queue("capture-only-session")


class _RateRecordings:
    def __init__(self, manifest: object, manifest_digest: str) -> None:
        self._bundle = SimpleNamespace(
            manifest_sha256=manifest_digest,
            manifest=manifest,
        )

    def inspect_uri(self, _uri: str):
        return self._bundle

    def verify(self, bundle: object) -> None:
        assert bundle is self._bundle


class _RateProcessing:
    def __init__(self) -> None:
        self.values: dict[str, object] | None = None

    def create_expanded_run(self, **values: object) -> None:
        self.values = values


class _NativeCatalog:
    def __init__(self, session_id: str, manifest_digest: str) -> None:
        self.session_id = session_id
        self.manifest_digest = manifest_digest

    def presentation_snapshot(self, session_id: str):
        assert session_id == self.session_id
        return SimpleNamespace(
            bundle_uri=f"bulk://{session_id}",
            manifest_digest=self.manifest_digest,
        )

    def active_run_id(self, session_id: str, *_args: object):
        assert session_id == self.session_id
        return None

    def pipeline_release_snapshot(self, release_id: str):
        assert release_id == _RELEASE
        return SimpleNamespace(code_revision=_RELEASE)

    def current_run_id(self, session_id: str):
        assert session_id == self.session_id
        return "frozen-standard-current"


def test_manual_native_action_is_explicit_and_evidence_only() -> None:
    manifest = native_manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    manifest_digest = canonical_digest({"native": manifest.session_id})
    processing = _RateProcessing()
    service = StandardReprocessService(
        catalog=cast(CatalogRepository, _NativeCatalog(manifest.session_id, manifest_digest)),
        recordings=cast(RecordingStore, _RateRecordings(manifest, manifest_digest)),
        processing=cast(ProcessingService, processing),
        pipeline_release_id=_RELEASE,
    )

    current = service.queue(manifest.session_id)
    assert current.previous_current_run_id == "frozen-standard-current"
    assert current.queued_job_count == 16
    assert processing.values is not None
    assert processing.values["promotion_policy"] == "current"
    assert processing.values["trigger"] == "reprocess"

    result = service.queue_native_evidence(manifest.session_id)

    assert result.pipeline_family == "standard-native-evidence-v1"
    assert result.promotion_policy == "evidence_only"
    assert result.previous_current_run_id == "frozen-standard-current"
    assert result.queued_job_count == 16
    assert processing.values is not None
    assert processing.values["promotion_policy"] == "evidence_only"
    plan = processing.values["plan"]
    assert {job.stage_key for job in plan.jobs} == {
        "path-standard-native",
        "path-alternate-tracks-native",
        "path-pss-native",
        "radio-scientific-report-native",
        "paired-scientific-report-native",
        "paired-presentation-native",
    }


def test_research_action_directs_current_manifest_to_standard_native() -> None:
    manifest = native_manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    manifest_digest = canonical_digest({"native": manifest.session_id})
    service = ResearchReprocessService(
        catalog=cast(CatalogRepository, _NativeCatalog(manifest.session_id, manifest_digest)),
        recordings=cast(RecordingStore, _RateRecordings(manifest, manifest_digest)),
        processing=cast(ProcessingService, SimpleNamespace()),
        pipeline_release_id=_RELEASE,
    )

    with pytest.raises(StandardReprocessError, match="explicit Standard-native action"):
        service.queue(manifest.session_id)
