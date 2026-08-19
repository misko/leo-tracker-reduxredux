from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text

import leo.processing.service as processing_service_module
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import (
    CatalogNotFoundError,
    CatalogSubjectBindingReader,
    InvalidStateError,
    JobDefinition,
    ProductConflictError,
    ProductRegistration,
    RawIntegrityAttestationRegistration,
    RunSubjectBindingRegistration,
    StageDerivationOutputRegistration,
    StageDerivationRegistration,
    StageResultCommit,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV2
from leo.pipeline import (
    AnalyzerRegistry,
    ProductSpec,
    ScopeIdentityV1,
    StageDerivationKeyV1,
    StageOutcome,
    StageResult,
    StageSpec,
)
from leo.processing import LoadedWorkerRelease, ProcessingService, WorkerIncompatibleError

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
RELEASE = "1" * 40
REVISION = "2" * 40
EXECUTABLE = "sha256:" + "e" * 64


class _IdleIq:
    def close(self) -> None:
        return


class _LatePublishingAnalyzer:
    product = ProductSpec(kind="late.output")
    spec = StageSpec(
        key="path-report",
        algorithm_version="1",
        configuration_schema="late.v1",
        output_products=(product,),
        resource_class="heavy",
    )

    def __init__(self, completion_marker: Path | None = None) -> None:
        self._completion_marker = completion_marker

    def analyze(self, _context, _iq, _products, outputs) -> StageResult:
        published = outputs.publish_json(self.product, {"too_late": True})
        # The child is allowed to finish writing its private staging file, then
        # hangs.  The parent must still expose no artifact after terminating it.
        time.sleep(0.25)
        if self._completion_marker is not None:
            self._completion_marker.write_text("child escaped cancellation", encoding="utf-8")
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


class _FastPublishingAnalyzer(_LatePublishingAnalyzer):
    def analyze(self, _context, _iq, _products, outputs) -> StageResult:
        published = outputs.publish_json(self.product, {"complete": True})
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


class _MutatingPublishingAnalyzer(_LatePublishingAnalyzer):
    def __init__(self, marker: Path) -> None:
        self._marker = marker

    def analyze(self, _context, _iq, _products, outputs) -> StageResult:
        self._marker.write_text("runtime changed", encoding="utf-8")
        published = outputs.publish_json(self.product, {"must_not_publish": True})
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


class _IdleIqProvider:
    def open_scope(self, _execution, _scope) -> _IdleIq:
        return _IdleIq()


class _ForbiddenIqProvider:
    def __init__(self) -> None:
        self.called = False

    def open_scope(self, _execution, _scope) -> _IdleIq:
        self.called = True
        raise AssertionError("stale worker reached IQ")


def _authority() -> WorkerReleaseAuthority:
    return WorkerReleaseAuthority(
        pipeline_release_id=RELEASE,
        code_revision=REVISION,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration_digest=canonical_digest({}),
        executable_digest=EXECUTABLE,
    )


def _changed_authority() -> WorkerReleaseAuthority:
    value = _authority()
    return WorkerReleaseAuthority(
        pipeline_release_id=value.pipeline_release_id,
        code_revision=value.code_revision,
        environment_digest=value.environment_digest,
        graph_digest=value.graph_digest,
        configuration_digest=value.configuration_digest,
        executable_digest=DIGEST_B,
    )


def _seed_typed_capture(
    harness: CatalogHarness,
    session_id: str = "typed-T1",
    *,
    epoch_start_ns: int | None = 1_767_225_600_000_000_000,
    epoch_end_ns: int = 1_767_225_603_000_000_000,
) -> None:
    harness.repository.create_capture_session(
        session_id=session_id,
        source_type="test",
        state="committed",
        bundle_uri=f"bulk://recordings/{session_id}",
        manifest_digest=DIGEST_A,
    )
    with harness.engine.begin() as connection:
        profile_revision_id = connection.scalar(
            text(
                "WITH profile AS ("
                "INSERT INTO capture_profile (id, name) VALUES "
                "('typed-profile', 'Typed profile') RETURNING id"
                ") INSERT INTO capture_profile_revision "
                "(profile_id, revision_number, digest, document) "
                "SELECT id, 1, :digest, '{}'::jsonb FROM profile RETURNING id"
            ),
            {"digest": DIGEST_B},
        )
        connection.execute(
            text("UPDATE capture_session SET profile_revision_id=:revision WHERE id=:session"),
            {"revision": profile_revision_id, "session": session_id},
        )
        connection.execute(
            text(
                "INSERT INTO radio (id, serial, uri, transport) "
                "VALUES ('radio-0', :serial, 'ip:test', 'ethernet')"
            ),
            {"serial": f"serial-{session_id}"},
        )
        connection.execute(
            text(
                "INSERT INTO radio_stream "
                "(session_id, id, radio_id, manifest_ordinal, state, receiver_ids, sample_rate_hz, "
                "captured_sample_count, observed_start_at, observed_end_at, attributes) VALUES "
                "(:session, 'stream-0', 'radio-0', 0, 'complete', ARRAY[0,1], 2500000, 8, "
                "'2026-01-01 00:00:01+00', '2026-01-01 00:00:02+00', "
                "CAST(:attributes AS jsonb))"
            ),
            {
                "session": session_id,
                "attributes": (
                    '{"timing":{"first_sample":{"estimate_utc_ns":1767225601000000000},'
                    '"last_sample":{"estimate_utc_ns":1767225602000000000}}}'
                ),
            },
        )
        connection.execute(
            text(
                "INSERT INTO receiver_path "
                "(radio_id, receiver_id, physical_receiver_id) VALUES "
                "('radio-0', 0, 'physical-0'), ('radio-0', 1, 'physical-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO hardware_epoch "
                "(external_id, radio_id, started_at, ended_at, started_utc_ns, ended_utc_ns) "
                "VALUES (:epoch, 'radio-0', '2026-01-01 00:00:00+00', "
                "to_timestamp(:epoch_end_ns / 1000000000.0), :epoch_start_ns, "
                ":epoch_end_ns)"
            ),
            {
                "epoch": f"epoch-{session_id}",
                "epoch_start_ns": epoch_start_ns,
                "epoch_end_ns": epoch_end_ns,
            },
        )
        connection.execute(
            text(
                "INSERT INTO capture_receiver_lineage "
                "(session_id, stream_id, receiver_id, radio_id, radio_serial, "
                "manifest_digest, stream_identity_digest, lineage_status, "
                "physical_receiver_id, hardware_epoch_external_id, receiver_path_id, "
                "hardware_epoch_id) "
                "SELECT :session, 'stream-0', path.receiver_id, 'radio-0', :serial, "
                ":digest, :digest, 'resolved', path.physical_receiver_id, epoch.external_id, "
                "path.id, epoch.id FROM receiver_path path CROSS JOIN hardware_epoch epoch "
                "WHERE path.radio_id='radio-0' AND epoch.external_id=:epoch"
            ),
            {
                "session": session_id,
                "serial": f"serial-{session_id}",
                "digest": DIGEST_A,
                "epoch": f"epoch-{session_id}",
            },
        )
    harness.repository.add_pipeline_release(
        release_id=RELEASE,
        code_revision=REVISION,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        executable_digest=EXECUTABLE,
    )


def _attest(harness: CatalogHarness, session_id: str, *, suffix: str = "0") -> str:
    verified_at = datetime(2026, 8, 19, tzinfo=UTC) + timedelta(seconds=int(suffix))
    document = {
        "schema_version": 1,
        "session_id": session_id,
        "manifest_digest": DIGEST_A,
        "streams": [
            {
                "stream_id": "stream-0",
                "chunk_count": 1,
                "compressed_closure_digest": DIGEST_A,
                "uncompressed_closure_digest": DIGEST_B,
            }
        ],
        "verifier_version": "test-authority",
        "verified_utc_ns": int(verified_at.timestamp()) * 1_000_000_000,
    }
    digest = canonical_digest(document)
    harness.repository.register_raw_integrity_attestation(
        RawIntegrityAttestationRegistration(
            session_id=session_id,
            manifest_digest=DIGEST_A,
            attestation_digest=digest,
            document=document,
            verified_at=verified_at,
        )
    )
    return digest


def _subject_bindings(
    scopes: tuple[ScopeIdentityV1, ...], attestation_digest: str
) -> tuple[RunSubjectBindingRegistration, ...]:
    result: list[RunSubjectBindingRegistration] = []
    for scope in sorted(set(scopes), key=lambda item: item.canonical_digest):
        if scope.kind.value != "receiver_path":
            continue
        assert scope.stream_id is not None and scope.receiver_id is not None
        values: dict[str, Any] = {
            "schema_version": 2,
            "algorithm_version": "standard-path-input-bind-v2",
            "session_id": scope.session_id,
            "stream_id": scope.stream_id,
            "radio_id": "radio-0",
            "receiver_id": scope.receiver_id,
            "manifest_digest": DIGEST_A,
            "raw_integrity_attestation_digest": attestation_digest,
            "selected_stream_digest": DIGEST_A,
            "compressed_chunk_closure_digest": DIGEST_A,
            "uncompressed_chunk_closure_digest": DIGEST_B,
            "synchronization_inventory_digest": DIGEST_A,
            "profile_revision_digest": DIGEST_B,
            "capture_plan_digest": DIGEST_A,
            "receiver_settings_digest": DIGEST_B,
            "science_configuration_digest": canonical_digest({}),
            "science_implementation_digest": EXECUTABLE,
            "capture_lineage_resolution": "resolved",
            "physical_receiver_id": f"physical-{scope.receiver_id}",
            "hardware_epoch_id": f"epoch-{scope.session_id}",
            "tuned_center_frequency_hz": 1_709_687_500,
            "sample_rate_hz": 2_500_000,
            "declared_sample_count": 8,
            "timing": {
                "schema_version": 1,
                "first_estimate_utc_ns": 1_767_225_601_000_000_000,
                "first_earliest_utc_ns": 1_767_225_601_000_000_000,
                "first_latest_utc_ns": 1_767_225_601_000_000_000,
                "last_estimate_utc_ns": 1_767_225_602_000_000_000,
                "last_earliest_utc_ns": 1_767_225_602_000_000_000,
                "last_latest_utc_ns": 1_767_225_602_000_000_000,
            },
            "frequency_reference": {
                "schema_version": 1,
                "reference": "uncalibrated_prior",
                "center_frequency_hz": None,
                "uncertainty_hz": None,
                "calibration_digest": None,
            },
        }
        binding = StandardPathInputBindV2.model_validate(
            {**values, "binding_digest": canonical_digest(values)}
        )
        result.append(
            RunSubjectBindingRegistration(
                scope=scope,
                document=binding.model_dump(mode="json"),
            )
        )
    return tuple(result)


def _create_three_node_run(harness: CatalogHarness, run_id: str = "typed-run") -> tuple:
    path0 = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    path1 = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=1
    )
    radio = ScopeIdentityV1.radio(session_id="typed-T1", stream_id="stream-0", radio_id="radio-0")
    attestation = _attest(harness, "typed-T1")
    harness.repository.create_analysis_run(
        run_id=run_id,
        session_id="typed-T1",
        pipeline_release_id=RELEASE,
        input_manifest_digest=DIGEST_A,
        jobs=(
            JobDefinition(
                node_id="rx0",
                stage_key="path-report",
                scope=path0,
                resource_class="heavy",
                iq_access="receiver_path",
            ),
            JobDefinition(
                node_id="rx1",
                stage_key="path-report",
                scope=path1,
                resource_class="heavy",
                iq_access="receiver_path",
            ),
            JobDefinition(
                node_id="radio",
                stage_key="radio-report",
                scope=radio,
                depends_on_node_ids=("rx0", "rx1"),
                resource_class="cpu",
                iq_access="none",
            ),
        ),
        expanded_plan_digest=DIGEST_B,
        raw_integrity_attestation_digest=attestation,
        require_integrity_prerequisite=True,
        subject_bindings=_subject_bindings((path0, path1), attestation),
    )
    return path0, path1, radio


