"""Immutable on-disk cache for verified Standard presentation PNGs."""

from __future__ import annotations

import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PNG_BYTES = 32 * 1024 * 1024


class StandardPngDiskCache:
    """Create-once PNG cache rooted beneath approved local analysis storage."""

    def __init__(self, bulk_root: Path) -> None:
        if not bulk_root.is_absolute() or str(bulk_root).startswith("/mnt/qnap01"):
            raise ValueError("PNG cache requires an approved absolute local bulk root")
        root = bulk_root / "presentation-cache"
        root.mkdir(mode=0o750, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("PNG cache root must be a real directory")
        self._root = root

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= _MAX_PNG_BYTES
        ):
            raise ValueError("cached PNG inode is invalid")
        payload = path.read_bytes()
        if len(payload) != metadata.st_size or not payload.startswith(_PNG_SIGNATURE):
            raise ValueError("cached PNG bytes are invalid")
        return payload

    def publish(self, key: str, payload: bytes) -> bytes:
        if not payload.startswith(_PNG_SIGNATURE) or not 0 < len(payload) <= _MAX_PNG_BYTES:
            raise ValueError("rendered PNG bytes are invalid")
        destination = self._path(key)
        existing = self.read(key)
        if existing is not None:
            return existing
        temporary = self._root / f".{key}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o640,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            with suppress(FileExistsError):
                os.link(temporary, destination, follow_symlinks=False)
            directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        cached = self.read(key)
        if cached is None:
            raise RuntimeError("PNG cache publication did not create its destination")
        return cached

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("PNG cache key must be a lowercase SHA-256 digest")
        return self._root / f"{key}.png"
