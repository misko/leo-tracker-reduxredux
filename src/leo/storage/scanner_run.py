"""Atomic local publication for long-form scanner run manifests."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.schedule import ScannerRunManifestV1
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _fsync_directory, _mkdir_durable

_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class PublishedScannerRun:
    run_id: str
    path: Path
    uri: str
    manifest: ScannerRunManifestV1
    manifest_sha256: str


class ScannerRunStore:
    """Own terminal scanner run evidence beneath the local bulk root."""

    def __init__(self, root: Path) -> None:
        if root == Path("/mnt/qnap01") or str(root).startswith("/mnt/qnap01/"):
            raise ValueError("scanner runs cannot be written beneath QNAP")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        if self.root == Path("/mnt/qnap01") or str(self.root).startswith("/mnt/qnap01/"):
            raise ValueError("scanner runs cannot be written beneath QNAP")
        self.spool_root = self.root / "spool"
        self.runs_root = self.root / "scanner-runs"
        self.spool_root.mkdir(exist_ok=True)
        self.runs_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.runs_root).st_dev:
            raise ValueError("scanner run spool and destination must share one filesystem")
        self.resolver = BulkUriResolver(self.root, allowed_namespaces=("scanner-runs",))

    def publish(self, manifest: ScannerRunManifestV1) -> PublishedScannerRun:
        payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        spool = (
            self.spool_root / f"{manifest.run_id}.{os.getpid()}.{uuid4().hex}.scanner-run.partial"
        )
        spool.mkdir(exist_ok=False)
        try:
            _fsync_directory(self.spool_root)
            partial = spool / "manifest.json.partial"
            with partial.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(partial, spool / "manifest.json")
            _fsync_directory(spool)
            started = datetime.fromtimestamp(manifest.started_utc_ns / 1_000_000_000, tz=UTC)
            parent = (
                self.runs_root
                / f"{started.year:04d}"
                / f"{started.month:02d}"
                / f"{started.day:02d}"
            )
            _mkdir_durable(parent, stop=self.runs_root)
            destination = parent / manifest.run_id
            if destination.exists():
                raise FileExistsError(f"scanner run already exists: {destination}")
            os.rename(spool, destination)
            _fsync_directory(parent)
            return PublishedScannerRun(
                run_id=manifest.run_id,
                path=destination,
                uri=self.resolver.uri_for(destination),
                manifest=manifest,
                manifest_sha256=sha256_digest(payload),
            )
        finally:
            if spool.exists():
                for member in spool.iterdir():
                    member.unlink()
                spool.rmdir()

    def inspect(self, run_id: str) -> PublishedScannerRun:
        if not _IDENTIFIER.fullmatch(run_id):
            raise ValueError("scanner run ID is not one safe persisted identifier")
        matches = tuple(self.runs_root.glob(f"*/*/*/{run_id}"))
        if not matches:
            raise BundleNotFoundError(f"scanner run does not exist: {run_id}")
        if len(matches) != 1:
            raise BundleCorruptionError(f"scanner run appears more than once: {run_id}")
        path = confined_path(self.runs_root, matches[0], must_exist=True)
        manifest_path = path / "manifest.json"
        descriptor = os.open(manifest_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or not 0 < metadata.st_size <= _MAX_MANIFEST_BYTES
            ):
                raise BundleCorruptionError("scanner run manifest inode is invalid")
            chunks: list[bytes] = []
            remaining = metadata.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if len(payload) != metadata.st_size or (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise BundleCorruptionError("scanner run manifest changed while reading")
        finally:
            os.close(descriptor)
        try:
            manifest = ScannerRunManifestV1.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner run manifest: {error}") from error
        if manifest.run_id != run_id:
            raise BundleCorruptionError("scanner run manifest ID disagrees with its path")
        return PublishedScannerRun(
            run_id=run_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )
