"""Read-only projection of the latest locally published scanner report."""

from __future__ import annotations

import stat
from pathlib import Path

from leo.scanner import ScannerReport

_REPORT_GLOB = "starlink-scan-*.json"
_MAXIMUM_REPORT_BYTES = 4 * 1024 * 1024


class ScannerReportStore:
    """Load the newest bounded scanner report without constructing QNAP paths."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute() or str(root).startswith("/mnt/qnap01"):
            raise ValueError("scanner report store requires an approved local root")
        self._root = root

    def latest(self) -> ScannerReport | None:
        try:
            root_metadata = self._root.lstat()
        except FileNotFoundError:
            return None
        if self._root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
            raise ValueError("scanner report root must be a real directory")
        reports = sorted(self._root.glob(_REPORT_GLOB), reverse=True)
        if not reports:
            return None
        return ScannerReport.model_validate_json(self._read_regular(reports[0]))

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
