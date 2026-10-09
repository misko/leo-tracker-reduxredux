"""Read-only, digest-bound access to automatic T1AT and V16 comparisons."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from leo.contracts.digests import Sha256Digest, sha256_digest
from leo.contracts.regional_position_products import (
    Method,
    RegionalPositionReader,
    RegionalPositionStatusV1,
)
from leo.contracts.regional_position_v2 import RegionalPositionReaderV2, RegionalPositionStatusV2
from leo.contracts.regional_position_v3 import RegionalPositionReaderV3, RegionalPositionStatusV3

Identifier = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


def regional_position_router(
    reader: RegionalPositionReader | RegionalPositionReaderV2 | RegionalPositionReaderV3 | None,
    *,
    version=1,
) -> APIRouter:
    if version not in (1, 2, 3):
        raise ValueError("unknown regional result version")
    router = APIRouter(prefix="/api/v1/scanner/tracking")
    base = "/{session_id}/regional-position-v" + str(version)

    @router.api_route(
        base,
        methods=["GET", "HEAD"],
        response_model={
            1: RegionalPositionStatusV1,
            2: RegionalPositionStatusV2,
            3: RegionalPositionStatusV3,
        }[version],
    )
    def status(session_id: Identifier):
        if reader is None:
            raise HTTPException(404, "regional position evidence is unavailable")
        try:
            return reader.status(session_id)
        except (ValueError, OSError) as error:
            raise HTTPException(409, "regional position evidence failed verification") from error

    @router.api_route(base + "/{method}.png", methods=["GET", "HEAD"])
    def artifact(session_id: Identifier, method: Method, sha256: Annotated[Sha256Digest, Query()]):
        if reader is None:
            raise HTTPException(404, "regional position evidence is unavailable")
        try:
            current = reader.status(session_id)
            if current.manifest is None:
                raise HTTPException(404, "regional position PNG has not been published")
            reference = next((a for a in current.manifest.artifacts if a.name == method), None)
            if reference is None:
                raise HTTPException(404, "method is not present in this publication")
            if reference.sha256 != sha256:
                raise HTTPException(409, "regional position PNG digest query differs")
            payload = reader.artifact(session_id, method)
            if payload is None:
                raise HTTPException(404, "regional position PNG has not been published")
            if sha256_digest(payload) != sha256 or len(payload) != reference.byte_count:
                raise ValueError("regional position PNG payload differs")
        except HTTPException:
            raise
        except (ValueError, OSError) as error:
            raise HTTPException(409, "regional position evidence failed verification") from error
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
