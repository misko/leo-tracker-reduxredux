"""Read-only API for additive scanner position-method sidecars."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from leo.contracts.digests import Sha256Digest
from leo.contracts.position_methods import (
    PositionMethod,
    PositionMethodsReader,
    PositionMethodsStatusV1,
)
from leo.storage.errors import RecordingStoreError

Identifier = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def position_methods_router(reader: PositionMethodsReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/tracking")

    def read(method: str, *args):
        if reader is None:
            raise HTTPException(404, "Position method evidence is unavailable")
        try:
            return getattr(reader, method)(*args)
        except (ValueError, OSError, RecordingStoreError) as error:
            raise HTTPException(409, "Position method evidence failed verification") from error

    @router.api_route(
        "/{session_id}/position-methods",
        methods=["GET", "HEAD"],
        response_model=PositionMethodsStatusV1,
    )
    def status(session_id: Identifier):
        return read("status", session_id)

    @router.api_route(
        "/{session_id}/position-methods/{method}.png", methods=["GET", "HEAD"]
    )
    def artifact(
        session_id: Identifier,
        method: PositionMethod,
        sha256: Annotated[Sha256Digest, Query()],
    ):
        status_value = read("status", session_id)
        if status_value.manifest is None:
            raise HTTPException(404, "Position method PNG has not been published")
        reference = next(
            item for item in status_value.manifest.artifacts if item.method == method
        )
        if sha256 != reference.sha256:
            raise HTTPException(409, "Position method PNG digest query differs")
        payload = read("artifact", session_id, method)
        if payload is None:
            raise HTTPException(404, "Position method PNG has not been published")
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "Content-Disposition": f'inline; filename="{method}.png"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
