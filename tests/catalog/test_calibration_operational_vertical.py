from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from leo.application.calibration_runtime import (
    PostgresCalibrationOperationsAdapter,
    calibration_run_id,
)
from leo.application.frequency_calibration import TrustedFrequencyCalibrationPromoter
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogNotFoundError, CurrentSummary, JobDefinition, ProductRegistration
from leo.qualification.frequency_calibration_documents import (
    AnalysisArtifactTrustedDocumentAdapter,
    ImmutableCalibrationPlanStore,
)
from leo.qualification.frequency_calibration_extractor import EXTRACTOR_PRODUCT
from leo.qualification.frequency_calibration_stage import CALIBRATION_EXTRACTOR_STAGE
from leo.qualification.frequency_calibration_store import (
    AuthoritativeCalibrationResolver,
    ImmutableCalibrationPromotionStore,
)
from tests.qualification.test_frequency_calibration import (
    _CalibrationExecutionPort,
    _good_dwells,
    _plan,
    _RecordingPort,
    _ReleasePort,
)

from .conftest import CatalogHarness

DIGEST = "sha256:" + "a" * 64


class _VerifiedRecordings(_RecordingPort):
    def verify(self, bundle) -> None:
        self.verify_digests(bundle)


def test_fresh_database_bootstraps_verified_path_and_retry_resolves(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    plan = _plan()
    dwells = _good_dwells()
    artifacts = AnalysisArtifactStore(tmp_path / "bulk")
    bundles = {dwell.capture.recording_uri: _published_bundle(dwell.capture) for dwell in dwells}
    recordings = _VerifiedRecordings(bundles)
    recordings.extractions = {
        dwell.capture.manifest.session_id: dwell.extraction for dwell in dwells
    }
    repository = catalog_harness.repository
    repository.add_pipeline_release(
        release_id="test-release",
        code_revision=plan.extractor_git_revision,
        environment_digest=DIGEST,
        graph_digest=DIGEST,
    )

    for dwell in dwells:
        capture = dwell.capture
        session_id = capture.manifest.session_id
        repository.create_capture_session(
            session_id=session_id,
            source_type="live",
            state="committed",
            bundle_uri=capture.recording_uri,
            manifest_digest=capture.manifest_digest,
        )
        run_id = calibration_run_id(plan, session_id)
        repository.create_analysis_run(
            run_id=run_id,
            session_id=session_id,
            pipeline_release_id="test-release",
            input_manifest_digest=capture.manifest_digest,
            jobs=(
                JobDefinition(
                    stage_key=CALIBRATION_EXTRACTOR_STAGE.key,
                    scope_key=capture.stream_id,
                ),
            ),
            trigger="reprocess",
            promotion_policy="evidence_only",
        )
        published = artifacts.publish_json(
            session_id=session_id,
            run_id=run_id,
            stage_key=CALIBRATION_EXTRACTOR_STAGE.key,
            scope_key=capture.stream_id,
            product=EXTRACTOR_PRODUCT,
            document=dwell.extraction.model_dump(mode="json"),
        )
        repository.register_product(
            ProductRegistration(
                run_id=run_id,
                stage_key=CALIBRATION_EXTRACTOR_STAGE.key,
                scope_key=capture.stream_id,
                kind=EXTRACTOR_PRODUCT.kind,
                schema_version=EXTRACTOR_PRODUCT.schema_version,
                role="scientific",
                status="complete",
                media_type=EXTRACTOR_PRODUCT.media_type,
                logical_uri=published.logical_uri,
                digest=published.digest,
                byte_size=published.byte_size,
                summary={"plan_id": plan.plan_id, "plan_digest": plan.plan_digest},
            )
        )
        lease = repository.claim_job(worker_id="vertical-worker", lease_for=timedelta(seconds=30))
        assert lease is not None and lease.run_id == run_id
        repository.complete_job(
            job_id=lease.job_id,
            worker_id="vertical-worker",
            outcome="complete",
        )
        repository.seal_and_promote(
            run_id=run_id,
            manifest_uri=f"bulk://analysis/{session_id}/{run_id}/manifest.json",
            manifest_digest=DIGEST,
            summary=CurrentSummary(),
        )

    plan_root = tmp_path / "plans"
    promotion_root = tmp_path / "promotions"
    plan_root.mkdir()
    promotion_root.mkdir()
    plans = ImmutableCalibrationPlanStore(plan_root, clock_ns=lambda: 50)
    plan_ref = plans.publish(plan)
    outputs = ImmutableCalibrationPromotionStore(
        promotion_root,
        clock_ns=lambda: 2_000_000_000_000,
    )
    releases = _ReleasePort()
    resolver = AuthoritativeCalibrationResolver(
        outputs,
        releases,
        allowed_release_ids=("test-release",),
    )
    promoter = TrustedFrequencyCalibrationPromoter(
        plans=plans,
        recordings=recordings,
        artifacts=AnalysisArtifactTrustedDocumentAdapter(artifacts),
        outputs=outputs,
        releases=releases,
        extractor_executor=_CalibrationExecutionPort(recordings),
    )
    first_backend = PostgresCalibrationOperationsAdapter(repository, resolver, recordings)
    inputs = first_backend.promotion_inputs(plan)
    publication = promoter.promote(
        plan_ref=plan_ref,
        dwell_inputs=inputs,
        promotion_id="fresh-db-promotion",
        calibration_id="fresh-db-calibration",
        calibration_set_id="fresh-db-set",
    )
    with pytest.raises(CatalogNotFoundError):
        repository.frequency_calibration_set_by_promotion_id(publication.promotion_id)
    with catalog_harness.engine.connect() as connection:
        assert tuple(
            connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM receiver_path), "
                    "(SELECT count(*) FROM hardware_epoch), "
                    "(SELECT count(*) FROM frequency_calibration)"
                )
            ).one()
        ) == (0, 0, 0)
    assert all(session_id in recordings.verified for session_id in plan.scheduled_session_ids)
    first = first_backend.publish(publication)

    second_backend = PostgresCalibrationOperationsAdapter(repository, resolver, recordings)
    retry_inputs = second_backend.promotion_inputs(plan)
    retry_publication = promoter.promote(
        plan_ref=plan_ref,
        dwell_inputs=retry_inputs,
        promotion_id="fresh-db-promotion",
        calibration_id="fresh-db-calibration",
        calibration_set_id="fresh-db-set",
    )
    second = second_backend.publish(retry_publication)

    assert retry_publication == publication
    assert second == first
    assert second_backend.lookup(publication.promotion_id) == first
    assert recordings.verified.count("cal-a-1") >= 4
    calibration = first.calibration_set_id
    assert calibration == "fresh-db-set"
    expected_epoch_start = min(dwell.capture.interval_bounds()[0] for dwell in dwells)
    with catalog_harness.engine.connect() as connection:
        counts_and_start = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM receiver_path), "
                "(SELECT count(*) FROM hardware_epoch), "
                "(SELECT count(*) FROM frequency_calibration), "
                "(SELECT started_utc_ns FROM hardware_epoch)"
            )
        ).one()
    assert tuple(counts_and_start) == (1, 1, 1, expected_epoch_start)


def _published_bundle(capture):
    from leo.storage.writer import PublishedBundle

    return PublishedBundle(
        session_id=capture.manifest.session_id,
        path=Path("/nonexistent") / capture.manifest.session_id,
        uri=capture.recording_uri,
        manifest=capture.manifest,
        manifest_sha256=capture.manifest_digest,
    )
