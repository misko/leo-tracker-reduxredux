"""Crash-safe adaptive dual-RX phase sidecar store."""

from __future__ import annotations

import ctypes
import json
import os
import stat
import struct
import time
import zlib
from pathlib import Path
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_dual_rx_phase_product import (
    MAX_ADAPTIVE_PHASE_PNG_BYTES,
    AdaptiveDualRxPhaseFigureV1,
    AdaptiveDualRxPhaseManifestV1,
)
from leo.storage.errors import BundleCorruptionError
from leo.storage.pinned import PinnedLocalRoot

_NAMESPACE = "scanner-adaptive-dual-rx-phase"
_MAX_MANIFEST = 1024 * 1024
_MANIFEST = "manifest.v1.json"
_ARTIFACT = "dual-rx-phase-progression.v1.png"


def _read(directory: PinnedLocalRoot, name: str, maximum: int) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fileno()
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise BundleCorruptionError("adaptive phase file is not bounded regular data")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        if len(payload) != info.st_size or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise BundleCorruptionError("adaptive phase file changed during read")
        return payload
    finally:
        os.close(descriptor)


def _publish(directory: PinnedLocalRoot, name: str, payload: bytes, maximum: int) -> None:
    if not 0 < len(payload) <= maximum:
        raise ValueError("adaptive phase publication exceeds its byte bound")
    temporary = f".{name}.{uuid4().hex}.partial"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
        dir_fd=directory.fileno(),
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory.fileno(), temporary.encode(), directory.fileno(), name.encode(), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), name)
    os.fsync(directory.fileno())


def _png(payload: bytes) -> None:
    if (
        not 45 <= len(payload) <= MAX_ADAPTIVE_PHASE_PNG_BYTES
        or payload[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        or payload[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"
    ):
        raise ValueError("adaptive phase artifact is not a bounded PNG")
    width, height = struct.unpack(">II", payload[16:24])
    if (
        not 0 < width <= 4096
        or not 0 < height <= 4096
        or width * height > 12_000_000
        or zlib.crc32(payload[12:29]) != struct.unpack(">I", payload[29:33])[0]
    ):
        raise ValueError("adaptive phase PNG dimensions are invalid")


class AdaptiveDualRxPhaseStore:
    def __init__(self, root: Path, *, read_only: bool = False):
        self._root = PinnedLocalRoot(root)
        self._read_only = read_only

    def close(self) -> None:
        self._root.close()

    def _directory(
        self, session_id: str, input_manifest_sha256: str, *, create: bool
    ) -> tuple[PinnedLocalRoot, ...]:
        if self._read_only and create:
            raise PermissionError("adaptive phase store is read-only")
        handles = []
        parent = self._root
        try:
            for component in (
                _NAMESPACE,
                session_id,
                input_manifest_sha256.removeprefix("sha256:"),
            ):
                child = parent.child(component, create=create)
                handles.append(child)
                parent = child
        except Exception:
            for handle in reversed(handles):
                handle.close()
            raise
        return tuple(handles)

    def manifest(
        self, session_id: str, input_manifest_sha256: str
    ) -> AdaptiveDualRxPhaseManifestV1 | None:
        handles = self._directory(session_id, input_manifest_sha256, create=False)
        try:
            try:
                envelope = json.loads(_read(handles[-1], _MANIFEST, _MAX_MANIFEST))
                if set(envelope) != {"document", "sha256"} or envelope["sha256"] != sha256_digest(
                    canonical_json_bytes(envelope["document"])
                ):
                    raise ValueError("seal differs")
                manifest = AdaptiveDualRxPhaseManifestV1.model_validate(envelope["document"])
            except FileNotFoundError:
                return None
            except (ValueError, TypeError, KeyError) as error:
                raise BundleCorruptionError("invalid adaptive phase manifest") from error
            if (
                manifest.session_id != session_id
                or manifest.input_manifest_sha256 != input_manifest_sha256
            ):
                raise BundleCorruptionError("adaptive phase manifest changed source identity")
            if manifest.artifact is not None:
                info = os.stat(_ARTIFACT, dir_fd=handles[-1].fileno(), follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_size != manifest.artifact.byte_count
                ):
                    raise BundleCorruptionError("adaptive phase artifact inventory differs")
            return manifest
        except FileNotFoundError:
            return None
        finally:
            for handle in reversed(handles):
                handle.close()

    def publish(
        self,
        *,
        session_id: str,
        input_manifest_sha256: str,
        glrt_binding_sha256: str,
        glrt_metrics_manifest_sha256: str,
        qualified_phase_count: int,
        association_count: int,
        png: bytes | None,
    ) -> AdaptiveDualRxPhaseManifestV1:
        if self._read_only:
            raise PermissionError("adaptive phase store is read-only")
        if png is not None:
            _png(png)
        artifact = (
            None
            if png is None
            else AdaptiveDualRxPhaseFigureV1(sha256=sha256_digest(png), byte_count=len(png))
        )
        manifest = AdaptiveDualRxPhaseManifestV1(
            session_id=session_id,
            input_manifest_sha256=input_manifest_sha256,
            glrt_binding_sha256=glrt_binding_sha256,
            glrt_metrics_manifest_sha256=glrt_metrics_manifest_sha256,
            state="ready" if png is not None else "insufficient_signal",
            reason="published_phase_evidence"
            if png is not None
            else "no_qualified_double_difference",
            qualified_phase_count=qualified_phase_count if png is not None else 0,
            association_count=association_count if png is not None else 0,
            artifact=artifact,
            finalized_utc_ns=time.time_ns(),
        )
        handles = self._directory(session_id, input_manifest_sha256, create=True)
        try:
            existing = self.manifest(session_id, input_manifest_sha256)
            if existing is not None:
                comparable = manifest.model_copy(
                    update={"finalized_utc_ns": existing.finalized_utc_ns}
                )
                if comparable != existing:
                    raise BundleCorruptionError("adaptive phase publication cannot be overwritten")
                return existing
            if png is not None:
                _publish(handles[-1], _ARTIFACT, png, MAX_ADAPTIVE_PHASE_PNG_BYTES)
            body = manifest.model_dump(mode="json")
            _publish(
                handles[-1],
                _MANIFEST,
                canonical_json_bytes(
                    {"document": body, "sha256": sha256_digest(canonical_json_bytes(body))}
                ),
                _MAX_MANIFEST,
            )
            return manifest
        finally:
            for handle in reversed(handles):
                handle.close()

    def artifact(
        self, manifest: AdaptiveDualRxPhaseManifestV1, *, expected_sha256: str
    ) -> bytes | None:
        if manifest.artifact is None:
            return None
        if manifest.artifact.sha256 != expected_sha256:
            raise BundleCorruptionError("adaptive phase artifact request changed digest")
        handles = self._directory(manifest.session_id, manifest.input_manifest_sha256, create=False)
        try:
            payload = _read(handles[-1], _ARTIFACT, MAX_ADAPTIVE_PHASE_PNG_BYTES)
            if (
                len(payload) != manifest.artifact.byte_count
                or sha256_digest(payload) != expected_sha256
            ):
                raise BundleCorruptionError("adaptive phase PNG digest differs")
            _png(payload)
            return payload
        finally:
            for handle in reversed(handles):
                handle.close()
