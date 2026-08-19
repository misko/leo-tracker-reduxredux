from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.analysis.adapters import production_long_dwell_registry
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.application.wp11_dynamic import DynamicWP11Analyzer
from leo.application.wp11_operations import wp11_run_id
from leo.cli.processing import ProcessingBackendSettings, build_processing_backend
from leo.pipeline import AnalysisContext, StageOutcome, StageResult
from leo.qualification import native_release
from leo.qualification.trusted_matched_recovery_stage import TRUSTED_MATCHED_RECOVERY_STAGE

from .conftest import ProcessingDatabase


class _Delegate:
    spec = NATIVE_KNOWN_PILOT_EVIDENCE_STAGE

    def analyze(self, _context, _iq, _products, _outputs):
        return StageResult(outcome=StageOutcome.COMPLETE)


class _Plans:
    def __init__(self, plan=None) -> None:
        self.plan = plan

    def load_for_run(self, _run_id):
        if self.plan is None:
            raise FileNotFoundError(_run_id)
        return self.plan, object()


def _plan():
    inventory = SimpleNamespace(session_id="session-a", stream_id="stream-a")
    member = SimpleNamespace(inventory=inventory)
    return SimpleNamespace(
        campaign_id="campaign-a",
        plan_digest="sha256:" + "1" * 64,
        pipeline_release_id="release-a",
        members=(member,),
    )


def test_dynamic_wp11_analyzer_fails_closed_without_plan_or_exact_run_binding() -> None:
    missing = DynamicWP11Analyzer(  # type: ignore[arg-type]
        NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
        _Plans(),
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


def test_wp11_dynamic_stage_is_execution_only_not_a_default_run_stage() -> None:
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    default_stage_keys = registry.keys
    registry.register(  # type: ignore[arg-type]
        DynamicWP11Analyzer(
            NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
            _Plans(),  # type: ignore[arg-type]
            lambda _plan, _stage: _Delegate(),
        )
    )
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key in registry.keys
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key not in default_stage_keys


def test_postgres_processing_composition_loads_wp11_only_for_execution(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    bulk = tmp_path / "bulk"
    qualification = tmp_path / "qualification"
    legacy = tmp_path / "legacy"
    corpus = tmp_path / "corpus"
    for root in (bulk, qualification, legacy, corpus):
        root.mkdir()
    (bulk / "spool").mkdir()
    (bulk / "recordings").mkdir()
    (qualification / "frequency-calibration-plans").mkdir()
    (qualification / "frequency-calibration-promotions").mkdir()
    backend = build_processing_backend(
        ProcessingBackendSettings(
            database_url=processing_database.engine.url.render_as_string(
                hide_password=False
            ),
            bulk_root=bulk,
            corpus_root=corpus,
            pipeline_release_id="wp11-dynamic-release",
            qualification_root=qualification,
            legacy_evidence_root=legacy,
            scratch_root=tmp_path,
        )
    )

    registry = backend.services.processing.registry
    defaults = backend.services.processing.default_stage_keys
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key in registry.keys
    assert TRUSTED_MATCHED_RECOVERY_STAGE.key in registry.keys
    assert defaults is not None
    assert NATIVE_KNOWN_PILOT_EVIDENCE_STAGE.key not in defaults
    assert TRUSTED_MATCHED_RECOVERY_STAGE.key not in defaults


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
