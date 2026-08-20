"""Read-only access to the locally collected TLE archive.

The collector in :mod:`leo.operations.tle_collector` writes immutable snapshots
to ``<root>/archive/<provider>/<collected_utc_ns>-<sha256>.tle``.  This reader
never writes, never deletes, and never repairs; it resolves one snapshot,
re-verifies its digest against the name it was stored under, and hands back the
bytes.

Failure is always explicit.  A tampered, truncated, unreadable or absent
snapshot raises :class:`TleArchiveError` rather than degrading to an empty
constellation, because an empty sky and an unavailable sky are different claims
and only one of them is honest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = ("space-track", "huggingface")

# The collector bounds each response to 16 MiB; a stored snapshot cannot exceed
# it, and refusing anything larger keeps a corrupted directory from being read
# into memory.
MAXIMUM_SNAPSHOT_BYTES = 16 * 1024 * 1024

_SNAPSHOT_NAME = re.compile(r"^(?P<collected>\d{1,19})-(?P<digest>[0-9a-f]{64})\.tle$")


class TleArchiveError(RuntimeError):
    """The requested snapshot could not be resolved or verified."""


@dataclass(frozen=True, slots=True, order=True)
class TleSnapshotRef:
    """One immutable archived snapshot, identified by collection time and digest."""

    collected_utc_ns: int
    provider: str
    sha256: str
    byte_size: int
    path: Path

    @property
    def digest(self) -> str:
        """The digest in the repository's canonical ``sha256:`` form."""

        return f"sha256:{self.sha256}"


class TleArchiveReader:
    """Resolve and verify snapshots beneath one archive root."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def list_snapshots(self, provider: str | None = None) -> tuple[TleSnapshotRef, ...]:
        """Return every well-formed snapshot, oldest first.

        A file whose name does not match the collector's format is ignored
        rather than guessed at: the collector is the only writer, so an
        unrecognised name is not a snapshot.
        """

        providers = self._requested_providers(provider)
        found: list[TleSnapshotRef] = []
        for name in providers:
            directory = self._root / "archive" / name
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                match = _SNAPSHOT_NAME.match(entry.name)
                if match is None or not entry.is_file():
                    continue
                found.append(
                    TleSnapshotRef(
                        collected_utc_ns=int(match["collected"]),
                        provider=name,
                        sha256=match["digest"],
                        byte_size=entry.stat().st_size,
                        path=entry,
                    )
                )
        return tuple(sorted(found))

    def select_nearest(self, anchor_utc_ns: int, provider: str | None = None) -> TleSnapshotRef:
        """Resolve the snapshot collected closest to ``anchor_utc_ns``.

        Element-set accuracy decays with age in both directions, so nearest is
        preferred over most-recent.  Ties break towards the earlier snapshot and
        then by digest, keeping the choice reproducible.
        """

        snapshots = self.list_snapshots(provider)
        if not snapshots:
            raise TleArchiveError(
                f"no TLE snapshot is available beneath {self._root}"
                + ("" if provider is None else f" for provider {provider!r}")
            )
        return min(
            snapshots,
            key=lambda item: (
                abs(item.collected_utc_ns - anchor_utc_ns),
                item.collected_utc_ns,
                item.sha256,
            ),
        )

    def read(self, snapshot: TleSnapshotRef) -> str:
        """Return the snapshot text after re-verifying its digest.

        The digest is recomputed on every read rather than trusted from the
        file name, so silent corruption after collection is caught at the point
        of use.
        """

        if snapshot.byte_size > MAXIMUM_SNAPSHOT_BYTES:
            raise TleArchiveError(
                f"TLE snapshot {snapshot.path.name} exceeds the {MAXIMUM_SNAPSHOT_BYTES} byte bound"
            )
        try:
            payload = snapshot.path.read_bytes()
        except OSError as error:
            raise TleArchiveError(f"TLE snapshot {snapshot.path.name} is unreadable") from error
        if len(payload) > MAXIMUM_SNAPSHOT_BYTES:
            raise TleArchiveError(
                f"TLE snapshot {snapshot.path.name} exceeds the {MAXIMUM_SNAPSHOT_BYTES} byte bound"
            )
        observed = hashlib.sha256(payload).hexdigest()
        if observed != snapshot.sha256:
            raise TleArchiveError(
                f"TLE snapshot {snapshot.path.name} does not match its recorded digest"
            )
        try:
            return payload.decode("ascii")
        except UnicodeDecodeError as error:
            raise TleArchiveError(
                f"TLE snapshot {snapshot.path.name} is not ASCII element-set data"
            ) from error

    def _requested_providers(self, provider: str | None) -> tuple[str, ...]:
        if provider is None:
            return PROVIDERS
        if provider not in PROVIDERS:
            raise TleArchiveError(f"unsupported TLE provider: {provider!r}")
        return (provider,)
