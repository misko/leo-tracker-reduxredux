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
) -> ScientificCampaignStreamRegistration:
    session_id = f"science-session-{ordinal:02d}"
    stream_id = f"science-stream-{ordinal:02d}"
    run_id = f"science-run-{ordinal:02d}"
    capture_uri = f"bulk://recordings/2026/08/19/{session_id}"
    scientific_uri = f"bulk://analysis/{session_id}/{run_id}/scientific/result.json"
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
        promotion_policy=PromotionPolicy.CURRENT,
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
    harness: CatalogHarness, *, count: int = 40
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
    )


def test_exact_40_member_seal_is_idempotent_and_database_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    members = _campaign_with_members(catalog_harness)
    repeated = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-campaign", stream=members[0]
    )
    assert len(repeated.streams) == 40

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
    crossed_identity = replace(
        members[0], analysis_product_id=members[1].analysis_product_id
    )
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
        assert connection.execute(
            text("SELECT count(*) FROM scientific_campaign_stream")
        ).scalar_one() == 40


def test_campaign_members_override_raw_and_product_retention(
    catalog_harness: CatalogHarness,
) -> None:
    members = _campaign_with_members(catalog_harness, count=1)
    member = members[0]
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
            product_id=member.analysis_product_id,
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
    second_uri = (
        f"bulk://analysis/{first.session_id}/{first.analysis_run_id}/scientific/peer.json"
    )
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
            text(
                "UPDATE frequency_calibration SET valid_until = :until WHERE id = :id"
            ),
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
            text(
                "UPDATE frequency_calibration SET valid_until = :until WHERE id = :id"
            ),
            {
                "until": datetime(2026, 8, 19, 1, 1, tzinfo=UTC),
                "id": member.frequency_calibration_id,
            },
        )
    record = catalog_harness.repository.add_scientific_campaign_stream(
        campaign_id="wp11-validity-boundary", stream=member
    )
    assert len(record.streams) == 1
