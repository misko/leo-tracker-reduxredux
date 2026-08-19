from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from leo.catalog import (
    CurrentSummary,
    InvalidStateError,
    JobDefinition,
    ProductConflictError,
    ProductRegistration,
    PromotionPolicy,
    RadioStreamRegistration,
    RecordingChunkRegistration,
    ScientificCampaignRegistration,
    ScientificCampaignSeal,
    ScientificCampaignStreamRegistration,
)

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _seed_station(harness: CatalogHarness) -> int:
    with harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO radio (id, serial, uri, transport) "
                "VALUES ('science-radio', 'science-serial', 'ip:192.0.2.1', 'ethernet')"
            )
        )
        receiver_path_id = connection.execute(
            text(
                "INSERT INTO receiver_path (radio_id, receiver_id, label) "
                "VALUES ('science-radio', 1, 'RX1') RETURNING id"
            )
        ).scalar_one()
        calibration_id = connection.execute(
            text(
                "INSERT INTO frequency_calibration "
                "(receiver_path_id, center_offset_hz, valid_from, evidence_uri, evidence_digest) "
                "VALUES (:path, 1250.0, :valid_from, :uri, :digest) RETURNING id"
            ),
            {
                "path": receiver_path_id,
                "valid_from": datetime(2026, 8, 19, tzinfo=UTC),
                "uri": "bulk://calibration/wp11.json",
                "digest": DIGEST_C,
            },
        ).scalar_one()
    harness.repository.add_pipeline_release(
        release_id="science-release",
        code_revision="science-code",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
    )
    return int(calibration_id)


def _seed_stream(
    harness: CatalogHarness,
    *,
    ordinal: int,
    calibration_id: int,
    preexisting_capture: bool = False,
) -> ScientificCampaignStreamRegistration:
    session_id = f"science-session-{ordinal:02d}"
    stream_id = f"science-stream-{ordinal:02d}"
    run_id = f"science-run-{ordinal:02d}"
    capture_uri = f"bulk://recordings/2026/08/19/{session_id}"
    scientific_uri = f"bulk://analysis/{session_id}/{run_id}/scientific/result.json"
    if not preexisting_capture:
        harness.repository.create_capture_session(
            session_id=session_id,
            source_type="live",
            state="committed",
            bundle_uri=capture_uri,
            manifest_digest=DIGEST_A,
            allocated_bytes=1_000,
            observed_start_at=datetime(2026, 8, 19, 1, tzinfo=UTC),
            observed_end_at=datetime(2026, 8, 19, 1, 1, tzinfo=UTC),
        )
        with harness.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO radio_stream "
                    "(id, session_id, radio_id, state, receiver_ids, sample_rate_hz, "
                    "captured_sample_count) "
                    "VALUES (:id, :session, 'science-radio', 'complete', ARRAY[1], 2500000, "
                    "150000000)"
                ),
                {"id": stream_id, "session": session_id},
            )
    harness.repository.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id="science-release",
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="matched", scope_key=stream_id),),
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
    )
    lease = harness.repository.claim_job(
        worker_id=f"science-worker-{ordinal}", lease_for=timedelta(minutes=1)
    )
    assert lease is not None and lease.run_id == run_id
    product_id = harness.repository.register_product(
        ProductRegistration(
            run_id=run_id,
            stage_key="matched",
            scope_key=stream_id,
            kind="starlink.matched-acceptance",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri=scientific_uri,
            digest=DIGEST_B,
            byte_size=500,
        )
    )
    harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )
    harness.repository.seal_and_promote(
        run_id=run_id,
        manifest_uri=f"bulk://analysis/{session_id}/{run_id}/manifest.json",
        manifest_digest=DIGEST_C,
        summary=CurrentSummary(candidate_count=1),
    )
    return ScientificCampaignStreamRegistration(
        ordinal=ordinal,
        session_id=session_id,
        stream_id=stream_id,
        analysis_run_id=run_id,
        analysis_run_uri=f"bulk://analysis/{session_id}/{run_id}/manifest.json",
        analysis_run_digest=DIGEST_C,
        pipeline_release_id="science-release",
        analysis_product_id=product_id,
        frequency_calibration_id=calibration_id,
        capture_uri=capture_uri,
        capture_digest=DIGEST_A,
        calibration_uri="bulk://calibration/wp11.json",
        calibration_digest=DIGEST_C,
        scientific_uri=scientific_uri,
        scientific_digest=DIGEST_B,
        status="pass",
    )


