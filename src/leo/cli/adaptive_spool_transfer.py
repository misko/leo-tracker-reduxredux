"""Restartable, incremental NVMe-to-RAID publisher for adaptive captures."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import inspect
import json
import multiprocessing
import os
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.cli.firmware_adaptive_import import (
    UnsupportedFirmwareArchiveError,
    import_archive,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore

_LEDGER_NAME = ".adaptive-spool-transfer.v1.json"
_LOCK_NAME = ".adaptive-spool-transfer.lock"
_DIGEST_CHUNK_BYTES = 1024 * 1024
_IMPORT_TIMEOUT_SECONDS = 15 * 60.0
_CHILD_EXIT_GRACE_SECONDS = 5.0
_RETIRED_PREFIX = ".retired-"
_MAXIMUM_PARALLEL_IMPORTS = 2


@dataclass(frozen=True, slots=True)
class TransferSummary:
    published_session_ids: tuple[str, ...]
    firmware_imported_session_ids: tuple[str, ...]
    firmware_unsupported: tuple[dict[str, str], ...]
    unchanged_count: int
    deferred_firmware_count: int = 0

    def as_json(self) -> dict[str, Any]:
        # IDs are current-run deltas, never the repeatedly emitted history.
        return {
            "published_count": len(self.published_session_ids),
            "published_session_ids": self.published_session_ids,
            "firmware_imported_count": len(self.firmware_imported_session_ids),
            "firmware_imported_session_ids": self.firmware_imported_session_ids,
            "firmware_unsupported_count": len(self.firmware_unsupported),
            "firmware_unsupported": self.firmware_unsupported,
            "unchanged_count": self.unchanged_count,
            "deferred_firmware_count": self.deferred_firmware_count,
        }


def _manifest_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while payload := stream.read(_DIGEST_CHUNK_BYTES):
            digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def _importer_digest(importer: Callable[[Path, Path], tuple[str, str]]) -> str:
    """Change the reconciliation key whenever importer behavior is deployed."""
    target = import_archive if importer is _isolated_import else importer
    try:
        source_path = inspect.getsourcefile(target)
        payload = (
            Path(source_path).read_bytes()
            if importer is _isolated_import and source_path is not None
            else inspect.getsource(target).encode()
        )
    except (OSError, TypeError):
        payload = f"{target.__module__}:{target.__qualname__}".encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _load_ledger(path: Path) -> dict[str, dict[str, str]]:
    try:
        document = json.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    if document.get("schema_version") != 1 or not isinstance(document.get("entries"), dict):
        raise ValueError("adaptive spool transfer ledger has an unsupported schema")
    entries = document["entries"]
    for session_id, entry in entries.items():
        if (
            not isinstance(session_id, str)
            or not isinstance(entry, dict)
            or entry.get("status") not in {"imported", "unsupported"}
            or not _is_digest(entry.get("manifest_sha256"))
            or not _is_digest(entry.get("importer_sha256"))
            or (entry["status"] == "unsupported" and not isinstance(entry.get("reason"), str))
        ):
            raise ValueError("adaptive spool transfer ledger contains a malformed entry")
    return entries


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    return all(character in "0123456789abcdef" for character in value[7:])


def _write_ledger(path: Path, entries: dict[str, dict[str, str]]) -> None:
    payload = (
        json.dumps(
            {"schema_version": 1, "entries": entries}, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _retire_imported_archive(archive: Path, firmware_root: Path) -> None:
    """Remove a source only after its imported ledger checkpoint is durable."""
    if archive.parent != firmware_root or archive.is_symlink() or not archive.is_dir():
        raise ValueError("firmware archive retirement escaped its spool root")
    retired = firmware_root / f"{_RETIRED_PREFIX}{archive.name}"
    if retired.exists():
        raise FileExistsError(f"firmware retirement path already exists: {retired.name}")
    os.replace(archive, retired)
    _fsync_directory(firmware_root)
    shutil.rmtree(retired)
    _fsync_directory(firmware_root)


def _finish_interrupted_retirements(firmware_root: Path) -> None:
    for retired in firmware_root.glob(f"{_RETIRED_PREFIX}scan-fw-*"):
        if retired.is_symlink() or not retired.is_dir():
            raise ValueError("firmware retirement path is not a directory")
        shutil.rmtree(retired)
        _fsync_directory(firmware_root)


def _import_worker(connection: Any, archive: str, bulk_root: str) -> None:
    try:
        connection.send(("imported", import_archive(Path(archive), Path(bulk_root))))
    except UnsupportedFirmwareArchiveError as error:
        connection.send(("unsupported", str(error)))
    except BaseException as error:
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


def _isolated_import(archive: Path, bulk_root: Path) -> tuple[str, str]:
    """Import one archive in a disposable process to release allocator memory."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_import_worker, args=(child, os.fspath(archive), os.fspath(bulk_root))
    )
    process.start()
    child.close()
    try:
        if not parent.poll(_IMPORT_TIMEOUT_SECONDS):
            process.terminate()
            process.join(_CHILD_EXIT_GRACE_SECONDS)
            if process.is_alive():
                process.kill()
                process.join()
            raise TimeoutError(f"firmware importer exceeded {_IMPORT_TIMEOUT_SECONDS:g} seconds")
        result = parent.recv()
    except EOFError as error:
        process.join(_CHILD_EXIT_GRACE_SECONDS)
        raise RuntimeError(
            f"firmware importer exited without a result ({process.exitcode})"
        ) from error
    finally:
        parent.close()
    process.join(_CHILD_EXIT_GRACE_SECONDS)
    if process.is_alive():
        process.terminate()
        process.join(_CHILD_EXIT_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
            process.join()
        raise RuntimeError("firmware importer sent a result but did not exit")
    if process.exitcode != 0:
        raise RuntimeError(f"firmware importer process failed ({process.exitcode})")
    status, detail = result
    if status == "error":
        raise RuntimeError(detail)
    return status, detail


def transfer_pending(
    bulk_root: Path,
    spool_root: Path,
    *,
    importer: Callable[[Path, Path], tuple[str, str]] = _isolated_import,
    maximum_firmware_imports: int | None = None,
) -> TransferSummary:
    if maximum_firmware_imports is not None and maximum_firmware_imports < 1:
        raise ValueError("maximum_firmware_imports must be positive")
    spool_root.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(spool_root / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o640)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        store = AdaptiveHopIqStore(bulk_root, spool_root=spool_root, defer_spool_transfer=True)
        try:
            recovered = store.recover_spooled_sessions()
        finally:
            store.close()

        ledger_path = spool_root / _LEDGER_NAME
        ledger = _load_ledger(ledger_path)
        imported: list[str] = []
        unsupported: list[dict[str, str]] = []
        unchanged = 0
        attempted = 0
        deferred = 0
        firmware_root = spool_root / "v052-adaptive"
        firmware_root.mkdir(parents=True, exist_ok=True)
        _finish_interrupted_retirements(firmware_root)
        importer_digest = _importer_digest(importer)
        ordered = sorted(
            firmware_root.glob("scan-fw-*/manifest.json"),
            key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
        )
        # First make the newest capture visible, then spend the second lane on
        # the oldest backlog. Continue alternating when an operator requests a
        # larger bounded recovery batch.
        manifests = []
        while ordered:
            manifests.append(ordered.pop())
            if ordered:
                manifests.append(ordered.pop(0))
        candidates: list[tuple[Path, str, str]] = []
        for manifest in manifests:
            session_id = manifest.parent.name
            digest = _manifest_digest(manifest)
            previous = ledger.get(session_id)
            if (
                previous is not None
                and previous.get("manifest_sha256") == digest
                and previous.get("importer_sha256") == importer_digest
            ):
                unchanged += 1
                continue
            candidates.append((manifest, session_id, digest))
        selected = (
            candidates
            if maximum_firmware_imports is None
            else candidates[:maximum_firmware_imports]
        )
        deferred = len(candidates) - len(selected)
        attempted = len(selected)
        with ThreadPoolExecutor(
            max_workers=max(1, min(_MAXIMUM_PARALLEL_IMPORTS, attempted))
        ) as executor:
            results = executor.map(lambda item: importer(item[0].parent, bulk_root), selected)
            completed = zip(selected, results, strict=True)
            for (manifest, session_id, digest), (status, detail) in completed:
                if status == "imported":
                    imported.append(detail)
                    entry: dict[str, str] = {
                        "manifest_sha256": digest,
                        "importer_sha256": importer_digest,
                        "status": "imported",
                    }
                elif status == "unsupported":
                    unsupported.append({"session_id": session_id, "reason": detail})
                    entry = {
                        "manifest_sha256": digest,
                        "importer_sha256": importer_digest,
                        "status": "unsupported",
                        "reason": detail,
                    }
                else:
                    raise RuntimeError(f"firmware importer returned unknown status: {status}")
                ledger[session_id] = entry
                # Checkpoint every terminal item. A crash only repeats the current archive.
                _write_ledger(ledger_path, ledger)
                if status == "imported":
                    _retire_imported_archive(manifest.parent, firmware_root)
        return TransferSummary(
            tuple(recovered), tuple(imported), tuple(unsupported), unchanged, deferred
        )
    finally:
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--spool-root", type=Path, required=True)
    parser.add_argument("--maximum-firmware-imports", type=int, default=2)
    arguments = parser.parse_args()
    summary = transfer_pending(
        arguments.bulk_root,
        arguments.spool_root,
        maximum_firmware_imports=arguments.maximum_firmware_imports,
    )
    print(
        json.dumps(
            summary.as_json(),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
