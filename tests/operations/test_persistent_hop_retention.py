from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.operations import (
    CatalogRetentionService,
    HoldReceipt,
    HoldReceiptStore,
    PersistentHopPurgeTombstone,
    PersistentHopPurgeTombstoneStore,
    PurgeExecutor,
    StorageUsage,
)
from leo.storage import RecordingStore


class _EmptyCatalog:
    def retention_candidates(self) -> tuple[()]:
        return ()


@dataclass(frozen=True)
class _Manifest:
    created_utc_ns: int
    document: dict[str, object]
    receipt: object

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return self.document


class _PersistentHopIq:
    def __init__(
        self,
        root: Path,
        *,
        session_id: str = "hop-retain",
        qualified: bool = True,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.session_id = session_id
        self.path = root / "scanner-hop-recordings" / "2026" / "09" / "03" / session_id
        self.path.mkdir(parents=True)
        (self.path / "iq-sweep-000000.ci16.zst").write_bytes(b"persistent-hop-iq")
        self.document: dict[str, object] = {
            "schema_version": 1,
            "kind": "starlink_persistent_hop_iq",
            "session_id": session_id,
            "created_utc_ns": 123,
            "receipt": {"qualified": qualified},
        }
        payload = canonical_json_bytes(self.document)
        (self.path / "manifest.json").write_bytes(payload)
        self.uri = f"bulk://scanner-hop-recordings/2026/09/03/{session_id}"
        self.digest = sha256_digest(payload)
        self.qualified = qualified

    def session_ids(self) -> tuple[str, ...]:
        return (self.session_id,) if self.path.exists() else ()

    def inspect(self, session_id: str):
        if session_id != self.session_id or not self.path.exists():
            raise FileNotFoundError(session_id)
        return SimpleNamespace(
            session_id=session_id,
            path=self.path,
            uri=self.uri,
            manifest=_Manifest(
                created_utc_ns=123,
                document=self.document,
                receipt=SimpleNamespace(qualified=self.qualified),
            ),
            manifest_sha256=self.digest,
        )


def _system(
    tmp_path: Path,
    *,
    qualified: bool = True,
    held: bool = False,
    failure_injector=None,
):
    bulk = tmp_path / "bulk"
    persistent_hop_iq = _PersistentHopIq(bulk, qualified=qualified)
    recordings = RecordingStore(bulk)
    holds = HoldReceiptStore(bulk)
    if held:
        holds.put(HoldReceipt("hop-retain", "important science", "operator", 123))
    executor = PurgeExecutor(bulk)
    tombstones = PersistentHopPurgeTombstoneStore(bulk)
    retention = CatalogRetentionService(
        _EmptyCatalog(),  # type: ignore[arg-type]
        recordings,
        holds,
        executor,
        persistent_hop_iq=persistent_hop_iq,  # type: ignore[arg-type]
        persistent_hop_tombstones=tombstones,
        failure_injector=failure_injector,
    )
    return persistent_hop_iq, executor, tombstones, retention


def test_only_qualified_unheld_persistent_hop_iq_is_watermark_eligible(
    tmp_path: Path,
) -> None:
    persistent_hop_iq, executor, tombstones, retention = _system(tmp_path)

    below = retention.run(StorageUsage(total_bytes=1_000, used_bytes=699), dry_run=True)
    assert below.decision.selected_session_ids == ()

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))
    assert result.committed == ("persistent-hop:hop-retain",)
    assert result.failures == ()
    assert result.decision.selected_session_ids == ("persistent-hop:hop-retain",)
    assert not persistent_hop_iq.path.exists()
    tombstone = tombstones.get("hop-retain")
    assert tombstone is not None
    assert tombstone.iq_manifest == persistent_hop_iq.document
    assert len(executor.pending()) == 1

    recovery = retention.recover()
    assert recovery.discarded == ("persistent-hop:hop-retain",)
    assert recovery.restored == ()
    assert executor.pending() == ()


@pytest.mark.parametrize(("qualified", "held"), ((False, False), (True, True)))
def test_unqualified_or_held_persistent_hop_iq_is_never_selected(
    tmp_path: Path,
    qualified: bool,
    held: bool,
) -> None:
    persistent_hop_iq, executor, tombstones, retention = _system(
        tmp_path,
        qualified=qualified,
        held=held,
    )

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))

    assert result.decision.selected_session_ids == ()
    assert result.committed == ()
    assert persistent_hop_iq.path.is_dir()
    assert tombstones.get("hop-retain") is None
    assert executor.pending() == ()


