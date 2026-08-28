"""Read-only projections of locally published scanner reports."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from leo.scanner import (
    ScannerAnalysisHistoryPageV1,
    ScannerAnalysisHistoryPageV2,
    ScannerAnalysisHistoryPageV3,
    ScannerCaptureReportLike,
    ScannerReport,
    ScannerReportLike,
    ScannerReportV2,
    ScannerReportV3,
    ScannerReportV4,
)

_REPORT_GLOB = "starlink-scan-*.json"
_MAXIMUM_REPORT_BYTES = 4 * 1024 * 1024
_REPORT_PREFIX = "starlink-scan-"
_REPORT_SUFFIX = ".json"
_REPORT_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_REPORT_STAMP_LENGTH = len("20260821T201339Z")


class ScannerHistoryItemV1(BaseModel):
    """One timestamped immutable scanner report selected from the archive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    scanned_at: datetime
    report: ScannerReport


class ScannerHistoryPageV1(BaseModel):
    """A deterministic newest-first scanner-history page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[ScannerHistoryItemV1, ...]


class ScannerHistoryItemV2(BaseModel):
    """One immutable scanner report supporting both capture contract versions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    scanned_at: datetime
    report: ScannerReportLike


class ScannerHistoryPageV2(BaseModel):
    """Additive scanner history page supporting metadata-attested reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[ScannerHistoryItemV2, ...]


class ScannerHistoryItemV3(BaseModel):
    """One immutable scanner report including terminal close failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[3] = 3
    scanned_at: datetime
    report: ScannerCaptureReportLike


