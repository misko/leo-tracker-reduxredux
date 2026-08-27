"""FastAPI application exposing presentation data and narrow operator actions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Response
from fastapi import Path as ApiPath
from fastapi.staticfiles import StaticFiles

from leo.acquisition import CaptureAuthorityError
from leo.api.artifacts import RegisteredArtifactError, RegisteredArtifactResolver
from leo.application.capture_control import OperatorCaptureControl
from leo.application.research_reprocess import (
    AnalysisControlStatusV2,
    ResearchReprocessor,
    ResearchReprocessResultV1,
)
from leo.application.sky_field import (
    DEFAULT_DOWNLINK_FREQUENCY_HZ,
    SkyFieldService,
    SkyFieldUnavailableError,
)
from leo.application.sky_views import SkyViewService
from leo.application.standard_native_presentation import validate_standard_native_view_binding
from leo.application.standard_presentation import (
    StandardPresentationNotReady,
    StandardPresentationUnavailable,
)
from leo.application.standard_reprocess import (
    StandardReprocessError,
    StandardReprocessor,
    StandardReprocessResultV1,
)
from leo.contracts.capture_control import CaptureControlStateV1
from leo.contracts.sky import (
    MAXIMUM_REPORT_OBJECTS,
    SKY_WINDOW_HALF_WIDTH_S,
    BeamPointingV1,
    ObserverSiteV1,
    SkyFieldReportV1,
    SkyWindowV1,
)
from leo.operations.tle_archive import PROVIDERS, TleArchiveError
from leo.presentation.models import (
    AcquisitionQueueV1,
    ActiveQueueV1,
    AnalysisProductV1,
    AnalysisStateV1,
    AnalysisSummaryV1,
    ProductContentV1,
    QualificationCampaignDetailV1,
    QualificationCampaignListV1,
    RecordingDetailV1,
    RecordingRadioSetupV2,
    RecordingSearchResponseV1,
    StorageStateV1,
    SystemStatusV1,
)
from leo.presentation.repository import PresentationRepository
from leo.presentation.scanner import (
    ScannerAnalysisReader,
    ScannerHistoryPageV1,
    ScannerHistoryPageV2,
    ScannerHistoryPageV3,
    ScannerReportStore,
)
from leo.presentation.sky import (
    MAXIMUM_DOWNLINK_FREQUENCY_HZ,
    MAXIMUM_GLOBE_OBJECTS,
    MAXIMUM_LISTED_SNAPSHOTS,
    MAXIMUM_VIEW_SAMPLES,
    GlobeFrameSetV1,
    SkySiteListV1,
    SkySnapshotListV1,
    SkyViewFrameSetV1,
    SkyViewObjectDetailV1,
    SkyViewTleComparisonV1,
    TleArchiveListV1,
    site_list,
    snapshot_list,
)
from leo.presentation.standard_investigation import (
    StandardInvestigationGalleryV1,
    StandardInvestigationStore,
)
from leo.presentation.standard_native_artifacts import (
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactInventoryV5,
)
from leo.presentation.standard_native_pipeline import (
    StandardNativePlotViewV3,
    StandardNativePlotViewV4,
    StandardNativeSubjectDetailV3,
    StandardNativeSubjectDetailV4,
    StandardNativeSubjectHierarchyV3,
    StandardNativeSubjectHierarchyV4,
)
from leo.presentation.standard_native_repository import (
    DefinitionDispatchedStandardPresentationPort,
)
from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardReplayAuditV1,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardTrackGateAuditV1,
    StandardViewKindV2,
)
from leo.presentation.standard_repository import (
    StandardPresentationRepository,
    validate_standard_view_binding,
)
from leo.scanner import (
    ScannerAnalysisHistoryPageV1,
    ScannerAnalysisHistoryPageV2,
    ScannerAnalysisHistoryPageV3,
    ScannerCaptureReportLike,
    ScannerReport,
    ScannerReportLike,
    ScannerReportV2,
    ScannerReportV3,
)


def create_app(
    repository: PresentationRepository,
    *,
    artifact_root: Path,
    sky_service: SkyFieldService | None = None,
    sky_archive_root: Path | None = None,
    static_directory: Path | None = None,
    standard_repository: (
        StandardPresentationRepository | DefinitionDispatchedStandardPresentationPort | None
    ) = None,
    research_repository: StandardPresentationRepository | None = None,
    standard_reprocessor: StandardReprocessor | None = None,
    research_reprocessor: ResearchReprocessor | None = None,
    scanner_reports: ScannerReportStore | None = None,
    scanner_analyses: ScannerAnalysisReader | None = None,
    capture_control: OperatorCaptureControl | None = None,
) -> FastAPI:
    """Create presentation routes and an optional explicit reprocess action."""

    app = FastAPI(
        title="Leo Tracker Operator UI",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    resolver = RegisteredArtifactResolver(artifact_root)
    standard_investigations = StandardInvestigationStore(artifact_root)
    router = APIRouter(prefix="/api/v1")
    v2_router = APIRouter(prefix="/api/v2")
    v3_router = APIRouter(prefix="/api/v3")

    @router.api_route(
        "/recordings",
        methods=["GET", "HEAD"],
        response_model=RecordingSearchResponseV1,
    )
    def recordings(
        query: Annotated[str | None, Query(max_length=160)] = None,
        include_test: bool = False,
        analysis_state: AnalysisStateV1 | None = None,
        storage_state: StorageStateV1 | None = None,
        held: bool | None = None,
        tag: Annotated[str | None, Query(max_length=80)] = None,
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> RecordingSearchResponseV1:
        return repository.search_recordings(
            query=query,
            include_test=include_test,
            analysis_state=analysis_state,
            storage_state=storage_state,
            held=held,
            tag=tag,
            cursor=cursor,
            limit=limit,
        )

    @router.api_route(
        "/recordings/{session_id}",
        methods=["GET", "HEAD"],
        response_model=RecordingDetailV1,
    )
    def recording_detail(session_id: str) -> RecordingDetailV1:
        detail = repository.recording_detail(session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="recording not found")
        return detail

    @router.api_route(
        "/recordings/{session_id}/analysis/current",
        methods=["GET", "HEAD"],
        response_model=AnalysisSummaryV1,
    )
    def current_analysis(session_id: str) -> AnalysisSummaryV1:
        detail = repository.recording_detail(session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="recording not found")
        return detail.analysis

    @router.api_route(
        "/products/{product_id}",
        methods=["GET", "HEAD"],
        response_model=AnalysisProductV1,
    )
    def product(product_id: str) -> AnalysisProductV1:
        registered = repository.product(product_id)
        if registered is None:
            raise HTTPException(status_code=404, detail="analysis product not found")
        return registered

    @router.api_route(
        "/products/{product_id}/content",
        methods=["GET", "HEAD"],
        response_model=ProductContentV1,
    )
    def product_content(
        product_id: str,
        maximum_points: Annotated[int, Query(ge=1, le=2048)] = 512,
    ) -> ProductContentV1:
        registered = repository.product(product_id)
        if registered is None:
            raise HTTPException(status_code=404, detail="analysis product not found")
        if registered.kind not in {"waterfall", "overlays"}:
            raise HTTPException(status_code=409, detail="product has no bounded plot content")
        try:
            return resolver.content(registered, maximum_points)
        except RegisteredArtifactError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.api_route(
        "/status",
        methods=["GET", "HEAD"],
        response_model=SystemStatusV1,
    )
    def status() -> SystemStatusV1:
        return repository.status()

    @router.api_route("/queue", methods=["GET", "HEAD"], response_model=ActiveQueueV1)
    def active_queue(
        limit: Annotated[int, Query(ge=1, le=200)] = 200,
    ) -> ActiveQueueV1:
        return repository.active_queue(limit=limit)

    @router.api_route(
        "/acquisition-queue", methods=["GET", "HEAD"], response_model=AcquisitionQueueV1
    )
    def acquisition_queue(
        limit: Annotated[int, Query(ge=1, le=200)] = 200,
    ) -> AcquisitionQueueV1:
        return repository.acquisition_queue(limit=limit)

    def capture_control_service() -> OperatorCaptureControl:
        if capture_control is None:
            raise HTTPException(status_code=503, detail="capture control is unavailable")
        return capture_control

    def capture_control_result(
        operation: Callable[[], CaptureControlStateV1],
    ) -> CaptureControlStateV1:
        try:
            return operation()
        except (CaptureAuthorityError, OSError) as error:
            raise HTTPException(status_code=503, detail="capture control is unavailable") from error

    @router.api_route(
        "/capture-control",
        methods=["GET", "HEAD"],
        response_model=CaptureControlStateV1,
    )
    def capture_control_status() -> CaptureControlStateV1:
        service = capture_control_service()
        return capture_control_result(service.status)

    @router.post(
        "/capture-control/stop",
        response_model=CaptureControlStateV1,
    )
    def stop_capture() -> CaptureControlStateV1:
        service = capture_control_service()
        return capture_control_result(service.stop)

    @router.post(
        "/capture-control/start",
        response_model=CaptureControlStateV1,
    )
    def start_capture() -> CaptureControlStateV1:
        service = capture_control_service()
        return capture_control_result(service.start)

    @router.api_route(
        "/scanner/latest",
        methods=["GET", "HEAD"],
        response_model=ScannerReport,
    )
    def latest_scanner_report() -> ScannerReport:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        try:
            report = scanner_reports.latest()
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="scanner report is unavailable") from error
        if report is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        return report

    @router.api_route(
        "/scanner/reports",
        methods=["GET", "HEAD"],
        response_model=ScannerHistoryPageV1,
    )
    def scanner_report_history(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerHistoryPageV1:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report history is not available")
        try:
            return scanner_reports.page(cursor=cursor, limit=limit)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=409, detail="scanner report page is unavailable"
            ) from error

    @v2_router.api_route(
        "/scanner/latest",
        methods=["GET", "HEAD"],
        response_model=ScannerReport | ScannerReportV2,
    )
    def latest_scanner_report_v2() -> ScannerReportLike:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        try:
            report = scanner_reports.latest_v2()
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="scanner report is unavailable") from error
        if report is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        return report

    @v2_router.api_route(
        "/scanner/reports",
        methods=["GET", "HEAD"],
        response_model=ScannerHistoryPageV2,
    )
    def scanner_report_history_v2(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerHistoryPageV2:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report history is not available")
        try:
            return scanner_reports.page_v2(cursor=cursor, limit=limit)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=409, detail="scanner report page is unavailable"
            ) from error

    @v3_router.api_route(
        "/scanner/latest",
        methods=["GET", "HEAD"],
        response_model=ScannerReport | ScannerReportV2 | ScannerReportV3,
    )
    def latest_scanner_report_v3() -> ScannerCaptureReportLike:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        try:
            report = scanner_reports.latest_v3()
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=503, detail="scanner report is unavailable") from error
        if report is None:
            raise HTTPException(status_code=404, detail="scanner report is not available")
        return report

    @v3_router.api_route(
        "/scanner/reports",
        methods=["GET", "HEAD"],
        response_model=ScannerHistoryPageV3,
    )
    def scanner_report_history_v3(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerHistoryPageV3:
        if scanner_reports is None:
            raise HTTPException(status_code=404, detail="scanner report history is not available")
        try:
            return scanner_reports.page_v3(cursor=cursor, limit=limit)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=409, detail="scanner report page is unavailable"
            ) from error

    @router.api_route(
        "/scanner/analyses",
        methods=["GET", "HEAD"],
        response_model=ScannerAnalysisHistoryPageV1,
    )
    def scanner_analysis_history(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerAnalysisHistoryPageV1:
        if scanner_analyses is None:
            raise HTTPException(status_code=404, detail="scanner analysis history is not available")
        try:
            return scanner_analyses.page(cursor=cursor, limit=limit)
        except Exception as error:
            raise HTTPException(
                status_code=409, detail="scanner analysis page is unavailable"
            ) from error

    @v2_router.api_route(
        "/scanner/analyses",
        methods=["GET", "HEAD"],
        response_model=ScannerAnalysisHistoryPageV2,
    )
    def scanner_analysis_history_v2(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerAnalysisHistoryPageV2:
        if scanner_analyses is None:
            raise HTTPException(status_code=404, detail="scanner analysis history is not available")
        try:
            return scanner_analyses.page_v2(cursor=cursor, limit=limit)
        except Exception as error:
            raise HTTPException(
                status_code=409, detail="scanner analysis page is unavailable"
            ) from error

    @v3_router.api_route(
        "/scanner/analyses",
        methods=["GET", "HEAD"],
        response_model=ScannerAnalysisHistoryPageV3,
    )
    def scanner_analysis_history_v3(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ScannerAnalysisHistoryPageV3:
        if scanner_analyses is None:
            raise HTTPException(status_code=404, detail="scanner analysis history is not available")
        try:
            return scanner_analyses.page_v3(cursor=cursor, limit=limit)
        except Exception as error:
            raise HTTPException(
                status_code=409, detail="scanner analysis page is unavailable"
            ) from error

    @router.api_route(
        "/scanner/analyses/{scan_id}/{analysis_id}/{artifact}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def scanner_analysis_png(
        scan_id: str,
        analysis_id: str,
        artifact: Literal[
            "waterfall",
            "glrt64",
            "pilot-doppler",
            "pilot-carrier-tracking",
            "pilot-segment-rates",
        ],
    ) -> Response:
        if scanner_analyses is None:
            raise HTTPException(status_code=404, detail="scanner analysis is not available")
        try:
            content = scanner_analyses.artifact(scan_id, analysis_id, artifact)
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="scanner analysis artifact is unavailable"
            ) from error
        if content is None:
            raise HTTPException(status_code=404, detail="scanner analysis is not available")
        return Response(
            content=content,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="scanner-{artifact}.png"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "artifact",
            },
        )

    @router.api_route(
        "/qualification/campaigns",
        methods=["GET", "HEAD"],
        response_model=QualificationCampaignListV1,
    )
    def qualification_campaigns(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=25)] = 10,
    ) -> QualificationCampaignListV1:
        return repository.qualification_campaigns(cursor=cursor, limit=limit)

    @router.api_route(
        "/qualification/campaigns/{campaign_id}",
        methods=["GET", "HEAD"],
        response_model=QualificationCampaignDetailV1,
    )
    def qualification_campaign(campaign_id: str) -> QualificationCampaignDetailV1:
        campaign = repository.qualification_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="qualification campaign not found")
        return campaign

    app.include_router(router)
    app.include_router(v2_router)
    app.include_router(v3_router)

    standard_router = APIRouter(prefix="/api/v2")

    @standard_router.api_route(
        "/recordings/{session_id}/radio-setup",
        methods=["GET", "HEAD"],
        response_model=RecordingRadioSetupV2,
    )
    def recording_radio_setup(session_id: str) -> RecordingRadioSetupV2:
        try:
            setup = repository.recording_radio_setup(session_id)
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="recording setup projection is invalid",
            ) from error
        if setup is None:
            raise HTTPException(status_code=404, detail="recording setup not found")
        return setup

    @standard_router.api_route(
        "/control/status",
        methods=["GET", "HEAD"],
        response_model=AnalysisControlStatusV2,
    )
    def standard_control_status() -> AnalysisControlStatusV2:
        return AnalysisControlStatusV2(
            standard_reprocess_enabled=standard_reprocessor is not None,
            research_reprocess_enabled=research_reprocessor is not None,
        )

    if standard_reprocessor is not None:

        @standard_router.post(
            "/control/recordings/{session_id}/reprocess",
            response_model=StandardReprocessResultV1,
            status_code=202,
        )
        def reprocess_recording(
            session_id: Annotated[
                str,
                ApiPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"),
            ],
        ) -> StandardReprocessResultV1:
            try:
                return standard_reprocessor.queue(session_id)
            except StandardReprocessError as error:
                raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    if research_reprocessor is not None:

        @standard_router.post(
            "/control/recordings/{session_id}/research",
            response_model=ResearchReprocessResultV1,
            status_code=202,
        )
        def research_recording(
            session_id: Annotated[
                str,
                ApiPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"),
            ],
        ) -> ResearchReprocessResultV1:
            try:
                return research_reprocessor.queue(session_id)
            except StandardReprocessError as error:
                raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    def _standard_repository() -> (
        StandardPresentationRepository | DefinitionDispatchedStandardPresentationPort
    ):
        if standard_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation projection is not configured",
            )
        return standard_repository

    def _research_repository() -> StandardPresentationRepository:
        if research_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Research presentation projection is not configured",
            )
        return research_repository

    def _visible_hierarchy(
        session_id: str, *, include_test: bool
    ) -> (
        StandardSubjectHierarchyV2
        | StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
    ):
        try:
            hierarchy = _standard_repository().subject_hierarchy(session_id)
        except StandardPresentationNotReady as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if hierarchy is None:
            raise HTTPException(status_code=404, detail="Standard subject hierarchy not found")
        try:
            if isinstance(hierarchy, StandardNativeSubjectHierarchyV4):
                hierarchy = StandardNativeSubjectHierarchyV4.model_validate(hierarchy.model_dump())
            elif isinstance(hierarchy, StandardNativeSubjectHierarchyV3):
                hierarchy = StandardNativeSubjectHierarchyV3.model_validate(hierarchy.model_dump())
            else:
                hierarchy = StandardSubjectHierarchyV2.model_validate(hierarchy.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="Standard subject hierarchy projection is invalid",
            ) from error
        if hierarchy.eligibility.evidence_only and not include_test:
            raise HTTPException(
                status_code=404,
                detail="TEST evidence requires include_test=true",
            )
        return hierarchy

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects",
        methods=["GET", "HEAD"],
        response_model=(
            StandardSubjectHierarchyV2
            | StandardNativeSubjectHierarchyV3
            | StandardNativeSubjectHierarchyV4
        ),
    )
    def standard_subjects(
        session_id: str,
        include_test: bool = False,
    ) -> (
        StandardSubjectHierarchyV2
        | StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
    ):
        return _visible_hierarchy(session_id, include_test=include_test)

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}",
        methods=["GET", "HEAD"],
        response_model=(
            StandardSubjectDetailV2 | StandardNativeSubjectDetailV3 | StandardNativeSubjectDetailV4
        ),
    )
    def standard_subject_detail(
        session_id: str,
        subject_id: str,
        include_test: bool = False,
    ) -> StandardSubjectDetailV2 | StandardNativeSubjectDetailV3 | StandardNativeSubjectDetailV4:
        _visible_hierarchy(session_id, include_test=include_test)
        try:
            detail = _standard_repository().subject_detail(session_id, subject_id)
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if detail is None:
            raise HTTPException(status_code=404, detail="Standard subject not found")
        try:
            if isinstance(detail, StandardNativeSubjectDetailV4):
                return StandardNativeSubjectDetailV4.model_validate(detail.model_dump())
            if isinstance(detail, StandardNativeSubjectDetailV3):
                return StandardNativeSubjectDetailV3.model_validate(detail.model_dump())
            return StandardSubjectDetailV2.model_validate(detail.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="Standard subject detail projection is invalid",
            ) from error

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/replay-audit",
        methods=["GET", "HEAD"],
        response_model=StandardReplayAuditV1,
    )
    def standard_replay_audit(
        session_id: str, subject_id: str, include_test: bool = False
    ) -> StandardReplayAuditV1:
        _visible_hierarchy(session_id, include_test=include_test)
        audit = _standard_repository().subject_replay_audit(session_id, subject_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Standard replay audit not found")
        return StandardReplayAuditV1.model_validate(audit.model_dump())

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/track-gates",
        methods=["GET", "HEAD"],
        response_model=StandardTrackGateAuditV1,
    )
    def standard_track_gates(
        session_id: str, subject_id: str, include_test: bool = False
    ) -> StandardTrackGateAuditV1:
        _visible_hierarchy(session_id, include_test=include_test)
        audit = _standard_repository().subject_track_gate_audit(session_id, subject_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Standard track-gate audit not found")
        return StandardTrackGateAuditV1.model_validate(audit.model_dump())

    def _verified_standard_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        include_test: bool,
        maximum_points: int,
    ) -> StandardPlotViewV2 | StandardNativePlotViewV3 | StandardNativePlotViewV4:
        _visible_hierarchy(session_id, include_test=include_test)
        presentation = _standard_repository()
        try:
            detail = presentation.subject_detail(session_id, subject_id)
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if detail is None:
            raise HTTPException(status_code=404, detail="Standard subject not found")
        try:
            view = presentation.subject_view(
                session_id,
                subject_id,
                view_kind,
                maximum_points=maximum_points,
            )
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if view is None:
            raise HTTPException(status_code=404, detail="Standard subject view not found")
        try:
            if isinstance(view, (StandardNativePlotViewV3, StandardNativePlotViewV4)):
                native_verifier = getattr(presentation, "verify_source_proof", None)
                verified = native_verifier is not None and native_verifier(
                    session_id,
                    subject_id,
                    view_kind,
                    view.source_proof,
                )
            else:
                verified = presentation.verify_source_extrema(
                    session_id,
                    subject_id,
                    view_kind,
                    view.source_extrema,
                )
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if not verified:
            raise HTTPException(
                status_code=503,
                detail="Standard subject view source-extrema proof is invalid",
            )
        try:
            if isinstance(
                detail, (StandardNativeSubjectDetailV3, StandardNativeSubjectDetailV4)
            ) and isinstance(view, (StandardNativePlotViewV3, StandardNativePlotViewV4)):
                validate_standard_native_view_binding(detail, view)
            elif isinstance(detail, StandardSubjectDetailV2) and isinstance(
                view, StandardPlotViewV2
            ):
                validate_standard_view_binding(detail, view)
            else:
                raise ValueError("Standard subject detail and view majors differ")
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="Standard subject view is inconsistent with selected subject",
            ) from error
        return view

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/views/{view_kind}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def standard_subject_view_png(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        include_test: bool = False,
        maximum_points: Annotated[int, Query(ge=4, le=2048)] = 2048,
    ) -> Response:
        """Serve a registered analysis artifact; never render a PNG in the API."""

        del maximum_points  # Retained as an immutable public query contract.
        _visible_hierarchy(session_id, include_test=include_test)
        if view_kind in {StandardViewKindV2.POWER, StandardViewKindV2.QUALITY}:
            raise HTTPException(status_code=404, detail="Standard PNG is not published")
        standard = _standard_repository()
        artifact_reader = getattr(standard, "subject_png_artifact", None)
        if artifact_reader is None:
            raise HTTPException(status_code=503, detail="Registered Standard PNG is unavailable")
        try:
            artifact = artifact_reader(session_id, subject_id, view_kind)
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="Registered Standard PNG artifact is unavailable",
            ) from error
        if artifact is None:
            raise HTTPException(status_code=404, detail="Standard PNG is not published")
        return _png_response(artifact, view_kind)

    def _png_response(
        content: bytes,
        view_kind: StandardViewKindV2,
    ) -> Response:
        filename = f"standard-{view_kind.value}.png"
        return Response(
            content=content,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "artifact",
            },
        )

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/artifacts/{artifact_name}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def standard_subject_named_png(
        session_id: str,
        subject_id: str,
        artifact_name: Literal[
            "cfo-raw",
            "cfo-dealiased",
            "cfo-final",
            "cfo-alternate",
            "trajectory-accounting",
            "pilot-doppler",
            "pilot-carrier-tracking",
            "pilot-segment-rates",
            "full-capture-glrt20ms",
        ],
    ) -> Response:
        """Serve an already-published presentation PNG; never render on request."""

        reader = getattr(_standard_repository(), "subject_named_png_artifact", None)
        if reader is None:
            raise HTTPException(status_code=503, detail="Registered Standard PNG is unavailable")
        try:
            artifact = reader(session_id, subject_id, artifact_name)
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="Registered Standard PNG artifact is unavailable",
            ) from error
        if artifact is None:
            raise HTTPException(status_code=404, detail="Standard PNG is not published")
        return Response(
            content=artifact,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="standard-{artifact_name}.png"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "artifact",
            },
        )

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/artifacts",
        methods=["GET", "HEAD"],
        response_model=StandardNativePngArtifactInventoryV4 | StandardNativePngArtifactInventoryV5,
    )
    def standard_subject_png_inventory(
        session_id: str,
        subject_id: str,
        include_test: bool = False,
    ) -> StandardNativePngArtifactInventoryV4 | StandardNativePngArtifactInventoryV5:
        """Return the sealed native 11/5/5 PNG inventory for one subject."""

        hierarchy = _visible_hierarchy(session_id, include_test=include_test)
        if not isinstance(
            hierarchy, (StandardNativeSubjectHierarchyV3, StandardNativeSubjectHierarchyV4)
        ):
            raise HTTPException(status_code=404, detail="Native PNG inventory is not published")
        reader = getattr(_standard_repository(), "subject_png_inventory", None)
        if reader is None:
            raise HTTPException(status_code=503, detail="Native PNG inventory is unavailable")
        try:
            inventory = reader(session_id, subject_id)
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Native PNG inventory is unavailable",
            ) from error
        if inventory is None:
            raise HTTPException(status_code=404, detail="Native PNG inventory is not published")
        try:
            if isinstance(inventory, StandardNativePngArtifactInventoryV5):
                return StandardNativePngArtifactInventoryV5.model_validate(inventory.model_dump())
            return StandardNativePngArtifactInventoryV4.model_validate(inventory.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="Native PNG inventory is invalid",
            ) from error

    @standard_router.api_route(
        "/recordings/{session_id}/standard-investigations",
        methods=["GET", "HEAD"],
        response_model=StandardInvestigationGalleryV1,
    )
    def standard_investigation_gallery(
        session_id: str,
    ) -> StandardInvestigationGalleryV1 | Response:
        try:
            gallery = standard_investigations.gallery(session_id)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail="Standard investigation gallery is unavailable",
            ) from error
        if gallery is None:
            # This gallery is an optional, bounded follow-up rather than a
            # Standard pipeline product.  Empty is an ordinary state and must
            # not create a failed-resource error in every recording page.
            return Response(status_code=204)
        return gallery

    @standard_router.api_route(
        "/recordings/{session_id}/standard-investigations/{image_id}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def standard_investigation_image(session_id: str, image_id: str) -> Response:
        try:
            payload = standard_investigations.image(session_id, image_id)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail="Standard investigation image is unavailable",
            ) from error
        if payload is None:
            raise HTTPException(status_code=404, detail="Standard investigation image not found")
        return Response(
            content=payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": f'inline; filename="{image_id}.png"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "investigation-artifact",
            },
        )

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/views/{view_kind}",
        methods=["GET", "HEAD"],
        response_model=StandardPlotViewV2 | StandardNativePlotViewV3 | StandardNativePlotViewV4,
    )
    def standard_subject_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        include_test: bool = False,
        maximum_points: Annotated[int, Query(ge=4, le=2048)] = 512,
    ) -> StandardPlotViewV2 | StandardNativePlotViewV3 | StandardNativePlotViewV4:
        return _verified_standard_view(
            session_id,
            subject_id,
            view_kind,
            include_test=include_test,
            maximum_points=maximum_points,
        )

    def _visible_research_hierarchy(
        session_id: str, *, include_test: bool
    ) -> StandardSubjectHierarchyV2:
        presentation = _research_repository()
        try:
            hierarchy = presentation.subject_hierarchy(session_id)
        except StandardPresentationNotReady as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503, detail="Research presentation is unavailable"
            ) from error
        if hierarchy is None:
            raise HTTPException(status_code=404, detail="Research analysis has not been run")
        try:
            hierarchy = StandardSubjectHierarchyV2.model_validate(hierarchy.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503, detail="Research hierarchy projection is invalid"
            ) from error
        if hierarchy.eligibility.evidence_only and not include_test:
            raise HTTPException(status_code=404, detail="TEST evidence requires include_test=true")
        return hierarchy

    def _verified_research_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        include_test: bool,
        maximum_points: int,
    ) -> StandardPlotViewV2:
        _visible_research_hierarchy(session_id, include_test=include_test)
        presentation = _research_repository()
        try:
            detail = presentation.subject_detail(session_id, subject_id)
            view = presentation.subject_view(
                session_id, subject_id, view_kind, maximum_points=maximum_points
            )
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503, detail="Research presentation is unavailable"
            ) from error
        if detail is None or view is None:
            raise HTTPException(status_code=404, detail="Research subject view not found")
        if not presentation.verify_source_extrema(
            session_id, subject_id, view_kind, view.source_extrema
        ):
            raise HTTPException(status_code=503, detail="Research source-extrema proof is invalid")
        try:
            validate_standard_view_binding(detail, view)
        except ValueError as error:
            raise HTTPException(
                status_code=503, detail="Research view is inconsistent with its subject"
            ) from error
        return view

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects",
        methods=["GET", "HEAD"],
        response_model=StandardSubjectHierarchyV2,
    )
    def research_subjects(
        session_id: str, include_test: bool = False
    ) -> StandardSubjectHierarchyV2:
        return _visible_research_hierarchy(session_id, include_test=include_test)

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}",
        methods=["GET", "HEAD"],
        response_model=StandardSubjectDetailV2,
    )
    def research_subject_detail(
        session_id: str, subject_id: str, include_test: bool = False
    ) -> StandardSubjectDetailV2:
        _visible_research_hierarchy(session_id, include_test=include_test)
        try:
            detail = _research_repository().subject_detail(session_id, subject_id)
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503, detail="Research presentation is unavailable"
            ) from error
        if detail is None:
            raise HTTPException(status_code=404, detail="Research subject not found")
        try:
            return StandardSubjectDetailV2.model_validate(detail.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503, detail="Research subject projection is invalid"
            ) from error

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}/replay-audit",
        methods=["GET", "HEAD"],
        response_model=StandardReplayAuditV1,
    )
    def research_replay_audit(
        session_id: str, subject_id: str, include_test: bool = False
    ) -> StandardReplayAuditV1:
        _visible_research_hierarchy(session_id, include_test=include_test)
        audit = _research_repository().subject_replay_audit(session_id, subject_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Research replay audit not found")
        return StandardReplayAuditV1.model_validate(audit.model_dump())

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}/track-gates",
        methods=["GET", "HEAD"],
        response_model=StandardTrackGateAuditV1,
    )
    def research_track_gates(
        session_id: str, subject_id: str, include_test: bool = False
    ) -> StandardTrackGateAuditV1:
        _visible_research_hierarchy(session_id, include_test=include_test)
        audit = _research_repository().subject_track_gate_audit(session_id, subject_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Research track-gate audit not found")
        return StandardTrackGateAuditV1.model_validate(audit.model_dump())

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}/views/{view_kind}",
        methods=["GET", "HEAD"],
        response_model=StandardPlotViewV2,
    )
    def research_subject_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        include_test: bool = False,
        maximum_points: Annotated[int, Query(ge=4, le=2048)] = 512,
    ) -> StandardPlotViewV2:
        return _verified_research_view(
            session_id,
            subject_id,
            view_kind,
            include_test=include_test,
            maximum_points=maximum_points,
        )

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}/views/{view_kind}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def research_subject_view_png(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        include_test: bool = False,
    ) -> Response:
        _visible_research_hierarchy(session_id, include_test=include_test)
        if view_kind in {StandardViewKindV2.POWER, StandardViewKindV2.QUALITY}:
            raise HTTPException(status_code=404, detail="Research PNG is not published")
        reader = getattr(_research_repository(), "subject_png_artifact", None)
        try:
            artifact = None if reader is None else reader(session_id, subject_id, view_kind)
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="Registered Research PNG is unavailable"
            ) from error
        if artifact is None:
            raise HTTPException(status_code=404, detail="Research PNG is not published")
        return Response(
            content=artifact,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="research-{view_kind.value}.png"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "artifact",
            },
        )

    @standard_router.api_route(
        "/recordings/{session_id}/research-subjects/{subject_id}/artifacts/{artifact_name}.png",
        methods=["GET", "HEAD"],
        response_class=Response,
    )
    def research_subject_named_png(
        session_id: str,
        subject_id: str,
        artifact_name: Literal[
            "cfo-raw",
            "cfo-dealiased",
            "cfo-final",
            "cfo-alternate",
            "trajectory-accounting",
            "pilot-doppler",
            "pilot-carrier-tracking",
            "pilot-segment-rates",
            "full-capture-glrt20ms",
        ],
    ) -> Response:
        reader = getattr(_research_repository(), "subject_named_png_artifact", None)
        try:
            artifact = None if reader is None else reader(session_id, subject_id, artifact_name)
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="Registered Research PNG is unavailable"
            ) from error
        if artifact is None:
            raise HTTPException(status_code=404, detail="Research PNG is not published")
        return Response(
            content=artifact,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="research-{artifact_name}.png"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": "artifact",
            },
        )

    app.include_router(standard_router)

    sky_router = APIRouter(prefix="/api/v1/sky")

    def _require_known_provider(provider: str | None) -> None:
        """An unsupported provider is a client mistake, not an outage."""

        if provider is not None and provider not in PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"unsupported TLE provider {provider!r}; expected one of "
                + ", ".join(PROVIDERS),
            )

    def _sky_window(at: int, half_width_s: int) -> SkyWindowV1:
        try:
            return SkyWindowV1(anchor_utc_ns=at, half_width_s=half_width_s)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def _sky_view_call[ViewT](build: Callable[[], ViewT], provider: str | None) -> ViewT:
        """Run a view projection, mapping its failures onto honest statuses."""

        # Validate the request before reporting on the service: a typo is the
        # caller's mistake whether or not sky prediction happens to be
        # configured, and the field and snapshot routes already order it so.
        _require_known_provider(provider)
        _sky()
        try:
            return build()
        except SkyFieldUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def _sky() -> SkyFieldService:
        if sky_service is None:
            raise HTTPException(
                status_code=503,
                detail="Sky prediction is not configured",
            )
        return sky_service

    @sky_router.api_route("/sites", methods=["GET", "HEAD"], response_model=SkySiteListV1)
    def sky_sites() -> SkySiteListV1:
        """Reviewed observer presets.  Available without an element-set archive."""

        return site_list()

    @sky_router.api_route("/snapshots", methods=["GET", "HEAD"], response_model=SkySnapshotListV1)
    def sky_snapshots(
        provider: str | None = None,
        limit: Annotated[int, Query(ge=1, le=MAXIMUM_LISTED_SNAPSHOTS)] = 20,
    ) -> SkySnapshotListV1:
        _require_known_provider(provider)
        service = _sky()
        try:
            snapshots = service.archive.list_snapshots(provider)
        except TleArchiveError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if not snapshots:
            # Consistent with /field: an archive with nothing in it is
            # unavailable, not an empty sky.
            raise HTTPException(
                status_code=503,
                detail="no TLE snapshot is available"
                + ("" if provider is None else f" for provider {provider!r}"),
            )
        root = sky_archive_root or service.archive.root
        return snapshot_list(str(root), snapshots, limit=limit)

    @sky_router.api_route(
        "/tle/snapshots", methods=["GET", "HEAD"], response_model=TleArchiveListV1
    )
    def tle_snapshots(
        limit: Annotated[int, Query(ge=1, le=MAXIMUM_LISTED_SNAPSHOTS)] = (
            MAXIMUM_LISTED_SNAPSHOTS
        ),
    ) -> TleArchiveListV1:
        """Verified local TLE files with source and satellite inventory."""

        return _sky_view_call(
            lambda: SkyViewService(_sky()).tle_inventory(limit=limit),
            None,
        )

    @sky_router.api_route("/field", methods=["GET", "HEAD"], response_model=SkyFieldReportV1)
    def sky_field(
        latitude_deg: Annotated[float, Query(alias="lat", ge=-90.0, le=90.0)],
        longitude_deg: Annotated[float, Query(alias="lon", gt=-180.0, le=180.0)],
        at: Annotated[int, Query(gt=0, description="Anchor instant, UTC nanoseconds.")],
        altitude_m: Annotated[float, Query(alias="alt", ge=-500.0, le=9_000.0)] = 0.0,
        azimuth_deg: Annotated[float, Query(alias="az", ge=0.0, lt=360.0)] = 180.0,
        elevation_deg: Annotated[float, Query(alias="el", ge=-90.0, le=90.0)] = 45.0,
        half_angle_deg: Annotated[float, Query(alias="fov", gt=0.0, le=90.0)] = 3.0,
        horizon_mask_deg: Annotated[float, Query(alias="mask", ge=0.0, le=90.0)] = 0.0,
        half_width_s: Annotated[int, Query(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S,
        downlink_hz: Annotated[
            float, Query(gt=0.0, le=MAXIMUM_DOWNLINK_FREQUENCY_HZ)
        ] = DEFAULT_DOWNLINK_FREQUENCY_HZ,
        limit: Annotated[int, Query(ge=1, le=MAXIMUM_REPORT_OBJECTS)] = 20,
        label: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        provider: str | None = None,
    ) -> SkyFieldReportV1:
        """Predicted objects in one beam.

        The anchor instant is required: an answer that silently means "now" is
        not reproducible, and this surface is read by scripts as well as people.
        """

        _require_known_provider(provider)
        service = _sky()
        observer = ObserverSiteV1(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=altitude_m,
            label=label or f"{latitude_deg:+.5f},{longitude_deg:+.5f}",
        )
        pointing = BeamPointingV1(
            boresight_azimuth_deg=azimuth_deg,
            boresight_elevation_deg=elevation_deg,
            half_angle_deg=half_angle_deg,
            horizon_mask_deg=horizon_mask_deg,
        )
        try:
            window = SkyWindowV1(anchor_utc_ns=at, half_width_s=half_width_s)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            return service.bounded(limit).field_report(
                observer=observer,
                pointing=pointing,
                window=window,
                downlink_frequency_hz=downlink_hz,
                provider=provider,
            )
        except SkyFieldUnavailableError as error:
            # An unavailable sky is never served as an empty one.
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            # A request the contracts or the numerics refuse is the caller's
            # input, not a server fault.  Without this an arithmetic rejection
            # deep in the fit reaches the client as a 500.
            raise HTTPException(status_code=422, detail=str(error)) from error

    @sky_router.api_route("/globe", methods=["GET", "HEAD"], response_model=GlobeFrameSetV1)
    def sky_globe(
        at: Annotated[int, Query(gt=0, description="Anchor instant, UTC nanoseconds.")],
        half_width_s: Annotated[int, Query(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S,
        sample_count: Annotated[int, Query(ge=3, le=MAXIMUM_VIEW_SAMPLES)] = 5,
        limit: Annotated[int, Query(ge=1, le=MAXIMUM_GLOBE_OBJECTS)] = MAXIMUM_GLOBE_OBJECTS,
        provider: str | None = None,
    ) -> GlobeFrameSetV1:
        """Quantised ECEF tracks for the constellation.

        Tracks rather than frames: the browser interpolates between knots, so a
        smooth globe needs one request per window instead of one per frame.
        """

        return _sky_view_call(
            lambda: SkyViewService(_sky()).globe(
                window=_sky_window(at, half_width_s),
                sample_count=sample_count,
                limit=limit,
                provider=provider,
            ),
            provider,
        )

    @sky_router.api_route("/skyview", methods=["GET", "HEAD"], response_model=SkyViewFrameSetV1)
    def sky_dome(
        latitude_deg: Annotated[float, Query(alias="lat", ge=-90.0, le=90.0)],
        longitude_deg: Annotated[float, Query(alias="lon", gt=-180.0, le=180.0)],
        at: Annotated[int, Query(gt=0, description="Anchor instant, UTC nanoseconds.")],
        altitude_m: Annotated[float, Query(alias="alt", ge=-500.0, le=9_000.0)] = 0.0,
        horizon_mask_deg: Annotated[float, Query(alias="mask", ge=0.0, le=90.0)] = 0.0,
        half_width_s: Annotated[int, Query(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S,
        sample_count: Annotated[int, Query(ge=3, le=MAXIMUM_VIEW_SAMPLES)] = 9,
        limit: Annotated[int, Query(ge=1, le=MAXIMUM_GLOBE_OBJECTS)] = 512,
        label: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        provider: str | None = None,
    ) -> SkyViewFrameSetV1:
        """Horizon-frame tracks as seen looking up from one ground position."""

        observer = ObserverSiteV1(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=altitude_m,
            label=label or f"{latitude_deg:+.5f},{longitude_deg:+.5f}",
        )
        return _sky_view_call(
            lambda: SkyViewService(_sky()).sky_view(
                observer=observer,
                window=_sky_window(at, half_width_s),
                horizon_mask_deg=horizon_mask_deg,
                sample_count=sample_count,
                limit=limit,
                provider=provider,
            ),
            provider,
        )

    @sky_router.api_route(
        "/skyview/object", methods=["GET", "HEAD"], response_model=SkyViewObjectDetailV1
    )
    def sky_dome_object(
        catalog_number: Annotated[int, Query(alias="catalog", ge=1)],
        latitude_deg: Annotated[float, Query(alias="lat", ge=-90.0, le=90.0)],
        longitude_deg: Annotated[float, Query(alias="lon", gt=-180.0, le=180.0)],
        at: Annotated[int, Query(gt=0, description="Anchor instant, UTC nanoseconds.")],
        altitude_m: Annotated[float, Query(alias="alt", ge=-500.0, le=9_000.0)] = 0.0,
        downlink_frequency_hz: Annotated[
            float, Query(alias="downlink_hz", gt=0.0, le=MAXIMUM_DOWNLINK_FREQUENCY_HZ)
        ] = DEFAULT_DOWNLINK_FREQUENCY_HZ,
        half_width_s: Annotated[int, Query(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S,
        sample_count: Annotated[int, Query(ge=3, le=MAXIMUM_VIEW_SAMPLES)] = 9,
        label: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        provider: str | None = None,
        snapshot_digest: Annotated[str | None, Query(alias="snapshot")] = None,
    ) -> SkyViewObjectDetailV1:
        """Orbit elements and predicted Doppler for one selected sky-view object."""

        observer = ObserverSiteV1(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=altitude_m,
            label=label or f"{latitude_deg:+.5f},{longitude_deg:+.5f}",
        )
        return _sky_view_call(
            lambda: SkyViewService(_sky()).object_detail(
                observer=observer,
                window=_sky_window(at, half_width_s),
                catalog_number=catalog_number,
                downlink_frequency_hz=downlink_frequency_hz,
                sample_count=sample_count,
                provider=provider,
                snapshot_digest=snapshot_digest,
            ),
            provider,
        )

    @sky_router.api_route(
        "/skyview/object/tle-comparison",
        methods=["GET", "HEAD"],
        response_model=SkyViewTleComparisonV1,
    )
    def sky_dome_object_tle_comparison(
        catalog_number: Annotated[int, Query(alias="catalog", ge=1)],
        latitude_deg: Annotated[float, Query(alias="lat", ge=-90.0, le=90.0)],
        longitude_deg: Annotated[float, Query(alias="lon", gt=-180.0, le=180.0)],
        at: Annotated[int, Query(gt=0, description="Comparison instant, UTC nanoseconds.")],
        provider: str,
        snapshot_digest: Annotated[str, Query(alias="snapshot")],
        altitude_m: Annotated[float, Query(alias="alt", ge=-500.0, le=9_000.0)] = 0.0,
        half_width_s: Annotated[int, Query(ge=1, le=3_600)] = SKY_WINDOW_HALF_WIDTH_S,
        label: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    ) -> SkyViewTleComparisonV1:
        """Latest five unique local element sets for one selected object."""

        observer = ObserverSiteV1(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=altitude_m,
            label=label or f"{latitude_deg:+.5f},{longitude_deg:+.5f}",
        )
        return _sky_view_call(
            lambda: SkyViewService(_sky()).object_tle_comparison(
                observer=observer,
                window=_sky_window(at, half_width_s),
                catalog_number=catalog_number,
                provider=provider,
                snapshot_digest=snapshot_digest,
            ),
            provider,
        )

    app.include_router(sky_router)
    if static_directory is not None:
        static_root = static_directory.resolve(strict=True)
        if not static_root.is_dir() or static_directory.is_symlink():
            raise ValueError("static directory must be a real directory")
        app.mount("/", StaticFiles(directory=static_root, html=True), name="web-ui")
    return app