def _campaign_with_members(
    harness: CatalogHarness, *, count: int = 40, bind: bool = True
) -> tuple[ScientificCampaignStreamRegistration, ...]:
    calibration_id = _seed_station(harness)
    harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-campaign",
            capture_uri="bulk://qualification/wp11/capture-receipt.json",
            capture_digest=DIGEST_A,
        )
    )
    members = tuple(
        _seed_stream(harness, ordinal=index, calibration_id=calibration_id)
        for index in range(count)
    )
    if bind:
        for member in members:
            harness.repository.add_scientific_campaign_stream(
                campaign_id="wp11-campaign", stream=member
            )
    return members


def _seal(*, presentation_digest: str = DIGEST_C) -> ScientificCampaignSeal:
    return ScientificCampaignSeal(
        scientific_uri="bulk://qualification/wp11/scientific-receipt.json",
        scientific_digest=DIGEST_B,
        presentation_uri="bulk://qualification/wp11/presentation-receipt.json",
        presentation_digest=presentation_digest,
        result_status="pass",
        outer_seal_uri="bulk://qualification/wp11/outer-seal.json",
        outer_seal_digest=DIGEST_A,
    )


def test_exact_40_member_seal_is_idempotent_and_database_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    members = _campaign_with_members(catalog_harness)
    repeated = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-campaign", stream=members[0]
    )
    assert len(repeated.streams) == 40
    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-open-campaign",
            capture_uri="bulk://qualification/wp11/open-capture.json",
            capture_digest=DIGEST_A,
        )
    )

    sealed = catalog_harness.repository.seal_scientific_campaign(
        campaign_id="wp11-campaign", seal=_seal()
    )
    retry = catalog_harness.repository.seal_scientific_campaign(
        campaign_id="wp11-campaign", seal=_seal()
    )
    assert sealed == retry
    assert sealed.state == "sealed" and sealed.result_status == "pass"
    assert tuple(item.ordinal for item in sealed.streams) == tuple(range(40))
    with pytest.raises(ProductConflictError, match="conflicts with retry"):
        catalog_harness.repository.seal_scientific_campaign(
            campaign_id="wp11-campaign", seal=_seal(presentation_digest=DIGEST_A)
        )
    crossed_identity = replace(members[0], analysis_product_id=members[1].analysis_product_id)
    with pytest.raises(ProductConflictError, match="conflicts"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-campaign", stream=crossed_identity
        )
    with pytest.raises(DBAPIError), catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE scientific_campaign SET result_status = 'fail' WHERE id = 'wp11-campaign'")
        )
    with pytest.raises(DBAPIError), catalog_harness.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM scientific_campaign_stream WHERE campaign_id = 'wp11-campaign'")
        )
    with pytest.raises(DBAPIError), catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE scientific_campaign_stream SET campaign_id = 'wp11-open-campaign' "
                "WHERE campaign_id = 'wp11-campaign' AND ordinal = 0"
            )
        )


