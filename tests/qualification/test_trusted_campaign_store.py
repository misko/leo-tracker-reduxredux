from __future__ import annotations

from pathlib import Path
from runpy import run_path
from types import MethodType, SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from leo.analysis.starlink.trusted_acceptance import evaluate_trusted_campaign_v2
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
    TrustedCampaignMemberSealV1,
    TrustedCampaignOuterSealV1,
    TrustedCampaignSealMaterialV1,
    _presentation,
    _ResolvedMember,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import MatchedAcceptanceStatus
from leo.domain.profiles import load_profile_revision
from leo.qualification.capture_modes import (
    CaptureModeAcceptanceHarness,
    CaptureModeExpectationV1,
)
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.qualification.trusted_campaign_store import (
    ImmutableTrustedCampaignStore,
    TrustedCampaignPublicationConflict,
)
from leo.storage import PinnedLocalRoot, RecordingStore

_V2 = run_path(str(Path(__file__).parents[1] / "analysis" / "test_trusted_acceptance_v2.py"))
_CAPTURE = run_path(str(Path(__file__).with_name("test_capture_modes.py")))


def _campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt_path: Path | None = None,
):
    revision = load_profile_revision(
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml"
    )
    expectation = CaptureModeExpectationV1.from_hardware_profile_revision(
        revision, _CAPTURE["_HARDWARE_IDS"]
    )

    def passed_check(self, expected, role, session_id, expected_radios):
        del self
        return _CAPTURE["_synthetic_hardware_check"](expected, role, session_id, expected_radios)

    monkeypatch.setattr(CaptureModeAcceptanceHarness, "_check", passed_check)
    capture = CaptureModeAcceptanceHarness(RecordingStore(tmp_path / "recordings")).run_campaign(
        expectation,
        acceptance_id="capture-authority",
        independent_radio_a_session_ids=tuple(f"a-{index}" for index in range(10)),
        independent_radio_b_session_ids=tuple(f"b-{index}" for index in range(10)),
        synchronized_pair_session_ids=tuple(f"pair-{index}" for index in range(10)),
        observed_utc_ns=1_800_000_100_000_000_000,
        receipt_path=receipt_path,
    )
    binding = _V2["_binding"]()
    config = campaign_config_from_accepted_capture(
        campaign_id="trusted-campaign",
        capture_receipt=capture,
        detector_binding=binding,
    )
    products = tuple(
        _V2["_product"](
            _V2["_identity"](
                session_id=item.session_id,
                stream_id=item.stream_id,
                manifest_digest=item.manifest_digest,
                profile_digest=item.profile_revision_digest,
                radio_id=item.radio_id,
                radio_serial=item.radio_serial,
                physical_receiver_id=item.physical_receiver_id,
                hardware_epoch_id=item.hardware_epoch_id,
                start_ns=item.dwell_start_utc_ns,
                end_ns=item.dwell_end_utc_ns,
            ),
            binding=binding,
        )
        for item in config.capture_inventory
    )
    return capture, evaluate_trusted_campaign_v2(config=config, products=products)


def _material(capture, scientific):
    members = tuple(
        TrustedCampaignMemberSealV1(
            ordinal=index,
            session_id=item.product.receipt.path_identity.session_id,
            stream_id=item.product.scope_key,
            analysis_run_id=item.product.analysis_run_id,
            analysis_run_uri=f"bulk://analysis/{index}/manifest.json",
            analysis_run_digest="sha256:" + "1" * 64,
            pipeline_release_id=item.product.pipeline_release,
            analysis_product_id=index + 1,
            analysis_product_uri=f"bulk://analysis/{index}/product.json",
            analysis_product_digest="sha256:" + "2" * 64,
            frequency_calibration_id=index + 1,
            calibration_uri=f"bulk://calibration/{index}",
            calibration_digest="sha256:" + "3" * 64,
            legacy_envelope_digest=item.product.receipt.legacy_execution.envelope_digest,
            legacy_receipt_name=f"legacy-{index}.json",
            product_dependency_closure=(
                TrustedCampaignDependencySealV1(
                    analysis_product_id=index + 1,
                    kind="starlink.trusted-matched-recovery",
                    schema_version_of_product=2,
                    scope_key=item.product.scope_key,
                    logical_uri=f"bulk://analysis/{index}/product.json",
                    digest="sha256:" + "2" * 64,
                ),
            ),
        )
        for index, item in enumerate(scientific.streams)
    )

    return TrustedCampaignSealMaterialV1(
        campaign_id=scientific.config.campaign_id,
        capture={
            "schema_version": 1,
            "logical_uri": "qualification://capture/accepted.json",
            "digest": canonical_digest(capture.model_dump(mode="json")),
        },
        current_release_evidence_digest="sha256:" + "4" * 64,
        members=members,
        result_status=scientific.status,
        mathematical_eligible=scientific.mathematical_eligible,
        production_accepted=scientific.status is MatchedAcceptanceStatus.PASS,
    )


