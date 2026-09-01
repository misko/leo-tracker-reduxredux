from __future__ import annotations

import copy
import hashlib
import json
import runpy
import socket
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from leo.contracts.host_health import (
    QualificationHostHealthEvidenceV1,
    QualificationHostHealthEvidenceV2,
)
from leo.contracts.profile import CaptureProfileRevisionV2
from leo.contracts.states import SourceType
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.qualification.release_contract import (
    RELEASE_QUALIFICATION_V2_COMMAND_NAMES,
    RELEASE_QUALIFICATION_V2_JUNIT_PATHS,
    RELEASE_QUALIFICATION_V2_LOG_PATHS,
    RELEASE_QUALIFICATION_V2_RESULT_PATHS,
    release_qualification_v2_definition,
    summarize_pytest_junit_v1,
)

PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "verify-production-cutover"
SCRIPT_GLOBALS = runpy.run_path(str(SCRIPT))


def _call(name: str, *args: object, **kwargs: object) -> Any:
    function = SCRIPT_GLOBALS[name]
    return function(*args, **kwargs)


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _release_qualification_definition(
    revision: str,
    uv_digest: str,
    npm_digest: str,
    *,
    corpus_digest: str = "c" * 64,
    run_id: str = "run-1",
    started_utc: str = "2026-08-26T12:00:00.000000Z",
) -> dict[str, Any]:
    return release_qualification_v2_definition(
        run_id=run_id,
        started_utc=started_utc,
        git_revision=revision,
        python_version="3.12.11",
        platform_identity="Linux-test-x86_64",
        uv_lock_sha256=uv_digest,
        package_lock_sha256=npm_digest,
        corpus_manifest_sha256=corpus_digest,
        database_identity="postgresql+psycopg:///leo_qualification",
        protected_corpus_root="/srv/bulk/leo/test-corpus",
        native_rate_corpus_root="/srv/bulk/leo/recordings/2026/08/25",
    )


def _canonical_json_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def _test_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    ]


def _seal_test_tree(root: Path) -> None:
    paths = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in paths:
        path.chmod(0o550 if path.is_dir() else 0o440)
    root.chmod(0o550)


def _rewrite_sealed_json(path: Path, document: object) -> str:
    path.chmod(0o640)
    payload = _canonical_json_bytes(document)
    path.write_bytes(payload)
    path.chmod(0o440)
    return hashlib.sha256(payload).hexdigest()


def _refresh_release_receipt(
    receipt_path: Path,
    receipt: dict[str, Any],
    run_root: Path,
) -> None:
    receipt["evidence"] = _test_inventory(run_root)
    _rewrite_sealed_json(receipt_path, receipt)