def test_raw_integrity_registration_redigests_document_and_rejects_forgery(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    verified_at = datetime(2026, 8, 19, tzinfo=UTC)
    document = {
        "schema_version": 1,
        "session_id": "typed-T1",
        "manifest_digest": DIGEST_A,
        "streams": [
            {
                "stream_id": "stream-0",
                "chunk_count": 1,
                "compressed_closure_digest": DIGEST_A,
                "uncompressed_closure_digest": DIGEST_B,
            }
        ],
        "verifier_version": "test-authority",
        "verified_utc_ns": int(verified_at.timestamp()) * 1_000_000_000,
    }
    forged = {**document, "verifier_version": "forged"}
    with pytest.raises(ValueError, match="columns disagree"):
        catalog_harness.repository.register_raw_integrity_attestation(
            RawIntegrityAttestationRegistration(
                session_id="typed-T1",
                manifest_digest=DIGEST_A,
                attestation_digest=canonical_digest(document),
                document=forged,
                verified_at=verified_at,
            )
        )


def test_typed_receiver_path_requires_resolved_path_and_hardware_epoch_lineage(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    catalog_harness.repository.create_capture_session(
        session_id="unresolved-T1",
        source_type="test",
        state="committed",
        bundle_uri="bulk://recordings/unresolved-T1",
        manifest_digest=DIGEST_A,
    )
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO radio (id, serial, uri, transport) VALUES "
                "('radio-unresolved', 'serial-unresolved', 'ip:unresolved', 'ethernet')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO radio_stream "
                "(session_id, id, radio_id, manifest_ordinal, state, receiver_ids, "
                "sample_rate_hz, captured_sample_count) VALUES "
                "('unresolved-T1', 'stream-0', 'radio-unresolved', 0, 'complete', "
                "ARRAY[0], 2500000, 8)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO capture_receiver_lineage "
                "(session_id, stream_id, receiver_id, radio_id, radio_serial, "
                "manifest_digest, stream_identity_digest, lineage_status) VALUES "
                "('unresolved-T1', 'stream-0', 0, 'radio-unresolved', "
                "'serial-unresolved', :digest, :digest, 'unresolved')"
            ),
            {"digest": DIGEST_A},
        )
    scope = ScopeIdentityV1.receiver_path(
        session_id="unresolved-T1", stream_id="stream-0", receiver_id=0
    )
    attestation = _attest(catalog_harness, "unresolved-T1")
    with pytest.raises(InvalidStateError, match="capture-time manifest lineage"):
        catalog_harness.repository.create_analysis_run(
            run_id="unresolved-run",
            session_id="unresolved-T1",
            pipeline_release_id=RELEASE,
            input_manifest_digest=DIGEST_A,
            jobs=(
                JobDefinition(
                    node_id="path",
                    stage_key="path-quality",
                    scope=scope,
                    resource_class="streaming",
                    iq_access="receiver_path",
                ),
            ),
            expanded_plan_digest=DIGEST_B,
            raw_integrity_attestation_digest=attestation,
            require_integrity_prerequisite=True,
            subject_bindings=_subject_bindings((scope,), attestation),
        )


