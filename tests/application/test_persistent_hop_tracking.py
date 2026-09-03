from __future__ import annotations

from pathlib import Path

import pytest

import leo.scanner.persistent_hop_analysis as persistent_source_module
from leo.application.persistent_hop_analysis_v2 import PersistentHopAnalysisServiceV2
from leo.application.persistent_hop_tracking import PersistentHopTrackingService
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.persistent_hop_analysis_v2 import render_persistent_hop_analysis_pngs_v2
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore


def _fractional_dwell(_samples, configuration, *, edge) -> DwellGlrt64Analysis:
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=0.05,
        full_best_margin=0.05,
        reason=f"fixture {edge}",
        probes=tuple(
            Glrt64ProbeResponse(
                receiver_id=receiver_id,
                probe_index=probe_index,
                probe_start_ms=probe_index * configuration.probe_stride_ms,
                candidates=(
                    Glrt64CandidateResponse(
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
                    ),
                ),
            )
            for probe_index in range(configuration.scheduled_probe_count)
            for receiver_id in configuration.receiver_ids
        ),
    )


def test_legacy_capture_is_terminally_unsupported_instead_of_inventing_utc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="scan-hop-legacy-tracking")
    captures = PersistentHopIqStore(tmp_path)
    writer = captures.begin("scan-hop-legacy-tracking", plan)
    writer.append(session.read_visit())
    session.request_cancel()
    writer.finish(session.finish())
    radio.close()

    analyses = PersistentHopAnalysisStoreV2(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fractional_dwell)
    analysis = PersistentHopAnalysisServiceV2(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=analyses,
        renderer=render_persistent_hop_analysis_pngs_v2,
        probe_stride_ms=120,
    )
    assert analysis.run_pending(maximum_sessions=1).failures == ()

    products = PersistentHopTrackingStore(tmp_path)
    service = PersistentHopTrackingService(
        captures=PersistentHopIqStore.open_read_only(tmp_path),
        analyses=analyses,
        products=products,
        tle_archive=TleArchiveReader(tmp_path / "tle"),
        observer_site=ObserverSiteV1(
            latitude_deg=37.858988,
            longitude_deg=-122.478103,
            altitude_m=-29.0,
            label="Spinnaker, Sausalito",
        ),
        renderer=lambda *_args: pytest.fail("legacy captures must not be rendered"),
    )

    summary = service.run_pending(maximum_sessions=1)

    assert summary.failures == ()
    assert summary.unsupported_session_ids == ("scan-hop-legacy-tracking",)
    publication = products.inspect("scan-hop-legacy-tracking")
    assert publication.manifest.terminal_outcome == "unsupported"
    assert publication.manifest.terminal_reasons == (
        "utc-timing-authority-unavailable-in-capture-manifest-v1",
    )
    assert products.status("scan-hop-legacy-tracking").state == "unsupported"
    assert service.run_pending(maximum_sessions=1).requested_session_count == 0
