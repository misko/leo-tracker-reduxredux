"""Narrow read repository used by presentation HTTP adapters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from leo.presentation.models import (
    AnalysisProductV1,
    AnalysisStateV1,
    RecordingDetailV1,
    RecordingSearchResponseV1,
    SourceTypeV1,
    StorageStateV1,
    SystemStatusV1,
)
from leo.presentation.projectors import recording_summary_v1


class PresentationRepository(Protocol):
    def search_recordings(
        self,
        *,
        query: str | None,
        include_test: bool,
        analysis_state: AnalysisStateV1 | None,
        storage_state: StorageStateV1 | None,
        held: bool | None,
        tag: str | None,
        cursor: int,
        limit: int,
    ) -> RecordingSearchResponseV1: ...

    def recording_detail(self, session_id: str) -> RecordingDetailV1 | None: ...

    def product(self, product_id: str) -> AnalysisProductV1 | None: ...

    def status(self) -> SystemStatusV1: ...


class FixturePresentationRepository:
    """Deterministic fixture-backed repository with production query semantics."""

    def __init__(
        self,
        recordings: Sequence[RecordingDetailV1],
        status: SystemStatusV1,
    ) -> None:
        self._recordings = tuple(recordings)
        self._by_session = {item.session_id: item for item in recordings}
        if len(self._by_session) != len(self._recordings):
            raise ValueError("fixture recording session IDs must be unique")
        products = [product for item in recordings for product in item.products]
        self._products = {item.product_id: item for item in products}
        if len(self._products) != len(products):
            raise ValueError("fixture product IDs must be unique")
        self._status = status

    def search_recordings(
        self,
        *,
        query: str | None,
        include_test: bool,
        analysis_state: AnalysisStateV1 | None,
        storage_state: StorageStateV1 | None,
        held: bool | None,
        tag: str | None,
        cursor: int,
        limit: int,
    ) -> RecordingSearchResponseV1:
        needle = query.casefold().strip() if query else None
        matches = []
        for detail in self._recordings:
            if detail.source_type is SourceTypeV1.TEST and not include_test:
                continue
            if analysis_state is not None and detail.analysis.state is not analysis_state:
                continue
            if storage_state is not None and detail.storage_state is not storage_state:
                continue
            if held is not None and detail.hold.held is not held:
                continue
            if tag is not None and tag not in detail.tags:
                continue
            if (
                needle
                and needle
                not in " ".join(
                    (detail.session_id, detail.title, detail.profile.name, *detail.tags)
                ).casefold()
            ):
                continue
            matches.append(recording_summary_v1(detail))
        ordered = sorted(matches, key=lambda item: item.started_at, reverse=True)
        selected = tuple(ordered[cursor : cursor + limit])
        candidate_cursor = cursor + len(selected)
        next_cursor = candidate_cursor if candidate_cursor < len(ordered) else None
        return RecordingSearchResponseV1(
            items=selected,
            total=len(ordered),
            next_cursor=next_cursor,
        )

    def recording_detail(self, session_id: str) -> RecordingDetailV1 | None:
        return self._by_session.get(session_id)

    def product(self, product_id: str) -> AnalysisProductV1 | None:
        return self._products.get(product_id)

    def status(self) -> SystemStatusV1:
        return self._status
