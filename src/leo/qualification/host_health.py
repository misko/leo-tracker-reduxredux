"""Bounded read-only collection of qualification host-health evidence."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.host_health import (
    QualificationHostHealthCheckV1,
    QualificationHostHealthEvidenceV1,
    QualificationHostHealthPolicyV1,
    QualificationHostHealthSnapshotV1,
    QualificationRaidHealthV1,
    RaidOperation,
    qualification_host_health_check_results,
)

_MAX_PROC_BYTES = 1024 * 1024
_MAX_KERNEL_ERROR_LINES = 1_000
_MAX_KERNEL_ERROR_BYTES = 1024 * 1024
_KERNEL_IO_ERROR_PATTERN = (
    r"I/O error|buffer I/O|blk_update_request|end_request: I/O|"
    r"XFS.*(error|corruption)|EXT4-fs error|md.*(error|fault)|NVMe.*(error|reset)"
)
_RAID_OPERATIONS: tuple[RaidOperation, ...] = (
    "resync",
    "recovery",
    "reshape",
    "check",
    "repair",
)

ProcReader = Callable[[Path], bytes]
KernelLogReader = Callable[[], tuple[bytes, bool]]
DiskUsageReader = Callable[[Path], Any]


def capture_qualification_host_health_snapshot(
    policy: QualificationHostHealthPolicyV1,
    *,
    proc_root: Path = Path("/proc"),
    proc_reader: ProcReader | None = None,
    kernel_log_reader: KernelLogReader | None = None,
    disk_usage_reader: DiskUsageReader = shutil.disk_usage,
    host_name_reader: Callable[[], str] = socket.gethostname,
    utc_ns: Callable[[], int] = time.time_ns,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> QualificationHostHealthSnapshotV1:
    """Capture one bounded snapshot without changing host or qualification state."""

    read_proc = proc_reader or _read_bounded_file
    mdstat = read_proc(proc_root / "mdstat")
    meminfo = read_proc(proc_root / "meminfo")
    vmstat = read_proc(proc_root / "vmstat")
    boot_id = read_proc(proc_root / "sys/kernel/random/boot_id").decode("ascii").strip().lower()
    kernel_errors, kernel_log_complete = (kernel_log_reader or _read_kernel_io_errors)()
    if len(kernel_errors) > _MAX_KERNEL_ERROR_BYTES:
        kernel_errors = kernel_errors[:_MAX_KERNEL_ERROR_BYTES]
        kernel_log_complete = False
    error_lines = tuple(line for line in kernel_errors.splitlines() if line.strip())
    if len(error_lines) > _MAX_KERNEL_ERROR_LINES:
        error_lines = error_lines[-_MAX_KERNEL_ERROR_LINES:]
        kernel_log_complete = False
    normalized_errors = b"\n".join(error_lines)
    vmstat_values = _integer_key_values(vmstat, "vmstat")
    meminfo_values = _meminfo_bytes(meminfo)
    for key in ("oom_kill", "pswpin", "pswpout"):
        if key not in vmstat_values:
            raise ValueError(f"vmstat is missing required counter: {key}")
    if "MemAvailable" not in meminfo_values:
        raise ValueError("meminfo is missing MemAvailable")
    disk_usage = disk_usage_reader(Path(policy.disk_path))
    free_disk_bytes = int(disk_usage.free)
    values = {
        "schema_version": 1,
        "algorithm_version": "qualification-host-health-snapshot-v1",
        "host_name": host_name_reader(),
        "boot_id": boot_id,
        "observed_utc_ns": utc_ns(),
        "observed_monotonic_ns": monotonic_ns(),
        "raid": _parse_mdstat(mdstat, policy.raid_array_name).model_dump(mode="json"),
        "kernel_log_complete": kernel_log_complete,
        "kernel_io_error_count": len(error_lines),
        "kernel_io_error_log_digest": sha256_digest(normalized_errors),
        "oom_kill_count": vmstat_values["oom_kill"],
        "swap_in_pages": vmstat_values["pswpin"],
        "swap_out_pages": vmstat_values["pswpout"],
        "available_memory_bytes": meminfo_values["MemAvailable"],
        "disk_path": policy.disk_path,
        "free_disk_bytes": free_disk_bytes,
        "mdstat_digest": sha256_digest(mdstat),
        "meminfo_digest": sha256_digest(meminfo),
        "vmstat_digest": sha256_digest(vmstat),
    }
    return QualificationHostHealthSnapshotV1.model_validate(
        {**values, "snapshot_digest": canonical_digest(values)}
    )


def evaluate_qualification_host_health(
    policy: QualificationHostHealthPolicyV1,
    before: QualificationHostHealthSnapshotV1,
    after: QualificationHostHealthSnapshotV1,
) -> QualificationHostHealthEvidenceV1:
    """Seal the canonical pre/post gate inventory and its deterministic result."""

    results = qualification_host_health_check_results(policy, before, after)
    checks = tuple(
        QualificationHostHealthCheckV1(name=name, passed=passed) for name, passed in results
    )
    values = {
        "schema_version": 1,
        "algorithm_version": "qualification-host-health-pre-post-v1",
        "policy": policy.model_dump(mode="json"),
        "before": before.model_dump(mode="json"),
        "after": after.model_dump(mode="json"),
        "checks": tuple(item.model_dump(mode="json") for item in checks),
        "passed": all(item.passed for item in checks),
    }
    return QualificationHostHealthEvidenceV1.model_validate(
        {**values, "evidence_digest": canonical_digest(values)}
    )


def _read_bounded_file(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(_MAX_PROC_BYTES + 1)
    if len(payload) > _MAX_PROC_BYTES:
        raise ValueError(f"host-health source exceeds bounded read: {path}")
    return payload


def _read_kernel_io_errors() -> tuple[bytes, bool]:
    try:
        completed = subprocess.run(
            (
                "journalctl",
                "--dmesg",
                "--boot",
                "--no-pager",
                "--quiet",
                "--output=cat",
                "--case-sensitive=no",
                "--grep",
                _KERNEL_IO_ERROR_PATTERN,
                "--lines",
                str(_MAX_KERNEL_ERROR_LINES + 1),
            ),
            check=False,
            capture_output=True,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return b"", False
    if completed.returncode not in (0, 1):
        return b"", False
    lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
    complete = (
        len(lines) <= _MAX_KERNEL_ERROR_LINES and len(completed.stdout) <= _MAX_KERNEL_ERROR_BYTES
    )
    return b"\n".join(lines[-_MAX_KERNEL_ERROR_LINES:]), complete


def _integer_key_values(payload: bytes, source: str) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"{source} is not ASCII") from error
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError(f"{source} contains a malformed counter")
        values[parts[0]] = int(parts[1])
    return values


def _meminfo_bytes(payload: bytes) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("meminfo is not ASCII") from error
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z_()]+):\s+(\d+)\s+kB", line)
        if match is not None:
            values[match.group(1)] = int(match.group(2)) * 1024
    return values


def _parse_mdstat(payload: bytes, array_name: str) -> QualificationRaidHealthV1:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("mdstat is not ASCII") from error
    lines = text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(rf"^{re.escape(array_name)}\s*:", line)
        ),
        None,
    )
    if start is None:
        raise ValueError(f"mdstat does not contain required array: {array_name}")
    stop = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^[A-Za-z0-9_-]+\s*:", lines[index])
            or lines[index].startswith("unused devices:")
        ),
        len(lines),
    )
    block = "\n".join(lines[start:stop])
    header = lines[start].split()
    if len(header) < 4 or header[1] != ":":
        raise ValueError("mdstat array header is malformed")
    active = header[2] == "active"
    raid_level = header[3]
    members = re.search(r"\[(\d+)/(\d+)\]\s+\[([U_]+)\]", block)
    if members is None:
        raise ValueError("mdstat array lacks exact member health evidence")
    expected_member_count = int(members.group(1))
    active_member_count = int(members.group(2))
    member_status = members.group(3)
    active_operation: RaidOperation = next(
        (operation for operation in _RAID_OPERATIONS if re.search(rf"\b{operation}\b", block)),
        "none",
    )
    healthy = (
        active
        and active_member_count == expected_member_count
        and member_status == "U" * expected_member_count
        and active_operation == "none"
    )
    return QualificationRaidHealthV1(
        array_name=array_name,
        raid_level=raid_level,
        active=active,
        expected_member_count=expected_member_count,
        active_member_count=active_member_count,
        member_status=member_status,
        active_operation=active_operation,
        healthy=healthy,
    )
