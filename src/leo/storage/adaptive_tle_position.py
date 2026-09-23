"""Immutable adaptive TLE position sidecars in a pinned local namespace."""

from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager, suppress
from pathlib import Path

from pydantic import TypeAdapter

from leo.contracts.adaptive_tle_position import (
    AdaptiveTleArtifactV1,
    AdaptiveTlePositionDocumentV1,
    AdaptiveTlePositionManifestV1,
    AdaptiveTlePositionStatusV1,
    SessionId,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.pinned import PinnedLocalRoot

_LIMIT = 16 * 1024 * 1024


class AdaptiveTlePositionStore:
    def __init__(self, root: Path, *, read_only: bool = True):
        resolved = root.resolve()
        if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
            raise ValueError("adaptive TLE position evidence cannot use QNAP")
        self.root, self.read_only = root, read_only

    @contextmanager
    def _directory(self, session_id: str, *, create: bool = False):
        TypeAdapter(SessionId).validate_python(session_id)
        if create and self.read_only:
            raise PermissionError("adaptive TLE position store is read-only")
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child("scanner-adaptive-tle-position-v1", session_id, create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def status(self, session_id: str) -> AdaptiveTlePositionStatusV1:
        try:
            with self._directory(session_id) as directory:
                manifest = _unseal(
                    _read(directory, "manifest.json", _LIMIT), AdaptiveTlePositionManifestV1
                )
                raw = _read(directory, "document.json", _LIMIT)
            if raw != canonical_json_bytes(manifest.document.model_dump(mode="json")):
                raise ValueError("adaptive TLE position document encoding differs")
            if sha256_digest(raw) != manifest.document_sha256:
                raise ValueError("adaptive TLE position document digest differs")
            return AdaptiveTlePositionStatusV1(
                session_id=session_id, state="complete", manifest=manifest
            )
        except FileNotFoundError:
            return AdaptiveTlePositionStatusV1(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return AdaptiveTlePositionStatusV1(session_id=session_id)
            raise

    @contextmanager
    def writer(self, session_id: str):
        if self.read_only:
            raise PermissionError("adaptive TLE position store is read-only")
        with self._directory(session_id, create=True) as directory:
            descriptor = os.open(
                ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640,
                dir_fd=directory.fileno(),
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size:
                    raise ValueError("adaptive TLE position writer lock is invalid")
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield self
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def publish(self, document: AdaptiveTlePositionDocumentV1, image: bytes):
        if self.read_only:
            raise PermissionError("adaptive TLE position store is read-only")
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("adaptive TLE position artifact is not PNG")
        raw = canonical_json_bytes(document.model_dump(mode="json"))
        manifest = AdaptiveTlePositionManifestV1(
            document=document,
            document_sha256=sha256_digest(raw),
            artifacts=(AdaptiveTleArtifactV1(sha256=sha256_digest(image), byte_count=len(image)),),
        )
        sealed = _seal(manifest)
        with self._directory(document.session_id, create=True) as directory:
            try:
                existing = _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if existing != sealed:
                    raise ValueError("immutable adaptive TLE position publication conflict")
                return manifest
            for name, payload in (("document.json", raw), ("map.png", image)):
                temporary = f".{name}.{os.getpid()}.partial"
                try:
                    _publish(directory, temporary, payload, _LIMIT)
                    os.replace(
                        temporary,
                        name,
                        src_dir_fd=directory.fileno(),
                        dst_dir_fd=directory.fileno(),
                    )
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary, dir_fd=directory.fileno())
            _publish(directory, "manifest.json", sealed, _LIMIT)
            os.fsync(directory.fileno())
        return manifest

    def artifact(self, session_id: str) -> bytes | None:
        status = self.status(session_id)
        if status.manifest is None:
            return None
        with self._directory(session_id) as directory:
            payload = _read(directory, "map.png", _LIMIT)
        reference = status.manifest.artifacts[0]
        if len(payload) != reference.byte_count or sha256_digest(payload) != reference.sha256:
            raise ValueError("adaptive TLE position PNG digest differs")
        return payload