def test_manifest_reconciled_stream_is_directly_eligible_for_campaign_membership(
    catalog_harness: CatalogHarness,
) -> None:
    calibration_id = _seed_station(catalog_harness)
    session_id = "science-session-00"
    stream_id = "science-stream-00"
    capture_uri = f"bulk://recordings/2026/08/19/{session_id}"
    observed_start = datetime(2026, 8, 19, 1, tzinfo=UTC)
    observed_end = datetime(2026, 8, 19, 1, 1, tzinfo=UTC)
    inserted = catalog_harness.repository.reconcile_capture_session(
        session_id=session_id,
        source_type="live",
        bundle_uri=capture_uri,
        manifest_digest=DIGEST_A,
        allocated_bytes=1_000,
        attributes={"reconciled": True},
        observed_start_at=observed_start,
        observed_end_at=observed_end,
        streams=(
            RadioStreamRegistration(
                stream_id=stream_id,
                radio_id="science-radio",
                radio_serial="science-serial",
                radio_uri="ip:192.0.2.1",
                radio_transport="ethernet",
                state="complete",
                receiver_ids=(1,),
                sample_rate_hz=2_500_000,
                captured_sample_count=150_000_000,
                observed_start_at=observed_start,
                observed_end_at=observed_end,
                attributes={"manifest": "exact"},
                chunks=(
                    RecordingChunkRegistration(
                        chunk_index=0,
                        sample_start=0,
                        sample_count=150_000_000,
                        logical_uri=f"{capture_uri}/streams/{stream_id}/chunk-0.zst",
                        compressed_digest=DIGEST_A,
                        uncompressed_digest=DIGEST_B,
                        compressed_bytes=1,
                        uncompressed_bytes=600_000_000,
                    ),
                ),
            ),
        ),
    )
    assert inserted
    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="reconciled-campaign",
            capture_uri="qualification://capture/reconciled.json",
            capture_digest=DIGEST_A,
        )
    )
    member = _seed_stream(
        catalog_harness,
        ordinal=0,
        calibration_id=calibration_id,
        preexisting_capture=True,
    )
    campaign = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="reconciled-campaign",
        stream=member,
    )
    assert len(campaign.streams) == 1
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text("SELECT session_id, stream_id FROM recording_chunk WHERE session_id=:session"),
            {"session": session_id},
        ).one() == (session_id, stream_id)


def test_incomplete_campaign_fails_closed_and_lineage_conflicts(
    catalog_harness: CatalogHarness,
) -> None:
    members = _campaign_with_members(catalog_harness, count=1)
    with pytest.raises(InvalidStateError, match="exactly 40"):
        catalog_harness.repository.seal_scientific_campaign(
            campaign_id="wp11-campaign", seal=_seal()
        )
    forged = replace(members[0], scientific_digest=DIGEST_A)
    with pytest.raises(ProductConflictError, match="conflicts"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-campaign", stream=forged
        )


def test_concurrent_exact_seal_serializes_and_retries_idempotently(
    catalog_harness: CatalogHarness,
) -> None:
    _campaign_with_members(catalog_harness)

    def seal() -> str:
        record = catalog_harness.repository.seal_scientific_campaign(
            campaign_id="wp11-campaign", seal=_seal()
        )
        return record.state

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda _index: seal(), range(8))) == ["sealed"] * 8
    with catalog_harness.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM scientific_campaign_stream")).scalar_one()
            == 40
        )


