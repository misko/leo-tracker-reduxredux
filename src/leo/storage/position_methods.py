"""Immutable position-method sidecars in a pinned local namespace."""

from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager, suppress
from pathlib import Path

from pydantic import TypeAdapter

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.position_methods import (
    POSITION_METHODS,
    PositionMethod,
    PositionMethodArtifactV1,
    PositionMethodsDocumentV1,
    PositionMethodsManifestV1,
    PositionMethodsStatusV1,
    SessionId,
)
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.pinned import PinnedLocalRoot

_LIMIT = 16 * 1024 * 1024


class PositionMethodsStore:
    def __init__(self, root: Path, *, read_only: bool = True):
        resolved = root.resolve()
        if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
            raise ValueError("position method sidecars cannot use QNAP")
        self.root = root
        self.read_only = read_only

    @contextmanager
    def _directory(self, session_id: str, *, create: bool = False):
        TypeAdapter(SessionId).validate_python(session_id)
        if create and self.read_only:
            raise PermissionError("position method store is read-only")
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child("scanner-position-methods-v1", session_id, create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def status(self, session_id: str) -> PositionMethodsStatusV1:
        try:
            with self._directory(session_id) as directory:
                manifest = _unseal(
                    _read(directory, "manifest.json", _LIMIT), PositionMethodsManifestV1
                )
        except FileNotFoundError:
            return PositionMethodsStatusV1(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return PositionMethodsStatusV1(session_id=session_id)
            raise
        if manifest.document.session_id != session_id:
            raise ValueError("position method session binding differs")
        expected = canonical_json_bytes(manifest.document.model_dump(mode="json"))
        with self._directory(session_id) as directory:
            raw = _read(directory, "document.json", _LIMIT)
        if raw != expected or sha256_digest(raw) != manifest.document_sha256:
            raise ValueError("position method document digest differs")
        return PositionMethodsStatusV1(
            session_id=session_id, state="complete", manifest=manifest
        )

    def complete(self, session_id: str) -> bool:
        return self.status(session_id).state == "complete"

    @contextmanager
    def writer(self, session_id: str):
        """Serialize cohort selection and publication for one capture."""
        if self.read_only:
            raise PermissionError("position method store is read-only")
        with self._directory(session_id, create=True) as directory:
            descriptor = os.open(
                ".writer.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o640,
                dir_fd=directory.fileno(),
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size:
                    raise ValueError("position method writer lock is invalid")
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield self
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def publish(
        self, document: PositionMethodsDocumentV1, images: dict[str, bytes]
    ) -> PositionMethodsManifestV1:
        document = PositionMethodsDocumentV1.model_validate(document.model_dump())
        if set(images) != set(POSITION_METHODS):
            raise ValueError("position method image inventory differs")
        raw_document = canonical_json_bytes(document.model_dump(mode="json"))
        references = []
        members: list[tuple[str, bytes]] = [("document.json", raw_document)]
        for method in POSITION_METHODS:
            payload = images[method]
            if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("position method artifact is not a PNG")
            reference = PositionMethodArtifactV1(
                method=method, sha256=sha256_digest(payload), byte_count=len(payload)
            )
            references.append(reference)
            members.append((method + ".png", payload))
        manifest = PositionMethodsManifestV1(
            document=document,
            document_sha256=sha256_digest(raw_document),
            artifacts=tuple(references),
        )
        members.append(("manifest.json", _seal(manifest)))
        with self._directory(document.session_id, create=True) as directory:
            try:
                published = _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                published = None
            if published is not None:
                if published != members[-1][1]:
                    raise ValueError("immutable position method publication conflict")
                return manifest
            for name, payload in members:
                if name == "manifest.json":
                    _publish(directory, name, payload, _LIMIT)
                else:
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
            os.fsync(directory.fileno())
        return manifest

    def artifact(self, session_id: str, method: PositionMethod) -> bytes | None:
        if method not in POSITION_METHODS:
            raise ValueError("unsupported position method")
        status = self.status(session_id)
        if status.manifest is None:
            return None
        reference = next(item for item in status.manifest.artifacts if item.method == method)
        with self._directory(session_id) as directory:
            payload = _read(directory, method + ".png", _LIMIT)
        if len(payload) != reference.byte_count or sha256_digest(payload) != reference.sha256:
            raise ValueError("position method PNG digest differs")
        return payload
