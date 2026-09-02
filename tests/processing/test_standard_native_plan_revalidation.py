from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any, Literal, cast

import pytest

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_registry,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV6,
)
from leo.pipeline import (
    ExpandedRunPlanV1,
    IqAccess,
    JobNodeV1,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ResourceClass,
    ScopeIdentityV1,
)
from leo.pipeline.standard_native import (
    compile_standard_native_automatic_run_plan,
    compile_standard_native_default_run_plan,
    compile_standard_native_run_plan,
)
from leo.processing import ProcessingService
from leo.processing.adapters import IqReaderProvider
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore
from tests.pipeline.test_standard_native_topology import _manifest, _reviewed_v2_manifest
from tests.processing.test_mixed_rate_standard_native_operational_vertical import (
    _RADIO_IDS,
    _bounded_direct_async_plan,
)

_RELEASE = "1" * 40


class _Catalog:
    def __init__(
        self,
        manifest_digest: str,
        *,
        promotion_permitted: bool = True,
    ) -> None:
        self.manifest_digest = manifest_digest
        self.promotion_permitted = promotion_permitted
        self.created: dict[str, Any] | None = None
        self.attestation: object | None = None

    def capture_recording_identity(self, session_id: str) -> object:
        return SimpleNamespace(
            session_id=session_id,
            manifest_digest=self.manifest_digest,
        )

    def capture_path_authority(self, session_id: str) -> object:
        return SimpleNamespace(
            session_id=session_id,
            manifest_digest=self.manifest_digest,
            authority_kind="station",
            authority_digest=canonical_digest({"station": session_id}),
            topology_digest=canonical_digest({"topology": session_id}),
            evidence_only=False,
            current_analysis_eligible=True,
            physical_association_permitted=True,
            calibration_association_permitted=True,
            promotion_permitted=self.promotion_permitted,
        )

    def register_raw_integrity_attestation(self, value: object) -> None:
        self.attestation = value

    def create_analysis_run(self, **values: Any) -> None:
        self.created = values


class _Provider:
    def __init__(self, manifest: object, manifest_digest: str) -> None:
        self.manifest = manifest
        self.integrity = RawIntegrityAttestationV1(
            session_id=manifest.session_id,  # type: ignore[attr-defined]
            manifest_digest=manifest_digest,
            streams=tuple(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=1,
                    compressed_closure_digest=canonical_digest({"compressed": stream.stream_id}),
                    uncompressed_closure_digest=canonical_digest(
                        {"uncompressed": stream.stream_id}
                    ),
                )
                for stream in manifest.streams  # type: ignore[attr-defined]
            ),
            verifier_version="native-test-v1",
            verified_utc_ns=1,
        )

    def verify_integrity(self, _identity: object) -> RawIntegrityAttestationV1:
        return self.integrity

    def verified_manifest(self, attestation_digest: str) -> object:
        assert attestation_digest == self.integrity.attestation_digest
        return self.manifest


def _system():  # noqa: ANN202
    manifest = _manifest("starlink-ch4-lower-3m-60s-device-axis-v3")
    manifest_digest = canonical_digest({"manifest": "native-service"})
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest)
    provider = _Provider(manifest, manifest_digest)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, provider),
    )
    return service, catalog, plan, manifest


def _historical_v2_system():  # noqa: ANN202
    manifest = _reviewed_v2_manifest(5_000_000)
    manifest_digest = canonical_digest({"manifest": "historical-v2-native-service"})
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest)
    provider = _Provider(manifest, manifest_digest)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, provider),
    )
    return service, catalog, plan


def test_native_plan_cannot_enter_research_lane() -> None:
    service, _, plan, _ = _system()

    with pytest.raises(ValueError, match="disjoint Standard-lane"):
        service.create_expanded_run(
            run_id="native-run",
            plan=plan,
            trigger="reprocess",
            pipeline_lane=PipelineLane.RESEARCH,
            promotion_policy="evidence_only",
        )


