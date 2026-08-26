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
    QualificationBlockDeviceEvidenceV1,
    QualificationHostHealthCheckV1,
    QualificationHostHealthCheckV2,
    QualificationHostHealthEvidenceV1,
    QualificationHostHealthEvidenceV2,
    QualificationHostHealthPolicyV1,
    QualificationHostHealthPolicyV2,
    QualificationHostHealthSnapshotV1,
    QualificationHostHealthSnapshotV2,
    QualificationKernelIoErrorV1,
    QualificationRaidHealthV1,
    RaidOperation,
    qualification_host_health_check_results,
    qualification_host_health_check_results_v2,
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
BlockInventoryReader = Callable[
    [Path],
    tuple[str, tuple[QualificationBlockDeviceEvidenceV1, ...]],
]


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


def capture_qualification_host_health_snapshot_v2(
    policy: QualificationHostHealthPolicyV2,
    *,
    proc_root: Path = Path("/proc"),
    proc_reader: ProcReader | None = None,
    kernel_log_reader: KernelLogReader | None = None,
    disk_usage_reader: DiskUsageReader = shutil.disk_usage,
    block_inventory_reader: BlockInventoryReader | None = None,
    host_name_reader: Callable[[], str] = socket.gethostname,
    utc_ns: Callable[[], int] = time.time_ns,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> QualificationHostHealthSnapshotV2:
    """Capture V2 evidence without mutating devices or clearing boot history."""

    raw_kernel_errors, raw_log_complete = (kernel_log_reader or _read_kernel_io_errors)()
    normalized_errors, kernel_log_complete = _normalize_kernel_errors(
        raw_kernel_errors, raw_log_complete
    )
    base_policy = QualificationHostHealthPolicyV1(
        raid_array_name=policy.raid_array_name,
        disk_path=policy.disk_path,
        minimum_available_memory_bytes=policy.minimum_available_memory_bytes,
        minimum_free_disk_bytes=policy.minimum_free_disk_bytes,
    )
    base = capture_qualification_host_health_snapshot(
        base_policy,
        proc_root=proc_root,
        proc_reader=proc_reader,
        kernel_log_reader=lambda: (normalized_errors, kernel_log_complete),
        disk_usage_reader=disk_usage_reader,
        host_name_reader=host_name_reader,
        utc_ns=utc_ns,
        monotonic_ns=monotonic_ns,
    )
    mount_source, devices = (block_inventory_reader or _read_block_device_inventory)(
        Path(policy.disk_path)
    )
    device_by_name = {item.name: item for item in devices}
    errors: list[QualificationKernelIoErrorV1] = []
    for raw_line in normalized_errors.splitlines():
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("kernel I/O error line is not UTF-8") from error
        referenced_names = _kernel_error_block_devices(line, tuple(device_by_name))
        referenced = tuple(device_by_name.get(name) for name in referenced_names)
        safely_ignored = bool(referenced) and all(
            item is not None and item.removable and not item.protected for item in referenced
        )
        errors.append(
            QualificationKernelIoErrorV1(
                line=line,
                line_sha256=sha256_digest(raw_line),
                block_devices=referenced_names,
                disposition=("ignored_preexisting_removable" if safely_ignored else "relevant"),
            )
        )
    values = {
        "schema_version": 2,
        "algorithm_version": "qualification-host-health-snapshot-v2",
        "base": base.model_dump(mode="json"),
        "disk_mount_source": mount_source,
        "block_devices": tuple(item.model_dump(mode="json") for item in devices),
        "kernel_io_errors": tuple(item.model_dump(mode="json") for item in errors),
        "relevant_kernel_io_error_count": sum(item.disposition == "relevant" for item in errors),
        "ignored_removable_kernel_io_error_count": sum(
            item.disposition == "ignored_preexisting_removable" for item in errors
        ),
    }
    return QualificationHostHealthSnapshotV2.model_validate(
        {**values, "snapshot_digest": canonical_digest(values)}
    )


def evaluate_qualification_host_health_v2(
    policy: QualificationHostHealthPolicyV2,
    before: QualificationHostHealthSnapshotV2,
    after: QualificationHostHealthSnapshotV2,
) -> QualificationHostHealthEvidenceV2:
    """Seal the scoped V2 gate; any new error line fails the campaign."""

    results = qualification_host_health_check_results_v2(policy, before, after)
    checks = tuple(
        QualificationHostHealthCheckV2(name=name, passed=passed) for name, passed in results
    )
    values = {
        "schema_version": 2,
        "algorithm_version": "qualification-host-health-pre-post-v2",
        "policy": policy.model_dump(mode="json"),
        "before": before.model_dump(mode="json"),
        "after": after.model_dump(mode="json"),
        "checks": tuple(item.model_dump(mode="json") for item in checks),
        "passed": all(item.passed for item in checks),
    }
    return QualificationHostHealthEvidenceV2.model_validate(
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


def _normalize_kernel_errors(payload: bytes, complete: bool) -> tuple[bytes, bool]:
    if len(payload) > _MAX_KERNEL_ERROR_BYTES:
        payload = payload[:_MAX_KERNEL_ERROR_BYTES]
        complete = False
    lines = tuple(line for line in payload.splitlines() if line.strip())
    if len(lines) > _MAX_KERNEL_ERROR_LINES:
        lines = lines[-_MAX_KERNEL_ERROR_LINES:]
        complete = False
    return b"\n".join(lines), complete


def _read_block_device_inventory(
    disk_path: Path,
    *,
    sys_class_block: Path = Path("/sys/class/block"),
) -> tuple[str, tuple[QualificationBlockDeviceEvidenceV1, ...]]:
    """Resolve a mount and its complete sysfs slave/partition ancestry."""

    try:
        completed = subprocess.run(
            (
                "findmnt",
                "--noheadings",
                "--raw",
                "--output",
                "SOURCE",
                "--target",
                str(disk_path),
            ),
            check=False,
            capture_output=True,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("cannot resolve production-storage mount source") from error
    if completed.returncode != 0:
        raise ValueError("cannot resolve production-storage mount source")
    try:
        sources = tuple(
            line.decode("utf-8").strip() for line in completed.stdout.splitlines() if line.strip()
        )
    except UnicodeDecodeError as error:
        raise ValueError("production-storage mount source is not UTF-8") from error
    if len(sources) != 1 or not sources[0].startswith("/"):
        raise ValueError("production-storage mount source is not one absolute path")
    mount_source = sources[0]
    source_device = Path(mount_source).resolve().name
    known_names = {path.name for path in sys_class_block.iterdir() if path.is_symlink()}
    if source_device not in known_names:
        raise ValueError("production-storage mount source is not a sysfs block device")

    protected: set[str] = set()

    def add_protected(name: str) -> None:
        if name in protected:
            return
        if name not in known_names:
            raise ValueError(f"protected block dependency is absent from sysfs: {name}")
        protected.add(name)
        slaves = sys_class_block / name / "slaves"
        if slaves.is_dir():
            for slave in sorted(slaves.iterdir(), key=lambda item: item.name):
                add_protected(slave.name)
        resolved = (sys_class_block / name).resolve()
        parent_name = resolved.parent.name
        if parent_name in known_names and parent_name != name:
            add_protected(parent_name)

    add_protected(source_device)
    devices: list[QualificationBlockDeviceEvidenceV1] = []
    for name in sorted(known_names):
        device_root = sys_class_block / name
        major_minor = _read_bounded_file(device_root / "dev").decode("ascii").strip()
        resolved = device_root.resolve()
        removable_path = device_root / "removable"
        if not removable_path.is_file():
            parent_name = resolved.parent.name
            removable_path = sys_class_block / parent_name / "removable"
        if not removable_path.is_file():
            raise ValueError(f"block device lacks removable evidence: {name}")
        removable_text = _read_bounded_file(removable_path).decode("ascii").strip()
        if removable_text not in {"0", "1"}:
            raise ValueError(f"block device has malformed removable evidence: {name}")
        devices.append(
            QualificationBlockDeviceEvidenceV1(
                name=name,
                major_minor=major_minor,
                removable=removable_text == "1",
                protected=name in protected,
            )
        )
    return mount_source, tuple(devices)


def _kernel_error_block_devices(line: str, known_names: tuple[str, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for match in re.finditer(r"\bdev(?:ice)?\s+([A-Za-z0-9][A-Za-z0-9._+-]*)", line, re.I):
        names.add(match.group(1).rstrip(".,:;"))
    for name in sorted(known_names, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9._+-]){re.escape(name)}(?![A-Za-z0-9._+-])", line):
            names.add(name)
    return tuple(sorted(names))


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
