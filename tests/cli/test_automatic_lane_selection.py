from __future__ import annotations

from types import SimpleNamespace

import pytest

from leo.cli import processing as processing_module
from leo.cli.processing import LocalProcessingBackend
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.states import CaptureState
from tests.pipeline.test_standard_native_topology import _manifest as native_manifest


class _Catalog:
    def __init__(self, manifest_digest: str) -> None:
        self.manifest_digest = manifest_digest
        self.current: dict[PipelineLane, str] = {}
        self.active: dict[PipelineLane, str] = {}

    def current_run_id(self, _session_id: str, lane: PipelineLane) -> str | None:
        return self.current.get(lane)

    def active_run_id(self, _session_id: str, lane: PipelineLane) -> str | None:
        return self.active.get(lane)

    def presentation_snapshot(self, session_id: str):
        return SimpleNamespace(
            session_id=session_id,
            bundle_uri="bulk://recordings/dwell",
            manifest_digest=self.manifest_digest,
        )


class _Recordings:
    def __init__(self, manifest_digest: str, manifest: object) -> None:
        self.bundle = SimpleNamespace(
            manifest_sha256=manifest_digest,
            manifest=manifest,
        )

    def inspect_uri(self, _uri: str):
        return self.bundle


class _Processing:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_expanded_run(self, **values: object) -> None:
        self.calls.append(values)


def _services(manifest_digest: str, manifest: object):
    return SimpleNamespace(
        catalog=_Catalog(manifest_digest),
        recordings=_Recordings(manifest_digest, manifest),
        processing=_Processing(),
        pipeline_release_id="1" * 40,
    )


def test_current_native_dwell_is_queued_in_the_standard_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_digest = canonical_digest({"native": "current"})
    services = _services(
        manifest_digest,
        native_manifest("starlink-ch4-lower-5m-60s-device-axis-v3"),
    )
    plan = SimpleNamespace(
        session_id="dwell",
        manifest_digest=manifest_digest,
        plan_digest=canonical_digest({"plan": "native"}),
    )
    monkeypatch.setattr(
        processing_module,
        "compile_standard_native_automatic_run_plan",
        lambda *_args, **_kwargs: plan,
    )

    run_id = LocalProcessingBackend(services)._ensure_default_run("dwell")

    assert run_id is not None and run_id.startswith("native-capture-")
    assert services.processing.calls == [
        {
            "run_id": run_id,
            "plan": plan,
            "trigger": "new_capture",
            "pipeline_lane": PipelineLane.STANDARD,
            "promotion_policy": "current",
        }
    ]


@pytest.mark.parametrize("existing_lane", tuple(PipelineLane))
@pytest.mark.parametrize("state", ("current", "active"))
def test_existing_run_in_either_lane_prevents_second_automatic_run(
    existing_lane: PipelineLane,
    state: str,
) -> None:
    manifest_digest = canonical_digest({"native": "existing"})
    services = _services(
        manifest_digest,
        native_manifest("starlink-ch4-lower-5m-60s-device-axis-v3"),
    )
    getattr(services.catalog, state)[existing_lane] = f"{existing_lane.value}-existing"

    assert LocalProcessingBackend(services)._ensure_default_run("dwell") is None
    assert services.processing.calls == []


def test_retired_manifest_is_not_automatically_routed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manifest_digest = canonical_digest({"legacy": "v1"})
    services = _services(manifest_digest, SimpleNamespace(schema_version=1))

    assert LocalProcessingBackend(services)._ensure_default_run("dwell") is None
    assert services.processing.calls == []
    assert "unsupported online" in caplog.text


def test_v3_native_dispatch_allows_degraded_capture_only_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_digest = canonical_digest({"native": "gapped-capture-only"})
    base_manifest = native_manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    manifest = base_manifest.model_copy(
        update={
            "state": CaptureState.DEGRADED,
            "tags": tuple(sorted({*base_manifest.tags, "CAPTURE_ONLY"})),
        }
    )
    services = _services(manifest_digest, manifest)
    plan = SimpleNamespace(
        session_id="dwell",
        manifest_digest=manifest_digest,
        plan_digest=canonical_digest({"plan": "native"}),
    )
    monkeypatch.setattr(
        processing_module,
        "compile_standard_native_automatic_run_plan",
        lambda *_args, **_kwargs: plan,
    )

    run_id = LocalProcessingBackend(services)._ensure_default_run("dwell")

    assert run_id is not None and run_id.startswith("native-capture-")
    assert services.processing.calls[0]["plan"] is plan
    assert services.processing.calls[0]["pipeline_lane"] is PipelineLane.STANDARD
