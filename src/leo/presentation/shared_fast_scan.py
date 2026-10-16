"""Read-only port for versioned fast-scan shared-model results."""

from typing import Protocol


class SharedFastScanReader(Protocol):
    def page(self, limit: int = 100) -> dict: ...

    def detail(self, job_id: str) -> dict: ...
