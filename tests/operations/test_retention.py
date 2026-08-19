from __future__ import annotations

from pathlib import Path

import pytest

from leo.operations.retention import (
    HoldReceipt,
    HoldReceiptStore,
    PurgeExecutor,
    RetentionCandidate,
    StorageUsage,
    plan_retention,
)


def candidate(session_id: str, age: int, size: int, **flags: bool) -> RetentionCandidate:
    return RetentionCandidate(
        session_id=session_id,
        created_utc_ns=age,
        allocated_bytes=size,
        **flags,
    )


def test_retention_starts_at_70_and_selects_oldest_until_65() -> None:
    below = plan_retention(
        StorageUsage(total_bytes=1_000, used_bytes=699),
        (candidate("old", 1, 100),),
    )
    assert not below.should_run
    assert below.selected_session_ids == ()

    at_threshold = plan_retention(
        StorageUsage(total_bytes=1_000, used_bytes=700),
        (
            candidate("new", 2, 100),
            candidate("old", 1, 40),
            candidate("middle", 2, 20),
        ),
    )
    assert at_threshold.should_run
    assert at_threshold.selected_session_ids == ("old", "middle")
    assert at_threshold.predicted_used_bytes == 640
    assert not at_threshold.blocked


def test_protected_candidates_are_never_selected_and_80_can_stop_admission() -> None:
    decision = plan_retention(
        StorageUsage(total_bytes=1_000, used_bytes=810),
        (
            candidate("held", 1, 200, held=True),
            candidate("test", 2, 200, is_test=True),
            candidate("active", 3, 200, active_claim=True),
            candidate("partial", 4, 200, committed=False),
        ),
    )
    assert decision.warning
    assert decision.blocked
    assert not decision.admission_allowed_after_plan
    assert decision.selected_session_ids == ()


def test_paired_session_is_one_candidate_unit() -> None:
    decision = plan_retention(
        StorageUsage(total_bytes=10_000, used_bytes=7_000),
        (candidate("paired-session", 1, 600),),
    )
    assert decision.selected_session_ids == ("paired-session",)
    assert decision.selected_bytes == 600


def test_hold_receipt_is_atomic_and_symlinks_fail_closed(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    holds = HoldReceiptStore(bulk)
    receipt = HoldReceipt("session-a", "important science", "operator", 123)
    path = holds.put(receipt)
    assert holds.contains("session-a")
    assert path.read_text().startswith('{"actor":"operator"')

    holds.remove_after_catalog_deactivation("session-a")
    assert not holds.contains("session-a")
    outside = tmp_path / "outside"
    outside.write_text("unsafe")
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        holds.remove_after_catalog_deactivation("session-a")


def test_purge_stages_restores_and_discards_only_local_recording(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    bundle = bulk / "recordings" / "2026" / "08" / "19" / "session-a"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text("{}")
    executor = PurgeExecutor(bulk)

    receipt = executor.stage(bundle, "session-a", "claim-1")
    assert not bundle.exists()
    assert Path(receipt.staged_path).is_dir()
    restored = executor.restore(receipt)
    assert restored == bundle

    second = executor.stage(bundle, "session-a", "claim-2")
    assert executor.discard_staged(second) == second.staged_bytes
    assert not Path(second.staged_path).exists()


def test_artifact_purge_is_exact_journaled_and_recoverable(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "recordings").mkdir(parents=True)
    artifact = bulk / "analysis" / "session-a" / "run-old" / "quality.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"quality":1}')
    executor = PurgeExecutor(bulk)

    receipt = executor.stage_artifact(
        artifact,
        product_id=42,
        session_id="session-a",
        claim_token="claim-a",
    )
    assert executor.pending() == (receipt,)
    assert not artifact.exists()
    assert executor.restore(receipt) == artifact
    assert executor.pending() == ()

    receipt = executor.stage_artifact(
        artifact,
        product_id=42,
        session_id="session-a",
        claim_token="claim-b",
    )
    assert executor.discard_staged(receipt) > 0
    assert not artifact.exists()
    assert executor.pending() == ()


def test_purge_rejects_qnap_other_roots_and_symlinked_content(tmp_path: Path) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "recordings").mkdir(parents=True)
    executor = PurgeExecutor(bulk)
    qnap_like = tmp_path / "mnt" / "qnap01" / "session-qnap"
    qnap_like.mkdir(parents=True)
    with pytest.raises(ValueError, match="escapes"):
        executor.stage(qnap_like, "session-qnap", "claim")

    bundle = bulk / "recordings" / "2026" / "08" / "19" / "session-link"
    bundle.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("not recording data")
    (bundle / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        executor.stage(bundle, "session-link", "claim")


def test_qnap_mount_can_never_be_configured_as_a_destructive_root() -> None:
    forbidden = Path("/mnt/qnap01")
    with pytest.raises(ValueError, match="read-only"):
        HoldReceiptStore(forbidden)
    with pytest.raises(ValueError, match="read-only"):
        PurgeExecutor(forbidden)
