"""Read-only routes for separately published scanner comparison artifacts."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response

from leo.contracts.scanner_refinement import Artifact, ComparisonStatusV1, ScannerRefinementReader
from leo.storage.errors import RecordingStoreError

Identifier = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def scanner_refinement_router(reader: ScannerRefinementReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/refinement-comparisons")

    def read(method: str, *args):
        if reader is None:
            raise HTTPException(404, "Scanner comparison evidence is unavailable")
        try:
            return getattr(reader, method)(*args)
        except (ValueError, OSError, RecordingStoreError) as error:
            raise HTTPException(409, "Scanner comparison evidence failed verification") from error

    @router.api_route("/{session_id}", methods=["GET", "HEAD"], response_model=ComparisonStatusV1)
    def status(session_id: Identifier):
        return read("status", session_id)

    @router.api_route("/{session_id}/evidence.json", methods=["GET", "HEAD"])
    def evidence(session_id: Identifier):
        payload = read("evidence", session_id)
        if payload is None:
            raise HTTPException(404, "Scanner comparison evidence has not been published")
        return Response(
            payload, media_type="application/json", headers={"Cache-Control": "no-cache"}
        )

    @router.api_route("/{session_id}/{artifact}.png", methods=["GET", "HEAD"])
    def image(session_id: Identifier, artifact: Artifact):
        payload = read("artifact", session_id, artifact)
        if payload is None:
            raise HTTPException(404, "Scanner comparison PNG has not been published")
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": f'inline; filename="{artifact}.png"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
