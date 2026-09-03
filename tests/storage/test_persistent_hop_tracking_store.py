from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.scanner.persistent_hop_tracking import (
    PersistentHopTleCandidateV1,
    PersistentHopTrackingArtifactV1,
    PersistentHopTrackingManifestV1,
    PersistentHopTrajectoryTrackletV1,
)
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore


def _digest(label: str) -> str:
    return canonical_digest({"label": label})


def _manifest(session_id: str, start_ns: int) -> tuple[PersistentHopTrackingManifestV1, bytes]:
    artifact_payload = b"\x89PNG\r\n\x1a\ntracking"
    tracklet_id = _digest(f"tracklet-{session_id}")
    tracklet = PersistentHopTrajectoryTrackletV1(
        tracklet_id=tracklet_id,
        channel=2,
        edge="lower",
        receiver_id=0,
        actual_rf_hz=10_959_687_500.0,
        start_utc_ns=start_ns,
        end_utc_ns=start_ns + 300_000_000_000,
        observation_count=128,
        normalized_rate_hz_per_s=-2100.0,
        residual_rms_hz=320.0,
    )
    candidate = PersistentHopTleCandidateV1(
        hypothesis_rank=1,
        hypothesis_id=_digest(f"hypothesis-{session_id}"),
        physical_group_id=_digest(f"group-{session_id}"),
        representative_tracklet_id=tracklet_id,
        tracklet_ids=(tracklet_id,),
        source_observation_count=128,
        scored_observation_count=128,
        support_span_s=300.0,
        nominal_candidate_count=42,
        leading_catalog_number=44714,
        selected_tau_s=0.0,
        training_runner_negative_log_score_margin=12.0,
        training_leader_heldout_rank=1,
        heldout_runner_negative_log_score_margin=8.0,
        nominal_heldout_negative_log_score=100.0,
        radio_null_heldout_negative_log_score=120.0,
        wrong_time_minus_500_heldout_negative_log_score=140.0,
        wrong_time_plus_500_heldout_negative_log_score=150.0,
        leading_candidate_persisted_on_heldout=True,
        abstention_recommended=False,
        abstention_reasons=(),
        match_content_digest=_digest(f"match-{session_id}"),
    )
    created = datetime(2026, 9, 3, 12, tzinfo=UTC)
    manifest = PersistentHopTrackingManifestV1.create(
        session_id=session_id,
        created_at=created,
        completed_at=created + timedelta(minutes=1),
        input_manifest_sha256=_digest(f"input-{session_id}"),
        fractional_analysis_manifest_sha256=_digest(f"analysis-{session_id}"),
        projection_config_digest=_digest("projection"),
        trajectory_config_digest=_digest("trajectory"),
        tle_match_config_digest=_digest("tle-match"),
        observer_site=ObserverSiteV1(
            latitude_deg=37.858988,
            longitude_deg=-122.478103,
            altitude_m=-29.0,
            label="Spinnaker, Sausalito",
        ),
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=start_ns - 3_600_000_000_000,
            digest=_digest("tle"),
            object_count=8_000,
        ),
        terminal_outcome="complete",
        terminal_reasons=(),
        input_probe_count=4_000,
        nonoverlapping_probe_count=4_000,
        passing_fractional_candidate_count=1_000,
        projected_candidate_count=1_000,
        trajectory_hypothesis_count=1,
        physical_group_count=1,
        tle_matching_attempted_group_count=1,
        tracklets=(tracklet,),
        tle_candidates=(candidate,),
        unscored_physical_group_count=0,
        artifact=PersistentHopTrackingArtifactV1(
            sha256=sha256_digest(artifact_payload),
            byte_count=len(artifact_payload),
        ),
    )
    return manifest, artifact_payload


def test_tracking_store_seals_artifact_status_and_recurrence(tmp_path: Path) -> None:
    store = PersistentHopTrackingStore(tmp_path)
    first, first_png = _manifest("scan-hop-first", 1_788_400_000_000_000_000)
    second, second_png = _manifest("scan-hop-second", 1_788_401_200_000_000_000)

    first_publication = store.publish(first, artifact=first_png)
    store.publish(second, artifact=second_png)

    assert store.inspect("scan-hop-first").manifest == first
    assert first_publication.manifest_sha256.startswith("sha256:")
    assert store.artifact("scan-hop-first") == first_png
    assert store.status("scan-hop-first").state == "complete"
    detail = store.detail("scan-hop-first")
    assert detail.product == first

    recurrence = store.recurrences().items
    assert len(recurrence) == 1
    assert recurrence[0].catalog_number == 44714
    assert recurrence[0].session_ids == ("scan-hop-second", "scan-hop-first")
    assert recurrence[0].scan_count == 2
    assert recurrence[0].heldout_persistent_scan_count == 2
    assert recurrence[0].nonabstaining_scan_count == 2
    assert recurrence[0].candidate_only and recurrence[0].identity_claimed is False


def test_tracking_store_seals_legacy_capture_as_explicitly_unsupported(
    tmp_path: Path,
) -> None:
    store = PersistentHopTrackingStore(tmp_path)
    created = datetime(2026, 9, 3, 12, tzinfo=UTC)
    manifest = PersistentHopTrackingManifestV1.create(
        session_id="scan-hop-legacy",
        created_at=created,
        completed_at=created,
        input_manifest_sha256=_digest("legacy-input"),
        fractional_analysis_manifest_sha256=_digest("legacy-analysis"),
        projection_config_digest=_digest("projection"),
        trajectory_config_digest=_digest("trajectory"),
        terminal_outcome="unsupported",
        terminal_reasons=("utc-timing-authority-unavailable-in-capture-manifest-v1",),
    )

    store.publish(manifest, artifact=None)

    assert store.status("scan-hop-legacy").state == "unsupported"
    assert store.detail("scan-hop-legacy").product == manifest
    assert store.artifact("scan-hop-legacy") is None