def _release_qualification_fixture(
    tmp_path: Path,
    *,
    revision: str = "a" * 40,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    release = tmp_path / "release"
    uv_digest = _write(release / "uv.lock", b"locked-python\n")
    npm_digest = _write(release / "web/package-lock.json", b"locked-node\n")
    corpus_digest = _write(release / "corpus/manifest.json", b'{"schema":"test"}\n')
    _write(
        release / "src/leo/qualification/release_contract.py",
        (PROJECT_ROOT / "src/leo/qualification/release_contract.py").read_bytes(),
    )
    _write(release / "web/dist/index.html", b"<main>compiled</main>\n")
    _write(release / "web/dist/assets/app.js", b"compiled();\n")

    run_root = tmp_path / "qualification" / "run-1"
    definition = _release_qualification_definition(
        revision,
        uv_digest,
        npm_digest,
        corpus_digest=corpus_digest,
    )
    definition_digest = _write(
        run_root / "definition.json",
        _canonical_json_bytes(definition),
    )
    timestamp = "2026-08-26T12:00:00.000000Z"
    outcomes: list[dict[str, Any]] = []
    for command_name in RELEASE_QUALIFICATION_V2_COMMAND_NAMES:
        log_relative = RELEASE_QUALIFICATION_V2_LOG_PATHS[command_name]
        log_digest = _write(run_root / log_relative, f"{command_name} passed\n".encode())
        result_relative = RELEASE_QUALIFICATION_V2_RESULT_PATHS[command_name]
        if command_name in RELEASE_QUALIFICATION_V2_JUNIT_PATHS:
            junit_relative = RELEASE_QUALIFICATION_V2_JUNIT_PATHS[command_name]
            junit_payload = (
                "<testsuites><testsuite tests='1' failures='0' errors='0' skipped='0'>"
                f"<testcase classname='qualification' name='{command_name}'/>"
                "</testsuite></testsuites>\n"
            ).encode()
            _write(run_root / junit_relative, junit_payload)
            result = summarize_pytest_junit_v1(
                junit_payload,
                command_name=command_name,
                junit_relative_path=junit_relative,
            )
        elif command_name == "production-web-build":
            result = {
                "schema": "org.leo.release-qualification/v2",
                "kind": "compiled-web-inventory",
                "files": _test_inventory(release / "web/dist"),
            }
        else:
            _write(run_root / "results/playwright/trace.txt", b"browser trace\n")
            result = {
                "schema": "org.leo.release-qualification/v2",
                "kind": "production-chromium-e2e-result",
                "project": "production-chromium",
                "passed": True,
                "files": _test_inventory(run_root / "results/playwright"),
            }
        result_digest = _write(run_root / result_relative, _canonical_json_bytes(result))
        outcomes.append(
            {
                "name": command_name,
                "exit_code": 0,
                "passed": True,
                "started_utc": timestamp,
                "finished_utc": timestamp,
                "duration_seconds": 0.0,
                "log_relative_path": log_relative,
                "log_sha256": log_digest,
                "result_relative_path": result_relative,
                "result_sha256": result_digest,
                "validation_error": None,
            }
        )
    receipt = {
        "schema": "org.leo.release-qualification/v2",
        "run_id": "run-1",
        "status": "passed",
        "passed": True,
        "started_utc": timestamp,
        "finished_utc": timestamp,
        "duration_seconds": 0.0,
        "git_revision": revision,
        "definition_relative_path": "definition.json",
        "definition_sha256": definition_digest,
        "commands": outcomes,
        "evidence": _test_inventory(run_root),
    }
    receipt_path = run_root / "receipt.json"
    _write(receipt_path, _canonical_json_bytes(receipt))
    _seal_test_tree(run_root)
    return release, run_root, receipt_path, receipt


def _stage_reviewed_profiles(release: Path) -> None:
    for relative in SCRIPT_GLOBALS["REVIEWED_CAPTURE_PROFILE_SHA256"]:
        source = PROJECT_ROOT / relative
        target = release / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _canonical_target_digest(target: dict[str, Any]) -> str:
    payload = json.dumps(
        target,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _host_health_evidence(
    host_name: str,
    *,
    after_utc_ns: int | None = None,
) -> dict[str, Any]:
    policy = {
        "schema_version": 1,
        "raid_array_name": "md127",
        "disk_path": "/srv/bulk",
        "minimum_available_memory_bytes": 32 * 1024**3,
        "minimum_free_disk_bytes": 1024**4,
    }

    def snapshot(*, observed_utc_ns: int, observed_monotonic_ns: int) -> dict[str, Any]:
        values = {
            "schema_version": 1,
            "algorithm_version": "qualification-host-health-snapshot-v1",
            "host_name": host_name,
            "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
            "observed_utc_ns": observed_utc_ns,
            "observed_monotonic_ns": observed_monotonic_ns,
            "raid": {
                "schema_version": 1,
                "array_name": "md127",
                "raid_level": "raid6",
                "active": True,
                "expected_member_count": 8,
                "active_member_count": 8,
                "member_status": "UUUUUUUU",
                "active_operation": "none",
                "healthy": True,
            },
            "kernel_log_complete": True,
            "kernel_io_error_count": 0,
            "kernel_io_error_log_digest": (
                "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
            "oom_kill_count": 0,
            "swap_in_pages": 100,
            "swap_out_pages": 200,
            "available_memory_bytes": 64 * 1024**3,
            "disk_path": "/srv/bulk",
            "free_disk_bytes": 2 * 1024**4,
            "mdstat_digest": "sha256:" + "a" * 64,
            "meminfo_digest": "sha256:" + "b" * 64,
            "vmstat_digest": "sha256:" + "c" * 64,
        }
        return {**values, "snapshot_digest": _canonical_target_digest(values)}

    resolved_after_utc_ns = after_utc_ns or time.time_ns()
    before = snapshot(
        observed_utc_ns=resolved_after_utc_ns - 1_000,
        observed_monotonic_ns=100,
    )
    after = snapshot(observed_utc_ns=resolved_after_utc_ns, observed_monotonic_ns=200)
    check_names = [
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
    values = {
        "schema_version": 1,
        "algorithm_version": "qualification-host-health-pre-post-v1",
        "policy": policy,
        "before": before,
        "after": after,
        "checks": [{"schema_version": 1, "name": name, "passed": True} for name in check_names],
        "passed": True,
    }
    return {**values, "evidence_digest": _canonical_target_digest(values)}


def _reseal_v4_host_health(receipt: dict[str, Any]) -> None:
    health = receipt["target"]["prerequisites"]["host_health"]
    for name in ("before", "after"):
        snapshot = health[name]
        snapshot["snapshot_digest"] = _canonical_target_digest(
            {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
        )
    health["evidence_digest"] = _canonical_target_digest(
        {key: value for key, value in health.items() if key != "evidence_digest"}
    )
    receipt["target_digest"] = _canonical_target_digest(receipt["target"])


def _host_health_evidence_v2(
    host_name: str,
    *,
    after_utc_ns: int | None = None,
) -> dict[str, Any]:
    base = _host_health_evidence(host_name, after_utc_ns=after_utc_ns)
    removable_lines = [
        "Buffer I/O error on dev sdf1, logical block 2, async page read",
        "Buffer I/O error on dev sdf1, logical block 33, async page read",
        "I/O error, dev sdf, sector 265 op 0x0:(READ)",
    ]
    devices = [
        {
            "schema_version": 1,
            "name": "dm-5",
            "major_minor": "252:5",
            "removable": False,
            "protected": True,
        },
        {
            "schema_version": 1,
            "name": "md127",
            "major_minor": "9:127",
            "removable": False,
            "protected": True,
        },
        {
            "schema_version": 1,
            "name": "sdf",
            "major_minor": "8:80",
            "removable": True,
            "protected": False,
        },
        {
            "schema_version": 1,
            "name": "sdf1",
            "major_minor": "8:81",
            "removable": True,
            "protected": False,
        },
    ]
    errors = [
        {
            "schema_version": 1,
            "line": line,
            "line_sha256": "sha256:" + hashlib.sha256(line.encode()).hexdigest(),
            "block_devices": ["sdf1"] if "sdf1" in line else ["sdf"],
            "disposition": "ignored_preexisting_removable",
        }
        for line in removable_lines
    ]
    normalized = "\n".join(removable_lines).encode()

    def snapshot(base_snapshot: dict[str, Any]) -> dict[str, Any]:
        base_snapshot = copy.deepcopy(base_snapshot)
        base_snapshot["kernel_io_error_count"] = len(errors)
        base_snapshot["kernel_io_error_log_digest"] = (
            "sha256:" + hashlib.sha256(normalized).hexdigest()
        )
        base_snapshot["snapshot_digest"] = _canonical_target_digest(
            {key: value for key, value in base_snapshot.items() if key != "snapshot_digest"}
        )
        values = {
            "schema_version": 2,
            "algorithm_version": "qualification-host-health-snapshot-v2",
            "base": base_snapshot,
            "disk_mount_source": "/dev/mapper/vg_bulk-bulk",
            "block_devices": copy.deepcopy(devices),
            "kernel_io_errors": copy.deepcopy(errors),
            "relevant_kernel_io_error_count": 0,
            "ignored_removable_kernel_io_error_count": len(errors),
        }
        return {**values, "snapshot_digest": _canonical_target_digest(values)}

    check_names = list(SCRIPT_GLOBALS["_QUALIFICATION_HOST_HEALTH_CHECK_ORDER_V2"])
    values = {
        "schema_version": 2,
        "algorithm_version": "qualification-host-health-pre-post-v2",
        "policy": {
            "schema_version": 2,
            "raid_array_name": "md127",
            "disk_path": "/srv/bulk",
            "required_disk_mount_source": "/dev/mapper/vg_bulk-bulk",
            "minimum_available_memory_bytes": 32 * 1024**3,
            "minimum_free_disk_bytes": 1024**4,
        },
        "before": snapshot(base["before"]),
        "after": snapshot(base["after"]),
        "checks": [{"schema_version": 2, "name": name, "passed": True} for name in check_names],
        "passed": True,
    }
    return {**values, "evidence_digest": _canonical_target_digest(values)}


def _reseal_v5_host_health(receipt: dict[str, Any]) -> None:
    health = receipt["target"]["prerequisites"]["host_health"]
    for name in ("before", "after"):
        snapshot = health[name]
        base = snapshot["base"]
        lines = [item["line"] for item in snapshot["kernel_io_errors"]]
        base["kernel_io_error_count"] = len(lines)
        base["kernel_io_error_log_digest"] = (
            "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()
        )
        base["snapshot_digest"] = _canonical_target_digest(
            {key: value for key, value in base.items() if key != "snapshot_digest"}
        )
        snapshot["relevant_kernel_io_error_count"] = sum(
            item["disposition"] == "relevant" for item in snapshot["kernel_io_errors"]
        )
        snapshot["ignored_removable_kernel_io_error_count"] = sum(
            item["disposition"] == "ignored_preexisting_removable"
            for item in snapshot["kernel_io_errors"]
        )
        snapshot["snapshot_digest"] = _canonical_target_digest(
            {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
        )
    health["evidence_digest"] = _canonical_target_digest(
        {key: value for key, value in health.items() if key != "evidence_digest"}
    )
    receipt["target_digest"] = _canonical_target_digest(receipt["target"])


def _lossless_metrics(radio_id: str, sample_count: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "radio_id": radio_id,
        "requested_sample_count": sample_count,
        "observed_sample_count": sample_count,
        "device_span_sample_count": sample_count,
        "observed_gap_count": 0,
        "observed_missing_sample_count": 0,
        "observed_overflow_count": 0,
        "enqueue_failure_count": 0,
    }


def _usb_control_radios() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 2,
            "radio_id": "usb_control_pluto_003a",
            "serial": "104000bac4950008230026001b440a003a",
            "uri": "usb:5.27.5",
            "transport": "iio_usb",
            "model": "Pluto+",
            "firmware_version": "v0.41-control-a",
            "hardware_revision": None,
        },
        {
            "schema_version": 2,
            "radio_id": "usb_control_pluto_3ef2",
            "serial": "1040007c4a94000211000b009186843ef2",
            "uri": "usb:3.21.5",
            "transport": "iio_usb",
            "model": "Pluto+",
            "firmware_version": "v0.41-control-b",
            "hardware_revision": None,
        },
    ]


def _strict_rate_prerequisites() -> dict[str, Any]:
    radio_ids = ("radio_pluto_5d4d", "radio_pluto_19f2")
    safety = [
        {
            "schema_version": 1,
            "radio_id": radio_id,
            "pre_safety_evidence_sha256": "sha256:" + f"{index + 1:x}" * 64,
            "post_safety_evidence_sha256": "sha256:" + f"{index + 3:x}" * 64,
            "pre_tx_safe": True,
            "post_tx_safe": True,
            "rx_settings_restored": True,
            "passed": True,
        }
        for index, radio_id in enumerate(radio_ids)
    ]
    canaries = [
        {
            "schema_version": 1,
            "transport": "iio_ip",
            "duration_ns": 1_000_000_000,
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "evidence_sha256": "sha256:" + f"{index + 5:x}" * 64,
            "metrics": _lossless_metrics(radio_id, 3_000_000),
            "passed": True,
        }
        for index, radio_id in enumerate(radio_ids)
    ]
    usb_radios = _usb_control_radios()
    usb_intervals = [
        {
            "schema_version": 2,
            "radio_id": radio["radio_id"],
            "started_monotonic_ns": 1_000_000_000,
            "ended_monotonic_ns": 61_000_000_000,
        }
        for radio in usb_radios
    ]
    usb_restoration = [
        {
            "schema_version": 2,
            "radio_id": radio["radio_id"],
            "pre_settings_evidence_sha256": "sha256:" + f"{index + 9:x}" * 64,
            "post_settings_evidence_sha256": "sha256:" + f"{index + 11:x}" * 64,
            "rx_settings_restored": True,
            "passed": True,
        }
        for index, radio in enumerate(usb_radios)
    ]
    return {
        "schema_version": 2,
        "radio_safety": safety,
        "native_ip_canaries": canaries,
        "usb_control_arm": {
            "schema_version": 2,
            "transport": "iio_usb",
            "simultaneous": True,
            "duration_ns": 60_000_000_000,
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "evidence_sha256": "sha256:" + "7" * 64,
            "minimum_overlap_fraction": 0.99,
            "radios": usb_radios,
            "capture_intervals": usb_intervals,
            "radio_restoration": usb_restoration,
            "radio_metrics": [
                _lossless_metrics(radio["radio_id"], 180_000_000) for radio in usb_radios
            ],
            "passed": True,
        },
        "writer_benchmark": {
            "schema_version": 1,
            "payload_kind": "incompressible",
            "evidence_sha256": "sha256:" + "8" * 64,
            "uncompressed_bytes_written": 144_000_000,
            "elapsed_ns": 2_000_000_000,
            "sustained_bytes_per_second": 72_000_000,
            "passed": True,
        },
    }


def _expected_rate_radios() -> list[dict[str, Any]]:
    return [
        {
            "radio_id": "radio_pluto_5d4d",
            "serial": "1040005e0b100007100010000bf33a5d4d",
            "uri": "ip:192.168.1.20",
            "transport": "iio_ip",
            "firmware_version": "v0.38",
        },
        {
            "radio_id": "radio_pluto_19f2",
            "serial": "10400056f695001322002d0010ad1719f2",
            "uri": "ip:192.168.1.21",
            "transport": "iio_ip",
            "firmware_version": "v0.38",
        },
    ]


def _expected_rate_radios_v4() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            **radio,
            "model": "Pluto+",
            "hardware_revision": None,
        }
        for radio in _expected_rate_radios()
    ]


def _device_axis_stream_check(
    radio_id: str,
    *,
    trial_index: int,
) -> dict[str, Any]:
    observed_digest = (
        "sha256:" + hashlib.sha256(f"{trial_index}:{radio_id}:observed".encode()).hexdigest()
    )

    def digest(label: str) -> str:
        return "sha256:" + hashlib.sha256(f"{trial_index}:{radio_id}:{label}".encode()).hexdigest()

    return {
        "schema_version": 1,
        "radio_id": radio_id,
        "logical_sample_count": 180_000_000,
        "observed_sample_count": 180_000_000,
        "zero_fill_sample_count": 0,
        "continuity_segment_count": 1,
        "observed_iq_sha256": observed_digest,
        "logical_iq_sha256": observed_digest,
        "timeline_sha256": digest("timeline"),
        "gap_map_sha256": digest("gap-map"),
        "validity_inventory_sha256": digest("validity"),
    }


def _five_m_stream_check(radio_id: str, *, index: int) -> dict[str, Any]:
    def digest(label: str) -> str:
        return "sha256:" + hashlib.sha256(f"5m:{index}:{radio_id}:{label}".encode()).hexdigest()

    return {
        "schema_version": 1,
        "radio_id": radio_id,
        "logical_sample_count": 300_000_000,
        "observed_sample_count": 299_737_856,
        "zero_fill_sample_count": 262_144,
        "continuity_segment_count": 2,
        "gap_count": 1,
        "missing_sample_count": 262_144,
        "overflow_count": 0,
        "enqueue_failure_count": 0,
        "terminal_rejected_gap_count": 0,
        "terminal_rejected_missing_sample_count": 0,
        "terminal_rejected_overflow_count": 0,
        "queue_capacity_refills": 32,
        "queue_high_water_refills": 24,
        "gap_map_segment_count": 2,
        "gap_map_boundary_count": 1,
        "validity_segment_count": 2,
        "observed_iq_sha256": digest("observed-iq"),
        "logical_iq_sha256": digest("logical-iq"),
        "timeline_sha256": digest("timeline"),
        "gap_map_sha256": digest("gap-map"),
        "validity_inventory_sha256": digest("validity"),
    }


def _five_m_characterization(
    *,
    radios: list[dict[str, Any]],
    host: dict[str, Any],
    producer: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_sha256": "sha256:" + "d" * 64,
        "manifest_sha256": "sha256:" + "e" * 64,
        "session_id": "session-5m-characterization",
        "profile_revision_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_5M_DEVICE_AXIS_PROFILE_DIGEST"],
        "capture_plan_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_5M_DEVICE_AXIS_PLAN_DIGEST"],
        "sample_rate_hz": 5_000_000,
        "bandwidth_hz": 2_500_000,
        "requested_sample_count": 300_000_000,
        "radios": copy.deepcopy(radios),
        "host": copy.deepcopy(host),
        "producer": copy.deepcopy(producer),
        "manifest_state": "degraded",
        "streams": [
            _five_m_stream_check(radio["radio_id"], index=index)
            for index, radio in enumerate(radios)
        ],
        "bundle_verified": True,
        "physical_zero_verified": True,
        "validity_verified": True,
        "gap_map_verified": True,
        "passed": True,
        "errors": [],
    }


