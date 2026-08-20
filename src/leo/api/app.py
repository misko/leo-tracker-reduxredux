"""FastAPI application exposing presentation data and narrow operator actions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query, Response
from fastapi import Path as ApiPath
from fastapi.staticfiles import StaticFiles

from leo.api.artifacts import RegisteredArtifactError, RegisteredArtifactResolver
from leo.api.png_cache import StandardPngDiskCache
from leo.application.standard_presentation import StandardPresentationUnavailable
from leo.application.standard_reprocess import (
    StandardReprocessError,
    StandardReprocessor,
    StandardReprocessResultV1,
)
from leo.presentation.models import (
    ActiveQueueV1,
    AnalysisProductV1,
    AnalysisStateV1,
    AnalysisSummaryV1,
    ProductContentV1,
    QualificationCampaignDetailV1,
    QualificationCampaignListV1,
    RecordingDetailV1,
    RecordingSearchResponseV1,
    StorageStateV1,
    SystemStatusV1,
)
from leo.presentation.repository import PresentationRepository
from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardViewKindV2,
)
from leo.presentation.standard_png import (
    render_full_standard_plot_png,
    render_standard_plot_png,
)
from leo.presentation.standard_repository import (
    StandardPresentationRepository,
    validate_standard_view_binding,
)


def create_app(
    repository: PresentationRepository,
    *,
    artifact_root: Path,
    static_directory: Path | None = None,
    standard_repository: StandardPresentationRepository | None = None,
    standard_reprocessor: StandardReprocessor | None = None,
) -> FastAPI:
    """Create presentation routes and an optional explicit reprocess action."""

    app = FastAPI(
        title="Leo Tracker Read-only UI",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    resolver = RegisteredArtifactResolver(artifact_root)
    standard_png_cache = StandardPngDiskCache(artifact_root)
    router = APIRouter(prefix="/api/v1")

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

    standard_router = APIRouter(prefix="/api/v2")

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

    def _standard_repository() -> StandardPresentationRepository:
        if standard_repository is None:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation projection is not configured",
            )
        return standard_repository

    def _visible_hierarchy(session_id: str, *, include_test: bool) -> StandardSubjectHierarchyV2:
        try:
            hierarchy = _standard_repository().subject_hierarchy(session_id)
        except StandardPresentationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="Standard-v2 presentation is unavailable",
            ) from error
        if hierarchy is None:
            raise HTTPException(status_code=404, detail="Standard subject hierarchy not found")
        try:
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
        response_model=StandardSubjectHierarchyV2,
    )
    def standard_subjects(
        session_id: str,
        include_test: bool = False,
    ) -> StandardSubjectHierarchyV2:
        return _visible_hierarchy(session_id, include_test=include_test)

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}",
        methods=["GET", "HEAD"],
        response_model=StandardSubjectDetailV2,
    )
    def standard_subject_detail(
        session_id: str,
        subject_id: str,
        include_test: bool = False,
    ) -> StandardSubjectDetailV2:
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
            return StandardSubjectDetailV2.model_validate(detail.model_dump())
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="Standard subject detail projection is invalid",
            ) from error

    def _verified_standard_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        include_test: bool,
        maximum_points: int,
    ) -> StandardPlotViewV2:
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
            validate_standard_view_binding(detail, view)
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
        if view_kind in {StandardViewKindV2.POWER, StandardViewKindV2.QUALITY}:
            raise HTTPException(status_code=404, detail="Standard PNG is not published")
        standard = _standard_repository()
        identity_reader = getattr(standard, "subject_png_cache_identity", None)
        identity = (
            None if identity_reader is None else identity_reader(session_id, subject_id, view_kind)
        )
        cache_key = (
            None
            if identity is None
            else hashlib.sha256(
                (f"standard-png-renderer-v3\0{identity}\0{include_test}\0{maximum_points}").encode()
            ).hexdigest()
        )
        cached = None if cache_key is None else standard_png_cache.read(cache_key)
        if cached is not None:
            return _png_response(cached, view_kind, cache_state="hit")
        view = _verified_standard_view(
            session_id,
            subject_id,
            view_kind,
            include_test=include_test,
            maximum_points=maximum_points,
        )
        cfo_companion = None
        if view_kind is StandardViewKindV2.GLRT64:
            cfo_companion = _verified_standard_view(
                session_id,
                subject_id,
                StandardViewKindV2.CFO_TRAJECTORY,
                include_test=include_test,
                maximum_points=maximum_points,
            )
        source_reader = getattr(standard, "subject_png_source", None)
        full_source = (
            None if source_reader is None else source_reader(session_id, subject_id, view_kind)
        )
        content = (
            render_full_standard_plot_png(full_source, view_kind)
            if full_source is not None
            else render_standard_plot_png(view, cfo_companion=cfo_companion)
        )
        if cache_key is not None:
            content = standard_png_cache.publish(cache_key, content)
        return _png_response(content, view_kind, cache_state="miss")

    def _png_response(
        content: bytes,
        view_kind: StandardViewKindV2,
        *,
        cache_state: str,
    ) -> Response:
        filename = f"standard-{view_kind.value}.png"
        return Response(
            content=content,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
                "X-Leo-PNG-Cache": cache_state,
            },
        )

    @standard_router.api_route(
        "/recordings/{session_id}/standard-subjects/{subject_id}/views/{view_kind}",
        methods=["GET", "HEAD"],
        response_model=StandardPlotViewV2,
    )
    def standard_subject_view(
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        include_test: bool = False,
        maximum_points: Annotated[int, Query(ge=4, le=2048)] = 512,
    ) -> StandardPlotViewV2:
        return _verified_standard_view(
            session_id,
            subject_id,
            view_kind,
            include_test=include_test,
            maximum_points=maximum_points,
        )

    app.include_router(standard_router)
    if static_directory is not None:
        static_root = static_directory.resolve(strict=True)
        if not static_root.is_dir() or static_directory.is_symlink():
            raise ValueError("static directory must be a real directory")
        app.mount("/", StaticFiles(directory=static_root, html=True), name="web-ui")
    return app