def test_typed_receiver_epoch_must_cover_full_exact_nanosecond_interval(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(
        catalog_harness,
        epoch_end_ns=1_767_225_601_500_000_000,
    )
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    attestation = _attest(catalog_harness, "typed-T1")
    with pytest.raises(InvalidStateError, match="physical lineage changed"):
        catalog_harness.repository.create_analysis_run(
            run_id="short-epoch-run",
            session_id="typed-T1",
            pipeline_release_id=RELEASE,
            input_manifest_digest=DIGEST_A,
            jobs=(
                JobDefinition(
                    node_id="path",
                    stage_key="path-quality",
                    scope=scope,
                    resource_class="streaming",
                    iq_access="receiver_path",
                ),
            ),
            expanded_plan_digest=DIGEST_B,
            raw_integrity_attestation_digest=attestation,
            require_integrity_prerequisite=True,
            subject_bindings=_subject_bindings((scope,), attestation),
        )


def test_capture_receiver_binding_exposes_exact_profile_path_epoch_and_interval(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=1
    )

    binding = catalog_harness.repository.capture_receiver_binding(scope)

    assert binding.scope == scope
    assert binding.radio_id == "radio-0"
    assert binding.radio_serial == "serial-typed-T1"
    assert binding.physical_receiver_id == "physical-1"
    assert binding.hardware_epoch_id == "epoch-typed-T1"
    assert binding.manifest_digest == DIGEST_A
    assert binding.profile_revision_digest == DIGEST_B
    assert (binding.capture_start_utc_ns, binding.capture_end_utc_ns) == (
        1_767_225_601_000_000_000,
        1_767_225_602_000_000_000,
    )


def test_run_subject_binding_is_run_owned_immutable_and_never_rereads_profile(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    path0, _path1, _radio = _create_three_node_run(catalog_harness)
    reader = CatalogSubjectBindingReader(catalog_harness.repository)
    original = reader.receiver_path("typed-run", path0)
    snapshot_digest = reader.snapshot_digest("typed-run", path0)
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text("UPDATE capture_profile_revision SET document=CAST(:document AS jsonb)"),
            {"document": '{"changed":true}'},
        )
    assert reader.receiver_path("typed-run", path0) == original
    assert reader.snapshot_digest("typed-run", path0) == snapshot_digest
    with pytest.raises(CatalogNotFoundError):
        reader.receiver_path("foreign-run", path0)
    for statement in (
        "UPDATE run_subject_binding SET document='{}'::jsonb",
        "DELETE FROM run_subject_binding",
    ):
        with (
            catalog_harness.engine.connect() as connection,
            connection.begin(),
            pytest.raises(Exception, match="immutable"),
        ):
            connection.execute(text(statement))


def test_exact_stream_timing_rejects_epoch_without_exact_nanosecond_authority(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness, epoch_start_ns=None)
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    attestation = _attest(catalog_harness, "typed-T1")
    with pytest.raises(InvalidStateError, match="physical lineage changed"):
        catalog_harness.repository.create_analysis_run(
            run_id="missing-exact-epoch-run",
            session_id="typed-T1",
            pipeline_release_id=RELEASE,
            input_manifest_digest=DIGEST_A,
            jobs=(
                JobDefinition(
                    node_id="path",
                    stage_key="path-quality",
                    scope=scope,
                    resource_class="streaming",
                    iq_access="receiver_path",
                ),
            ),
            expanded_plan_digest=DIGEST_B,
            raw_integrity_attestation_digest=attestation,
            require_integrity_prerequisite=True,
            subject_bindings=_subject_bindings((scope,), attestation),
        )


def test_post_claim_incompatibility_deferral_is_attempt_neutral_and_atomic(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    lease = catalog_harness.repository.claim_job(
        worker_id="stale-worker",
        lease_for=timedelta(minutes=1),
        authority=_authority(),
        resource_classes=("heavy",),
    )
    assert lease is not None

    catalog_harness.repository.defer_incompatible_job(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        authority=_authority(),
    )

    with catalog_harness.engine.connect() as connection:
        job = connection.execute(
            text("SELECT state, attempt_count, lease_owner FROM processing_job WHERE id = :id"),
            {"id": lease.job_id},
        ).one()
        attempts = connection.scalar(
            text("SELECT count(*) FROM processing_job_attempt WHERE job_id = :id"),
            {"id": lease.job_id},
        )
        run_state = connection.scalar(text("SELECT state FROM analysis_run WHERE id = 'typed-run'"))
        events = connection.scalar(text("SELECT count(*) FROM worker_incompatibility_event"))
    assert job == ("pending", 0, None)
    assert attempts == 0
    assert run_state == "pending"
    assert events == 1


def test_service_post_claim_release_change_uses_incompatible_deferral(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    current = [_authority()]
    loaded = LoadedWorkerRelease(
        authority=_authority(),
        registry_document={},
        environment_document={},
        executable_inventory=(("worker", EXECUTABLE),),
        _revalidator=lambda: current[0],
    )

    def change_release(point: str) -> None:
        if point == "execution:after_claim":
            current[0] = _changed_authority()

    iq_readers = _ForbiddenIqProvider()

    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=cast(Any, object()),
        registry=AnalyzerRegistry(),
        iq_readers=iq_readers,  # type: ignore[arg-type]
        loaded_worker_release=loaded,
        worker_resource_classes=("heavy",),
        failure_injector=change_release,
    )
    execution = service.run_once(worker_id="post-claim-stale")
    assert execution is not None and not execution.succeeded
    assert WorkerIncompatibleError.__name__ in (execution.error or "")
    assert iq_readers.called is False
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text("SELECT state, attempt_count FROM processing_job WHERE id=:job_id"),
            {"job_id": execution.job_id},
        ).one() == ("pending", 0)


def test_service_live_release_change_before_claim_consumes_no_attempt(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    loaded = LoadedWorkerRelease(
        authority=_authority(),
        registry_document={},
        environment_document={},
        executable_inventory=(("worker", EXECUTABLE),),
        _revalidator=_changed_authority,
    )
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=cast(Any, object()),
        registry=AnalyzerRegistry(),
        iq_readers=cast(Any, object()),
        loaded_worker_release=loaded,
        worker_resource_classes=("heavy",),
    )

    with pytest.raises(WorkerIncompatibleError, match="changed after composition"):
        service.run_once(worker_id="pre-claim-stale")
    with catalog_harness.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM processing_job_attempt")) == 0


def test_migrated_zero_digest_release_cannot_back_typed_run(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    quarantined_release = "4" * 40
    zero = "sha256:" + "0" * 64
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO pipeline_release "
                "(id, code_revision, environment_digest, graph_digest, configuration_digest, "
                "executable_digest, authority_version, configuration) VALUES "
                "(:release, :release, :zero, :zero, :zero, :zero, 0, '{}'::jsonb)"
            ),
            {"release": quarantined_release, "zero": zero},
        )
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    attestation = _attest(catalog_harness, "typed-T1")
    with pytest.raises(InvalidStateError, match="freshly registered exact release"):
        catalog_harness.repository.create_analysis_run(
            run_id="quarantined-typed-run",
            session_id="typed-T1",
            pipeline_release_id=quarantined_release,
            input_manifest_digest=DIGEST_A,
            jobs=(
                JobDefinition(
                    node_id="path",
                    stage_key="path-report",
                    scope=scope,
                    resource_class="heavy",
                    iq_access="receiver_path",
                ),
            ),
            expanded_plan_digest=DIGEST_B,
            raw_integrity_attestation_digest=attestation,
            require_integrity_prerequisite=True,
            subject_bindings=_subject_bindings((scope,), attestation),
        )
    with (
        catalog_harness.engine.connect() as connection,
        connection.begin(),
        pytest.raises(Exception, match="authoritative Standard identity is immutable"),
    ):
        connection.execute(
            text("UPDATE pipeline_release SET authority_version=1 WHERE id=:release"),
            {"release": quarantined_release},
        )


