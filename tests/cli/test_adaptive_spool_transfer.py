from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.cli import adaptive_spool_transfer as subject


class _Store:
    recovered: tuple[str, ...] = ()

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def recover_spooled_sessions(self) -> tuple[str, ...]:
        return self.recovered

    def close(self) -> None:
        pass


def _archive(spool: Path, session_id: str, payload: bytes) -> Path:
    path = spool / "v052-adaptive" / session_id
    path.mkdir(parents=True)
    (path / "manifest.json").write_bytes(payload)
    return path


def test_transfer_is_incremental_and_only_reports_current_deltas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    _archive(spool, "scan-fw-first", b"first")
    _archive(spool, "scan-fw-second", b"second")
    _Store.recovered = ("scan-host-current",)
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)
    calls: list[str] = []

    def importer(archive: Path, _bulk: Path) -> tuple[str, str]:
        calls.append(archive.name)
        if archive.name.endswith("second"):
            return "unsupported", "missing visit"
        return "imported", archive.name

    first = subject.transfer_pending(bulk, spool, importer=importer)
    assert calls == ["scan-fw-second", "scan-fw-first"]
    assert first.firmware_imported_session_ids == ("scan-fw-first",)
    assert first.firmware_unsupported == (
        {"session_id": "scan-fw-second", "reason": "missing visit"},
    )
    assert first.as_json()["published_session_ids"] == ("scan-host-current",)
    assert not (spool / "v052-adaptive" / "scan-fw-first").exists()
    assert (spool / "v052-adaptive" / "scan-fw-second").is_dir()

    calls.clear()
    _Store.recovered = ()
    second = subject.transfer_pending(bulk, spool, importer=importer)
    assert calls == []
    assert second.unchanged_count == 1
    assert second.firmware_imported_session_ids == ()
    assert second.firmware_unsupported == ()
    assert second.as_json()["firmware_imported_count"] == 0


def test_imported_archive_is_retired_after_ledger_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    archive = _archive(spool, "scan-fw-change", b"before")
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)

    def importer(path: Path, _bulk: Path) -> tuple[str, str]:
        return "imported", path.name

    result = subject.transfer_pending(bulk, spool, importer=importer)
    assert result.firmware_imported_session_ids == ("scan-fw-change",)
    assert not archive.exists()
    ledger = json.loads((spool / subject._LEDGER_NAME).read_bytes())
    assert ledger["entries"]["scan-fw-change"]["status"] == "imported"


def test_changed_importer_revisits_an_unchanged_unsupported_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    _archive(spool, "scan-fw-sparse", b"same manifest")
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)

    def old_importer(archive: Path, _bulk: Path) -> tuple[str, str]:
        return "unsupported", f"{archive.name} has a gap"

    def new_importer(archive: Path, _bulk: Path) -> tuple[str, str]:
        return "imported", archive.name

    first = subject.transfer_pending(bulk, spool, importer=old_importer)
    assert first.firmware_unsupported
    second = subject.transfer_pending(bulk, spool, importer=new_importer)
    assert second.firmware_imported_session_ids == ("scan-fw-sparse",)
    assert second.unchanged_count == 0


def test_ledger_checkpoints_each_archive_before_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    _archive(spool, "scan-fw-a", b"a")
    _archive(spool, "scan-fw-b", b"b")
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)
    calls: list[str] = []
    inject_failure = True

    def failing(archive: Path, _bulk: Path) -> tuple[str, str]:
        nonlocal inject_failure
        calls.append(archive.name)
        if inject_failure and archive.name == "scan-fw-a":
            raise RuntimeError("injected")
        return "imported", archive.name

    with pytest.raises(RuntimeError, match="injected"):
        subject.transfer_pending(bulk, spool, importer=failing)
    ledger = json.loads((spool / subject._LEDGER_NAME).read_bytes())
    assert set(ledger["entries"]) == {"scan-fw-b"}

    calls.clear()
    inject_failure = False
    result = subject.transfer_pending(bulk, spool, importer=failing)
    assert result.unchanged_count == 0
    assert result.firmware_imported_session_ids == ("scan-fw-a",)


def test_firmware_reconciliation_can_be_bounded_between_capture_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    for name in ("scan-fw-a", "scan-fw-b", "scan-fw-c"):
        _archive(spool, name, name.encode())
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)
    calls: list[str] = []

    def importer(archive: Path, _bulk: Path) -> tuple[str, str]:
        calls.append(archive.name)
        return "imported", archive.name

    first = subject.transfer_pending(
        bulk, spool, importer=importer, maximum_firmware_imports=1
    )
    assert calls == ["scan-fw-c"]
    assert first.deferred_firmware_count == 2

    calls.clear()
    second = subject.transfer_pending(
        bulk, spool, importer=importer, maximum_firmware_imports=1
    )
    assert calls == ["scan-fw-b"]
    assert second.unchanged_count == 0
    assert second.deferred_firmware_count == 1


def test_failed_and_unsupported_archives_are_not_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    failed = _archive(spool, "scan-fw-failed", b"failed")
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)

    def failure(_archive: Path, _bulk: Path) -> tuple[str, str]:
        raise RuntimeError("copy failed")

    with pytest.raises(RuntimeError, match="copy failed"):
        subject.transfer_pending(bulk, spool, importer=failure)
    assert failed.is_dir()

    def unsupported(archive: Path, _bulk: Path) -> tuple[str, str]:
        return "unsupported", archive.name

    result = subject.transfer_pending(bulk, spool, importer=unsupported)
    assert result.firmware_unsupported
    assert failed.is_dir()


