"""Bounded 40-stream producer/catalog/artifact/outer-seal orchestration integration.

The release executor and raw-recording replay are deterministic test boundaries here so CI does
not materialize 24 GB of IQ. Production composition still requires the concrete release-local
executor; its raw-IQ replay is covered by focused authority tests. This module cannot evidence
production acceptance: it exercises cardinality, persistence, and orchestration only.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from types import MethodType, SimpleNamespace

import pytest
from sqlalchemy import text

from leo.analysis.starlink.acceptance import (
    NativeEvidenceExecutionResult,
    NativeEvidenceScopeBinding,
    NativeKnownPilotEvidenceAnalyzer,
)
from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.frequency_calibration import (
    ImmutableDocumentRefV1,
    NativeReleaseCalibrationEvidenceAdapter,
)
from leo.application.trusted_campaign import (
    ConfinedLegacyExecutionAuthority,
    ImmutableCaptureCampaignAuthority,
    TrustedCampaignDependencySealV1,
    TrustedCampaignFinalizer,
    TrustedCampaignMemberInput,
    TrustedCampaignMemberSealV1,
    _ResolvedMember,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import RadioStreamRegistration, ScientificCampaignStreamRegistration
from leo.contracts.scientific import NativeKnownPilotEvidenceProductV2
from leo.contracts.trusted_scientific import TrustedMatchedRecoveryProductV2
from leo.pipeline import AnalyzerRegistry
from leo.processing import ProcessingService
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.trusted_campaign_store import ImmutableTrustedCampaignStore
from leo.qualification.trusted_matched_recovery_stage import (
    TrustedMatchedRecoveryAnalyzer,
    TrustedMatchedRecoveryBinding,
)
from leo.storage import PinnedLocalRoot, RecordingStore
from tests.processing.conftest import (
    ProcessingDatabase,
)
from tests.processing.conftest import (
    processing_database as _processing_database_fixture,
)
from tests.processing.test_processing_service import _execute_until_idle

_STORE = run_path(str(Path(__file__).with_name("test_trusted_campaign_store.py")))


@pytest.fixture
def trusted_processing_database():
    yield from _processing_database_fixture.__wrapped__()


class _Iq:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_521_250
    sample_count = 150_000_000
    receiver_ids = (1,)

    def iter_blocks(self, *, block_samples):
        del block_samples
        return ()


class _IqProvider:
    def open(self, _execution, _scope_key):
        return _Iq()


class _Scopes:
    def __init__(self, products):
        self.products = products

    def resolve(self, context, _iq):
        product = self.products[(context.session_id, context.scope_key)]
        return NativeEvidenceScopeBinding(
            input_manifest_digest=product.receipt.path_identity.manifest_digest,
            path_identity=product.receipt.path_identity,
            calibration=product.receipt.calibration,
        )


class _Releases:
    def __init__(self, products):
        self.products = products

    def resolve(self, context):
        return self.products[(context.session_id, context.scope_key)].receipt.native_release


class _ExecutorBoundary:
    def __init__(self, products):
        self.products = products

    def execute(self, *, path_identity, **_kwargs):
        execution = self.products[
            (path_identity.session_id, path_identity.stream_id)
        ].receipt.native_execution
        return NativeEvidenceExecutionResult(
            decisions=execution.decisions,
            execution_environment_digest=execution.execution_environment_digest,
            worker_output_digest=execution.worker_output_digest,
        )


class _Bindings:
    def __init__(self, products):
        self.products = products

    def resolve(self, context, _iq, _native):
        receipt = self.products[(context.session_id, context.scope_key)].receipt
        return TrustedMatchedRecoveryBinding(
            config=receipt.config,
            path_identity=receipt.path_identity,
            calibration=receipt.calibration,
            legacy_execution=receipt.legacy_execution,
        )


class _UnusedCalibrationAuthority:
    def resolve(self, _ref):
        raise AssertionError("bounded member resolver owns this test boundary")


def _utc(ns: int) -> datetime:
    seconds, remainder = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=remainder // 1_000)


def test_bounded_40_stream_producer_catalog_and_outer_seal_orchestration(
    trusted_processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch,
) -> None:
    processing_database = trusted_processing_database
    capture_root = tmp_path / "qualification" / "capture"
    legacy_root = tmp_path / "qualification" / "legacy"
    capture_root.mkdir(parents=True)
    legacy_root.mkdir()
    capture, scientific = _STORE["_campaign"](
        tmp_path / "capture-work",
        monkeypatch,
        receipt_path=capture_root / "accepted.json",
    )
    expected = {
        (item.product.receipt.path_identity.session_id, item.product.scope_key): item.product
        for item in scientific.streams
    }
    by_session: dict[str, list[TrustedMatchedRecoveryProductV2]] = defaultdict(list)
    for product in expected.values():
        by_session[product.receipt.path_identity.session_id].append(product)
    checks = {
        check.session_id: check for trial in capture.trial_receipts for check in trial.checks
    }

    catalog = processing_database.catalog
    catalog.add_pipeline_release(
        release_id="trusted-release",
        code_revision="test-boundary",
        environment_digest="sha256:" + "a" * 64,
        graph_digest="sha256:" + "b" * 64,
    )
    for session_id, products in by_session.items():
        check = checks[session_id]
        streams = []
        for product in products:
            identity = product.receipt.path_identity
            radio_index = check.observed_radio_ids.index(identity.radio_id)
            streams.append(
                RadioStreamRegistration(
                    stream_id=identity.stream_id,
                    radio_id=identity.radio_id,
                    radio_serial=identity.radio_serial,
                    radio_uri=check.observed_radio_uris[radio_index],
                    radio_transport="ethernet",
                    state="complete",
                    receiver_ids=(1,),
                    sample_rate_hz=2_500_000,
                    captured_sample_count=150_000_000,
                    observed_start_at=_utc(identity.capture_utc_ns),
                    observed_end_at=_utc(identity.capture_end_utc_ns),
                    attributes={"bounded_test_boundary": True},
                    chunks=(),
                )
            )
        assert catalog.reconcile_capture_session(
            session_id=session_id,
            source_type="live",
            bundle_uri=check.bundle_uri,
            manifest_digest=products[0].receipt.path_identity.manifest_digest,
            allocated_bytes=1,
            attributes={"bounded_test_boundary": True},
            observed_start_at=min(item.observed_start_at for item in streams),
            observed_end_at=max(item.observed_end_at for item in streams),
            streams=tuple(streams),
        )

    calibration_ids = {}
    with processing_database.engine.begin() as connection:
        for product in expected.values():
            identity = product.receipt.path_identity
            path_id = connection.execute(
                text(
                    "INSERT INTO receiver_path (radio_id, receiver_id, label) VALUES "
                    "(:radio, 1, 'RX1') ON CONFLICT (radio_id, receiver_id, physical_receiver_id) "
                    "DO NOTHING RETURNING id"
                ),
                {"radio": identity.radio_id},
            ).scalar_one_or_none()
            if path_id is None:
                path_id = connection.execute(
                    text(
                        "SELECT id FROM receiver_path WHERE radio_id=:radio "
                        "AND receiver_id=1 AND physical_receiver_id IS NULL"
                    ),
                    {"radio": identity.radio_id},
                ).scalar_one()
            evidence = product.receipt.calibration.evidence[0]
            calibration_ids[(identity.session_id, identity.stream_id)] = connection.execute(
                text(
                    "INSERT INTO frequency_calibration "
                    "(receiver_path_id, center_offset_hz, valid_from, valid_until, "
                    "evidence_uri, evidence_digest) VALUES "
                    "(:path, 0, :start, :end, :uri, :digest) RETURNING id"
                ),
                {
                    "path": path_id,
                    "start": _utc(identity.capture_utc_ns),
                    "end": _utc(identity.capture_end_utc_ns),
                    "uri": evidence.uri,
                    "digest": evidence.digest,
                },
            ).scalar_one()

    bulk = tmp_path / "bulk"
    (bulk / "spool").mkdir(parents=True)
    (bulk / "recordings").mkdir()
    pin = PinnedLocalRoot(bulk)
    artifacts = AnalysisArtifactStore.open_pinned(pin)
    recordings = RecordingStore.open_pinned(pin)
    pin.close()
    config = next(iter(expected.values())).receipt.config
    service = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=AnalyzerRegistry(
            (
                NativeKnownPilotEvidenceAnalyzer(
                    config=config,
                    scopes=_Scopes(expected),
                    releases=_Releases(expected),
                    executor=_ExecutorBoundary(expected),
                ),
                TrustedMatchedRecoveryAnalyzer(_Bindings(expected)),
            )
        ),
        iq_readers=_IqProvider(),
    )
    for session_id, products in by_session.items():
        run_id = f"run-{session_id}"
        service.create_reprocess_run(
            run_id=run_id,
            session_id=session_id,
            pipeline_release_id="trusted-release",
            input_manifest_digest=products[0].receipt.path_identity.manifest_digest,
            scope_keys=tuple(item.scope_key for item in products),
            promotion_policy="evidence_only",
            stage_keys=("native-known-pilot-evidence", "trusted-matched-recovery-v2"),
        )
        _execute_until_idle(service)
        service.finalize_run(run_id)

    with processing_database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM analysis_run")).scalar_one() == 30
        assert connection.execute(text("SELECT count(*) FROM analysis_product")).scalar_one() == 80
        assert connection.execute(
            text(
                "SELECT count(DISTINCT (run_id, scope_key)) FROM analysis_product "
                "WHERE kind='starlink.trusted-matched-recovery'"
            )
        ).scalar_one() == 40
        assert connection.execute(
            text(
                "SELECT count(*) FROM product_dependency dependency "
                "JOIN analysis_product output ON output.id=dependency.product_id "
                "JOIN analysis_product input ON input.id=dependency.input_product_id "
                "WHERE output.kind='starlink.trusted-matched-recovery' "
                "AND input.kind='starlink.native-known-pilot-evidence'"
            )
        ).scalar_one() == 40
    for run_id in (f"run-{session_id}" for session_id in by_session):
        reference = catalog.run_manifest_reference(run_id)
        artifacts.read_json(reference.logical_uri, reference.digest)
        matched = tuple(
            item
            for item in catalog.run_seal_snapshot(run_id).products
            if item.kind == "starlink.trusted-matched-recovery"
        )
        for product in matched:
            closure = catalog.product_dependency_closure(product.product_id)
            assert len(closure) == 2
            assert {item.kind for item in closure} == {
                "starlink.native-known-pilot-evidence",
                "starlink.trusted-matched-recovery",
            }

    qualification_pin = PinnedLocalRoot(tmp_path / "qualification")
    outputs = ImmutableTrustedCampaignStore(qualification_pin)
    qualification_pin.close()
    finalizer = TrustedCampaignFinalizer._bootstrap_production(
        catalog=catalog,
        artifacts=artifacts,
        recordings=recordings,
        calibrations=PostgresCalibrationCatalogAdapter(catalog, _UnusedCalibrationAuthority()),
        capture=ImmutableCaptureCampaignAuthority(PinnedLocalRoot(capture_root)),
        legacy=ConfinedLegacyExecutionAuthority(PinnedLocalRoot(legacy_root)),
        releases=NativeReleaseCalibrationEvidenceAdapter("trusted-release"),
        native_executor=ReleaseLocalNativeEvidenceExecutor(scratch_root=tmp_path),
        outputs=outputs,
    )
    release = next(iter(expected.values())).receipt.native_release
    finalizer._releases = SimpleNamespace(
        current_release=lambda: SimpleNamespace(
            evidence_digest="sha256:" + "c" * 64,
            native_release=release,
        )
    )

    def bounded_resolve(self, value, _release, _checks):
        snapshot = catalog.run_seal_snapshot(value.analysis_run_id)
        root = next(
            item for item in snapshot.products if item.product_id == value.analysis_product_id
        )
        product = TrustedMatchedRecoveryProductV2.model_validate(
            artifacts.read_json(root.logical_uri, root.digest)
        )
        closure = catalog.product_dependency_closure(root.product_id)
        native = next(
            item for item in closure if item.kind == "starlink.native-known-pilot-evidence"
        )
        NativeKnownPilotEvidenceProductV2.model_validate(
            artifacts.read_json(native.logical_uri, native.digest)
        )
        manifest_ref = catalog.run_manifest_reference(value.analysis_run_id)
        artifacts.read_json(manifest_ref.logical_uri, manifest_ref.digest)
        identity = product.receipt.path_identity
        evidence = product.receipt.calibration.evidence[0]
        dependencies = tuple(
            TrustedCampaignDependencySealV1(
                analysis_product_id=item.product_id,
                kind=item.kind,
                schema_version_of_product=item.schema_version,
                scope_key=item.scope_key,
                logical_uri=item.logical_uri,
                digest=item.digest,
            )
            for item in closure
        )
        common = dict(
            ordinal=0,
            session_id=identity.session_id,
            stream_id=identity.stream_id,
            analysis_run_id=value.analysis_run_id,
            analysis_run_uri=manifest_ref.logical_uri,
            analysis_run_digest=manifest_ref.digest,
            pipeline_release_id=product.pipeline_release,
            analysis_product_id=root.product_id,
            frequency_calibration_id=calibration_ids[(identity.session_id, identity.stream_id)],
            calibration_uri=evidence.uri,
            calibration_digest=evidence.digest,
        )
        return _ResolvedMember(
            product=product,
            registration=ScientificCampaignStreamRegistration(
                **common,
                capture_uri=checks[identity.session_id].bundle_uri,
                capture_digest=identity.manifest_digest,
                scientific_uri=root.logical_uri,
                scientific_digest=root.digest,
                status=product.receipt.status.value,
            ),
            seal=TrustedCampaignMemberSealV1(
                **common,
                analysis_product_uri=root.logical_uri,
                analysis_product_digest=root.digest,
                legacy_envelope_digest=product.receipt.legacy_execution.envelope_digest,
                legacy_receipt_name=value.legacy_receipt_name,
                product_dependency_closure=dependencies,
            ),
        )

    finalizer._resolve_member = MethodType(bounded_resolve, finalizer)
    members = tuple(
        TrustedCampaignMemberInput(
            analysis_run_id=f"run-{product.receipt.path_identity.session_id}",
            analysis_product_id=next(
                item.product_id
                for item in catalog.run_seal_snapshot(
                    f"run-{product.receipt.path_identity.session_id}"
                ).products
                if item.scope_key == product.scope_key
                and item.kind == "starlink.trusted-matched-recovery"
            ),
            legacy_receipt_name=f"legacy-{index:02d}.json",
        )
        for index, product in enumerate(expected.values())
    )
    capture_ref = ImmutableDocumentRefV1(
        logical_uri="qualification://capture/accepted.json",
        digest=_STORE["canonical_digest"](capture.model_dump(mode="json")),
    )
    publication = finalizer.finalize(
        campaign_id="trusted-campaign",
        capture_ref=capture_ref,
        members=members,
    )
    # The private member resolver is deliberately replaced in this test; therefore the
    # resulting PASS-shaped outer document is not evidence of production authority.
    assert finalizer.resolve_publication("trusted-campaign") == publication
    campaign = catalog.scientific_campaign("trusted-campaign")
    assert campaign is not None and campaign.state == "sealed" and len(campaign.streams) == 40