def test_heavy_resource_capacity_is_enforced_atomically(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    attestation = _attest(catalog_harness, "typed-T1")
    scopes = (
        ScopeIdentityV1.receiver_path(session_id="typed-T1", stream_id="stream-0", receiver_id=0),
        ScopeIdentityV1.receiver_path(session_id="typed-T1", stream_id="stream-0", receiver_id=1),
    )
    catalog_harness.repository.create_analysis_run(
        run_id="heavy-capacity-run",
        session_id="typed-T1",
        pipeline_release_id=RELEASE,
        input_manifest_digest=DIGEST_A,
        jobs=tuple(
            JobDefinition(
                node_id=f"heavy-{index}",
                stage_key=f"heavy-stage-{index}",
                scope=scopes[index % 2],
                resource_class="heavy",
                iq_access="receiver_path",
            )
            for index in range(8)
        ),
        expanded_plan_digest=DIGEST_B,
        raw_integrity_attestation_digest=attestation,
        require_integrity_prerequisite=True,
        subject_bindings=_subject_bindings(scopes, attestation),
    )

    def claim(index: int):
        return catalog_harness.repository.claim_job(
            worker_id=f"heavy-{index}",
            lease_for=timedelta(minutes=1),
            authority=_authority(),
            resource_classes=("heavy",),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        leases = tuple(executor.map(claim, range(8)))
    claimed = tuple(item for item in leases if item is not None)
    assert len(claimed) == 4
    assert len({item.job_id for item in claimed}) == 4
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE processing_job SET lease_expires_at=now() - interval '1 second' "
                "WHERE id=:job_id"
            ),
            {"job_id": claimed[0].job_id},
        )
    replacement = claim(9)
    assert replacement is not None and replacement.job_id not in {item.job_id for item in claimed}


