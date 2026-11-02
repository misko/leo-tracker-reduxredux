"""Read-only standard ALGO07 result and digest-bound figure routes."""
from fastapi import APIRouter, HTTPException, Response


def standard_analysis_router(reader):
    router=APIRouter(prefix='/api/v2/fast-scans')

    @router.get('/{run_id}/standard-analysis')
    def detail(run_id: str):
        try:
            return reader.detail(run_id)
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard analysis not found') from error

    @router.get('/{run_id}/standard-analysis/{name}.png')
    def figure(run_id: str,name: str,sha256: str | None=None):
        try:
            data=reader.artifact(run_id,name,sha256)
            return Response(data,media_type='image/png',headers={'Cache-Control':'public, max-age=31536000, immutable'} if sha256 else {'Cache-Control':'no-cache'})
        except (OSError,ValueError) as error:
            raise HTTPException(404,'Standard figure not found') from error
    return router
