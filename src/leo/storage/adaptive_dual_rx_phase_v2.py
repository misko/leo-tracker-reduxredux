"""Immutable resumable V2 adaptive double-difference phase sidecar."""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_dual_rx_phase_product import MAX_ADAPTIVE_PHASE_PNG_BYTES
from leo.scanner.adaptive_dual_rx_phase_product_v2 import (
    AdaptiveDualRxPhaseManifestV2,
    AdaptiveDualRxPhaseTimeFigureV2,
    AdaptiveDualRxPhaseVisitV2,
)
from leo.storage.errors import BundleCorruptionError
from leo.storage.pinned import PinnedLocalRoot

_NAMESPACE = "scanner-adaptive-dual-rx-phase-v2"
_MANIFEST = "manifest.v2.json"
_ARTIFACT = "dual-rx-double-difference-time.v2.png"
_VISIT = re.compile(r"visit-([0-9]{6})\.v2\.json")
_MAX_VISIT = 128 * 1024
_MAX_MANIFEST = 1024 * 1024


def _sealed(model) -> bytes:
    document = model.model_dump(mode="json")
    return canonical_json_bytes(
        {"document": document, "sha256": sha256_digest(canonical_json_bytes(document))}
    )


def _read(directory: PinnedLocalRoot, name: str, maximum: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno())
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise BundleCorruptionError("phase V2 file is not bounded regular data")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        if len(payload) != info.st_size or info.st_mtime_ns != after.st_mtime_ns:
            raise BundleCorruptionError("phase V2 file changed during read")
        return payload
    finally:
        os.close(descriptor)


def _publish(directory: PinnedLocalRoot, name: str, payload: bytes, maximum: int) -> None:
    if not 0 < len(payload) <= maximum:
        raise ValueError("phase V2 publication exceeds its byte bound")
    temporary = f".{name}.{uuid4().hex}.partial"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
        dir_fd=directory.fileno(),
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(descriptor)
        os.link(
            temporary,
            name,
            src_dir_fd=directory.fileno(),
            dst_dir_fd=directory.fileno(),
            follow_symlinks=False,
        )
        os.unlink(temporary, dir_fd=directory.fileno())
        os.fsync(directory.fileno())
    finally:
        os.close(descriptor)


def _unseal(raw: bytes, model):
    try:
        envelope = json.loads(raw)
        if set(envelope) != {"document", "sha256"} or envelope["sha256"] != sha256_digest(
            canonical_json_bytes(envelope["document"])
        ):
            raise ValueError("seal differs")
        return model.model_validate(envelope["document"])
    except (ValueError, TypeError, KeyError) as error:
        raise BundleCorruptionError("invalid phase V2 sealed document") from error