class _UnusedCalibrationAuthority:
    def resolve(self, ref):
        raise AssertionError(f"store unit test must not resolve calibration {ref}")


def _bound_store(tmp_path: Path, *, failure_injector=None):
    bulk = tmp_path / "pinned-bulk"
    qualification = tmp_path / "pinned-qualification"
    capture = tmp_path / "pinned-capture"
    legacy = tmp_path / "pinned-legacy"
    for root in (bulk, qualification, capture, legacy):
        root.mkdir()
    (bulk / "spool").mkdir()
    (bulk / "recordings").mkdir()
    artifacts = AnalysisArtifactStore.open_pinned(PinnedLocalRoot(bulk))
    recordings = RecordingStore.open_pinned(PinnedLocalRoot(bulk))
    store = ImmutableTrustedCampaignStore(
        PinnedLocalRoot(qualification), failure_injector=failure_injector
    )
    catalog = CatalogRepository(
        sessionmaker(bind=create_engine("postgresql+psycopg:///leo_tracker"))
    )
    calibrations = PostgresCalibrationCatalogAdapter(
        catalog,
        _UnusedCalibrationAuthority(),
    )
    finalizer = TrustedCampaignFinalizer._bootstrap_production(
        catalog=catalog,
        artifacts=artifacts,
        recordings=recordings,
        calibrations=calibrations,
        capture=ImmutableCaptureCampaignAuthority(PinnedLocalRoot(capture)),
        legacy=ConfinedLegacyExecutionAuthority(PinnedLocalRoot(legacy)),
        releases=NativeReleaseCalibrationEvidenceAdapter("trusted-release"),
        native_executor=ReleaseLocalNativeEvidenceExecutor(scratch_root=tmp_path),
        outputs=store,
    )
    return store, finalizer


def test_store_is_capability_protected_atomic_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, scientific = _campaign(tmp_path, monkeypatch)
    store, finalizer = _bound_store(tmp_path)
    authority = finalizer._authority
    sentinel = finalizer._initialization_sentinel
    presentation = _presentation(scientific)
    material = _material(capture, scientific)

    forged_finalizer = object.__new__(TrustedCampaignFinalizer)
    forged_finalizer._initialization_sentinel = object()
    with pytest.raises(TypeError, match="fully initialized"):
        store._bind_trusted_finalizer(
            forged_finalizer,
            forged_finalizer._initialization_sentinel,
        )

    with pytest.raises(PermissionError):
        store._publish_verified(
            object(),
            finalizer,
            sentinel,
            "trusted-campaign",
            scientific,
            presentation,
            material,
        )
    original_root = tmp_path / "pinned-qualification"
    retained_root = tmp_path / "retained-qualification-inode"
    original_root.rename(retained_root)
    original_root.mkdir()
    first = store._publish_verified(
        authority,
        finalizer,
        sentinel,
        "trusted-campaign",
        scientific,
        presentation,
        material,
    )
    second = store._publish_verified(
        authority,
        finalizer,
        sentinel,
        "trusted-campaign",
        scientific,
        presentation,
        material,
    )
    assert first == second == store._load_confined("trusted-campaign")
    assert (retained_root / "trusted-campaigns" / "trusted-campaign" / "seal.json").is_file()
    assert not (original_root / "trusted-campaigns").exists()
    assert first.seal.production_accepted
    assert not scientific.acceptance_eligible and not scientific.production_accepted
    assert {path.name for path in (store.campaign_root / "trusted-campaign").iterdir()} == {
        "scientific.json",
        "presentation.json",
        "seal.json",
    }

    changed = scientific.model_copy(update={"status": MatchedAcceptanceStatus.FAIL})
    with pytest.raises(TrustedCampaignPublicationConflict):
        store._publish_verified(
            authority,
            finalizer,
            sentinel,
            "trusted-campaign",
            changed,
            presentation,
            material,
        )


