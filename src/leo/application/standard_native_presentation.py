"""Read-only presentation projection for promoted Standard-native runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal, cast
from urllib.parse import quote

from leo.analysis.standard.native_products import (
    ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
    CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    DOPPLER_WATERFALL_PNG_V1_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V1_PRODUCT,
    FULL_CAPTURE_GLRT20MS_V2_PRODUCT,
    NUMERICAL_WATERFALL_V3_PRODUCT,
    NUMERICAL_WATERFALL_V4_PRODUCT,
    PAIRED_REPORT_V4_PRODUCT,
    PAIRED_REPORT_V5_PRODUCT,
    PAIRED_REPORT_V6_PRODUCT,
    PAIRED_REPORT_V7_PRODUCT,
    PATH_REPORT_V3_PRODUCT,
    PATH_REPORT_V4_PRODUCT,
    PILOT_CARRIER_TRACKING_PNG_V3_PRODUCT,
    PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_PNG_V3_PRODUCT,
    PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT,
    PILOT_METHODS_PNG_V2_PRODUCT,
    PILOT_SEGMENT_RATES_PNG_V3_PRODUCT,
    PILOT_SEGMENT_RATES_PNG_V4_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    POWER_TIMELINE_V4_PRODUCT,
    RADIO_REPORT_V4_PRODUCT,
    RADIO_REPORT_V5_PRODUCT,
    RADIO_REPORT_V6_PRODUCT,
    TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,
    WATERFALL_PNG_V2_PRODUCT,
)
from leo.artifacts import (
    AnalysisArtifactStore,
    AnalysisRunManifestV3,
    AnalysisRunManifestV4,
    AnalysisRunManifestV5,
    AnalysisRunManifestV6,
    parse_analysis_run_manifest,
)
from leo.catalog import CatalogRepository
from leo.catalog.types import CatalogJobRecord, CatalogProductRecord, CatalogSessionReadSnapshot
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import (
    NativeQualityReceiverV2,
    NativeSufficientStatisticsV1,
    StandardNativeNumericalWaterfallV3,
    StandardNativeNumericalWaterfallV4,
    StandardNativePowerTimelineV3,
    StandardNativePowerTimelineV4,
)
from leo.contracts.standard_native_glrt import (
    StandardNativeFullCaptureGlrt20msV1,
    StandardNativeFullCaptureGlrt20msV2,
)
from leo.contracts.standard_native_path_report import (
    StandardNativePathReportV3,
    StandardNativePathReportV4,
)
from leo.contracts.standard_native_terminal import (
    NativeTerminalPathEvidenceV2,
    NativeTerminalPathEvidenceV3,
    StandardNativePairedReportV4,
    StandardNativePairedReportV5,
    StandardNativePairedReportV6,
    StandardNativePairedReportV7,
    StandardNativeRadioReportV4,
    StandardNativeRadioReportV5,
    StandardNativeRadioReportV6,
    terminal_track_accounting,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4, StandardPathInputBindV5
from leo.pipeline.scopes import ScopeIdentityV1, ScopeKind
from leo.pipeline.standard_native import standard_native_pipeline_definition_v1
from leo.presentation.standard_native_artifacts import (
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7,
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8,
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactInventoryV5,
    StandardNativePngArtifactInventoryV6,
    StandardNativePngArtifactInventoryV7,
    StandardNativePngArtifactInventoryV8,
    StandardNativePngArtifactInventoryV9,
    StandardNativePngArtifactNameV4,
    StandardNativePngArtifactV4,
    StandardNativePngArtifactV8,
)
from leo.presentation.standard_native_pipeline import (
    NativeArtifactNameV3,
    StandardNativeEligibilityV3,
    StandardNativeEligibilityV4,
    StandardNativeEligibilityV5,
    StandardNativeEligibilityV6,
    StandardNativeFrequencyAxisV4,
    StandardNativeFrequencyAxisV5,
    StandardNativeMetricPointV3,
    StandardNativeMetricSeriesV3,
    StandardNativeMixedLegV4,
    StandardNativePathEvidenceV3,
    StandardNativePipelineReleaseV3,
    StandardNativePlotViewV3,
    StandardNativePlotViewV4,
    StandardNativePlotViewV5,
    StandardNativePlotViewV6,
    StandardNativePresentationProductRefV3,
    StandardNativeProductionLegV5,
    StandardNativeProductionLegV6,
    StandardNativeSourceProofV3,
    StandardNativeSubjectDetailV3,
    StandardNativeSubjectDetailV4,
    StandardNativeSubjectDetailV5,
    StandardNativeSubjectDetailV6,
    StandardNativeSubjectHierarchyV3,
    StandardNativeSubjectHierarchyV4,
    StandardNativeSubjectHierarchyV5,
    StandardNativeSubjectHierarchyV6,
    StandardNativeSubjectSummaryV3,
    StandardNativeSubjectSummaryV4,
    StandardNativeSubjectSummaryV5,
    StandardNativeSubjectSummaryV6,
    StandardNativeTerminalSummaryV3,
    StandardNativeTrajectoryV3,
    StandardNativeViewDescriptorV3,
    StandardNativeWaterfallTileV3,
    StandardNativeWaterfallTileV4,
    native_stage_status_v3,
)
from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardReceiverPathRefV2,
    StandardReplayAuditV1,
    StandardReuseSummaryV2,
    StandardSourceExtremaProofV2,
    StandardStageStatusV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardSubjectKindV2,
    StandardTimeDomainV2,
    StandardTrackGateAuditV1,
    StandardViewKindV2,
    StandardViewStateV2,
)

from .standard_presentation import (
    CatalogStandardPresentationRepository,
    StandardPresentationNotReady,
    StandardPresentationUnavailable,
)

_TerminalRadioReport = (
    StandardNativeRadioReportV4 | StandardNativeRadioReportV5 | StandardNativeRadioReportV6
)
_TerminalPairedReport = (
    StandardNativePairedReportV4
    | StandardNativePairedReportV5
    | StandardNativePairedReportV6
    | StandardNativePairedReportV7
)


@dataclass(frozen=True, slots=True)
class _NativePath:
    product: CatalogProductRecord
    binding: StandardPathInputBindV4 | StandardPathInputBindV5
    report: StandardNativePathReportV3 | StandardNativePathReportV4
    terminal: NativeTerminalPathEvidenceV2 | NativeTerminalPathEvidenceV3
    power_product: CatalogProductRecord
    power: StandardNativePowerTimelineV3 | StandardNativePowerTimelineV4
    waterfall_product: CatalogProductRecord
    waterfall: StandardNativeNumericalWaterfallV3 | StandardNativeNumericalWaterfallV4
    glrt_product: CatalogProductRecord
    glrt: StandardNativeFullCaptureGlrt20msV1 | StandardNativeFullCaptureGlrt20msV2
    reference: StandardReceiverPathRefV2


@dataclass(frozen=True, slots=True)
class _NativeProjection:
    snapshot: CatalogSessionReadSnapshot
    run_id: str
    manifest_digest: str
    manifest: (
        AnalysisRunManifestV3
        | AnalysisRunManifestV4
        | AnalysisRunManifestV5
        | AnalysisRunManifestV6
    )
    release: StandardNativePipelineReleaseV3
    eligibility: (
        StandardNativeEligibilityV3
        | StandardNativeEligibilityV4
        | StandardNativeEligibilityV5
        | StandardNativeEligibilityV6
    )
    paths: tuple[_NativePath, ...]
    radios: tuple[tuple[CatalogProductRecord, _TerminalRadioReport], ...]
    paired: tuple[CatalogProductRecord, _TerminalPairedReport] | None
    jobs: tuple[CatalogJobRecord, ...]
    products: tuple[CatalogProductRecord, ...]
    hierarchy: (
        StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
        | StandardNativeSubjectHierarchyV5
        | StandardNativeSubjectHierarchyV6
    )
    subjects: dict[
        str,
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6,
    ]


_PILOT_PNG_KINDS = (
    "standard.pilot-doppler-segments-png",
    "standard.pilot-carrier-tracking-png",
    "standard.pilot-segment-rates-png",
)


def _pilot_png_schema_version(loaded: _NativeProjection) -> Literal[3, 4] | None:
    """Resolve one run-wide pilot-view generation without rewriting old contracts."""

    schemas_by_kind = {
        kind: {
            product.schema_version
            for product in loaded.products
            if product.kind == kind
            and product.role == "presentation"
            and product.media_type == "image/png"
            and product.available
        }
        for kind in _PILOT_PNG_KINDS
    }
    if all(schemas == {4} for schemas in schemas_by_kind.values()):
        return 4
    if all(schemas == {3} for schemas in schemas_by_kind.values()):
        return 3
    if all(not schemas for schemas in schemas_by_kind.values()):
        return None
    raise StandardPresentationUnavailable(
        "sealed Standard-native run has a mixed or incomplete pilot PNG generation"
    )


class CatalogStandardNativePresentationRepository:
    """Project exact Current common- or mixed-rate Standard-native runs."""

    def __init__(self, catalog: CatalogRepository, artifacts: AnalysisArtifactStore) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._projection_lock = Lock()
        self._cached_projection: _NativeProjection | None = None

    def recognizes_native_current(self, session_id: str) -> bool:
        """Return whether the selected Standard run declares manifest schema V3.

        Once schema V3 is declared, corruption fails through the native branch;
        it must never fall back to the frozen V2 projector.
        """

        snapshot = self._catalog.presentation_snapshot(session_id)
        if snapshot is None or snapshot.analysis is None:
            return False
        analysis = snapshot.analysis
        if analysis.manifest_uri is None or analysis.manifest_digest is None:
            return False
        try:
            document = self._artifacts.read_json(
                analysis.manifest_uri,
                analysis.manifest_digest,
            )
        except Exception as error:
            raise StandardPresentationUnavailable(
                "Standard-native run manifest is unavailable"
            ) from error
        return document.get("schema_version") in {3, 4, 5, 6}

    def subject_hierarchy(
        self, session_id: str
    ) -> (
        StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
        | StandardNativeSubjectHierarchyV5
        | StandardNativeSubjectHierarchyV6
        | None
    ):
        loaded = self._load(session_id)
        return None if loaded is None else loaded.hierarchy

    def subject_detail(
        self, session_id: str, subject_id: str
    ) -> (
        StandardNativeSubjectDetailV3
        | StandardNativeSubjectDetailV4
        | StandardNativeSubjectDetailV5
        | StandardNativeSubjectDetailV6
        | None
    ):
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        paths = self._subject_paths(loaded, subject)
        trajectories = tuple(
            trajectory for path in paths for trajectory in _path_trajectories(path, paths)
        )
        stages = _stage_rows(loaded, subject, paths)
        descriptors = tuple(
            self._view_descriptor(loaded, subject, paths, kind) for kind in StandardViewKindV2
        )
        artifacts: list[NativeArtifactNameV3] = []
        if self._png_product(loaded, subject, WATERFALL_PNG_V2_PRODUCT.kind, 2) is not None:
            artifacts.append("waterfall")
        if (
            subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            and self._png_product(
                loaded,
                subject,
                ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT.kind,
                ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT.schema_version,
            )
            is not None
        ):
            artifacts.append("cfo-alternate")
        common = {
            "time_domain": _time_domain(paths),
            "receiver_path_evidence": tuple(_path_evidence(path) for path in paths),
            "stage_source_count": len(stages),
            "stages": stages[:256],
            "stages_truncated": len(stages) > 256,
            "trajectory_source_count": len(trajectories),
            "trajectories": trajectories[:256],
            "trajectories_truncated": len(trajectories) > 256,
            "views": descriptors,
            "available_artifacts": tuple(artifacts),
            "limitations": (
                "Candidate evidence only; source identity is unassessed; "
                "no payload recovery is claimed",
                "Stateful algorithms reset at every continuity boundary",
                "Power, quality, QAM, and opportunity reducers use valid samples "
                "and sufficient statistics",
                "Waterfall tiles retain the global device-time axis and mark missing cells invalid",
                "Paired-radio support is the intersection of valid UTC intervals",
            ),
        }
        if isinstance(subject, StandardNativeSubjectSummaryV6):
            expansions_v6 = cast(
                tuple[StandardNativeSubjectSummaryV6, ...],
                tuple(loaded.subjects[path.reference.subject_id] for path in paths),
            )
            return StandardNativeSubjectDetailV6.model_validate(
                {
                    "subject": subject,
                    "receiver_path_expansions": expansions_v6,
                    **common,
                }
            )
        if isinstance(subject, StandardNativeSubjectSummaryV5):
            expansions_v5 = cast(
                tuple[StandardNativeSubjectSummaryV5, ...],
                tuple(loaded.subjects[path.reference.subject_id] for path in paths),
            )
            return StandardNativeSubjectDetailV5.model_validate(
                {
                    "subject": subject,
                    "receiver_path_expansions": expansions_v5,
                    **common,
                }
            )
        if isinstance(subject, StandardNativeSubjectSummaryV4):
            expansions_v4 = cast(
                tuple[StandardNativeSubjectSummaryV4, ...],
                tuple(loaded.subjects[path.reference.subject_id] for path in paths),
            )
            return StandardNativeSubjectDetailV4.model_validate(
                {
                    "subject": subject,
                    "receiver_path_expansions": expansions_v4,
                    **common,
                }
            )
        expansions_v3 = cast(
            tuple[StandardNativeSubjectSummaryV3, ...],
            tuple(loaded.subjects[path.reference.subject_id] for path in paths),
        )
        return StandardNativeSubjectDetailV3.model_validate(
            {
                "subject": subject,
                "receiver_path_expansions": expansions_v3,
                **common,
            }
        )

    def subject_replay_audit(self, session_id: str, subject_id: str) -> None:
        del session_id, subject_id
        return None

    def subject_png_inventory(
        self,
        session_id: str,
        subject_id: str,
    ) -> (
        StandardNativePngArtifactInventoryV4
        | StandardNativePngArtifactInventoryV5
        | StandardNativePngArtifactInventoryV6
        | StandardNativePngArtifactInventoryV7
        | StandardNativePngArtifactInventoryV8
        | StandardNativePngArtifactInventoryV9
        | None
    ):
        """Return the complete sealed 11/5/5 artifact inventory, if present."""

        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        doppler_waterfall_present = (
            self._png_product(
                loaded,
                subject,
                DOPPLER_WATERFALL_PNG_V1_PRODUCT.kind,
                DOPPLER_WATERFALL_PNG_V1_PRODUCT.schema_version,
            )
            is not None
        )
        names = (
            (
                STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V8
                if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
                else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8
            )
            if doppler_waterfall_present
            else (
                STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V4
                if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
                else STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
            )
        )
        pilot_png_schema = _pilot_png_schema_version(loaded)
        if pilot_png_schema is None:
            return None
        product_specs = {
            "waterfall": WATERFALL_PNG_V2_PRODUCT,
            "doppler-waterfall": DOPPLER_WATERFALL_PNG_V1_PRODUCT,
            "pilot-methods": PILOT_METHODS_PNG_V2_PRODUCT,
            "cfo-raw": CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            "cfo-dealiased": DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            "cfo-final": FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            "cfo-alternate": ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,
            "trajectory-accounting": TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,
            "full-capture-glrt20ms": FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,
            "pilot-doppler": (
                PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT
                if pilot_png_schema == 4
                else PILOT_DOPPLER_SEGMENTS_PNG_V3_PRODUCT
            ),
            "pilot-carrier-tracking": (
                PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT
                if pilot_png_schema == 4
                else PILOT_CARRIER_TRACKING_PNG_V3_PRODUCT
            ),
            "pilot-segment-rates": (
                PILOT_SEGMENT_RATES_PNG_V4_PRODUCT
                if pilot_png_schema == 4
                else PILOT_SEGMENT_RATES_PNG_V3_PRODUCT
            ),
        }
        artifacts: list[StandardNativePngArtifactV4 | StandardNativePngArtifactV8] = []
        for name in names:
            spec = product_specs[name]
            product = self._png_product(loaded, subject, spec.kind, spec.schema_version)
            if product is None:
                return None
            artifact: StandardNativePngArtifactV4 | StandardNativePngArtifactV8
            if doppler_waterfall_present:
                label, description, kind, schema_version, view_name = (
                    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V8[name]
                )
            else:
                legacy_name = cast(StandardNativePngArtifactNameV4, name)
                legacy_definitions = (
                    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V7
                    if pilot_png_schema == 4
                    else STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4
                )
                label, description, kind, schema_version, view_name = legacy_definitions[
                    legacy_name
                ]
            base = (
                f"/api/v2/recordings/{quote(session_id, safe='')}/standard-subjects/"
                f"{quote(subject.subject_id, safe='')}"
            )
            href = (
                f"{base}/views/{view_name}.png"
                if view_name is not None
                else f"{base}/artifacts/{name}.png"
            )
            if doppler_waterfall_present:
                artifact = StandardNativePngArtifactV8(
                    name=name,
                    label=label,
                    description=description,
                    href=href,
                    catalog_kind=kind,
                    product_schema_version=schema_version,
                    digest=product.digest,
                    byte_size=product.byte_size,
                )
            else:
                artifact = StandardNativePngArtifactV4(
                    name=legacy_name,
                    label=label,
                    description=description,
                    href=href,
                    catalog_kind=kind,
                    product_schema_version=schema_version,
                    digest=product.digest,
                    byte_size=product.byte_size,
                )
            artifacts.append(artifact)
        common_values = {
            "session_id": session_id,
            "subject_id": subject.subject_id,
            "subject_kind": subject.subject_kind.value,
            "run_id": loaded.run_id,
            "run_manifest_digest": loaded.manifest_digest,
            "coverage_status": subject.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
        }
        if doppler_waterfall_present:
            if isinstance(subject, StandardNativeSubjectSummaryV6):
                direct_sample_rates_hz = cast(
                    tuple[Literal[2_500_000, 10_000_000, 15_000_000, 25_000_000], ...],
                    tuple(
                        sorted(
                            {
                                path.report.source.sample_rate_hz
                                for path in self._subject_paths(loaded, subject)
                            }
                        )
                    ),
                )
                content_values_v9 = {
                    "schema_version": 9,
                    **common_values,
                    "sample_rates_hz": direct_sample_rates_hz,
                }
                return StandardNativePngArtifactInventoryV9(
                    session_id=session_id,
                    subject_id=subject.subject_id,
                    subject_kind=subject.subject_kind,
                    run_id=loaded.run_id,
                    run_manifest_digest=loaded.manifest_digest,
                    sample_rates_hz=direct_sample_rates_hz,
                    coverage_status=subject.coverage_status,
                    artifacts=tuple(cast(StandardNativePngArtifactV8, item) for item in artifacts),
                    content_digest=canonical_digest(content_values_v9),
                )
            doppler_sample_rates_hz = cast(
                tuple[
                    Literal[
                        2_500_000,
                        3_000_000,
                        5_000_000,
                        10_000_000,
                        15_000_000,
                        20_000_000,
                    ],
                    ...,
                ],
                tuple(
                    sorted(
                        {
                            path.report.source.sample_rate_hz
                            for path in self._subject_paths(loaded, subject)
                        }
                    )
                ),
            )
            content_values_v8 = {
                "schema_version": 8,
                **common_values,
                "sample_rates_hz": doppler_sample_rates_hz,
            }
            return StandardNativePngArtifactInventoryV8(
                session_id=session_id,
                subject_id=subject.subject_id,
                subject_kind=subject.subject_kind,
                run_id=loaded.run_id,
                run_manifest_digest=loaded.manifest_digest,
                sample_rates_hz=doppler_sample_rates_hz,
                coverage_status=subject.coverage_status,
                artifacts=tuple(cast(StandardNativePngArtifactV8, item) for item in artifacts),
                content_digest=canonical_digest(content_values_v8),
            )
        if pilot_png_schema == 4:
            phase_sample_rates_hz = cast(
                tuple[
                    Literal[
                        2_500_000,
                        3_000_000,
                        5_000_000,
                        10_000_000,
                        15_000_000,
                        20_000_000,
                    ],
                    ...,
                ],
                tuple(
                    sorted(
                        {
                            path.report.source.sample_rate_hz
                            for path in self._subject_paths(loaded, subject)
                        }
                    )
                ),
            )
            content_values_v7 = {
                "schema_version": 7,
                **common_values,
                "sample_rates_hz": phase_sample_rates_hz,
            }
            return StandardNativePngArtifactInventoryV7(
                session_id=session_id,
                subject_id=subject.subject_id,
                subject_kind=subject.subject_kind,
                run_id=loaded.run_id,
                run_manifest_digest=loaded.manifest_digest,
                sample_rates_hz=phase_sample_rates_hz,
                coverage_status=subject.coverage_status,
                artifacts=tuple(cast(StandardNativePngArtifactV4, item) for item in artifacts),
                content_digest=canonical_digest(content_values_v7),
            )
        if isinstance(subject, StandardNativeSubjectSummaryV5):
            production_sample_rates_hz = cast(
                tuple[
                    Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000],
                    ...,
                ],
                tuple(
                    sorted(
                        {
                            path.report.source.sample_rate_hz
                            for path in self._subject_paths(loaded, subject)
                        }
                    )
                ),
            )
            content_values_v6 = {
                "schema_version": 6,
                **common_values,
                "sample_rates_hz": production_sample_rates_hz,
            }
            return StandardNativePngArtifactInventoryV6(
                session_id=session_id,
                subject_id=subject.subject_id,
                subject_kind=subject.subject_kind,
                run_id=loaded.run_id,
                run_manifest_digest=loaded.manifest_digest,
                sample_rates_hz=production_sample_rates_hz,
                coverage_status=subject.coverage_status,
                artifacts=tuple(cast(StandardNativePngArtifactV4, item) for item in artifacts),
                content_digest=canonical_digest(content_values_v6),
            )
        if isinstance(subject, StandardNativeSubjectSummaryV4):
            sample_rates_hz = cast(
                tuple[Literal[2_500_000, 5_000_000, 10_000_000], ...],
                tuple(
                    sorted(
                        {
                            path.report.source.sample_rate_hz
                            for path in self._subject_paths(loaded, subject)
                        }
                    )
                ),
            )
            content_values_v5 = {
                "schema_version": 5,
                **common_values,
                "sample_rates_hz": sample_rates_hz,
            }
            return StandardNativePngArtifactInventoryV5(
                session_id=session_id,
                subject_id=subject.subject_id,
                subject_kind=subject.subject_kind,
                run_id=loaded.run_id,
                run_manifest_digest=loaded.manifest_digest,
                sample_rates_hz=sample_rates_hz,
                coverage_status=subject.coverage_status,
                artifacts=tuple(cast(StandardNativePngArtifactV4, item) for item in artifacts),
                content_digest=canonical_digest(content_values_v5),
            )
        content_values = {
            "schema_version": 4,
            **common_values,
            "sample_rate_hz": subject.eligibility.sample_rate_hz,
        }
        return StandardNativePngArtifactInventoryV4(
            session_id=session_id,
            subject_id=subject.subject_id,
            subject_kind=subject.subject_kind,
            run_id=loaded.run_id,
            run_manifest_digest=loaded.manifest_digest,
            sample_rate_hz=subject.eligibility.sample_rate_hz,
            coverage_status=subject.coverage_status,
            artifacts=tuple(cast(StandardNativePngArtifactV4, item) for item in artifacts),
            content_digest=canonical_digest(content_values),
        )

    def subject_track_gate_audit(self, session_id: str, subject_id: str) -> None:
        del session_id, subject_id
        return None

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> (
        StandardNativePlotViewV3
        | StandardNativePlotViewV4
        | StandardNativePlotViewV5
        | StandardNativePlotViewV6
        | None
    ):
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        if not 4 <= maximum_points <= 2048:
            raise ValueError("maximum_points must be between 4 and 2,048")
        subject = loaded.subjects[subject_id]
        paths = self._subject_paths(loaded, subject)
        return _build_view(
            loaded,
            subject,
            paths,
            view_kind,
            maximum_points=maximum_points,
        )

    def verify_source_proof(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardNativeSourceProofV3,
    ) -> bool:
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return False
        subject = loaded.subjects[subject_id]
        paths = self._subject_paths(loaded, subject)
        return proof == _source_proof(loaded, paths, view_kind)

    def subject_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> bytes | None:
        product_spec = {
            StandardViewKindV2.WATERFALL: WATERFALL_PNG_V2_PRODUCT,
            StandardViewKindV2.GLRT64: PILOT_METHODS_PNG_V2_PRODUCT,
            StandardViewKindV2.CFO_TRAJECTORY: CFO_TRAJECTORIES_PNG_V2_PRODUCT,
        }.get(view_kind)
        if product_spec is None:
            return None
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        product = self._png_product(
            loaded,
            loaded.subjects[subject_id],
            product_spec.kind,
            product_spec.schema_version,
        )
        return (
            None
            if product is None
            else self._artifacts.read_bytes(product.logical_uri, product.digest)
        )

    def subject_named_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        artifact_name: str,
    ) -> bytes | None:
        product_specs = {
            "doppler-waterfall": (DOPPLER_WATERFALL_PNG_V1_PRODUCT,),
            "cfo-raw": (CFO_TRAJECTORIES_PNG_V2_PRODUCT,),
            "cfo-dealiased": (DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,),
            "cfo-final": (FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,),
            "cfo-alternate": (ALTERNATE_CFO_TRACKS_PNG_V3_PRODUCT,),
            "trajectory-accounting": (TRAJECTORY_CONDITIONED_ACCOUNTING_PNG_V3_PRODUCT,),
            "full-capture-glrt20ms": (FULL_CAPTURE_GLRT20MS_PNG_V2_PRODUCT,),
            "pilot-doppler": (
                PILOT_DOPPLER_SEGMENTS_PNG_V4_PRODUCT,
                PILOT_DOPPLER_SEGMENTS_PNG_V3_PRODUCT,
            ),
            "pilot-carrier-tracking": (
                PILOT_CARRIER_TRACKING_PNG_V4_PRODUCT,
                PILOT_CARRIER_TRACKING_PNG_V3_PRODUCT,
            ),
            "pilot-segment-rates": (
                PILOT_SEGMENT_RATES_PNG_V4_PRODUCT,
                PILOT_SEGMENT_RATES_PNG_V3_PRODUCT,
            ),
        }.get(artifact_name)
        if product_specs is None:
            return None
        loaded = self._load(session_id)
        if loaded is None or subject_id not in loaded.subjects:
            return None
        subject = loaded.subjects[subject_id]
        if (
            artifact_name not in {"doppler-waterfall", "cfo-raw", "cfo-dealiased", "cfo-final"}
            and subject.subject_kind is not StandardSubjectKindV2.RECEIVER_PATH
        ):
            return None
        product = next(
            (
                candidate
                for spec in product_specs
                if (
                    candidate := self._png_product(
                        loaded,
                        subject,
                        spec.kind,
                        spec.schema_version,
                    )
                )
                is not None
            ),
            None,
        )
        return (
            None
            if product is None
            else self._artifacts.read_bytes(product.logical_uri, product.digest)
        )

    @staticmethod
    def _subject_paths(
        loaded: _NativeProjection,
        subject: (
            StandardNativeSubjectSummaryV3
            | StandardNativeSubjectSummaryV4
            | StandardNativeSubjectSummaryV5
            | StandardNativeSubjectSummaryV6
        ),
    ) -> tuple[_NativePath, ...]:
        wanted = {item.path_id for item in subject.receiver_paths}
        return tuple(item for item in loaded.paths if item.reference.path_id in wanted)

    def _view_descriptor(
        self,
        loaded: _NativeProjection,
        subject: (
            StandardNativeSubjectSummaryV3
            | StandardNativeSubjectSummaryV4
            | StandardNativeSubjectSummaryV5
            | StandardNativeSubjectSummaryV6
        ),
        paths: tuple[_NativePath, ...],
        kind: StandardViewKindV2,
    ) -> StandardNativeViewDescriptorV3:
        count = _source_count(paths, kind)
        state = (
            StandardViewStateV2.UNAVAILABLE
            if not count
            else (
                StandardViewStateV2.PARTIAL
                if subject.coverage_status != "complete"
                else StandardViewStateV2.AVAILABLE
            )
        )
        png = self._png_product(
            loaded,
            subject,
            WATERFALL_PNG_V2_PRODUCT.kind,
            WATERFALL_PNG_V2_PRODUCT.schema_version,
        )
        png_available = kind is StandardViewKindV2.WATERFALL and png is not None
        base = (
            f"/api/v2/recordings/{loaded.snapshot.session_id}/"
            f"standard-subjects/{subject.subject_id}"
        )
        return StandardNativeViewDescriptorV3(
            view_kind=kind,
            state=state,
            href=f"{base}/views/{kind.value}",
            source_point_count=count,
            png_available=png_available,
            png_href=f"{base}/views/{kind.value}.png" if png_available else None,
            reason=(
                "No sealed terminal evidence is available for this native view"
                if not count
                else (
                    "Validity-aware native evidence is available with partial coverage"
                    if state is StandardViewStateV2.PARTIAL
                    else "Validity-aware native evidence is available"
                )
            ),
        )

    @staticmethod
    def _png_product(
        loaded: _NativeProjection,
        subject: (
            StandardNativeSubjectSummaryV3
            | StandardNativeSubjectSummaryV4
            | StandardNativeSubjectSummaryV5
            | StandardNativeSubjectSummaryV6
        ),
        kind: str,
        schema_version: int,
    ) -> CatalogProductRecord | None:
        matches = tuple(
            product
            for product in loaded.products
            if product.kind == kind
            and product.schema_version == schema_version
            and product.role == "presentation"
            and product.media_type == "image/png"
            and product.available
            and product.scope is not None
            and _scope_matches_subject(subject, product.scope)
        )
        if len(matches) > 1:
            raise StandardPresentationUnavailable(
                "sealed Standard-native run duplicates a presentation PNG"
            )
        return matches[0] if matches else None

    def _load(self, session_id: str) -> _NativeProjection | None:
        snapshot = self._catalog.presentation_snapshot(session_id)
        with self._projection_lock:
            cached = self._cached_projection
            if cached is not None and cached.snapshot == snapshot:
                return cached
            loaded = self._load_uncached(session_id, snapshot)
            self._cached_projection = loaded
            return loaded

    def _load_uncached(
        self,
        session_id: str,
        snapshot: CatalogSessionReadSnapshot | None,
    ) -> _NativeProjection | None:
        try:
            if snapshot is None or snapshot.analysis is None:
                return None
            analysis = snapshot.analysis
            if analysis.state in {"queued", "pending", "running"}:
                raise StandardPresentationNotReady(
                    "Standard-native analysis is still processing; "
                    "no sealed presentation is available"
                )
            if analysis.state != "succeeded":
                raise StandardPresentationUnavailable("Standard-native analysis did not succeed")
            if (
                snapshot.source_type.upper() != "LIVE"
                or snapshot.state not in {"committed", "degraded"}
                or not analysis.is_current
                or analysis.promotion_policy != "current"
                or analysis.pipeline_lane != "standard"
            ):
                raise StandardPresentationUnavailable(
                    "Standard-native presentation requires the exact Current LIVE run"
                )
            if (
                analysis.sealed_at is None
                or analysis.manifest_uri is None
                or analysis.manifest_digest is None
            ):
                raise StandardPresentationUnavailable("Standard-native run is not sealed")
            reference = self._catalog.run_manifest_reference(analysis.run_id)
            if (
                reference.logical_uri != analysis.manifest_uri
                or reference.digest != analysis.manifest_digest
            ):
                raise StandardPresentationUnavailable(
                    "Standard-native catalog manifest authority drifted"
                )
            parsed = parse_analysis_run_manifest(
                self._artifacts.read_json(reference.logical_uri, reference.digest)
            )
            if not isinstance(
                parsed,
                (
                    AnalysisRunManifestV3,
                    AnalysisRunManifestV4,
                    AnalysisRunManifestV5,
                    AnalysisRunManifestV6,
                ),
            ):
                return None
            execution = self._catalog.run_execution_info(analysis.run_id)
            seal = self._catalog.run_seal_snapshot(analysis.run_id)
            if (
                parsed.run_id != analysis.run_id
                or parsed.session_id != session_id
                or parsed.pipeline_release_id != analysis.pipeline_release_id
                or parsed.input_manifest_digest != analysis.input_manifest_digest
                or execution.session_id != session_id
                or execution.pipeline_lane != "standard"
                or execution.promotion_policy != "current"
                or execution.code_revision != execution.pipeline_release_id
            ):
                raise StandardPresentationUnavailable("Standard-native sealed run identity drifted")
            _require_seal_inventory(parsed, seal.jobs, seal.products)
            definition = standard_native_pipeline_definition_v1(
                executable_git_sha=execution.code_revision,
                graph_digest=execution.graph_digest,
                configuration_digest=execution.configuration_digest,
            )
            authority = parsed.promotion_authority
            if authority.pipeline_definition != definition:
                raise StandardPresentationUnavailable(
                    "Standard-native promotion used a foreign pipeline definition"
                )
            release = StandardNativePipelineReleaseV3(
                authoritative_pipeline_release_id=execution.pipeline_release_id,
                source_revision=execution.code_revision,
                pipeline_definition_id=definition.definition_id,
                graph_digest=execution.graph_digest,
                configuration_digest=execution.configuration_digest,
                environment_digest=execution.environment_digest,
            )
            terminal_ids = {item.product_id for item in authority.terminal_products}
            terminal_products = tuple(
                item for item in seal.products if item.product_id in terminal_ids
            )
            path_products = (
                *_products_of(
                    terminal_products,
                    PATH_REPORT_V3_PRODUCT.kind,
                    PATH_REPORT_V3_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    PATH_REPORT_V4_PRODUCT.kind,
                    PATH_REPORT_V4_PRODUCT.schema_version,
                ),
            )
            radio_products = (
                *_products_of(
                    terminal_products,
                    RADIO_REPORT_V4_PRODUCT.kind,
                    RADIO_REPORT_V4_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    RADIO_REPORT_V5_PRODUCT.kind,
                    RADIO_REPORT_V5_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    RADIO_REPORT_V6_PRODUCT.kind,
                    RADIO_REPORT_V6_PRODUCT.schema_version,
                ),
            )
            paired_products = (
                *_products_of(
                    terminal_products,
                    PAIRED_REPORT_V4_PRODUCT.kind,
                    PAIRED_REPORT_V4_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    PAIRED_REPORT_V5_PRODUCT.kind,
                    PAIRED_REPORT_V5_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    PAIRED_REPORT_V6_PRODUCT.kind,
                    PAIRED_REPORT_V6_PRODUCT.schema_version,
                ),
                *_products_of(
                    terminal_products,
                    PAIRED_REPORT_V7_PRODUCT.kind,
                    PAIRED_REPORT_V7_PRODUCT.schema_version,
                ),
            )
            if not path_products or not radio_products or len(paired_products) > 1:
                raise StandardPresentationUnavailable(
                    "Standard-native terminal product inventory is incomplete"
                )
            radio_documents = tuple(
                sorted(
                    (
                        (
                            product,
                            _load_terminal_radio_report(
                                product,
                                self._artifacts.read_json(product.logical_uri, product.digest),
                            ),
                        )
                        for product in radio_products
                    ),
                    key=lambda item: (item[1].stream_id, item[1].radio_id),
                )
            )
            paired = (
                None
                if not paired_products
                else (
                    paired_products[0],
                    (
                        StandardNativePairedReportV7.model_validate(
                            self._artifacts.read_json(
                                paired_products[0].logical_uri,
                                paired_products[0].digest,
                            )
                        )
                        if paired_products[0].schema_version == 7
                        else (
                            StandardNativePairedReportV6.model_validate(
                                self._artifacts.read_json(
                                    paired_products[0].logical_uri,
                                    paired_products[0].digest,
                                )
                            )
                            if paired_products[0].schema_version == 6
                            else (
                                StandardNativePairedReportV5.model_validate(
                                    self._artifacts.read_json(
                                        paired_products[0].logical_uri,
                                        paired_products[0].digest,
                                    )
                                )
                                if paired_products[0].schema_version == 5
                                else StandardNativePairedReportV4.model_validate(
                                    self._artifacts.read_json(
                                        paired_products[0].logical_uri,
                                        paired_products[0].digest,
                                    )
                                )
                            )
                        )
                    ),
                )
            )
            paths = tuple(
                self._load_path(
                    analysis.run_id,
                    product,
                    seal.products,
                    radio_documents,
                )
                for product in path_products
            )
            paths = _normalize_path_labels(
                tuple(
                    sorted(
                        paths,
                        key=lambda item: (item.binding.stream_id, item.binding.receiver_id),
                    )
                )
            )
            capture_state: Literal["committed", "degraded"] = (
                "degraded"
                if any(item.report.source.missing_sample_count for item in paths)
                else "committed"
            )
            if isinstance(parsed, AnalysisRunManifestV6):
                authority_v4 = parsed.promotion_authority
                direct_legs = cast(
                    tuple[StandardNativeProductionLegV6, StandardNativeProductionLegV6],
                    tuple(
                        StandardNativeProductionLegV6.model_validate(
                            {
                                "schema_version": 6,
                                **item.model_dump(mode="json", exclude={"schema_version"}),
                            }
                        )
                        for item in authority_v4.stream_authorities
                    ),
                )
                eligibility: (
                    StandardNativeEligibilityV3
                    | StandardNativeEligibilityV4
                    | StandardNativeEligibilityV5
                    | StandardNativeEligibilityV6
                ) = StandardNativeEligibilityV6(
                    capture_state=capture_state,
                    capture_committed=capture_state == "committed",
                    dwell_class=authority_v4.dwell_class,
                    tuning_branch=authority_v4.tuning_branch,
                    legs=direct_legs,
                    scheduled_intent_digest=authority_v4.scheduled_intent_digest,
                    capture_plan_digest=authority_v4.capture_plan_digest,
                    capture_hardware_binding_digest=authority_v4.capture_hardware_binding_digest,
                    pipeline_definition_id=definition.definition_id,
                    promotion_authority_digest=authority_v4.content_digest,
                    reason=(
                        "Promoted reviewed production Standard-native capture is Current"
                        if capture_state == "committed"
                        else (
                            "Promoted reviewed production Standard-native capture is Current "
                            "with partial validity coverage"
                        )
                    ),
                )
            elif isinstance(parsed, AnalysisRunManifestV5):
                authority_v3 = parsed.promotion_authority
                production_legs = cast(
                    tuple[StandardNativeProductionLegV5, StandardNativeProductionLegV5],
                    tuple(
                        StandardNativeProductionLegV5.model_validate(
                            {
                                "schema_version": 5,
                                **item.model_dump(mode="json", exclude={"schema_version"}),
                            }
                        )
                        for item in authority_v3.stream_authorities
                    ),
                )
                eligibility = StandardNativeEligibilityV5(
                    capture_state=capture_state,
                    capture_committed=capture_state == "committed",
                    dwell_class=authority_v3.dwell_class,
                    tuning_branch=authority_v3.tuning_branch,
                    legs=production_legs,
                    scheduled_intent_digest=authority_v3.scheduled_intent_digest,
                    capture_plan_digest=authority_v3.capture_plan_digest,
                    capture_hardware_binding_digest=authority_v3.capture_hardware_binding_digest,
                    pipeline_definition_id=definition.definition_id,
                    promotion_authority_digest=authority_v3.content_digest,
                    reason=(
                        "Promoted reviewed production Standard-native capture is Current"
                        if capture_state == "committed"
                        else (
                            "Promoted reviewed production Standard-native capture is Current "
                            "with partial validity coverage"
                        )
                    ),
                )
            elif isinstance(parsed, AnalysisRunManifestV4):
                authority_v2 = parsed.promotion_authority
                mixed_legs = cast(
                    tuple[StandardNativeMixedLegV4, StandardNativeMixedLegV4],
                    tuple(
                        StandardNativeMixedLegV4(
                            stream_id=item.stream_id,
                            radio_id=item.radio_id,
                            profile_name=item.profile_name,
                            profile_revision_digest=item.profile_revision_digest,
                            starlink_channel=item.starlink_channel,
                            starlink_edge=item.starlink_edge,
                            sample_rate_hz=item.sample_rate_hz,
                            rf_bandwidth_hz=cast(
                                Literal[2_500_000, 5_000_000, 10_000_000],
                                item.rf_bandwidth_hz,
                            ),
                            tuned_center_frequency_hz=item.tuned_center_frequency_hz,
                            pilot_if_center_frequency_hz=item.pilot_if_center_frequency_hz,
                            channel_if_start_hz=item.channel_if_start_hz,
                            channel_if_stop_hz=item.channel_if_stop_hz,
                            captured_if_start_hz=item.captured_if_start_hz,
                            captured_if_stop_hz=item.captured_if_stop_hz,
                        )
                        for item in authority_v2.stream_authorities
                    ),
                )
                eligibility = StandardNativeEligibilityV4(
                    capture_state=capture_state,
                    capture_committed=capture_state == "committed",
                    dwell_class=authority_v2.dwell_class,
                    legs=mixed_legs,
                    pipeline_definition_id=definition.definition_id,
                    promotion_authority_digest=authority_v2.content_digest,
                    reason=(
                        "Promoted reviewed mixed Standard-native capture is Current"
                        if capture_state == "committed"
                        else (
                            "Promoted reviewed mixed Standard-native capture is Current "
                            "with partial validity coverage"
                        )
                    ),
                )
            else:
                authority_v1 = parsed.promotion_authority
                eligibility = StandardNativeEligibilityV3(
                    capture_state=capture_state,
                    capture_committed=capture_state == "committed",
                    profile_revision_digest=authority_v1.profile_revision_digest,
                    sample_rate_hz=authority_v1.sample_rate_hz,
                    pipeline_definition_id=definition.definition_id,
                    promotion_authority_digest=authority_v1.content_digest,
                    reason=(
                        "Promoted reviewed V3 Standard-native capture is Current"
                        if capture_state == "committed"
                        else (
                            "Promoted reviewed V3 Standard-native capture is Current with partial "
                            "validity coverage"
                        )
                    ),
                )
            _require_terminal_topology(paths, radio_documents, paired)
            hierarchy, subjects = _hierarchy(
                snapshot,
                analysis.sealed_at,
                release,
                eligibility,
                paths,
                radio_documents,
                paired,
            )
            return _NativeProjection(
                snapshot=snapshot,
                run_id=analysis.run_id,
                manifest_digest=analysis.manifest_digest,
                manifest=parsed,
                release=release,
                eligibility=eligibility,
                paths=paths,
                radios=radio_documents,
                paired=paired,
                jobs=seal.jobs,
                products=seal.products,
                hierarchy=hierarchy,
                subjects=subjects,
            )
        except (StandardPresentationNotReady, StandardPresentationUnavailable):
            raise
        except Exception as error:
            raise StandardPresentationUnavailable(
                "Standard-native presentation authority or artifact is unavailable"
            ) from error

    def _load_path(
        self,
        run_id: str,
        product: CatalogProductRecord,
        products: tuple[CatalogProductRecord, ...],
        radios: tuple[tuple[CatalogProductRecord, _TerminalRadioReport], ...],
    ) -> _NativePath:
        scope = product.scope
        if scope is None or scope.kind is not ScopeKind.RECEIVER_PATH:
            raise StandardPresentationUnavailable("native path report lacks a typed path scope")
        binding_document = self._catalog.run_subject_binding(run_id, scope).document
        binding = (
            StandardPathInputBindV5.model_validate(binding_document)
            if binding_document.get("schema_version") == 5
            else StandardPathInputBindV4.model_validate(binding_document)
        )
        report_document = self._artifacts.read_json(product.logical_uri, product.digest)
        report = (
            StandardNativePathReportV4.model_validate(report_document)
            if product.schema_version == PATH_REPORT_V4_PRODUCT.schema_version
            else StandardNativePathReportV3.model_validate(report_document)
        )
        if (
            report.source.path_input_binding_digest != binding.binding_digest
            or report.source.session_id != scope.session_id
            or report.source.stream_id != scope.stream_id
            or report.source.receiver_id != scope.receiver_id
        ):
            raise StandardPresentationUnavailable("native path report source binding drifted")
        terminals = tuple(
            path
            for _, radio in radios
            for path in radio.paths
            if path.source.path_input_binding_digest == binding.binding_digest
        )
        if len(terminals) != 1 or terminals[0].path_report != report:
            raise StandardPresentationUnavailable(
                "native path report is not closed by one terminal radio reducer"
            )
        wideband = isinstance(report, StandardNativePathReportV4)
        power_spec = POWER_TIMELINE_V4_PRODUCT if wideband else POWER_TIMELINE_V3_PRODUCT
        waterfall_spec = (
            NUMERICAL_WATERFALL_V4_PRODUCT if wideband else NUMERICAL_WATERFALL_V3_PRODUCT
        )
        glrt_spec = (
            FULL_CAPTURE_GLRT20MS_V2_PRODUCT if wideband else FULL_CAPTURE_GLRT20MS_V1_PRODUCT
        )
        power_product = _one_scoped_product(
            products,
            scope,
            power_spec.kind,
            power_spec.schema_version,
        )
        waterfall_product = _one_scoped_product(
            products,
            scope,
            waterfall_spec.kind,
            waterfall_spec.schema_version,
        )
        glrt_product = _one_scoped_product(
            products,
            scope,
            glrt_spec.kind,
            glrt_spec.schema_version,
        )
        if (
            power_product.digest != report.products.power_timeline_product_digest
            or waterfall_product.digest != report.products.numerical_waterfall_product_digest
            or glrt_product.digest != report.products.full_capture_glrt20ms_product_digest
        ):
            raise StandardPresentationUnavailable(
                "native path source products differ from its terminal digest closure"
            )
        power_document = self._artifacts.read_json(power_product.logical_uri, power_product.digest)
        waterfall_document = self._artifacts.read_json(
            waterfall_product.logical_uri, waterfall_product.digest
        )
        glrt_document = self._artifacts.read_json(glrt_product.logical_uri, glrt_product.digest)
        power = (
            StandardNativePowerTimelineV4.model_validate(power_document)
            if wideband
            else StandardNativePowerTimelineV3.model_validate(power_document)
        )
        waterfall = (
            StandardNativeNumericalWaterfallV4.model_validate(waterfall_document)
            if wideband
            else StandardNativeNumericalWaterfallV3.model_validate(waterfall_document)
        )
        glrt = (
            StandardNativeFullCaptureGlrt20msV2.model_validate(glrt_document)
            if wideband
            else StandardNativeFullCaptureGlrt20msV1.model_validate(glrt_document)
        )
        if (
            power.source != report.source
            or waterfall.source != report.source
            or glrt.source != report.source
        ):
            raise StandardPresentationUnavailable(
                "native path view products cross source authority"
            )
        path_id = f"{binding.radio_id}:rx{binding.receiver_id}"
        return _NativePath(
            product=product,
            binding=binding,
            report=report,
            terminal=terminals[0],
            power_product=power_product,
            power=power,
            waterfall_product=waterfall_product,
            waterfall=waterfall,
            glrt_product=glrt_product,
            glrt=glrt,
            reference=StandardReceiverPathRefV2(
                subject_id=f"path:{path_id}",
                path_id=path_id,
                radio_id=binding.radio_id,
                radio_label="Radio0",
                receiver_id=binding.receiver_id,
                receiver_label=f"RX{binding.receiver_id}",
                scope=scope,
                scope_digest=scope.canonical_digest.removeprefix("sha256:"),
            ),
        )


def _require_seal_inventory(
    manifest: (
        AnalysisRunManifestV3
        | AnalysisRunManifestV4
        | AnalysisRunManifestV5
        | AnalysisRunManifestV6
    ),
    jobs: tuple[CatalogJobRecord, ...],
    products: tuple[CatalogProductRecord, ...],
) -> None:
    manifest_products = {
        (
            item.product_id,
            item.stage_key,
            item.scope_key,
            item.kind,
            item.product_schema_version,
            item.role,
            item.status,
            item.media_type,
            item.logical_uri,
            item.digest,
            item.byte_size,
            item.coverage,
        )
        for item in manifest.products
    }
    catalog_products = {
        (
            item.product_id,
            item.stage_key,
            item.scope_key,
            item.kind,
            item.schema_version,
            item.role,
            item.status,
            item.media_type,
            item.logical_uri,
            item.digest,
            item.byte_size,
            item.coverage,
        )
        for item in products
    }
    manifest_jobs = {
        (item.job_id, item.stage_key, item.scope_key, item.outcome) for item in manifest.jobs
    }
    catalog_jobs = {(item.job_id, item.stage_key, item.scope_key, item.outcome) for item in jobs}
    if manifest_products != catalog_products or manifest_jobs != catalog_jobs:
        raise StandardPresentationUnavailable("Standard-native sealed inventory drifted")
    if any(item.state != "succeeded" for item in jobs):
        raise StandardPresentationUnavailable("Standard-native sealed run has a nonterminal job")


def _products_of(
    products: tuple[CatalogProductRecord, ...], kind: str, schema_version: int
) -> tuple[CatalogProductRecord, ...]:
    return tuple(
        item
        for item in products
        if item.kind == kind
        and item.schema_version == schema_version
        and item.role == "scientific"
        and item.available
    )


def _load_terminal_radio_report(
    product: CatalogProductRecord,
    document: dict[str, Any],
) -> _TerminalRadioReport:
    if product.schema_version == RADIO_REPORT_V6_PRODUCT.schema_version:
        return StandardNativeRadioReportV6.model_validate(document)
    if product.schema_version == RADIO_REPORT_V5_PRODUCT.schema_version:
        return StandardNativeRadioReportV5.model_validate(document)
    if product.schema_version == RADIO_REPORT_V4_PRODUCT.schema_version:
        return StandardNativeRadioReportV4.model_validate(document)
    raise StandardPresentationUnavailable("unsupported Standard-native radio report schema")


def _one_scoped_product(
    products: tuple[CatalogProductRecord, ...],
    scope: ScopeIdentityV1,
    kind: str,
    schema_version: int,
) -> CatalogProductRecord:
    matches = tuple(
        item
        for item in products
        if item.kind == kind
        and item.schema_version == schema_version
        and item.role == "scientific"
        and item.available
        and item.scope == scope
    )
    if len(matches) != 1:
        raise StandardPresentationUnavailable(
            f"Standard-native run lacks one exact {kind} source product"
        )
    return matches[0]


def _require_terminal_topology(
    paths: tuple[_NativePath, ...],
    radios: tuple[tuple[CatalogProductRecord, _TerminalRadioReport], ...],
    paired: tuple[CatalogProductRecord, _TerminalPairedReport] | None,
) -> None:
    if len(paths) != len({item.binding.binding_digest for item in paths}) or len(paths) > 4:
        raise StandardPresentationUnavailable("native path inventory is duplicated or unbounded")
    streams = {item.binding.stream_id for item in paths}
    if {item.stream_id for _, item in radios} != streams or len(radios) != len(streams):
        raise StandardPresentationUnavailable("native radio reducer inventory is incomplete")
    if len(streams) == 2:
        if paired is None or paired[1].radios != tuple(item for _, item in radios):
            raise StandardPresentationUnavailable("native paired terminal reducer is incomplete")
    elif len(streams) != 1 or paired is not None:
        raise StandardPresentationUnavailable("native terminal topology is invalid")


def _hierarchy(
    snapshot: CatalogSessionReadSnapshot,
    generated_at: datetime,
    release: StandardNativePipelineReleaseV3,
    eligibility: (
        StandardNativeEligibilityV3
        | StandardNativeEligibilityV4
        | StandardNativeEligibilityV5
        | StandardNativeEligibilityV6
    ),
    paths: tuple[_NativePath, ...],
    radio_documents: tuple[tuple[CatalogProductRecord, _TerminalRadioReport], ...],
    paired: tuple[CatalogProductRecord, _TerminalPairedReport] | None,
) -> tuple[
    StandardNativeSubjectHierarchyV3
    | StandardNativeSubjectHierarchyV4
    | StandardNativeSubjectHierarchyV5
    | StandardNativeSubjectHierarchyV6,
    dict[
        str,
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6,
    ],
]:
    streams = tuple(sorted({item.binding.stream_id for item in paths}))
    labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}

    def summary(
        *,
        subject_id: str,
        kind: StandardSubjectKindV2,
        label: str,
        selected: tuple[_NativePath, ...],
        children: tuple[str, ...],
        terminal: StandardNativeTerminalSummaryV3,
    ) -> (
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6
    ):
        values = dict(
            subject_id=subject_id,
            session_id=snapshot.session_id,
            subject_kind=kind,
            label=label,
            derived=kind is not StandardSubjectKindV2.RECEIVER_PATH,
            receiver_paths=tuple(item.reference for item in selected),
            expected_path_count=len(selected),
            completed_path_count=len(selected),
            child_subject_ids=children,
            coverage_status=terminal.coverage_status,
            scientific_disposition=terminal.scientific_disposition,
            pipeline_release=release,
            desired_pipeline_release_id=release.authoritative_pipeline_release_id,
            reuse=StandardReuseSummaryV2(
                computed_stage_count=1,
                reused_stage_count=0,
                recompute_stage_count=0,
                reason="Rendered for this run",
            ),
            terminal=terminal,
        )
        if isinstance(eligibility, StandardNativeEligibilityV6):
            return StandardNativeSubjectSummaryV6.model_validate(
                {"eligibility": eligibility, **values}
            )
        if isinstance(eligibility, StandardNativeEligibilityV5):
            return StandardNativeSubjectSummaryV5.model_validate(
                {"eligibility": eligibility, **values}
            )
        if isinstance(eligibility, StandardNativeEligibilityV4):
            return StandardNativeSubjectSummaryV4.model_validate(
                {"eligibility": eligibility, **values}
            )
        return StandardNativeSubjectSummaryV3.model_validate({"eligibility": eligibility, **values})

    path_subjects = tuple(
        summary(
            subject_id=path.reference.subject_id,
            kind=StandardSubjectKindV2.RECEIVER_PATH,
            label=f"{path.reference.radio_label} {path.reference.receiver_label}",
            selected=(path,),
            children=(),
            terminal=_path_terminal_summary(path),
        )
        for path in paths
    )
    radio_subjects = tuple(
        summary(
            subject_id=f"radio:{report.stream_id}",
            kind=StandardSubjectKindV2.RADIO,
            label=labels[report.stream_id],
            selected=tuple(item for item in paths if item.binding.stream_id == report.stream_id),
            children=tuple(
                item.reference.subject_id
                for item in paths
                if item.binding.stream_id == report.stream_id
            ),
            terminal=_aggregate_terminal_summary(report),
        )
        for _, report in radio_documents
    )
    subjects: tuple[
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6,
        ...,
    ] = (
        *path_subjects,
        *radio_subjects,
    )
    rows: tuple[
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6,
        ...,
    ]
    if paired is not None:
        pair_report = paired[1]
        pair = summary(
            subject_id=f"pair:{streams[0]}:{streams[1]}",
            kind=StandardSubjectKindV2.PAIRED,
            label="Paired Radio0 + Radio1",
            selected=paths,
            children=tuple(item.subject_id for item in radio_subjects),
            terminal=_aggregate_terminal_summary(pair_report),
        )
        rows = (pair, *radio_subjects)
        subjects = (*subjects, pair)
    else:
        rows = radio_subjects
    hierarchy: (
        StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
        | StandardNativeSubjectHierarchyV5
        | StandardNativeSubjectHierarchyV6
    )
    if isinstance(eligibility, StandardNativeEligibilityV6):
        hierarchy = StandardNativeSubjectHierarchyV6(
            session_id=snapshot.session_id,
            eligibility=eligibility,
            generated_at=generated_at,
            rows=cast(tuple[StandardNativeSubjectSummaryV6, ...], rows),
        )
    elif isinstance(eligibility, StandardNativeEligibilityV5):
        hierarchy = StandardNativeSubjectHierarchyV5(
            session_id=snapshot.session_id,
            eligibility=eligibility,
            generated_at=generated_at,
            rows=cast(tuple[StandardNativeSubjectSummaryV5, ...], rows),
        )
    elif isinstance(eligibility, StandardNativeEligibilityV4):
        hierarchy = StandardNativeSubjectHierarchyV4(
            session_id=snapshot.session_id,
            eligibility=eligibility,
            generated_at=generated_at,
            rows=cast(tuple[StandardNativeSubjectSummaryV4, ...], rows),
        )
    else:
        hierarchy = StandardNativeSubjectHierarchyV3(
            session_id=snapshot.session_id,
            eligibility=eligibility,
            generated_at=generated_at,
            rows=cast(tuple[StandardNativeSubjectSummaryV3, ...], rows),
        )
    return hierarchy, {item.subject_id: item for item in subjects}


def _path_statistics(quality: NativeQualityReceiverV2) -> NativeSufficientStatisticsV1:
    assert quality.minimum_i is not None
    assert quality.maximum_i is not None
    assert quality.minimum_q is not None
    assert quality.maximum_q is not None
    return NativeSufficientStatisticsV1(
        receiver_path_count=1,
        valid_complex_sample_count=quality.valid_sample_count,
        energy_sum_ci16_squared=quality.energy_sum_ci16_squared,
        clipped_component_count=quality.clipped_component_count,
        clipped_complex_sample_count=quality.clipped_complex_sample_count,
        clipped_complex_fraction=quality.clipped_complex_fraction,
        mean_power_full_scale_squared=(
            quality.energy_sum_ci16_squared / (quality.valid_sample_count * 32768**2)
        ),
        constant_iq=quality.constant_iq,
        minimum_i=quality.minimum_i,
        maximum_i=quality.maximum_i,
        minimum_q=quality.minimum_q,
        maximum_q=quality.maximum_q,
    )


def _path_terminal_summary(path: _NativePath) -> StandardNativeTerminalSummaryV3:
    source = path.report.source
    return StandardNativeTerminalSummaryV3(
        expected_complex_sample_count=source.logical_sample_count,
        valid_complex_sample_count=source.observed_sample_count,
        missing_complex_sample_count=source.missing_sample_count,
        coverage_fraction=source.observed_sample_count / source.logical_sample_count,
        coverage_status=path.terminal.stage_outcome,
        sufficient_statistics=_path_statistics(path.terminal.quality),
        terminal_opportunities=path.report.schedule_execution.accounting,
        qam_statistics=path.report.qam_statistics,
        terminal_tracks=terminal_track_accounting(path.report),
        scientific_disposition=path.report.scientific_disposition,
        valid_utc_intervals=path.terminal.valid_utc_intervals,
    )


def _aggregate_terminal_summary(
    report: _TerminalRadioReport | _TerminalPairedReport,
) -> StandardNativeTerminalSummaryV3:
    sources = (
        tuple(item.source for item in report.paths)
        if isinstance(
            report,
            (StandardNativeRadioReportV4, StandardNativeRadioReportV5, StandardNativeRadioReportV6),
        )
        else tuple(path.source for radio in report.radios for path in radio.paths)
    )
    expected = sum(item.logical_sample_count for item in sources)
    valid = report.aggregate_statistics.valid_complex_sample_count
    return StandardNativeTerminalSummaryV3(
        expected_complex_sample_count=expected,
        valid_complex_sample_count=valid,
        missing_complex_sample_count=expected - valid,
        coverage_fraction=valid / expected,
        coverage_status=report.status,
        sufficient_statistics=report.aggregate_statistics,
        terminal_opportunities=report.aggregate_terminal_opportunities,
        qam_statistics=report.aggregate_qam_statistics,
        terminal_tracks=report.aggregate_terminal_tracks,
        scientific_disposition=report.scientific_disposition,
        valid_utc_intervals=report.valid_utc_intervals,
    )


def _normalize_path_labels(paths: tuple[_NativePath, ...]) -> tuple[_NativePath, ...]:
    streams = tuple(sorted({item.binding.stream_id for item in paths}))
    labels = {stream: f"Radio{index}" for index, stream in enumerate(streams)}
    return tuple(
        _NativePath(
            product=item.product,
            binding=item.binding,
            report=item.report,
            terminal=item.terminal,
            power_product=item.power_product,
            power=item.power,
            waterfall_product=item.waterfall_product,
            waterfall=item.waterfall,
            glrt_product=item.glrt_product,
            glrt=item.glrt,
            reference=item.reference.model_copy(
                update={"radio_label": labels[item.binding.stream_id]}
            ),
        )
        for item in paths
    )


def _time_domain(paths: tuple[_NativePath, ...]) -> StandardTimeDomainV2:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    last = max(item.binding.timing.last_estimate_utc_ns for item in paths)
    uncertainty_ns = max(
        max(
            item.binding.timing.first_estimate_utc_ns - item.binding.timing.first_earliest_utc_ns,
            item.binding.timing.first_latest_utc_ns - item.binding.timing.first_estimate_utc_ns,
            item.binding.timing.last_estimate_utc_ns - item.binding.timing.last_earliest_utc_ns,
            item.binding.timing.last_latest_utc_ns - item.binding.timing.last_estimate_utc_ns,
        )
        for item in paths
    )
    return StandardTimeDomainV2(
        absolute_start_utc=datetime.fromtimestamp(first / 1_000_000_000, UTC),
        absolute_end_utc=datetime.fromtimestamp(last / 1_000_000_000, UTC),
        elapsed_end_s=(last - first) / 1_000_000_000,
        timing_uncertainty_s=uncertainty_ns / 1_000_000_000 + 1e-6,
    )


def _path_offset_s(path: _NativePath, paths: tuple[_NativePath, ...]) -> float:
    first = min(item.binding.timing.first_estimate_utc_ns for item in paths)
    return (path.binding.timing.first_estimate_utc_ns - first) / 1_000_000_000


def _path_evidence(path: _NativePath) -> StandardNativePathEvidenceV3:
    source = path.report.source
    rate = source.sample_rate_hz
    return StandardNativePathEvidenceV3(
        receiver_path=path.reference,
        terminal=_path_terminal_summary(path),
        declared_seconds=source.logical_sample_count / rate,
        valid_seconds=source.observed_sample_count / rate,
        continuity_segment_count=len(source.continuity_segments),
        continuity_boundary_count=len(source.continuity_segments) - 1,
    )


def _path_trajectories(
    path: _NativePath, all_paths: tuple[_NativePath, ...]
) -> tuple[StandardNativeTrajectoryV3, ...]:
    offset = _path_offset_s(path, all_paths)
    rows: list[StandardNativeTrajectoryV3] = []
    for segment in path.report.segments:
        segment_offset = offset + (
            segment.continuity_segment.device_sample_start / path.binding.sample_rate_hz
        )
        for trajectory in segment.final_trajectories:
            rows.append(
                StandardNativeTrajectoryV3(
                    receiver_path_id=path.reference.path_id,
                    continuity_segment_index=segment.continuity_segment.segment_index,
                    trajectory_id=trajectory.trajectory_id,
                    start_s=segment_offset + trajectory.start_s,
                    end_s=segment_offset + trajectory.end_s,
                    reference_time_s=segment_offset + trajectory.reference_time_s,
                    polynomial_degree=trajectory.polynomial_degree,
                    absolute_coefficients_hz=trajectory.absolute_coefficients_hz,
                    support_count=len(trajectory.observation_ids),
                    automatic_correction_eligible=trajectory.automatic_correction_eligible,
                    replay_tier=trajectory.replay_tier.value,
                )
            )
    return tuple(rows)


def _stage_rows(
    loaded: _NativeProjection,
    subject: (
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6
    ),
    paths: tuple[_NativePath, ...],
) -> tuple[StandardStageStatusV2, ...]:
    path_scopes = {item.reference.scope.canonical_digest for item in paths}
    stream_ids = {item.binding.stream_id for item in paths}
    rows = []
    for job in loaded.jobs:
        scope = job.scope
        if scope is None:
            continue
        if scope.kind is ScopeKind.RECEIVER_PATH and scope.canonical_digest not in path_scopes:
            continue
        if scope.kind is ScopeKind.RADIO and (
            subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH
            or scope.stream_id not in stream_ids
        ):
            continue
        if (
            scope.kind is ScopeKind.PAIRED
            and subject.subject_kind is not StandardSubjectKindV2.PAIRED
        ):
            continue
        output = next(
            (
                item.digest
                for item in loaded.products
                if item.stage_key == job.stage_key and item.scope_key == job.scope_key
            ),
            None,
        )
        rows.append(
            native_stage_status_v3(
                stage_key=job.stage_key,
                subject_id=subject.subject_id,
                output_digest=output,
            )
        )
    return tuple(rows)


def _source_count(paths: tuple[_NativePath, ...], kind: StandardViewKindV2) -> int:
    if kind is StandardViewKindV2.QUALITY:
        return len(paths)
    if kind is StandardViewKindV2.POWER:
        return sum(len(item.power.timeline.timeline) for item in paths)
    if kind is StandardViewKindV2.WATERFALL:
        return sum(len(item.waterfall.waterfall.tiles) for item in paths)
    if kind is StandardViewKindV2.GLRT64:
        return sum(len(segment.windows) for item in paths for segment in item.glrt.segments)
    if kind is StandardViewKindV2.QAM:
        return 2 * sum(item.report.qam_statistics.qam_result_count for item in paths)
    return sum(
        segment.returned_trajectory_count for item in paths for segment in item.report.segments
    )


def _source_products(
    paths: tuple[_NativePath, ...], kind: StandardViewKindV2
) -> tuple[CatalogProductRecord, ...]:
    if kind is StandardViewKindV2.POWER:
        return tuple(item.power_product for item in paths)
    if kind is StandardViewKindV2.WATERFALL:
        return tuple(item.waterfall_product for item in paths)
    if kind is StandardViewKindV2.GLRT64:
        return tuple(item.glrt_product for item in paths)
    return tuple(item.product for item in paths)


def _source_proof(
    loaded: _NativeProjection,
    paths: tuple[_NativePath, ...],
    kind: StandardViewKindV2,
) -> StandardNativeSourceProofV3:
    references = tuple(
        sorted(
            (
                StandardNativePresentationProductRefV3(
                    product_id=item.product_id,
                    scope_key=item.scope_key,
                    kind=item.kind,
                    product_schema_version=item.schema_version,
                    digest=item.digest,
                )
                for item in _source_products(paths, kind)
            ),
            key=lambda item: (item.scope_key, item.kind, item.product_schema_version),
        )
    )
    values = {
        "schema_version": 3,
        "run_manifest_digest": loaded.manifest_digest,
        "products": tuple(item.model_dump(mode="json") for item in references),
    }
    return StandardNativeSourceProofV3(
        run_manifest_digest=loaded.manifest_digest,
        products=references,
        content_digest=canonical_digest(values),
    )


def _build_view(
    loaded: _NativeProjection,
    subject: (
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6
    ),
    paths: tuple[_NativePath, ...],
    kind: StandardViewKindV2,
    *,
    maximum_points: int,
) -> (
    StandardNativePlotViewV3
    | StandardNativePlotViewV4
    | StandardNativePlotViewV5
    | StandardNativePlotViewV6
):
    source_count = _source_count(paths, kind)
    state = (
        StandardViewStateV2.UNAVAILABLE
        if not source_count
        else (
            StandardViewStateV2.PARTIAL
            if subject.coverage_status != "complete"
            else StandardViewStateV2.AVAILABLE
        )
    )
    series: tuple[StandardNativeMetricSeriesV3, ...] = ()
    frequencies: tuple[float, ...] = ()
    frequency_axes: tuple[StandardNativeFrequencyAxisV4 | StandardNativeFrequencyAxisV5, ...] = ()
    tiles: tuple[StandardNativeWaterfallTileV3 | StandardNativeWaterfallTileV4, ...] = ()
    trajectories: tuple[StandardNativeTrajectoryV3, ...] = ()
    if kind is StandardViewKindV2.WATERFALL:
        if isinstance(
            subject,
            (
                StandardNativeSubjectSummaryV4,
                StandardNativeSubjectSummaryV5,
                StandardNativeSubjectSummaryV6,
            ),
        ):
            frequency_axes, tiles = _mixed_waterfall_payload(
                paths,
                wide=isinstance(subject, StandardNativeSubjectSummaryV6),
            )
        else:
            frequencies, tiles = _waterfall_payload(paths)
        if len(tiles) > 2048:
            raise StandardPresentationUnavailable("native waterfall global time axis is unbounded")
    elif kind is StandardViewKindV2.CFO_TRAJECTORY:
        all_trajectories = tuple(row for path in paths for row in _path_trajectories(path, paths))
        trajectories = all_trajectories[: min(maximum_points, 256)]
    else:
        series = _metric_payload(paths, kind, maximum_points)
    returned = sum(len(item.points) for item in series) + len(tiles) + len(trajectories)
    common_values: dict[str, Any] = {
        "session_id": loaded.snapshot.session_id,
        "subject_id": subject.subject_id,
        "view_kind": kind.value,
        "state": state.value,
        "time_domain": _time_domain(paths).model_dump(mode="json"),
        "receiver_path_ids": tuple(item.reference.path_id for item in paths),
        "source_proof": _source_proof(loaded, paths, kind).model_dump(mode="json"),
        "source_point_count": source_count,
        "returned_point_count": returned,
        "truncated": source_count > returned,
        "metric_series": tuple(item.model_dump(mode="json") for item in series),
        "waterfall_tiles": tuple(item.model_dump(mode="json") for item in tiles),
        "trajectories": tuple(item.model_dump(mode="json") for item in trajectories),
        "reason": (
            "No sealed terminal evidence is available for this native view"
            if not source_count
            else "Validity-aware native evidence projected without resampling"
        ),
    }
    if isinstance(subject, StandardNativeSubjectSummaryV6):
        values_v6: dict[str, Any] = {
            "schema_version": 6,
            **common_values,
            "sample_rates_hz": tuple(sorted({item.report.source.sample_rate_hz for item in paths})),
            "frequency_axes": tuple(item.model_dump(mode="json") for item in frequency_axes),
        }
        return StandardNativePlotViewV6.model_validate(
            {**values_v6, "projection_digest": canonical_digest(values_v6)}
        )
    if isinstance(subject, StandardNativeSubjectSummaryV5):
        values_v5: dict[str, Any] = {
            "schema_version": 5,
            **common_values,
            "sample_rates_hz": tuple(sorted({item.report.source.sample_rate_hz for item in paths})),
            "frequency_axes": tuple(item.model_dump(mode="json") for item in frequency_axes),
        }
        return StandardNativePlotViewV5.model_validate(
            {**values_v5, "projection_digest": canonical_digest(values_v5)}
        )
    if isinstance(subject, StandardNativeSubjectSummaryV4):
        values_v4: dict[str, Any] = {
            "schema_version": 4,
            **common_values,
            "sample_rates_hz": tuple(sorted({item.report.source.sample_rate_hz for item in paths})),
            "frequency_axes": tuple(item.model_dump(mode="json") for item in frequency_axes),
        }
        return StandardNativePlotViewV4.model_validate(
            {**values_v4, "projection_digest": canonical_digest(values_v4)}
        )
    if not isinstance(loaded.eligibility, StandardNativeEligibilityV3):
        raise StandardPresentationUnavailable("native plot eligibility major is crossed")
    values: dict[str, Any] = {
        "schema_version": 3,
        **common_values,
        "sample_rate_hz": loaded.eligibility.sample_rate_hz,
        "frequency_bin_centers_hz": frequencies,
    }
    return StandardNativePlotViewV3.model_validate(
        {**values, "projection_digest": canonical_digest(values)}
    )


def _metric_payload(
    paths: tuple[_NativePath, ...], kind: StandardViewKindV2, maximum_points: int
) -> tuple[StandardNativeMetricSeriesV3, ...]:
    raw: list[tuple[str, str, str, str, StandardNativeMetricPointV3]] = []
    for path in paths:
        lane = path.reference.path_id
        offset = _path_offset_s(path, paths)
        if kind is StandardViewKindV2.QUALITY:
            raw.append(
                (
                    lane,
                    "clipped",
                    "Clipped sample fraction",
                    "fraction",
                    StandardNativeMetricPointV3(
                        time_s=offset,
                        value=path.terminal.quality.clipped_complex_fraction,
                        valid=True,
                    ),
                )
            )
        elif kind is StandardViewKindV2.POWER:
            for power_window in path.power.timeline.timeline:
                raw.append(
                    (
                        lane,
                        "power",
                        "Window power",
                        "dBFS",
                        StandardNativeMetricPointV3(
                            time_s=offset
                            + (power_window.time_start_s + power_window.time_stop_s) / 2,
                            value=power_window.mean_power_dbfs,
                            valid=power_window.mean_power_dbfs is not None,
                        ),
                    )
                )
        elif kind is StandardViewKindV2.GLRT64:
            for segment in path.glrt.segments:
                for window in segment.windows:
                    raw.append(
                        (
                            lane,
                            "glrt64",
                            "GLRT64 detector response",
                            "response",
                            StandardNativeMetricPointV3(
                                time_s=offset + window.global_center_time_s,
                                value=window.glrt_exact_score,
                                valid=window.glrt_exact_score is not None,
                            ),
                        )
                    )
        elif kind is StandardViewKindV2.QAM:
            for probe_execution in path.report.schedule_execution.opportunities:
                qam = probe_execution.qam
                if qam is None or qam.statistics.qam_result_count == 0:
                    continue
                assert qam.statistics.hard_symbol_accuracy is not None
                assert qam.statistics.rms_evm is not None
                time_s = offset + probe_execution.opportunity.probe.time_s
                raw.extend(
                    (
                        (
                            lane,
                            "qam-accuracy",
                            "Known-pilot QAM accuracy",
                            "accuracy",
                            StandardNativeMetricPointV3(
                                time_s=time_s,
                                value=float(qam.statistics.hard_symbol_accuracy),
                                valid=True,
                            ),
                        ),
                        (
                            lane,
                            "qam-evm",
                            "Known-pilot QAM RMS EVM",
                            "EVM",
                            StandardNativeMetricPointV3(
                                time_s=time_s,
                                value=float(qam.statistics.rms_evm),
                                valid=True,
                            ),
                        ),
                    )
                )
    grouped: dict[tuple[str, str, str, str], list[StandardNativeMetricPointV3]] = {}
    for lane, series_id, label, unit, point in raw:
        grouped.setdefault((lane, series_id, label, unit), []).append(point)
    if not grouped:
        return ()
    per_series = max(1, maximum_points // len(grouped))
    values = []
    for (lane, series_id, label, unit), points in grouped.items():
        selected = _evenly_spaced(tuple(points), per_series)
        values.append(
            StandardNativeMetricSeriesV3(
                series_id=f"{lane}:{series_id}",
                receiver_path_id=lane,
                label=label,
                unit=unit,  # type: ignore[arg-type]
                source_point_count=len(points),
                points=selected,
                truncated=len(selected) < len(points),
            )
        )
    return tuple(values)


def _waterfall_payload(
    paths: tuple[_NativePath, ...],
) -> tuple[tuple[float, ...], tuple[StandardNativeWaterfallTileV3, ...]]:
    axes = {item.waterfall.waterfall.frequency_bin_centers_hz for item in paths}
    if len(axes) != 1:
        raise StandardPresentationUnavailable("native waterfall frequency axes disagree")
    frequencies = next(iter(axes))
    rows: list[StandardNativeWaterfallTileV3] = []
    for path in paths:
        waterfall = path.waterfall.waterfall
        offset = _path_offset_s(path, paths)
        for tile in waterfall.tiles:
            powers = tile.receiver_power_dbfs[0]
            rows.append(
                StandardNativeWaterfallTileV3(
                    receiver_path_id=path.reference.path_id,
                    time_bin=tile.time_bin,
                    time_start_s=offset + tile.sample_start / path.binding.sample_rate_hz,
                    time_stop_s=offset + tile.sample_stop / path.binding.sample_rate_hz,
                    sample_start=tile.sample_start,
                    sample_stop=tile.sample_stop,
                    transform_count=tile.transform_count,
                    valid=tile.transform_count > 0,
                    power_dbfs=powers,
                )
            )
    return frequencies, tuple(rows)


def _mixed_waterfall_payload(
    paths: tuple[_NativePath, ...],
    *,
    wide: bool,
) -> tuple[
    tuple[StandardNativeFrequencyAxisV4 | StandardNativeFrequencyAxisV5, ...],
    tuple[StandardNativeWaterfallTileV3 | StandardNativeWaterfallTileV4, ...],
]:
    axis_model = StandardNativeFrequencyAxisV5 if wide else StandardNativeFrequencyAxisV4
    tile_model = StandardNativeWaterfallTileV4 if wide else StandardNativeWaterfallTileV3
    maximum_frequency_bins = 4096 if wide else 1024
    projected_axes = {
        path.reference.path_id: _frequency_projection_indexes(
            len(path.waterfall.waterfall.frequency_bin_centers_hz),
            maximum=maximum_frequency_bins,
        )
        for path in paths
    }
    axes = tuple(
        axis_model(
            receiver_path_id=path.reference.path_id,
            frequency_bin_centers_hz=tuple(
                path.waterfall.waterfall.frequency_bin_centers_hz[index]
                for index in projected_axes[path.reference.path_id]
            ),
        )
        for path in paths
    )
    rows: list[StandardNativeWaterfallTileV3 | StandardNativeWaterfallTileV4] = []
    for path in paths:
        waterfall = path.waterfall.waterfall
        offset = _path_offset_s(path, paths)
        for tile in waterfall.tiles:
            rows.append(
                tile_model(
                    receiver_path_id=path.reference.path_id,
                    time_bin=tile.time_bin,
                    time_start_s=offset + tile.sample_start / path.binding.sample_rate_hz,
                    time_stop_s=offset + tile.sample_stop / path.binding.sample_rate_hz,
                    sample_start=tile.sample_start,
                    sample_stop=tile.sample_stop,
                    transform_count=tile.transform_count,
                    valid=tile.transform_count > 0,
                    power_dbfs=tuple(
                        tile.receiver_power_dbfs[0][index]
                        for index in projected_axes[path.reference.path_id]
                    ),
                )
            )
    return axes, tuple(rows)


def _frequency_projection_indexes(source_count: int, *, maximum: int) -> tuple[int, ...]:
    """Select a deterministic contract-bounded view without altering analysis products."""

    if source_count <= maximum:
        return tuple(range(source_count))
    last = source_count - 1
    return tuple(round(index * last / (maximum - 1)) for index in range(maximum))


def _evenly_spaced[ValueT](values: tuple[ValueT, ...], maximum: int) -> tuple[ValueT, ...]:
    if len(values) <= maximum:
        return values
    if maximum <= 1:
        return values[:1]
    last = len(values) - 1
    indexes = tuple(round(index * last / (maximum - 1)) for index in range(maximum))
    return tuple(values[index] for index in indexes)


def _scope_matches_subject(
    subject: (
        StandardNativeSubjectSummaryV3
        | StandardNativeSubjectSummaryV4
        | StandardNativeSubjectSummaryV5
        | StandardNativeSubjectSummaryV6
    ),
    scope: ScopeIdentityV1,
) -> bool:
    if subject.subject_kind is StandardSubjectKindV2.RECEIVER_PATH:
        return scope == subject.receiver_paths[0].scope
    if subject.subject_kind is StandardSubjectKindV2.RADIO:
        return scope.kind is ScopeKind.RADIO and scope.stream_id in {
            item.scope.stream_id for item in subject.receiver_paths
        }
    return scope.kind is ScopeKind.PAIRED


def validate_standard_native_view_binding(
    detail: (
        StandardNativeSubjectDetailV3
        | StandardNativeSubjectDetailV4
        | StandardNativeSubjectDetailV5
        | StandardNativeSubjectDetailV6
    ),
    view: (
        StandardNativePlotViewV3
        | StandardNativePlotViewV4
        | StandardNativePlotViewV5
        | StandardNativePlotViewV6
    ),
) -> None:
    expected_lanes = tuple(item.path_id for item in detail.subject.receiver_paths)
    if (
        view.session_id != detail.subject.session_id
        or view.subject_id != detail.subject.subject_id
        or view.receiver_path_ids != expected_lanes
        or view.time_domain != detail.time_domain
    ):
        raise ValueError("native plot does not match its selected subject detail")
    if isinstance(detail, StandardNativeSubjectDetailV6):
        if not isinstance(view, StandardNativePlotViewV6):
            raise ValueError("direct-async native plot schema does not match its detail")
        streams = {item.scope.stream_id for item in detail.subject.receiver_paths}
        expected_rates_v6 = tuple(
            sorted(
                {
                    item.sample_rate_hz
                    for item in detail.subject.eligibility.legs
                    if item.stream_id in streams
                }
            )
        )
        if view.sample_rates_hz != expected_rates_v6:
            raise ValueError("direct-async native plot rates do not match its detail")
    elif isinstance(detail, StandardNativeSubjectDetailV5):
        if not isinstance(view, StandardNativePlotViewV5):
            raise ValueError("production native plot schema does not match its detail")
        streams = {item.scope.stream_id for item in detail.subject.receiver_paths}
        expected_rates_v5 = tuple(
            sorted(
                {
                    item.sample_rate_hz
                    for item in detail.subject.eligibility.legs
                    if item.stream_id in streams
                }
            )
        )
        if view.sample_rates_hz != expected_rates_v5:
            raise ValueError("production native plot rates do not match its detail")
    elif isinstance(detail, StandardNativeSubjectDetailV4):
        if not isinstance(view, StandardNativePlotViewV4):
            raise ValueError("mixed native plot schema does not match its detail")
        streams = {item.scope.stream_id for item in detail.subject.receiver_paths}
        expected_rates_v4 = tuple(
            sorted(
                {
                    item.sample_rate_hz
                    for item in detail.subject.eligibility.legs
                    if item.stream_id in streams
                }
            )
        )
        if view.sample_rates_hz != expected_rates_v4:
            raise ValueError("mixed native plot rates do not match its detail")
    elif (
        not isinstance(view, StandardNativePlotViewV3)
        or view.sample_rate_hz != detail.subject.eligibility.sample_rate_hz
    ):
        raise ValueError("native plot sample rate does not match its detail")


class DefinitionDispatchedStandardPresentationRepository:
    """Select the immutable projector from the sealed run-manifest major."""

    def __init__(
        self,
        standard_v2: CatalogStandardPresentationRepository,
        standard_native_v3: CatalogStandardNativePresentationRepository,
    ) -> None:
        self._standard_v2 = standard_v2
        self._standard_native_v3 = standard_native_v3

    def _native(self, session_id: str) -> bool:
        return self._standard_native_v3.recognizes_native_current(session_id)

    def subject_hierarchy(
        self, session_id: str
    ) -> (
        StandardSubjectHierarchyV2
        | StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
        | StandardNativeSubjectHierarchyV5
        | StandardNativeSubjectHierarchyV6
        | None
    ):
        if self._native(session_id):
            return self._standard_native_v3.subject_hierarchy(session_id)
        return self._standard_v2.subject_hierarchy(session_id)

    def subject_detail(
        self, session_id: str, subject_id: str
    ) -> (
        StandardSubjectDetailV2
        | StandardNativeSubjectDetailV3
        | StandardNativeSubjectDetailV4
        | StandardNativeSubjectDetailV5
        | StandardNativeSubjectDetailV6
        | None
    ):
        if self._native(session_id):
            return self._standard_native_v3.subject_detail(session_id, subject_id)
        return self._standard_v2.subject_detail(session_id, subject_id)

    def subject_replay_audit(
        self, session_id: str, subject_id: str
    ) -> StandardReplayAuditV1 | None:
        if self._native(session_id):
            return None
        return self._standard_v2.subject_replay_audit(session_id, subject_id)

    def subject_track_gate_audit(
        self, session_id: str, subject_id: str
    ) -> StandardTrackGateAuditV1 | None:
        if self._native(session_id):
            return None
        return self._standard_v2.subject_track_gate_audit(session_id, subject_id)

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> (
        StandardPlotViewV2
        | StandardNativePlotViewV3
        | StandardNativePlotViewV4
        | StandardNativePlotViewV5
        | StandardNativePlotViewV6
        | None
    ):
        target = self._standard_native_v3 if self._native(session_id) else self._standard_v2
        return target.subject_view(
            session_id,
            subject_id,
            view_kind,
            maximum_points=maximum_points,
        )

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool:
        if self._native(session_id):
            return False
        return self._standard_v2.verify_source_extrema(session_id, subject_id, view_kind, proof)

    def verify_source_proof(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardNativeSourceProofV3,
    ) -> bool:
        if not self._native(session_id):
            return False
        return self._standard_native_v3.verify_source_proof(
            session_id, subject_id, view_kind, proof
        )

    def subject_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> bytes | None:
        target = self._standard_native_v3 if self._native(session_id) else self._standard_v2
        return target.subject_png_artifact(session_id, subject_id, view_kind)

    def subject_png_inventory(
        self,
        session_id: str,
        subject_id: str,
    ) -> (
        StandardNativePngArtifactInventoryV4
        | StandardNativePngArtifactInventoryV5
        | StandardNativePngArtifactInventoryV6
        | StandardNativePngArtifactInventoryV7
        | StandardNativePngArtifactInventoryV8
        | StandardNativePngArtifactInventoryV9
        | None
    ):
        if not self._native(session_id):
            return None
        return self._standard_native_v3.subject_png_inventory(session_id, subject_id)

    def subject_named_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        artifact_name: str,
    ) -> bytes | None:
        target = self._standard_native_v3 if self._native(session_id) else self._standard_v2
        return target.subject_named_png_artifact(session_id, subject_id, artifact_name)
