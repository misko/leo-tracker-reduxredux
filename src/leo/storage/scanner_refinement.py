"""Immutable companion evidence and PNGs; owns only its new local namespace."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.scanner_refinement import (
    ARTIFACTS,
    Artifact,
    ComparisonArtifactV1,
    ComparisonEvidenceV1,
    ComparisonManifestV1,
    ComparisonMetricV1,
    ComparisonStatusV1,
    SessionId,
)
from leo.storage.adaptive_hop_analysis import _publish, _read, _seal, _unseal
from leo.storage.pinned import PinnedLocalRoot

_LIMIT = 8 * 1024 * 1024


class ScannerRefinementStore:
    def __init__(self, root: Path, *, read_only: bool = True):
        self.root = root
        self.read_only = read_only

    @contextmanager
    def _directory(self, session_id: str, *, create: bool = False):
        TypeAdapter(SessionId).validate_python(session_id)
        if create and self.read_only:
            raise PermissionError("comparison store is read-only")
        root = PinnedLocalRoot(self.root)
        directory = None
        try:
            directory = root.child("scanner-refinement-comparisons", session_id, create=create)
            yield directory
        finally:
            if directory is not None:
                directory.close()
            root.close()

    def status(self, session_id: str) -> ComparisonStatusV1:
        try:
            with self._directory(session_id) as directory:
                try:
                    manifest = _unseal(
                        _read(directory, "manifest.json", _LIMIT), ComparisonManifestV1
                    )
                except FileNotFoundError:
                    return ComparisonStatusV1(session_id=session_id, state="partial")
                if manifest.session_id != session_id:
                    raise ValueError("comparison session binding differs")
                return ComparisonStatusV1(
                    session_id=session_id, state="complete", manifest=manifest
                )
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ComparisonStatusV1(session_id=session_id, state="not_started")
            raise

    def work(self, session_id: str) -> ComparisonEvidenceV1 | None:
        try:
            with self._directory(session_id) as directory:
                return _unseal(_read(directory, "work.json", _LIMIT), ComparisonEvidenceV1)
        except FileNotFoundError:
            return None
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return None
            raise

    def save_work(self, evidence: ComparisonEvidenceV1) -> None:
        evidence = ComparisonEvidenceV1.model_validate(evidence.model_dump())
        with self._directory(evidence.session_id, create=True) as directory:
            payload = _seal(evidence)
            if len(payload) > _LIMIT:
                raise ValueError("comparison checkpoint exceeds bound")
            # The private checkpoint is replaceable; the final manifest is immutable.
            name = f".work-{uuid4().hex}.partial"
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o640,
                dir_fd=directory.fileno(),
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                name, "work.json", src_dir_fd=directory.fileno(), dst_dir_fd=directory.fileno()
            )
            os.fsync(directory.fileno())

    def publish(
        self,
        evidence: ComparisonEvidenceV1,
        metrics: tuple[ComparisonMetricV1, ...],
        artifacts: dict[str, bytes],
    ) -> ComparisonManifestV1:
        evidence = ComparisonEvidenceV1.model_validate(evidence.model_dump())
        if len({r.probe_id for r in evidence.rows}) + len(evidence.failures) != len(
            evidence.scheduled_probe_ids
        ):
            raise ValueError("comparison schedule is not complete")
        if set(artifacts) != set(ARTIFACTS):
            raise ValueError("comparison artifact inventory differs")
        with self._directory(evidence.session_id, create=True) as directory:
            raw = canonical_json_bytes(evidence.model_dump(mode="json"))
            members = [("evidence.json", raw)]
            references = []
            for name in ARTIFACTS:
                payload = artifacts[name]
                if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("comparison artifact is not a PNG")
                references.append(
                    ComparisonArtifactV1(
                        name=name, sha256=sha256_digest(payload), byte_count=len(payload)
                    )
                )
                members.append((name + ".png", payload))
            manifest = ComparisonManifestV1(
                session_id=evidence.session_id,
                input_manifest_sha256=evidence.input_manifest_sha256,
                evidence_sha256=sha256_digest(raw),
                sample_rate_hz=evidence.sample_rate_hz,
                scheduled_probes=len(evidence.scheduled_probe_ids),
                completed_probes=len({r.probe_id for r in evidence.rows}),
                failed_probes=len(evidence.failures),
                metrics=metrics,
                artifacts=tuple(references),
            )
            members.append(("manifest.json", _seal(manifest)))
            for filename, payload in members:
                try:
                    previous = _read(directory, filename, _LIMIT)
                except FileNotFoundError:
                    _publish(directory, filename, payload, _LIMIT)
                else:
                    if previous != payload:
                        raise ValueError("immutable comparison publication conflict")
            return manifest

    def evidence(self, session_id: str) -> bytes | None:
        status = self.status(session_id)
        if status.manifest is None:
            return None
        with self._directory(session_id) as directory:
            raw = _read(directory, "evidence.json", _LIMIT)
        if sha256_digest(raw) != status.manifest.evidence_sha256:
            raise ValueError("comparison evidence digest differs")
        return raw

    def artifact(self, session_id: str, name: Artifact) -> bytes | None:
        if name not in ARTIFACTS:
            raise ValueError("unsupported comparison artifact")
        status = self.status(session_id)
        if status.manifest is None:
            return None
        reference = next(a for a in status.manifest.artifacts if a.name == name)
        with self._directory(session_id) as directory:
            raw = _read(directory, name + ".png", _LIMIT)
        if len(raw) != reference.byte_count or sha256_digest(raw) != reference.sha256:
            raise ValueError("comparison PNG digest differs")
        return raw