def _live_station_probe_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "radios": [
            {
                "schema_version": 1,
                **radio,
                "firmware_version": "v0.48-plutoplus-spf-iq-direct-async-v3",
                "metadata_abi_version": 3,
                "buffer_direct_async": True,
                "buffer_direct_async_ring": True,
                "buffer_direct_async_overrun_policies": [
                    "drop-backlog",
                    "preserve-backlog",
                ],
                "buffer_direct_async_default_overrun_policy": "drop-backlog",
                "buffer_ddr_ring_max_iq_bytes": 200_000_000,
                "supports_device_sample_counter": True,
                "supports_continuity_sequence": True,
            }
            for radio in _expected_rate_radios()
        ],
    }


def test_qnap_is_rejected_lexically_without_access() -> None:
    with pytest.raises(ValueError, match="must not resolve beneath /mnt/qnap01"):
        _call("reject_qnap", Path("/mnt/qnap01/never-open-this"), "evidence")


@pytest.mark.parametrize(
    ("reviewed", "tampered"),
    (
        ("continuity_policy: allow_segments", "continuity_policy: require_contiguous"),
        (
            "tags: [CAPTURE_ONLY, DEVICE_AXIS_ZERO_FILL, EXPERIMENTAL, LIVE, "
            "RANDOM_TUNING, STANDARD_NATIVE]",
            "tags: [DEVICE_AXIS_ZERO_FILL, EXPERIMENTAL, LIVE, RANDOM_TUNING, STANDARD_NATIVE]",
        ),
    ),
)
def test_staged_profile_bytes_reject_five_msps_policy_or_tag_tamper(
    tmp_path: Path,
    reviewed: str,
    tampered: str,
) -> None:
    release = tmp_path / "release"
    _stage_reviewed_profiles(release)
    _call("verify_staged_capture_profiles", release)

    five_msps = release / "profiles/starlink-ch4-lower-5m-60s-device-axis-v3.yaml"
    payload = five_msps.read_text(encoding="utf-8")
    assert reviewed in payload
    five_msps.write_text(payload.replace(reviewed, tampered), encoding="utf-8")

    with pytest.raises(ValueError, match=r"digest mismatch: .*5m-60s-device-axis"):
        _call("verify_staged_capture_profiles", release)


def test_v4_qualification_constants_bind_deployed_three_msps_profile_and_plan() -> None:
    revision = load_profile_revision(
        PROJECT_ROOT / "profiles/starlink-ch4-lower-3m-60s-device-axis-v3.yaml"
    )
    assert isinstance(revision, CaptureProfileRevisionV2)
    plan = compile_capture_plan(
        revision,
        ("radio_pluto_5d4d", "radio_pluto_19f2"),
        source_type=SourceType.LIVE,
    )

    assert (
        revision.revision_digest == SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_PROFILE_DIGEST"]
    )
    assert plan.plan_digest == SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_PLAN_DIGEST"]
    assert (
        tuple(revision.profile.tags)
        == SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_REQUIRED_TAGS"]
    )
    five_m_revision = load_profile_revision(
        PROJECT_ROOT / "profiles/starlink-ch4-lower-5m-60s-device-axis-v3.yaml"
    )
    assert isinstance(five_m_revision, CaptureProfileRevisionV2)
    five_m_plan = compile_capture_plan(
        five_m_revision,
        ("radio_pluto_5d4d", "radio_pluto_19f2"),
        source_type=SourceType.LIVE,
    )
    assert (
        five_m_revision.revision_digest
        == SCRIPT_GLOBALS["CONTIGUOUS_RATE_5M_DEVICE_AXIS_PROFILE_DIGEST"]
    )
    assert five_m_plan.plan_digest == SCRIPT_GLOBALS["CONTIGUOUS_RATE_5M_DEVICE_AXIS_PLAN_DIGEST"]


def test_staged_acquisition_service_requires_exact_profile_and_radio_order(
    tmp_path: Path,
) -> None:
    _call("verify_staged_acquisition_service", PROJECT_ROOT)

    release = tmp_path / "release"
    service = release / SCRIPT_GLOBALS["ACQUISITION_SERVICE_RELATIVE_PATH"]
    service.parent.mkdir(parents=True)
    expected = SCRIPT_GLOBALS["EXPECTED_ACQUISITION_EXEC_START"]
    assert expected.startswith(
        "/usr/bin/env PYTHONDONTWRITEBYTECODE=1 "
        "/opt/leo-tracker/current-acquisition/.venv/bin/leo acquire run "
    )
    service.write_text(f"[Service]\nExecStart={expected}\n", encoding="utf-8")
    _call("verify_staged_acquisition_service", release)

    profile_5m = "--profile ${LEO_CAPTURE_PROFILE_5M} "
    radio_a = "--radio radio_pluto_5d4d "
    radio_b = "--radio radio_pluto_19f2 "
    mixed_policy = "--mixed-rate-policy ${LEO_MIXED_RATE_POLICY}"
    tampered_commands = (
        expected.replace("PYTHONDONTWRITEBYTECODE=1 ", ""),
        expected.replace(profile_5m, ""),
        expected.replace(profile_5m, profile_5m + profile_5m),
        expected.replace(radio_a + radio_b, radio_b + radio_a),
        expected.replace(radio_b, ""),
        expected.replace(radio_b, radio_b + "--radio unexpected-radio "),
        expected.replace(mixed_policy, ""),
        expected.replace(mixed_policy, "--mixed-rate-policy mixed-native-rates-16-safe-v1"),
    )
    assert len(set(tampered_commands)) == len(tampered_commands)
    for command in tampered_commands:
        service.write_text(f"[Service]\nExecStart={command}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="exact ordered profile and radio pool"):
            _call("verify_staged_acquisition_service", release)


def test_live_station_probe_uses_staged_adapter_and_rejects_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    payload = _live_station_probe_payload()
    calls: list[tuple[tuple[str, ...], float | None]] = []

    def fake_command(*argv: str, timeout_seconds: float | None = None) -> str:
        calls.append((argv, timeout_seconds))
        return json.dumps(payload)

    function = SCRIPT_GLOBALS["probe_live_station_radios"]
    monkeypatch.setitem(function.__globals__, "command", fake_command)
    assert _call("probe_live_station_radios", release) == payload
    argv, timeout_seconds = calls[-1]
    assert argv[:4] == ("runuser", "-u", "leo", "--")
    assert argv[4:7] == (str(release / ".venv/bin/python"), "-I", "-c")
    assert "from leo.radio import PlutoIioRadioSource" in argv[7]
    assert timeout_seconds == 30.0

    payload = _live_station_probe_payload()
    payload["radios"][0]["firmware_version"] = "v0.44-plutoplus-spf-ddr-ring-prefill-v1"
    with pytest.raises(ValueError, match="exact qualified v0.48"):
        _call("probe_live_station_radios", release)

    payload = _live_station_probe_payload()
    payload["radios"][1]["serial"] = "different-serial"
    with pytest.raises(ValueError, match="identity differs"):
        _call("probe_live_station_radios", release)

    payload = _live_station_probe_payload()
    payload["radios"][0]["metadata_abi_version"] = 2
    with pytest.raises(ValueError, match="metadata ABI"):
        _call("probe_live_station_radios", release)

    payload = _live_station_probe_payload()
    payload["radios"][0]["supports_device_sample_counter"] = False
    with pytest.raises(ValueError, match="counter-authoritative capabilities"):
        _call("probe_live_station_radios", release)

    payload = _live_station_probe_payload()
    payload["radios"][0]["buffer_direct_async_ring"] = False
    with pytest.raises(ValueError, match="does not attest RAM/drop direct-async"):
        _call("probe_live_station_radios", release)


def test_native_bandwidth_receipt_uses_staged_contract_and_exact_v5_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    release = tmp_path / "release"
    root = tmp_path / "native-bandwidth"
    receipt = root / revision / "native-bandwidth-qualification-receipt-v1.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}\n", encoding="utf-8")
    receipt.chmod(0o440)
    created_utc_ns = time.time_ns()
    host = {
        "schema_version": 1,
        "hostname": "gauss",
        "machine_id": "machine-id",
        "operating_system": "test-linux",
    }
    radios = _expected_rate_radios_v4()
    ppu_revision = "8" * 40
    summary = {
        "target_revision": revision,
        "host": host,
        "radios": radios,
        "pluto_plus_utils_revision": ppu_revision,
        "created_utc_ns": created_utc_ns,
        "modes": [
            "ordinary_2p5",
            "ordinary_3",
            "ordinary_5",
            "mixed_2p5_5_high_first",
            "mixed_2p5_5_high_second",
        ],
    }
    calls: list[tuple[str, ...]] = []

    def fake_command(*argv: str, timeout_seconds: float | None = None) -> str:
        assert timeout_seconds is None
        calls.append(argv)
        return json.dumps(summary)

    function = SCRIPT_GLOBALS["verify_native_bandwidth_receipt_v1"]
    monkeypatch.setitem(function.__globals__, "NATIVE_BANDWIDTH_RECEIPT_ROOT", root)
    monkeypatch.setitem(function.__globals__, "command", fake_command)
    rate_target = {
        "expected_host": host,
        "expected_radios": radios,
        "pluto_plus_utils_revision": ppu_revision,
    }

    _call(
        "verify_native_bandwidth_receipt_v1",
        receipt,
        revision=revision,
        release=release,
        rate_target=rate_target,
    )

    assert len(calls) == 1
    argv = calls[0]
    assert argv[:4] == ("runuser", "-u", "leo", "--")
    assert argv[4:8] == (str(release / ".venv/bin/python"), "-I", "-B", "-c")
    assert "NativeBandwidthQualificationReceiptV1.model_validate_json" in argv[8]
    assert argv[9] == str(receipt)

    for key, value in (
        ("target_revision", "b" * 40),
        ("host", {**host, "hostname": "other-host"}),
        ("radios", list(reversed(radios))),
        ("pluto_plus_utils_revision", "9" * 40),
        ("modes", summary["modes"][:-1]),
    ):
        original = summary[key]
        summary[key] = value
        with pytest.raises(ValueError, match="differs from the V5"):
            _call(
                "verify_native_bandwidth_receipt_v1",
                receipt,
                revision=revision,
                release=release,
                rate_target=rate_target,
            )
        summary[key] = original

    summary["created_utc_ns"] = time.time_ns() - SCRIPT_GLOBALS["RATE_RECEIPT_MAXIMUM_AGE_NS"] - 1
    with pytest.raises(ValueError, match="stale or future-dated"):
        _call(
            "verify_native_bandwidth_receipt_v1",
            receipt,
            revision=revision,
            release=release,
            rate_target=rate_target,
        )

    with pytest.raises(ValueError, match="path is not the revision authority"):
        _call(
            "verify_native_bandwidth_receipt_v1",
            tmp_path / "alias.json",
            revision=revision,
            release=release,
            rate_target=rate_target,
        )