def test_store_crash_never_exposes_partial_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, scientific = _campaign(tmp_path, monkeypatch)

    def fail(point: str) -> None:
        if point == "after_presentation":
            raise RuntimeError("injected crash")

    store, finalizer = _bound_store(tmp_path, failure_injector=fail)
    authority = finalizer._authority
    sentinel = finalizer._initialization_sentinel
    with pytest.raises(RuntimeError, match="injected crash"):
        store._publish_verified(
            authority,
            finalizer,
            sentinel,
            "trusted-campaign",
            scientific,
            _presentation(scientific),
            _material(capture, scientific),
        )
    assert not (store.campaign_root / "trusted-campaign").exists()
    assert not tuple(store.campaign_root.glob("*.partial"))


def test_store_rejects_qnap() -> None:
    with pytest.raises(ValueError, match="local storage"):
        PinnedLocalRoot(Path("/mnt/qnap01/trusted-campaign"))


def test_capture_authority_reloads_exact_create_only_receipt_and_rejects_forgery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "capture-evidence"
    evidence.mkdir()
    receipt_path = evidence / "accepted.json"
    capture, _scientific = _campaign(
        tmp_path,
        monkeypatch,
        receipt_path=receipt_path,
    )
    authority = ImmutableCaptureCampaignAuthority(PinnedLocalRoot(evidence))
    ref = ImmutableDocumentRefV1(
        logical_uri="qualification://capture/accepted.json",
        digest=canonical_digest(capture.model_dump(mode="json")),
    )
    assert authority.resolve(ref) == capture

    with pytest.raises(ValueError, match="durable reference"):
        authority.resolve(ref.model_copy(update={"digest": "sha256:" + "f" * 64}))
    forged = evidence / "forged.json"
    forged.write_bytes(receipt_path.read_bytes())
    forged.chmod(0o440)
    with pytest.raises(ValueError, match="durable reference"):
        authority.resolve(
            ImmutableDocumentRefV1(
                logical_uri="qualification://capture/forged.json",
                digest="sha256:" + "e" * 64,
            )
        )


def test_public_resolver_rejects_forged_aggregate_and_copied_capture_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, scientific = _campaign(tmp_path, monkeypatch)
    store, finalizer = _bound_store(tmp_path)
    publication = store._publish_verified(
        finalizer._authority,
        finalizer,
        finalizer._initialization_sentinel,
        "trusted-campaign",
        scientific,
        _presentation(scientific),
        _material(capture, scientific),
    )
    products = {index + 1: stream.product for index, stream in enumerate(scientific.streams)}
    seals = {item.analysis_product_id: item for item in publication.seal.members}

    def resolve_member(self, member, release, checks):
        del self, release, checks
        return _ResolvedMember(
            product=products[member.analysis_product_id],
            registration=None,  # type: ignore[arg-type]
            seal=seals[member.analysis_product_id].model_copy(update={"ordinal": 0}),
        )

    class Output:
        value = publication

        def _load_verified(self, authority, owner, sentinel, campaign_id):
            del authority, owner, sentinel, campaign_id
            return self.value, scientific, _presentation(scientific)

    output = Output()
    record = SimpleNamespace(
        state="sealed",
        capture_uri=publication.seal.capture.logical_uri,
        capture_digest=publication.seal.capture.digest,
        outer_seal_uri=publication.outer_seal.logical_uri,
        outer_seal_digest=publication.outer_seal.digest,
        scientific_uri=publication.scientific.logical_uri,
        scientific_digest=publication.scientific.digest,
        presentation_uri=publication.presentation.logical_uri,
        presentation_digest=publication.presentation.digest,
        result_status=scientific.status.value,
    )
    finalizer._catalog = SimpleNamespace(scientific_campaign=lambda _campaign_id: record)
    finalizer._outputs = output
    finalizer._capture = SimpleNamespace(resolve=lambda _ref: capture)
    finalizer._releases = SimpleNamespace(
        current_release=lambda: SimpleNamespace(
            evidence_digest=publication.seal.current_release_evidence_digest
        )
    )
    finalizer._resolve_member = MethodType(resolve_member, finalizer)

    assert finalizer.resolve_publication("trusted-campaign") == publication

    record.capture_uri = "qualification://capture/copied.json"
    with pytest.raises(ValueError, match="catalog campaign references"):
        finalizer.resolve_publication("trusted-campaign")
    record.capture_uri = publication.seal.capture.logical_uri

    values = publication.seal.model_dump(mode="python", exclude={"seal_digest"})
    values["result_status"] = "fail"
    values["production_accepted"] = False
    forged_seal = TrustedCampaignOuterSealV1.model_validate(
        {**values, "seal_digest": canonical_digest(values)}
    )
    output.value = publication.model_copy(update={"seal": forged_seal})
    record.result_status = "fail"
    with pytest.raises(ValueError, match="outer/catalog campaign result"):
        finalizer.resolve_publication("trusted-campaign")


