"""Immutable pre/post host-health evidence for bounded qualification runs."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest

HostName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
RaidArrayName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]
AbsolutePath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=4096, pattern=r"^/"),
]
BootId = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}$"
        )
    ),
]
RaidOperation = Literal["none", "resync", "recovery", "reshape", "check", "repair"]
BlockDeviceName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"),
]
KernelIoErrorDisposition = Literal["ignored_preexisting_removable", "relevant"]
HostHealthCheckName = Literal[
    "same_host",
    "same_boot",
    "same_disk_path",
    "raid_identity",
    "raid_healthy_before",
    "raid_healthy_after",
    "raid_idle_before",
    "raid_idle_after",
    "kernel_log_complete_before",
    "kernel_log_complete_after",
    "no_kernel_io_errors_before",
    "no_kernel_io_errors_after",
    "no_oom_before",
    "no_oom_after",
    "no_swap_in",
    "no_swap_out",
    "memory_headroom_before",
    "memory_headroom_after",
    "disk_headroom_before",
    "disk_headroom_after",
]

HOST_HEALTH_CHECK_ORDER: tuple[HostHealthCheckName, ...] = (
    "same_host",
    "same_boot",
    "same_disk_path",
    "raid_identity",
    "raid_healthy_before",
    "raid_healthy_after",
    "raid_idle_before",
    "raid_idle_after",
    "kernel_log_complete_before",
    "kernel_log_complete_after",
    "no_kernel_io_errors_before",
    "no_kernel_io_errors_after",
    "no_oom_before",
    "no_oom_after",
    "no_swap_in",
    "no_swap_out",
    "memory_headroom_before",
    "memory_headroom_after",
    "disk_headroom_before",
    "disk_headroom_after",
)

HostHealthCheckNameV2 = Literal[
    "same_host",
    "same_boot",
    "same_disk_path",
    "same_disk_mount_source",
    "raid_identity",
    "raid_healthy_before",
    "raid_healthy_after",
    "raid_idle_before",
    "raid_idle_after",
    "kernel_log_complete_before",
    "kernel_log_complete_after",
    "block_device_inventory_unchanged",
    "kernel_io_error_inventory_unchanged",
    "no_relevant_kernel_io_errors_before",
    "no_relevant_kernel_io_errors_after",
    "no_oom_before",
    "no_oom_after",
    "no_swap_in",
    "no_swap_out",
    "memory_headroom_before",
    "memory_headroom_after",
    "disk_headroom_before",
    "disk_headroom_after",
]

HOST_HEALTH_CHECK_ORDER_V2: tuple[HostHealthCheckNameV2, ...] = (
    "same_host",
    "same_boot",
    "same_disk_path",
    "same_disk_mount_source",
    "raid_identity",
    "raid_healthy_before",
    "raid_healthy_after",
    "raid_idle_before",
    "raid_idle_after",
    "kernel_log_complete_before",
    "kernel_log_complete_after",
    "block_device_inventory_unchanged",
    "kernel_io_error_inventory_unchanged",
    "no_relevant_kernel_io_errors_before",
    "no_relevant_kernel_io_errors_after",
    "no_oom_before",
    "no_oom_after",
    "no_swap_in",
    "no_swap_out",
    "memory_headroom_before",
    "memory_headroom_after",
    "disk_headroom_before",
    "disk_headroom_after",
)


class QualificationRaidHealthV1(ContractModel):
    schema_version: Literal[1] = 1
    array_name: RaidArrayName
    raid_level: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    active: bool
    expected_member_count: Annotated[int, Field(gt=0, le=256)]
    active_member_count: Annotated[int, Field(ge=0, le=256)]
    member_status: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    active_operation: RaidOperation
    healthy: bool

    @model_validator(mode="after")
    def _health_is_exact(self) -> Self:
        if len(self.member_status) != self.expected_member_count or set(self.member_status) - {
            "U",
            "_",
        }:
            raise ValueError("RAID member status disagrees with expected member count")
        if self.active_member_count != self.member_status.count("U"):
            raise ValueError("RAID active member count disagrees with member status")
        expected_health = (
            self.active
            and self.active_member_count == self.expected_member_count
            and self.active_operation == "none"
        )
        if self.healthy != expected_health:
            raise ValueError("RAID healthy flag disagrees with member and operation evidence")
        return self


class QualificationHostHealthPolicyV1(ContractModel):
    schema_version: Literal[1] = 1
    raid_array_name: RaidArrayName
    disk_path: AbsolutePath
    minimum_available_memory_bytes: Annotated[int, Field(gt=0)]
    minimum_free_disk_bytes: Annotated[int, Field(gt=0)]


class QualificationHostHealthSnapshotV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["qualification-host-health-snapshot-v1"] = (
        "qualification-host-health-snapshot-v1"
    )
    host_name: HostName
    boot_id: BootId
    observed_utc_ns: Annotated[int, Field(gt=0)]
    observed_monotonic_ns: Annotated[int, Field(gt=0)]
    raid: QualificationRaidHealthV1
    kernel_log_complete: bool
    kernel_io_error_count: Annotated[int, Field(ge=0)]
    kernel_io_error_log_digest: Sha256Digest
    oom_kill_count: Annotated[int, Field(ge=0)]
    swap_in_pages: Annotated[int, Field(ge=0)]
    swap_out_pages: Annotated[int, Field(ge=0)]
    available_memory_bytes: Annotated[int, Field(ge=0)]
    disk_path: AbsolutePath
    free_disk_bytes: Annotated[int, Field(ge=0)]
    mdstat_digest: Sha256Digest
    meminfo_digest: Sha256Digest
    vmstat_digest: Sha256Digest
    snapshot_digest: Sha256Digest

    @model_validator(mode="after")
    def _snapshot_digest_is_exact(self) -> Self:
        expected = canonical_digest(self.model_dump(mode="json", exclude={"snapshot_digest"}))
        if self.snapshot_digest != expected:
            raise ValueError("host-health snapshot digest disagrees with its content")
        return self


class QualificationHostHealthCheckV1(ContractModel):
    schema_version: Literal[1] = 1
    name: HostHealthCheckName
    passed: bool


class QualificationHostHealthEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["qualification-host-health-pre-post-v1"] = (
        "qualification-host-health-pre-post-v1"
    )
    policy: QualificationHostHealthPolicyV1
    before: QualificationHostHealthSnapshotV1
    after: QualificationHostHealthSnapshotV1
    checks: tuple[QualificationHostHealthCheckV1, ...]
    passed: bool
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _evidence_is_exact(self) -> Self:
        if self.after.observed_utc_ns < self.before.observed_utc_ns:
            raise ValueError("host-health after snapshot precedes before snapshot")
        expected = qualification_host_health_check_results(self.policy, self.before, self.after)
        observed = tuple((item.name, item.passed) for item in self.checks)
        if observed != expected:
            raise ValueError("host-health checks disagree with snapshot evidence")
        if self.passed != all(passed for _name, passed in expected):
            raise ValueError("host-health pass flag disagrees with checks")
        digest = canonical_digest(self.model_dump(mode="json", exclude={"evidence_digest"}))
        if self.evidence_digest != digest:
            raise ValueError("host-health evidence digest disagrees with its content")
        return self


def qualification_host_health_check_results(
    policy: QualificationHostHealthPolicyV1,
    before: QualificationHostHealthSnapshotV1,
    after: QualificationHostHealthSnapshotV1,
) -> tuple[tuple[HostHealthCheckName, bool], ...]:
    """Return the canonical closed gate inventory for two bounded snapshots."""

    values: dict[HostHealthCheckName, bool] = {
        "same_host": before.host_name == after.host_name,
        "same_boot": (
            before.boot_id == after.boot_id
            and after.observed_monotonic_ns >= before.observed_monotonic_ns
        ),
        "same_disk_path": (before.disk_path == after.disk_path == policy.disk_path),
        "raid_identity": (
            before.raid.array_name == after.raid.array_name == policy.raid_array_name
            and before.raid.raid_level == after.raid.raid_level
            and before.raid.expected_member_count == after.raid.expected_member_count
        ),
        "raid_healthy_before": before.raid.healthy,
        "raid_healthy_after": after.raid.healthy,
        "raid_idle_before": before.raid.active_operation == "none",
        "raid_idle_after": after.raid.active_operation == "none",
        "kernel_log_complete_before": before.kernel_log_complete,
        "kernel_log_complete_after": after.kernel_log_complete,
        "no_kernel_io_errors_before": before.kernel_io_error_count == 0,
        "no_kernel_io_errors_after": after.kernel_io_error_count == 0,
        "no_oom_before": before.oom_kill_count == 0,
        "no_oom_after": after.oom_kill_count == 0,
        "no_swap_in": after.swap_in_pages == before.swap_in_pages,
        "no_swap_out": after.swap_out_pages == before.swap_out_pages,
        "memory_headroom_before": (
            before.available_memory_bytes >= policy.minimum_available_memory_bytes
        ),
        "memory_headroom_after": (
            after.available_memory_bytes >= policy.minimum_available_memory_bytes
        ),
        "disk_headroom_before": before.free_disk_bytes >= policy.minimum_free_disk_bytes,
        "disk_headroom_after": after.free_disk_bytes >= policy.minimum_free_disk_bytes,
    }
    return tuple((name, values[name]) for name in HOST_HEALTH_CHECK_ORDER)


class QualificationHostHealthPolicyV2(ContractModel):
    """Reviewed host policy with an exact production-storage mount identity."""

    schema_version: Literal[2] = 2
    raid_array_name: RaidArrayName
    disk_path: AbsolutePath
    required_disk_mount_source: AbsolutePath
    minimum_available_memory_bytes: Annotated[int, Field(gt=0)]
    minimum_free_disk_bytes: Annotated[int, Field(gt=0)]


class QualificationBlockDeviceEvidenceV1(ContractModel):
    """One sysfs block-device identity used to classify a kernel error."""

    schema_version: Literal[1] = 1
    name: BlockDeviceName
    major_minor: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9]+:[0-9]+$"),
    ]
    removable: bool
    protected: bool

    @model_validator(mode="after")
    def _protected_storage_is_not_removable(self) -> Self:
        if self.protected and self.removable:
            raise ValueError("production-storage devices cannot be classified as removable")
        return self


class QualificationKernelIoErrorV1(ContractModel):
    """One exact boot-journal I/O error with fail-closed device classification."""

    schema_version: Literal[1] = 1
    line: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    line_sha256: Sha256Digest
    block_devices: tuple[BlockDeviceName, ...]
    disposition: KernelIoErrorDisposition

    @model_validator(mode="after")
    def _line_digest_and_device_order_are_exact(self) -> Self:
        if tuple(sorted(set(self.block_devices))) != self.block_devices:
            raise ValueError("kernel I/O error block devices must be sorted and unique")
        if self.line_sha256 != sha256_digest(self.line.encode("utf-8")):
            raise ValueError("kernel I/O error line digest disagrees with its content")
        return self


class QualificationHostHealthSnapshotV2(ContractModel):
    """V1 host facts plus exact block ancestry and classified boot I/O errors."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["qualification-host-health-snapshot-v2"] = (
        "qualification-host-health-snapshot-v2"
    )
    base: QualificationHostHealthSnapshotV1
    disk_mount_source: AbsolutePath
    block_devices: tuple[QualificationBlockDeviceEvidenceV1, ...]
    kernel_io_errors: tuple[QualificationKernelIoErrorV1, ...]
    relevant_kernel_io_error_count: Annotated[int, Field(ge=0)]
    ignored_removable_kernel_io_error_count: Annotated[int, Field(ge=0)]
    snapshot_digest: Sha256Digest

    @model_validator(mode="after")
    def _classified_inventory_is_exact(self) -> Self:
        names = tuple(item.name for item in self.block_devices)
        if tuple(sorted(set(names))) != names:
            raise ValueError("host-health block-device inventory must be sorted and unique")
        devices = {item.name: item for item in self.block_devices}
        if not any(item.protected for item in self.block_devices):
            raise ValueError("host-health snapshot has no protected production-storage devices")
        normalized = "\n".join(item.line for item in self.kernel_io_errors).encode("utf-8")
        if self.base.kernel_io_error_count != len(self.kernel_io_errors):
            raise ValueError("classified kernel I/O error count disagrees with V1 snapshot")
        if self.base.kernel_io_error_log_digest != sha256_digest(normalized):
            raise ValueError("classified kernel I/O errors disagree with V1 log digest")
        for error in self.kernel_io_errors:
            referenced = tuple(devices.get(name) for name in error.block_devices)
            safely_ignored = bool(referenced) and all(
                item is not None and item.removable and not item.protected for item in referenced
            )
            expected: KernelIoErrorDisposition = (
                "ignored_preexisting_removable" if safely_ignored else "relevant"
            )
            if error.disposition != expected:
                raise ValueError("kernel I/O error disposition disagrees with device evidence")
        relevant = sum(item.disposition == "relevant" for item in self.kernel_io_errors)
        ignored = sum(
            item.disposition == "ignored_preexisting_removable" for item in self.kernel_io_errors
        )
        if self.relevant_kernel_io_error_count != relevant:
            raise ValueError("relevant kernel I/O error count is not exact")
        if self.ignored_removable_kernel_io_error_count != ignored:
            raise ValueError("ignored removable kernel I/O error count is not exact")
        expected_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"snapshot_digest"})
        )
        if self.snapshot_digest != expected_digest:
            raise ValueError("V2 host-health snapshot digest disagrees with its content")
        return self

    @property
    def protected_block_devices(self) -> tuple[QualificationBlockDeviceEvidenceV1, ...]:
        return tuple(item for item in self.block_devices if item.protected)