@pytest.mark.parametrize(
    "profile_name",
    (
        "starlink-ch4-lower-2p5m-60s-device-axis-v3",
        "starlink-ch4-lower-3m-60s-device-axis-v3",
        "starlink-ch4-lower-5m-60s-device-axis-v3",
    ),
)
@pytest.mark.parametrize("trigger", ("new_capture", "reprocess"))
def test_exact_v3_native_plan_respects_automatic_2p5_only_policy(
    monkeypatch: pytest.MonkeyPatch,
    profile_name: str,
    trigger: Literal["new_capture", "reprocess"],
) -> None:
    from leo.processing import service as processing_service

    manifest = _manifest(profile_name)
    manifest_digest = canonical_digest({"manifest": profile_name})
    rate_hz = manifest.capture_plan.profile_revision.profile.sample_rate_hz
    compiler = (
        compile_standard_native_automatic_run_plan
        if trigger == "new_capture"
        else compile_standard_native_run_plan
    )
    if trigger == "new_capture" and rate_hz != 2_500_000:
        with pytest.raises(
            ValueError,
            match="automatic Standard-native analysis requires a 2.5 MS/s stream",
        ):
            compiler(
                manifest,
                manifest_digest=manifest_digest,
                pipeline_release_id=_RELEASE,
            )
        return
    plan = compiler(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, _Provider(manifest, manifest_digest)),
    )
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: (),
    )

    service.create_expanded_run(
        run_id=(f"native-current-{trigger}-{rate_hz}"),
        plan=plan,
        trigger=trigger,
        pipeline_lane=PipelineLane.STANDARD,
        promotion_policy="current",
    )

    assert catalog.created is not None
    assert catalog.created["promotion_policy"] == "current"
    assert catalog.created["pipeline_lane"] is PipelineLane.STANDARD
    assert catalog.created["trigger"] == trigger


def test_v3_current_requires_station_promotion_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leo.processing import service as processing_service

    manifest = _manifest("starlink-ch4-lower-3m-60s-device-axis-v3")
    manifest_digest = canonical_digest({"manifest": "station-refusal"})
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest, promotion_permitted=False)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, _Provider(manifest, manifest_digest)),
    )
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: pytest.fail("unauthorized run reached subject binding persistence"),
    )

    with pytest.raises(ValueError, match="station hardware authority"):
        service.create_expanded_run(
            run_id="native-current-without-station-authority",
            plan=plan,
            trigger="new_capture",
            promotion_policy="current",
        )

    assert catalog.created is None


@pytest.mark.parametrize(
    ("trigger", "promotion"),
    (("new_capture", "evidence_only"), ("reprocess", "current")),
)
def test_historical_v2_native_plan_never_enters_automatic_or_current(
    trigger: str,
    promotion: str,
) -> None:
    service, catalog, plan = _historical_v2_system()

    with pytest.raises(ValueError, match="V2 requires a manual Standard-lane evidence-only"):
        service.create_expanded_run(
            run_id="historical-v2-native-run",
            plan=plan,
            trigger=trigger,  # type: ignore[arg-type]
            pipeline_lane=PipelineLane.STANDARD,
            promotion_policy=promotion,
        )

    assert catalog.created is None


def test_v3_manifest_cannot_enter_frozen_standard_graph() -> None:
    service, _, _, manifest = _system()
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=manifest.streams[0].stream_id,
        receiver_id=0,
    )
    plan = ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=canonical_digest({"manifest": "native-service"}),
        pipeline_release_id=_RELEASE,
        jobs=(
            JobNodeV1(
                node_id="path-00-standard",
                stage_key="path-standard",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class=ResourceClass.HEAVY,
            ),
        ),
        edges=(),
    )

    with pytest.raises(ValueError, match="frozen Standard accepts only V1/V2"):
        service.create_expanded_run(
            run_id="foreign-run",
            plan=plan,
            trigger="reprocess",
            promotion_policy="evidence_only",
        )


