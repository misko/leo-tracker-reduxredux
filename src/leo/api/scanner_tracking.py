"""Shared tracking HTTP port for every scanner capture mode."""

from fastapi import APIRouter, HTTPException, Response

from leo.contracts.scanner_tracking import (
    ArtifactNameV12,
    ScannerTrackingReader,
    ScannerTrackingStatusV1,
    ScannerTrackingStatusV2,
    ScannerTrackingStatusV3,
    ScannerTrackingStatusV4,
    ScannerTrackingStatusV5,
    ScannerTrackingStatusV6,
    ScannerTrackingStatusV7,
    ScannerTrackingStatusV8,
    ScannerTrackingStatusV9,
    ScannerTrackingStatusV10,
    ScannerTrackingStatusV11,
    ScannerTrackingStatusV12,
    ScannerTrackingStatusV13,
)


def scanner_tracking_router(reader: ScannerTrackingReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/tracking")

    @router.get(
        "/{session_id}",
        response_model=ScannerTrackingStatusV13
        | ScannerTrackingStatusV12
        | ScannerTrackingStatusV11
        | ScannerTrackingStatusV10
        | ScannerTrackingStatusV9
        | ScannerTrackingStatusV8
        | ScannerTrackingStatusV7
        | ScannerTrackingStatusV6
        | ScannerTrackingStatusV5
        | ScannerTrackingStatusV4
        | ScannerTrackingStatusV3
        | ScannerTrackingStatusV2
        | ScannerTrackingStatusV1,
    )
    def status(session_id: str):
        if reader is None:
            raise HTTPException(404, "shared tracking is unavailable")
        try:
            return reader.status(session_id)
        except ValueError as error:
            raise HTTPException(409, "tracking evidence is invalid") from error

    @router.get("/{session_id}/{name}.png")
    def artifact(session_id: str, name: ArtifactNameV12):
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
