from __future__ import annotations

from pathlib import Path

import pytest

import leo.scanner.persistent_hop_analysis as persistent_source_module
from leo.application.persistent_hop_analysis import PersistentHopAnalysisService
from leo.application.persistent_hop_analysis_v2 import PersistentHopAnalysisServiceV2
from leo.presentation.persistent_hop_analysis import render_persistent_hop_analysis_pngs
from leo.presentation.persistent_hop_analysis_v2 import render_persistent_hop_analysis_pngs_v2
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis import PersistentHopAnalysisStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from leo.storage.persistent_hop_analysis_v2 import (
    PersistentHopAnalysisStoreV2,
    PersistentHopPresentationStoreV2,
)


def _capture(root: Path, receiver_id=None) -> PersistentHopIqStore:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    if receiver_id is not None:
        from leo.scanner.single_rx import SingleRxPersistentHopPlanV2

        plan = SingleRxPersistentHopPlanV2(
            receiver_ids=(receiver_id,),
            transition_guard_samples=10_000,
            profiles=plan.profiles,
        )
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="hop-fractional-v2")
    captures = PersistentHopIqStore(root)
    writer = captures.begin("hop-fractional-v2", plan)
    writer.append(session.read_visit())
    session.request_cancel()
    receipt = session.finish()
    timing = None
    if receiver_id is not None:
        from leo.scanner.single_rx import SingleRxHopTimingV2

        timing = SingleRxHopTimingV2.from_host_bracket(
            session_id=receipt.session_id,
            session_start_device_sample_counter=receipt.session_start_device_sample_counter,
            sample_rate_hz=plan.sample_rate_hz,
            begin_before_realtime_ns=1_000_000_000,
            begin_after_realtime_ns=1_001_000_000,
            begin_before_monotonic_ns=2_000_000_000,
            begin_after_monotonic_ns=2_001_000_000,
            terminal_realtime_ns=2_000_000_000,
            terminal_monotonic_ns=3_000_000_000,
        )
    writer.finish(receipt, timing=timing)
    radio.close()
    return captures


@pytest.mark.parametrize("receiver_id", [0, 1])
def test_single_rx_analysis_publication_and_v4_history(tmp_path, monkeypatch, receiver_id):
    captures = _capture(tmp_path, receiver_id)
    current = PersistentHopAnalysisStoreV2(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fractional_dwell)
    service = PersistentHopAnalysisServiceV2(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=current,
        renderer=render_persistent_hop_analysis_pngs_v2,
        probe_stride_ms=120,
    )
    assert service.run_pending(maximum_sessions=1).failures == ()
    publication = current.inspect("hop-fractional-v2")
    assert publication.manifest.schema_version == 3
    assert publication.manifest.sample_rate_hz == 10_000_000
    assert publication.manifest.probe_count == 1
    (chunk,) = current.published_chunks("hop-fractional-v2")
    assert chunk.schema_version == 3 and chunk.receiver_ids == (receiver_id,)
    assert chunk.probes[0].receiver_id == receiver_id
    candidate = chunk.probes[0].fractional_candidates[0]
    assert candidate.fractional_tracking_cfo_hz == 1018.0
    presentation = PersistentHopPresentationStoreV2(captures, current)
    assert presentation.page_v3(cursor=0, limit=5).total == 0
    page = presentation.page_v4(cursor=0, limit=5)
    assert page.schema_version == 4 and page.items[0].capture.receiver_ids == (receiver_id,)
    detail = presentation.detail_v3("hop-fractional-v2")
    assert detail.product == publication.manifest
    assert presentation.detail_v2("hop-fractional-v2") is None
    from fastapi.testclient import TestClient

    from leo.api.app import create_app
    from leo.presentation.fixtures import build_fixture_repository

    client = TestClient(
        create_app(
            build_fixture_repository(tmp_path),
            artifact_root=tmp_path,
            persistent_hop_presentations_v2=presentation,
        )
    )
    response = client.get("/api/v4/scanner/persistent-sessions")
    assert response.status_code == 200
    assert response.json()["items"][0]["capture"]["receiver_ids"] == [receiver_id]
    response = client.get("/api/v4/scanner/persistent-sessions/hop-fractional-v2")
    assert (
        response.status_code == 200 and response.json()["product"]["sample_rate_hz"] == 10_000_000
    )


