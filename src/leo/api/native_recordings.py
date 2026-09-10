"""Native episode reads by registered ID, with bounded measurement pages."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from leo.presentation.native_recordings import (
    NativeRecordingDetailV1,
    NativeRecordingListV1,
    NativeRecordingReader,
    NativeRecordingUnavailable,
)


def native_recording_router(reader: NativeRecordingReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/native-recordings")

    @router.api_route("", methods=["GET", "HEAD"], response_model=NativeRecordingListV1)
    def recordings(
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NativeRecordingListV1:
        if reader is None:
            raise HTTPException(503, "Native recording reader is not configured")
        return reader.list_recordings(cursor=cursor, limit=limit)

    @router.api_route(
        "/{bundle_id}", methods=["GET", "HEAD"], response_model=NativeRecordingDetailV1
    )
    def recording(
        bundle_id: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")],
        cursor: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    ) -> NativeRecordingDetailV1:
        if reader is None:
            raise HTTPException(503, "Native recording reader is not configured")
        try:
            return reader.get_recording(bundle_id, cursor=cursor, limit=limit)
        except KeyError:
            raise HTTPException(404, "Native recording is not registered") from None
        except NativeRecordingUnavailable:
            raise HTTPException(409, "Native recording integrity unavailable") from None

    return router
