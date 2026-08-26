"""Immutable pre/post host-health evidence for bounded qualification runs."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest

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