def _fractional_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    responses = []
    for probe_index in range(configuration.scheduled_probe_count):
        for receiver_id in configuration.receiver_ids:
            candidate = Glrt64CandidateResponse(
                candidate_rank=0,
                epoch_sample=100,
                acquired_cfo_hz=1_000.0,
                residual_cfo_hz=20.0,
                tracking_cfo_hz=1_020.0,
                exact_score=0.14,
                control_score=0.10,
                margin=0.04,
                passed_margin_gate=True,
                fractional_epoch_status="complete",
                fractional_epoch_offset_samples=0.25,
                fractional_frame_phase_sample=100.25,
                fractional_exact_score=0.15,
                fractional_control_score=0.10,
                fractional_residual_cfo_hz=18.0,
                fractional_tracking_cfo_hz=1_018.0,
                fractional_margin=0.05,
            )
            responses.append(
                Glrt64ProbeResponse(
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * configuration.probe_stride_ms,
                    candidates=(candidate,),
                )
            )
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=0.04,
        full_best_margin=0.04,
        reason=f"fixture {edge}",
        probes=tuple(responses),
    )


def _empty_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=None,
        full_best_margin=None,
        reason=f"empty {edge}",
        probes=tuple(
            Glrt64ProbeResponse(
                receiver_id=receiver_id,
                probe_index=probe_index,
                probe_start_ms=probe_index * configuration.probe_stride_ms,
                candidates=(),
            )
            for probe_index in range(configuration.scheduled_probe_count)
            for receiver_id in configuration.receiver_ids
        ),
    )


def test_v2_publication_is_separate_from_immutable_v1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = _capture(tmp_path)
    inputs = PersistentHopAnalysisInputStore(captures)
    legacy = PersistentHopAnalysisStore(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _empty_dwell)
    legacy_service = PersistentHopAnalysisService(
        inputs=inputs,
        products=legacy,
        renderer=render_persistent_hop_analysis_pngs,
        probe_stride_ms=120,
    )
    assert legacy_service.run_pending(maximum_sessions=1).failures == ()
    legacy_publication = legacy.inspect("hop-fractional-v2")
    legacy_digest = legacy_publication.manifest_sha256

    current = PersistentHopAnalysisStoreV2(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fractional_dwell)
    current_service = PersistentHopAnalysisServiceV2(
        inputs=inputs,
        products=current,
        renderer=render_persistent_hop_analysis_pngs_v2,
        probe_stride_ms=120,
    )
    assert current_service.run_pending(maximum_sessions=1).failures == ()

    publication = current.inspect("hop-fractional-v2")
    assert publication.manifest.analysis_id == "persistent-hop-fractional-glrt64-cfo-v2"
    assert publication.manifest.probe_count == 2
    assert publication.manifest.fractionally_scored_candidate_count == 2
    assert publication.manifest.passed_fractional_candidate_count == 2
    assert publication.manifest.fractionally_scored_best_count == 2
    assert publication.manifest.passed_fractional_best_count == 2
    assert publication.path.name == "persistent-hop-fractional-glrt64-cfo-v2"
    assert legacy.inspect("hop-fractional-v2").manifest_sha256 == legacy_digest
    assert legacy_publication.path != publication.path
    assert (publication.path / "metrics-sweep-000000.v2.json.zst").is_file()
    assert (publication.path / "work-manifest.v2.json").is_file()
    sealed_chunks = current.published_chunks("hop-fractional-v2")
    assert len(sealed_chunks) == 1
    assert sealed_chunks[0].session_id == "hop-fractional-v2"
    for artifact in ("coverage", "glrt64-response", "cfo-trajectories"):
        payload = current.artifact("hop-fractional-v2", artifact)
        assert payload is not None and payload.startswith(b"\x89PNG\r\n\x1a\n")

    presentation = PersistentHopPresentationStoreV2(captures, current)
    page = presentation.page_v3(cursor=0, limit=5)
    assert page.items[0].analysis.schema_version == 2
    assert page.items[0].analysis.state == "complete"
    detail = presentation.detail_v2("hop-fractional-v2")
    assert detail is not None and detail.product == publication.manifest
