from __future__ import annotations

import json
from typing import Any, cast

from typer.testing import CliRunner

from leo.cli.app import create_cli
from leo.cli.composition import BackendFactory
from leo.cli.standard_pipeline import (
    StandardIntegrityAttestationV2,
    StandardPlanDataV2,
    StandardPlanEdgeV2,
    StandardPlanNodeV2,
    StandardReprocessDataV2,
    StandardShowDataV2,
    StandardStaleDataV2,
    StandardStaleItemV2,
)
from leo.presentation.standard_fixtures import build_standard_fixture_repository
from leo.presentation.standard_pipeline import (
    StandardComputationDispositionV2,
    StandardStaleReasonCodeV2,
    StandardStateReasonV2,
    StandardSubjectStateV2,
)

runner = CliRunner()
SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeStandardBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        hierarchy = build_standard_fixture_repository().subject_hierarchy("T1")
        assert hierarchy is not None
        self.hierarchy = hierarchy

    def standard_show(self, session_id: str, *, include_test: bool) -> StandardShowDataV2:
        self.calls.append(("show", {"session_id": session_id, "include_test": include_test}))
        return StandardShowDataV2(hierarchy=self.hierarchy)

    def standard_plan(self, session_id: str, *, pipeline_release_id: str) -> StandardPlanDataV2:
        self.calls.append(
            (
                "plan",
                {"session_id": session_id, "pipeline_release_id": pipeline_release_id},
            )
        )
        return _plan(session_id, pipeline_release_id)

    def standard_reprocess(
        self,
        session_id: str,
        *,
        pipeline_release_id: str,
        dry_run: bool,
        wait: bool,
    ) -> StandardReprocessDataV2:
        self.calls.append(
            (
                "reprocess",
                {
                    "session_id": session_id,
                    "pipeline_release_id": pipeline_release_id,
                    "dry_run": dry_run,
                    "wait": wait,
                },
            )
        )
        return StandardReprocessDataV2(
            session_id=session_id,
            pipeline_release_id=pipeline_release_id,
            state="dry_run" if dry_run else "succeeded" if wait else "queued",
            run_id=None if dry_run else "run-standard-v2",
            waited=wait,
            plan=_plan(session_id, pipeline_release_id),
            previous_current_run_id="run-old",
        )

    def standard_stale(
        self,
        *,
        pipeline_release_id: str,
        include_test: bool,
        limit: int,
    ) -> StandardStaleDataV2:
        self.calls.append(
            (
                "stale",
                {
                    "pipeline_release_id": pipeline_release_id,
                    "include_test": include_test,
                    "limit": limit,
                },
            )
        )
        return StandardStaleDataV2(
            desired_pipeline_release_id=pipeline_release_id,
            include_test=include_test,
            items=(
                StandardStaleItemV2(
                    session_id="T1",
                    subject_id="radio:radio1",
                    label="Radio1",
                    state=StandardSubjectStateV2.STALE,
                    analyzed_pipeline_release_id="f" * 40,
                    desired_pipeline_release_id=pipeline_release_id,
                    reasons=(
                        StandardStateReasonV2(
                            code=StandardStaleReasonCodeV2.STAGE_IMPLEMENTATION_CHANGED,
                            message="trajectory fitter changed",
                            affected_stage_keys=("path-trajectory-bank",),
                            affected_subject_ids=("radio:radio1", "pair:radio0:radio1"),
                        ),
                    ),
                ),
            ),
            source_item_count=1,
            truncated=False,
        )


