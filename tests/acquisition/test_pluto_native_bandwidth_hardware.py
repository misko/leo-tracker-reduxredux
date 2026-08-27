"""Bounded hardware qualification for the enabled native-bandwidth capture pool.

This campaign is deliberately separate from the contiguous-rate V5 campaign. It
uses only the two production native-IP radios, never enables TX, restores both
radios before publishing evidence, and is inert without the authorization and
identity environment required by ``test_pluto_rate_modes_hardware``.
"""

from __future__ import annotations

import grp
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Event, Timer
from typing import Any
from uuid import uuid4

import pytest

from leo.acquisition import AcquisitionCoordinator
from leo.contracts.mixed_rate_capture import CapturePlanV3
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV3,
    RecordingManifestV4,
)
from leo.contracts.states import SourceType, StarlinkEdge
from leo.domain.mixed_rate_capture import compile_mixed_rate_capture_plan_v3
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.qualification.native_bandwidth import (
    NativeBandwidthCaptureEvidenceV2,
    NativeBandwidthCaptureModeV1,
    NativeBandwidthMetadataContinuityCellV1,
    NativeBandwidthMetadataLadderEvidenceV1,
    NativeBandwidthQualificationReceiptV2,
    NativeBandwidthTransportEvidenceV2,
    build_native_bandwidth_capture_evidence_v2,
    native_bandwidth_qualification_receipt_digest,
)
from leo.storage import RecordingStore
from tests.acquisition.test_pluto_rate_modes_hardware import (
    _RADIO_IDS,
    _RF_SHUTDOWN_RESERVE_SECONDS,
    _atomic_write_json,
    _attest_libiio,
    _attest_native_routes,
    _attest_production_radio_owners_quiescent,
    _attest_source_tree,
    _claim_paused_campaign_authority,
    _close_sources,
    _hardware_config,
    _host_identity,
    _new_sources,
    _preflight_radios,
    _producer,
    _require_campaign_time,
    _restore_radio_safety,
    _snapshot_radio_safety,
)

_NATIVE_BANDWIDTH_ROOT = Path("/srv/bulk/leo/qualification/native-bandwidth")
_PPU_ROOT = Path("/home/mouse9911/gits/pluto-plus-utils")
_PPU_EXECUTABLE = _PPU_ROOT / ".venv/bin/pluto"
_PPU_RATES = (2_500_000, 3_000_000, 5_000_000)
_PPU_REFILL_LADDER = (4_194_304, 2_097_152, 1_048_576, 524_288)
_REFILL_SAMPLES = 1_048_576
_KERNEL_BUFFERS = 4
_QUEUE_CAPACITY = 32
_DURATION_SECONDS = 60
_CAMPAIGN_BUDGET_SECONDS = 15 * 60
_MODES = tuple(NativeBandwidthCaptureModeV1)


def _ppu_ladder_argv(host: str, serial: str, rate_hz: int) -> tuple[str, ...]:
    return (
        str(_PPU_EXECUTABLE),
        "radio",
        "metadata-ladder",
        host,
        "--transport",
        "ip",
        "--expect-serial",
        serial,
        "--metadata-abi",
        "1",
        "--sample-rate-hz",
        str(rate_hz),
        "--rf-bandwidth-hz",
        str(rate_hz),
        "--frames",
        "6",
        "--samples",
        ",".join(str(item) for item in _PPU_REFILL_LADDER),
        "--kernel-buffers",
        str(_KERNEL_BUFFERS),
    )