def test_native_plan_is_recompiled_before_persistence() -> None:
    service, _, plan, _ = _system()
    altered_jobs = tuple(
        job.model_copy(update={"resource_class": ResourceClass.CPU})
        if job.stage_key == "path-standard-native"
        else job
        for job in plan.jobs
    )
    altered = ExpandedRunPlanV1.create(
        session_id=plan.session_id,
        manifest_digest=plan.manifest_digest,
        pipeline_release_id=plan.pipeline_release_id,
        jobs=altered_jobs,
        edges=plan.edges,
    )

    with pytest.raises(ValueError, match="manifest-authoritative Standard-native DAG"):
        service.create_expanded_run(
            run_id="altered-run",
            plan=altered,
            trigger="reprocess",
            promotion_policy="evidence_only",
        )


def test_exact_native_plan_reaches_evidence_only_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leo.processing import service as processing_service

    service, catalog, plan, _ = _system()
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: (),
    )

    service.create_expanded_run(
        run_id="exact-native-run",
        plan=plan,
        trigger="reprocess",
        promotion_policy="evidence_only",
    )

    assert catalog.attestation is not None
    assert catalog.created is not None
    assert catalog.created["promotion_policy"] == "evidence_only"
    assert catalog.created["pipeline_lane"] is PipelineLane.STANDARD
    assert len(catalog.created["jobs"]) == len(plan.jobs)


def test_v6_automatic_run_revalidates_the_complete_2p5_x25_pair(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leo.processing import service as processing_service

    capture_plan = _bounded_direct_async_plan(monkeypatch, high_rate_hz=25_000_000)
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        capture_plan,
        {
            _RADIO_IDS[0]: FakeRadioSource(_RADIO_IDS[0], seed=81),
            _RADIO_IDS[1]: FakeRadioSource(_RADIO_IDS[1], seed=82),
        },
        session_id="automatic-low-only-v6",
    )
    assert type(result.manifest) is RecordingManifestV6
    manifest = result.manifest
    manifest_digest = canonical_digest({"manifest": "automatic-low-only-v6"})
    automatic = compile_standard_native_automatic_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    explicit = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    default = compile_standard_native_default_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, _Provider(manifest, manifest_digest)),
    )
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: (),
    )

    service.create_expanded_run(
        run_id="automatic-low-only-v6-run",
        plan=automatic,
        trigger="new_capture",
        promotion_policy="current",
    )

    assert catalog.created is not None
    rates_by_stream_id = {
        stream.stream_id: stream.applied_settings.sample_rate_hz for stream in manifest.streams
    }
    automatic_rates = {
        rates_by_stream_id[job.scope.stream_id]
        for job in automatic.jobs
        if job.scope.stream_id is not None
    }
    explicit_rates = {
        rates_by_stream_id[job.scope.stream_id]
        for job in explicit.jobs
        if job.scope.stream_id is not None
    }
    assert automatic_rates == {2_500_000, 25_000_000}
    assert explicit_rates == {2_500_000, 25_000_000}
    assert default == automatic
    assert Counter(job.stage_key for job in automatic.jobs) == Counter(
        {
            "path-standard-native": 2,
            "path-alternate-tracks-native": 2,
            "path-pss-native": 1,
            "radio-scientific-report-native": 1,
            "paired-pss-glrt-presentation-native": 1,
        }
    )
    assert Counter(job.stage_key for job in explicit.jobs) == Counter(
        {
            "path-standard-native": 3,
            "path-alternate-tracks-native": 3,
            "path-pss-native": 3,
            "radio-scientific-report-native": 2,
            "paired-scientific-report-native": 1,
            "paired-presentation-native": 1,
            "paired-pss-glrt-presentation-native": 1,
        }
    )
    assert {
        rates_by_stream_id[job.scope.stream_id]
        for job in automatic.jobs
        if job.stage_key == "path-standard-native" and job.scope.stream_id is not None
    } == {2_500_000}
    assert {
        rates_by_stream_id[job.scope.stream_id]
        for job in automatic.jobs
        if job.stage_key == "path-pss-native" and job.scope.stream_id is not None
    } == {25_000_000}
