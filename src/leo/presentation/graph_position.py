"""Narrow read-only port for explicitly selected graph localization."""

from typing import Protocol


class GraphPositions(Protocol):
    def detail(self, run_id: str) -> dict: ...
