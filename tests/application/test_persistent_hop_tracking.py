from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import leo.application.persistent_hop_tracking as tracking_module
import leo.scanner.persistent_hop_analysis as persistent_source_module
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryConfig,
)
from leo.application.persistent_hop_analysis_v2 import PersistentHopAnalysisServiceV2
from leo.application.persistent_hop_tracking import PersistentHopTrackingService
from leo.application.persistent_hop_trajectory import (
    PersistentHopTrajectoryProjection,
    PersistentHopTrajectoryProjectionConfig,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.states import StarlinkEdge
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.persistent_hop_analysis_v2 import render_persistent_hop_analysis_pngs_v2
from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import (
    PersistentHopUtcTimingAuthorityV1,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.persistent_hop_tracking import PersistentHopTrackingStatusV1
from leo.sky.propagation import element_line_checksum, parse_element_sets
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore

_BASE_LINE_ONE = "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"
_BASE_LINE_TWO = "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"


def _valid_element_line(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _snapshot_payload() -> str:
    records: list[str] = []
    for index, mean_anomaly_deg in enumerate(range(0, 360, 30)):
        catalog_number = 44714 + index
        first = _valid_element_line(f"1 {catalog_number:05d}{_BASE_LINE_ONE[7:]}")
        second = f"2 {catalog_number:05d}{_BASE_LINE_TWO[7:]}"
        second = _valid_element_line(second[:43] + f"{mean_anomaly_deg:8.4f}" + second[51:])
        records.extend((f"STARLINK-{catalog_number}", first, second))
    return "\n".join(records) + "\n"


def _site() -> ObserverSiteV1:
    return ObserverSiteV1(
        latitude_deg=37.858988,
        longitude_deg=-122.478103,
        altitude_m=-29.0,
        label="Spinnaker, Sausalito",
    )


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


def _v2_capture(
    tmp_path: Path,
    *,
    session_id: str,
    first_sample_utc_ns: int,
):  # type: ignore[no-untyped-def]
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id=session_id)
    block = session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id=receipt.session_id,
        session_start_device_sample_counter=receipt.session_start_device_sample_counter,
        sample_rate_hz=plan.sample_rate_hz,
        begin_before_realtime_ns=first_sample_utc_ns,
        begin_before_monotonic_ns=100_000_000_000,
        begin_after_realtime_ns=first_sample_utc_ns + 1_000_000,
        begin_after_monotonic_ns=100_001_000_000,
        terminal_realtime_ns=first_sample_utc_ns + 140_000_000,
        terminal_monotonic_ns=100_140_000_000,
    )
    store = PersistentHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, plan)
    writer.append(block)
    return writer.finish(receipt, timing=timing)


def _long_scan_projection(
    *,
    session_id: str,
    manifest_digest: str,
    base_utc_ns: int,
    config_digest: str,
) -> PersistentHopTrajectoryProjection:
    authority = canonical_digest({"authority": session_id})
    actual_rf_hz = 10_709_687_500.0
    scale = 11_200_000_000.0 / actual_rf_hz
    candidates = tuple(
        PersistentHopCfoCandidate(
            candidate_id=canonical_digest({"candidate": point}),
            source_group_id=canonical_digest({"source": point}),
            candidate_rank=0,
            session_id=session_id,
            input_manifest_digest=manifest_digest,
            raw_recording_authority_digest=authority,
            radio_id="radio-pluto-test",
            stream_generation="iio-0000000000000001",
            receiver_id=0,
            visit_index=point,
            probe_index=0,
            channel=1,
            edge=StarlinkEdge.LOWER,
            actual_rf_hz=actual_rf_hz,
            source_sample_start=point * 100_000,
            source_sample_end=point * 100_000 + 50_000,
            support_start_utc_ns=base_utc_ns + point * 1_000_000_000 - 10_000_000,
            support_center_utc_ns=base_utc_ns + point * 1_000_000_000,
            support_end_utc_ns=base_utc_ns + point * 1_000_000_000 + 10_000_000,
            measured_cfo_hz=(350_000.0 - 2_000.0 * point) / scale,
            standard_uncertainty_hz=400.0,
            factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
            exact_score=0.15,
            control_score=0.10,
            margin=0.05,
        )
        for point in range(0, 301, 4)
    )
    count = len(candidates)
    return PersistentHopTrajectoryProjection(
        candidates=candidates,
        input_probe_count=count,
        nonoverlapping_probe_count=count,
        fractionally_scored_candidate_count=count,
        passing_fractional_candidate_count=count,
        projected_candidate_count=count,
        input_manifest_digest=manifest_digest,
        raw_recording_authority_digest=authority,
        config_digest=config_digest,
    )