class _InjectedCrash(BaseException):
    pass


@pytest.mark.parametrize(
    ("failure_point", "restored", "discarded"),
    (
        ("persistent-hop:after_stage", ("persistent-hop:hop-retain",), ()),
        ("persistent-hop:after_commit", (), ("persistent-hop:hop-retain",)),
    ),
)
def test_persistent_hop_recovery_uses_durable_tombstone_as_commit_point(
    tmp_path: Path,
    failure_point: str,
    restored: tuple[str, ...],
    discarded: tuple[str, ...],
) -> None:
    def crash(point: str) -> None:
        if point == failure_point:
            raise _InjectedCrash

    persistent_hop_iq, executor, tombstones, retention = _system(
        tmp_path,
        failure_injector=crash,
    )
    with pytest.raises(_InjectedCrash):
        retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))
    assert len(executor.pending()) == 1

    recovered = CatalogRetentionService(
        _EmptyCatalog(),  # type: ignore[arg-type]
        RecordingStore(persistent_hop_iq.root),
        HoldReceiptStore(persistent_hop_iq.root),
        executor,
        persistent_hop_iq=persistent_hop_iq,  # type: ignore[arg-type]
        persistent_hop_tombstones=tombstones,
    ).recover()

    assert recovered.restored == restored
    assert recovered.discarded == discarded
    assert persistent_hop_iq.path.exists() is bool(restored)
    assert executor.pending() == ()


def test_durable_hold_added_after_staging_restores_persistent_hop_iq(tmp_path: Path) -> None:
    hold_store: HoldReceiptStore | None = None

    def add_hold(point: str) -> None:
        if point == "persistent-hop:after_stage":
            assert hold_store is not None
            hold_store.put(HoldReceipt("hop-retain", "late hold", "operator", 456))

    persistent_hop_iq, executor, tombstones, retention = _system(
        tmp_path,
        failure_injector=add_hold,
    )
    hold_store = HoldReceiptStore(persistent_hop_iq.root)

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))

    assert result.committed == ()
    assert result.failures and "durable hold won" in result.failures[0]
    assert persistent_hop_iq.path.is_dir()
    assert tombstones.get("hop-retain") is None
    assert executor.pending() == ()


def test_persistent_hop_stage_is_exact_and_rejects_symlinked_content(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "recordings").mkdir(parents=True)
    bundle = bulk / "scanner-hop-recordings" / "2026" / "09" / "03" / "hop-safe"
    bundle.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("not persistent-hop data")
    (bundle / "escape").symlink_to(outside)
    executor = PurgeExecutor(bulk)

    with pytest.raises(ValueError, match="symlink"):
        executor.stage_persistent_hop(
            bundle,
            session_id="hop-safe",
            claim_token="claim-safe",
        )


def test_persistent_hop_retention_roots_cannot_be_redirected_by_symlinks(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "recordings").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (bulk / "scanner-hop-recordings").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        PurgeExecutor(bulk)

    (bulk / "scanner-hop-recordings").unlink()
    control = bulk / "control"
    control.mkdir()
    (control / "persistent-hop-purges").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symlink"):
        PersistentHopPurgeTombstoneStore(bulk)


def test_persistent_hop_tombstones_and_purge_refuse_qnap() -> None:
    forbidden = Path("/mnt/qnap01")
    with pytest.raises(ValueError, match="read-only"):
        PersistentHopPurgeTombstoneStore(forbidden)
    with pytest.raises(ValueError, match="read-only"):
        PurgeExecutor(forbidden)


def test_persistent_hop_tombstone_rejects_another_storage_namespace(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "recordings").mkdir(parents=True)
    store = PersistentHopPurgeTombstoneStore(bulk)
    document: dict[str, object] = {"session_id": "hop-wrong-root", "created_utc_ns": 123}

    tombstone = PersistentHopPurgeTombstone(
        schema_version=1,
        session_id="hop-wrong-root",
        claim_token="claim-wrong-root",
        iq_bundle_uri="bulk://scanner-hop-recordings/2026/09/03/hop-wrong-root",
        iq_manifest_sha256=sha256_digest(canonical_json_bytes(document)),
        iq_manifest=document,
        original_path=str(bulk / "scanner-recordings" / "2026" / "09" / "03" / "hop-wrong-root"),
        staged_bytes=1,
        purged_utc_ns=123,
    )
    with pytest.raises(ValueError, match="escapes"):
        store.put(tombstone)
