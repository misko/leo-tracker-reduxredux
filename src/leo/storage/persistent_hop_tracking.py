"""Crash-safe local storage for causal long-scan tracking products."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.persistent_hop_tracking import (
    PersistentHopCandidateRecurrencePageV1,
    PersistentHopCandidateRecurrenceV1,
    PersistentHopTleCandidateV1,
    PersistentHopTrackingDetailV1,
    PersistentHopTrackingManifestV1,
    PersistentHopTrackingStatusV1,
    TrackingState,
)
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _fsync_directory

_ANALYSIS_ID = "persistent-hop-causal-tle-tracking-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_PNG_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PublishedPersistentHopTrackingV1:
    session_id: str
    path: Path
    uri: str
    manifest: PersistentHopTrackingManifestV1
    manifest_sha256: str


class PersistentHopTrackingStore:
    """Immutable tracking publications plus replaceable operational status."""

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
            raise ValueError("persistent-hop tracking cannot use the QNAP namespace")
        if writable:
            root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.tracking_root = self.root / "scanner-hop-tracking"
        self.status_root = self.root / "control" / "persistent-hop-tracking"
        self._writable = writable
        if writable:
            self.tracking_root.mkdir(parents=True, exist_ok=True)
            self.status_root.mkdir(parents=True, exist_ok=True)
        self.resolver = BulkUriResolver(
            self.root,
            allowed_namespaces=("scanner-hop-tracking",),
        )

    def publish(
        self,
        manifest: PersistentHopTrackingManifestV1,
        *,
        artifact: bytes | None,
    ) -> PublishedPersistentHopTrackingV1:
        self._require_writable()
        self._validate_id(manifest.session_id)
        final = self._final_path(manifest.session_id)
        if final.exists():
            published = self.inspect(manifest.session_id)
            if published.manifest != manifest:
                raise BundleCorruptionError("persistent-hop tracking publication changed")
            return published
        if (manifest.artifact is None) != (artifact is None):
            raise ValueError("persistent-hop tracking artifact presence disagrees")
        if artifact is not None and (
            not artifact.startswith(b"\x89PNG\r\n\x1a\n")
            or len(artifact) > _MAX_PNG_BYTES
            or manifest.artifact is None
            or len(artifact) != manifest.artifact.byte_count
            or sha256_digest(artifact) != manifest.artifact.sha256
        ):
            raise ValueError("persistent-hop tracking artifact is invalid")
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = final.parent / f".{_ANALYSIS_ID}.{os.getpid()}.{uuid4().hex}.partial"
        staging.mkdir()
        if artifact is not None:
            presentation = staging / "presentation"
            presentation.mkdir()
            self._write_new_regular(
                presentation / "persistent-hop-trajectory-tle.v1.png",
                artifact,
            )
            _fsync_directory(presentation)
        payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        self._write_new_regular(staging / "manifest.json", payload)
        _fsync_directory(staging)
        os.rename(staging, final)
        _fsync_directory(final.parent)
        state: TrackingState = (
            "complete" if manifest.terminal_outcome == "complete" else "unsupported"
        )
        self.write_status(
            PersistentHopTrackingStatusV1(
                session_id=manifest.session_id,
                state=state,
                phase="complete",
                completed_groups=(manifest.tle_matching_attempted_group_count),
                total_groups=manifest.tle_matching_attempted_group_count,
                updated_at=manifest.completed_at,
            )
        )
        return PublishedPersistentHopTrackingV1(
            session_id=manifest.session_id,
            path=final,
            uri=self.resolver.uri_for(final),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def inspect(self, session_id: str) -> PublishedPersistentHopTrackingV1:
        self._validate_id(session_id)
        candidate = self._final_path(session_id)
        if not candidate.exists():
            raise BundleNotFoundError("persistent-hop tracking does not exist")
        path = confined_path(self.tracking_root, candidate, must_exist=True)
        payload = self._read_regular(path / "manifest.json", _MAX_JSON_BYTES)
        try:
            manifest = PersistentHopTrackingManifestV1.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid persistent-hop tracking manifest: {error}"
            ) from error
        if manifest.session_id != session_id:
            raise BundleCorruptionError("persistent-hop tracking identity disagrees")
        if manifest.artifact is not None:
            artifact = self._read_regular(
                path / manifest.artifact.relative_path,
                manifest.artifact.byte_count,
            )
            if (
                len(artifact) != manifest.artifact.byte_count
                or sha256_digest(artifact) != manifest.artifact.sha256
            ):
                raise BundleCorruptionError("persistent-hop tracking artifact digest mismatch")
        return PublishedPersistentHopTrackingV1(
            session_id=session_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def is_terminal(self, session_id: str) -> bool:
        try:
            self.inspect(session_id)
        except BundleNotFoundError:
            return False
        return True

    def status(self, session_id: str) -> PersistentHopTrackingStatusV1:
        self._validate_id(session_id)
        try:
            published = self.inspect(session_id)
        except BundleNotFoundError:
            pass
        else:
            manifest = published.manifest
            state: TrackingState = (
                "complete" if manifest.terminal_outcome == "complete" else "unsupported"
            )
            return PersistentHopTrackingStatusV1(
                session_id=session_id,
                state=state,
                phase="complete",
                completed_groups=(manifest.tle_matching_attempted_group_count),
                total_groups=manifest.tle_matching_attempted_group_count,
                updated_at=manifest.completed_at,
            )
        path = self.status_root / f"{session_id}.v1.json"
        if not path.exists():
            return PersistentHopTrackingStatusV1(
                session_id=session_id,
                state="pending",
                phase="waiting",
                updated_at=datetime.now(tz=UTC),
            )
        payload = self._read_regular(path, _MAX_JSON_BYTES)
        try:
            status = PersistentHopTrackingStatusV1.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid persistent-hop tracking status: {error}"
            ) from error
        if status.session_id != session_id:
            raise BundleCorruptionError("persistent-hop tracking status identity disagrees")
        return status

    def write_status(self, status: PersistentHopTrackingStatusV1) -> None:
        self._require_writable()
        self._validate_id(status.session_id)
        self._write_atomic_regular(
            self.status_root / f"{status.session_id}.v1.json",
            canonical_json_bytes(status.model_dump(mode="json")),
        )

    def artifact(self, session_id: str) -> bytes | None:
        try:
            published = self.inspect(session_id)
        except BundleNotFoundError:
            return None
        contract = published.manifest.artifact
        if contract is None:
            return None
        return self._read_regular(
            published.path / contract.relative_path,
            contract.byte_count,
        )

    def detail(self, session_id: str) -> PersistentHopTrackingDetailV1:
        status = self.status(session_id)
        product = None
        if status.state in ("complete", "unsupported"):
            product = self.inspect(session_id).manifest
        return PersistentHopTrackingDetailV1(status=status, product=product)

    def recurrences(self) -> PersistentHopCandidateRecurrencePageV1:
        """Aggregate candidate recurrence without upgrading it to identity."""

        publications: list[PersistentHopTrackingManifestV1] = []
        if self.tracking_root.exists():
            for session_dir in self.tracking_root.iterdir():
                if not _IDENTIFIER.fullmatch(session_dir.name):
                    continue
                try:
                    publications.append(self.inspect(session_dir.name).manifest)
                except BundleNotFoundError:
                    continue
        publications.sort(key=lambda item: (item.completed_at, item.session_id), reverse=True)
        publications = publications[:256]
        by_catalogue: dict[
            int,
            list[tuple[PersistentHopTrackingManifestV1, PersistentHopTleCandidateV1]],
        ] = {}
        for manifest in publications:
            per_session: dict[int, PersistentHopTleCandidateV1] = {}
            for candidate in manifest.tle_candidates:
                if candidate.leading_catalog_number is None:
                    continue
                existing = per_session.get(candidate.leading_catalog_number)
                if existing is None or (
                    existing.abstention_recommended,
                    -existing.source_observation_count,
                ) > (
                    candidate.abstention_recommended,
                    -candidate.source_observation_count,
                ):
                    per_session[candidate.leading_catalog_number] = candidate
            for catalog_number, candidate in per_session.items():
                by_catalogue.setdefault(catalog_number, []).append((manifest, candidate))
        rows = []
        for catalog_number, occurrences in by_catalogue.items():
            supports = []
            for manifest, candidate in occurrences:
                tracklet = next(
                    item
                    for item in manifest.tracklets
                    if item.tracklet_id == candidate.representative_tracklet_id
                )
                supports.append((tracklet.start_utc_ns, tracklet.end_utc_ns))
            rows.append(
                PersistentHopCandidateRecurrenceV1(
                    catalog_number=catalog_number,
                    session_ids=tuple(item[0].session_id for item in occurrences),
                    scan_count=len(occurrences),
                    heldout_persistent_scan_count=sum(
                        item[1].leading_candidate_persisted_on_heldout for item in occurrences
                    ),
                    nonabstaining_scan_count=sum(
                        not item[1].abstention_recommended for item in occurrences
                    ),
                    first_support_utc_ns=min(item[0] for item in supports),
                    last_support_utc_ns=max(item[1] for item in supports),
                )
            )
        rows.sort(
            key=lambda item: (
                -item.nonabstaining_scan_count,
                -item.heldout_persistent_scan_count,
                -item.scan_count,
                item.catalog_number,
            )
        )
        return PersistentHopCandidateRecurrencePageV1(items=tuple(rows[:256]))

    def _final_path(self, session_id: str) -> Path:
        return self.tracking_root / session_id / _ANALYSIS_ID

    def _require_writable(self) -> None:
        if not self._writable:
            raise PermissionError("persistent-hop tracking store is read-only")

    @staticmethod
    def _validate_id(session_id: str) -> None:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("persistent-hop tracking session ID is not safe")

    @staticmethod
    def _write_new_regular(path: Path, payload: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o640)

    def _write_atomic_regular(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.partial"
        self._write_new_regular(partial, payload)
        os.replace(partial, path)
        _fsync_directory(path.parent)

    @staticmethod
    def _read_regular(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise BundleCorruptionError("persistent-hop tracking member is not regular")
            if metadata.st_size > maximum_bytes:
                raise BundleCorruptionError("persistent-hop tracking member exceeds bound")
            payload = b""
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                payload += chunk
                remaining -= len(chunk)
            return payload
        finally:
            os.close(descriptor)


class PersistentHopTrackingPresentationStore:
    """Read facade that distinguishes an absent capture from pending tracking."""

    def __init__(
        self,
        captures: PersistentHopIqStore,
        tracking: PersistentHopTrackingStore,
    ) -> None:
        self._captures = captures
        self._tracking = tracking

    def detail(self, session_id: str) -> PersistentHopTrackingDetailV1 | None:
        try:
            self._captures.inspect(session_id)
        except BundleNotFoundError:
            return None
        return self._tracking.detail(session_id)

    def artifact(self, session_id: str) -> bytes | None:
        return self._tracking.artifact(session_id)

    def recurrences(self) -> PersistentHopCandidateRecurrencePageV1:
        return self._tracking.recurrences()


__all__ = [
    "PersistentHopTrackingPresentationStore",
    "PersistentHopTrackingStore",
    "PublishedPersistentHopTrackingV1",
]
