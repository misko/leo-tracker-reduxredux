"""Read-only access to separately versioned fast scan orbit PNGs."""

from fastapi import APIRouter, HTTPException, Response


def fast_scan_orbit_router(store, shared=None):
    router = APIRouter(prefix="/api/v1/fast-scans")

    def selected(run_id):
        return shared if shared and shared.orbit_manifest(run_id)['artifacts'] else store

    @router.get("/{run_id}/orbits")
    def manifest(run_id: str):
        try:
            reader = selected(run_id)
            return reader.orbit_manifest(run_id) if reader else {"artifacts": []}
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(404, "Orbit plots not found") from error

    @router.get("/{run_id}/orbits/{name}.png")
    def png(run_id: str, name: str):
        try:
            reader = selected(run_id)
            if reader is None:
                raise FileNotFoundError(run_id)
            data = reader.orbit_artifact(run_id, name)
            return Response(data, media_type="image/png")
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(404, "Orbit plot not found") from error

    return router