def test_public_resolver_rejects_release_document_and_member_seal_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture, scientific = _campaign(tmp_path, monkeypatch)
    store, finalizer = _bound_store(tmp_path)
    publication = store._publish_verified(
        finalizer._authority,
        finalizer,
        finalizer._initialization_sentinel,
        "trusted-campaign",
        scientific,
        _presentation(scientific),
        _material(capture, scientific),
    )
    products = {index + 1: stream.product for index, stream in enumerate(scientific.streams)}
    seals = {item.analysis_product_id: item for item in publication.seal.members}

    def resolve_member(self, member, release, checks):
        del self, release, checks
        return _ResolvedMember(
            product=products[member.analysis_product_id],
            registration=None,  # type: ignore[arg-type]
            seal=seals[member.analysis_product_id],
        )

    class Output:
        value = publication
        presentation = _presentation(scientific)

        def _load_verified(self, authority, owner, sentinel, campaign_id):
            del authority, owner, sentinel, campaign_id
            return self.value, scientific, self.presentation

    output = Output()
    record = SimpleNamespace(
        state="sealed",
        capture_uri=publication.seal.capture.logical_uri,
        capture_digest=publication.seal.capture.digest,
        outer_seal_uri=publication.outer_seal.logical_uri,
        outer_seal_digest=publication.outer_seal.digest,
        scientific_uri=publication.scientific.logical_uri,
        scientific_digest=publication.scientific.digest,
        presentation_uri=publication.presentation.logical_uri,
        presentation_digest=publication.presentation.digest,
        result_status=scientific.status.value,
    )
    release = SimpleNamespace(
        evidence_digest=publication.seal.current_release_evidence_digest
    )
    finalizer._catalog = SimpleNamespace(scientific_campaign=lambda _campaign_id: record)
    finalizer._outputs = output
    finalizer._capture = SimpleNamespace(resolve=lambda _ref: capture)
    finalizer._releases = SimpleNamespace(current_release=lambda: release)
    finalizer._resolve_member = MethodType(resolve_member, finalizer)

    assert finalizer.resolve_publication("trusted-campaign") == publication

    release.evidence_digest = "sha256:" + "9" * 64
    with pytest.raises(ValueError, match="non-current deployed release"):
        finalizer.resolve_publication("trusted-campaign")
    release.evidence_digest = publication.seal.current_release_evidence_digest

    record.presentation_digest = "sha256:" + "8" * 64
    with pytest.raises(ValueError, match="catalog campaign references"):
        finalizer.resolve_publication("trusted-campaign")
    record.presentation_digest = publication.presentation.digest

    output.presentation = output.presentation.model_copy(
        update={"result_status": MatchedAcceptanceStatus.FAIL}
    )
    with pytest.raises(ValueError, match="authoritative replay"):
        finalizer.resolve_publication("trusted-campaign")
    output.presentation = _presentation(scientific)

    changed_member = publication.seal.members[0].model_copy(
        update={"analysis_run_digest": "sha256:" + "7" * 64}
    )
    values = publication.seal.model_dump(mode="json", exclude={"seal_digest"})
    values["members"] = tuple(
        item.model_dump(mode="json")
        for item in (changed_member, *publication.seal.members[1:])
    )
    changed_seal = TrustedCampaignOuterSealV1.model_validate(
        {**values, "seal_digest": canonical_digest(values)}
    )
    output.value = publication.model_copy(update={"seal": changed_seal})
    with pytest.raises(ValueError, match="member seal"):
        finalizer.resolve_publication("trusted-campaign")