def _attest_ppu_checkout(expected_revision: str) -> None:
    if not _PPU_EXECUTABLE.is_file():
        raise AssertionError(f"exact PPU executable is missing: {_PPU_EXECUTABLE}")
    head = subprocess.run(
        ("git", "-C", str(_PPU_ROOT), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    upstream = subprocess.run(
        ("git", "-C", str(_PPU_ROOT), "rev-parse", "origin/main"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        (
            "env",
            "GIT_OPTIONAL_LOCKS=0",
            "git",
            "-C",
            str(_PPU_ROOT),
            "status",
            "--porcelain",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != expected_revision or upstream != expected_revision or dirty:
        raise AssertionError(
            "pluto-plus-utils must be clean and exactly pinned to origin/main before RF work"
        )


def _run_ppu_ladder(
    *,
    radio_id: str,
    host: str,
    serial: str,
    ppu_revision: str,
    evidence_root: Path,
    campaign_deadline: float,
) -> NativeBandwidthTransportEvidenceV2:
    _require_campaign_time(
        campaign_deadline,
        phase=f"{radio_id} PPU native-bandwidth ladder",
        minimum_remaining_seconds=120 + _RF_SHUTDOWN_RESERVE_SECONDS,
    )
    ladders: list[NativeBandwidthMetadataLadderEvidenceV1] = []
    for rate_hz in _PPU_RATES:
        argv = _ppu_ladder_argv(host, serial, rate_hz)
        completed = subprocess.run(
            argv,
            cwd=_PPU_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        process_path = evidence_root / f"{radio_id}-ppu-{rate_hz}-process-v2.json"
        _atomic_write_json(
            process_path,
            {
                "argv": list(argv),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"{radio_id} {rate_hz} Hz PPU metadata ladder failed; "
                f"process evidence preserved at {process_path}"
            )
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"{radio_id} PPU metadata ladder returned malformed JSON; "
                f"evidence at {process_path}"
            ) from error
        report_path = evidence_root / f"{radio_id}-ppu-{rate_hz}-metadata-ladder-v1.json"
        _atomic_write_json(report_path, report)
        if (
            report.get("serial") != serial
            or report.get("uri") != f"ip:{host}"
            or report.get("transport") != "iio_ip"
            or report.get("metadata_abi") != 1
            or report.get("sample_rate_hz") != rate_hz
            or report.get("rf_bandwidth_hz") != rate_hz
            or report.get("kernel_buffers") != _KERNEL_BUFFERS
            or report.get("minimum_observed_fraction") != 0.95
            or report.get("largest_passing_samples_per_channel") != _REFILL_SAMPLES
            or report.get("original_settings_restored") is not True
            or report.get("failures") != []
        ):
            raise AssertionError(
                f"{radio_id} PPU metadata ladder identity, RF readback, or restoration is not exact"
            )
        cells = report.get("cells")
        if (
            not isinstance(cells, list)
            or tuple(item.get("samples_per_channel") for item in cells) != _PPU_REFILL_LADDER
        ):
            raise AssertionError(f"{radio_id} PPU metadata refill inventory is not exact")
        ladders.append(
            NativeBandwidthMetadataLadderEvidenceV1.model_validate(
                {
                    "report_sha256": _sha256_digest(report_path),
                    "metadata_abi": 1,
                    "sample_rate_hz": rate_hz,
                    "rf_bandwidth_hz": rate_hz,
                    "kernel_buffers": _KERNEL_BUFFERS,
                    "largest_passing_samples_per_channel": _REFILL_SAMPLES,
                    "original_settings_restored": True,
                    "readback_verified": True,
                    "failure_count": 0,
                    "cells": tuple(
                        NativeBandwidthMetadataContinuityCellV1(
                            samples_per_channel=item["samples_per_channel"],
                            requested_frames=item["requested_frames"],
                            observed_frames=item["observed_frames"],
                            observed_sample_count=item["observed_sample_count"],
                            device_span_sample_count=item["device_span_sample_count"],
                            missing_sample_count=item["missing_sample_count"],
                            gap_count=item["gap_count"],
                            overflow_count=item["overflow_count"],
                            observed_fraction=item["observed_fraction"],
                            passed=item["passed"],
                        )
                        for item in cells
                    ),
                }
            )
        )
    return NativeBandwidthTransportEvidenceV2.model_validate(
        {
            "radio_id": radio_id,
            "endpoint": host,
            "serial": serial,
            "pluto_plus_utils_revision": ppu_revision,
            "ladders": tuple(ladders),
        }
    )


def _sha256_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _make_leo_readable(path: Path, *, directory: bool) -> None:
    """Keep the sealed accepted authority traversable by cutover's leo validator."""

    leo_gid = grp.getgrnam("leo").gr_gid
    path.chmod(0o750 if directory else 0o440)
    os.chown(path, -1, leo_gid)


def _ordinary_plan(repository: Path, rate_label: str) -> CapturePlanV2:
    revision = load_profile_revision(
        repository / "profiles" / f"starlink-ch4-lower-{rate_label}-60s-native-bandwidth-v4.yaml"
    )
    assert isinstance(revision, CaptureProfileRevisionV2)
    profile = revision.profile
    if (
        profile.bandwidth_hz != profile.sample_rate_hz
        or profile.refill_samples != _REFILL_SAMPLES
        or profile.kernel_buffers != _KERNEL_BUFFERS
        or profile.refill_queue_capacity != _QUEUE_CAPACITY
        or "NATIVE_BANDWIDTH" not in profile.tags
    ):
        raise AssertionError("ordinary native-bandwidth profile geometry is not exact")
    plan = compile_capture_plan(revision, _RADIO_IDS, source_type=SourceType.LIVE)
    assert isinstance(plan, CapturePlanV2)
    return plan


def _mixed_plan(
    repository: Path,
    *,
    high_radio_index: int,
) -> CapturePlanV3:
    low = load_profile_revision(
        repository / "profiles/starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4.yaml"
    )
    high = load_profile_revision(
        repository / "profiles/starlink-ch4-lower-5m-60s-mixed-device-axis-v4.yaml"
    )
    assert isinstance(low, CaptureProfileRevisionV2)
    assert isinstance(high, CaptureProfileRevisionV2)
    revisions = {radio_id: low for radio_id in _RADIO_IDS}
    revisions[_RADIO_IDS[high_radio_index]] = high
    return compile_mixed_rate_capture_plan_v3(
        dwell_class=ProductionDwellClass.MIXED_2P5_5,
        radio_ids=_RADIO_IDS,
        profile_revisions_by_radio=revisions,
        starlink_channel=4,
        starlink_edge=StarlinkEdge.LOWER,
        source_type=SourceType.LIVE,
    )


def _capture_inventory(
    repository: Path,
) -> tuple[
    tuple[NativeBandwidthCaptureModeV1, CapturePlanV2 | CapturePlanV3],
    tuple[NativeBandwidthCaptureModeV1, CapturePlanV2 | CapturePlanV3],
    tuple[NativeBandwidthCaptureModeV1, CapturePlanV2 | CapturePlanV3],
    tuple[NativeBandwidthCaptureModeV1, CapturePlanV2 | CapturePlanV3],
    tuple[NativeBandwidthCaptureModeV1, CapturePlanV2 | CapturePlanV3],
]:
    return (
        (NativeBandwidthCaptureModeV1.ORDINARY_2P5, _ordinary_plan(repository, "2p5m")),
        (NativeBandwidthCaptureModeV1.ORDINARY_3, _ordinary_plan(repository, "3m")),
        (NativeBandwidthCaptureModeV1.ORDINARY_5, _ordinary_plan(repository, "5m")),
        (
            NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_FIRST,
            _mixed_plan(repository, high_radio_index=0),
        ),
        (
            NativeBandwidthCaptureModeV1.MIXED_2P5_5_HIGH_SECOND,
            _mixed_plan(repository, high_radio_index=1),
        ),
    )


def _capture_with_deadline(
    coordinator: AcquisitionCoordinator,
    plan: CapturePlanV2 | CapturePlanV3,
    *,
    config: Any,
    session_id: str,
    campaign_deadline: float,
) -> Any:
    _require_campaign_time(
        campaign_deadline,
        phase=session_id,
        minimum_remaining_seconds=_DURATION_SECONDS + _RF_SHUTDOWN_RESERVE_SECONDS,
    )
    sources = _new_sources(config)
    cancel = Event()
    cancel_after = max(
        0.0,
        campaign_deadline - time.monotonic() - _RF_SHUTDOWN_RESERVE_SECONDS,
    )
    timer = Timer(cancel_after, cancel.set)
    timer.daemon = True
    timer.start()
    try:
        result = coordinator.capture_once(
            plan,
            dict(zip(_RADIO_IDS, sources, strict=True)),
            session_id=session_id,
            cancel=cancel,
        )
    finally:
        timer.cancel()
        timer.join(timeout=1)
        close_errors = _close_sources(sources)
    if close_errors:
        raise AssertionError(session_id + " source close failed: " + "; ".join(close_errors))
    return result


def _conservative_campaign_wall_seconds() -> float:
    ppu_seconds = sum(2 * 6 * sum(_PPU_REFILL_LADDER) / rate / 0.9 for rate in _PPU_RATES)
    capture_seconds = len(_MODES) * (_DURATION_SECONDS + 2.0)
    return ppu_seconds + capture_seconds + 60.0


def _logical_raw_bytes(plan: CapturePlanV2 | CapturePlanV3) -> int:
    rates = (
        tuple(leg.requested_settings.sample_rate_hz for leg in plan.radio_plans)
        if isinstance(plan, CapturePlanV3)
        else (plan.profile_revision.profile.sample_rate_hz,) * 2
    )
    return sum(rate * _DURATION_SECONDS * 2 * 4 for rate in rates)


def test_native_bandwidth_campaign_is_bounded_and_uses_maximum_buffers() -> None:
    assert _conservative_campaign_wall_seconds() < _CAMPAIGN_BUDGET_SECONDS
    argv = _ppu_ladder_argv("192.168.1.20", "serial", 5_000_000)
    assert argv[argv.index("--samples") + 1] == "4194304,2097152,1048576,524288"
    assert argv[argv.index("--kernel-buffers") + 1] == "4"
    assert argv[argv.index("--sample-rate-hz") + 1] == "5000000"
    assert argv[argv.index("--rf-bandwidth-hz") + 1] == "5000000"


def test_enabled_hardware_plan_inventory_has_exact_native_rf_geometry() -> None:
    inventory = _capture_inventory(Path(__file__).resolve().parents[2])
    assert tuple(mode for mode, _plan in inventory) == _MODES
    for _mode, plan in inventory:
        if isinstance(plan, CapturePlanV3):
            for leg in plan.radio_plans:
                profile = leg.profile_revision.profile
                assert profile.bandwidth_hz == profile.sample_rate_hz
                assert profile.refill_samples == _REFILL_SAMPLES
                assert profile.kernel_buffers == _KERNEL_BUFFERS
                assert leg.requested_settings.bandwidth_hz == leg.requested_settings.sample_rate_hz
        else:
            profile = plan.profile_revision.profile
            assert profile.bandwidth_hz == profile.sample_rate_hz
            assert profile.refill_samples == _REFILL_SAMPLES
            assert profile.kernel_buffers == _KERNEL_BUFFERS


@pytest.mark.hardware
def test_native_ip_plutos_qualify_enabled_native_bandwidth_pool(
    request: pytest.FixtureRequest,
    record_property: Any,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = _hardware_config(repository)
    if config.hosts != ("192.168.1.20", "192.168.1.21") or config.serials != (
        "1040005e0b100007100010000bf33a5d4d",
        "10400056f695001322002d0010ad1719f2",
    ):
        pytest.fail(
            "native-bandwidth qualification requires exact ordered .20/.21 production radios",
            pytrace=False,
        )
    _attest_production_radio_owners_quiescent()
    _attest_source_tree(repository, config)
    _attest_libiio(config)
    _attest_native_routes(config)
    _attest_ppu_checkout(config.ppu_revision)

    _NATIVE_BANDWIDTH_ROOT.mkdir(mode=0o750, parents=True, exist_ok=True)
    campaign_id = f"native-bandwidth-{time.time_ns()}-{uuid4().hex[:8]}"
    campaign_root = _NATIVE_BANDWIDTH_ROOT / "campaigns" / campaign_id
    campaign_root.mkdir(mode=0o700, parents=True)
    evidence_root = campaign_root / "evidence"
    evidence_root.mkdir(mode=0o700)
    raw_bytes = sum(_logical_raw_bytes(plan) for _mode, plan in _capture_inventory(repository))
    required_free_bytes = raw_bytes + 1024**3
    available_free_bytes = shutil.disk_usage(campaign_root).free
    if available_free_bytes < required_free_bytes:
        pytest.fail(
            f"insufficient campaign storage: need {required_free_bytes}, "
            f"have {available_free_bytes}; preserved {campaign_root}",
            pytrace=False,
        )

    maintenance_claim = _claim_paused_campaign_authority(config, task_id=campaign_id)
    request.addfinalizer(maintenance_claim.verify_and_release)
    safety_snapshots = _snapshot_radio_safety(config, evidence_root=evidence_root)
    campaign_deadline = time.monotonic() + _CAMPAIGN_BUDGET_SECONDS
    host = _host_identity()
    producer = _producer(config)
    radios = _preflight_radios(config)
    store = RecordingStore(campaign_root / "bulk")
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            codec="zstd",
            level=3,
            target_uncompressed_bytes=128 * 1024 * 1024,
        ),
        host=host,
        producer=producer,
    )
    transport: list[NativeBandwidthTransportEvidenceV2] = []
    captures: list[NativeBandwidthCaptureEvidenceV2] = []
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    try:
        for radio_id, host_address, serial in zip(
            _RADIO_IDS,
            config.hosts,
            config.serials,
            strict=True,
        ):
            transport.append(
                _run_ppu_ladder(
                    radio_id=radio_id,
                    host=host_address,
                    serial=serial,
                    ppu_revision=config.ppu_revision,
                    evidence_root=evidence_root,
                    campaign_deadline=campaign_deadline,
                )
            )
        for mode, plan in _capture_inventory(repository):
            session_id = f"{campaign_id}-{mode.value}"
            result = _capture_with_deadline(
                coordinator,
                plan,
                config=config,
                session_id=session_id,
                campaign_deadline=campaign_deadline,
            )
            expected_manifest_type = (
                RecordingManifestV4 if isinstance(plan, CapturePlanV3) else RecordingManifestV3
            )
            if result.bundle is None or not isinstance(result.manifest, expected_manifest_type):
                raise AssertionError(
                    f"{session_id} did not publish its exact manifest major: "
                    f"state={result.state.value}; errors={result.errors!r}"
                )
            expected_errors = tuple(
                f"{stream.radio.radio_id}: {stream.error}"
                for stream in result.manifest.streams
                if stream.error is not None
            )
            if result.errors != expected_errors:
                raise AssertionError(f"{session_id} contains non-integrity capture errors")
            verification = store.verify(result.bundle)
            if (
                verification.timeline_count != 2
                or verification.gap_map_count != 2
                or verification.validity_inventory_count != 2
            ):
                raise AssertionError(f"{session_id} lacks physical-zero validity closure")
            captures.append(
                build_native_bandwidth_capture_evidence_v2(
                    result.manifest,
                    mode=mode,
                    manifest_sha256=result.bundle.manifest_sha256,
                )
            )
    except BaseException as error:  # pragma: no cover - real hardware failure path
        operation_error = error
    finally:
        try:
            _restore_radio_safety(config, safety_snapshots, evidence_root=evidence_root)
        except BaseException as error:  # pragma: no cover - real cleanup failure path
            restoration_error = error

    maintenance_claim.verify_and_release()
    if restoration_error is not None:
        raise restoration_error
    if operation_error is not None:
        raise operation_error
    if len(transport) != 2 or len(captures) != len(_MODES):
        raise AssertionError("native-bandwidth campaign evidence inventory is incomplete")

    candidate = NativeBandwidthQualificationReceiptV2.model_construct(
        target_revision=config.leo_revision,
        host=host,
        radios=radios,
        pluto_plus_utils_revision=config.ppu_revision,
        transport_evidence=(transport[0], transport[1]),
        captures=(captures[0], captures[1], captures[2], captures[3], captures[4]),
        created_utc_ns=time.time_ns(),
        receipt_digest="sha256:" + "0" * 64,
    )
    receipt = NativeBandwidthQualificationReceiptV2.model_validate(
        {
            **candidate.model_dump(mode="json"),
            "receipt_digest": native_bandwidth_qualification_receipt_digest(candidate),
        }
    )
    receipt_path = campaign_root / "native-bandwidth-qualification-receipt-v2.json"
    _atomic_write_json(receipt_path, receipt.model_dump(mode="json"))
    accepted_root = _NATIVE_BANDWIDTH_ROOT / "accepted" / config.leo_revision
    accepted_root.mkdir(mode=0o750, parents=True, exist_ok=False)
    _make_leo_readable(accepted_root.parent, directory=True)
    _make_leo_readable(accepted_root, directory=True)
    accepted_path = accepted_root / receipt_path.name
    _atomic_write_json(accepted_path, receipt.model_dump(mode="json"))
    _make_leo_readable(accepted_path, directory=False)
    record_property("native_bandwidth_qualification_receipt", str(receipt_path))
    record_property("accepted_native_bandwidth_qualification_receipt", str(accepted_path))
    print(f"accepted native-bandwidth qualification receipt: {accepted_path}")