def test_campaign_members_override_raw_and_product_retention(
    catalog_harness: CatalogHarness,
) -> None:
    members = _campaign_with_members(catalog_harness, count=1)
    member = members[0]
    with catalog_harness.engine.begin() as connection:
        dependency_leaf = connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "(:run, 'survey', 'leaf', 'survey.leaf', 1, 'scientific', 'complete', "
                "'application/json', 'bulk://analysis/wp11/leaf.json', :digest, 30) "
                "RETURNING id"
            ),
            {"run": member.analysis_run_id, "digest": DIGEST_A},
        ).scalar_one()
        dependency_middle = connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "(:run, 'refine', 'middle', 'refine.middle', 1, 'scientific', 'complete', "
                "'application/json', 'bulk://analysis/wp11/middle.json', :digest, 40) "
                "RETURNING id"
            ),
            {"run": member.analysis_run_id, "digest": DIGEST_B},
        ).scalar_one()
        unrelated_product = connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "(:run, 'unrelated', 'other', 'unrelated.other', 1, 'scientific', "
                "'complete', 'application/json', 'bulk://analysis/wp11/unrelated.json', "
                ":digest, 50) RETURNING id"
            ),
            {"run": member.analysis_run_id, "digest": DIGEST_C},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO product_dependency (product_id, input_product_id) VALUES "
                "(:bound, :middle), (:middle, :leaf)"
            ),
            {
                "bound": member.analysis_product_id,
                "middle": dependency_middle,
                "leaf": dependency_leaf,
            },
        )
    catalog_harness.repository.create_analysis_run(
        run_id="replacement-run",
        session_id=member.session_id,
        pipeline_release_id="science-release",
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="replacement"),),
    )
    lease = catalog_harness.repository.claim_job(
        worker_id="replacement-worker", lease_for=timedelta(minutes=1)
    )
    assert lease is not None and lease.run_id == "replacement-run"
    catalog_harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )
    catalog_harness.repository.seal_and_promote(
        run_id="replacement-run",
        manifest_uri="bulk://analysis/replacement/manifest.json",
        manifest_digest=DIGEST_C,
        summary=CurrentSummary(),
    )

    identities = {
        (candidate.kind, candidate.item_id)
        for candidate in catalog_harness.repository.retention_candidates()
    }
    assert ("session", member.session_id) not in identities
    assert ("artifact", str(member.analysis_product_id)) not in identities
    assert ("artifact", str(dependency_middle)) not in identities
    assert ("artifact", str(dependency_leaf)) not in identities
    assert ("artifact", str(unrelated_product)) in identities
    claim = catalog_harness.repository.claim_product_for_purge(
        product_id=int(unrelated_product),
        claim_token="dependency-race-claim",
        lease_for=timedelta(minutes=1),
    )
    assert claim is not None
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO product_dependency (product_id, input_product_id) "
                "VALUES (:bound, :new_input)"
            ),
            {
                "bound": member.analysis_product_id,
                "new_input": unrelated_product,
            },
        )
    with pytest.raises(InvalidStateError, match="campaign won the product purge fence"):
        catalog_harness.repository.commit_product_purge(
            product_id=int(unrelated_product),
            claim_token="dependency-race-claim",
            staged_bytes=50,
        )
    assert (
        catalog_harness.repository.claim_session_for_purge(
            session_id=member.session_id,
            claim_token="campaign-session-claim",
            lease_for=timedelta(minutes=1),
        )
        is None
    )
    assert (
        catalog_harness.repository.claim_product_for_purge(
            product_id=int(dependency_leaf),
            claim_token="campaign-product-claim",
            lease_for=timedelta(minutes=1),
        )
        is None
    )


