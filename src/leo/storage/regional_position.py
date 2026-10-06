"""Verified, immutable T1AT/V16 products in a pinned local namespace."""

import os
from contextlib import suppress
from pathlib import Path
from typing import Literal

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.regional_position_products import (
    RegionalArtifactV1,
    RegionalPositionDocumentV1,
    RegionalPositionManifestV1,
    RegionalPositionStatusV1,
)
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore

_LIMIT = 16 * 1024 * 1024
_METHODS: tuple[Literal["T1AT", "V16"], ...] = ("T1AT", "V16")


class RegionalPositionStore:
    """Reuse the storage component's pinned-directory and writer-lock machinery."""

    namespace = "scanner-regional-position-v1"

    def __init__(self, root: Path, *, read_only: bool = True):
        self.read_only = read_only
        self._backing = AdaptiveTlePositionStore(root, read_only=read_only)
        self._backing.namespace = self.namespace

    def _directory(self, session_id: str, *, create: bool = False):
        return self._backing._directory(session_id, create=create)

    def status(self, session_id: str) -> RegionalPositionStatusV1:
        try:
            with self._directory(session_id) as directory:
                manifest = _unseal(
                    _read(directory, "manifest.json", _LIMIT), RegionalPositionManifestV1
                )
                raw = _read(directory, "document.json", _LIMIT)
            if raw != canonical_json_bytes(manifest.document.model_dump(mode="json")):
                raise ValueError("regional position document encoding differs")
            return RegionalPositionStatusV1(
                session_id=session_id, state="complete", manifest=manifest
            )
        except FileNotFoundError:
            return RegionalPositionStatusV1(session_id=session_id)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return RegionalPositionStatusV1(session_id=session_id)
            raise

    def publish(self, document: RegionalPositionDocumentV1, images: dict[str, bytes]):
        if self.read_only:
            raise PermissionError("regional position store is read-only")
        if set(images) != set(_METHODS):
            raise ValueError("both method PNGs are required")
        if any(not payload.startswith(b"\x89PNG\r\n\x1a\n") for payload in images.values()):
            raise ValueError("regional position artifact is not PNG")
        raw = canonical_json_bytes(document.model_dump(mode="json"))
        manifest = RegionalPositionManifestV1(
            document=document,
            document_sha256=sha256_digest(raw),
            artifacts=tuple(
                RegionalArtifactV1(
                    name=name, sha256=sha256_digest(images[name]), byte_count=len(images[name])
                )
                for name in _METHODS
            ),
        )
        sealed = _seal(manifest)
        # Publishing acquires the lock itself: callers cannot accidentally omit it.
        with (
            self._backing.writer(document.session_id),
            self._directory(document.session_id) as directory,
        ):
            try:
                existing = _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if existing != sealed:
                    raise ValueError("immutable regional position publication conflict")
                for name in _METHODS:
                    if _read(directory, f"{name}.png", _LIMIT) != images[name]:
                        raise ValueError("regional position PNG differs")
                return manifest
            payloads = [("document.json", raw)] + [
                (f"{name}.png", images[name]) for name in _METHODS
            ]
            for filename, payload in payloads:
                temporary = f".{filename}.{os.getpid()}.partial"
                try:
                    _publish(directory, temporary, payload, _LIMIT)
                    os.replace(
                        temporary,
                        filename,
                        src_dir_fd=directory.fileno(),
                        dst_dir_fd=directory.fileno(),
                    )
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary, dir_fd=directory.fileno())
            _publish(directory, "manifest.json", sealed, _LIMIT)
            os.fsync(directory.fileno())
        return manifest

    def artifact(self, session_id: str, method: str) -> bytes | None:
        if method not in _METHODS:
            raise ValueError("unknown regional positioning method")
        status = self.status(session_id)
        if status.manifest is None:
            return None
        with self._directory(session_id) as directory:
            payload = _read(directory, f"{method}.png", _LIMIT)
        reference = next(a for a in status.manifest.artifacts if a.name == method)
        if len(payload) != reference.byte_count or sha256_digest(payload) != reference.sha256:
            raise ValueError("regional position PNG digest differs")
        return payload