def test_interrupted_retirement_is_finished_before_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    retired = _archive(spool, ".retired-scan-fw-old", b"old")
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)

    result = subject.transfer_pending(
        bulk, spool, importer=lambda archive, _bulk: ("imported", archive.name)
    )

    assert not retired.exists()
    assert result.firmware_imported_session_ids == ()


def test_bounded_reconciliation_prioritizes_newest_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool, bulk = tmp_path / "spool", tmp_path / "bulk"
    bulk.mkdir()
    old = _archive(spool, "scan-fw-old", b"old") / "manifest.json"
    new = _archive(spool, "scan-fw-new", b"new") / "manifest.json"
    old.touch()
    new.touch()
    old_mtime = old.stat().st_mtime_ns
    new_mtime = old_mtime + 1_000_000_000
    import os

    os.utime(old, ns=(old_mtime, old_mtime))
    os.utime(new, ns=(new_mtime, new_mtime))
    monkeypatch.setattr(subject, "AdaptiveHopIqStore", _Store)
    calls: list[str] = []

    def importer(archive: Path, _bulk: Path) -> tuple[str, str]:
        calls.append(archive.name)
        return "imported", archive.name

    result = subject.transfer_pending(
        bulk, spool, importer=importer, maximum_firmware_imports=1
    )
    assert calls == ["scan-fw-new"]
    assert result.deferred_firmware_count == 1


def test_firmware_reconciliation_rejects_nonpositive_bound(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        subject.transfer_pending(
            tmp_path / "bulk", tmp_path / "spool", maximum_firmware_imports=0
        )


def test_manifest_digest_reads_in_bounded_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"x" * (subject._DIGEST_CHUNK_BYTES * 2 + 17))
    largest = 0
    original = Path.open

    class _Reader:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def __enter__(self) -> _Reader:
            self.stream.__enter__()  # type: ignore[attr-defined]
            return self

        def __exit__(self, *args: object) -> object:
            return self.stream.__exit__(*args)  # type: ignore[attr-defined]

        def read(self, size: int) -> bytes:
            nonlocal largest
            largest = max(largest, size)
            return self.stream.read(size)  # type: ignore[attr-defined,no-any-return]

    def bounded_open(target: Path, *args: object, **kwargs: object) -> _Reader:
        return _Reader(original(target, *args, **kwargs))

    monkeypatch.setattr(Path, "open", bounded_open)
    assert subject._manifest_digest(path).startswith("sha256:")
    assert largest == subject._DIGEST_CHUNK_BYTES


@pytest.mark.parametrize(
    "document",
    [
        {"schema_version": 1, "entries": []},
        {"schema_version": 1, "entries": {"scan-fw-a": "bad"}},
        {
            "schema_version": 1,
            "entries": {
                "scan-fw-a": {
                    "status": "imported",
                    "manifest_sha256": "sha256:not-a-digest",
                    "importer_sha256": "sha256:" + "0" * 64,
                }
            },
        },
        {
            "schema_version": 1,
            "entries": {
                "scan-fw-a": {
                    "status": "unsupported",
                    "manifest_sha256": "sha256:" + "0" * 64,
                    "importer_sha256": "sha256:" + "1" * 64,
                }
            },
        },
    ],
)
def test_malformed_ledger_fails_closed(tmp_path: Path, document: object) -> None:
    path = tmp_path / subject._LEDGER_NAME
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="ledger"):
        subject._load_ledger(path)


def test_isolated_import_terminates_a_hung_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Connection:
        def poll(self, _timeout: float) -> bool:
            return False

        def close(self) -> None:
            pass

    class _Process:
        exitcode = None
        terminated = False
        killed = False
        alive = True

        def start(self) -> None:
            pass

        def terminate(self) -> None:
            self.terminated = True
            self.alive = False

        def kill(self) -> None:
            self.killed = True
            self.alive = False

        def join(self, _timeout: float | None = None) -> None:
            pass

        def is_alive(self) -> bool:
            return self.alive

    process = _Process()

    class _Context:
        def Pipe(self, *, duplex: bool) -> tuple[_Connection, _Connection]:
            assert not duplex
            return _Connection(), _Connection()

        def Process(self, **_kwargs: object) -> _Process:
            return process

    monkeypatch.setattr(subject.multiprocessing, "get_context", lambda _name: _Context())
    with pytest.raises(TimeoutError, match="exceeded"):
        subject._isolated_import(tmp_path / "archive", tmp_path / "bulk")
    assert process.terminated
    assert not process.killed


def test_isolated_import_reports_child_crash_without_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Parent:
        def poll(self, _timeout: float) -> bool:
            return True

        def recv(self) -> object:
            raise EOFError

        def close(self) -> None:
            pass

    class _Child:
        def close(self) -> None:
            pass

    class _Process:
        exitcode = 17

        def start(self) -> None:
            pass

        def join(self, _timeout: float | None = None) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class _Context:
        def Pipe(self, *, duplex: bool) -> tuple[_Parent, _Child]:
            assert not duplex
            return _Parent(), _Child()

        def Process(self, **_kwargs: object) -> _Process:
            return _Process()

    monkeypatch.setattr(subject.multiprocessing, "get_context", lambda _name: _Context())
    with pytest.raises(RuntimeError, match=r"without a result \(17\)"):
        subject._isolated_import(tmp_path / "archive", tmp_path / "bulk")