def test_paired_session_can_bind_two_scoped_products_from_one_run(
    catalog_harness: CatalogHarness,
) -> None:
    first = _campaign_with_members(catalog_harness, count=1)[0]
    second_stream_id = "science-stream-paired-peer"
    second_uri = f"bulk://analysis/{first.session_id}/{first.analysis_run_id}/scientific/peer.json"
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO radio (id, serial, uri, transport) "
                "VALUES ('science-radio-peer', 'science-serial-peer', "
                "'ip:192.0.2.2', 'ethernet')"
            )
        )
        path_id = connection.execute(
            text(
                "INSERT INTO receiver_path (radio_id, receiver_id, label) "
                "VALUES ('science-radio-peer', 1, 'RX1') RETURNING id"
            )
        ).scalar_one()
        calibration_id = connection.execute(
            text(
                "INSERT INTO frequency_calibration "
                "(receiver_path_id, center_offset_hz, valid_from, evidence_uri, evidence_digest) "
                "VALUES (:path, 1200, :valid, :uri, :digest) RETURNING id"
            ),
            {
                "path": path_id,
                "valid": datetime(2026, 8, 19, tzinfo=UTC),
                "uri": "bulk://calibration/wp11-peer.json",
                "digest": DIGEST_C,
            },
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO radio_stream "
                "(id, session_id, radio_id, state, receiver_ids, sample_rate_hz, "
                "captured_sample_count) VALUES "
                "(:id, :session, 'science-radio-peer', 'complete', ARRAY[1], 2500000, "
                "150000000)"
            ),
            {"id": second_stream_id, "session": first.session_id},
        )
        second_product_id = connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "(:run, 'matched', :scope, 'starlink.matched-acceptance', 1, "
                "'scientific', 'complete', 'application/json', :uri, :digest, 500) "
                "RETURNING id"
            ),
            {
                "run": first.analysis_run_id,
                "scope": second_stream_id,
                "uri": second_uri,
                "digest": DIGEST_C,
            },
        ).scalar_one()
    peer = replace(
        first,
        ordinal=1,
        stream_id=second_stream_id,
        analysis_product_id=second_product_id,
        frequency_calibration_id=int(calibration_id),
        calibration_uri="bulk://calibration/wp11-peer.json",
        scientific_uri=second_uri,
        scientific_digest=DIGEST_C,
    )
    record = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-campaign", stream=peer
    )
    assert len(record.streams) == 2
    assert record.streams[0].analysis_run_id == record.streams[1].analysis_run_id

    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-distinct-run",
            capture_uri="bulk://qualification/wp11/distinct-run-capture.json",
            capture_digest=DIGEST_A,
        )
    )
    catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-distinct-run", stream=first
    )
    distinct_run_id = "science-run-paired-distinct"
    distinct_uri = "bulk://analysis/wp11/distinct-peer.json"
    catalog_harness.repository.create_analysis_run(
        run_id=distinct_run_id,
        session_id=first.session_id,
        pipeline_release_id="science-release",
        input_manifest_digest=DIGEST_A,
        jobs=(JobDefinition(stage_key="matched", scope_key=second_stream_id),),
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
    )
    lease = catalog_harness.repository.claim_job(
        worker_id="distinct-run-worker", lease_for=timedelta(minutes=1)
    )
    assert lease is not None and lease.run_id == distinct_run_id
    distinct_product_id = catalog_harness.repository.register_product(
        ProductRegistration(
            run_id=distinct_run_id,
            stage_key="matched",
            scope_key=second_stream_id,
            kind="starlink.matched-acceptance",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri=distinct_uri,
            digest=DIGEST_A,
            byte_size=500,
        )
    )
    catalog_harness.repository.complete_job(
        job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
    )
    distinct_manifest_uri = "bulk://analysis/wp11/distinct-run-manifest.json"
    catalog_harness.repository.seal_and_promote(
        run_id=distinct_run_id,
        manifest_uri=distinct_manifest_uri,
        manifest_digest=DIGEST_A,
        summary=CurrentSummary(),
    )
    distinct_peer = replace(
        peer,
        analysis_run_id=distinct_run_id,
        analysis_run_uri=distinct_manifest_uri,
        analysis_run_digest=DIGEST_A,
        analysis_product_id=distinct_product_id,
        scientific_uri=distinct_uri,
        scientific_digest=DIGEST_A,
    )
    with pytest.raises(ProductConflictError, match="require one exact analysis run"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-distinct-run", stream=distinct_peer
        )


def test_product_scope_and_calibration_path_are_fail_closed(
    catalog_harness: CatalogHarness,
) -> None:
    member = _campaign_with_members(catalog_harness, count=1)[0]
    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-adversarial",
            capture_uri="bulk://qualification/wp11/capture-receipt-adversarial.json",
            capture_digest=DIGEST_A,
        )
    )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE analysis_product SET scope_key = 'wrong-stream' WHERE id = :id"),
            {"id": member.analysis_product_id},
        )
    with pytest.raises(InvalidStateError, match="product is unavailable or disagrees"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-adversarial", stream=member
        )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE analysis_product SET scope_key = :scope WHERE id = :id"),
            {"scope": member.stream_id, "id": member.analysis_product_id},
        )
        connection.execute(
            text(
                "UPDATE receiver_path SET receiver_id = 0 WHERE id = "
                "(SELECT receiver_path_id FROM frequency_calibration WHERE id = :id)"
            ),
            {"id": member.frequency_calibration_id},
        )
    with pytest.raises(ProductConflictError, match="calibration evidence disagrees"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-adversarial", stream=member
        )