def test_v2_capture_publishes_complete_300_second_tracking_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "scan-hop-v2-tracking"
    tle_payload = _snapshot_payload()
    tle_epoch_utc_ns = parse_element_sets(tle_payload).element_epoch_utc_ns()[0]
    base_utc_ns = tle_epoch_utc_ns + 58_000 * 1_000_000_000
    capture = _v2_capture(
        tmp_path,
        session_id=session_id,
        first_sample_utc_ns=base_utc_ns,
    )
    analyses = PersistentHopAnalysisStoreV2(tmp_path)
    monkeypatch.setattr(persistent_source_module, "analyze_glrt64_dwell", _fractional_dwell)
    analysis = PersistentHopAnalysisServiceV2(
        inputs=PersistentHopAnalysisInputStore(PersistentHopIqStore(tmp_path)),
        products=analyses,
        renderer=render_persistent_hop_analysis_pngs_v2,
        probe_stride_ms=120,
    )
    assert analysis.run_pending(maximum_sessions=1).failures == ()
    analyzed = analyses.inspect(session_id)

    products = PersistentHopTrackingStore(tmp_path)
    projection_config = PersistentHopTrajectoryProjectionConfig()
    trajectory_config = PersistentHopTrajectoryConfig(maximum_gap_s=5.0)
    service = PersistentHopTrackingService(
        captures=PersistentHopIqStore.open_read_only(tmp_path),
        analyses=analyses,
        products=products,
        tle_archive=TleArchiveReader(tmp_path / "tle"),
        observer_site=_site(),
        renderer=render_persistent_hop_tracking_png,
        projection_config=projection_config,
        trajectory_config=trajectory_config,
        maximum_physical_groups=1,
    )
    projection = _long_scan_projection(
        session_id=session_id,
        manifest_digest=capture.manifest_sha256,
        base_utc_ns=base_utc_ns,
        config_digest=projection_config.digest,
    )

    def project(manifest, chunks, *, input_manifest_sha256, config):  # type: ignore[no-untyped-def]
        assert manifest == capture.manifest
        assert chunks == analyses.published_chunks(session_id)
        assert input_manifest_sha256 == capture.manifest_sha256
        assert config.digest == projection.config_digest
        return projection

    monkeypatch.setattr(tracking_module, "project_fractional_persistent_hop_candidates", project)
    digest = sha256_digest(tle_payload.encode("ascii"))
    collected_utc_ns = base_utc_ns - 3_600 * 1_000_000_000
    archive = tmp_path / "tle" / "archive" / "space-track"
    archive.mkdir(parents=True)
    (archive / f"{collected_utc_ns}-{digest.removeprefix('sha256:')}.tle").write_text(
        tle_payload,
        encoding="ascii",
    )

    manifest = service.track_session(session_id)

    assert manifest.terminal_outcome == "complete"
    assert manifest.input_manifest_sha256 == capture.manifest_sha256
    assert manifest.fractional_analysis_manifest_sha256 == analyzed.manifest_sha256
    assert manifest.projected_candidate_count == 76
    assert manifest.trajectory_hypothesis_count == 1
    assert manifest.physical_group_count == 1
    assert manifest.tle_matching_attempted_group_count == 1
    assert len(manifest.tracklets) == 1
    assert (manifest.tracklets[0].end_utc_ns - manifest.tracklets[0].start_utc_ns) / 1e9 == (
        pytest.approx(300.02)
    )
    assert len(manifest.tle_candidates) == 1
    assert manifest.tle_candidates[0].candidate_only
    assert manifest.tle_candidates[0].identity_claimed is False
    assert manifest.tle_snapshot is not None
    assert manifest.tle_snapshot.digest == digest
    artifact = products.artifact(session_id)
    assert artifact is not None
    assert artifact.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(artifact) > 10_000
    assert products.status(session_id).state == "complete"


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

    products.write_status(
        PersistentHopTrackingStatusV1(
            session_id="scan-hop-legacy-tracking",
            state="failed",
            phase="waiting",
            updated_at=datetime.now(tz=UTC),
            failure_summary="deterministic failure is quarantined",
        )
    )
    assert service.run_pending(maximum_sessions=1).requested_session_count == 0

    summary = service.run_pending(
        maximum_sessions=1,
        session_id="scan-hop-legacy-tracking",
    )

    assert summary.failures == ()
    assert summary.unsupported_session_ids == ("scan-hop-legacy-tracking",)
    publication = products.inspect("scan-hop-legacy-tracking")
    assert publication.manifest.terminal_outcome == "unsupported"
    assert publication.manifest.terminal_reasons == (
        "utc-timing-authority-unavailable-in-capture-manifest-v1",
    )
    assert products.status("scan-hop-legacy-tracking").state == "unsupported"
    assert service.run_pending(maximum_sessions=1).requested_session_count == 0
