from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import leo.application.wp11_dynamic as wp11_dynamic_module
from leo.analysis.adapters import (
    production_long_dwell_registry,
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
from leo.application.wp11_dynamic import DynamicWP11Analyzer
from leo.application.wp11_operations import wp11_run_id
from leo.application.wp11_production import WP11ProductionWorkflow
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import PromotionPolicy
from leo.cli.processing import ProcessingBackendSettings, build_processing_backend
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    StageOutcome,
    StageResult,
    compile_standard_run_plan,
)
from leo.processing import ProcessingService
from leo.qualification import native_release
from leo.qualification.trusted_matched_recovery_stage import TRUSTED_MATCHED_RECOVERY_STAGE
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
from leo.storage import PinnedLocalRoot
from tests.analysis.test_trusted_acceptance_v2 import _binding
from tests.qualification.test_trusted_campaign_store import _campaign
from tests.station.manifest_examples import manifest_example, verified_digest

from .conftest import ProcessingDatabase


class _Delegate:
    spec = NATIVE_KNOWN_PILOT_EVIDENCE_STAGE

    def analyze(self, _context, _iq, _products, _outputs):
        return StageResult(outcome=StageOutcome.COMPLETE)


class _MatchedDelegate(_Delegate):
    spec = TRUSTED_MATCHED_RECOVERY_STAGE


class _Plans:
    def __init__(self, plan=None) -> None:
        self.plan = plan

    def load_for_run(self, _run_id):
        if self.plan is None:
            raise FileNotFoundError(_run_id)
        return self.plan, object()


_CAPTURE_REF = ImmutableDocumentRefV1(
    logical_uri="qualification://capture/missing.json",
    digest="sha256:" + "1" * 64,
)


def _plan():
    inventory = SimpleNamespace(session_id="session-a", stream_id="stream-a")
    member = SimpleNamespace(inventory=inventory)
    return SimpleNamespace(
        campaign_id="campaign-a",
        plan_digest="sha256:" + "1" * 64,
        pipeline_release_id="release-a",
        processing_config=SimpleNamespace(
            detector_binding=SimpleNamespace(pipeline_release="release-a")
        ),
        capture=_CAPTURE_REF,
        members=(member,),
    )


def _capture_authority(tmp_path: Path) -> ImmutableCaptureCampaignAuthority:
    root = tmp_path / "capture-authority"
    root.mkdir(exist_ok=True)
    pinned = PinnedLocalRoot(root)
    try:
        return ImmutableCaptureCampaignAuthority(pinned)
    finally:
        pinned.close()


def test_dynamic_wp11_analyzer_fails_closed_without_plan_or_exact_run_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wp11_dynamic_module,
        "validate_authoritative_plan",
        lambda _plan, _capture, **_kwargs: None,
    )
    capture = _capture_authority(tmp_path)
    missing = DynamicWP11Analyzer(  # type: ignore[arg-type]
        NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
        _Plans(),
        capture,
        "release-a",
        lambda _plan, _stage: _Delegate(),
    )
    context = AnalysisContext(
        session_id="session-a",
        run_id=wp11_run_id("campaign-a", "session-a"),
        pipeline_release="release-a",
        scope_key="stream-a",
    )
    with pytest.raises(FileNotFoundError):
        missing.analyze(context, object(), object(), object())  # type: ignore[arg-type]

    bound = DynamicWP11Analyzer(  # type: ignore[arg-type]
        NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
        _Plans(_plan()),
        capture,
        "release-a",
        lambda _plan, _stage: _Delegate(),
    )
    with pytest.raises(ValueError, match="retargeted"):
        bound.analyze(  # type: ignore[arg-type]
            context.model_copy(update={"pipeline_release": "wrong-release"}),
            object(),
            object(),
            object(),
        )
    assert bound.analyze(context, object(), object(), object()).outcome is StageOutcome.COMPLETE  # type: ignore[arg-type]
    capture.close()


def test_dynamic_wp11_analyzer_re_resolves_capture_before_delegating(
    tmp_path: Path,
) -> None:
    capture = _capture_authority(tmp_path)
    analyzer = DynamicWP11Analyzer(  # type: ignore[arg-type]
        NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
        _Plans(_plan()),
        capture,
        "release-a",
        lambda _plan, _stage: _Delegate(),
    )
    with pytest.raises(FileNotFoundError):
        analyzer.analyze(  # type: ignore[arg-type]
            AnalysisContext(
                session_id="session-a",
                run_id=wp11_run_id("campaign-a", "session-a"),
                pipeline_release="release-a",
                scope_key="stream-a",
            ),
            object(),
            object(),
            object(),
        )
    capture.close()


def test_wp11_dynamic_stage_is_execution_only_not_a_default_run_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wp11_dynamic_module,
        "validate_authoritative_plan",
        lambda _plan, _capture, **_kwargs: None,
    )
    capture = _capture_authority(tmp_path)
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    default_stage_keys = registry.keys
    registry.register(  # type: ignore[arg-type]
        DynamicWP11Analyzer(
            NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
            _Plans(),  # type: ignore[arg-type]
            capture,
            "release-a",
            lambda _plan, _stage: _Delegate(),
        )
    )
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key in registry.keys
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key not in default_stage_keys
    capture.close()


