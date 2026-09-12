"""Separate, immutable shared tracking products with resumable checkpoints."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from leo.contracts.digests import sha256_digest
from leo.contracts.scanner_tracking import (
    ArtifactName,
    ScannerTrackingProductV1,
    ScannerTrackingStatusV1,
    SessionId,
    TrackingArtifactV1,
)
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.pinned import PinnedLocalRoot

_LIMIT = 64 * 1024 * 1024


class ScannerTrackingStore:
    def __init__(self, root: Path, *, read_only: bool = True):
        resolved = root.resolve()
        if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
            raise ValueError("shared tracking cannot use QNAP")
        self.root, self.read_only = root, read_only

    @contextmanager
    def directory(self, session_id: str, *, create: bool = False):
        TypeAdapter(SessionId).validate_python(session_id)
        if create and self.read_only:
            raise PermissionError("tracking store is read-only")
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child("scanner-shared-tracking-v1", session_id, create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def status(self, session_id: str) -> ScannerTrackingStatusV1:
        try:
            with self.directory(session_id) as directory:
                try:
                    product = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ScannerTrackingProductV1
                    )
                    result = ScannerTrackingStatusV1(
                        session_id=session_id, state="complete", phase="complete", product=product
                    )
                except FileNotFoundError:
                    try:
                        result = _unseal(
                            _read(directory, "checkpoint.json", _LIMIT), ScannerTrackingStatusV1
                        )
                    except FileNotFoundError:
                        result = ScannerTrackingStatusV1(session_id=session_id)
                if result.session_id != session_id or (
                    result.product and result.product.session_id != session_id
                ):
                    raise ValueError("tracking session binding differs")
                return result
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ScannerTrackingStatusV1(session_id=session_id)
            raise

    def save(self, status: ScannerTrackingStatusV1) -> None:
        status = ScannerTrackingStatusV1.model_validate(status.model_dump())
        with self.directory(status.session_id, create=True) as directory:
            try:
                _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("tracking publication is already immutable")
            temporary = f".checkpoint-{uuid4().hex}"
            _publish(directory, temporary, _seal(status), _LIMIT)
            os.replace(
                temporary,
                "checkpoint.json",
                src_dir_fd=directory.fileno(),
                dst_dir_fd=directory.fileno(),
            )
            os.fsync(directory.fileno())

    def put_artifact(
        self, session_id: str, name: ArtifactName, payload: bytes
    ) -> TrackingArtifactV1:
        TypeAdapter(ArtifactName).validate_python(name)
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("tracking artifact is not PNG")
        reference = TrackingArtifactV1(
            name=name, sha256=sha256_digest(payload), byte_count=len(payload)
        )
        with self.directory(session_id, create=True) as directory:
            try:
                old = _read(directory, name + ".png", _LIMIT)
            except FileNotFoundError:
                _publish(directory, name + ".png", payload, _LIMIT)
            else:
                if old != payload:
                    raise ValueError("tracking artifact is immutable")
        return reference

    def publish(self, product: ScannerTrackingProductV1) -> None:
        product = ScannerTrackingProductV1.model_validate(product.model_dump())
        if product.tle_state == "pending":
            raise ValueError("cannot finalize pending TLE comparisons")
        with self.directory(product.session_id, create=True) as directory:
            for ref in product.artifacts:
                payload = _read(directory, ref.name + ".png", _LIMIT)
                if len(payload) != ref.byte_count or sha256_digest(payload) != ref.sha256:
                    raise ValueError("tracking artifact digest differs")
            payload = _seal(product)
            try:
                previous = _read(directory, "manifest.json", _LIMIT)
            except FileNotFoundError:
                _publish(directory, "manifest.json", payload, _LIMIT)
            else:
                if previous != payload:
                    raise ValueError("tracking publication is immutable")

    def artifact(self, session_id: str, name: ArtifactName) -> bytes | None:
        TypeAdapter(ArtifactName).validate_python(name)
        product = self.status(session_id).product
        ref = next((r for r in product.artifacts if r.name == name), None) if product else None
        if ref is None:
            return None
        with self.directory(session_id) as directory:
            payload = _read(directory, name + ".png", _LIMIT)
        if len(payload) != ref.byte_count or sha256_digest(payload) != ref.sha256:
            raise ValueError("tracking artifact digest differs")
        return payload
