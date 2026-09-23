"""Read-only API for adaptive TLE position-selection evidence."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from leo.contracts.adaptive_tle_position import (
    AdaptiveTlePositionReader,
    AdaptiveTlePositionStatusV1,
)
from leo.contracts.digests import Sha256Digest

Identifier = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def adaptive_tle_position_router(reader: AdaptiveTlePositionReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/tracking")

    @router.api_route(
        "/{session_id}/adaptive-tle-position",
        methods=["GET", "HEAD"],
        response_model=AdaptiveTlePositionStatusV1,
    )
    def status(session_id: Identifier):
        if reader is None:
            raise HTTPException(404, "adaptive TLE position evidence is unavailable")
        try:
            return reader.status(session_id)
        except (ValueError, OSError) as error:
            raise HTTPException(
                409, "adaptive TLE position evidence failed verification"
            ) from error

    @router.api_route("/{session_id}/adaptive-tle-position/map.png", methods=["GET", "HEAD"])
    def artifact(session_id: Identifier, sha256: Annotated[Sha256Digest, Query()]):
        if reader is None:
            raise HTTPException(404, "adaptive TLE position evidence is unavailable")
        try:
            current = reader.status(session_id)
            if current.manifest is None:
                raise HTTPException(404, "adaptive TLE position PNG has not been published")
            if current.manifest.artifacts[0].sha256 != sha256:
                raise HTTPException(409, "adaptive TLE position PNG digest query differs")
            payload = reader.artifact(session_id)
        except HTTPException:
            raise
        except (ValueError, OSError) as error:
            raise HTTPException(
                409, "adaptive TLE position evidence failed verification"
            ) from error
        if payload is None:
            raise HTTPException(404, "adaptive TLE position PNG has not been published")
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
