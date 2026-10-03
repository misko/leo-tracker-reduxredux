"""Read-only, digest-bound partial-band analysis routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Response

from leo.contracts.partial_band import PartialBandReader, PartialBandStatusV1


def partial_band_router(reader: PartialBandReader | None):
    router = APIRouter(prefix="/api/v1/scanner/adaptive-sessions")
    Identifier = Annotated[str, Path(pattern=r"^scan-fw-[0-9a-f]{16}$")]
    Digest = Annotated[str, Query(pattern=r"^sha256:[0-9a-f]{64}$")]

    @router.get("/{session_id}/partial-band", response_model=PartialBandStatusV1)
    def status(session_id: Identifier, input_manifest_sha256: Digest):
        if reader is None:
            raise HTTPException(404, "Partial-band analysis is unavailable")
        try:
            return reader.status(session_id, input_manifest_sha256)
        except (ValueError, OSError) as error:
            raise HTTPException(409, "Partial-band evidence failed verification") from error

    @router.get("/{session_id}/partial-band/{name}")
    def artifact(
        session_id: Identifier,
        input_manifest_sha256: Digest,
        artifact_sha256: Digest,
        name: Literal[
            "coverage.png",
            "glrt64-response.png",
            "cfo-trajectories.png",
            "bandwidth.png",
            "probes.jsonl.gz",
            "segments.json",
        ],
    ):
        if reader is None:
            raise HTTPException(404, "Partial-band analysis is unavailable")
        try:
            raw = reader.artifact(session_id, input_manifest_sha256, name, artifact_sha256)
        except (ValueError, OSError) as error:
            raise HTTPException(409, "Partial-band artifact failed verification") from error
        if raw is None:
            raise HTTPException(404, "Partial-band artifact is not published")
        media = (
            "image/png"
            if name.endswith(".png")
            else "application/gzip"
            if name.endswith(".gz")
            else "application/json"
        )
        return Response(
            raw,
            media_type=media,
            headers={
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'inline; filename="{name}"',
            },
        )

    return router
