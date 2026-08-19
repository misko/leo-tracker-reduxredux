from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from leo.catalog import (
    InvalidStateError,
    JobDefinition,
    ProductRegistration,
    RawIntegrityAttestationRegistration,
    StageDerivationOutputRegistration,
    StageDerivationRegistration,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_digest
from leo.pipeline import ScopeIdentityV1, StageDerivationKeyV1

from .conftest import CatalogHarness

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
RELEASE = "1" * 40
REVISION = "2" * 40
EXECUTABLE = "sha256:" + "e" * 64


def _authority() -> WorkerReleaseAuthority:
    return WorkerReleaseAuthority(
        pipeline_release_id=RELEASE,
        code_revision=REVISION,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration_digest=canonical_digest({}),
        executable_digest=EXECUTABLE,
    )


def _seed_typed_capture(harness: CatalogHarness, session_id: str = "typed-T1") -> None:
    harness.repository.create_capture_session(
        session_id=session_id,
        source_type="test",
        state="committed",
        bundle_uri=f"bulk://recordings/{session_id}",
        manifest_digest=DIGEST_A,
    )
    with harness.engine.begin() as connection:
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
                "(session_id, id, radio_id, state, receiver_ids, sample_rate_hz, "
                "captured_sample_count) VALUES "
                "(:session, 'stream-0', 'radio-0', 'complete', ARRAY[0,1], 2500000, 8)"
            ),
            {"session": session_id},
        )
    harness.repository.add_pipeline_release(
        release_id=RELEASE,
        code_revision=REVISION,
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        executable_digest=EXECUTABLE,
    )


def _attest(harness: CatalogHarness, session_id: str, *, suffix: str = "0") -> str:
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
        "verified_utc_ns": int(suffix) + 1,
    }
    digest = canonical_digest(document)
    harness.repository.register_raw_integrity_attestation(
        RawIntegrityAttestationRegistration(
            session_id=session_id,
            manifest_digest=DIGEST_A,
            attestation_digest=digest,
            document=document,
            verified_at=datetime(2026, 8, 19, tzinfo=UTC) + timedelta(seconds=int(suffix)),
        )
    )
    return digest


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
    )
    return path0, path1, radio


def _product(run_id: str, stage: str, scope: ScopeIdentityV1, kind: str, **kwargs: object):
    return ProductRegistration(
        run_id=run_id,
        stage_key=stage,
        scope=scope,
        kind=kind,
        schema_version=1,
        role="scientific",
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
    for lease in (first, second):
        catalog_harness.repository.complete_job(
            job_id=lease.job_id, worker_id=lease.worker_id, outcome="complete"
        )

    p0 = catalog_harness.repository.register_product(
        _product("typed-run", "path-report", path0, "path.report")
    )
    p1 = catalog_harness.repository.register_product(
        _product("typed-run", "path-report", path1, "path.report")
    )
    reducer = catalog_harness.repository.claim_job(
        worker_id="cpu",
        lease_for=timedelta(minutes=1),
        resource_classes=("cpu",),
        authority=_authority(),
    )
    assert reducer is not None and reducer.node_id == "radio" and reducer.iq_access == "none"

    with pytest.raises(InvalidStateError, match="exact required predecessor"):
        catalog_harness.repository.register_product(
            _product(
                "typed-run",
                "radio-report",
                radio,
                "radio.report",
                input_product_ids=(p0,),
            )
        )
    radio_product = catalog_harness.repository.register_product(
        _product(
            "typed-run",
            "radio-report",
            radio,
            "radio.report",
            input_product_ids=(p0, p1),
        )
    )
    assert tuple(
        item.product_id
        for item in catalog_harness.repository.product_direct_dependencies(radio_product)
    ) == (p0, p1)


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
            status="complete",
            media_type="application/json",
            logical_uri="bulk://derivations/path-report.json",
            digest=DIGEST_B,
            byte_size=10,
        )
    )
    assert output.derivation_key == key.derivation_digest
    assert catalog_harness.repository.stage_derivation_outputs(key.derivation_digest) == (output,)
