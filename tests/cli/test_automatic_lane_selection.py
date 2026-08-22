from __future__ import annotations

from types import SimpleNamespace

import pytest

from leo.cli import processing as processing_module
from leo.cli.processing import LocalProcessingBackend
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import (
    PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    PipelineLane,
    assign_dwell_pipeline_lane,
)


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
    def __init__(self, manifest_digest: str) -> None:
        stream = SimpleNamespace(captured_sample_count=1, chunks=(object(),))
        source_type = SimpleNamespace(value="live")
        self.bundle = SimpleNamespace(
            manifest_sha256=manifest_digest,
            manifest=SimpleNamespace(streams=(stream,), tags=frozenset(), source_type=source_type),
        )

    def inspect_uri(self, _uri: str):
        return self.bundle


class _Processing:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_expanded_run(self, **values: object) -> None:
        self.calls.append(values)


def _manifest_for_lane(lane: PipelineLane) -> str:
    for index in range(1_000):
        digest = canonical_digest({"automatic-lane-test": index})
        assignment = assign_dwell_pipeline_lane(
            digest,
            PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
        )
        if assignment.selected_lane is lane:
            return digest
    raise AssertionError(f"failed to construct manifest for {lane.value}")


@pytest.mark.parametrize("expected_lane", tuple(PipelineLane))
def test_new_dwell_is_queued_only_in_its_deterministic_lane(
    monkeypatch: pytest.MonkeyPatch,
    expected_lane: PipelineLane,
) -> None:
    manifest_digest = _manifest_for_lane(expected_lane)
    catalog = _Catalog(manifest_digest)
    processing = _Processing()
    services = SimpleNamespace(
        catalog=catalog,
        recordings=_Recordings(manifest_digest),
        processing=processing,
        pipeline_release_id="1" * 40,
        automatic_lane_selection=PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    )
    plan = SimpleNamespace(session_id="dwell", manifest_digest=manifest_digest)
    monkeypatch.setattr(processing_module, "compile_standard_run_plan", lambda *_a, **_k: plan)

    run_id = LocalProcessingBackend(services)._ensure_default_run("dwell")

    assert run_id is not None
    assert run_id.startswith("research-" if expected_lane is PipelineLane.RESEARCH else "capture-")
    assert len(processing.calls) == 1
    assert processing.calls[0]["pipeline_lane"] is expected_lane
    assert processing.calls[0]["trigger"] == "new_capture"


@pytest.mark.parametrize("existing_lane", tuple(PipelineLane))
@pytest.mark.parametrize("state", ("current", "active"))
def test_existing_run_in_either_lane_prevents_second_automatic_run(
    existing_lane: PipelineLane,
    state: str,
) -> None:
    manifest_digest = _manifest_for_lane(PipelineLane.RESEARCH)
    catalog = _Catalog(manifest_digest)
    getattr(catalog, state)[existing_lane] = f"{existing_lane.value}-existing"
    processing = _Processing()
    services = SimpleNamespace(
        catalog=catalog,
        recordings=_Recordings(manifest_digest),
        processing=processing,
        pipeline_release_id="1" * 40,
        automatic_lane_selection=PRODUCTION_AUTOMATIC_LANE_SELECTION_V1,
    )

    assert LocalProcessingBackend(services)._ensure_default_run("dwell") is None
    assert processing.calls == []
