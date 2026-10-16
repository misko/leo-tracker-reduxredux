"""Read-only access to separately versioned fast scan orbit PNGs."""

from fastapi import APIRouter, HTTPException, Response


def fast_scan_orbit_router(store):
    router = APIRouter(prefix="/api/v1/fast-scans")

    @router.get("/{run_id}/orbits")
    def manifest(run_id: str):
        try:
            return store.orbit_manifest(run_id) if store else {"artifacts": []}
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(404, "Orbit plots not found") from error

    @router.get("/{run_id}/orbits/{name}.png")
    def png(run_id: str, name: str):
        try:
            if store is None:
                raise FileNotFoundError(run_id)
            data = store.orbit_artifact(run_id, name)
            return Response(data, media_type="image/png")
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(404, "Orbit plot not found") from error

    return router