def test_calibration_must_cover_full_capture_interval_inclusively(
    catalog_harness: CatalogHarness,
) -> None:
    member = _campaign_with_members(catalog_harness, count=1)[0]
    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-validity-boundary",
            capture_uri="bulk://qualification/wp11/capture-validity.json",
            capture_digest=DIGEST_A,
        )
    )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE frequency_calibration SET valid_until = :until WHERE id = :id"),
            {
                "until": datetime(2026, 8, 19, 1, 0, 59, tzinfo=UTC),
                "id": member.frequency_calibration_id,
            },
        )
    with pytest.raises(InvalidStateError, match="does not cover capture interval"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-validity-boundary", stream=member
        )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE frequency_calibration SET valid_until = :until WHERE id = :id"),
            {
                "until": datetime(2026, 8, 19, 1, 1, tzinfo=UTC),
                "id": member.frequency_calibration_id,
            },
        )
    record = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-validity-boundary", stream=member
    )
    assert len(record.streams) == 1


def test_campaign_rejects_a_current_promotion_run(
    catalog_harness: CatalogHarness,
) -> None:
    member = _campaign_with_members(catalog_harness, count=1)[0]
    catalog_harness.repository.create_scientific_campaign(
        ScientificCampaignRegistration(
            campaign_id="wp11-current-policy",
            capture_uri="bulk://qualification/wp11/current-policy.json",
            capture_digest=DIGEST_A,
        )
    )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE analysis_run SET promotion_policy = 'current' WHERE id = :run_id"),
            {"run_id": member.analysis_run_id},
        )
    with pytest.raises(InvalidStateError, match="must be sealed evidence-only"):
        catalog_harness.repository.add_scientific_campaign_stream(
            campaign_id="wp11-current-policy", stream=member
        )


def test_campaign_add_serializes_with_dependency_purge_commit(
    catalog_harness: CatalogHarness,
) -> None:
    member = _campaign_with_members(catalog_harness, count=1, bind=False)[0]
    with catalog_harness.engine.begin() as connection:
        dependency_id = connection.execute(
            text(
                "INSERT INTO analysis_product "
                "(run_id, stage_key, scope_key, kind, schema_version, role, status, "
                "media_type, logical_uri, digest, byte_size) VALUES "
                "(:run, 'upstream', 'upstream', 'science.upstream', 1, 'scientific', "
                "'complete', 'application/json', 'bulk://analysis/wp11/upstream.json', "
                ":digest, 75) RETURNING id"
            ),
            {"run": member.analysis_run_id, "digest": DIGEST_C},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO product_dependency (product_id, input_product_id) "
                "VALUES (:product, :input)"
            ),
            {"product": member.analysis_product_id, "input": dependency_id},
        )
    claim = catalog_harness.repository.claim_product_for_purge(
        product_id=int(dependency_id),
        claim_token="concurrent-dependency-purge",
        lease_for=timedelta(minutes=1),
    )
    assert claim is not None

    def commit_purge() -> str:
        catalog_harness.repository.commit_product_purge(
            product_id=int(dependency_id),
            claim_token="concurrent-dependency-purge",
            staged_bytes=75,
        )
        return "purged"

    def add_campaign() -> str:
        try:
            catalog_harness.repository.add_scientific_campaign_stream(
                campaign_id="wp11-campaign", stream=member
            )
        except InvalidStateError as error:
            assert "dependency is unavailable or purge-claimed" in str(error)
            return "blocked"
        return "added"

    with ThreadPoolExecutor(max_workers=2) as pool:
        commit_future = pool.submit(commit_purge)
        add_future = pool.submit(add_campaign)
        outcomes = {commit_future.result(), add_future.result()}
    assert outcomes == {"purged", "blocked"}
    campaign = catalog_harness.repository.scientific_campaign("wp11-campaign")
    assert campaign is not None and campaign.streams == ()
