from __future__ import annotations

from types import SimpleNamespace

import pytest

from leo.cli.models import ExitCode
from leo.cli.processing import CliBackendError, LocalProcessingBackend
from leo.contracts.digests import canonical_digest
from tests.pipeline.test_standard_native_topology import _manifest, _reviewed_v2_manifest

_RELEASE = "1" * 40


class _Catalog:
    def __init__(self, session_id: str, manifest_digest: str) -> None:
        self.session_id = session_id
        self.manifest_digest = manifest_digest

    def presentation_snapshot(self, session_id: str) -> object:
        assert session_id == self.session_id
        return SimpleNamespace(
            bundle_uri=f"bulk://recordings/{session_id}",
            manifest_digest=self.manifest_digest,
        )

    def pipeline_release_snapshot(self, release_id: str) -> object:
        assert release_id == _RELEASE
        return SimpleNamespace(code_revision=_RELEASE)

    def active_run_id(self, session_id: str) -> None:
        assert session_id == self.session_id

    def current_run_id(self, session_id: str) -> str:
        assert session_id == self.session_id
        return "frozen-standard-current"


class _Recordings:
    def __init__(self, manifest: object, manifest_digest: str) -> None:
        self.bundle = SimpleNamespace(
            manifest=manifest,
            manifest_sha256=manifest_digest,
        )

    def inspect_uri(self, _uri: str) -> object:
        return self.bundle

    def verify(self, bundle: object) -> None:
        assert bundle is self.bundle


def _backend() -> tuple[LocalProcessingBackend, object]:
    manifest = _reviewed_v2_manifest(5_000_000)
    manifest_digest = canonical_digest(manifest.model_dump(mode="json"))
    services = SimpleNamespace(
        pipeline_release_id=_RELEASE,
        catalog=_Catalog(manifest.session_id, manifest_digest),
        recordings=_Recordings(manifest, manifest_digest),
    )
    return LocalProcessingBackend(services), manifest


def test_cli_queues_reviewed_historical_v2_only_through_manual_evidence_action() -> None:
    backend, manifest = _backend()

    result = backend.native_evidence(
        manifest.session_id,
        pipeline_release_id=_RELEASE,
        dry_run=True,
    )

    assert result.state == "dry_run"
    assert result.previous_current_run_id == "frozen-standard-current"
    assert result.queued_job_count == 16
    assert result.queued_scope_keys == tuple(stream.stream_id for stream in manifest.streams)


def test_cli_frozen_standard_action_still_refuses_capture_only_historical_v2() -> None:
    backend, manifest = _backend()

    with pytest.raises(CliBackendError) as captured:
        backend._standard_plan(manifest.session_id, _RELEASE)

    assert captured.value.exit_code is ExitCode.CONFLICT
    assert "separately versioned scientific pipeline" in str(captured.value)


def test_cli_standard_reprocess_dispatches_reviewed_v3_to_native_current() -> None:
    manifest = _manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    for stream in manifest.streams:
        stream.chunks = (object(),)
    manifest_digest = canonical_digest({"manifest": "native-current-cli"})
    services = SimpleNamespace(
        pipeline_release_id=_RELEASE,
        catalog=_Catalog(manifest.session_id, manifest_digest),
        recordings=_Recordings(manifest, manifest_digest),
    )
    backend = LocalProcessingBackend(services)

    result = backend.reprocess(manifest.session_id, dry_run=True)

    assert result.state == "dry_run"
    assert result.previous_current_run_id == "frozen-standard-current"
    assert result.queued_scope_keys == tuple(stream.stream_id for stream in manifest.streams)
    _, plan = backend._standard_plan(manifest.session_id, _RELEASE)
    assert {job.stage_key for job in plan.jobs} == {
        "path-standard-native",
        "path-alternate-tracks-native",
        "path-pss-native",
        "radio-scientific-report-native",
        "paired-scientific-report-native",
        "paired-presentation-native",
    }