def test_heavy_analyzer_timeout_kills_process_before_output_and_releases_lease(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    artifacts = AnalysisArtifactStore(tmp_path / "bulk")
    completion_marker = tmp_path / "timed-out-child-completed"
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=artifacts,
        registry=AnalyzerRegistry((_LatePublishingAnalyzer(completion_marker),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        worker_authority=_authority(),
        worker_resource_classes=("heavy",),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=20),
    )
    service._wall_time_limits_seconds = {"heavy": 0.05}  # noqa: SLF001

    execution = service.run_once(worker_id="timeout-worker")

    assert execution is not None and not execution.succeeded
    assert "enforceable wall-time boundary" in (execution.error or "")
    assert not tuple((tmp_path / "bulk").glob("**/late.output.v1.json"))
    time.sleep(0.3)
    assert not completion_marker.exists()
    with catalog_harness.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM processing_job WHERE state='leased'")) == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM analysis_product")) == 0


def test_successful_heavy_analyzer_returns_child_receipt_for_atomic_registration(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=AnalysisArtifactStore(tmp_path / "bulk"),
        registry=AnalyzerRegistry((_FastPublishingAnalyzer(),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        worker_authority=_authority(),
        worker_resource_classes=("heavy",),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=20),
    )

    execution = service.run_once(worker_id="isolated-success")

    assert execution is not None and execution.succeeded
    with catalog_harness.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM analysis_product")) == 1


def test_isolated_staging_ignores_tmpdir_and_survives_directory_name_swap(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    retained: list[Path] = []
    original_names: list[Path] = []
    staging_directories: list[Any] = []
    original_staging_type = processing_service_module._LocalStagingDirectory

    class TrackingStagingDirectory(original_staging_type):
        def __enter__(self):
            directory = super().__enter__()
            staging_directories.append(directory)
            return directory

    original_open = processing_service_module.os.open
    qnap_probes: list[str] = []

    def guarded_open(path, flags, *args, **kwargs):
        if str(path).startswith("/mnt/qnap01"):
            qnap_probes.append(str(path))
            raise AssertionError("isolated staging probed QNAP")
        return original_open(path, flags, *args, **kwargs)

    def swap_after_analysis(point: str) -> None:
        if point != "execution:after_analyze":
            return
        original = staging_directories[0].root
        moved = tmp_path / "retained-staging"
        original.rename(moved)
        original.symlink_to("/mnt/qnap01/never-probe", target_is_directory=True)
        original_names.append(original)
        retained.append(moved)

    monkeypatch.setenv("TMPDIR", "/mnt/qnap01/forbidden-tmp")
    monkeypatch.setattr(processing_service_module.tempfile, "tempdir", None)
    monkeypatch.setattr(
        processing_service_module,
        "_LocalStagingDirectory",
        TrackingStagingDirectory,
    )
    monkeypatch.setattr(processing_service_module.os, "open", guarded_open)
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=AnalysisArtifactStore(tmp_path / "bulk"),
        registry=AnalyzerRegistry((_FastPublishingAnalyzer(),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        worker_authority=_authority(),
        worker_resource_classes=("heavy",),
        failure_injector=swap_after_analysis,
    )

    try:
        execution = service.run_once(worker_id="local-staging-swap")
        assert execution is not None and execution.succeeded
        assert qnap_probes == []
        assert tuple((tmp_path / "bulk").glob("**/late.output.v1.json"))
    finally:
        for path in original_names:
            if path.is_symlink():
                path.unlink()
        for path in retained:
            if path.exists():
                path.rmdir()


def test_live_release_mutation_inside_heavy_stage_blocks_output_attempt_neutrally(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    marker = tmp_path / "release-mutated"
    loaded = LoadedWorkerRelease(
        authority=_authority(),
        registry_document={},
        environment_document={},
        executable_inventory=(("worker", EXECUTABLE),),
        _revalidator=lambda: _changed_authority() if marker.exists() else _authority(),
    )
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=AnalysisArtifactStore(tmp_path / "bulk"),
        registry=AnalyzerRegistry((_MutatingPublishingAnalyzer(marker),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        loaded_worker_release=loaded,
        worker_resource_classes=("heavy",),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=20),
    )

    execution = service.run_once(worker_id="mutating-worker")

    assert execution is not None and not execution.succeeded
    assert WorkerIncompatibleError.__name__ in (execution.error or "")
    assert not tuple((tmp_path / "bulk").glob("**/late.output.v1.json"))
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text("SELECT state, attempt_count FROM processing_job WHERE id=:job_id"),
            {"job_id": execution.job_id},
        ).one() == ("pending", 0)
        assert connection.scalar(text("SELECT count(*) FROM analysis_product")) == 0


def test_live_release_change_after_analysis_blocks_staged_output_materialization(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    current = [_authority()]
    loaded = LoadedWorkerRelease(
        authority=_authority(),
        registry_document={},
        environment_document={},
        executable_inventory=(("worker", EXECUTABLE),),
        _revalidator=lambda: current[0],
    )

    def change_after_analysis(point: str) -> None:
        if point == "execution:after_analyze":
            current[0] = _changed_authority()

    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=AnalysisArtifactStore(tmp_path / "bulk"),
        registry=AnalyzerRegistry((_FastPublishingAnalyzer(),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        loaded_worker_release=loaded,
        worker_resource_classes=("heavy",),
        failure_injector=change_after_analysis,
    )

    execution = service.run_once(worker_id="post-analysis-stale")

    assert execution is not None and not execution.succeeded
    assert WorkerIncompatibleError.__name__ in (execution.error or "")
    assert not tuple((tmp_path / "bulk").glob("**/late.output.v1.json"))
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text("SELECT state, attempt_count FROM processing_job WHERE id=:job_id"),
            {"job_id": execution.job_id},
        ).one() == ("pending", 0)
        assert connection.scalar(text("SELECT count(*) FROM analysis_product")) == 0


@pytest.mark.parametrize(
    "injection_point",
    (
        "execution:after_iq_reader_open",
        "execution:before_product_register",
        "execution:before_job_complete",
    ),
)
def test_release_change_at_atomic_boundaries_leaves_no_catalog_result(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
    injection_point: str,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    current = [_authority()]
    loaded = LoadedWorkerRelease(
        authority=_authority(),
        registry_document={},
        environment_document={},
        executable_inventory=(("worker", EXECUTABLE),),
        _revalidator=lambda: current[0],
    )

    def mutate(point: str) -> None:
        if point == injection_point:
            current[0] = _changed_authority()

    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=AnalysisArtifactStore(tmp_path / "bulk"),
        registry=AnalyzerRegistry((_FastPublishingAnalyzer(),)),
        iq_readers=_IdleIqProvider(),  # type: ignore[arg-type]
        loaded_worker_release=loaded,
        worker_resource_classes=("heavy",),
        failure_injector=mutate,
    )
    execution = service.run_once(worker_id=f"boundary-{injection_point}")
    assert execution is not None and not execution.succeeded
    assert WorkerIncompatibleError.__name__ in (execution.error or "")
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text("SELECT state, attempt_count FROM processing_job WHERE id=:id"),
            {"id": execution.job_id},
        ).one() == ("pending", 0)
        assert connection.scalar(text("SELECT count(*) FROM analysis_product")) == 0


def _product(
    run_id: str,
    stage: str,
    scope: ScopeIdentityV1,
    kind: str,
    *,
    role: str = "scientific",
    **kwargs: object,
):
    return ProductRegistration(
        run_id=run_id,
        stage_key=stage,
        scope=scope,
        kind=kind,
        schema_version=1,
        role=role,
        status="complete",
        media_type="application/json",
        logical_uri=f"bulk://analysis/{run_id}/{scope.canonical_digest}/{kind}.json",
        digest=DIGEST_A,
        byte_size=10,
        **kwargs,
    )


def test_typed_cross_scope_dependencies_require_exact_consumed_predecessors(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    path0, path1, radio = _create_three_node_run(catalog_harness)

    first = catalog_harness.repository.claim_job(
        worker_id="heavy-0",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    second = catalog_harness.repository.claim_job(
        worker_id="heavy-1",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    assert first is not None and second is not None
    assert {first.node_id, second.node_id} == {"rx0", "rx1"}
    assert first.resource_class == second.resource_class == "heavy"
    assert first.scope is not None and second.scope is not None
    product_ids: dict[int, int] = {}
    for lease in (first, second):
        assert lease.scope is not None and lease.scope.receiver_id is not None
        registration = _product("typed-run", "path-report", lease.scope, "path.report")
        product_ids[lease.scope.receiver_id] = catalog_harness.repository.commit_stage_result(
            StageResultCommit(
                job_id=lease.job_id,
                worker_id=lease.worker_id,
                attempt_number=lease.attempt_number,
                authority=_authority(),
                outcome="complete",
                declared_products=(("path.report", 1),),
                products=(registration,),
            )
        )[0]

    p0 = product_ids[0]
    p1 = product_ids[1]

    reducer = catalog_harness.repository.claim_job(
        worker_id="cpu",
        lease_for=timedelta(minutes=1),
        resource_classes=("cpu",),
        authority=_authority(),
    )
    assert reducer is not None and reducer.node_id == "radio" and reducer.iq_access == "none"
    assert reducer.dependency_node_ids == ("rx0", "rx1")

    with pytest.raises(InvalidStateError, match="exact predecessor-job inventory"):
        catalog_harness.repository.commit_stage_result(
            StageResultCommit(
                job_id=reducer.job_id,
                worker_id=reducer.worker_id,
                attempt_number=reducer.attempt_number,
                authority=_authority(),
                outcome="complete",
                declared_products=(("radio.report", 1),),
                products=(
                    _product(
                        "typed-run",
                        "radio-report",
                        radio,
                        "radio.report",
                        input_product_ids=(p0,),
                    ),
                ),
                consumed_product_ids=(p0,),
            )
        )
    radio_product = catalog_harness.repository.commit_stage_result(
        StageResultCommit(
            job_id=reducer.job_id,
            worker_id=reducer.worker_id,
            attempt_number=reducer.attempt_number,
            authority=_authority(),
            outcome="complete",
            declared_products=(("radio.report", 1),),
            products=(
                _product(
                    "typed-run",
                    "radio-report",
                    radio,
                    "radio.report",
                    input_product_ids=(p0, p1),
                ),
            ),
            consumed_product_ids=(p0, p1),
        )
    )[0]
    assert tuple(
        item.product_id
        for item in catalog_harness.repository.product_direct_dependencies(radio_product)
    ) == (p0, p1)


def test_atomic_multi_output_rolls_back_replays_and_rejects_lost_lease(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    path0, _path1, _radio = _create_three_node_run(catalog_harness)
    lease = catalog_harness.repository.claim_job(
        worker_id="atomic-worker",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    assert lease is not None and lease.scope == path0
    products = (
        _product("typed-run", "path-report", path0, "atomic.a"),
        _product("typed-run", "path-report", path0, "atomic.b"),
    )
    base = StageResultCommit(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        attempt_number=lease.attempt_number,
        authority=_authority(),
        outcome="complete",
        declared_products=(("atomic.a", 1), ("atomic.b", 1)),
        products=products,
    )
    with pytest.raises(Exception, match="nonnegative_byte_size"):
        catalog_harness.repository.commit_stage_result(
            replace(base, products=(products[0], replace(products[1], byte_size=-1)))
        )
    with catalog_harness.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM analysis_product WHERE run_id='typed-run'")
            )
            == 0
        )
    committed = catalog_harness.repository.commit_stage_result(base)
    assert catalog_harness.repository.commit_stage_result(base) == committed

    # A different root lease is expired before commit; neither membership nor
    # completion may survive the lost lease.
    other = catalog_harness.repository.claim_job(
        worker_id="expired-worker",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    assert other is not None and other.scope is not None
    expired_product = _product("typed-run", "path-report", other.scope, "expired.out")
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE processing_job SET lease_expires_at=now()-interval '1 second' WHERE id=:id"
            ),
            {"id": other.job_id},
        )
    with pytest.raises(Exception, match="no longer owns live job lease"):
        catalog_harness.repository.commit_stage_result(
            StageResultCommit(
                job_id=other.job_id,
                worker_id=other.worker_id,
                attempt_number=other.attempt_number,
                authority=_authority(),
                outcome="complete",
                declared_products=(("expired.out", 1),),
                products=(expired_product,),
            )
        )
    with catalog_harness.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM analysis_product WHERE kind='expired.out'")
            )
            == 0
        )


def test_incompatible_worker_and_resource_filter_consume_no_attempt(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    wrong = WorkerReleaseAuthority(
        pipeline_release_id="3" * 40,
        code_revision="4" * 40,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration_digest=canonical_digest({}),
        executable_digest=EXECUTABLE,
    )

    assert (
        catalog_harness.repository.claim_job(
            worker_id="no-authority",
            lease_for=timedelta(minutes=1),
            resource_classes=("heavy",),
        )
        is None
    )
    assert (
        catalog_harness.repository.claim_job(
            worker_id="stale",
            lease_for=timedelta(minutes=1),
            authority=wrong,
            resource_classes=("heavy",),
        )
        is None
    )
    assert (
        catalog_harness.repository.claim_job(
            worker_id="wrong-resource",
            lease_for=timedelta(minutes=1),
            resource_classes=("memory",),
            authority=_authority(),
        )
        is None
    )
    with catalog_harness.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM processing_job_attempt")).scalar_one()
            == 0
        )
        assert set(
            connection.execute(text("SELECT attempt_count FROM processing_job")).scalars()
        ) == {0}


def test_derivation_registration_is_replayable_and_concurrent(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    key = StageDerivationKeyV1(
        stage_key="path-report",
        algorithm_version="1",
        implementation_digest=DIGEST_A,
        output_schema_identity="path-report.v1",
        configuration_digest=DIGEST_A,
        scope=scope,
        input_closure_digest=DIGEST_B,
        environment_digest=DIGEST_A,
    )
    registration = StageDerivationRegistration(
        derivation_key=key.derivation_digest,
        stage_key=key.stage_key,
        algorithm_version=key.algorithm_version,
        implementation_digest=key.implementation_digest,
        configuration_digest=key.configuration_digest,
        environment_digest=key.environment_digest,
        scope_digest=key.scope.canonical_digest,
        input_closure_digest=key.input_closure_digest,
        producing_release_id=RELEASE,
        key_document=key.model_dump(mode="json"),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        derivation_ids = tuple(
            executor.map(
                lambda _: catalog_harness.repository.register_stage_derivation(registration),
                range(8),
            )
        )
    assert len(set(derivation_ids)) == 1
    output = catalog_harness.repository.register_stage_derivation_output(
        StageDerivationOutputRegistration(
            derivation_id=derivation_ids[0],
            kind="path.report",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri="bulk://derivations/path-report.json",
            digest=DIGEST_B,
            byte_size=10,
        )
    )
    assert output.derivation_key == key.derivation_digest
    assert catalog_harness.repository.stage_derivation_outputs(key.derivation_digest) == (output,)


@pytest.mark.parametrize("mismatch", ["stage", "scope", "configuration", "role"])
def test_derivation_membership_rejects_lineage_substitution(
    catalog_harness: CatalogHarness, mismatch: str
) -> None:
    _seed_typed_capture(catalog_harness)
    path0, path1, _radio = _create_three_node_run(catalog_harness)
    key = StageDerivationKeyV1(
        stage_key="other-stage" if mismatch == "stage" else "path-report",
        algorithm_version="1",
        implementation_digest=DIGEST_A,
        output_schema_identity="path-report.v1",
        configuration_digest=(DIGEST_B if mismatch == "configuration" else canonical_digest({})),
        scope=path1 if mismatch == "scope" else path0,
        input_closure_digest=DIGEST_B,
        environment_digest=DIGEST_A,
    )
    derivation_id = catalog_harness.repository.register_stage_derivation(
        StageDerivationRegistration(
            derivation_key=key.derivation_digest,
            stage_key=key.stage_key,
            algorithm_version=key.algorithm_version,
            implementation_digest=key.implementation_digest,
            configuration_digest=key.configuration_digest,
            environment_digest=key.environment_digest,
            scope_digest=key.scope.canonical_digest,
            input_closure_digest=key.input_closure_digest,
            producing_release_id=RELEASE,
            key_document=key.model_dump(mode="json"),
        )
    )
    output = catalog_harness.repository.register_stage_derivation_output(
        StageDerivationOutputRegistration(
            derivation_id=derivation_id,
            kind="path.report",
            schema_version=1,
            role="scientific",
            status="complete",
            media_type="application/json",
            logical_uri=(f"bulk://analysis/typed-run/{path0.canonical_digest}/path.report.json"),
            digest=DIGEST_A,
            byte_size=10,
        )
    )
    registration = _product(
        "typed-run",
        "path-report",
        path0,
        "path.report",
        role="diagnostic" if mismatch == "role" else "scientific",
        derivation_output_id=output.output_id,
        derivation_mode="computed",
    )
    expected = ProductConflictError if mismatch == "role" else InvalidStateError
    lease = catalog_harness.repository.claim_job(
        worker_id="derivation-worker",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    assert lease is not None and lease.scope == path0
    with pytest.raises(expected):
        catalog_harness.repository.commit_stage_result(
            StageResultCommit(
                job_id=lease.job_id,
                worker_id=lease.worker_id,
                attempt_number=lease.attempt_number,
                authority=_authority(),
                outcome="complete",
                declared_products=(("path.report", 1),),
                products=(registration,),
            )
        )


def test_capture_lineage_authorities_reject_physical_chain_and_epoch_retarget(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    with (
        catalog_harness.engine.begin() as connection,
        pytest.raises(Exception, match="receiver path is immutable"),
    ):
        connection.execute(
            text(
                "UPDATE receiver_path SET physical_receiver_id='retargeted' "
                "WHERE radio_id='radio-0' AND receiver_id=0"
            )
        )
    epoch_external_id = "epoch-typed-T1"
    with (
        catalog_harness.engine.begin() as connection,
        pytest.raises(Exception, match="hardware epoch is immutable"),
    ):
        connection.execute(
            text(
                "UPDATE hardware_epoch SET external_id='epoch-retargeted' "
                "WHERE external_id=:external_id"
            ),
            {"external_id": epoch_external_id},
        )


def test_typed_lineage_and_derivation_output_identity_are_sql_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    _seed_typed_capture(catalog_harness)
    _create_three_node_run(catalog_harness)
    scope = ScopeIdentityV1.receiver_path(
        session_id="typed-T1", stream_id="stream-0", receiver_id=0
    )
    key = StageDerivationKeyV1(
        stage_key="path-report",
        algorithm_version="1",
        implementation_digest=DIGEST_A,
        output_schema_identity="path-report.v1",
        configuration_digest=canonical_digest({}),
        scope=scope,
        input_closure_digest=DIGEST_B,
        environment_digest=DIGEST_A,
    )
    derivation_registration = StageDerivationRegistration(
        derivation_key=key.derivation_digest,
        stage_key=key.stage_key,
        algorithm_version=key.algorithm_version,
        implementation_digest=key.implementation_digest,
        configuration_digest=key.configuration_digest,
        environment_digest=key.environment_digest,
        scope_digest=key.scope.canonical_digest,
        input_closure_digest=key.input_closure_digest,
        producing_release_id=RELEASE,
        key_document=key.model_dump(mode="json"),
    )
    derivation_id = catalog_harness.repository.register_stage_derivation(derivation_registration)
    output_registration = StageDerivationOutputRegistration(
        derivation_id=derivation_id,
        kind="path.report",
        schema_version=1,
        role="scientific",
        status="complete",
        media_type="application/json",
        logical_uri=f"bulk://analysis/typed-run/{scope.canonical_digest}/path.report.json",
        digest=DIGEST_A,
        byte_size=10,
    )
    output = catalog_harness.repository.register_stage_derivation_output(output_registration)
    product_registration = _product(
        "typed-run",
        "path-report",
        scope,
        "path.report",
        derivation_output_id=output.output_id,
        derivation_mode="computed",
    )
    lease = catalog_harness.repository.claim_job(
        worker_id="immutability-worker",
        lease_for=timedelta(minutes=1),
        resource_classes=("heavy",),
        authority=_authority(),
    )
    assert lease is not None and lease.scope == scope
    commit = StageResultCommit(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        attempt_number=lease.attempt_number,
        authority=_authority(),
        outcome="complete",
        declared_products=(("path.report", 1),),
        products=(product_registration,),
    )
    product_id = catalog_harness.repository.commit_stage_result(commit)[0]
    assert catalog_harness.repository.register_stage_derivation(derivation_registration) == (
        derivation_id
    )
    assert catalog_harness.repository.register_stage_derivation_output(output_registration) == (
        output
    )
    assert catalog_harness.repository.commit_stage_result(commit) == (product_id,)
    with catalog_harness.engine.begin() as connection:
        legacy_product_id = connection.scalar(
            text(
                "INSERT INTO analysis_product (run_id, stage_key, scope_key, scope_id, kind, "
                "schema_version, role, status, media_type, logical_uri, digest, byte_size, "
                "lineage_sealed) SELECT 'typed-run', 'path-report', CAST(:scope AS varchar), id, "
                "'legacy.path-report', 1, 'scientific', 'complete', 'application/json', "
                "'bulk://legacy', :digest, 10, true FROM analysis_scope "
                "WHERE canonical_digest=CAST(:scope AS varchar) RETURNING id"
            ),
            {"scope": scope.canonical_digest, "digest": DIGEST_A},
        )
    with (
        catalog_harness.engine.begin() as connection,
        pytest.raises(Exception, match="immutable"),
    ):
        connection.execute(text("DELETE FROM capture_receiver_lineage WHERE session_id='typed-T1'"))
    with (
        catalog_harness.engine.begin() as connection,
        pytest.raises(Exception, match="immutable"),
    ):
        connection.execute(
            text("UPDATE stage_derivation_output SET role='diagnostic' WHERE id=:id"),
            {"id": output.output_id},
        )
    with (
        catalog_harness.engine.begin() as connection,
        pytest.raises(Exception, match="immutable"),
    ):
        connection.execute(
            text("DELETE FROM stage_derivation_output WHERE id=:id"),
            {"id": output.output_id},
        )
    for statement, parameters in (
        ("UPDATE stage_derivation SET algorithm_version='2' WHERE id=:id", {"id": derivation_id}),
        ("DELETE FROM stage_derivation WHERE id=:id", {"id": derivation_id}),
        (
            "UPDATE analysis_product SET scope_key='retargeted' WHERE id=:id",
            {"id": product_id},
        ),
        (
            "UPDATE analysis_product SET derivation_output_id=:output, "
            "derivation_mode='computed' WHERE id=:id",
            {"id": legacy_product_id, "output": output.output_id},
        ),
        ("DELETE FROM analysis_product WHERE id=:id", {"id": product_id}),
        (
            "UPDATE pipeline_release SET code_revision=:revision WHERE id=:release",
            {"revision": "3" * 40, "release": RELEASE},
        ),
        ("DELETE FROM pipeline_release WHERE id=:release", {"release": RELEASE}),
    ):
        with (
            catalog_harness.engine.begin() as connection,
            pytest.raises(Exception, match="immutable"),
        ):
            connection.execute(text(statement), parameters)
