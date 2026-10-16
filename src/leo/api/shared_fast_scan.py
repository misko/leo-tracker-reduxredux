"""Separate read-only routes for shared-model fast-scan processing."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from leo.presentation.shared_fast_scan import SharedFastScanReader


def shared_fast_scan_router(reader: SharedFastScanReader | None):
    router = APIRouter(prefix="/api/v1/fast-scan-shared-model")

    @router.get("")
    def page(limit: Annotated[int, Query(ge=1, le=100)] = 100):
        if reader is None:
            return {"items": []}
        try:
            return reader.page(limit=limit)
        except (ValueError, OSError) as error:
            raise HTTPException(409, "Shared-model evidence failed verification") from error

    @router.get("/{job_id}")
    def detail(job_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]):
        if reader is None:
            raise HTTPException(404, "Shared-model result not found")
        try:
            return reader.detail(job_id)
        except FileNotFoundError as error:
            raise HTTPException(404, "Shared-model result not found") from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, "Shared-model evidence failed verification") from error

    return router
