from __future__ import annotations

from types import SimpleNamespace

import pytest

from leo.contracts.host_health import (
    QualificationHostHealthEvidenceV1,
    QualificationHostHealthPolicyV1,
    QualificationHostHealthSnapshotV1,
)
from leo.qualification.host_health import (
    capture_qualification_host_health_snapshot,
    evaluate_qualification_host_health,
)

_BOOT_A = "01234567-89ab-cdef-0123-456789abcdef"
_BOOT_B = "11234567-89ab-cdef-0123-456789abcdef"
_HEALTHY_MDSTAT = b"""Personalities : [raid6]
md0 : active raid6 sda1[0] sdb1[1] sdc1[2] sdd1[3]
      100 blocks super 1.2 level 6 [4/4] [UUUU]

unused devices: <none>
"""
_RESYNC_MDSTAT = b"""Personalities : [raid6]
md0 : active raid6 sda1[0] sdb1[1] sdc1[2] sdd1[3]
      100 blocks super 1.2 level 6 [4/4] [UUUU]
      [=>...................] resync = 10.0% finish=10min speed=100K/sec

unused devices: <none>
"""


def _policy() -> QualificationHostHealthPolicyV1:
    return QualificationHostHealthPolicyV1(
        raid_array_name="md0",
        disk_path="/srv/bulk",
        minimum_available_memory_bytes=8 * 1024**3,
        minimum_free_disk_bytes=100 * 1024**3,
    )


def _snapshot(
    *,
    utc_ns: int,
    monotonic_ns: int,
    host_name: str = "gauss",
    boot_id: str = _BOOT_A,
    mdstat: bytes = _HEALTHY_MDSTAT,
    kernel_errors: bytes = b"",
    kernel_log_complete: bool = True,
    oom_kill: int = 0,
    swap_in: int = 10,
    swap_out: int = 20,
    available_memory_kib: int = 16 * 1024**2,
    free_disk_bytes: int = 200 * 1024**3,
) -> QualificationHostHealthSnapshotV1:
    sources = {
        "mdstat": mdstat,
        "meminfo": f"MemAvailable: {available_memory_kib} kB\n".encode(),
        "vmstat": (f"oom_kill {oom_kill}\npswpin {swap_in}\npswpout {swap_out}\n").encode(),
        "boot_id": f"{boot_id}\n".encode(),
    }

    return capture_qualification_host_health_snapshot(
        _policy(),
        proc_reader=lambda path: sources[path.name],
        kernel_log_reader=lambda: (kernel_errors, kernel_log_complete),
        disk_usage_reader=lambda _path: SimpleNamespace(free=free_disk_bytes),
        host_name_reader=lambda: host_name,
        utc_ns=lambda: utc_ns,
        monotonic_ns=lambda: monotonic_ns,
    )


def test_healthy_pre_post_snapshots_seal_a_deterministic_passing_receipt() -> None:
    before = _snapshot(utc_ns=1_000, monotonic_ns=100)
    after = _snapshot(
        utc_ns=2_000,
        monotonic_ns=200,
        available_memory_kib=15 * 1024**2,
        free_disk_bytes=190 * 1024**3,
    )

    evidence = evaluate_qualification_host_health(_policy(), before, after)
    round_tripped = QualificationHostHealthEvidenceV1.model_validate(
        evidence.model_dump(mode="json")
    )

    assert round_tripped == evidence
    assert evidence.passed
    assert all(item.passed for item in evidence.checks)
    assert before.raid.healthy and after.raid.healthy
    assert before.raid.active_operation == after.raid.active_operation == "none"


def test_pre_post_gate_fails_closed_for_every_required_host_health_signal() -> None:
    before = _snapshot(utc_ns=1_000, monotonic_ns=100)
    after = _snapshot(
        utc_ns=2_000,
        monotonic_ns=50,
        host_name="other-host",
        boot_id=_BOOT_B,
        mdstat=_RESYNC_MDSTAT,
        kernel_errors=b"blk_update_request: I/O error",
        kernel_log_complete=False,
        oom_kill=1,
        swap_in=11,
        swap_out=21,
        available_memory_kib=1024,
        free_disk_bytes=1024,
    )

    evidence = evaluate_qualification_host_health(_policy(), before, after)
    failed = {item.name for item in evidence.checks if not item.passed}

    assert not evidence.passed
    assert failed == {
        "same_host",
        "same_boot",
        "raid_healthy_after",
        "raid_idle_after",
        "kernel_log_complete_after",
        "no_kernel_io_errors_after",
        "no_oom_after",
        "no_swap_in",
        "no_swap_out",
        "memory_headroom_after",
        "disk_headroom_after",
    }


def test_snapshot_digest_and_raid_inventory_are_fail_closed() -> None:
    snapshot = _snapshot(utc_ns=1_000, monotonic_ns=100)
    tampered = snapshot.model_dump(mode="json")
    tampered["free_disk_bytes"] = snapshot.free_disk_bytes - 1

    with pytest.raises(ValueError, match="snapshot digest"):
        QualificationHostHealthSnapshotV1.model_validate(tampered)
    with pytest.raises(ValueError, match="required array"):
        _snapshot(
            utc_ns=1_000,
            monotonic_ns=100,
            mdstat=b"unused devices: <none>\n",
        )
