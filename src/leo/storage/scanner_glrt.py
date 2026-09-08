"""Atomic, additive GLRT publications; never modifies an IQ bundle or QNAP."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Self
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.scanner_glrt_publication import GLRT_SESSION_PATTERN, ScannerGlrtPublicationV1
from leo.scanner.glrt_publication import validate_glrt_capture_binding
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.pinned import PinnedLocalRoot

_NAMESPACE = "scanner-hop-classifications"
_MAX_BYTES = 4 * 1024 * 1024


class ScannerGlrtStore:
    """One immutable, checksummed JSON file per captured session.

    Root must already exist. No-follow directory capabilities are opened per
    operation; read-only use creates nothing, including when no results exist.
    Atomic hard-link publication cannot overwrite a concurrent writer's result.
    """

    def __init__(self, root: Path) -> None:
        self._configure(root, writable=True)

    @classmethod
    def open_read_only(cls, root: Path) -> Self:
        store = cls.__new__(cls)
        store._configure(root, writable=False)
        return store

    def _configure(self, root: Path, *, writable: bool) -> None:
        self.root = Path(os.path.abspath(root))
        pin = PinnedLocalRoot(self.root)
        pin.close()
        self._writable = writable

    @staticmethod
    def _name(session_id: str) -> str:
        if not re.fullmatch(GLRT_SESSION_PATTERN, session_id):
            raise ValueError("unsafe GLRT session identifier")
        return f"{session_id}.v1.json"

    def publish(self, publication: ScannerGlrtPublicationV1) -> None:
        if not self._writable:
            raise PermissionError("GLRT store is read-only")
        publication = ScannerGlrtPublicationV1.model_validate(publication.model_dump())
        name = self._name(publication.session_id)
        body = publication.model_dump(mode="json")
        payload = canonical_json_bytes(
            {
                "publication": body,
                "sha256": sha256_digest(canonical_json_bytes(body)),
            }
        )
        if len(payload) > _MAX_BYTES:
            raise ValueError("GLRT publication exceeds its byte bound")
        root = PinnedLocalRoot(self.root)
        namespace = None
        temporary = f".{name}.{uuid4().hex}.partial"
        created = False
        try:
            namespace = root.child(_NAMESPACE, create=True)
            fd = namespace.fileno()
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=fd
            )
            created = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                if self._read(namespace, name) != publication:
                    raise BundleCorruptionError(
                        "GLRT publication already exists and differs"
                    ) from None
            os.fsync(fd)
            os.fsync(root.fileno())
        finally:
            if namespace is not None:
                try:
                    if created:
                        os.unlink(temporary, dir_fd=namespace.fileno())
                finally:
                    namespace.close()
            root.close()

    def read(self, session_id: str) -> ScannerGlrtPublicationV1 | None:
        name = self._name(session_id)
        root = PinnedLocalRoot(self.root)
        namespace = None
        try:
            # Distinguish a genuinely absent namespace from a symlink/access
            # failure. PinnedLocalRoot deliberately reports the latter strictly.
            try:
                os.stat(_NAMESPACE, dir_fd=root.fileno(), follow_symlinks=False)
            except FileNotFoundError:
                return None
            namespace = root.child(_NAMESPACE)
            try:
                publication = self._read(namespace, name)
            except FileNotFoundError:
                return None
            if publication.session_id != session_id:
                raise BundleCorruptionError("GLRT publication filename disagrees with identity")
            return publication
        finally:
            if namespace is not None:
                namespace.close()
            root.close()

    @staticmethod
    def _read(namespace: PinnedLocalRoot, name: str) -> ScannerGlrtPublicationV1:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=namespace.fileno()
        )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_BYTES:
                raise BundleCorruptionError("GLRT publication is not a bounded regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise BundleCorruptionError("GLRT publication grew beyond its byte bound")
            sealed = json.loads(raw)
            if (
                not isinstance(sealed, dict)
                or set(sealed) != {"publication", "sha256"}
                or sealed["sha256"] != sha256_digest(canonical_json_bytes(sealed["publication"]))
            ):
                raise ValueError("publication checksum differs")
            return ScannerGlrtPublicationV1.model_validate(sealed["publication"])
        except (ValueError, TypeError, KeyError) as error:
            raise BundleCorruptionError("GLRT publication is corrupt") from error
        finally:
            os.close(descriptor)


class ScannerGlrtPresentationStore:
    """Serve only evidence bound to the currently published public IQ manifest."""

    def __init__(self, iq: PersistentHopIqStore, classifications: ScannerGlrtStore):
        self._iq = iq
        self._classifications = classifications

    def detail(self, session_id: str) -> ScannerGlrtPublicationV1 | None:
        publication = self._classifications.read(session_id)
        if publication is None:
            return None
        try:
            capture = self._iq.inspect(session_id)
        except BundleNotFoundError:
            return None
        validate_glrt_capture_binding(
            publication, capture.manifest.receipt, input_manifest_sha256=capture.manifest_sha256
        )
        return publication