class QualificationHostHealthCheckV2(ContractModel):
    schema_version: Literal[2] = 2
    name: HostHealthCheckNameV2
    passed: bool


class QualificationHostHealthEvidenceV2(ContractModel):
    """Pre/post V2 gate allowing only unchanged removable-device history."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["qualification-host-health-pre-post-v2"] = (
        "qualification-host-health-pre-post-v2"
    )
    policy: QualificationHostHealthPolicyV2
    before: QualificationHostHealthSnapshotV2
    after: QualificationHostHealthSnapshotV2
    checks: tuple[QualificationHostHealthCheckV2, ...]
    passed: bool
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _evidence_is_exact(self) -> Self:
        if self.after.base.observed_utc_ns < self.before.base.observed_utc_ns:
            raise ValueError("V2 host-health after snapshot precedes before snapshot")
        expected = qualification_host_health_check_results_v2(self.policy, self.before, self.after)
        observed = tuple((item.name, item.passed) for item in self.checks)
        if observed != expected:
            raise ValueError("V2 host-health checks disagree with snapshot evidence")
        if self.passed != all(passed for _name, passed in expected):
            raise ValueError("V2 host-health pass flag disagrees with checks")
        digest = canonical_digest(self.model_dump(mode="json", exclude={"evidence_digest"}))
        if self.evidence_digest != digest:
            raise ValueError("V2 host-health evidence digest disagrees with its content")
        return self


def qualification_host_health_check_results_v2(
    policy: QualificationHostHealthPolicyV2,
    before: QualificationHostHealthSnapshotV2,
    after: QualificationHostHealthSnapshotV2,
) -> tuple[tuple[HostHealthCheckNameV2, bool], ...]:
    """Return the V2 closed gate inventory for scoped, unchanged kernel history."""

    before_base = before.base
    after_base = after.base
    values: dict[HostHealthCheckNameV2, bool] = {
        "same_host": before_base.host_name == after_base.host_name,
        "same_boot": (
            before_base.boot_id == after_base.boot_id
            and after_base.observed_monotonic_ns >= before_base.observed_monotonic_ns
        ),
        "same_disk_path": (before_base.disk_path == after_base.disk_path == policy.disk_path),
        "same_disk_mount_source": (
            before.disk_mount_source == after.disk_mount_source == policy.required_disk_mount_source
        ),
        "raid_identity": (
            before_base.raid.array_name == after_base.raid.array_name == policy.raid_array_name
            and before_base.raid.raid_level == after_base.raid.raid_level
            and before_base.raid.expected_member_count == after_base.raid.expected_member_count
        ),
        "raid_healthy_before": before_base.raid.healthy,
        "raid_healthy_after": after_base.raid.healthy,
        "raid_idle_before": before_base.raid.active_operation == "none",
        "raid_idle_after": after_base.raid.active_operation == "none",
        "kernel_log_complete_before": before_base.kernel_log_complete,
        "kernel_log_complete_after": after_base.kernel_log_complete,
        "block_device_inventory_unchanged": before.block_devices == after.block_devices,
        "kernel_io_error_inventory_unchanged": (before.kernel_io_errors == after.kernel_io_errors),
        "no_relevant_kernel_io_errors_before": (before.relevant_kernel_io_error_count == 0),
        "no_relevant_kernel_io_errors_after": after.relevant_kernel_io_error_count == 0,
        "no_oom_before": before_base.oom_kill_count == 0,
        "no_oom_after": after_base.oom_kill_count == 0,
        "no_swap_in": after_base.swap_in_pages == before_base.swap_in_pages,
        "no_swap_out": after_base.swap_out_pages == before_base.swap_out_pages,
        "memory_headroom_before": (
            before_base.available_memory_bytes >= policy.minimum_available_memory_bytes
        ),
        "memory_headroom_after": (
            after_base.available_memory_bytes >= policy.minimum_available_memory_bytes
        ),
        "disk_headroom_before": before_base.free_disk_bytes >= policy.minimum_free_disk_bytes,
        "disk_headroom_after": after_base.free_disk_bytes >= policy.minimum_free_disk_bytes,
    }
    return tuple((name, values[name]) for name in HOST_HEALTH_CHECK_ORDER_V2)
