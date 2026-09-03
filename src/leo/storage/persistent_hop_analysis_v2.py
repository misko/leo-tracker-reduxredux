"""Crash-safe storage for fractional-epoch persistent-hop V2 products."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

import zstandard as zstd
from pydantic import Field

from leo.contracts.digests import Sha256Digest, canonical_json_bytes, sha256_digest
from leo.scanner.models import ScannerModel
from leo.scanner.persistent_hop_history import (
    PersistentHopHistoryItemV3,
    PersistentHopHistoryPageV3,
    PersistentHopSessionDetailV2,
)
from leo.scanner.persistent_hop_products import (
    PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID,
    PersistentHopAnalysisArtifactV2,
    PersistentHopAnalysisChunkReferenceV2,
    PersistentHopAnalysisChunkV2,
    PersistentHopAnalysisConfigurationV2,
    PersistentHopAnalysisManifestV2,
    PersistentHopAnalysisStatusV2,
)
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _fsync_directory

_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_COMPRESSED_CHUNK_BYTES = 16 * 1024 * 1024
_MAX_PNG_BYTES = 64 * 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class _PersistentHopAnalysisWorkV2(ScannerModel):
    schema_version: Literal[2] = 2
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    analysis_id: Literal["persistent-hop-fractional-glrt64-cfo-v2"] = (
        "persistent-hop-fractional-glrt64-cfo-v2"
    )
    input_manifest_sha256: Sha256Digest
    configuration: PersistentHopAnalysisConfigurationV2
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublishedPersistentHopAnalysisV2:
    session_id: str
    path: Path
    uri: str
    manifest: PersistentHopAnalysisManifestV2
    manifest_sha256: str


class PersistentHopAnalysisStoreV2:
    """V2 namespace isolated from immutable V1 publications and checkpoints."""

    def __init__(self, root: Path) -> None:
        self._configure(root, writable=True)

    @classmethod
    def open_read_only(cls, root: Path) -> Self:
        store = cls.__new__(cls)
        store._configure(root, writable=False)
        return store

    def _configure(self, root: Path, *, writable: bool) -> None:
        resolved = root.resolve(strict=False)
        if resolved == Path("/mnt/qnap01") or str(resolved).startswith("/mnt/qnap01/"):
            raise ValueError("persistent-hop V2 analysis cannot be written beneath QNAP")
        if writable:
            root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.analysis_root = self.root / "scanner-hop-analysis"
        self.work_root = self.root / "scanner-hop-analysis-work"
        self.status_root = self.root / "control" / "persistent-hop-analysis"
        self._writable = writable
        if writable:
            for path in (self.analysis_root, self.work_root, self.status_root):
                path.mkdir(parents=True, exist_ok=True)
            devices = {os.stat(path).st_dev for path in (self.analysis_root, self.work_root)}
            if len(devices) != 1:
                raise ValueError("persistent-hop V2 work and publication must share a filesystem")
        self.resolver = BulkUriResolver(
            self.root,
            allowed_namespaces=("scanner-hop-analysis",),
        )

    @contextmanager
    def worker_lock(self) -> Iterator[bool]:
        """Share the existing lock so V1/V2 workers never compete with acquisition."""

        self._require_writable()
        path = self.status_root / "worker.lock"
        with path.open("a+b") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def begin_or_resume(
        self,
        *,
        session_id: str,
        input_manifest_sha256: str,
        configuration: PersistentHopAnalysisConfigurationV2,
    ) -> datetime:
        self._require_writable()
        self._validate_id(session_id)
        work = self._work_path(session_id)
        work.parent.mkdir(parents=True, exist_ok=True)
        if work.exists():
            binding = self._read_work_v2(work)
            if (
                binding.input_manifest_sha256 != input_manifest_sha256
                or binding.configuration != configuration
            ):
                raise BundleCorruptionError(
                    "persistent-hop V2 checkpoint binding disagrees with input"
                )
            return binding.created_at
        binding = _PersistentHopAnalysisWorkV2(
            session_id=session_id,
            input_manifest_sha256=input_manifest_sha256,
            configuration=configuration,
            created_at=datetime.now(tz=UTC),
        )
        staging = work.parent / (
            f".{PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID}.{os.getpid()}.{uuid4().hex}.partial"
        )
        staging.mkdir()
        self._write_new_regular(
            staging / "work-manifest.v2.json",
            canonical_json_bytes(binding.model_dump(mode="json")),
        )
        _fsync_directory(staging)
        os.rename(staging, work)
        _fsync_directory(work.parent)
        return binding.created_at

    def write_chunk(
        self,
        session_id: str,
        chunk: PersistentHopAnalysisChunkV2,
    ) -> PersistentHopAnalysisChunkReferenceV2:
        self._require_writable()
        work = self._work_path(session_id)
        binding = self._read_work_v2(work)
        if (
            chunk.session_id != session_id
            or chunk.input_manifest_sha256 != binding.input_manifest_sha256
            or chunk.configuration != binding.configuration
        ):
            raise ValueError("persistent-hop V2 chunk disagrees with checkpoint binding")
        name = f"metrics-sweep-{chunk.sweep_index:06d}.v2.json.zst"
        destination = work / name
        raw = canonical_json_bytes(chunk.model_dump(mode="json"))
        compressed = zstd.ZstdCompressor(level=3, threads=0).compress(raw)
        if destination.exists():
            existing, reference = self._read_chunk_file_v2(destination)
            if existing != chunk:
                raise BundleCorruptionError(
                    "persistent-hop V2 checkpoint changed for an existing sweep"
                )
            return reference
        partial = work / f".{name}.{os.getpid()}.{uuid4().hex}.partial"
        self._write_new_regular(partial, compressed)
        os.replace(partial, destination)
        _fsync_directory(work)
        return self._chunk_reference_v2(destination, chunk, raw, compressed)

    def completed_sweeps(self, session_id: str) -> tuple[int, ...]:
        work = self._work_path(session_id)
        if not work.exists():
            return ()
        self._read_work_v2(work)
        indexes = []
        for path in work.glob("metrics-sweep-*.v2.json.zst"):
            match = re.fullmatch(r"metrics-sweep-([0-9]{6})\.v2\.json\.zst", path.name)
            if match is None:
                continue
            chunk, _reference = self._read_chunk_file_v2(path)
            if chunk.sweep_index != int(match.group(1)):
                raise BundleCorruptionError("persistent-hop V2 checkpoint path disagrees")
            indexes.append(chunk.sweep_index)
        return tuple(sorted(indexes))

    def work_chunks(self, session_id: str) -> tuple[PersistentHopAnalysisChunkV2, ...]:
        return tuple(
            self._read_chunk_file_v2(
                self._work_path(session_id) / f"metrics-sweep-{index:06d}.v2.json.zst"
            )[0]
            for index in self.completed_sweeps(session_id)
        )

    def publish(
        self,
        *,
        session_id: str,
        input_uri: str,
        sample_rate_hz: int,
        bandwidth_hz: int,
        visit_count: int,
        artifacts: dict[str, bytes],
    ) -> PublishedPersistentHopAnalysisV2:
        self._require_writable()
        self._validate_id(session_id)
        final = self._final_path(session_id)
        if final.exists():
            published = self.inspect(session_id)
            if (
                published.manifest.input_uri != input_uri
                or published.manifest.sample_rate_hz != sample_rate_hz
                or published.manifest.bandwidth_hz != bandwidth_hz
                or published.manifest.visit_count != visit_count
            ):
                raise BundleCorruptionError("persistent-hop V2 publication input changed")
            return published
        work = self._work_path(session_id)
        binding = self._read_work_v2(work)
        binding_payload = self._read_regular(work / "work-manifest.v2.json", _MAX_JSON_BYTES)
        chunks = self.work_chunks(session_id)
        if any(
            chunk.session_id != session_id
            or chunk.input_manifest_sha256 != binding.input_manifest_sha256
            or chunk.configuration != binding.configuration
            for chunk in chunks
        ):
            raise BundleCorruptionError("persistent-hop V2 checkpoints disagree with binding")
        if tuple(item.sweep_index for item in chunks) != tuple(range(len(chunks))):
            raise ValueError("persistent-hop V2 checkpoints are not gapless")
        if sum(item.visit_count for item in chunks) != visit_count:
            raise ValueError("persistent-hop V2 checkpoints do not cover all visits")
        references = tuple(
            self._read_chunk_file_v2(work / f"metrics-sweep-{chunk.sweep_index:06d}.v2.json.zst")[1]
            for chunk in chunks
        )
        expected_artifacts: dict[
            Literal["coverage", "glrt64-response", "cfo-trajectories"], str
        ] = {
            "coverage": "persistent-hop-coverage.v2.png",
            "glrt64-response": "persistent-hop-glrt64-response.v2.png",
            "cfo-trajectories": "persistent-hop-cfo-trajectories.v2.png",
        }
        if set(artifacts) != set(expected_artifacts):
            raise ValueError("persistent-hop V2 artifact set is incomplete")
        presentation = work / "presentation"
        presentation.mkdir(exist_ok=True)
        metadata = presentation.stat(follow_symlinks=False)
        if presentation.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise BundleCorruptionError("persistent-hop V2 presentation is not a real directory")
        artifact_contracts = []
        for name, filename in expected_artifacts.items():
            payload = artifacts[name]
            if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > _MAX_PNG_BYTES:
                raise ValueError(f"persistent-hop V2 {name} artifact is not one bounded PNG")
            path = presentation / filename
            self._write_atomic_regular(path, payload)
            artifact_contracts.append(
                PersistentHopAnalysisArtifactV2(
                    name=name,
                    relative_path=f"presentation/{filename}",
                    sha256=sha256_digest(payload),
                    byte_count=len(payload),
                )
            )
        manifest = PersistentHopAnalysisManifestV2.model_validate(
            {
                "session_id": session_id,
                "input_uri": input_uri,
                "input_manifest_sha256": binding.input_manifest_sha256,
                "checkpoint_binding_sha256": sha256_digest(binding_payload),
                "created_at": binding.created_at,
                "completed_at": datetime.now(tz=UTC),
                "sample_rate_hz": sample_rate_hz,
                "bandwidth_hz": bandwidth_hz,
                "configuration": binding.configuration,
                "visit_count": visit_count,
                "sweep_count": len(chunks),
                "probe_count": sum(len(item.probes) for item in chunks),
                "fractionally_scored_candidate_count": sum(
                    len(item.fractional_candidates) for chunk in chunks for item in chunk.probes
                ),
                "passed_fractional_candidate_count": sum(
                    candidate.passed_fractional_margin_gate
                    for chunk in chunks
                    for item in chunk.probes
                    for candidate in item.fractional_candidates
                ),
                "fractionally_scored_best_count": sum(
                    item.best is not None for chunk in chunks for item in chunk.probes
                ),
                "passed_fractional_best_count": sum(
                    item.best is not None and item.best.passed_fractional_margin_gate
                    for chunk in chunks
                    for item in chunk.probes
                ),
                "chunks": references,
                "artifacts": tuple(artifact_contracts),
            }
        )
        manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        self._write_atomic_regular(work / "manifest.json", manifest_payload)
        self._remove_stale_partials(presentation)
        self._remove_stale_partials(work)
        _fsync_directory(presentation)
        _fsync_directory(work)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.rename(work, final)
        _fsync_directory(final.parent)
        self.write_status(
            PersistentHopAnalysisStatusV2(
                session_id=session_id,
                state="complete",
                total_visits=visit_count,
                analyzed_visits=visit_count,
                updated_at=datetime.now(tz=UTC),
            )
        )
        return PublishedPersistentHopAnalysisV2(
            session_id=session_id,
            path=final,
            uri=self.resolver.uri_for(final),
            manifest=manifest,
            manifest_sha256=sha256_digest(manifest_payload),
        )

    def inspect(self, session_id: str) -> PublishedPersistentHopAnalysisV2:
        self._validate_id(session_id)
        candidate = self._final_path(session_id)
        if not candidate.exists():
            raise BundleNotFoundError("persistent-hop V2 analysis does not exist")
        path = confined_path(self.analysis_root, candidate, must_exist=True)
        payload = self._read_regular(path / "manifest.json", _MAX_JSON_BYTES)
        try:
            manifest = PersistentHopAnalysisManifestV2.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid persistent-hop V2 analysis manifest: {error}"
            ) from error
        if manifest.session_id != session_id:
            raise BundleCorruptionError("persistent-hop V2 manifest identity disagrees")
        binding_payload = self._read_regular(
            path / manifest.checkpoint_binding_relative_path,
            _MAX_JSON_BYTES,
        )
        if sha256_digest(binding_payload) != manifest.checkpoint_binding_sha256:
            raise BundleCorruptionError("persistent-hop V2 binding digest mismatch")
        return PublishedPersistentHopAnalysisV2(
            session_id=session_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def is_complete(self, session_id: str) -> bool:
        try:
            self.inspect(session_id)
        except BundleNotFoundError:
            return False
        return True

    def artifact(self, session_id: str, name: str) -> bytes | None:
        try:
            published = self.inspect(session_id)
        except BundleNotFoundError:
            return None
        artifact = next((item for item in published.manifest.artifacts if item.name == name), None)
        if artifact is None:
            return None
        payload = self._read_regular(published.path / artifact.relative_path, artifact.byte_count)
        if len(payload) != artifact.byte_count or sha256_digest(payload) != artifact.sha256:
            raise BundleCorruptionError("persistent-hop V2 artifact digest mismatch")
        return payload

    def status(self, session_id: str, *, total_visits: int) -> PersistentHopAnalysisStatusV2:
        self._validate_id(session_id)
        try:
            published = self.inspect(session_id)
        except BundleNotFoundError:
            pass
        else:
            return PersistentHopAnalysisStatusV2(
                session_id=session_id,
                state="complete",
                total_visits=published.manifest.visit_count,
                analyzed_visits=published.manifest.visit_count,
                updated_at=published.manifest.completed_at,
            )
        path = self.status_root / f"{session_id}.v2.json"
        if not path.exists():
            analyzed = sum(item.visit_count for item in self.work_chunks(session_id))
            return PersistentHopAnalysisStatusV2(
                session_id=session_id,
                state="pending",
                total_visits=total_visits,
                analyzed_visits=analyzed,
                updated_at=datetime.now(tz=UTC),
            )
        payload = self._read_regular(path, _MAX_JSON_BYTES)
        try:
            status = PersistentHopAnalysisStatusV2.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid persistent-hop V2 status: {error}") from error
        if status.session_id != session_id or status.total_visits != total_visits:
            raise BundleCorruptionError("persistent-hop V2 status binding disagrees")
        return status

    def write_status(self, status: PersistentHopAnalysisStatusV2) -> None:
        self._require_writable()
        self._validate_id(status.session_id)
        self._write_atomic_regular(
            self.status_root / f"{status.session_id}.v2.json",
            canonical_json_bytes(status.model_dump(mode="json")),
        )

    def _read_work_v2(self, work: Path) -> _PersistentHopAnalysisWorkV2:
        if not work.exists():
            raise BundleNotFoundError("persistent-hop V2 checkpoint does not exist")
        path = confined_path(self.work_root, work, must_exist=True)
        payload = self._read_regular(path / "work-manifest.v2.json", _MAX_JSON_BYTES)
        try:
            binding = _PersistentHopAnalysisWorkV2.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid persistent-hop V2 work manifest: {error}"
            ) from error
        if path != self._work_path(binding.session_id):
            raise BundleCorruptionError("persistent-hop V2 work identity disagrees")
        return binding

    def _read_chunk_file_v2(
        self,
        path: Path,
    ) -> tuple[PersistentHopAnalysisChunkV2, PersistentHopAnalysisChunkReferenceV2]:
        compressed = self._read_regular(path, _MAX_COMPRESSED_CHUNK_BYTES)
        try:
            raw = zstd.ZstdDecompressor().decompress(
                compressed,
                max_output_size=_MAX_JSON_BYTES,
            )
            chunk = PersistentHopAnalysisChunkV2.model_validate_json(raw)
        except Exception as error:
            raise BundleCorruptionError(f"invalid persistent-hop V2 chunk: {error}") from error
        return chunk, self._chunk_reference_v2(path, chunk, raw, compressed)

    @staticmethod
    def _chunk_reference_v2(
        path: Path,
        chunk: PersistentHopAnalysisChunkV2,
        raw: bytes,
        compressed: bytes,
    ) -> PersistentHopAnalysisChunkReferenceV2:
        return PersistentHopAnalysisChunkReferenceV2(
            chunk_index=chunk.sweep_index,
            sweep_index=chunk.sweep_index,
            first_visit_index=chunk.first_visit_index,
            visit_count=chunk.visit_count,
            probe_count=len(chunk.probes),
            fractionally_scored_candidate_count=sum(
                len(item.fractional_candidates) for item in chunk.probes
            ),
            passed_fractional_candidate_count=sum(
                candidate.passed_fractional_margin_gate
                for item in chunk.probes
                for candidate in item.fractional_candidates
            ),
            fractionally_scored_best_count=sum(item.best is not None for item in chunk.probes),
            passed_fractional_best_count=sum(
                item.best is not None and item.best.passed_fractional_margin_gate
                for item in chunk.probes
            ),
            relative_path=path.name,
            uncompressed_bytes=len(raw),
            compressed_bytes=len(compressed),
            uncompressed_sha256=sha256_digest(raw),
            compressed_sha256=sha256_digest(compressed),
        )

    def _work_path(self, session_id: str) -> Path:
        return self.work_root / session_id / PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID

    def _final_path(self, session_id: str) -> Path:
        return self.analysis_root / session_id / PERSISTENT_HOP_FRACTIONAL_ANALYZER_ID

    def _require_writable(self) -> None:
        if not self._writable:
            raise PermissionError("persistent-hop V2 analysis store is read-only")

    @staticmethod
    def _validate_id(session_id: str) -> None:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("persistent-hop V2 session ID is not safe")

    @staticmethod
    def _write_new_regular(path: Path, payload: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o644)

    def _write_atomic_regular(self, path: Path, payload: bytes) -> None:
        partial = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.partial"
        self._write_new_regular(partial, payload)
        os.replace(partial, path)
        _fsync_directory(path.parent)

    @staticmethod
    def _remove_stale_partials(directory: Path) -> None:
        for path in directory.glob(".*.partial"):
            metadata = path.stat(follow_symlinks=False)
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise BundleCorruptionError(
                    "persistent-hop V2 analysis partial is not a regular file"
                )
            path.unlink()
        _fsync_directory(directory)

    @staticmethod
    def _read_regular(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise BundleCorruptionError("persistent-hop V2 analysis member is not regular")
            if metadata.st_size > maximum_bytes:
                raise BundleCorruptionError("persistent-hop V2 analysis member exceeds bound")
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)


class PersistentHopPresentationStoreV2:
    """Current read facade for fractional V2 products."""

    def __init__(
        self,
        captures: PersistentHopIqStore,
        analyses: PersistentHopAnalysisStoreV2,
    ) -> None:
        self._captures = captures
        self._analyses = analyses

    def page_v3(self, *, cursor: int, limit: int) -> PersistentHopHistoryPageV3:
        captures = self._captures.page(cursor=cursor, limit=limit)
        items = []
        for capture in captures.items:
            status = self._analyses.status(capture.session_id, total_visits=capture.visit_count)
            artifacts: tuple[Literal["coverage", "glrt64-response", "cfo-trajectories"], ...] = ()
            if status.state == "complete":
                artifacts = tuple(
                    item.name
                    for item in self._analyses.inspect(capture.session_id).manifest.artifacts
                )
            items.append(
                PersistentHopHistoryItemV3(
                    capture=capture,
                    analysis=status,
                    available_artifacts=artifacts,
                )
            )
        return PersistentHopHistoryPageV3(
            cursor=captures.cursor,
            limit=captures.limit,
            total=captures.total,
            next_cursor=captures.next_cursor,
            items=tuple(items),
        )

    def detail_v2(self, session_id: str) -> PersistentHopSessionDetailV2 | None:
        try:
            capture = self._captures.history_item(session_id)
        except BundleNotFoundError:
            return None
        status = self._analyses.status(session_id, total_visits=capture.visit_count)
        product = (
            self._analyses.inspect(session_id).manifest if status.state == "complete" else None
        )
        return PersistentHopSessionDetailV2(
            capture=capture,
            analysis=status,
            product=product,
        )

    def artifact(self, session_id: str, artifact: str) -> bytes | None:
        return self._analyses.artifact(session_id, artifact)
