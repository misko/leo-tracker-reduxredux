"""Separately versioned graph positions never masquerade as shared-q output."""

from fastapi import APIRouter, HTTPException

from leo.presentation.graph_position import GraphPositions


def graph_position_router(reader: GraphPositions | None):
    router = APIRouter(prefix="/api/v2/fast-scans")

    @router.get("/{run_id}/graph-position")
    def position(run_id: str):
        if reader is None:
            return dict(state="disabled", selected_model=None)
        try:
            return reader.detail(run_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(404, "Graph position not found") from error

    return router