def test_postgres_processing_composition_loads_wp11_only_for_execution(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    qualification = tmp_path / "qualification"
    legacy = tmp_path / "legacy"
    capture = tmp_path / "capture"
    corpus = tmp_path / "corpus"
    for root in (bulk, qualification, legacy, capture, corpus):
        root.mkdir()
    (bulk / "spool").mkdir()
    (bulk / "recordings").mkdir()
    (qualification / "frequency-calibration-plans").mkdir()
    (qualification / "frequency-calibration-promotions").mkdir()
    backend = build_processing_backend(
        ProcessingBackendSettings(
            database_url=processing_database.engine.url.render_as_string(hide_password=False),
            bulk_root=bulk,
            corpus_root=corpus,
            pipeline_release_id="wp11-dynamic-release",
            qualification_root=qualification,
            legacy_evidence_root=legacy,
            capture_evidence_root=capture,
            scratch_root=tmp_path,
        )
    )

    registry = backend.services.processing.registry
    defaults = backend.services.processing.default_stage_keys
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key in registry.keys
    assert TRUSTED_MATCHED_RECOVERY_STAGE.key in registry.keys
    assert defaults is not None
    assert defaults == production_standard_v2_registry().keys
    assert len(defaults) == 4
    assert "path-standard" in defaults
    assert "paired-scientific-report" in defaults
    assert "raw-validate" not in defaults
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key not in defaults
    assert TRUSTED_MATCHED_RECOVERY_STAGE.key not in defaults
    expected_configuration = {
        "stages": production_standard_v2_configuration(),
        "pipeline": "standard-v2",
    }
    expected_graph = {
        "stages": [
            registry.get(stage.key).spec.model_dump(mode="json")
            for stage in registry.graph(defaults).plan()
        ]
    }
    with processing_database.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT configuration, configuration_digest, graph_digest "
                "FROM pipeline_release WHERE id='wp11-dynamic-release'"
            )
        ).one()
    assert row.configuration == expected_configuration
    assert row.configuration_digest == canonical_digest(expected_configuration)
    assert row.graph_digest == canonical_digest(expected_graph)
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    plan = compile_standard_run_plan(
        manifest,
        manifest_digest=verified_digest(manifest),
        pipeline_release_id="1" * 40,
    )
    assert len(plan.jobs) == 8
    assert len(plan.edges) == 10
    assert {job.stage_key for job in plan.jobs} == set(defaults)


def test_wp11_processing_roots_reject_qnap_alias_before_syscall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = []

    def forbidden_open(*args, **kwargs):
        probes.append((args, kwargs))
        raise AssertionError("QNAP target was probed")

    monkeypatch.setattr(native_release.os, "open", forbidden_open)
    with pytest.raises(ValueError, match="double slash|QNAP"):
        build_processing_backend(
            ProcessingBackendSettings(
                database_url="postgresql+psycopg:///must-not-connect",
                bulk_root=Path("//mnt/qnap01/never-probe"),
                corpus_root=tmp_path,
            )
        )
    assert probes == []


def test_postgres_concurrent_wp11_queue_is_exactly_idempotent(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_receipt, _scientific = _campaign(tmp_path / "campaign", monkeypatch)
    catalog = processing_database.catalog
    release_id = "wp11-concurrent-release"
    catalog.add_pipeline_release(
        release_id=release_id,
        code_revision="1" * 40,
        environment_digest="sha256:" + "2" * 64,
        graph_digest="sha256:" + "3" * 64,
    )
    checks = {
        check.session_id: check
        for trial in capture_receipt.trial_receipts
        for check in trial.checks
    }
    for session_id, check in checks.items():
        catalog.create_capture_session(
            session_id=session_id,
            source_type="test",
            state="committed",
            bundle_uri=check.bundle_uri,
            manifest_digest=check.manifest_sha256,
            tags=("TEST",),
        )

    qualification = tmp_path / "qualification"
    capture_root = tmp_path / "capture"
    artifacts_root = tmp_path / "artifacts"
    qualification.mkdir()
    capture_root.mkdir()
    capture_path = capture_root / "accepted.json"
    capture_path.write_text(capture_receipt.model_dump_json(), encoding="utf-8")
    capture_path.chmod(0o440)

    plan_pin = PinnedLocalRoot(qualification)
    plans = ImmutableWP11PlanStore(plan_pin)
    plan_pin.close()
    capture_pin = PinnedLocalRoot(capture_root)
    capture_authority = ImmutableCaptureCampaignAuthority(capture_pin)
    capture_pin.close()
    processing = ProcessingService(
        catalog=catalog,
        artifacts=AnalysisArtifactStore(artifacts_root),
        registry=AnalyzerRegistry((_Delegate(), _MatchedDelegate())),
        iq_readers=object(),  # type: ignore[arg-type]
    )
    workflow = WP11ProductionWorkflow(
        plans=plans,
        capture=capture_authority,
        catalog=catalog,
        processing=processing,
        trusted=object(),  # type: ignore[arg-type]
        pipeline_release_id=release_id,
    )
    workflow.create(
        campaign_id="concurrent-campaign",
        capture=ImmutableDocumentRefV1(
            logical_uri="qualification://capture/accepted.json",
            digest=canonical_digest(capture_receipt.model_dump(mode="json")),
        ),
        processing_config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_binding(release=release_id)
        ),
    )

    first_session_id = sorted(checks)[0]
    first_run_id = wp11_run_id("concurrent-campaign", first_session_id)
    race = Barrier(2)
    original_create = processing.create_reprocess_run

    def synchronized_create(**values) -> None:
        if values["run_id"] == first_run_id:
            race.wait(timeout=10)
        original_create(**values)

    monkeypatch.setattr(processing, "create_reprocess_run", synchronized_create)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(lambda _index: workflow.queue("concurrent-campaign"), range(2))
        )

    assert results[0].run_ids == results[1].run_ids
    assert len(results[0].run_ids) == 30
    assert sum(result.already_queued_count for result in results) == 30
    for run_id in results[0].run_ids:
        snapshot = catalog.run_seal_snapshot(run_id)
        assert snapshot.execution.promotion_policy == PromotionPolicy.EVIDENCE_ONLY.value
        assert len(snapshot.jobs) in {2, 4}
    capture_authority.close()
    plans.close()
