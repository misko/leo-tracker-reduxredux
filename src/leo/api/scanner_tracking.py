"""Shared tracking HTTP port for every scanner capture mode."""

from fastapi import APIRouter, HTTPException, Response

from leo.contracts.scanner_tracking import (
    ArtifactName,
    ScannerTrackingReader,
    ScannerTrackingStatusV1,
)


def scanner_tracking_router(reader: ScannerTrackingReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/tracking")

    @router.get("/{session_id}", response_model=ScannerTrackingStatusV1)
    def status(session_id: str):
        if reader is None:
            raise HTTPException(404, "shared tracking is unavailable")
        try:
            return reader.status(session_id)
        except ValueError as error:
            raise HTTPException(409, "tracking evidence is invalid") from error

    @router.get("/{session_id}/{name}.png")
    def artifact(session_id: str, name: ArtifactName):
        if reader is None:
            raise HTTPException(404, "shared tracking is unavailable")
        try:
            payload = reader.artifact(session_id, name)
        except ValueError as error:
            raise HTTPException(409, "tracking artifact is invalid") from error
        if payload is None:
            raise HTTPException(404, "tracking artifact is not published")
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