class ScannerHistoryPageV3(BaseModel):
    """Current scanner attempt history, including failed capture products."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[3] = 3
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
    next_cursor: int | None
    items: tuple[ScannerHistoryItemV3, ...]


class ScannerReportStore:
    """Load the newest bounded scanner report without constructing QNAP paths."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute() or str(root).startswith("/mnt/qnap01"):
            raise ValueError("scanner report store requires an approved local root")
        self._root = root

    def latest(self) -> ScannerReport | None:
        """Return the newest V1 report without exposing additive report versions.

        V1 remains a stable projection after V2/V3 publication begins. Files
        that cannot be safely classified remain visible to V1 and fail when
        selected; a corrupt product can therefore never be hidden by the
        compatibility filter.
        """

        reports = self._v1_reports()
        if not reports:
            return None
        return ScannerReport.model_validate_json(self._read_regular(reports[0]))

    def latest_v2(self) -> ScannerReportLike | None:
        """Return the latest V1/V2 report, ignoring additive V3 attempts."""

        for path in self._ordered_reports():
            payload = self._read_regular(path)
            if self._schema_version(payload) in (3, 4):
                self._parse_current(payload)
                continue
            return self._parse_versioned(payload)
        return None

    def latest_v3(self) -> ScannerCaptureReportLike | None:
        """Return the latest attempt, including structured terminal failures."""

        reports = self._ordered_reports()
        if not reports:
            return None
        return self._parse_current(self._read_regular(reports[0]))

    def page(self, *, cursor: int, limit: int) -> ScannerHistoryPageV1:
        """Read one bounded newest-first page, never parsing unselected reports."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner history page is outside its bounded range")
        reports = self._v1_reports()
        selected = reports[cursor : cursor + limit]
        items = tuple(
            ScannerHistoryItemV1(
                scanned_at=self._timestamp(path),
                report=ScannerReport.model_validate_json(self._read_regular(path)),
            )
            for path in selected
        )
        next_cursor = cursor + len(items) if cursor + len(items) < len(reports) else None
        return ScannerHistoryPageV1(
            cursor=cursor,
            limit=limit,
            total=len(reports),
            next_cursor=next_cursor,
            items=items,
        )

    def _v1_reports(self) -> list[Path]:
        """Return reports visible through the immutable V1 projection.

        A valid V2/V3 document is intentionally absent from V1 pagination.
        Invalid JSON, unsafe inodes, and unsupported schemas remain candidates
        so the legacy endpoint still fails closed if the caller selects them.
        """

        visible: list[Path] = []
        for path in self._ordered_reports():
            try:
                payload = self._read_regular(path)
                schema_version = self._schema_version(payload)
                if schema_version in (2, 3, 4):
                    self._parse_current(payload)
            except (OSError, ValueError):
                visible.append(path)
                continue
            if schema_version not in (2, 3, 4):
                visible.append(path)
        return visible

    def page_v2(self, *, cursor: int, limit: int) -> ScannerHistoryPageV2:
        """Read V1/V2 history without downconverting or exposing additive V3."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner history page is outside its bounded range")
        reports: list[tuple[Path, bytes]] = []
        for path in self._ordered_reports():
            payload = self._read_regular(path)
            if self._schema_version(payload) in (3, 4):
                self._parse_current(payload)
                continue
            reports.append((path, payload))
        selected = reports[cursor : cursor + limit]
        items = tuple(
            ScannerHistoryItemV2(
                scanned_at=self._timestamp(path),
                report=self._parse_versioned(payload),
            )
            for path, payload in selected
        )
        next_cursor = cursor + len(items) if cursor + len(items) < len(reports) else None
        return ScannerHistoryPageV2(
            cursor=cursor,
            limit=limit,
            total=len(reports),
            next_cursor=next_cursor,
            items=items,
        )

    def page_v3(self, *, cursor: int, limit: int) -> ScannerHistoryPageV3:
        """Read current attempt history without hiding capture-failure products."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner history page is outside its bounded range")
        reports = self._ordered_reports()
        selected = reports[cursor : cursor + limit]
        items = tuple(
            ScannerHistoryItemV3(
                scanned_at=self._timestamp(path),
                report=self._parse_current(self._read_regular(path)),
            )
            for path in selected
        )
        next_cursor = cursor + len(items) if cursor + len(items) < len(reports) else None
        return ScannerHistoryPageV3(
            cursor=cursor,
            limit=limit,
            total=len(reports),
            next_cursor=next_cursor,
            items=items,
        )

    @staticmethod
    def _schema_version(payload: bytes) -> object:
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("scanner report is not valid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("scanner report must be a JSON object")
        return document.get("schema_version")

    @staticmethod
    def _parse_versioned(payload: bytes) -> ScannerReportLike:
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("scanner report is not valid JSON") from error
        schema_version = document.get("schema_version")
        if schema_version == 1:
            return ScannerReport.model_validate(document)
        if schema_version == 2:
            return ScannerReportV2.model_validate(document)
        raise ValueError(f"unsupported scanner report schema {schema_version!r}")

    @staticmethod
    def _parse_current(payload: bytes) -> ScannerCaptureReportLike:
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("scanner report is not valid JSON") from error
        schema_version = document.get("schema_version")
        if schema_version == 1:
            return ScannerReport.model_validate(document)
        if schema_version == 2:
            return ScannerReportV2.model_validate(document)
        if schema_version == 3:
            return ScannerReportV3.model_validate(document)
        if schema_version == 4:
            return ScannerReportV4.model_validate(document)
        raise ValueError(f"unsupported scanner report schema {schema_version!r}")

    def _ordered_reports(self) -> list[Path]:
        try:
            root_metadata = self._root.lstat()
        except FileNotFoundError:
            return []
        if self._root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise ValueError("scanner report root must be a real directory")
        # Directory enumeration and filename ordering are metadata-only. Report
        # bodies are read and validated only after pagination selects them.
        return sorted(self._root.glob(_REPORT_GLOB), reverse=True)

    @staticmethod
    def _timestamp(path: Path) -> datetime:
        name = path.name
        if not name.startswith(_REPORT_PREFIX) or not name.endswith(_REPORT_SUFFIX):
            raise ValueError("scanner report filename is invalid")
        stem = name[len(_REPORT_PREFIX) : -len(_REPORT_SUFFIX)]
        stamp = stem[:_REPORT_STAMP_LENGTH]
        suffix = stem[_REPORT_STAMP_LENGTH:]
        if suffix and not suffix.startswith("-"):
            raise ValueError("scanner report filename timestamp is invalid")
        try:
            return datetime.strptime(stamp, _REPORT_STAMP_FORMAT).replace(tzinfo=UTC)
        except ValueError as error:
            raise ValueError("scanner report filename timestamp is invalid") from error

    @staticmethod
    def _read_regular(path: Path) -> bytes:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= _MAXIMUM_REPORT_BYTES
        ):
            raise ValueError("scanner report inode is invalid")
        payload = path.read_bytes()
        after = path.stat(follow_symlinks=False)
        if len(payload) != metadata.st_size or (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("scanner report changed while it was read")
        return payload


class ScannerAnalysisReader(Protocol):
    """Narrow read port for already-published Standard scanner products."""

    def page(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV1: ...

    def page_v2(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV2: ...

    def page_v3(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV3: ...

    def artifact(
        self,
        scan_id: str,
        analysis_id: str,
        artifact: Literal[
            "waterfall",
            "glrt64",
            "pilot-doppler",
            "pilot-carrier-tracking",
            "pilot-segment-rates",
        ],
    ) -> bytes | None: ...