def _plan(session_id: str, release: str) -> StandardPlanDataV2:
    eligibility = build_standard_fixture_repository().subject_hierarchy("T1")
    assert eligibility is not None
    nodes = (
        StandardPlanNodeV2(
            node_id="path0",
            stage_key="path-pilot-scan",
            subject_id="path:radio0:rx0",
            disposition=StandardComputationDispositionV2.REUSED,
            resource_class="cpu-heavy",
            derivation_key="a" * 64,
            reason="exact derivation hit",
        ),
        StandardPlanNodeV2(
            node_id="radio0",
            stage_key="radio-standard-report",
            subject_id="radio:radio0",
            disposition=StandardComputationDispositionV2.RECOMPUTE,
            resource_class="cpu-light",
            derivation_key="b" * 64,
            reason="child wrapper changed",
        ),
    )
    return StandardPlanDataV2(
        session_id=session_id,
        pipeline_release_id=release,
        eligibility=eligibility.eligibility,
        integrity=(
            StandardIntegrityAttestationV2(
                stream_id="stream-0",
                manifest_digest="c" * 64,
                verified_chunk_count=4,
                verified_byte_count=1024,
                verified=True,
                reason="all declared chunks digest-verified",
            ),
        ),
        nodes=nodes,
        edges=(StandardPlanEdgeV2(producer_node_id="path0", consumer_node_id="radio0"),),
        plan_digest="d" * 64,
    )


def _app(backend: FakeStandardBackend):
    return create_cli(cast(BackendFactory, lambda: backend))


def _json(output: str) -> dict[str, Any]:
    return json.loads(output)


def test_plan_is_dry_run_only_and_lists_cache_frontier() -> None:
    backend = FakeStandardBackend()
    result = runner.invoke(
        _app(backend), ["process", "plan", "T1", "--release", SHA, "--json"]
    )

    assert result.exit_code == 0, result.stdout
    payload = _json(result.stdout)["payload"]
    assert payload["dry_run"] is True and payload["mutation_performed"] is False
    assert [node["disposition"] for node in payload["nodes"]] == ["reused", "recompute"]
    assert payload["integrity"][0]["verified"] is True
    assert backend.calls == [("plan", {"session_id": "T1", "pipeline_release_id": SHA})]


def test_show_subjects_makes_test_evidence_opt_in_and_lists_three_rows() -> None:
    backend = FakeStandardBackend()
    result = runner.invoke(
        _app(backend),
        ["process", "show", "T1", "--subjects", "--include-test", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    hierarchy = _json(result.stdout)["payload"]["hierarchy"]
    assert [row["label"] for row in hierarchy["rows"]] == [
        "Paired Radio0 + Radio1",
        "Radio0",
        "Radio1",
    ]
    assert hierarchy["eligibility"]["evidence_only"] is True
    assert backend.calls[-1] == ("show", {"session_id": "T1", "include_test": True})


def test_reprocess_release_dry_run_and_wait_are_forwarded_exactly() -> None:
    backend = FakeStandardBackend()
    app = _app(backend)
    dry = runner.invoke(
        app,
        ["process", "reprocess", "T1", "--release", SHA, "--dry-run", "--json"],
    )
    waited = runner.invoke(
        app,
        ["process", "reprocess", "T1", "--release", SHA, "--wait", "--json"],
    )

    assert dry.exit_code == 0 and waited.exit_code == 0
    assert _json(dry.stdout)["payload"]["state"] == "dry_run"
    assert _json(dry.stdout)["payload"]["run_id"] is None
    assert _json(waited.stdout)["payload"]["state"] == "succeeded"
    assert _json(waited.stdout)["payload"]["waited"] is True
    assert backend.calls[0][1]["dry_run"] is True
    assert backend.calls[1][1]["wait"] is True


def test_stale_and_release_refusal_are_machine_readable_and_pre_backend() -> None:
    backend = FakeStandardBackend()
    app = _app(backend)
    stale = runner.invoke(
        app,
        ["process", "stale", "--release", SHA, "--include-test", "--json"],
    )
    refused = runner.invoke(
        app,
        ["process", "plan", "T1", "--release", "standard-glrt64-v2", "--json"],
    )

    assert stale.exit_code == 0
    item = _json(stale.stdout)["payload"]["items"][0]
    assert item["state"] == "stale"
    assert item["reasons"][0]["code"] == "stage_implementation_changed"
    assert refused.exit_code == 2
    assert "exact lowercase 40-character Git SHA" in refused.output
    assert [call[0] for call in backend.calls] == ["stale"]