def test_processing_resource_capacity_probe_is_exact_read_only_and_service_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = "cpu|8\nheavy|2\nmemory|4\nstreaming|16"
    calls: list[tuple[tuple[str, ...], float | None]] = []

    def fake_command(*argv: str, timeout_seconds: float | None = None) -> str:
        calls.append((argv, timeout_seconds))
        return expected

    function = SCRIPT_GLOBALS["probe_processing_resource_capacity"]
    monkeypatch.setitem(function.__globals__, "command", fake_command)

    _call("probe_processing_resource_capacity")

    assert calls == [
        (
            (
                "runuser",
                "-u",
                "leo",
                "--",
                "/usr/bin/psql",
                "--no-psqlrc",
                "--set=ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--host=/var/run/postgresql",
                "--port=5432",
                "--username=leo",
                "--no-password",
                "--dbname=leo_tracker",
                "--command",
                SCRIPT_GLOBALS["PROCESSING_RESOURCE_CAPACITY_QUERY"],
            ),
            15.0,
        )
    ]
    assert SCRIPT_GLOBALS["PROCESSING_RESOURCE_CAPACITY_QUERY"].startswith("SELECT ")


def test_native_bandwidth_v2_receipt_requires_counter_refill_and_exact_rf_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    release = tmp_path / "release"
    root = tmp_path / "native-bandwidth"
    receipt = root / revision / "native-bandwidth-qualification-receipt-v2.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}\n", encoding="utf-8")
    receipt.chmod(0o440)
    created_utc_ns = time.time_ns()
    host = {
        "schema_version": 1,
        "hostname": "gauss",
        "machine_id": "machine-id",
        "operating_system": "test-linux",
    }
    radios = _expected_rate_radios_v4()
    ppu_revision = "8" * 40
    summary = {
        "target_revision": revision,
        "host": host,
        "radios": radios,
        "pluto_plus_utils_revision": ppu_revision,
        "created_utc_ns": created_utc_ns,
        "modes": [
            "ordinary_2p5",
            "ordinary_3",
            "ordinary_5",
            "mixed_2p5_5_high_first",
            "mixed_2p5_5_high_second",
        ],
        "metadata_rate_inventory": [[2_500_000, 3_000_000, 5_000_000]] * 2,
        "largest_passing_refill_inventory": [[1_048_576] * 3] * 2,
        "exact_rf_readback_inventory": [[True] * 3] * 2,
    }
    calls: list[tuple[str, ...]] = []

    def fake_command(*argv: str, timeout_seconds: float | None = None) -> str:
        assert timeout_seconds is None
        calls.append(argv)
        return json.dumps(summary)

    function = SCRIPT_GLOBALS["verify_native_bandwidth_receipt_v2"]
    monkeypatch.setitem(function.__globals__, "NATIVE_BANDWIDTH_RECEIPT_ROOT", root)
    monkeypatch.setitem(function.__globals__, "command", fake_command)
    rate_target = {
        "expected_host": host,
        "expected_radios": radios,
        "pluto_plus_utils_revision": ppu_revision,
    }

    _call(
        "verify_native_bandwidth_receipt_v2",
        receipt,
        revision=revision,
        release=release,
        rate_target=rate_target,
    )
    assert "NativeBandwidthQualificationReceiptV2.model_validate_json" in calls[0][8]

    for key, value in (
        ("largest_passing_refill_inventory", [[2_097_152] * 3] * 2),
        ("exact_rf_readback_inventory", [[False] * 3] * 2),
        ("metadata_rate_inventory", [[2_500_000, 3_000_000]] * 2),
    ):
        original = summary[key]
        summary[key] = value
        with pytest.raises(ValueError, match="counter, RF, or V5"):
            _call(
                "verify_native_bandwidth_receipt_v2",
                receipt,
                revision=revision,
                release=release,
                rate_target=rate_target,
            )
        summary[key] = original


@pytest.mark.parametrize(
    "inventory",
    (
        "cpu|8\nheavy|4\nmemory|4\nstreaming|16",
        "cpu|8\nheavy|2\nmemory|4",
        "cpu|8\nheavy|2\nmemory|4\nstreaming|16\nunreviewed|1",
        "cpu|8\nheavy|2\nmemory|4\nstreaming|16\nstreaming|16",
        "streaming|16\ncpu|8\nmemory|4\nheavy|2",
        "",
    ),
)
def test_processing_resource_capacity_rejects_drift_or_malformed_inventory(
    inventory: str,
) -> None:
    with pytest.raises(ValueError, match="resource capacity inventory"):
        _call("verify_processing_resource_capacity_rows", inventory)


def test_live_station_probe_runs_only_after_both_unit_scopes_are_quiescent() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    verify_source = text[text.index("def verify(args:") : text.index("\ndef main()")]
    capacity = verify_source.index("    probe_processing_resource_capacity()")
    probe = verify_source.index("    probe_live_station_radios(")
    assert verify_source.index("    if unexpected_legacy:") < capacity
    assert verify_source.index("    if system_active:") < capacity
    assert capacity < probe


def test_environment_binds_exact_release_roots_and_station_radios() -> None:
    revision = "a" * 40
    radios = [
        {
            "radio_id": "radio_pluto_5d4d",
            "serial": "1040005e0b100007100010000bf33a5d4d",
            "host": "192.168.1.20",
            "receiver_count": 2,
        },
        {
            "radio_id": "radio_pluto_19f2",
            "serial": "10400056f695001322002d0010ad1719f2",
            "host": "192.168.1.21",
            "receiver_count": 2,
        },
    ]
    environment = "\n".join(
        (
            "LEO_BULK_ROOT=/srv/bulk/leo",
            "LEO_QUALIFICATION_ROOT=/srv/bulk/leo/qualification",
            "LEO_CAPTURE_EVIDENCE_ROOT=/srv/bulk/leo/qualification/capture",
            "LEO_LEGACY_EVIDENCE_ROOT=/srv/bulk/leo/qualification/legacy",
            "LEO_STATION_AUTHORITY_ROOT=/etc/leo/station-authority",
            "LEO_STATION_TOPOLOGY_RELATIVE_PATH=gauss-four-path-postreboot-20260816-v1.json",
            "LEO_STATION_TOPOLOGY_FILE_DIGEST="
            "sha256:5ec14f15bfe2a6abc52024f41db29b4ab6123209e6c4779a47644b1e70c477ae",
            "LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]",
            "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-native-bandwidth-v4",
            "LEO_MIXED_RATE_POLICY=production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2",
            "LEO_DIRECT_ASYNC_ENABLED=true",
            "LEO_CAPTURE_INTERVAL_SECONDS=180",
            "LEO_QUALIFICATION_PROFILE=starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2",
            "LEO_SOAK_PROFILE=starlink-ch4-lower-2p5m-60s-continuity-v2",
            "LEO_SCANNER_ENABLED=true",
            "LEO_SCANNER_RADIO_ID=radio_pluto_5d4d",
            "LEO_SCANNER_INTERVAL_SECONDS=180",
            "LEO_SCANNER_MAXIMUM_LATENESS_SECONDS=180",
            "LEO_SCANNER_DWELL_MS=120",
            "LEO_SCANNER_GAIN_DB=40.0",
            "LEO_SCANNER_MARGIN_GATE=0.025",
            "LEO_SCANNER_REPORT_ROOT=/srv/bulk/leo/scanner-reports",
            f"LEO_PIPELINE_RELEASE_ID={revision}",
            f"LEO_RADIOS_JSON='{json.dumps(radios, separators=(',', ':'))}'",
        )
    )

    _call("verify_environment_text", environment, revision)

    with pytest.raises(ValueError, match="pipeline release ID"):
        _call("verify_environment_text", environment.replace(revision, "b" * 40), revision)
    with pytest.raises(ValueError, match="station topology"):
        _call(
            "verify_environment_text",
            environment.replace("radio_pluto_19f2", "pluto-b"),
            revision,
        )
    with pytest.raises(ValueError, match="station topology"):
        _call(
            "verify_environment_text",
            environment.replace(
                json.dumps(radios, separators=(",", ":")),
                json.dumps(list(reversed(radios)), separators=(",", ":")),
            ),
            revision,
        )
    with pytest.raises(ValueError, match="capture interval"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_INTERVAL_SECONDS=180", "LEO_CAPTURE_INTERVAL_SECONDS=0"
            ),
            revision,
        )
    with pytest.raises(ValueError, match="dual-RX"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="sample-rate profile pool"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-native-bandwidth-v4",
                "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-capture-v2",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="qualification and soak"):
        _call(
            "verify_environment_text",
            environment.replace(
                "starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2",
                "starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="scanner configuration"):
        _call(
            "verify_environment_text",
            environment.replace("LEO_SCANNER_ENABLED=true", "LEO_SCANNER_ENABLED=false"),
            revision,
        )
    station_lines = tuple(
        line for line in environment.splitlines() if line.startswith("LEO_STATION_")
    )
    for line in station_lines:
        with pytest.raises(ValueError, match="exact reviewed root"):
            _call("verify_environment_text", environment.replace(f"{line}\n", ""), revision)
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace("/etc/leo/station-authority", "/tmp/retargeted"),
            revision,
        )
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]",
                "LEO_FIXTURE_PATH_AUTHORITIES_JSON={}",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace("LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]\n", ""),
            revision,
        )


