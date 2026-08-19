"""FastAPI application exposing presentation-v1 as an open, read-only LAN UI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from leo.api.artifacts import RegisteredArtifactError, RegisteredArtifactResolver
from leo.presentation.models import (
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


def create_app(
    repository: PresentationRepository,
    *,
    artifact_root: Path,
    static_directory: Path | None = None,
) -> FastAPI:
    """Create an application with GET/HEAD project routes and optional static UI."""

    app = FastAPI(
        title="Leo Tracker Read-only UI",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    resolver = RegisteredArtifactResolver(artifact_root)
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

    @router.api_route(
        "/qualification/campaigns",
        methods=["GET", "HEAD"],
        response_model=QualificationCampaignListV1,
    )
    def qualification_campaigns() -> QualificationCampaignListV1:
        return repository.qualification_campaigns()

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
    if static_directory is not None:
        static_root = static_directory.resolve(strict=True)
        if not static_root.is_dir() or static_directory.is_symlink():
            raise ValueError("static directory must be a real directory")
        app.mount("/", StaticFiles(directory=static_root, html=True), name="web-ui")
    return app