class AdaptiveDualRxPhaseStoreV2:
    def __init__(self, root: Path, *, read_only: bool = False):
        self._root = PinnedLocalRoot(root)
        self._read_only = read_only

    def close(self) -> None:
        self._root.close()

    def _directory(
        self,
        session_id: str,
        input_manifest_sha256: str,
        glrt_binding_sha256: str,
        *,
        create: bool,
    ) -> tuple[PinnedLocalRoot, ...]:
        if create and self._read_only:
            raise PermissionError("adaptive phase V2 store is read-only")
        handles = []
        parent = self._root
        try:
            for component in (
                _NAMESPACE,
                session_id,
                input_manifest_sha256.removeprefix("sha256:"),
                glrt_binding_sha256.removeprefix("sha256:"),
            ):
                if not create:
                    os.stat(component, dir_fd=parent.fileno(), follow_symlinks=False)
                child = parent.child(component, create=create)
                handles.append(child)
                parent = child
        except Exception:
            for handle in reversed(handles):
                handle.close()
            raise
        return tuple(handles)

    def completed_visits(
        self, session_id: str, input_manifest_sha256: str, glrt_binding_sha256: str
    ) -> tuple[int, ...]:
        try:
            handles = self._directory(
                session_id, input_manifest_sha256, glrt_binding_sha256, create=False
            )
        except FileNotFoundError:
            return ()
        try:
            indexes = []
            with os.scandir(handles[-1].fileno()) as entries:
                for count, entry in enumerate(entries, start=1):
                    if count > 2600:
                        raise BundleCorruptionError("phase V2 checkpoint inventory exceeds bound")
                    match = _VISIT.fullmatch(entry.name)
                    if match is not None:
                        indexes.append(int(match.group(1)))
            return tuple(sorted(indexes))
        finally:
            for handle in reversed(handles):
                handle.close()

    def read_visit(
        self,
        session_id: str,
        input_manifest_sha256: str,
        glrt_binding_sha256: str,
        visit_index: int,
    ) -> AdaptiveDualRxPhaseVisitV2:
        handles = self._directory(
            session_id, input_manifest_sha256, glrt_binding_sha256, create=False
        )
        try:
            result = _unseal(
                _read(handles[-1], f"visit-{visit_index:06d}.v2.json", _MAX_VISIT),
                AdaptiveDualRxPhaseVisitV2,
            )
            if (
                result.session_id != session_id
                or result.input_manifest_sha256 != input_manifest_sha256
                or result.glrt_binding_sha256 != glrt_binding_sha256
                or result.visit_index != visit_index
            ):
                raise BundleCorruptionError("phase V2 visit changed source identity")
            return result
        finally:
            for handle in reversed(handles):
                handle.close()

    def write_visit(self, visit: AdaptiveDualRxPhaseVisitV2) -> None:
        if self._read_only:
            raise PermissionError("adaptive phase V2 store is read-only")
        handles = self._directory(
            visit.session_id,
            visit.input_manifest_sha256,
            visit.glrt_binding_sha256,
            create=True,
        )
        try:
            name = f"visit-{visit.visit_index:06d}.v2.json"
            try:
                existing = _unseal(_read(handles[-1], name, _MAX_VISIT), AdaptiveDualRxPhaseVisitV2)
            except FileNotFoundError:
                _publish(handles[-1], name, _sealed(visit), _MAX_VISIT)
            else:
                if existing != visit:
                    raise BundleCorruptionError("phase V2 checkpoint cannot be overwritten")
        finally:
            for handle in reversed(handles):
                handle.close()

    def manifest(
        self, session_id: str, input_manifest_sha256: str, glrt_binding_sha256: str
    ) -> AdaptiveDualRxPhaseManifestV2 | None:
        try:
            handles = self._directory(
                session_id, input_manifest_sha256, glrt_binding_sha256, create=False
            )
        except FileNotFoundError:
            return None
        try:
            try:
                manifest = _unseal(
                    _read(handles[-1], _MANIFEST, _MAX_MANIFEST),
                    AdaptiveDualRxPhaseManifestV2,
                )
                if (
                    manifest.session_id != session_id
                    or manifest.input_manifest_sha256 != input_manifest_sha256
                    or manifest.glrt_binding_sha256 != glrt_binding_sha256
                ):
                    raise BundleCorruptionError("phase V2 manifest changed source identity")
                return manifest
            except FileNotFoundError:
                return None
        finally:
            for handle in reversed(handles):
                handle.close()

    def finalize(
        self,
        *,
        session_id: str,
        input_manifest_sha256: str,
        glrt_binding_sha256: str,
        glrt_metrics_manifest_sha256: str,
        total_visit_count: int,
        geometry_phase_state: str,
        geometry_phase_reason: str,
        png: bytes | None,
    ) -> AdaptiveDualRxPhaseManifestV2:
        indexes = self.completed_visits(session_id, input_manifest_sha256, glrt_binding_sha256)
        if indexes != tuple(range(total_visit_count)):
            raise ValueError("phase V2 checkpoints do not cover every GLRT visit")
        visits = tuple(
            self.read_visit(session_id, input_manifest_sha256, glrt_binding_sha256, index)
            for index in indexes
        )
        qualified = sum(visit.state == "qualified" for visit in visits)
        hypotheses = sum(len(visit.hypotheses) for visit in visits)
        artifact = (
            None
            if png is None
            else AdaptiveDualRxPhaseTimeFigureV2(sha256=sha256_digest(png), byte_count=len(png))
        )
        if png is not None and (
            len(png) < 45
            or png[:8] != b"\x89PNG\r\n\x1a\n"
            or png[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"
        ):
            raise ValueError("phase V2 artifact is not a PNG")
        manifest = AdaptiveDualRxPhaseManifestV2(
            session_id=session_id,
            input_manifest_sha256=input_manifest_sha256,
            glrt_binding_sha256=glrt_binding_sha256,
            glrt_metrics_manifest_sha256=glrt_metrics_manifest_sha256,
            state="ready" if hypotheses else "insufficient_signal",
            reason=(
                "published_phase_time_hypotheses"
                if hypotheses
                else "no_qualified_double_difference"
            ),
            total_visit_count=total_visit_count,
            checkpoint_visit_count=len(indexes),
            qualified_visit_count=qualified,
            hypothesis_count=hypotheses,
            geometry_phase_state=geometry_phase_state,
            geometry_phase_reason=geometry_phase_reason,
            artifact=artifact,
            finalized_utc_ns=time.time_ns(),
        )
        handles = self._directory(
            session_id, input_manifest_sha256, glrt_binding_sha256, create=True
        )
        try:
            existing = self.manifest(session_id, input_manifest_sha256, glrt_binding_sha256)
            if existing is not None:
                comparable = manifest.model_copy(
                    update={"finalized_utc_ns": existing.finalized_utc_ns}
                )
                if comparable != existing:
                    raise BundleCorruptionError("phase V2 manifest cannot be overwritten")
                return existing
            if png is not None:
                _publish(handles[-1], _ARTIFACT, png, MAX_ADAPTIVE_PHASE_PNG_BYTES)
            _publish(handles[-1], _MANIFEST, _sealed(manifest), _MAX_MANIFEST)
            return manifest
        finally:
            for handle in reversed(handles):
                handle.close()

    def artifact(
        self, manifest: AdaptiveDualRxPhaseManifestV2, *, expected_sha256: str
    ) -> bytes | None:
        if manifest.artifact is None:
            return None
        if manifest.artifact.sha256 != expected_sha256:
            raise BundleCorruptionError("phase V2 artifact digest changed")
        handles = self._directory(
            manifest.session_id,
            manifest.input_manifest_sha256,
            manifest.glrt_binding_sha256,
            create=False,
        )
        try:
            payload = _read(handles[-1], _ARTIFACT, MAX_ADAPTIVE_PHASE_PNG_BYTES)
            if sha256_digest(payload) != expected_sha256:
                raise BundleCorruptionError("phase V2 artifact bytes changed")
            return payload
        finally:
            for handle in reversed(handles):
                handle.close()