def test_installed_station_authority_requires_exact_inode_and_digest(tmp_path: Path) -> None:
    parent = tmp_path / "leo"
    root = parent / "station-authority"
    parent.mkdir(mode=0o750)
    root.mkdir(mode=0o750)
    source = PROJECT_ROOT / "deploy/station/gauss-four-path-postreboot-20260816-v1.json"
    installed = root / source.name
    installed.write_bytes(source.read_bytes())
    installed.chmod(0o440)

    _call(
        "verify_station_authority_install",
        installed,
        expected_uid=installed.stat().st_uid,
        expected_gid=installed.stat().st_gid,
    )
    with pytest.raises(ValueError, match="ownership"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid + 1,
        )

    installed.chmod(0o640)
    with pytest.raises(ValueError, match="sealed"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid,
        )
    installed.write_bytes(b"{}")
    installed.chmod(0o440)
    with pytest.raises(ValueError, match="digest mismatch"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid,
        )


def test_scanner_data_directories_must_be_installed_exactly(tmp_path: Path) -> None:
    root = tmp_path / "bulk"
    root.mkdir()
    for relative in ("scanner-recordings", "scanner-reports"):
        path = root / relative
        path.mkdir(mode=0o770)
        path.chmod(0o2770)

    uid = root.stat().st_uid
    gid = root.stat().st_gid
    _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)

    (root / "scanner-reports").chmod(0o770)
    with pytest.raises(ValueError, match="permissions are not exact"):
        _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)

    (root / "scanner-reports").rmdir()
    with pytest.raises(ValueError, match="is missing"):
        _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)


def test_standard_cutover_receipt_is_exact_and_bound_to_staged_golden(
    tmp_path: Path,
) -> None:
    receipt_relative = Path("corpus/goldens/trial-132-standard-v2-full-review-receipt.json")
    summary_relative = Path("corpus/goldens/trial-132-standard-v2-summary.json")
    release = tmp_path / "release"
    receipt_source = PROJECT_ROOT / receipt_relative
    summary_source = PROJECT_ROOT / summary_relative
    (release / receipt_relative).parent.mkdir(parents=True)
    (release / receipt_relative).write_bytes(receipt_source.read_bytes())
    (release / summary_relative).write_bytes(summary_source.read_bytes())
    sealed = tmp_path / "standard-regression-receipt.json"
    sealed.write_bytes(receipt_source.read_bytes())
    sealed.chmod(0o440)
    receipt = _call("load_json", sealed, "Standard four-path regression receipt")

    _call("verify_standard_regression_receipt", sealed, receipt, release=release)

    (release / summary_relative).write_text("{}\n")
    with pytest.raises(ValueError, match="reviewed Standard golden"):
        _call("verify_standard_regression_receipt", sealed, receipt, release=release)
    (release / summary_relative).write_bytes(summary_source.read_bytes())
    tampered = dict(receipt)
    tampered["fixture_id"] = "other"
    with pytest.raises(ValueError, match="receipt contents"):
        _call("verify_standard_regression_receipt", sealed, tampered, release=release)


def test_json_receipt_must_be_sealed_and_not_a_symlink(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"accepted": true}\n')
    with pytest.raises(ValueError, match="not sealed read-only"):
        _call("load_json", receipt, "receipt")

    receipt.chmod(0o440)
    assert _call("load_json", receipt, "receipt") == {"accepted": True}

    link = tmp_path / "receipt-link.json"
    link.symlink_to(receipt)
    with pytest.raises(ValueError, match="must not be a symlink"):
        _call("load_json", link, "receipt")


