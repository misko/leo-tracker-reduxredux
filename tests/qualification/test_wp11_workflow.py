from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.wp11_production import WP11ProductionWorkflow
from leo.catalog import CatalogNotFoundError
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
from leo.storage import PinnedLocalRoot
from tests.qualification.test_trusted_campaign_store import _campaign


class _Capture:
    def __init__(self, receipt) -> None:
        self.receipt = receipt

    def resolve(self, _ref):
        return self.receipt


class _Catalog:
    def __init__(self) -> None:
        self.snapshots = {}

    def run_seal_snapshot(self, run_id):
        try:
            return self.snapshots[run_id]
        except KeyError as error:
            raise CatalogNotFoundError(run_id) from error

    def scientific_campaign(self, _campaign_id):
        return None


class _Processing:
    def __init__(self, catalog: _Catalog) -> None:
        self.catalog = catalog

    def create_reprocess_run(self, **values) -> None:
        jobs = tuple(
            SimpleNamespace(stage_key=stage, scope_key=scope)
            for scope in values["scope_keys"]
            for stage in values["stage_keys"]
        )
        self.catalog.snapshots[values["run_id"]] = SimpleNamespace(
            execution=SimpleNamespace(
                session_id=values["session_id"],
                pipeline_release_id=values["pipeline_release_id"],
                input_manifest_digest=values["input_manifest_digest"],
                promotion_policy="evidence_only",
            ),
            jobs=jobs,
            products=(),
        )


def test_wp11_create_and_queue_are_exact_and_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture, scientific = _campaign(tmp_path, monkeypatch)
    qualification = tmp_path / "qualification"
    qualification.mkdir()
    pinned = PinnedLocalRoot(qualification)
    plans = ImmutableWP11PlanStore(pinned)
    pinned.close()
    catalog = _Catalog()
    workflow = WP11ProductionWorkflow(
        plans=plans,
        capture=_Capture(capture),
        catalog=catalog,  # type: ignore[arg-type]
        processing=_Processing(catalog),  # type: ignore[arg-type]
        trusted=object(),  # type: ignore[arg-type]
        pipeline_release_id="trusted-release",
    )
    capture_ref = ImmutableDocumentRefV1(
        logical_uri="qualification://capture/accepted.json",
        digest=canonical_digest(capture.model_dump(mode="json")),
    )
    created = workflow.create(
        campaign_id="campaign-a",
        capture=capture_ref,
        processing_config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=scientific.config.detector_binding
        ),
    )
    assert (created.session_count, created.stream_count) == (30, 40)

    first = workflow.queue("campaign-a")
    second = workflow.queue("campaign-a")
    assert len(first.run_ids) == len(set(first.run_ids)) == 30
    assert first.already_queued_count == 0
    assert second.run_ids == first.run_ids
    assert second.already_queued_count == 30
    assert sum(len(snapshot.jobs) for snapshot in catalog.snapshots.values()) == 80
    bound_plan, bound_ref = plans.load_for_run(first.run_ids[0])
    assert bound_plan.campaign_id == "campaign-a"
    assert bound_ref == created.plan
    plan_path = qualification / "wp11-plans" / "campaign-a.json"
    plan_path.chmod(0o640)
    plan_path.write_text("{}", encoding="utf-8")
    plan_path.chmod(0o440)
    with pytest.raises(ValueError, match="digest|required"):
        plans.load("campaign-a")
    plans.close()
