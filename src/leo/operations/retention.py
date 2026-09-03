"""Pure retention planning and confined, recoverable local purge primitives."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleNotFoundError

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HIGH_WATERMARK = 0.70
LOW_WATERMARK = 0.65
WARNING_WATERMARK = 0.75
ADMISSION_STOP_WATERMARK = 0.80
_FORBIDDEN_DESTRUCTIVE_ROOT = Path("/mnt/qnap01")
_MAX_SCANNER_TOMBSTONE_BYTES = 17 * 1024 * 1024
_MAX_PERSISTENT_HOP_TOMBSTONE_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StorageUsage:
    total_bytes: int
    used_bytes: int

    def __post_init__(self) -> None:
        if self.total_bytes <= 0:
            raise ValueError("total_bytes must be positive")
        if not 0 <= self.used_bytes <= self.total_bytes:
            raise ValueError("used_bytes must be between zero and total_bytes")

    @property
    def fraction(self) -> float:
        return self.used_bytes / self.total_bytes


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    session_id: str
    created_utc_ns: int
    allocated_bytes: int
    held: bool = False
    is_test: bool = False
    active_claim: bool = False
    committed: bool = True
    reconciled: bool = True
    already_purging: bool = False

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.session_id):
            raise ValueError("session_id is not a safe identifier")
        if self.created_utc_ns < 0 or self.allocated_bytes < 0:
            raise ValueError("candidate time and bytes cannot be negative")

    @property
    def eligible(self) -> bool:
        return (
            self.committed
            and self.reconciled
            and not self.held
            and not self.is_test
            and not self.active_claim
            and not self.already_purging
        )


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    should_run: bool
    warning: bool
    admission_allowed_after_plan: bool
    selected_session_ids: tuple[str, ...]
    selected_bytes: int
    predicted_used_bytes: int
    target_used_bytes: int
    blocked: bool


def plan_retention(
    usage: StorageUsage,
    candidates: tuple[RetentionCandidate, ...],
) -> RetentionDecision:
    """Select oldest eligible session units until projected use reaches 65%."""

    should_run = usage.fraction >= HIGH_WATERMARK
    target = int(usage.total_bytes * LOW_WATERMARK)
    predicted = usage.used_bytes
    selected: list[str] = []
    selected_bytes = 0
    if should_run:
        ordered = sorted(
            candidates,
            key=lambda item: (item.created_utc_ns, item.session_id),
        )
        for candidate in ordered:
            if predicted <= target:
                break
            if not candidate.eligible:
                continue
            selected.append(candidate.session_id)
            selected_bytes += candidate.allocated_bytes
            predicted = max(0, predicted - candidate.allocated_bytes)

    blocked = should_run and predicted > target
    admission_allowed = not (usage.fraction >= ADMISSION_STOP_WATERMARK and blocked)
    return RetentionDecision(
        should_run=should_run,
        warning=usage.fraction >= WARNING_WATERMARK,
        admission_allowed_after_plan=admission_allowed,
        selected_session_ids=tuple(selected),
        selected_bytes=selected_bytes,
        predicted_used_bytes=predicted,
        target_used_bytes=target,
        blocked=blocked,
    )


@dataclass(frozen=True, slots=True)
class HoldReceipt:
    session_id: str
    reason: str
    actor: str
    created_utc_ns: int
    indefinite: bool = True

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.session_id):
            raise ValueError("session_id is not a safe identifier")
        if not self.reason.strip() or not self.actor.strip():
            raise ValueError("hold reason and actor are required")
        if self.created_utc_ns < 0:
            raise ValueError("created_utc_ns cannot be negative")


class HoldReceiptStore:
    """Durable fail-safe hold evidence independent of the database."""

    def __init__(self, bulk_root: Path) -> None:
        self.bulk_root = _validated_local_bulk_root(bulk_root)
        self.root = self.bulk_root / "control" / "holds"
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve(strict=True)

    def put(self, receipt: HoldReceipt) -> Path:
        destination = self.root / f"{receipt.session_id}.json"
        payload = json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = self.root / f".{receipt.session_id}.{uuid.uuid4().hex}.json.partial"
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        _fsync_directory(self.root)
        return destination

    def contains(self, session_id: str) -> bool:
        _validate_identifier(session_id)
        path = self.root / f"{session_id}.json"
        return path.is_file() and not path.is_symlink()

    def remove_after_catalog_deactivation(self, session_id: str) -> None:
        _validate_identifier(session_id)
        path = self.root / f"{session_id}.json"
        if path.is_symlink():
            raise ValueError("hold receipt cannot be a symlink")
        path.unlink(missing_ok=True)
        _fsync_directory(self.root)


@dataclass(frozen=True, slots=True)
class ScannerPurgeTombstone:
    """Durable evidence that one analyzed scanner IQ bundle was purged."""

    schema_version: Literal[1]
    scan_id: str
    claim_token: str
    iq_bundle_uri: str
    iq_manifest_sha256: str
    iq_manifest: dict[str, Any]
    original_path: str
    staged_bytes: int
    purged_utc_ns: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("scanner tombstone schema version must be 1")
        _validate_identifier(self.scan_id)
        _validate_identifier(self.claim_token)
        if not self.iq_bundle_uri.startswith("bulk://scanner-recordings/"):
            raise ValueError("scanner tombstone has an invalid IQ bundle URI")
        if sha256_digest(canonical_json_bytes(self.iq_manifest)) != self.iq_manifest_sha256:
            raise ValueError("scanner tombstone IQ manifest digest disagrees")
        if self.staged_bytes < 0 or self.purged_utc_ns < 0:
            raise ValueError("scanner tombstone bytes and time cannot be negative")


class ScannerPurgeTombstoneStore:
    """Append-only local availability evidence for scanner IQ retention."""

    def __init__(self, bulk_root: Path) -> None:
        self.bulk_root = _validated_local_bulk_root(bulk_root)
        self.root = self.bulk_root / "control" / "scanner-purges"
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = _validated_local_bulk_root(self.root)

    def put(self, tombstone: ScannerPurgeTombstone) -> Path:
        self._validate(tombstone)
        destination = self._path(tombstone.scan_id)
        payload = json.dumps(asdict(tombstone), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        temporary = self.root / f".{tombstone.scan_id}.{uuid.uuid4().hex}.json.partial"
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        _fsync_directory(self.root)
        return destination

    def get(self, scan_id: str) -> ScannerPurgeTombstone | None:
        path = self._path(scan_id)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise ValueError("scanner purge tombstone must be a real file")
        document = json.loads(self._read_regular(path))
        tombstone = ScannerPurgeTombstone(**document)
        if tombstone.scan_id != scan_id:
            raise ValueError("scanner purge tombstone identity disagrees with filename")
        self._validate(tombstone)
        return tombstone

    def commits(self, receipt: PurgeReceipt) -> bool:
        if receipt.kind != "scanner":
            raise ValueError("scanner tombstones only commit scanner purge receipts")
        tombstone = self.get(receipt.item_id)
        return tombstone is not None and (
            tombstone.scan_id == receipt.item_id
            and tombstone.claim_token == receipt.claim_token
            and tombstone.original_path == receipt.original_path
            and tombstone.staged_bytes == receipt.staged_bytes
        )

    def captured_at(self, scan_id: str) -> datetime:
        """Recover immutable capture time after the raw IQ bundle is gone."""

        tombstone = self.get(scan_id)
        if tombstone is None:
            raise BundleNotFoundError(f"scanner purge tombstone does not exist: {scan_id}")
        created_utc_ns = tombstone.iq_manifest.get("created_utc_ns")
        if not isinstance(created_utc_ns, int) or created_utc_ns < 0:
            raise ValueError("scanner purge tombstone has an invalid capture time")
        return datetime.fromtimestamp(created_utc_ns / 1_000_000_000, tz=UTC)

    def _path(self, scan_id: str) -> Path:
        _validate_identifier(scan_id)
        return self.root / f"{scan_id}.json"

    def _validate(self, tombstone: ScannerPurgeTombstone) -> None:
        original = Path(tombstone.original_path)
        scanner_root = self.bulk_root / "scanner-recordings"
        try:
            relative = original.relative_to(scanner_root)
        except ValueError as error:
            raise ValueError("scanner tombstone path escapes the scanner root") from error
        if len(relative.parts) != 4 or relative.parts[-1] != tombstone.scan_id:
            raise ValueError("scanner tombstone path is not one dated IQ bundle")
        expected_uri = f"bulk://scanner-recordings/{'/'.join(relative.parts)}"
        if tombstone.iq_bundle_uri != expected_uri:
            raise ValueError("scanner tombstone URI disagrees with its original path")
        if tombstone.iq_manifest.get("scan_id") != tombstone.scan_id:
            raise ValueError("scanner tombstone manifest identity disagrees")

    @staticmethod
    def _read_regular(path: Path) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 < before.st_size <= _MAX_SCANNER_TOMBSTONE_BYTES
            ):
                raise ValueError("scanner purge tombstone inode is invalid")
            chunks: list[bytes] = []
            remaining = before.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if len(payload) != before.st_size or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("scanner purge tombstone changed while reading")
            return payload
        finally:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class PersistentHopPurgeTombstone:
    """Durable evidence that one qualified persistent-hop IQ bundle was purged."""

    schema_version: Literal[1]
    session_id: str
    claim_token: str
    iq_bundle_uri: str
    iq_manifest_sha256: str
    iq_manifest: dict[str, Any]
    original_path: str
    staged_bytes: int
    purged_utc_ns: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("persistent-hop tombstone schema version must be 1")
        _validate_identifier(self.session_id)
        _validate_identifier(self.claim_token)
        if not self.iq_bundle_uri.startswith("bulk://scanner-hop-recordings/"):
            raise ValueError("persistent-hop tombstone has an invalid IQ bundle URI")
        if sha256_digest(canonical_json_bytes(self.iq_manifest)) != self.iq_manifest_sha256:
            raise ValueError("persistent-hop tombstone IQ manifest digest disagrees")
        if self.staged_bytes < 0 or self.purged_utc_ns < 0:
            raise ValueError("persistent-hop tombstone bytes and time cannot be negative")


class PersistentHopPurgeTombstoneStore:
    """Append-only local availability evidence for persistent-hop retention."""

    def __init__(self, bulk_root: Path) -> None:
        self.bulk_root = _validated_local_bulk_root(bulk_root)
        control_root = self.bulk_root / "control"
        control_root.mkdir(exist_ok=True)
        if control_root.is_symlink():
            raise ValueError("persistent-hop tombstone control root cannot be a symlink")
        control_root = _validated_local_bulk_root(control_root)
        _strict_descendant(self.bulk_root, control_root)
        self.root = control_root / "persistent-hop-purges"
        self.root.mkdir(exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("persistent-hop tombstone root cannot be a symlink")
        self.root = _validated_local_bulk_root(self.root)
        _strict_descendant(self.bulk_root, self.root)

    def put(self, tombstone: PersistentHopPurgeTombstone) -> Path:
        self._validate(tombstone)
        destination = self._path(tombstone.session_id)
        payload = json.dumps(asdict(tombstone), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        temporary = self.root / f".{tombstone.session_id}.{uuid.uuid4().hex}.json.partial"
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        _fsync_directory(self.root)
        return destination

    def get(self, session_id: str) -> PersistentHopPurgeTombstone | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise ValueError("persistent-hop purge tombstone must be a real file")
        document = json.loads(self._read_regular(path))
        tombstone = PersistentHopPurgeTombstone(**document)
        if tombstone.session_id != session_id:
            raise ValueError("persistent-hop purge tombstone identity disagrees with filename")
        self._validate(tombstone)
        return tombstone

    def commits(self, receipt: PurgeReceipt) -> bool:
        if receipt.kind != "persistent-hop":
            raise ValueError("persistent-hop tombstones only commit persistent-hop receipts")
        tombstone = self.get(receipt.item_id)
        return tombstone is not None and (
            tombstone.session_id == receipt.item_id
            and tombstone.claim_token == receipt.claim_token
            and tombstone.original_path == receipt.original_path
            and tombstone.staged_bytes == receipt.staged_bytes
        )

    def _path(self, session_id: str) -> Path:
        _validate_identifier(session_id)
        return self.root / f"{session_id}.json"

    def _validate(self, tombstone: PersistentHopPurgeTombstone) -> None:
        original = Path(tombstone.original_path)
        persistent_hop_root = self.bulk_root / "scanner-hop-recordings"
        try:
            relative = original.relative_to(persistent_hop_root)
        except ValueError as error:
            raise ValueError("persistent-hop tombstone path escapes its IQ root") from error
        if len(relative.parts) != 4 or relative.parts[-1] != tombstone.session_id:
            raise ValueError("persistent-hop tombstone path is not one dated IQ bundle")
        expected_uri = f"bulk://scanner-hop-recordings/{'/'.join(relative.parts)}"
        if tombstone.iq_bundle_uri != expected_uri:
            raise ValueError("persistent-hop tombstone URI disagrees with its original path")
        if tombstone.iq_manifest.get("session_id") != tombstone.session_id:
            raise ValueError("persistent-hop tombstone manifest identity disagrees")

    @staticmethod
    def _read_regular(path: Path) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 < before.st_size <= _MAX_PERSISTENT_HOP_TOMBSTONE_BYTES
            ):
                raise ValueError("persistent-hop purge tombstone inode is invalid")
            chunks: list[bytes] = []
            remaining = before.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if len(payload) != before.st_size or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("persistent-hop purge tombstone changed while reading")
            return payload
        finally:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class PurgeReceipt:
    kind: Literal["session", "artifact", "scanner", "persistent-hop"]
    item_id: str
    session_id: str
    claim_token: str
    original_path: str
    staged_path: str
    staged_bytes: int


class PurgeExecutor:
    """Stage exact recording bundles into local trash before final removal."""

    def __init__(self, bulk_root: Path) -> None:
        self.bulk_root = _validated_local_bulk_root(bulk_root)
        self.recordings_root = (self.bulk_root / "recordings").resolve(strict=True)
        self.scanner_root = self.bulk_root / "scanner-recordings"
        self.scanner_root.mkdir(parents=True, exist_ok=True)
        self.scanner_root = _validated_local_bulk_root(self.scanner_root)
        self.persistent_hop_root = self.bulk_root / "scanner-hop-recordings"
        self.persistent_hop_root.mkdir(parents=True, exist_ok=True)
        if self.persistent_hop_root.is_symlink():
            raise ValueError("persistent-hop recording root cannot be a symlink")
        self.persistent_hop_root = _validated_local_bulk_root(self.persistent_hop_root)
        _strict_descendant(self.bulk_root, self.persistent_hop_root)
        self.analysis_root = self.bulk_root / "analysis"
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        self.analysis_root = self.analysis_root.resolve(strict=True)
        self.trash_root = self.bulk_root / "trash"
        self.trash_root.mkdir(parents=True, exist_ok=True)
        self.trash_root = self.trash_root.resolve(strict=True)
        self.journal_root = self.bulk_root / "control" / "purges"
        self.journal_root.mkdir(parents=True, exist_ok=True)
        self.journal_root = self.journal_root.resolve(strict=True)
        devices = {
            os.stat(path).st_dev
            for path in (
                self.recordings_root,
                self.scanner_root,
                self.persistent_hop_root,
                self.analysis_root,
                self.trash_root,
            )
        }
        if len(devices) != 1:
            raise ValueError(
                "recording, scanner, persistent-hop, analysis, and trash roots must share "
                "one filesystem"
            )

    def stage(self, bundle_path: Path, session_id: str, claim_token: str) -> PurgeReceipt:
        _validate_identifier(session_id)
        _validate_identifier(claim_token)
        resolved = bundle_path.resolve(strict=True)
        relative = _strict_descendant(self.recordings_root, resolved)
        if len(relative.parts) != 4 or relative.parts[-1] != session_id:
            raise ValueError("purge target must be one dated recording session")
        if resolved.is_symlink() or not resolved.is_dir():
            raise ValueError("purge target must be a real recording directory")
        destination = self.trash_root / f"session.{session_id}.{claim_token}"
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"purge staging target already exists: {destination}")
        staged_bytes = _allocated_bytes(resolved)
        receipt = PurgeReceipt(
            kind="session",
            item_id=session_id,
            session_id=session_id,
            claim_token=claim_token,
            original_path=str(resolved),
            staged_path=str(destination),
            staged_bytes=staged_bytes,
        )
        self._write_journal(receipt)
        os.rename(resolved, destination)
        _fsync_directory(resolved.parent)
        _fsync_directory(self.trash_root)
        return receipt

    def stage_scanner(
        self,
        bundle_path: Path,
        *,
        scan_id: str,
        claim_token: str,
    ) -> PurgeReceipt:
        _validate_identifier(scan_id)
        _validate_identifier(claim_token)
        resolved = bundle_path.resolve(strict=True)
        relative = _strict_descendant(self.scanner_root, resolved)
        if len(relative.parts) != 4 or relative.parts[-1] != scan_id:
            raise ValueError("scanner purge target must be one dated IQ bundle")
        if resolved.is_symlink() or not resolved.is_dir():
            raise ValueError("scanner purge target must be a real recording directory")
        destination = self.trash_root / f"scanner.{scan_id}.{claim_token}"
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"purge staging target already exists: {destination}")
        staged_bytes = _allocated_bytes(resolved)
        receipt = PurgeReceipt(
            kind="scanner",
            item_id=scan_id,
            session_id=scan_id,
            claim_token=claim_token,
            original_path=str(resolved),
            staged_path=str(destination),
            staged_bytes=staged_bytes,
        )
        self._write_journal(receipt)
        os.rename(resolved, destination)
        _fsync_directory(resolved.parent)
        _fsync_directory(self.trash_root)
        return receipt

    def stage_persistent_hop(
        self,
        bundle_path: Path,
        *,
        session_id: str,
        claim_token: str,
    ) -> PurgeReceipt:
        _validate_identifier(session_id)
        _validate_identifier(claim_token)
        resolved = bundle_path.resolve(strict=True)
        relative = _strict_descendant(self.persistent_hop_root, resolved)
        if len(relative.parts) != 4 or relative.parts[-1] != session_id:
            raise ValueError("persistent-hop purge target must be one dated IQ bundle")
        if resolved.is_symlink() or not resolved.is_dir():
            raise ValueError("persistent-hop purge target must be a real recording directory")
        destination = self.trash_root / f"persistent-hop.{session_id}.{claim_token}"
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"purge staging target already exists: {destination}")
        staged_bytes = _allocated_bytes(resolved)
        receipt = PurgeReceipt(
            kind="persistent-hop",
            item_id=session_id,
            session_id=session_id,
            claim_token=claim_token,
            original_path=str(resolved),
            staged_path=str(destination),
            staged_bytes=staged_bytes,
        )
        self._write_journal(receipt)
        os.rename(resolved, destination)
        _fsync_directory(resolved.parent)
        _fsync_directory(self.trash_root)
        return receipt

    def stage_artifact(
        self,
        artifact_path: Path,
        *,
        product_id: int,
        session_id: str,
        claim_token: str,
    ) -> PurgeReceipt:
        _validate_identifier(session_id)
        _validate_identifier(claim_token)
        if product_id <= 0:
            raise ValueError("product_id must be positive")
        resolved = artifact_path.resolve(strict=True)
        _strict_descendant(self.analysis_root, resolved)
        if resolved.is_symlink() or not resolved.is_file():
            raise ValueError("artifact purge target must be a real file")
        item_id = str(product_id)
        destination = self.trash_root / f"artifact.{item_id}.{claim_token}"
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"purge staging target already exists: {destination}")
        staged_bytes = resolved.stat().st_blocks * 512
        receipt = PurgeReceipt(
            kind="artifact",
            item_id=item_id,
            session_id=session_id,
            claim_token=claim_token,
            original_path=str(resolved),
            staged_path=str(destination),
            staged_bytes=staged_bytes,
        )
        self._write_journal(receipt)
        os.rename(resolved, destination)
        _fsync_directory(resolved.parent)
        _fsync_directory(self.trash_root)
        return receipt

    def discard_staged(self, receipt: PurgeReceipt) -> int:
        staged = Path(receipt.staged_path)
        expected = self.trash_root / f"{receipt.kind}.{receipt.item_id}.{receipt.claim_token}"
        if staged != expected:
            raise ValueError("purge receipt does not identify its exact trash entry")
        if staged.exists():
            resolved = staged.resolve(strict=True)
            _strict_descendant(self.trash_root, resolved)
            if resolved.is_symlink():
                raise ValueError("staged purge target cannot be a symlink")
            if receipt.kind in {"session", "scanner", "persistent-hop"} and resolved.is_dir():
                shutil.rmtree(resolved)
            elif receipt.kind == "artifact" and resolved.is_file():
                resolved.unlink()
            else:
                raise ValueError("staged purge target has the wrong file type")
        _fsync_directory(self.trash_root)
        self._remove_journal(receipt)
        return receipt.staged_bytes

    def restore(self, receipt: PurgeReceipt) -> Path:
        staged = Path(receipt.staged_path)
        expected = self.trash_root / f"{receipt.kind}.{receipt.item_id}.{receipt.claim_token}"
        if staged != expected:
            raise ValueError("purge receipt does not identify its exact trash entry")
        destination = Path(receipt.original_path)
        parent = destination.parent.resolve(strict=True)
        allowed_root = (
            self.recordings_root
            if receipt.kind == "session"
            else self.scanner_root
            if receipt.kind == "scanner"
            else self.persistent_hop_root
            if receipt.kind == "persistent-hop"
            else self.analysis_root
        )
        _strict_descendant(allowed_root, destination)
        if staged.exists():
            resolved = staged.resolve(strict=True)
            _strict_descendant(self.trash_root, resolved)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"cannot restore over existing target: {destination}")
            os.rename(resolved, destination)
        elif not destination.exists() or destination.is_symlink():
            raise FileNotFoundError("neither staged nor original purge path exists")
        _fsync_directory(parent)
        _fsync_directory(self.trash_root)
        self._remove_journal(receipt)
        return destination

    def pending(self) -> tuple[PurgeReceipt, ...]:
        receipts: list[PurgeReceipt] = []
        for path in sorted(self.journal_root.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"invalid purge journal entry: {path}")
            document = json.loads(path.read_bytes())
            receipt = PurgeReceipt(**document)
            if self._journal_path(receipt) != path:
                raise ValueError(f"purge journal identity disagrees with filename: {path}")
            receipts.append(receipt)
        return tuple(receipts)

    def _write_journal(self, receipt: PurgeReceipt) -> None:
        path = self._journal_path(receipt)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
        payload = json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode()
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(self.journal_root)

    def _remove_journal(self, receipt: PurgeReceipt) -> None:
        self._journal_path(receipt).unlink(missing_ok=True)
        _fsync_directory(self.journal_root)

    def _journal_path(self, receipt: PurgeReceipt) -> Path:
        _validate_identifier(receipt.session_id)
        _validate_identifier(receipt.claim_token)
        if receipt.kind not in {"session", "artifact", "scanner", "persistent-hop"}:
            raise ValueError("unknown purge receipt kind")
        if receipt.kind == "artifact" and not receipt.item_id.isdigit():
            raise ValueError("artifact receipt item ID must be numeric")
        if receipt.kind in {"session", "scanner", "persistent-hop"} and (
            receipt.item_id != receipt.session_id
        ):
            raise ValueError("directory receipt identity disagrees")
        return self.journal_root / f"{receipt.kind}.{receipt.item_id}.{receipt.claim_token}.json"


def _validate_identifier(value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("value is not a safe identifier")


def _strict_descendant(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path escapes configured root: {path}") from error
    if not relative.parts:
        raise ValueError("operation cannot target the configured root itself")
    return relative


def _allocated_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"purge bundle contains a symlink: {path}")
        total += path.stat().st_blocks * 512
    return total


def allocated_bytes(root: Path) -> int:
    """Return allocated disk bytes while rejecting symlinked descendants."""

    resolved = root.resolve(strict=True)
    if resolved.is_file():
        return resolved.stat().st_blocks * 512
    if not resolved.is_dir():
        raise ValueError("allocated-byte target must be a file or directory")
    return _allocated_bytes(resolved)


def _validated_local_bulk_root(root: Path) -> Path:
    lexical = root.absolute()
    try:
        lexical.relative_to(_FORBIDDEN_DESTRUCTIVE_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("/mnt/qnap01 is read-only and cannot be a retention target")
    resolved = root.resolve(strict=True)
    try:
        resolved.relative_to(_FORBIDDEN_DESTRUCTIVE_ROOT)
    except ValueError:
        return resolved
    raise ValueError("/mnt/qnap01 is read-only and cannot be a retention target")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