def test_three_msps_receipt_is_exact_ten_trial_station_authority(tmp_path: Path) -> None:
    revision = "a" * 40
    now_utc_ns = time.time_ns()
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)
    release = tmp_path / "release"
    _write(release / "pyproject.toml", (PROJECT_ROOT / "pyproject.toml").read_bytes())
    runtime = {
        "schema_version": 1,
        "metadata_abi": 1,
        "libiio_version": "0.25 / test",
        "native_libiio_sha256": "b" * 64,
        "pylibiio_sha256": "c" * 64,
    }
    _write(
        release / ".venv/share/pluto-plus-utils/metadata-runtime.json",
        json.dumps(runtime).encode("utf-8"),
    )
    ppu_revision = project["tool"]["uv"]["sources"]["pluto-plus-utils"]["rev"]
    receipt = {
        "kind": "contiguous_rate_qualification",
        "schema_version": 2,
        "created_utc_ns": now_utc_ns,
        "complete": True,
        "passed": True,
        "target": {
            "schema_version": 2,
            "qualification_id": f"native-ip-3m-{revision[:12]}",
            "profile_revision_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_PROFILE_DIGEST"],
            "capture_plan_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_PLAN_DIGEST"],
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "requested_sample_count": 180_000_000,
            "expected_radios": _expected_rate_radios(),
            "expected_host": {
                "hostname": socket.gethostname(),
                "machine_id": Path("/etc/machine-id").read_text().strip(),
                "operating_system": "test-linux",
            },
            "expected_producer": {
                "name": "leo-acquisition",
                "version": project["project"]["version"],
                "source_revision": revision,
            },
            "pluto_plus_utils_revision": ppu_revision,
            "libiio_version": "0.25 / test",
            "libiio_library_sha256": "sha256:" + "b" * 64,
            "python_iio_sha256": "sha256:" + "c" * 64,
            "native_network_interface": "enp132s0",
            "native_source_address": "192.168.1.142",
            "prerequisites": _strict_rate_prerequisites(),
            "policy": {
                "schema_version": 1,
                "required_trial_count": 10,
                "minimum_overlap_fraction": 0.99,
                "required_kernel_buffers": 8,
                "required_queue_capacity_refills": 32,
                "maximum_queue_high_water_fraction": 0.75,
                "required_metadata_abi_version": 1,
                "maximum_refill_service_interval_ns": 699_050_666,
                "required_tags": ["QUALIFICATION"],
            },
        },
        "checks": [
            {
                "trial_id": f"trial-{index:02d}",
                "session_id": f"session-{index:02d}",
                "manifest_sha256": "sha256:" + f"{index:064x}",
                "passed": True,
                "errors": [],
            }
            for index in range(10)
        ],
    }
    receipt["target_digest"] = _canonical_target_digest(receipt["target"])

    _call("verify_contiguous_rate_3m_receipt", receipt, revision=revision, release=release)

    v3_receipt = copy.deepcopy(receipt)
    v3_receipt["schema_version"] = 3
    v3_receipt["target"]["schema_version"] = 3
    v3_prerequisites = v3_receipt["target"]["prerequisites"]
    v3_prerequisites["schema_version"] = 3
    v3_prerequisites.pop("usb_control_arm")
    v3_receipt["target_digest"] = _canonical_target_digest(v3_receipt["target"])
    _call(
        "verify_contiguous_rate_3m_receipt_v3",
        v3_receipt,
        revision=revision,
        release=release,
    )

    v4_receipt = copy.deepcopy(v3_receipt)
    v4_receipt["schema_version"] = 4
    v4_target = v4_receipt["target"]
    v4_target["schema_version"] = 4
    v4_target["profile_revision_digest"] = SCRIPT_GLOBALS[
        "CONTIGUOUS_RATE_3M_DEVICE_AXIS_PROFILE_DIGEST"
    ]
    v4_target["capture_plan_digest"] = SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_PLAN_DIGEST"]
    v4_target["expected_radios"] = _expected_rate_radios_v4()
    v4_target["expected_host"]["schema_version"] = 1
    v4_target["expected_producer"]["schema_version"] = 1
    v4_prerequisites = v4_target["prerequisites"]
    v4_prerequisites["schema_version"] = 4
    v4_prerequisites["writer_benchmark"].update(
        {
            "uncompressed_bytes_written": 200_000_000,
            "elapsed_ns": 2_000_000_000,
            "sustained_bytes_per_second": 100_000_000,
        }
    )
    v4_prerequisites["host_health"] = _host_health_evidence(
        v4_target["expected_host"]["hostname"],
        after_utc_ns=now_utc_ns - 1,
    )
    assert QualificationHostHealthEvidenceV1.model_validate(v4_prerequisites["host_health"]).passed
    v4_prerequisites["five_m_characterization"] = _five_m_characterization(
        radios=v4_target["expected_radios"],
        host=v4_target["expected_host"],
        producer=v4_target["expected_producer"],
    )
    v4_target["policy"]["required_tags"] = list(
        SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_REQUIRED_TAGS"]
    )
    v4_receipt["checks"] = [
        {
            "schema_version": 2,
            "trial_id": f"trial-{index:02d}",
            "session_id": f"session-{index:02d}",
            "manifest_sha256": "sha256:" + f"{index:064x}",
            "passed": True,
            "errors": [],
            "manifest_schema_version": 3,
            "stream_checks": [
                _device_axis_stream_check(
                    radio_id,
                    trial_index=index,
                )
                for radio_id in ("radio_pluto_5d4d", "radio_pluto_19f2")
            ],
        }
        for index in range(10)
    ]
    v4_receipt["target_digest"] = _canonical_target_digest(v4_target)
    _call(
        "verify_contiguous_rate_3m_receipt_v4",
        v4_receipt,
        revision=revision,
        release=release,
    )

    v5_receipt = copy.deepcopy(v4_receipt)
    v5_receipt["schema_version"] = 5
    v5_target = v5_receipt["target"]
    v5_target["schema_version"] = 5
    v5_target["qualification_id"] = f"native-ip-3m-v5-{revision[:12]}"
    v5_target["prerequisites"]["schema_version"] = 5
    v5_target["prerequisites"]["host_health"] = _host_health_evidence_v2(
        v5_target["expected_host"]["hostname"],
        after_utc_ns=now_utc_ns - 1,
    )
    assert QualificationHostHealthEvidenceV2.model_validate(
        v5_target["prerequisites"]["host_health"]
    ).passed
    v5_receipt["target_digest"] = _canonical_target_digest(v5_target)
    _call(
        "verify_contiguous_rate_3m_receipt_v5",
        v5_receipt,
        revision=revision,
        release=release,
    )

    v6_receipt = copy.deepcopy(v5_receipt)
    v6_receipt["schema_version"] = 6
    v6_target = v6_receipt["target"]
    v6_target.update(
        {
            "schema_version": 6,
            "qualification_id": f"native-ip-3m-v6-{revision[:12]}",
            "profile_revision_digest": SCRIPT_GLOBALS[
                "CONTIGUOUS_RATE_3M_NATIVE_BANDWIDTH_PROFILE_DIGEST"
            ],
            "capture_plan_digest": SCRIPT_GLOBALS[
                "CONTIGUOUS_RATE_3M_NATIVE_BANDWIDTH_PLAN_DIGEST"
            ],
            "bandwidth_hz": 3_000_000,
        }
    )
    v6_prerequisites = v6_target["prerequisites"]
    v6_prerequisites["schema_version"] = 6
    for canary in v6_prerequisites["native_ip_canaries"]:
        canary["bandwidth_hz"] = 3_000_000
    v6_five_m = v6_prerequisites["five_m_characterization"]
    v6_five_m.update(
        {
            "schema_version": 2,
            "profile_revision_digest": SCRIPT_GLOBALS[
                "CONTIGUOUS_RATE_5M_NATIVE_BANDWIDTH_PROFILE_DIGEST"
            ],
            "capture_plan_digest": SCRIPT_GLOBALS[
                "CONTIGUOUS_RATE_5M_NATIVE_BANDWIDTH_PLAN_DIGEST"
            ],
            "bandwidth_hz": 5_000_000,
        }
    )
    v6_target["policy"].update(
        {
            "required_kernel_buffers": 4,
            "maximum_refill_service_interval_ns": 1_398_101_333,
            "required_tags": list(
                SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_NATIVE_BANDWIDTH_REQUIRED_TAGS"]
            ),
        }
    )
    v6_receipt["target_digest"] = _canonical_target_digest(v6_target)
    _call(
        "verify_contiguous_rate_3m_receipt_v6",
        v6_receipt,
        revision=revision,
        release=release,
    )

    narrow_v6 = copy.deepcopy(v6_receipt)
    narrow_v6["target"]["bandwidth_hz"] = 2_500_000
    narrow_v6["target_digest"] = _canonical_target_digest(narrow_v6["target"])
    with pytest.raises(ValueError, match="native RF bandwidth plan"):
        _call(
            "verify_contiguous_rate_3m_receipt_v6",
            narrow_v6,
            revision=revision,
            release=release,
        )

    narrow_five_m = copy.deepcopy(v6_receipt)
    narrow_five_m["target"]["prerequisites"]["five_m_characterization"]["bandwidth_hz"] = 2_500_000
    narrow_five_m["target_digest"] = _canonical_target_digest(narrow_five_m["target"])
    with pytest.raises(ValueError, match="5 MS/s characterization"):
        _call(
            "verify_contiguous_rate_3m_receipt_v6",
            narrow_five_m,
            revision=revision,
            release=release,
        )

    new_removable_error = copy.deepcopy(v5_receipt)
    after_health = new_removable_error["target"]["prerequisites"]["host_health"]["after"]
    line = "I/O error, dev sdf, sector 266 op 0x0:(READ)"
    after_health["kernel_io_errors"].append(
        {
            "schema_version": 1,
            "line": line,
            "line_sha256": "sha256:" + hashlib.sha256(line.encode()).hexdigest(),
            "block_devices": ["sdf"],
            "disposition": "ignored_preexisting_removable",
        }
    )
    _reseal_v5_host_health(new_removable_error)
    with pytest.raises(ValueError, match="changed storage or kernel error inventory"):
        _call(
            "verify_contiguous_rate_3m_receipt_v5",
            new_removable_error,
            revision=revision,
            release=release,
        )

    protected_error = copy.deepcopy(v5_receipt)
    before_health = protected_error["target"]["prerequisites"]["host_health"]["before"]
    before_health["kernel_io_errors"][0]["block_devices"] = ["md127"]
    before_health["kernel_io_errors"][0]["disposition"] = "relevant"
    _reseal_v5_host_health(protected_error)
    with pytest.raises(ValueError, match="malformed scoped evidence"):
        _call(
            "verify_contiguous_rate_3m_receipt_v5",
            protected_error,
            revision=revision,
            release=release,
        )

    with pytest.raises(ValueError, match="complete strict V5 pass"):
        _call(
            "verify_contiguous_rate_3m_receipt_v5",
            v4_receipt,
            revision=revision,
            release=release,
        )

    missing_host_health = copy.deepcopy(v4_receipt)
    missing_host_health["target"]["prerequisites"].pop("host_health")
    missing_host_health["target_digest"] = _canonical_target_digest(missing_host_health["target"])
    with pytest.raises(ValueError, match="exact combined campaign"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            missing_host_health,
            revision=revision,
            release=release,
        )

    extra_host_health_key = copy.deepcopy(v4_receipt)
    extra_host_health_key["target"]["prerequisites"]["host_health"]["unreviewed"] = True
    _reseal_v4_host_health(extra_host_health_key)
    with pytest.raises(ValueError, match="host-health prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            extra_host_health_key,
            revision=revision,
            release=release,
        )

    reordered_host_checks = copy.deepcopy(v4_receipt)
    reordered_host_checks["target"]["prerequisites"]["host_health"]["checks"].reverse()
    _reseal_v4_host_health(reordered_host_checks)
    with pytest.raises(ValueError, match="check inventory"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            reordered_host_checks,
            revision=revision,
            release=release,
        )

    wrong_host_policy = copy.deepcopy(v4_receipt)
    wrong_host_policy["target"]["prerequisites"]["host_health"]["policy"][
        "minimum_free_disk_bytes"
    ] -= 1
    _reseal_v4_host_health(wrong_host_policy)
    with pytest.raises(ValueError, match="reviewed host policy"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_host_policy,
            revision=revision,
            release=release,
        )

    forged_host_evidence_digest = copy.deepcopy(v4_receipt)
    forged_health = forged_host_evidence_digest["target"]["prerequisites"]["host_health"]
    forged_health["evidence_digest"] = "sha256:" + "f" * 64
    forged_host_evidence_digest["target_digest"] = _canonical_target_digest(
        forged_host_evidence_digest["target"]
    )
    with pytest.raises(ValueError, match="digest does not bind"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            forged_host_evidence_digest,
            revision=revision,
            release=release,
        )

    wrong_health_host = copy.deepcopy(v4_receipt)
    health = wrong_health_host["target"]["prerequisites"]["host_health"]
    health["before"]["host_name"] = "other-host"
    health["after"]["host_name"] = "other-host"
    _reseal_v4_host_health(wrong_health_host)
    with pytest.raises(ValueError, match="malformed or failing snapshot"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_health_host,
            revision=revision,
            release=release,
        )

    low_memory = copy.deepcopy(v4_receipt)
    low_memory_health = low_memory["target"]["prerequisites"]["host_health"]
    low_memory_health["before"]["available_memory_bytes"] = 32 * 1024**3 - 1
    _reseal_v4_host_health(low_memory)
    with pytest.raises(ValueError, match="malformed or failing snapshot"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            low_memory,
            revision=revision,
            release=release,
        )

    with pytest.raises(ValueError, match="complete strict V4 pass"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            v3_receipt,
            revision=revision,
            release=release,
        )
    with pytest.raises(ValueError, match="not a complete strict pass"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            v4_receipt,
            revision=revision,
            release=release,
        )

    wrong_plan_v4 = copy.deepcopy(v4_receipt)
    wrong_plan_v4["target"]["capture_plan_digest"] = SCRIPT_GLOBALS[
        "CONTIGUOUS_RATE_3M_PLAN_DIGEST"
    ]
    wrong_plan_v4["target_digest"] = _canonical_target_digest(wrong_plan_v4["target"])
    with pytest.raises(ValueError, match="deployed device-axis plan"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_plan_v4,
            revision=revision,
            release=release,
        )

    wrong_tags_v4 = copy.deepcopy(v4_receipt)
    wrong_tags_v4["target"]["policy"]["required_tags"].remove("DEVICE_AXIS_ZERO_FILL")
    wrong_tags_v4["target_digest"] = _canonical_target_digest(wrong_tags_v4["target"])
    with pytest.raises(ValueError, match="device-axis gate"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_tags_v4,
            revision=revision,
            release=release,
        )

    wrong_policy_type_v4 = copy.deepcopy(v4_receipt)
    wrong_policy_type_v4["target"]["policy"]["schema_version"] = True
    wrong_policy_type_v4["target_digest"] = _canonical_target_digest(wrong_policy_type_v4["target"])
    with pytest.raises(ValueError, match="device-axis gate"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_policy_type_v4,
            revision=revision,
            release=release,
        )

    old_check_schema_v4 = copy.deepcopy(v4_receipt)
    old_check_schema_v4["checks"][0]["schema_version"] = 1
    with pytest.raises(ValueError, match="failed or malformed trial check"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            old_check_schema_v4,
            revision=revision,
            release=release,
        )

    extra_check_field_v4 = copy.deepcopy(v4_receipt)
    extra_check_field_v4["checks"][0]["unreviewed"] = True
    with pytest.raises(ValueError, match="failed or malformed trial check"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            extra_check_field_v4,
            revision=revision,
            release=release,
        )

    zero_filled_v4 = copy.deepcopy(v4_receipt)
    zero_filled_v4["checks"][0]["stream_checks"][0]["observed_sample_count"] -= 1
    zero_filled_v4["checks"][0]["stream_checks"][0]["zero_fill_sample_count"] = 1
    with pytest.raises(ValueError, match="exact lossless closure"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            zero_filled_v4,
            revision=revision,
            release=release,
        )

    digest_mismatch_v4 = copy.deepcopy(v4_receipt)
    digest_mismatch_v4["checks"][0]["stream_checks"][0]["logical_iq_sha256"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="exact lossless closure"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            digest_mismatch_v4,
            revision=revision,
            release=release,
        )

    reversed_streams_v4 = copy.deepcopy(v4_receipt)
    reversed_streams_v4["checks"][0]["stream_checks"].reverse()
    with pytest.raises(ValueError, match="exact lossless closure"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            reversed_streams_v4,
            revision=revision,
            release=release,
        )

    missing_five_m_v4 = copy.deepcopy(v4_receipt)
    missing_five_m_v4["target"]["prerequisites"].pop("five_m_characterization")
    missing_five_m_v4["target_digest"] = _canonical_target_digest(missing_five_m_v4["target"])
    with pytest.raises(ValueError, match="exact combined campaign"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            missing_five_m_v4,
            revision=revision,
            release=release,
        )

    unverified_five_m_v4 = copy.deepcopy(v4_receipt)
    unverified_five_m_v4["target"]["prerequisites"]["five_m_characterization"][
        "physical_zero_verified"
    ] = False
    unverified_five_m_v4["target_digest"] = _canonical_target_digest(unverified_five_m_v4["target"])
    with pytest.raises(ValueError, match="exact combined V4 campaign"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            unverified_five_m_v4,
            revision=revision,
            release=release,
        )

    overflow_five_m_v4 = copy.deepcopy(v4_receipt)
    overflow_five_m_v4["target"]["prerequisites"]["five_m_characterization"]["streams"][0][
        "overflow_count"
    ] = 1
    overflow_five_m_v4["target_digest"] = _canonical_target_digest(overflow_five_m_v4["target"])
    with pytest.raises(ValueError, match="does not close its device axis"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            overflow_five_m_v4,
            revision=revision,
            release=release,
        )

    insufficient_writer_v4 = copy.deepcopy(v4_receipt)
    v4_writer = insufficient_writer_v4["target"]["prerequisites"]["writer_benchmark"]
    v4_writer.update(
        {
            "uncompressed_bytes_written": 99_999_999,
            "elapsed_ns": 1_000_000_000,
            "sustained_bytes_per_second": 99_999_999,
        }
    )
    insufficient_writer_v4["target_digest"] = _canonical_target_digest(
        insufficient_writer_v4["target"]
    )
    with pytest.raises(ValueError, match="100 MB/s gate"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            insufficient_writer_v4,
            revision=revision,
            release=release,
        )

    wrong_queue_capacity_v4 = copy.deepcopy(v4_receipt)
    wrong_queue_capacity_v4["target"]["prerequisites"]["five_m_characterization"]["streams"][0][
        "queue_capacity_refills"
    ] = 31
    wrong_queue_capacity_v4["target_digest"] = _canonical_target_digest(
        wrong_queue_capacity_v4["target"]
    )
    with pytest.raises(ValueError, match="does not close its device axis"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_queue_capacity_v4,
            revision=revision,
            release=release,
        )

    missing_queue_evidence_v4 = copy.deepcopy(v4_receipt)
    missing_queue_evidence_v4["target"]["prerequisites"]["five_m_characterization"]["streams"][
        0
    ].pop("queue_capacity_refills")
    missing_queue_evidence_v4["target_digest"] = _canonical_target_digest(
        missing_queue_evidence_v4["target"]
    )
    with pytest.raises(ValueError, match="unreviewed wire shape"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            missing_queue_evidence_v4,
            revision=revision,
            release=release,
        )

    excessive_queue_high_water_v4 = copy.deepcopy(v4_receipt)
    excessive_queue_high_water_v4["target"]["prerequisites"]["five_m_characterization"]["streams"][
        0
    ]["queue_high_water_refills"] = 25
    excessive_queue_high_water_v4["target_digest"] = _canonical_target_digest(
        excessive_queue_high_water_v4["target"]
    )
    with pytest.raises(ValueError, match="does not close its device axis"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            excessive_queue_high_water_v4,
            revision=revision,
            release=release,
        )

    wrong_five_m_plan_v4 = copy.deepcopy(v4_receipt)
    wrong_five_m_plan_v4["target"]["prerequisites"]["five_m_characterization"][
        "capture_plan_digest"
    ] = SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_DEVICE_AXIS_PLAN_DIGEST"]
    wrong_five_m_plan_v4["target_digest"] = _canonical_target_digest(wrong_five_m_plan_v4["target"])
    with pytest.raises(ValueError, match="exact combined V4 campaign"):
        _call(
            "verify_contiguous_rate_3m_receipt_v4",
            wrong_five_m_plan_v4,
            revision=revision,
            release=release,
        )

    v3_with_usb = copy.deepcopy(v3_receipt)
    v3_with_usb["target"]["prerequisites"]["usb_control_arm"] = copy.deepcopy(
        receipt["target"]["prerequisites"]["usb_control_arm"]
    )
    v3_with_usb["target_digest"] = _canonical_target_digest(v3_with_usb["target"])
    with pytest.raises(ValueError, match="prerequisites have an unsupported contract"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            v3_with_usb,
            revision=revision,
            release=release,
        )

    for required_prerequisite in (
        "radio_safety",
        "native_ip_canaries",
        "writer_benchmark",
    ):
        incomplete_v3 = copy.deepcopy(v3_receipt)
        incomplete_v3["target"]["prerequisites"].pop(required_prerequisite)
        incomplete_v3["target_digest"] = _canonical_target_digest(incomplete_v3["target"])
        with pytest.raises(ValueError, match="prerequisites have an unsupported contract"):
            _call(
                "verify_contiguous_rate_3m_receipt_v3",
                incomplete_v3,
                revision=revision,
                release=release,
            )

    with pytest.raises(ValueError, match="not a complete strict pass"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            v3_receipt,
            revision=revision,
            release=release,
        )
    with pytest.raises(ValueError, match="not a complete strict pass"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            receipt,
            revision=revision,
            release=release,
        )

    unsafe_v3 = copy.deepcopy(v3_receipt)
    unsafe_v3["target"]["prerequisites"]["radio_safety"][0]["post_tx_safe"] = False
    unsafe_v3["target_digest"] = _canonical_target_digest(unsafe_v3["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            unsafe_v3,
            revision=revision,
            release=release,
        )

    lossy_canary_v3 = copy.deepcopy(v3_receipt)
    lossy_canary_v3["target"]["prerequisites"]["native_ip_canaries"][1]["metrics"][
        "observed_gap_count"
    ] = 1
    lossy_canary_v3["target_digest"] = _canonical_target_digest(lossy_canary_v3["target"])
    with pytest.raises(ValueError, match="native-IP canaries"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            lossy_canary_v3,
            revision=revision,
            release=release,
        )

    slow_writer_v3 = copy.deepcopy(v3_receipt)
    v3_writer = slow_writer_v3["target"]["prerequisites"]["writer_benchmark"]
    v3_writer["uncompressed_bytes_written"] = 71_999_999
    v3_writer["elapsed_ns"] = 1_000_000_000
    v3_writer["sustained_bytes_per_second"] = 71_999_999
    slow_writer_v3["target_digest"] = _canonical_target_digest(slow_writer_v3["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            slow_writer_v3,
            revision=revision,
            release=release,
        )

    missing_time = copy.deepcopy(receipt)
    missing_time.pop("created_utc_ns")
    with pytest.raises(ValueError, match="missing or not an actual integer"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            missing_time,
            revision=revision,
            release=release,
        )

    future = copy.deepcopy(receipt)
    future["created_utc_ns"] = now_utc_ns + 10 * 60 * 1_000_000_000
    with pytest.raises(ValueError, match="more than five minutes in the future"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            future,
            revision=revision,
            release=release,
        )

    stale = copy.deepcopy(receipt)
    stale["created_utc_ns"] = now_utc_ns - 25 * 60 * 60 * 1_000_000_000
    with pytest.raises(ValueError, match="older than 24 hours"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            stale,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][0]["pre_safety_evidence_sha256"] = (
        "sha256:" + "9" * 64
    )
    with pytest.raises(ValueError, match="target digest does not bind the full target"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][0]["pre_safety_evidence_sha256"] = (
        "not-a-digest"
    )
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][1]["rx_settings_restored"] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["native_ip_canaries"][0]["metrics"][
        "observed_sample_count"
    ] -= 1
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="native-IP canaries"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["simultaneous"] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radio_metrics"].reverse()
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radios"][0]["serial"] = (
        "WRONG-CONTROL-SERIAL"
    )
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radios"].reverse()
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["capture_intervals"][1][
        "started_monotonic_ns"
    ] = 2_000_000_001
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radio_restoration"][0][
        "rx_settings_restored"
    ] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["writer_benchmark"]["sustained_bytes_per_second"] += 1
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    writer = tampered["target"]["prerequisites"]["writer_benchmark"]
    writer["uncompressed_bytes_written"] = 71_999_999
    writer["elapsed_ns"] = 1_000_000_000
    writer["sustained_bytes_per_second"] = 71_999_999
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    receipt["target"]["expected_radios"].reverse()
    with pytest.raises(ValueError, match="radio identities"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["target"]["expected_radios"].reverse()
    original_trial_id = receipt["checks"][4]["trial_id"]
    receipt["checks"][4]["trial_id"] = receipt["checks"][3]["trial_id"]
    with pytest.raises(ValueError, match="trial IDs are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["trial_id"] = original_trial_id

    original_session_id = receipt["checks"][4]["session_id"]
    receipt["checks"][4]["session_id"] = receipt["checks"][3]["session_id"]
    with pytest.raises(ValueError, match="session IDs are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["session_id"] = original_session_id

    original_manifest_digest = receipt["checks"][4]["manifest_sha256"]
    receipt["checks"][4]["manifest_sha256"] = receipt["checks"][3]["manifest_sha256"]
    with pytest.raises(ValueError, match="manifest digests are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["manifest_sha256"] = original_manifest_digest

    receipt["checks"][4]["passed"] = False
    with pytest.raises(ValueError, match="failed or malformed"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )


def test_release_inventory_and_lockfiles_verify_then_fail_on_tamper(tmp_path: Path) -> None:
    revision = "a" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )

    _call(
        "verify_release_evidence",
        receipt_path,
        receipt,
        release=release,
        revision=revision,
    )

    tampered_log = run_root / RELEASE_QUALIFICATION_V2_LOG_PATHS["protected-real-corpus"]
    tampered_log.chmod(0o640)
    tampered_log.write_text("tampered\n")
    tampered_log.chmod(0o440)
    with pytest.raises(ValueError, match="inventory is not exact|digest mismatch"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_qualification_v2_requires_exact_native_gate_inventory() -> None:
    definition = _release_qualification_definition("a" * 40, "u" * 64, "n" * 64)

    _call("_verify_release_qualification_commands", definition, release=PROJECT_ROOT)

    missing = copy.deepcopy(definition)
    missing["commands"].pop(3)
    with pytest.raises(ValueError, match="command inventory"):
        _call("_verify_release_qualification_commands", missing, release=PROJECT_ROOT)

    weakened = copy.deepcopy(definition)
    weakened["commands"][1]["argv"].remove(
        "tests/analysis/test_standard_native_scientific_equivalence.py"
    )
    with pytest.raises(ValueError, match="command inventory"):
        _call("_verify_release_qualification_commands", weakened, release=PROJECT_ROOT)

    presentation_weakened = copy.deepcopy(definition)
    presentation_weakened["commands"][2]["argv"].remove(
        "tests/processing/test_standard_native_presentation_vertical.py::"
        "test_real_postgres_promoted_gapped_native_run_is_presented_as_current_partial"
    )
    with pytest.raises(ValueError, match="command inventory"):
        _call(
            "_verify_release_qualification_commands",
            presentation_weakened,
            release=PROJECT_ROOT,
        )

    mixed_weakened = copy.deepcopy(definition)
    mixed_weakened["commands"][2]["argv"].remove(
        "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
        "test_real_postgres_mixed_capture_standard_png_and_browser_vertical"
    )
    with pytest.raises(ValueError, match="command inventory"):
        _call(
            "_verify_release_qualification_commands",
            mixed_weakened,
            release=PROJECT_ROOT,
        )


@pytest.mark.parametrize(
    ("command_index", "mutation"),
    (
        (0, "collect-only"),
        (1, "keyword-filter"),
        (1, "deselect"),
        (2, "cwd"),
        (3, "log"),
        (3, "junit"),
        (4, "web-argument"),
        (5, "browser-cwd"),
    ),
)
def test_release_qualification_v2_rejects_command_bypass_variants(
    command_index: int,
    mutation: str,
) -> None:
    definition = _release_qualification_definition("a" * 40, "u" * 64, "n" * 64)
    command = definition["commands"][command_index]
    if mutation == "collect-only":
        command["argv"].append("--collect-only")
    elif mutation == "keyword-filter":
        command["argv"].extend(("-k", "not_expensive"))
    elif mutation == "deselect":
        command["argv"].append("--deselect=tests/analysis/test_standard_native_qam.py")
    elif mutation == "cwd":
        command["cwd"] = "web"
    elif mutation == "log":
        command["log_relative_path"] = "logs/forged.log"
    elif mutation == "junit":
        command["argv"][-1] = "--junitxml=$EVIDENCE_ROOT/$RUN_ID/results/forged.xml"
    elif mutation == "web-argument":
        command["argv"].append("--emptyOutDir=false")
    else:
        command["cwd"] = "."

    with pytest.raises(ValueError, match="command inventory"):
        _call("_verify_release_qualification_commands", definition, release=PROJECT_ROOT)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    (
        ("source", "corpus_manifest_sha256", "f" * 64),
        ("source", "git_clean", False),
        ("isolation", "database", "postgresql+psycopg:///leo_tracker"),
        ("isolation", "protected_corpus_root", "/tmp/corpus"),
        ("isolation", "native_rate_corpus_root", "/tmp/native"),
    ),
)
def test_release_evidence_rejects_noncanonical_definition_authority(
    tmp_path: Path,
    section: str,
    key: str,
    value: object,
) -> None:
    revision = "c" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    definition_path = run_root / "definition.json"
    definition = json.loads(definition_path.read_bytes())
    definition[section][key] = value
    receipt["definition_sha256"] = _rewrite_sealed_json(definition_path, definition)
    _refresh_release_receipt(receipt_path, receipt, run_root)

    with pytest.raises(ValueError, match="canonical staged V2 contract"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_evidence_rejects_failed_or_forged_outcome(tmp_path: Path) -> None:
    revision = "d" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    receipt["commands"][0]["passed"] = False
    _rewrite_sealed_json(receipt_path, receipt)

    with pytest.raises(ValueError, match="did not pass exactly"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


@pytest.mark.parametrize("mutation", ("duplicate", "missing"))
def test_release_evidence_inventory_rejects_duplicate_or_missing_entries(
    tmp_path: Path,
    mutation: str,
) -> None:
    revision = "e" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    if mutation == "duplicate":
        receipt["evidence"].append(copy.deepcopy(receipt["evidence"][0]))
    else:
        receipt["evidence"].pop()
    _rewrite_sealed_json(receipt_path, receipt)

    with pytest.raises(ValueError, match="inventory is not exact and complete"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_evidence_rejects_closed_but_unexpected_file(tmp_path: Path) -> None:
    revision = "f" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    results = run_root / "results"
    results.chmod(0o750)
    _write(results / "forged.json", b"{}\n")
    (results / "forged.json").chmod(0o440)
    results.chmod(0o550)
    _refresh_release_receipt(receipt_path, receipt, run_root)

    with pytest.raises(ValueError, match="evidence file set is not closed"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_evidence_rejects_symlinked_definition(tmp_path: Path) -> None:
    revision = "1" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    outside = tmp_path / "outside-definition.json"
    outside.write_bytes((run_root / "definition.json").read_bytes())
    run_root.chmod(0o750)
    (run_root / "definition.json").unlink()
    (run_root / "definition.json").symlink_to(outside)
    run_root.chmod(0o550)

    try:
        with pytest.raises(ValueError, match="regular non-symlink file"):
            _call(
                "verify_release_evidence",
                receipt_path,
                receipt,
                release=release,
                revision=revision,
            )
    finally:
        run_root.chmod(0o750)
        (run_root / "definition.json").unlink()


def test_release_evidence_rejects_staged_web_drift(tmp_path: Path) -> None:
    revision = "2" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    (release / "web/dist/index.html").write_text("<main>different</main>\n")

    with pytest.raises(ValueError, match="compiled web output differs"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


@pytest.mark.parametrize(
    "relative",
    ("uv.lock", "web/package-lock.json", "corpus/manifest.json"),
)
def test_release_evidence_rejects_staged_source_input_drift(
    tmp_path: Path,
    relative: str,
) -> None:
    revision = "4" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    (release / relative).write_text("drifted after qualification\n")

    with pytest.raises(ValueError, match="canonical staged V2 contract"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_evidence_requires_staged_contract_source(tmp_path: Path) -> None:
    revision = "5" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    (release / "src/leo/qualification/release_contract.py").unlink()

    with pytest.raises(ValueError, match="staged release qualification contract.*unavailable"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_loading_staged_release_contract_does_not_write_bytecode(tmp_path: Path) -> None:
    release = tmp_path / "release"
    source = release / "src/leo/qualification/release_contract.py"
    _write(
        source,
        (PROJECT_ROOT / "src/leo/qualification/release_contract.py").read_bytes(),
    )

    interpreter = SCRIPT_GLOBALS["sys"]
    prior = interpreter.dont_write_bytecode
    _call("_load_release_qualification_contract", release)

    assert interpreter.dont_write_bytecode is prior
    assert not (source.parent / "__pycache__").exists()


def test_release_cutover_rejects_historical_v1_receipt(tmp_path: Path) -> None:
    revision = "6" * 40
    release, _run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    receipt["schema"] = "org.leo.release-qualification/v1"
    _rewrite_sealed_json(receipt_path, receipt)

    with pytest.raises(ValueError, match="required V2 schema"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_evidence_rejects_nonpassing_junit_even_if_inventoried(
    tmp_path: Path,
) -> None:
    revision = "3" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    junit_path = run_root / RELEASE_QUALIFICATION_V2_JUNIT_PATHS["protected-real-corpus"]
    junit_path.chmod(0o640)
    junit_path.write_text(
        "<testsuite tests='1' failures='0' errors='0' skipped='1'>"
        "<testcase classname='qualification' name='skipped'><skipped/></testcase>"
        "</testsuite>\n"
    )
    junit_path.chmod(0o440)
    _refresh_release_receipt(receipt_path, receipt, run_root)

    with pytest.raises(ValueError, match="JUnit result is invalid"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_inventory_refuses_parent_traversal(tmp_path: Path) -> None:
    revision = "b" * 40
    release, run_root, receipt_path, receipt = _release_qualification_fixture(
        tmp_path,
        revision=revision,
    )
    receipt["definition_relative_path"] = "../definition.json"
    receipt_path.chmod(0o640)
    receipt_path.write_bytes(_canonical_json_bytes(receipt))
    receipt_path.chmod(0o440)

    with pytest.raises(ValueError, match="definition path is not canonical"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_lean_cutover_cli_accepts_standard_authority_without_soak() -> None:
    result = subprocess.run(
        (
            str(SCRIPT),
            "--revision",
            "not-a-revision",
            "--legacy-user",
            "mouse9911",
            "--release-receipt",
            "/does/not/exist",
            "--standard-regression-receipt",
            "/does/not/exist",
        ),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "full lowercase 40-character SHA" in result.stderr
    assert "--soak-receipt" not in result.stderr


def test_full_cutover_uses_release_and_production_policy_without_obsolete_3m_gate() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    verify_source = text[text.index("def verify(args:") : text.index("\ndef main()")]

    assert "rate_qualification_receipt" not in verify_source
    assert "verify_contiguous_rate_3m_receipt" not in verify_source
    assert "verify_native_bandwidth_receipt" not in verify_source
    assert "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2" in verify_source


def test_cutover_allows_only_the_isolated_postgresql_user_unit() -> None:
    allowed = (
        "leo-forward-v2-postgresql.service loaded active running "
        "Isolated forward-only V2 PostgreSQL 16 database\n"
    )
    assert _call("unexpected_legacy_active_units", allowed) == ()

    output = allowed + (
        "leo-api-production.service loaded active running stale API\n"
        "leo-reconcile.timer loaded active waiting stale reconcile\n"
    )
    assert _call("unexpected_legacy_active_units", output) == (
        "leo-api-production.service loaded active running stale API",
        "leo-reconcile.timer loaded active waiting stale reconcile",
    )


def test_cutover_git_checks_are_read_only() -> None:
    text = SCRIPT.read_text()
    assert '("env", "GIT_OPTIONAL_LOCKS=0", "git", "-C", str(release))' in text
