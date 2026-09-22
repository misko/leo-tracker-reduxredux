"""Read-only API for blind broad-region association and positioning."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from leo.contracts.blind_regional import ArtifactName, BlindRegionalReader, BlindRegionalStatusV1
from leo.contracts.digests import Sha256Digest

Identifier = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def blind_regional_router(reader: BlindRegionalReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/scanner/tracking")

    @router.api_route(
        "/{session_id}/blind-regional",
        methods=["GET", "HEAD"],
        response_model=BlindRegionalStatusV1,
    )
    def status(session_id: Identifier):
        if reader is None:
            raise HTTPException(404, "blind regional evidence is unavailable")
        try:
            return reader.status(session_id)
        except (ValueError, OSError) as error:
            raise HTTPException(409, "blind regional evidence failed verification") from error

    @router.api_route("/{session_id}/blind-regional/{name}.png", methods=["GET", "HEAD"])
    def artifact(
        session_id: Identifier, name: ArtifactName, sha256: Annotated[Sha256Digest, Query()]
    ):
        if reader is None:
            raise HTTPException(404, "blind regional evidence is unavailable")
        try:
            current = reader.status(session_id)
            if current.manifest is None:
                raise HTTPException(404, "blind regional PNG has not been published")
            reference = next(x for x in current.manifest.artifacts if x.name == name)
            if reference.sha256 != sha256:
                raise HTTPException(409, "blind regional PNG digest query differs")
            payload = reader.artifact(session_id, name)
        except HTTPException:
            raise
        except (ValueError, OSError) as error:
            raise HTTPException(409, "blind regional evidence failed verification") from error
        if payload is None:
            raise HTTPException(404, "blind regional PNG has not been published")
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
