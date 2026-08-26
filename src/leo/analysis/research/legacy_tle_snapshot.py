"""Read-only adapter for explicitly frozen legacy QNAP TLE snapshots.

The mutable archive index and nearest-snapshot selection are intentionally not
part of this adapter.  A caller supplies one exact metadata path and raw object
binding chosen before propagation; both regular files are opened with
``O_NOFOLLOW`` and verified byte-for-byte before the payload is returned.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from leo.sky.propagation import count_element_sets

SNAPSHOT_ROOT = Path("/mnt/qnap01/mouse9911/tle/snapshots/space-track/starlink")
RAW_ROOT = Path("/mnt/qnap01/mouse9911/tle/raw/space-track")


@dataclass(frozen=True, slots=True)
class FrozenLegacyTleBinding:
    metadata_path: Path
    metadata_sha256: str
    raw_path: Path
    raw_sha256: str
    raw_byte_size: int
    satellite_count: int
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class VerifiedLegacyTlePayload:
    binding: FrozenLegacyTleBinding
    text: str


class LegacyTleSnapshotReader:
    """Verify a preselected legacy snapshot without consulting an index."""

    def __init__(
        self,
        *,
        snapshot_root: Path = SNAPSHOT_ROOT,
        raw_root: Path = RAW_ROOT,
    ) -> None:
        self._snapshot_root = snapshot_root.absolute()
        self._raw_root = raw_root.absolute()

    def read(self, binding: FrozenLegacyTleBinding) -> VerifiedLegacyTlePayload:
        _require_beneath(binding.metadata_path, self._snapshot_root, ".json")
        _require_beneath(binding.raw_path, self._raw_root, ".tle")
        metadata_bytes = _read_regular_nofollow(binding.metadata_path)
        if _sha256(metadata_bytes) != binding.metadata_sha256:
            raise ValueError("legacy TLE snapshot metadata digest disagrees")
        raw_bytes = _read_regular_nofollow(binding.raw_path)
        if len(raw_bytes) != binding.raw_byte_size:
            raise ValueError("legacy TLE raw byte size disagrees")
        if _sha256(raw_bytes) != binding.raw_sha256:
            raise ValueError("legacy TLE raw digest disagrees")
        try:
            metadata = json.loads(metadata_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("legacy TLE snapshot metadata is invalid JSON") from error
        if not isinstance(metadata, dict):
            raise ValueError("legacy TLE snapshot metadata must be an object")
        expected_raw_object = f"raw/space-track/{binding.raw_sha256}.tle"
        required = {
            "schema": "leo-tracker.catalog-store-snapshot/v1",
            "source": "space-track",
            "scope": "starlink",
            "retrieved_at": binding.retrieved_at,
            "raw_object": expected_raw_object,
            "raw_sha256": binding.raw_sha256,
            "catalog_sha256": binding.raw_sha256,
            "satellite_count": binding.satellite_count,
        }
        if any(metadata.get(key) != value for key, value in required.items()):
            raise ValueError("legacy TLE snapshot metadata binding disagrees")
        try:
            text = raw_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("legacy TLE raw payload is not ASCII") from error
        if count_element_sets(text) != binding.satellite_count:
            raise ValueError("legacy TLE raw catalogue count disagrees")
        return VerifiedLegacyTlePayload(binding=binding, text=text)


def _require_beneath(path: Path, root: Path, suffix: str) -> None:
    if not path.is_absolute() or path.suffix != suffix or ".." in path.parts:
        raise ValueError("legacy TLE path is not an exact absolute artifact path")
    try:
        path.relative_to(root)
        path.parent.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError("legacy TLE path escapes its read-only authority root") from error


def _read_regular_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("legacy TLE authority is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
