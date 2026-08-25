"""Opt-in, bounded full-recorder qualification for two native-IP Pluto+ radios.

This test is inert unless the operator supplies the exact authorization phrase and
every identity/evidence variable listed in ``_REQUIRED_ENV``. A typical invocation is::

    uv run --extra hardware pytest -ra -s \
      tests/acquisition/test_pluto_rate_modes_hardware.py

The output root must be an existing local directory outside this repository and
outside ``/mnt/qnap01``. The test creates one unique campaign directory and never
deletes recordings. The simultaneous direct-USB control arm uses a separate,
explicitly serial-attested pair; it never readdresses the production Ethernet pair.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from importlib.metadata import PackageNotFoundError, distribution, version
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from threading import Barrier, Event, Lock, Timer, get_ident
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from leo.acquisition import (
    AcquisitionCoordinator,
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioLease,
    RadioResource,
)
from leo.contracts.capture_control import CaptureDesiredState, CaptureObservedState
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2
from leo.contracts.radio import RadioIdentityV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV2,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV2,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    SourceType,
    StreamState,
    SynchronizationGrade,
)
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.qualification.rate_modes import (
    ContiguousRateNativeIpCanaryEvidenceV1,
    ContiguousRatePrerequisitesV2,
    ContiguousRateQualificationPolicyV1,
    ContiguousRateQualificationReceiptV2,
    ContiguousRateQualificationTargetV2,
    ContiguousRateRadioMetricsV1,
    ContiguousRateRadioSafetyEvidenceV1,
    ContiguousRateTrialEvidenceV1,
    ContiguousRateUsbControlArmEvidenceV2,
    ContiguousRateUsbRadioCaptureIntervalV2,
    ContiguousRateUsbRadioIdentityV2,
    ContiguousRateUsbRadioRestorationEvidenceV2,
    ContiguousRateWriterBenchmarkEvidenceV1,
    evaluate_contiguous_rate,
)
from leo.radio import PlutoIioRadioSource
from leo.storage import RecordingStore

_AUTHORIZATION_ENV = "LEO_PLUTO_RATE_HARDWARE_AUTHORIZATION"
_AUTHORIZATION_PHRASE = "I_AUTHORIZE_BOUNDED_RX_ONLY_3M_5M"
_REQUIRED_ENV = (
    "LEO_PLUTO_RATE_RADIO_A_HOST",
    "LEO_PLUTO_RATE_RADIO_A_SERIAL",
    "LEO_PLUTO_RATE_RADIO_B_HOST",
    "LEO_PLUTO_RATE_RADIO_B_SERIAL",
    "LEO_PLUTO_RATE_USB_CONTROL_A_SERIAL",
    "LEO_PLUTO_RATE_USB_CONTROL_B_SERIAL",
    "LEO_PLUTO_RATE_OUTPUT_ROOT",
    "LEO_PLUTO_RATE_TRIAL_COUNT",
    "LEO_PLUTO_RATE_LEO_REVISION",
    "LEO_PLUTO_RATE_PPU_REVISION",
    "LEO_PLUTO_RATE_LIBIIO_VERSION",
    "LEO_PLUTO_RATE_LIBIIO_LIBRARY_PATH",
    "LEO_PLUTO_RATE_LIBIIO_LIBRARY_SHA256",
    "LEO_PLUTO_RATE_PYTHON_IIO_SHA256",
    "LEO_PLUTO_RATE_NETWORK_INTERFACE",
    "LEO_PLUTO_RATE_NETWORK_SOURCE_ADDRESS",
)

_SAMPLE_RATE_HZ = 3_000_000
_FIVE_M_SAMPLE_RATE_HZ = 5_000_000
_BANDWIDTH_HZ = 2_500_000
_DURATION_SECONDS = 60
_REQUESTED_SAMPLE_COUNT = _SAMPLE_RATE_HZ * _DURATION_SECONDS
_FIVE_M_REQUESTED_SAMPLE_COUNT = _FIVE_M_SAMPLE_RATE_HZ * _DURATION_SECONDS
_REFILL_SAMPLES = 262_144
_KERNEL_BUFFERS = 8
_QUEUE_CAPACITY = 32
_REQUIRED_TRIAL_COUNT = 10
_MAXIMUM_SERVICE_INTERVAL_NS = _KERNEL_BUFFERS * _REFILL_SAMPLES * 1_000_000_000 // _SAMPLE_RATE_HZ
_NATIVE_NETWORK = IPv4Network("192.168.1.0/24")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_QNAP_ROOT = Path("/mnt/qnap01")
_RATE_QUALIFICATION_ROOT = Path("/srv/bulk/leo/qualification/sample-rate-3m")
_CAPTURE_AUTHORITY_ROOT = Path("/srv/bulk/leo/control")
_RADIO_IDS = ("radio_pluto_5d4d", "radio_pluto_19f2")
_USB_CONTROL_RADIO_IDS = ("usb_control_pluto_003a", "usb_control_pluto_3ef2")
_USB_CONTROL_SERIALS = (
    "104000bac4950008230026001b440a003a",
    "1040007c4a94000211000b009186843ef2",
)
_PRODUCTION_RADIO_OWNER_UNITS = (
    "leo-acquisition.service",
    "leo-acquisition-soak.service",
    "leo-qualification.service",
)
_AUTHORIZED_RF_BUDGET_SECONDS = 30 * 60
_IIO_READ_TIMEOUT_SECONDS = 5.0
_RF_SHUTDOWN_RESERVE_SECONDS = 15.0
_campaign_started_monotonic: float | None = None
_USB_CAPTURE_BARRIER_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class _HardwareConfig:
    hosts: tuple[str, str]
    serials: tuple[str, str]
    usb_control_serials: tuple[str, str]
    output_root: Path
    trial_count: int
    leo_revision: str
    ppu_revision: str
    libiio_version: str
    libiio_library_path: Path
    libiio_library_sha256: str
    python_iio_sha256: str
    network_interface: str
    network_source_address: str


@dataclass(frozen=True, slots=True)
class _MetadataCaptureResult:
    radio_id: str
    serial: str
    uri: str
    transport: str
    model: str
    firmware_version: str
    sample_rate_hz: int
    refill_samples: int
    requested_refills: int
    observed_refills: int
    observed_samples: int
    gap_count: int
    missing_samples: int
    overflow_count: int
    first_sample_sequence: int
    last_sample_sequence_exclusive: int
    capture_started_monotonic_ns: int
    capture_ended_monotonic_ns: int
    elapsed_seconds: float
    pre_settings_evidence_sha256: str | None
    post_settings_evidence_sha256: str | None
    rx_settings_restored: bool | None

    @property
    def passed(self) -> bool:
        return (
            self.observed_refills == self.requested_refills
            and self.gap_count == 0
            and self.missing_samples == 0
            and self.overflow_count == 0
        )


@dataclass(frozen=True, slots=True)
class _RadioSafetyContext:
    radio_id: str
    serial: str
    host: str
    original_settings: Any
    pre_safety: _HostRadioSafetyObservation
    pre_evidence_path: Path
    pre_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class _HostRadioSafetyObservation:
    identity: dict[str, Any]
    diagnostics: dict[str, Any]
    capabilities: dict[str, bool]
    open_succeeded: bool
    close_succeeded: bool
    tx_mute_basis: str = "ppu_iio_open_close_fail_closed"

    @property
    def tx_safe(self) -> bool:
        return self.open_succeeded and self.close_succeeded


@dataclass(frozen=True, slots=True)
class _RadioSafetyResult:
    context: _RadioSafetyContext
    apply_readback: Any
    restored_settings: Any
    settings_restored: bool
    post_safety: _HostRadioSafetyObservation
    post_evidence_path: Path
    post_evidence_sha256: str


@dataclass(slots=True)
class _CampaignMaintenanceClaim:
    authority: LocalCaptureAuthority
    lease: RadioLease
    expected_generation: int

    def verify_and_release(self) -> None:
        if self.lease.released:
            return
        try:
            final = self.authority.snapshot()
            if (
                final.generation != self.expected_generation
                or final.desired_state is not CaptureDesiredState.PAUSED
                or final.observed_state is not CaptureObservedState.PAUSED
            ):
                raise AssertionError(
                    "capture authority changed or resumed during the hardware campaign"
                )
        finally:
            self.lease.release()


class _TestMetadataCapture:
    def __init__(self, *, failure_mode: str | None, read_delay_seconds: float) -> None:
        self.failure_mode = failure_mode
        self.read_delay_seconds = read_delay_seconds
        self.closed = False

    def read_block(self) -> Any:
        if self.failure_mode == "capture":
            raise TimeoutError("synthetic metadata timeout")
        if self.read_delay_seconds:
            time.sleep(self.read_delay_seconds)
        return SimpleNamespace(
            sample_count=_REFILL_SAMPLES,
            missing_samples_before=0,
            overflow_observed=False,
            first_sample_sequence=0,
            last_sample_sequence_exclusive=_REFILL_SAMPLES,
        )

    def close(self) -> None:
        self.closed = True


class _TestMetadataDevice:
    def __init__(
        self,
        *,
        radio_id: str,
        serial: str,
        original_settings: Any,
        failure_mode: str | None = None,
        begin_delay_seconds: float = 0.0,
        read_delay_seconds: float = 0.0,
        primed_threads: set[int] | None = None,
        primed_lock: Lock | None = None,
    ) -> None:
        self.identity = SimpleNamespace(
            radio_id=radio_id,
            serial=serial,
            uri="usb:test",
            transport=SimpleNamespace(value="iio_usb"),
            model="Pluto+",
            firmware_version="v0.41-test",
        )
        self.capabilities = SimpleNamespace(
            supports_device_sample_counter=True,
            supports_continuity_sequence=True,
        )
        self.original_settings = original_settings
        self.current_settings = original_settings
        self.failure_mode = failure_mode
        self.begin_delay_seconds = begin_delay_seconds
        self.read_delay_seconds = read_delay_seconds
        self.primed_threads = primed_threads
        self.primed_lock = primed_lock
        self.capture: _TestMetadataCapture | None = None
        self.closed = False
        self.begin_calls = 0
        self.read_settings_calls = 0

    def open(self) -> None:
        return None

    def read_settings(self) -> Any:
        self.read_settings_calls += 1
        return self.current_settings

    def apply_settings(self, settings: Any) -> Any:
        if self.failure_mode == "restore" and settings == self.original_settings:
            return self.current_settings
        self.current_settings = settings
        return settings

    def begin_metadata_capture(
        self,
        _sample_count: int,
        *,
        kernel_buffers: int,
    ) -> _TestMetadataCapture:
        assert kernel_buffers == _KERNEL_BUFFERS
        self.begin_calls += 1
        if self.begin_delay_seconds:
            time.sleep(self.begin_delay_seconds)
        if self.primed_threads is not None and self.primed_lock is not None:
            with self.primed_lock:
                self.primed_threads.add(get_ident())
        self.capture = _TestMetadataCapture(
            failure_mode=self.failure_mode,
            read_delay_seconds=self.read_delay_seconds,
        )
        return self.capture

    def close(self) -> None:
        self.closed = True


class _TestRadioSafetyDevice:
    def __init__(
        self,
        *,
        radio_id: str,
        serial: str,
        uri: str,
        initial_settings: Any,
        apply_updates: dict[str, Any] | None = None,
        independent_updates: dict[str, Any] | None = None,
        close_error: str | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.radio_id = radio_id
        self.identity = SimpleNamespace(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            transport=SimpleNamespace(value="iio_ip"),
            model="Pluto+",
            firmware_version="v0.41-test",
        )
        self.capabilities = SimpleNamespace(
            supports_device_sample_counter=True,
            supports_continuity_sequence=True,
        )
        self.current_settings = initial_settings
        self.apply_updates = apply_updates or {}
        self.independent_updates = independent_updates or {}
        self.close_error = close_error
        self.events = events if events is not None else []

    def open(self) -> None:
        self.events.append(f"open:{self.radio_id}")

    def diagnostic_facts(self) -> dict[str, Any]:
        return {"buffer_metadata_abi": 1}

    def read_settings(self) -> Any:
        self.events.append(f"read:{self.radio_id}")
        return self.current_settings

    def apply_settings(self, settings: Any) -> Any:
        self.events.append(f"apply:{self.radio_id}")
        apply_readback = settings.model_copy(update=self.apply_updates)
        self.current_settings = settings.model_copy(update=self.independent_updates)
        return apply_readback

    def close(self) -> None:
        self.events.append(f"close:{self.radio_id}")
        if self.close_error is not None:
            raise RuntimeError(self.close_error)


def _unit_hardware_config(output_root: Path) -> _HardwareConfig:
    return _HardwareConfig(
        hosts=("192.168.1.20", "192.168.1.21"),
        serials=("production-a", "production-b"),
        usb_control_serials=_USB_CONTROL_SERIALS,
        output_root=output_root,
        trial_count=_REQUIRED_TRIAL_COUNT,
        leo_revision="a" * 40,
        ppu_revision="b" * 40,
        libiio_version="test",
        libiio_library_path=output_root / "libiio.so",
        libiio_library_sha256="sha256:" + "c" * 64,
        python_iio_sha256="sha256:" + "d" * 64,
        network_interface="eth-test",
        network_source_address="192.168.1.142",
    )


def _validate_radio_serial_inventory(
    production_serials: tuple[str, str],
    usb_control_serials: tuple[str, str],
) -> None:
    if any(
        not value or value != value.strip() for value in (*production_serials, *usb_control_serials)
    ):
        raise ValueError("hardware qualification serials must be exact non-empty values")
    if len(set(production_serials)) != 2:
        raise ValueError("production hardware qualification serials must be unique")
    if len(set(usb_control_serials)) != 2:
        raise ValueError("USB control hardware qualification serials must be unique")
    reused = set(production_serials).intersection(usb_control_serials)
    if reused:
        raise ValueError("USB control radios must be distinct from the production radio pair")
    if usb_control_serials != _USB_CONTROL_SERIALS:
        raise ValueError("USB control serials must match the exact ordered frozen control pair")


def _claim_paused_campaign_authority(
    config: _HardwareConfig,
    *,
    task_id: str,
) -> _CampaignMaintenanceClaim:
    radio_ids = (*_RADIO_IDS, *_USB_CONTROL_RADIO_IDS)
    resources = (
        RadioResource(_RADIO_IDS[0], config.serials[0], f"ip:{config.hosts[0]}"),
        RadioResource(_RADIO_IDS[1], config.serials[1], f"ip:{config.hosts[1]}"),
        RadioResource(_USB_CONTROL_RADIO_IDS[0], config.usb_control_serials[0], "usb:"),
        RadioResource(_USB_CONTROL_RADIO_IDS[1], config.usb_control_serials[1], "usb:"),
    )
    authority = LocalCaptureAuthority(_CAPTURE_AUTHORITY_ROOT, resources)
    state = authority.snapshot()
    if (
        state.desired_state is not CaptureDesiredState.PAUSED
        or state.observed_state is not CaptureObservedState.PAUSED
    ):
        raise AssertionError("capture authority is not exactly paused and drained")
    lease = authority.claim_paused_maintenance(
        radio_ids,
        task_id=task_id,
        expected_generation=state.generation,
    )
    if set(lease.radio_ids) != set(radio_ids) or len(lease.radio_ids) != len(radio_ids):
        lease.release()
        raise AssertionError("maintenance lease does not bind all four exact radios")
    if lease.task_kind is not CaptureTaskKind.QUALIFICATION:
        lease.release()
        raise AssertionError("maintenance lease is not a qualification claim")
    return _CampaignMaintenanceClaim(authority, lease, state.generation)


def _hardware_config(repository: Path) -> _HardwareConfig:
    authorization = os.environ.get(_AUTHORIZATION_ENV)
    if authorization != _AUTHORIZATION_PHRASE:
        pytest.skip(
            "bounded Pluto+ hardware campaign is not authorized; set "
            f"{_AUTHORIZATION_ENV}={_AUTHORIZATION_PHRASE!r} and all explicit identity vars: "
            + ", ".join(_REQUIRED_ENV)
        )
    missing = tuple(name for name in _REQUIRED_ENV if not os.environ.get(name, "").strip())
    if missing:
        pytest.skip(
            "authorized hardware campaign lacks explicit environment: " + ", ".join(missing)
        )

    values = {name: os.environ[name].strip() for name in _REQUIRED_ENV}
    try:
        trial_count = int(values["LEO_PLUTO_RATE_TRIAL_COUNT"])
    except ValueError as error:
        pytest.fail("LEO_PLUTO_RATE_TRIAL_COUNT must be an integer", pytrace=False)
        raise AssertionError from error
    if trial_count != _REQUIRED_TRIAL_COUNT:
        pytest.fail(
            f"LEO_PLUTO_RATE_TRIAL_COUNT must be exactly {_REQUIRED_TRIAL_COUNT}",
            pytrace=False,
        )

    hosts = (
        _native_ip(values["LEO_PLUTO_RATE_RADIO_A_HOST"], "radio A host"),
        _native_ip(values["LEO_PLUTO_RATE_RADIO_B_HOST"], "radio B host"),
    )
    source_address = _native_ip(
        values["LEO_PLUTO_RATE_NETWORK_SOURCE_ADDRESS"],
        "native network source address",
    )
    serials = (
        os.environ["LEO_PLUTO_RATE_RADIO_A_SERIAL"],
        os.environ["LEO_PLUTO_RATE_RADIO_B_SERIAL"],
    )
    usb_control_serials = (
        os.environ["LEO_PLUTO_RATE_USB_CONTROL_A_SERIAL"],
        os.environ["LEO_PLUTO_RATE_USB_CONTROL_B_SERIAL"],
    )
    if len(set(hosts)) != 2:
        pytest.fail("hardware qualification requires two unique native-IP hosts", pytrace=False)
    try:
        _validate_radio_serial_inventory(serials, usb_control_serials)
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)

    output_root = Path(values["LEO_PLUTO_RATE_OUTPUT_ROOT"])
    if not output_root.is_absolute() or not output_root.is_dir():
        pytest.fail(
            "LEO_PLUTO_RATE_OUTPUT_ROOT must be an existing absolute directory",
            pytrace=False,
        )
    output_root = output_root.resolve(strict=True)
    if output_root in {Path("/"), Path.home().resolve()}:
        pytest.fail(
            "hardware output root cannot be a broad system or home directory",
            pytrace=False,
        )
    if output_root == _QNAP_ROOT or _QNAP_ROOT in output_root.parents:
        pytest.fail(
            "hardware qualification outputs cannot be written beneath /mnt/qnap01",
            pytrace=False,
        )
    if output_root == repository or repository in output_root.parents:
        pytest.fail("hardware output root must be outside the source repository", pytrace=False)
    if output_root != _RATE_QUALIFICATION_ROOT:
        pytest.fail(
            f"LEO_PLUTO_RATE_OUTPUT_ROOT must be the reviewed {_RATE_QUALIFICATION_ROOT}",
            pytrace=False,
        )

    leo_revision = values["LEO_PLUTO_RATE_LEO_REVISION"]
    ppu_revision = values["LEO_PLUTO_RATE_PPU_REVISION"]
    if _GIT_SHA_PATTERN.fullmatch(leo_revision) is None:
        pytest.fail("LEO_PLUTO_RATE_LEO_REVISION must be one lowercase 40-hex SHA", pytrace=False)
    if _GIT_SHA_PATTERN.fullmatch(ppu_revision) is None:
        pytest.fail("LEO_PLUTO_RATE_PPU_REVISION must be one lowercase 40-hex SHA", pytrace=False)
    for name in ("LEO_PLUTO_RATE_LIBIIO_LIBRARY_SHA256", "LEO_PLUTO_RATE_PYTHON_IIO_SHA256"):
        if _SHA256_PATTERN.fullmatch(values[name]) is None:
            pytest.fail(f"{name} must use sha256:<64 lowercase hex>", pytrace=False)

    library_path = Path(values["LEO_PLUTO_RATE_LIBIIO_LIBRARY_PATH"])
    if not library_path.is_absolute() or not library_path.is_file():
        pytest.fail(
            "LEO_PLUTO_RATE_LIBIIO_LIBRARY_PATH must be an existing absolute file",
            pytrace=False,
        )
    interface = values["LEO_PLUTO_RATE_NETWORK_INTERFACE"]
    if len(interface) > 64 or any(character.isspace() for character in interface):
        pytest.fail("native network interface must be one exact interface name", pytrace=False)

    return _HardwareConfig(
        hosts=hosts,
        serials=serials,
        usb_control_serials=usb_control_serials,
        output_root=output_root,
        trial_count=trial_count,
        leo_revision=leo_revision,
        ppu_revision=ppu_revision,
        libiio_version=values["LEO_PLUTO_RATE_LIBIIO_VERSION"],
        libiio_library_path=library_path.resolve(strict=True),
        libiio_library_sha256=values["LEO_PLUTO_RATE_LIBIIO_LIBRARY_SHA256"],
        python_iio_sha256=values["LEO_PLUTO_RATE_PYTHON_IIO_SHA256"],
        network_interface=interface,
        network_source_address=source_address,
    )


def _native_ip(value: str, label: str) -> str:
    try:
        address = IPv4Address(value)
    except ValueError:
        pytest.fail(f"{label} must be one literal IPv4 address", pytrace=False)
    if address not in _NATIVE_NETWORK:
        pytest.fail(
            f"{label} must be on native {_NATIVE_NETWORK}, not USB gadget IP",
            pytrace=False,
        )
    return str(address)


def _campaign_deadline() -> float:
    global _campaign_started_monotonic  # noqa: PLW0603
    if _campaign_started_monotonic is None:
        _campaign_started_monotonic = time.monotonic()
    return _campaign_started_monotonic + _AUTHORIZED_RF_BUDGET_SECONDS


def _require_campaign_time(
    deadline: float,
    *,
    phase: str,
    minimum_remaining_seconds: float,
) -> None:
    remaining = deadline - time.monotonic()
    if remaining < minimum_remaining_seconds:
        raise AssertionError(
            f"authorized RF budget cannot admit {phase}: "
            f"{remaining:.3f}s remain, need {minimum_remaining_seconds:.3f}s"
        )


def _conservative_radio_seconds() -> float:
    native_refills = math.ceil(_SAMPLE_RATE_HZ / _REFILL_SAMPLES)
    three_m_refills = math.ceil(_REQUESTED_SAMPLE_COUNT / _REFILL_SAMPLES)
    five_m_refills = math.ceil(_FIVE_M_REQUESTED_SAMPLE_COUNT / _REFILL_SAMPLES)
    native = 2 * (native_refills + 1) * _REFILL_SAMPLES / _SAMPLE_RATE_HZ
    usb = 2 * (three_m_refills + 1) * _REFILL_SAMPLES / _SAMPLE_RATE_HZ
    strict_ip = (
        _REQUIRED_TRIAL_COUNT * 2 * (three_m_refills + 2) * _REFILL_SAMPLES / _SAMPLE_RATE_HZ
    )
    segmented_ip = 2 * (five_m_refills + 2) * _REFILL_SAMPLES / _FIVE_M_SAMPLE_RATE_HZ
    recorder_settles = (_REQUIRED_TRIAL_COUNT + 1) * 2 * 0.5
    return native + usb + strict_ip + segmented_ip + recorder_settles


def test_bounded_hardware_campaign_fits_authorized_rf_budget() -> None:
    assert _conservative_radio_seconds() <= _AUTHORIZED_RF_BUDGET_SECONDS


def test_usb_control_serial_configuration_is_explicit_and_separate() -> None:
    assert {
        "LEO_PLUTO_RATE_USB_CONTROL_A_SERIAL",
        "LEO_PLUTO_RATE_USB_CONTROL_B_SERIAL",
    }.issubset(_REQUIRED_ENV)
    assert _USB_CONTROL_RADIO_IDS == (
        "usb_control_pluto_003a",
        "usb_control_pluto_3ef2",
    )
    assert all("SSH" not in name for name in _REQUIRED_ENV)
    assert {"ssh_password", "ssh_known_hosts"}.isdisjoint(_HardwareConfig.__dataclass_fields__)
    production = ("production-a", "production-b")
    controls = _USB_CONTROL_SERIALS
    _validate_radio_serial_inventory(production, controls)

    with pytest.raises(ValueError, match="USB control hardware qualification serials"):
        _validate_radio_serial_inventory(production, (controls[0], controls[0]))
    with pytest.raises(ValueError, match="exact ordered frozen control pair"):
        _validate_radio_serial_inventory(production, (controls[1], controls[0]))
    with pytest.raises(ValueError, match="distinct from the production"):
        _validate_radio_serial_inventory(production, (controls[0], production[1]))


def test_direct_usb_identity_attestation_rejects_transport_or_firmware_drift() -> None:
    identity = SimpleNamespace(
        radio_id=_USB_CONTROL_RADIO_IDS[0],
        serial="usb-control-a",
        uri="usb:5.27.5",
        transport=SimpleNamespace(value="iio_usb"),
        model="Pluto+",
        firmware_version="v0.41-control-a",
    )
    capabilities = SimpleNamespace(
        supports_device_sample_counter=True,
        supports_continuity_sequence=True,
    )
    assert _attest_metadata_capture_identity(
        identity,
        capabilities,
        radio_id=_USB_CONTROL_RADIO_IDS[0],
        serial="usb-control-a",
        requested_uri="usb:",
        expected_transport="iio_usb",
    ) == ("usb:5.27.5", "iio_usb", "Pluto+", "v0.41-control-a")

    identity.transport = SimpleNamespace(value="iio_ip")
    with pytest.raises(AssertionError, match="opened transport"):
        _attest_metadata_capture_identity(
            identity,
            capabilities,
            radio_id=_USB_CONTROL_RADIO_IDS[0],
            serial="usb-control-a",
            requested_uri="usb:",
            expected_transport="iio_usb",
        )
    identity.transport = SimpleNamespace(value="iio_usb")
    identity.firmware_version = None
    with pytest.raises(AssertionError, match="model and firmware identity"):
        _attest_metadata_capture_identity(
            identity,
            capabilities,
            radio_id=_USB_CONTROL_RADIO_IDS[0],
            serial="usb-control-a",
            requested_uri="usb:",
            expected_transport="iio_usb",
        )


def test_host_iio_safety_requires_exact_identity_capabilities_and_close() -> None:
    radio_id = _RADIO_IDS[0]
    serial = "production-a"
    uri = "ip:192.168.1.20"
    device = SimpleNamespace(
        identity=SimpleNamespace(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            transport=SimpleNamespace(value="iio_ip"),
            model="Pluto+",
            firmware_version="v0.41-test",
        ),
        capabilities=SimpleNamespace(
            supports_device_sample_counter=True,
            supports_continuity_sequence=True,
        ),
        diagnostic_facts=lambda: {
            "serial": serial,
            "firmware_version": "v0.41-test",
            "context_uri": uri,
            "phy_model": "ad9361",
            "buffer_metadata_abi": 1,
            "buffer_metadata_raw": "1",
            "buffer_metadata_state": "enabled",
            "tandem_agc": False,
            "rx_scan_channels": ("voltage0", "voltage1", "voltage2", "voltage3"),
        },
    )

    identity, diagnostics, capabilities = _opened_host_iio_safety_evidence(
        device,
        radio_id=radio_id,
        serial=serial,
        uri=uri,
    )
    observation = _HostRadioSafetyObservation(
        identity=identity,
        diagnostics=diagnostics,
        capabilities=capabilities,
        open_succeeded=True,
        close_succeeded=True,
    )
    assert observation.tx_safe
    assert diagnostics["buffer_metadata_abi"] == 1
    assert diagnostics["tandem_agc"] is False
    assert not replace(observation, close_succeeded=False).tx_safe

    device.capabilities.supports_continuity_sequence = False
    with pytest.raises(AssertionError, match="counter-authoritative metadata"):
        _opened_host_iio_safety_evidence(
            device,
            radio_id=radio_id,
            serial=serial,
            uri=uri,
        )
    device.capabilities.supports_continuity_sequence = True
    device.diagnostic_facts = lambda: {"buffer_metadata_abi": 2}
    with pytest.raises(AssertionError, match="metadata ABI 1"):
        _opened_host_iio_safety_evidence(
            device,
            radio_id=radio_id,
            serial=serial,
            uri=uri,
        )


def test_release_iio_preflight_precedes_import_and_fails_closed() -> None:
    verification = SimpleNamespace(metadata_abi=1)
    module = SimpleNamespace(__file__="/release/iio.py")
    events: list[str] = []

    def verifier(*, expected_abi: int) -> Any:
        events.append(f"verify:{expected_abi}")
        return verification

    def importer(name: str) -> Any:
        events.append(f"import:{name}")
        return module

    assert _load_release_iio(verifier=verifier, importer=importer) == (
        verification,
        module,
    )
    assert events == ["verify:1", "import:iio"]

    events.clear()

    def failing_verifier(*, expected_abi: int) -> Any:
        events.append(f"verify:{expected_abi}")
        raise RuntimeError("release runtime rejected")

    with pytest.raises(RuntimeError, match="release runtime rejected"):
        _load_release_iio(verifier=failing_verifier, importer=importer)
    assert events == ["verify:1"]


def test_production_radio_owners_must_be_loaded_inactive_and_dead() -> None:
    output = "\n\n".join(
        "\n".join(
            (
                f"Id={unit}",
                "LoadState=loaded",
                "ActiveState=inactive",
                "SubState=dead",
            )
        )
        for unit in _PRODUCTION_RADIO_OWNER_UNITS
    )
    calls: list[list[str]] = []

    def runner(arguments: list[str]) -> str:
        calls.append(arguments)
        return output

    _attest_production_radio_owners_quiescent(runner=runner)
    assert calls == [
        [
            "systemctl",
            "show",
            "--no-pager",
            "--property=Id",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            *_PRODUCTION_RADIO_OWNER_UNITS,
        ]
    ]

    for original, replacement in (
        ("LoadState=loaded", "LoadState=not-found"),
        ("ActiveState=inactive", "ActiveState=active"),
        ("ActiveState=inactive", "ActiveState=failed"),
        ("SubState=dead", "SubState=running"),
        ("SubState=dead", "SubState=failed"),
    ):
        tampered = output.replace(original, replacement, 1)

        def tampered_runner(_arguments: list[str], payload: str = tampered) -> str:
            return payload

        with pytest.raises(AssertionError, match="not loaded, inactive, and dead"):
            _attest_production_radio_owners_quiescent(runner=tampered_runner)


def test_campaign_maintenance_claim_binds_four_radios_and_rechecks_pause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[Any] = []

    class FakeLease:
        def __init__(self, radio_ids: tuple[str, ...], task_id: str) -> None:
            self.radio_ids = radio_ids
            self.task_id = task_id
            self.task_kind = CaptureTaskKind.QUALIFICATION
            self.released = False

        def release(self) -> None:
            self.released = True

    class FakeAuthority:
        def __init__(self, root: Path, resources: tuple[RadioResource, ...]) -> None:
            self.root = root
            self.resources = resources
            self.generation = 7
            self.claim_arguments: tuple[tuple[str, ...], str, int] | None = None
            instances.append(self)

        def snapshot(self) -> Any:
            return SimpleNamespace(
                generation=self.generation,
                desired_state=CaptureDesiredState.PAUSED,
                observed_state=CaptureObservedState.PAUSED,
            )

        def claim_paused_maintenance(
            self,
            radio_ids: tuple[str, ...],
            *,
            task_id: str,
            expected_generation: int,
        ) -> FakeLease:
            self.claim_arguments = (radio_ids, task_id, expected_generation)
            return FakeLease(radio_ids, task_id)

    function = _claim_paused_campaign_authority
    monkeypatch.setitem(function.__globals__, "LocalCaptureAuthority", FakeAuthority)
    config = _HardwareConfig(
        hosts=("192.168.1.20", "192.168.1.21"),
        serials=("production-a", "production-b"),
        usb_control_serials=_USB_CONTROL_SERIALS,
        output_root=tmp_path,
        trial_count=_REQUIRED_TRIAL_COUNT,
        leo_revision="a" * 40,
        ppu_revision="b" * 40,
        libiio_version="test",
        libiio_library_path=tmp_path / "libiio.so",
        libiio_library_sha256="sha256:" + "c" * 64,
        python_iio_sha256="sha256:" + "d" * 64,
        network_interface="eth-test",
        network_source_address="192.168.1.142",
    )

    claim = _claim_paused_campaign_authority(config, task_id="campaign-1")
    authority = instances[-1]
    assert authority.root == _CAPTURE_AUTHORITY_ROOT
    assert tuple(
        (resource.radio_id, resource.serial, resource.endpoint) for resource in authority.resources
    ) == (
        (_RADIO_IDS[0], config.serials[0], "ip:192.168.1.20"),
        (_RADIO_IDS[1], config.serials[1], "ip:192.168.1.21"),
        (_USB_CONTROL_RADIO_IDS[0], _USB_CONTROL_SERIALS[0], "usb:"),
        (_USB_CONTROL_RADIO_IDS[1], _USB_CONTROL_SERIALS[1], "usb:"),
    )
    assert authority.claim_arguments == (
        (*_RADIO_IDS, *_USB_CONTROL_RADIO_IDS),
        "campaign-1",
        7,
    )
    claim.verify_and_release()
    assert claim.lease.released

    changed = _claim_paused_campaign_authority(config, task_id="campaign-2")
    instances[-1].generation += 1
    with pytest.raises(AssertionError, match="changed or resumed"):
        changed.verify_and_release()
    assert changed.lease.released


def test_radio_safety_restore_attempts_b_after_a_constructor_failure(
    tmp_path: Path,
) -> None:
    config = _unit_hardware_config(tmp_path)
    snapshots = tuple(
        _RadioSafetyContext(
            radio_id=radio_id,
            serial=serial,
            host=host,
            original_settings=_metadata_settings().model_copy(
                update={"center_frequency_hz": 1_700_000_000 + index}
            ),
            pre_safety=_HostRadioSafetyObservation(
                identity={"radio_id": radio_id, "serial": serial, "uri": f"ip:{host}"},
                diagnostics={"buffer_metadata_abi": 1},
                capabilities={
                    "supports_device_sample_counter": True,
                    "supports_continuity_sequence": True,
                },
                open_succeeded=True,
                close_succeeded=True,
            ),
            pre_evidence_path=tmp_path / f"{radio_id}-pre.json",
            pre_evidence_sha256="sha256:" + f"{index + 1:x}" * 64,
        )
        for index, (radio_id, serial, host) in enumerate(
            zip(
                _RADIO_IDS,
                config.serials,
                config.hosts,
                strict=True,
            )
        )
    )
    assert len(snapshots) == 2
    events: list[str] = []

    class FakeDevice:
        def __init__(self, radio_id: str, serial: str, uri: str) -> None:
            self.radio_id = radio_id
            self.identity = SimpleNamespace(
                radio_id=radio_id,
                serial=serial,
                uri=uri,
                transport=SimpleNamespace(value="iio_ip"),
                model="Pluto+",
                firmware_version="v0.41-test",
            )
            self.capabilities = SimpleNamespace(
                supports_device_sample_counter=True,
                supports_continuity_sequence=True,
            )

        def open(self) -> None:
            events.append(f"open:{self.radio_id}")

        def diagnostic_facts(self) -> dict[str, Any]:
            return {"buffer_metadata_abi": 1}

        def apply_settings(self, settings: Any) -> Any:
            events.append(f"apply:{self.radio_id}")
            return settings

        def read_settings(self) -> Any:
            events.append(f"read:{self.radio_id}")
            return snapshots[1].original_settings

        def close(self) -> None:
            events.append(f"close:{self.radio_id}")
            raise RuntimeError("B close failed")

    def device_factory(
        uri: str,
        *,
        radio_id: str,
        serial: str,
        **_kwargs: Any,
    ) -> FakeDevice:
        events.append(f"construct:{radio_id}")
        if radio_id == _RADIO_IDS[0]:
            raise RuntimeError("A constructor failed")
        return FakeDevice(radio_id, serial, uri)

    with pytest.raises(AssertionError) as error:
        _restore_radio_safety(
            config,
            (snapshots[0], snapshots[1]),
            evidence_root=tmp_path,
            device_factory=device_factory,
        )
    assert "radio_pluto_5d4d RX restore raised RuntimeError: A constructor failed" in str(
        error.value
    )
    assert "radio_pluto_19f2 restore close raised RuntimeError: B close failed" in str(error.value)
    assert events == [
        "construct:radio_pluto_5d4d",
        "construct:radio_pluto_19f2",
        "open:radio_pluto_19f2",
        "apply:radio_pluto_19f2",
        "read:radio_pluto_19f2",
        "close:radio_pluto_19f2",
    ]
    for radio_id in _RADIO_IDS:
        evidence_path = _safety_evidence_path(tmp_path, radio_id, "restoration")
        assert evidence_path.is_file()
        assert json.loads(evidence_path.read_text(encoding="utf-8"))["passed"] is False


def test_radio_safety_snapshot_rejects_unstable_round_trip_before_rf(
    tmp_path: Path,
) -> None:
    config = _unit_hardware_config(tmp_path)
    original = _metadata_settings().model_copy(update={"center_frequency_hz": 1_700_000_000})
    events: list[str] = []

    def device_factory(
        uri: str,
        *,
        radio_id: str,
        serial: str,
        **_kwargs: Any,
    ) -> _TestRadioSafetyDevice:
        is_a = radio_id == _RADIO_IDS[0]
        return _TestRadioSafetyDevice(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            initial_settings=original,
            apply_updates={"center_frequency_hz": 1_700_000_004} if is_a else None,
            independent_updates=None if is_a else {"center_frequency_hz": 1_700_000_004},
            events=events,
        )

    rf_events: list[str] = []
    with pytest.raises(AssertionError, match="RX snapshot was not round-trip stable"):
        _snapshot_radio_safety(
            config,
            evidence_root=tmp_path,
            device_factory=device_factory,
        )
        rf_events.append("capture-started")

    assert rf_events == []
    assert events == [
        "open:radio_pluto_5d4d",
        "read:radio_pluto_5d4d",
        "apply:radio_pluto_5d4d",
        "read:radio_pluto_5d4d",
        "close:radio_pluto_5d4d",
        "open:radio_pluto_19f2",
        "read:radio_pluto_19f2",
        "apply:radio_pluto_19f2",
        "read:radio_pluto_19f2",
        "close:radio_pluto_19f2",
    ]
    for index, radio_id in enumerate(_RADIO_IDS):
        evidence = json.loads(
            _safety_evidence_path(tmp_path, radio_id, "preflight").read_text(encoding="utf-8")
        )
        assert evidence["passed"] is False
        assert evidence["settings_round_trip_stable"] is False
        assert evidence["settings_field_deltas"] == {
            "center_frequency_hz": {
                "snapshot": 1_700_000_000,
                "apply_readback": 1_700_000_004 if index == 0 else 1_700_000_000,
                "independent_readback": 1_700_000_000 if index == 0 else 1_700_000_004,
            }
        }


def test_radio_safety_snapshot_records_close_failure_before_rejecting(
    tmp_path: Path,
) -> None:
    config = _unit_hardware_config(tmp_path)
    original = _metadata_settings()

    def device_factory(
        uri: str,
        *,
        radio_id: str,
        serial: str,
        **_kwargs: Any,
    ) -> _TestRadioSafetyDevice:
        return _TestRadioSafetyDevice(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            initial_settings=original,
            close_error="synthetic preflight close failure" if radio_id == _RADIO_IDS[0] else None,
        )

    with pytest.raises(AssertionError, match="snapshot close raised RuntimeError"):
        _snapshot_radio_safety(
            config,
            evidence_root=tmp_path,
            device_factory=device_factory,
        )

    failed = json.loads(
        _safety_evidence_path(tmp_path, _RADIO_IDS[0], "preflight").read_text(encoding="utf-8")
    )
    passed = json.loads(
        _safety_evidence_path(tmp_path, _RADIO_IDS[1], "preflight").read_text(encoding="utf-8")
    )
    assert failed["settings_field_deltas"] == {}
    assert failed["host_iio_safety"]["close_succeeded"] is False
    assert failed["passed"] is False
    assert passed["passed"] is True


def test_radio_safety_restore_writes_exact_mismatch_evidence_before_rejecting(
    tmp_path: Path,
) -> None:
    config = _unit_hardware_config(tmp_path)
    original = _metadata_settings().model_copy(update={"center_frequency_hz": 1_700_000_000})

    def stable_factory(
        uri: str,
        *,
        radio_id: str,
        serial: str,
        **_kwargs: Any,
    ) -> _TestRadioSafetyDevice:
        return _TestRadioSafetyDevice(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            initial_settings=original,
        )

    snapshots = _snapshot_radio_safety(
        config,
        evidence_root=tmp_path,
        device_factory=stable_factory,
    )

    def mismatch_factory(
        uri: str,
        *,
        radio_id: str,
        serial: str,
        **_kwargs: Any,
    ) -> _TestRadioSafetyDevice:
        return _TestRadioSafetyDevice(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            initial_settings=original,
            independent_updates=(
                {"center_frequency_hz": 1_700_000_004} if radio_id == _RADIO_IDS[0] else None
            ),
        )

    with pytest.raises(AssertionError, match="RX settings did not restore exactly"):
        _restore_radio_safety(
            config,
            snapshots,
            evidence_root=tmp_path,
            device_factory=mismatch_factory,
        )

    failed = json.loads(
        _safety_evidence_path(tmp_path, _RADIO_IDS[0], "restoration").read_text(encoding="utf-8")
    )
    passed = json.loads(
        _safety_evidence_path(tmp_path, _RADIO_IDS[1], "restoration").read_text(encoding="utf-8")
    )
    assert failed["expected_rx_settings"]["center_frequency_hz"] == 1_700_000_000
    assert failed["apply_readback"]["center_frequency_hz"] == 1_700_000_000
    assert failed["independent_readback"]["center_frequency_hz"] == 1_700_000_004
    assert failed["settings_field_deltas"] == {
        "center_frequency_hz": {
            "snapshot": 1_700_000_000,
            "apply_readback": 1_700_000_000,
            "independent_readback": 1_700_000_004,
        }
    }
    assert failed["passed"] is False
    assert passed["settings_field_deltas"] == {}
    assert passed["passed"] is True


@pytest.mark.parametrize("failure_mode", (None, "capture", "deadline", "restore"))
def test_direct_usb_capture_always_restores_rx_settings(
    tmp_path: Path,
    failure_mode: str | None,
) -> None:
    radio_id = _USB_CONTROL_RADIO_IDS[0]
    serial = _USB_CONTROL_SERIALS[0]
    original_settings = _metadata_settings().model_copy(
        update={"sample_rate_hz": 2_500_000, "bandwidth_hz": 1_500_000}
    )
    device = _TestMetadataDevice(
        radio_id=radio_id,
        serial=serial,
        original_settings=original_settings,
        failure_mode=failure_mode,
    )
    deadline = time.monotonic() - 1 if failure_mode == "deadline" else time.monotonic() + 30

    def run() -> _MetadataCaptureResult:
        return _run_metadata_capture(
            uri="usb:",
            serial=serial,
            radio_id=radio_id,
            refills=1,
            campaign_deadline=deadline,
            restoration_evidence_root=tmp_path,
            device_factory=lambda *_args, **_kwargs: device,
        )

    if failure_mode == "capture":
        with pytest.raises(TimeoutError, match="synthetic metadata timeout"):
            run()
    elif failure_mode == "deadline":
        with pytest.raises(AssertionError, match="authorized RF budget"):
            run()
    elif failure_mode == "restore":
        with pytest.raises(AssertionError, match="RX cleanup was not exact"):
            run()
    else:
        result = run()
        assert result.rx_settings_restored is True
        assert result.pre_settings_evidence_sha256 == _file_sha256(
            tmp_path / f"{radio_id}-usb-rx-settings-pre.json"
        )
        assert result.post_settings_evidence_sha256 == _file_sha256(
            tmp_path / f"{radio_id}-usb-rx-settings-post.json"
        )

    if failure_mode == "deadline":
        assert device.begin_calls == 0
        assert device.capture is None
    else:
        assert device.begin_calls == 1
        assert device.capture is not None and device.capture.closed
    assert device.closed
    assert device.read_settings_calls >= 2
    post = json.loads(
        (tmp_path / f"{radio_id}-usb-rx-settings-post.json").read_text(encoding="utf-8")
    )
    if failure_mode == "restore":
        assert device.current_settings != original_settings
        assert post["rx_settings_restored"] is False
        assert post["cleanup_errors"]
    else:
        assert device.current_settings == original_settings
        assert post["rx_settings_restored"] is True
        assert post["cleanup_errors"] == []


def test_simultaneous_usb_deadline_reserves_barrier_wait_before_beginning(
    tmp_path: Path,
) -> None:
    radio_id = _USB_CONTROL_RADIO_IDS[0]
    serial = _USB_CONTROL_SERIALS[0]
    original_settings = _metadata_settings().model_copy(
        update={"sample_rate_hz": 2_500_000, "bandwidth_hz": 1_500_000}
    )
    device = _TestMetadataDevice(
        radio_id=radio_id,
        serial=serial,
        original_settings=original_settings,
    )

    with pytest.raises(AssertionError, match=r"need 35\.000s"):
        _run_metadata_capture(
            uri="usb:",
            serial=serial,
            radio_id=radio_id,
            refills=1,
            campaign_deadline=time.monotonic() + 30,
            barrier=Barrier(2),
            restoration_evidence_root=tmp_path,
            device_factory=lambda *_args, **_kwargs: device,
        )

    assert device.begin_calls == 0
    assert device.capture is None
    assert device.current_settings == original_settings
    assert device.closed


def test_prefix_metrics_accepts_slow_exact_canary_and_rejects_forged_counters() -> None:
    requested_refills = math.ceil(_SAMPLE_RATE_HZ / _REFILL_SAMPLES)
    observed_samples = requested_refills * _REFILL_SAMPLES
    first_sample_sequence = 10_000
    result = _MetadataCaptureResult(
        radio_id=_RADIO_IDS[0],
        serial="production-a",
        uri="ip:192.168.1.20",
        transport="iio_ip",
        model="Pluto+",
        firmware_version="v0.41-test",
        sample_rate_hz=_SAMPLE_RATE_HZ,
        refill_samples=_REFILL_SAMPLES,
        requested_refills=requested_refills,
        observed_refills=requested_refills,
        observed_samples=observed_samples,
        gap_count=0,
        missing_samples=0,
        overflow_count=0,
        first_sample_sequence=first_sample_sequence,
        last_sample_sequence_exclusive=first_sample_sequence + observed_samples,
        capture_started_monotonic_ns=1,
        capture_ended_monotonic_ns=2,
        elapsed_seconds=1.2,
        pre_settings_evidence_sha256=None,
        post_settings_evidence_sha256=None,
        rx_settings_restored=None,
    )
    assert result.observed_samples < math.floor(_SAMPLE_RATE_HZ * result.elapsed_seconds * 0.98)
    metrics = _prefix_metrics(result, requested_sample_count=_SAMPLE_RATE_HZ)
    assert metrics.observed_sample_count == _SAMPLE_RATE_HZ
    assert metrics.device_span_sample_count == _SAMPLE_RATE_HZ

    with pytest.raises(AssertionError, match="raw metadata sequence span"):
        _prefix_metrics(
            replace(
                result,
                last_sample_sequence_exclusive=(result.last_sample_sequence_exclusive + 1),
            ),
            requested_sample_count=_SAMPLE_RATE_HZ,
        )
    with pytest.raises(AssertionError, match="raw metadata sequence span"):
        _prefix_metrics(
            replace(result, observed_samples=result.observed_samples - 1),
            requested_sample_count=_SAMPLE_RATE_HZ,
        )


def test_individual_ip_canaries_opt_out_of_wall_pace_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _HardwareConfig(
        hosts=("192.168.1.20", "192.168.1.21"),
        serials=("production-a", "production-b"),
        usb_control_serials=_USB_CONTROL_SERIALS,
        output_root=tmp_path,
        trial_count=_REQUIRED_TRIAL_COUNT,
        leo_revision="a" * 40,
        ppu_revision="b" * 40,
        libiio_version="test",
        libiio_library_path=tmp_path / "libiio.so",
        libiio_library_sha256="sha256:" + "c" * 64,
        python_iio_sha256="sha256:" + "d" * 64,
        network_interface="eth-test",
        network_source_address="192.168.1.142",
    )
    sentinels = (object(), object())
    calls: list[dict[str, Any]] = []
    metadata_capture = _run_metadata_capture

    def capture(**arguments: Any) -> Any:
        calls.append(arguments)
        return sentinels[_RADIO_IDS.index(arguments["radio_id"])]

    monkeypatch.setitem(
        _run_individual_ip_canaries.__globals__,
        "_run_metadata_capture",
        capture,
    )
    assert _run_individual_ip_canaries(config, time.monotonic() + 30) == sentinels
    assert len(calls) == 2
    assert all(
        call["refills"] == math.ceil(_SAMPLE_RATE_HZ / _REFILL_SAMPLES)
        and call["require_realtime_delivery"] is False
        for call in calls
    )
    defaults = metadata_capture.__kwdefaults__ or {}
    assert defaults["require_realtime_delivery"] is True


def test_delayed_usb_worker_is_primed_before_the_simultaneous_read_barrier(
    tmp_path: Path,
) -> None:
    primed_threads: set[int] = set()
    primed_lock = Lock()

    class PrimedBarrier(Barrier):
        def wait(self, timeout: float | None = None) -> int:
            with primed_lock:
                assert get_ident() in primed_threads
            return super().wait(timeout)

    barrier = PrimedBarrier(2)
    original_settings = _metadata_settings().model_copy(
        update={"sample_rate_hz": 2_500_000, "bandwidth_hz": 1_500_000}
    )
    devices = (
        _TestMetadataDevice(
            radio_id=_USB_CONTROL_RADIO_IDS[0],
            serial=_USB_CONTROL_SERIALS[0],
            original_settings=original_settings,
            read_delay_seconds=0.05,
            primed_threads=primed_threads,
            primed_lock=primed_lock,
        ),
        _TestMetadataDevice(
            radio_id=_USB_CONTROL_RADIO_IDS[1],
            serial=_USB_CONTROL_SERIALS[1],
            original_settings=original_settings,
            begin_delay_seconds=0.1,
            read_delay_seconds=0.05,
            primed_threads=primed_threads,
            primed_lock=primed_lock,
        ),
    )

    def capture(index: int) -> _MetadataCaptureResult:
        device = devices[index]
        return _run_metadata_capture(
            uri="usb:",
            serial=_USB_CONTROL_SERIALS[index],
            radio_id=_USB_CONTROL_RADIO_IDS[index],
            refills=1,
            campaign_deadline=time.monotonic() + 45,
            barrier=barrier,
            restoration_evidence_root=tmp_path,
            device_factory=lambda *_args, **_kwargs: device,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(capture, index) for index in range(2))
        results = tuple(future.result() for future in futures)
    overlap_ns = min(result.capture_ended_monotonic_ns for result in results) - max(
        result.capture_started_monotonic_ns for result in results
    )
    assert overlap_ns > 0
    assert all(result.rx_settings_restored is True for result in results)


def _run_checked(arguments: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise AssertionError(
            f"runtime attestation command failed: {arguments!r}: {error}"
        ) from error
    return result.stdout.strip()


def _attest_production_radio_owners_quiescent(
    *,
    runner: Callable[[list[str]], str] | None = None,
) -> None:
    command_runner = runner or _run_checked
    output = command_runner(
        [
            "systemctl",
            "show",
            "--no-pager",
            "--property=Id",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            *_PRODUCTION_RADIO_OWNER_UNITS,
        ]
    )
    expected_keys = {"Id", "LoadState", "ActiveState", "SubState"}
    records: list[dict[str, str]] = []
    for block in output.split("\n\n"):
        if not block.strip():
            continue
        record: dict[str, str] = {}
        for line in block.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in record:
                raise AssertionError("systemctl returned malformed radio-owner state")
            record[key] = value
        if set(record) != expected_keys:
            raise AssertionError("systemctl omitted an exact radio-owner property")
        records.append(record)
    if tuple(record["Id"] for record in records) != _PRODUCTION_RADIO_OWNER_UNITS:
        raise AssertionError("systemctl did not return the exact ordered radio-owner units")
    expected_state = {
        "LoadState": "loaded",
        "ActiveState": "inactive",
        "SubState": "dead",
    }
    for record in records:
        observed_state = {key: value for key, value in record.items() if key != "Id"}
        if observed_state != expected_state:
            raise AssertionError(
                f"{record['Id']} is not loaded, inactive, and dead: {observed_state!r}"
            )


def _attest_source_tree(repository: Path, config: _HardwareConfig) -> None:
    observed_revision = _run_checked(["git", "rev-parse", "HEAD"], cwd=repository)
    if observed_revision != config.leo_revision:
        raise AssertionError(f"Leo revision is {observed_revision}, expected {config.leo_revision}")
    dirty = _run_checked(["git", "status", "--porcelain"], cwd=repository)
    if dirty:
        raise AssertionError("strict hardware qualification requires a clean Leo source tree")

    with (repository / "pyproject.toml").open("rb") as stream:
        configured_ppu = tomllib.load(stream)["tool"]["uv"]["sources"]["pluto-plus-utils"]["rev"]
    if configured_ppu != config.ppu_revision:
        raise AssertionError(
            f"pyproject pins pluto-plus-utils {configured_ppu}, expected {config.ppu_revision}"
        )
    try:
        package = distribution("pluto-plus-utils")
    except PackageNotFoundError as error:
        raise AssertionError(
            "install the pinned hardware extra with `uv sync --extra hardware`"
        ) from error
    direct_url_text = package.read_text("direct_url.json")
    if direct_url_text is None:
        raise AssertionError("installed pluto-plus-utils lacks VCS provenance")
    direct_url = json.loads(direct_url_text)
    installed_ppu = direct_url.get("vcs_info", {}).get("commit_id")
    if installed_ppu != config.ppu_revision:
        raise AssertionError(
            f"installed pluto-plus-utils is {installed_ppu!r}, expected {config.ppu_revision}"
        )
    from pluto_plus.hardware.iio_metadata import IIO_CONTEXT_TIMEOUT_MS

    if round(_IIO_READ_TIMEOUT_SECONDS * 1000) != IIO_CONTEXT_TIMEOUT_MS:
        raise AssertionError("pinned pluto-plus-utils IIO timeout differs from campaign policy")


def _load_release_iio(
    *,
    verifier: Callable[..., Any] | None = None,
    importer: Callable[[str], Any] | None = None,
) -> tuple[Any, Any]:
    if verifier is None:
        from pluto_plus.hardware.preflight import verify_metadata_runtime

        verifier = verify_metadata_runtime
    verification = verifier(expected_abi=1)
    iio = (importer or importlib.import_module)("iio")
    return verification, iio


def _attest_libiio(config: _HardwareConfig) -> None:
    verification, iio = _load_release_iio()
    runtime_path = Path(sys.prefix) / "share/pluto-plus-utils/metadata-runtime.json"
    try:
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssertionError("release-local metadata runtime receipt is unreadable") from error
    expected_runtime = {
        "schema_version": 1,
        "metadata_abi": 1,
        "libiio_version": config.libiio_version,
        "native_libiio_path": str(config.libiio_library_path),
        "native_libiio_sha256": config.libiio_library_sha256.removeprefix("sha256:"),
        "pylibiio_sha256": config.python_iio_sha256.removeprefix("sha256:"),
    }
    if not isinstance(runtime, dict) or any(
        runtime.get(key) != value for key, value in expected_runtime.items()
    ):
        raise AssertionError("hardware environment differs from release-local metadata runtime")

    expected_verification = {
        "metadata_abi": 1,
        "native_libiio_path": str(config.libiio_library_path),
        "native_libiio_sha256": config.libiio_library_sha256.removeprefix("sha256:"),
        "pylibiio_sha256": config.python_iio_sha256.removeprefix("sha256:"),
        "receipt_path": str(runtime_path.resolve(strict=True)),
    }
    observed_verification = {key: getattr(verification, key, None) for key in expected_verification}
    if observed_verification != expected_verification:
        raise AssertionError(
            "metadata runtime preflight differs from configured qualification runtime"
        )

    python_iio_path = Path(str(getattr(iio, "__file__", ""))).resolve(strict=True)
    verified_python_iio_path = Path(str(verification.pylibiio_path)).resolve(strict=True)
    if python_iio_path != verified_python_iio_path:
        raise AssertionError(
            f"Python iio binding is {python_iio_path}, expected {verified_python_iio_path}"
        )
    observed_python_digest = _file_sha256(python_iio_path)
    if observed_python_digest != config.python_iio_sha256:
        raise AssertionError(
            f"Python iio digest is {observed_python_digest}, expected {config.python_iio_sha256}"
        )

    observed_version = _iio_version(iio)
    if observed_version != config.libiio_version:
        raise AssertionError(
            f"loaded libiio version is {observed_version!r}, expected {config.libiio_version!r}"
        )
    observed_library_digest = _file_sha256(config.libiio_library_path)
    if observed_library_digest != config.libiio_library_sha256:
        raise AssertionError(
            "native libiio digest is "
            f"{observed_library_digest}, expected {config.libiio_library_sha256}"
        )
    loaded_libraries = _loaded_libiio_paths()
    if config.libiio_library_path not in loaded_libraries:
        rendered = ", ".join(str(path) for path in sorted(loaded_libraries)) or "none"
        raise AssertionError(
            f"configured libiio is not the loaded native library; loaded paths: {rendered}"
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def _iio_version(module: Any) -> str:
    observed = getattr(module, "version", None)
    observed = observed() if callable(observed) else observed
    if isinstance(observed, tuple) and len(observed) == 3:
        return f"{observed[0]}.{observed[1]} ({observed[2]})"
    if observed is None:
        raise AssertionError("Python iio binding does not expose the loaded libiio version")
    return str(observed)


def _loaded_libiio_paths() -> set[Path]:
    paths: set[Path] = set()
    maps = Path("/proc/self/maps")
    if not maps.is_file():
        raise AssertionError("cannot attest the loaded libiio without /proc/self/maps")
    for line in maps.read_text(encoding="utf-8").splitlines():
        candidate = line.rsplit(maxsplit=1)[-1]
        if candidate.startswith("/") and "libiio.so" in Path(candidate).name:
            paths.add(Path(candidate).resolve(strict=True))
    return paths


def _attest_native_routes(config: _HardwareConfig) -> None:
    for host in config.hosts:
        payload = json.loads(_run_checked(["ip", "-json", "route", "get", host]))
        if not isinstance(payload, list) or len(payload) != 1:
            raise AssertionError(f"native route lookup for {host} returned an ambiguous result")
        route = payload[0]
        interface = route.get("dev")
        source = route.get("prefsrc", route.get("src"))
        if interface != config.network_interface or source != config.network_source_address:
            raise AssertionError(
                f"route to {host} uses dev={interface!r} src={source!r}; expected "
                f"dev={config.network_interface!r} src={config.network_source_address!r}"
            )


def _opened_host_iio_safety_evidence(
    device: Any,
    *,
    radio_id: str,
    serial: str,
    uri: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bool]]:
    observed_uri, observed_transport, model, firmware_version = _attest_metadata_capture_identity(
        device.identity,
        device.capabilities,
        radio_id=radio_id,
        serial=serial,
        requested_uri=uri,
        expected_transport="iio_ip",
    )
    diagnostic_facts = dict(device.diagnostic_facts())
    if diagnostic_facts.get("buffer_metadata_abi") != 1:
        raise AssertionError(f"{radio_id} safety context did not attest metadata ABI 1")
    selected_diagnostics = {
        key: diagnostic_facts.get(key)
        for key in (
            "serial",
            "firmware_version",
            "context_uri",
            "phy_model",
            "buffer_metadata_abi",
            "buffer_metadata_raw",
            "buffer_metadata_state",
            "tandem_agc",
            "rx_scan_channels",
        )
    }
    identity = {
        "radio_id": radio_id,
        "serial": serial,
        "uri": observed_uri,
        "transport": observed_transport,
        "model": model,
        "firmware_version": firmware_version,
    }
    capabilities = {
        "supports_device_sample_counter": bool(device.capabilities.supports_device_sample_counter),
        "supports_continuity_sequence": bool(device.capabilities.supports_continuity_sequence),
    }
    return identity, selected_diagnostics, capabilities


def _settings_payload(settings: Any | None) -> dict[str, Any] | None:
    if settings is None:
        return None
    payload = settings.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise TypeError("radio settings did not serialize to a JSON object")
    return payload


def _settings_field_deltas(
    expected: dict[str, Any] | None,
    apply_readback: dict[str, Any] | None,
    independent_readback: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    fields = set(expected or ()) | set(apply_readback or ()) | set(independent_readback or ())
    deltas: dict[str, dict[str, Any]] = {}
    for field in sorted(fields):
        snapshot_value = None if expected is None else expected.get(field)
        apply_value = None if apply_readback is None else apply_readback.get(field)
        independent_value = (
            None if independent_readback is None else independent_readback.get(field)
        )
        values_present = (
            expected is not None
            and apply_readback is not None
            and independent_readback is not None
            and field in expected
            and field in apply_readback
            and field in independent_readback
        )
        if not values_present or not (snapshot_value == apply_value == independent_value):
            deltas[field] = {
                "snapshot": snapshot_value,
                "apply_readback": apply_value,
                "independent_readback": independent_value,
            }
    return deltas


def _host_iio_safety_payload(observation: _HostRadioSafetyObservation) -> dict[str, Any]:
    payload = asdict(observation)
    payload["tx_safe"] = observation.tx_safe
    return payload


def _safety_evidence_path(evidence_root: Path, radio_id: str, phase: str) -> Path:
    return evidence_root / f"{radio_id}-host-iio-safety-{phase}-v2.json"


def _snapshot_radio_safety(
    config: _HardwareConfig,
    *,
    evidence_root: Path,
    device_factory: Callable[..., Any] | None = None,
) -> tuple[_RadioSafetyContext, _RadioSafetyContext]:
    if device_factory is None:
        from pluto_plus.hardware.iio import IioRadioDevice

        device_factory = IioRadioDevice

    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    snapshots: list[_RadioSafetyContext] = []
    errors: list[str] = []
    for radio_id, host, serial in zip(_RADIO_IDS, config.hosts, config.serials, strict=True):
        radio_errors: list[str] = []
        device = None
        original_settings = None
        apply_readback = None
        independent_readback = None
        identity: dict[str, Any] | None = None
        diagnostics: dict[str, Any] | None = None
        capabilities: dict[str, bool] | None = None
        open_succeeded = False
        close_succeeded = False
        try:
            device = device_factory(
                f"ip:{host}",
                serial=serial,
                radio_id=radio_id,
                expected_metadata_abi=1,
            )
            device.open()
            open_succeeded = True
            identity, diagnostics, capabilities = _opened_host_iio_safety_evidence(
                device,
                radio_id=radio_id,
                serial=serial,
                uri=f"ip:{host}",
            )
            original_settings = device.read_settings()
            apply_readback = device.apply_settings(original_settings)
            independent_readback = device.read_settings()
        except Exception as error:  # pragma: no cover - real preflight failure
            radio_errors.append(f"{radio_id} RX snapshot raised {type(error).__name__}: {error}")
        finally:
            if device is not None:
                try:
                    device.close()
                    close_succeeded = True
                except Exception as error:  # pragma: no cover - real preflight failure
                    radio_errors.append(
                        f"{radio_id} snapshot close raised {type(error).__name__}: {error}"
                    )

        original_payload = _settings_payload(original_settings)
        apply_payload = _settings_payload(apply_readback)
        independent_payload = _settings_payload(independent_readback)
        settings_stable = (
            original_settings is not None
            and apply_readback == original_settings
            and independent_readback == original_settings
        )
        if original_settings is not None and not settings_stable:
            radio_errors.append(f"{radio_id} RX snapshot was not round-trip stable")
        pre_safety = _HostRadioSafetyObservation(
            identity=identity or {},
            diagnostics=diagnostics or {},
            capabilities=capabilities or {},
            open_succeeded=open_succeeded,
            close_succeeded=close_succeeded,
        )
        passed = (
            not radio_errors
            and settings_stable
            and identity is not None
            and diagnostics is not None
            and capabilities is not None
            and pre_safety.tx_safe
        )
        evidence_path = _safety_evidence_path(evidence_root, radio_id, "preflight")
        evidence_payload = {
            "kind": "host_iio_radio_safety_round_trip_preflight",
            "schema_version": 2,
            "radio_id": radio_id,
            "expected_rx_settings": original_payload,
            "apply_readback": apply_payload,
            "independent_readback": independent_payload,
            "settings_field_deltas": _settings_field_deltas(
                original_payload,
                apply_payload,
                independent_payload,
            ),
            "settings_round_trip_stable": settings_stable,
            "host_iio_safety": _host_iio_safety_payload(pre_safety),
            "errors": radio_errors,
            "passed": passed,
        }
        evidence_sha256: str | None = None
        try:
            _atomic_write_json(evidence_path, evidence_payload)
            evidence_sha256 = _file_sha256(evidence_path)
        except Exception as error:  # pragma: no cover - local evidence failure
            radio_errors.append(
                f"{radio_id} preflight evidence write raised {type(error).__name__}: {error}"
            )
        errors.extend(radio_errors)
        if radio_errors and evidence_sha256 is not None:
            errors.append(
                f"{radio_id} preflight evidence preserved at {evidence_path} ({evidence_sha256})"
            )
        if passed and evidence_sha256 is not None:
            snapshots.append(
                _RadioSafetyContext(
                    radio_id=radio_id,
                    serial=serial,
                    host=host,
                    original_settings=original_settings,
                    pre_safety=pre_safety,
                    pre_evidence_path=evidence_path,
                    pre_evidence_sha256=evidence_sha256,
                )
            )
    if errors:
        raise AssertionError("; ".join(errors))
    return snapshots[0], snapshots[1]


def _restore_radio_safety(
    config: _HardwareConfig,
    snapshots: tuple[_RadioSafetyContext, _RadioSafetyContext],
    *,
    evidence_root: Path,
    device_factory: Callable[..., Any] | None = None,
) -> tuple[_RadioSafetyResult, _RadioSafetyResult]:
    if device_factory is None:
        from pluto_plus.hardware.iio import IioRadioDevice

        device_factory = IioRadioDevice
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    restored: list[_RadioSafetyResult] = []
    errors: list[str] = []
    for snapshot in snapshots:
        radio_errors: list[str] = []
        apply_readback = None
        restored_settings = None
        settings_restored = False
        identity: dict[str, Any] | None = None
        diagnostics: dict[str, Any] | None = None
        capabilities: dict[str, bool] | None = None
        open_succeeded = False
        close_succeeded = False
        device = None
        try:
            device = device_factory(
                f"ip:{snapshot.host}",
                serial=snapshot.serial,
                radio_id=snapshot.radio_id,
                expected_metadata_abi=1,
            )
            device.open()
            open_succeeded = True
            identity, diagnostics, capabilities = _opened_host_iio_safety_evidence(
                device,
                radio_id=snapshot.radio_id,
                serial=snapshot.serial,
                uri=f"ip:{snapshot.host}",
            )
            apply_readback = device.apply_settings(snapshot.original_settings)
            restored_settings = device.read_settings()
            settings_restored = (
                apply_readback == snapshot.original_settings
                and restored_settings == snapshot.original_settings
            )
            if not settings_restored:
                radio_errors.append(f"{snapshot.radio_id} RX settings did not restore exactly")
        except Exception as error:  # pragma: no cover - real cleanup failure
            radio_errors.append(
                f"{snapshot.radio_id} RX restore raised {type(error).__name__}: {error}"
            )
        finally:
            if device is not None:
                try:
                    device.close()
                    close_succeeded = True
                except Exception as error:  # pragma: no cover - real cleanup failure
                    radio_errors.append(
                        f"{snapshot.radio_id} restore close raised {type(error).__name__}: {error}"
                    )
        post_safety = _HostRadioSafetyObservation(
            identity=identity or {},
            diagnostics=diagnostics or {},
            capabilities=capabilities or {},
            open_succeeded=open_succeeded,
            close_succeeded=close_succeeded,
        )
        expected_payload = _settings_payload(snapshot.original_settings)
        apply_payload = _settings_payload(apply_readback)
        independent_payload = _settings_payload(restored_settings)
        passed = (
            not radio_errors
            and settings_restored
            and identity is not None
            and diagnostics is not None
            and capabilities is not None
            and post_safety.tx_safe
        )
        evidence_path = _safety_evidence_path(
            evidence_root,
            snapshot.radio_id,
            "restoration",
        )
        evidence_payload = {
            "kind": "host_iio_radio_safety_restoration_attempt",
            "schema_version": 2,
            "radio_id": snapshot.radio_id,
            "expected_rx_settings": expected_payload,
            "apply_readback": apply_payload,
            "independent_readback": independent_payload,
            "settings_field_deltas": _settings_field_deltas(
                expected_payload,
                apply_payload,
                independent_payload,
            ),
            "rx_settings_restored": settings_restored,
            "host_iio_safety": _host_iio_safety_payload(post_safety),
            "errors": radio_errors,
            "passed": passed,
        }
        evidence_sha256: str | None = None
        try:
            _atomic_write_json(evidence_path, evidence_payload)
            evidence_sha256 = _file_sha256(evidence_path)
        except Exception as error:  # pragma: no cover - local evidence failure
            radio_errors.append(
                f"{snapshot.radio_id} restoration evidence write raised "
                f"{type(error).__name__}: {error}"
            )
        errors.extend(radio_errors)
        if radio_errors and evidence_sha256 is not None:
            errors.append(
                f"{snapshot.radio_id} restoration evidence preserved at {evidence_path} "
                f"({evidence_sha256})"
            )
        if passed and evidence_sha256 is not None:
            restored.append(
                _RadioSafetyResult(
                    context=snapshot,
                    apply_readback=apply_readback,
                    restored_settings=restored_settings,
                    settings_restored=settings_restored,
                    post_safety=post_safety,
                    post_evidence_path=evidence_path,
                    post_evidence_sha256=evidence_sha256,
                )
            )
    if errors:
        raise AssertionError("; ".join(errors))
    return restored[0], restored[1]


def _metadata_settings() -> Any:
    from pluto_plus.models import GainMode, RadioSettings

    return RadioSettings(
        center_frequency_hz=1_709_687_500,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        bandwidth_hz=_BANDWIDTH_HZ,
        gain_mode=GainMode.MANUAL,
        gain_db=30.0,
        channels=(0, 1),
    )


def _attest_metadata_capture_identity(
    identity: Any,
    capabilities: Any,
    *,
    radio_id: str,
    serial: str,
    requested_uri: str,
    expected_transport: str,
) -> tuple[str, str, str, str]:
    observed_transport = str(getattr(identity.transport, "value", identity.transport))
    observed_uri = str(identity.uri)
    if identity.radio_id != radio_id or identity.serial != serial:
        raise AssertionError(
            f"{radio_id} opened identity {identity.radio_id}/{identity.serial}, expected "
            f"{radio_id}/{serial}"
        )
    if observed_transport != expected_transport:
        raise AssertionError(
            f"{radio_id} opened transport {observed_transport!r}, expected {expected_transport!r}"
        )
    if expected_transport == "iio_usb":
        if not observed_uri.startswith("usb:"):
            raise AssertionError(f"{radio_id} direct-USB identity has URI {observed_uri!r}")
    elif observed_uri != requested_uri:
        raise AssertionError(
            f"{radio_id} opened URI {observed_uri!r}, expected exact {requested_uri!r}"
        )
    model = identity.model
    firmware_version = identity.firmware_version
    if (
        not isinstance(model, str)
        or not model
        or model != model.strip()
        or not isinstance(firmware_version, str)
        or not firmware_version
        or firmware_version != firmware_version.strip()
    ):
        raise AssertionError(f"{radio_id} did not attest model and firmware identity")
    if not (
        capabilities.supports_device_sample_counter and capabilities.supports_continuity_sequence
    ):
        raise AssertionError(f"{radio_id} lacks counter-authoritative metadata")
    return observed_uri, observed_transport, model, firmware_version


def _run_metadata_capture(
    *,
    uri: str,
    serial: str,
    radio_id: str,
    refills: int,
    campaign_deadline: float,
    barrier: Barrier | None = None,
    iio_contexts: dict[str, str] | None = None,
    restoration_evidence_root: Path | None = None,
    device_factory: Callable[..., Any] | None = None,
    require_realtime_delivery: bool = True,
) -> _MetadataCaptureResult:
    if (uri == "usb:") != (restoration_evidence_root is not None):
        raise ValueError("direct-USB metadata capture requires an RX-restoration evidence root")
    if restoration_evidence_root is not None and not restoration_evidence_root.is_dir():
        raise ValueError("RX-restoration evidence root must exist before direct-USB capture")
    if device_factory is None:
        from pluto_plus.hardware.iio import IioRadioDevice

        device_factory = IioRadioDevice
    device = device_factory(
        uri,
        serial=serial,
        radio_id=radio_id,
        expected_metadata_abi=1,
        iio_contexts=iio_contexts,
    )
    capture = None
    original_settings = None
    restored_settings = None
    restore_apply_readback = None
    operation_error: BaseException | None = None
    cleanup_errors: list[str] = []
    restoration_errors: list[str] = []
    blocks: list[Any] = []
    observed_uri: str | None = None
    observed_transport: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    capture_started_monotonic_ns: int | None = None
    capture_ended_monotonic_ns: int | None = None
    pre_settings_evidence_sha256: str | None = None
    post_settings_evidence_sha256: str | None = None
    rx_settings_restored: bool | None = None
    pre_path = (
        None
        if restoration_evidence_root is None
        else restoration_evidence_root / f"{radio_id}-usb-rx-settings-pre.json"
    )
    post_path = (
        None
        if restoration_evidence_root is None
        else restoration_evidence_root / f"{radio_id}-usb-rx-settings-post.json"
    )
    try:
        device.open()
        expected_transport = "iio_usb" if uri == "usb:" else "iio_ip"
        observed_uri, observed_transport, model, firmware_version = (
            _attest_metadata_capture_identity(
                device.identity,
                device.capabilities,
                radio_id=radio_id,
                serial=serial,
                requested_uri=uri,
                expected_transport=expected_transport,
            )
        )
        if pre_path is not None:
            original_settings = device.read_settings()
            _atomic_write_json(
                pre_path,
                {
                    "kind": "usb_control_rx_settings_pre",
                    "schema_version": 2,
                    "radio_id": radio_id,
                    "serial": serial,
                    "uri": observed_uri,
                    "settings": original_settings.model_dump(mode="json"),
                },
            )
            pre_settings_evidence_sha256 = _file_sha256(pre_path)
        applied = device.apply_settings(_metadata_settings())
        if applied != _metadata_settings():
            raise AssertionError(f"{radio_id} metadata control settings did not read back")
        _require_campaign_time(
            campaign_deadline,
            phase=f"{radio_id} metadata capture start",
            minimum_remaining_seconds=(
                _IIO_READ_TIMEOUT_SECONDS
                + _RF_SHUTDOWN_RESERVE_SECONDS
                + (_USB_CAPTURE_BARRIER_TIMEOUT_SECONDS if barrier is not None else 0.0)
            ),
        )
        capture = device.begin_metadata_capture(_REFILL_SAMPLES, kernel_buffers=_KERNEL_BUFFERS)
        if barrier is not None:
            barrier.wait(timeout=_USB_CAPTURE_BARRIER_TIMEOUT_SECONDS)
        capture_started_monotonic_ns = time.monotonic_ns()
        for _ in range(refills):
            _require_campaign_time(
                campaign_deadline,
                phase=f"{radio_id} metadata refill",
                minimum_remaining_seconds=(
                    _IIO_READ_TIMEOUT_SECONDS + _RF_SHUTDOWN_RESERVE_SECONDS
                ),
            )
            blocks.append(capture.read_block())
        capture_ended_monotonic_ns = time.monotonic_ns()
    except BaseException as error:
        operation_error = error
    finally:
        if capture is not None:
            try:
                capture.close()
            except Exception as error:  # pragma: no cover - real cleanup failure
                cleanup_errors.append(
                    f"metadata capture close raised {type(error).__name__}: {error}"
                )
        if original_settings is not None:
            try:
                restore_apply_readback = device.apply_settings(original_settings)
            except Exception as error:  # pragma: no cover - real cleanup failure
                restoration_errors.append(
                    f"RX settings restore raised {type(error).__name__}: {error}"
                )
            try:
                restored_settings = device.read_settings()
            except Exception as error:  # pragma: no cover - real cleanup failure
                restoration_errors.append(
                    f"RX settings readback raised {type(error).__name__}: {error}"
                )
            rx_settings_restored = (
                not restoration_errors
                and restore_apply_readback == original_settings
                and restored_settings == original_settings
            )
            if not rx_settings_restored and not restoration_errors:
                restoration_errors.append("RX settings restoration readback differs from snapshot")
            cleanup_errors.extend(restoration_errors)
        try:
            device.close()
        except Exception as error:  # pragma: no cover - real cleanup failure
            cleanup_errors.append(f"radio close raised {type(error).__name__}: {error}")
        if post_path is not None and original_settings is not None:
            try:
                _atomic_write_json(
                    post_path,
                    {
                        "kind": "usb_control_rx_settings_post",
                        "schema_version": 2,
                        "radio_id": radio_id,
                        "serial": serial,
                        "uri": observed_uri,
                        "settings": (
                            None
                            if restored_settings is None
                            else restored_settings.model_dump(mode="json")
                        ),
                        "rx_settings_restored": rx_settings_restored,
                        "capture_error": (
                            None
                            if operation_error is None
                            else f"{type(operation_error).__name__}: {operation_error}"
                        ),
                        "cleanup_errors": cleanup_errors,
                    },
                )
                post_settings_evidence_sha256 = _file_sha256(post_path)
            except Exception as error:  # pragma: no cover - filesystem evidence failure
                cleanup_errors.append(
                    f"post-restoration evidence write raised {type(error).__name__}: {error}"
                )
    if cleanup_errors:
        detail = "; ".join(cleanup_errors)
        if operation_error is not None:
            raise AssertionError(
                f"{radio_id} capture failed and RX cleanup was not exact: {detail}"
            ) from operation_error
        raise AssertionError(f"{radio_id} RX cleanup was not exact: {detail}")
    if operation_error is not None:
        raise operation_error
    assert observed_uri is not None
    assert observed_transport is not None
    assert model is not None
    assert firmware_version is not None
    assert capture_started_monotonic_ns is not None
    assert capture_ended_monotonic_ns is not None
    first = blocks[0]
    last = blocks[-1]
    missing = tuple(int(block.missing_samples_before) for block in blocks)
    overflows = tuple(bool(block.overflow_observed) for block in blocks)
    result = _MetadataCaptureResult(
        radio_id=radio_id,
        serial=serial,
        uri=observed_uri,
        transport=observed_transport,
        model=model,
        firmware_version=firmware_version,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        refill_samples=_REFILL_SAMPLES,
        requested_refills=refills,
        observed_refills=len(blocks),
        observed_samples=sum(int(block.sample_count) for block in blocks),
        gap_count=sum(value > 0 for value in missing),
        missing_samples=sum(missing),
        overflow_count=sum(overflows),
        first_sample_sequence=int(first.first_sample_sequence),
        last_sample_sequence_exclusive=int(last.last_sample_sequence_exclusive),
        capture_started_monotonic_ns=capture_started_monotonic_ns,
        capture_ended_monotonic_ns=capture_ended_monotonic_ns,
        elapsed_seconds=(capture_ended_monotonic_ns - capture_started_monotonic_ns) / 1e9,
        pre_settings_evidence_sha256=pre_settings_evidence_sha256,
        post_settings_evidence_sha256=post_settings_evidence_sha256,
        rx_settings_restored=rx_settings_restored,
    )
    if not result.passed:
        raise AssertionError(f"{radio_id} metadata control observed loss: {result!r}")
    if require_realtime_delivery:
        minimum_samples = math.floor(_SAMPLE_RATE_HZ * result.elapsed_seconds * 0.98)
        if result.observed_samples < minimum_samples:
            raise AssertionError(f"{radio_id} metadata control did not sustain real-time delivery")
    return result


def _run_individual_ip_canaries(
    config: _HardwareConfig,
    campaign_deadline: float,
) -> tuple[_MetadataCaptureResult, _MetadataCaptureResult]:
    refills = math.ceil(_SAMPLE_RATE_HZ / _REFILL_SAMPLES)
    results = tuple(
        _run_metadata_capture(
            uri=f"ip:{host}",
            serial=serial,
            radio_id=radio_id,
            refills=refills,
            campaign_deadline=campaign_deadline,
            # The immutable canary contract is an exact counter-contiguous
            # one-second sample prefix, not a host wall-clock throughput test.
            # The ten full-recorder trials retain their independent strict
            # continuity, queue, and refill-service gates below.
            require_realtime_delivery=False,
        )
        for radio_id, host, serial in zip(_RADIO_IDS, config.hosts, config.serials, strict=True)
    )
    return results[0], results[1]


def _run_simultaneous_usb_control(
    config: _HardwareConfig,
    campaign_deadline: float,
    evidence_root: Path,
) -> tuple[_MetadataCaptureResult, _MetadataCaptureResult]:
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    iio = importlib.import_module("iio")
    contexts = dict(iio.scan_contexts())
    refills = math.ceil(_REQUESTED_SAMPLE_COUNT / _REFILL_SAMPLES)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="usb-control") as executor:
        futures = tuple(
            executor.submit(
                _run_metadata_capture,
                uri="usb:",
                serial=serial,
                radio_id=radio_id,
                refills=refills,
                campaign_deadline=campaign_deadline,
                barrier=barrier,
                iio_contexts=contexts,
                restoration_evidence_root=evidence_root,
            )
            for radio_id, serial in zip(
                _USB_CONTROL_RADIO_IDS,
                config.usb_control_serials,
                strict=True,
            )
        )
        results = tuple(future.result() for future in futures)
    if (
        tuple(result.radio_id for result in results) != _USB_CONTROL_RADIO_IDS
        or tuple(result.serial for result in results) != config.usb_control_serials
        or any(
            result.transport != "iio_usb" or not result.uri.startswith("usb:") for result in results
        )
    ):
        raise AssertionError("USB control arm did not retain its exact ordered direct-USB pair")
    return results[0], results[1]


def _usb_control_identities(
    results: tuple[_MetadataCaptureResult, _MetadataCaptureResult],
) -> tuple[ContiguousRateUsbRadioIdentityV2, ContiguousRateUsbRadioIdentityV2]:
    if tuple(result.radio_id for result in results) != _USB_CONTROL_RADIO_IDS:
        raise AssertionError("USB control results are not in the fixed logical radio order")
    identities = tuple(
        ContiguousRateUsbRadioIdentityV2(
            radio_id=result.radio_id,
            serial=result.serial,
            uri=result.uri,
            transport="iio_usb",
            model=result.model,
            firmware_version=result.firmware_version,
        )
        for result in results
    )
    return identities[0], identities[1]


def _run_writer_capacity_gate(campaign_root: Path) -> tuple[Any, str]:
    from leo.qualification.acquisition import (
        WriterBenchmarkConfigV1,
        WriterThroughputBenchmark,
    )

    benchmark_root = campaign_root / "writer-capacity"
    receipt_path = benchmark_root / "writer-benchmark-receipt-v1.json"
    receipt = WriterThroughputBenchmark(RecordingStore(benchmark_root / "bulk")).run(
        benchmark_id="rate-3m-writer-capacity-v1",
        receipt_path=receipt_path,
        configuration=WriterBenchmarkConfigV1(
            duration_seconds=3.0,
            minimum_throughput_mb_s=72.0,
            block_uncompressed_bytes=32 * 1024 * 1024,
            receiver_count=2,
            zstd_level=3,
            random_seed=20260825,
        ),
        resume=False,
    )
    os.chmod(receipt_path, 0o440)
    if not receipt.passed or receipt.digest_valid is not True:
        raise AssertionError(
            f"incompressible writer capacity gate failed at {receipt.throughput_mb_s:.3f} MB/s"
        )
    return receipt, _file_sha256(receipt_path)


def _new_sources(config: _HardwareConfig) -> tuple[PlutoIioRadioSource, PlutoIioRadioSource]:
    return (
        PlutoIioRadioSource(
            config.hosts[0],
            expected_serial=config.serials[0],
            radio_id=_RADIO_IDS[0],
        ),
        PlutoIioRadioSource(
            config.hosts[1],
            expected_serial=config.serials[1],
            radio_id=_RADIO_IDS[1],
        ),
    )


def _close_sources(sources: tuple[PlutoIioRadioSource, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    for source in sources:
        try:
            source.close()
        except Exception as error:  # pragma: no cover - exercised only by real hardware
            errors.append(f"{source.identity.radio_id}: {type(error).__name__}: {error}")
    return tuple(errors)


def _preflight_radios(config: _HardwareConfig) -> tuple[RadioIdentityV1, RadioIdentityV1]:
    sources = _new_sources(config)
    identities: list[RadioIdentityV1] = []
    try:
        for source, host, serial in zip(sources, config.hosts, config.serials, strict=True):
            identity = source.open()
            if identity.uri != f"ip:{host}" or identity.serial != serial:
                raise AssertionError(
                    f"opened identity {identity.uri}/{identity.serial} differs from explicit target"
                )
            if identity.firmware_version is None:
                raise AssertionError(f"{identity.radio_id} did not attest firmware identity")
            if not (
                source.capabilities.supports_device_sample_counter
                and source.capabilities.supports_continuity_sequence
            ):
                raise AssertionError(f"{identity.radio_id} lacks counter-authoritative metadata")
            identities.append(identity)
    finally:
        close_errors = _close_sources(sources)
        if close_errors:
            raise AssertionError("radio preflight restoration failed: " + "; ".join(close_errors))
    if len(identities) != 2:
        raise AssertionError("radio preflight did not attest exactly two identities")
    return identities[0], identities[1]


def _capture_plan(repository: Path) -> CapturePlanV2:
    revision = load_profile_revision(
        repository / "profiles" / "hardware-canary-3m-60s-contiguous-v2.yaml"
    )
    assert isinstance(revision, CaptureProfileRevisionV2)
    profile = revision.profile
    assert profile.sample_rate_hz == _SAMPLE_RATE_HZ
    assert profile.bandwidth_hz == _BANDWIDTH_HZ
    assert profile.refill_samples == _REFILL_SAMPLES
    assert profile.kernel_buffers == _KERNEL_BUFFERS
    assert profile.refill_queue_capacity == _QUEUE_CAPACITY
    assert profile.continuity_policy is ContinuityPolicy.REQUIRE_CONTIGUOUS
    plan = compile_capture_plan(
        revision,
        _RADIO_IDS,
        source_type=SourceType.LIVE,
    )
    assert isinstance(plan, CapturePlanV2)
    assert plan.resolved_sample_count == _REQUESTED_SAMPLE_COUNT
    return plan


def _five_m_capture_plan(repository: Path) -> CapturePlanV2:
    revision = load_profile_revision(
        repository / "profiles" / "starlink-ch4-lower-5m-60s-segmented-v2.yaml"
    )
    assert isinstance(revision, CaptureProfileRevisionV2)
    profile = revision.profile
    assert profile.sample_rate_hz == _FIVE_M_SAMPLE_RATE_HZ
    assert profile.bandwidth_hz == _BANDWIDTH_HZ
    assert profile.refill_samples == _REFILL_SAMPLES
    assert profile.kernel_buffers == _KERNEL_BUFFERS
    assert profile.refill_queue_capacity == _QUEUE_CAPACITY
    assert profile.continuity_policy is ContinuityPolicy.ALLOW_SEGMENTS
    assert {"CAPTURE_ONLY", "EXPERIMENTAL"}.issubset(profile.tags)
    plan = compile_capture_plan(revision, _RADIO_IDS, source_type=SourceType.LIVE)
    assert isinstance(plan, CapturePlanV2)
    assert plan.resolved_sample_count == _FIVE_M_REQUESTED_SAMPLE_COUNT
    return plan


def _host_identity() -> HostIdentityV1:
    machine_id_path = Path("/etc/machine-id")
    if not machine_id_path.is_file():
        raise AssertionError("strict hardware qualification requires /etc/machine-id")
    machine_id = machine_id_path.read_text(encoding="utf-8").strip()
    if not machine_id:
        raise AssertionError("/etc/machine-id is empty")
    return HostIdentityV1(
        hostname=socket.gethostname(),
        machine_id=machine_id,
        operating_system=platform.platform(),
    )


def _producer(config: _HardwareConfig) -> ProducerV1:
    return ProducerV1(
        name="leo-acquisition",
        version=version("leo-tracker"),
        source_revision=config.leo_revision,
    )


def _require_exact_raw_sequence_span(result: _MetadataCaptureResult) -> None:
    raw_sequence_span = result.last_sample_sequence_exclusive - result.first_sample_sequence
    counter_accounted_span = result.observed_samples + result.missing_samples
    if raw_sequence_span != counter_accounted_span:
        raise AssertionError(
            f"{result.radio_id} raw metadata sequence span {raw_sequence_span} does not "
            f"equal observed plus missing samples {counter_accounted_span}"
        )


def _prefix_metrics(
    result: _MetadataCaptureResult,
    *,
    requested_sample_count: int,
) -> ContiguousRateRadioMetricsV1:
    _require_exact_raw_sequence_span(result)
    if result.observed_samples < requested_sample_count or not result.passed:
        raise AssertionError(
            f"{result.radio_id} cannot supply a lossless {requested_sample_count}-sample prefix"
        )
    return ContiguousRateRadioMetricsV1(
        radio_id=result.radio_id,
        requested_sample_count=requested_sample_count,
        observed_sample_count=requested_sample_count,
        device_span_sample_count=requested_sample_count,
        observed_gap_count=result.gap_count,
        observed_missing_sample_count=result.missing_samples,
        observed_overflow_count=result.overflow_count,
        enqueue_failure_count=0,
    )


def _build_prerequisites(
    campaign_root: Path,
    *,
    safety: tuple[_RadioSafetyResult, _RadioSafetyResult],
    native_ip: tuple[_MetadataCaptureResult, _MetadataCaptureResult],
    usb: tuple[_MetadataCaptureResult, _MetadataCaptureResult],
    writer_receipt: Any,
    writer_receipt_sha256: str,
) -> ContiguousRatePrerequisitesV2:
    evidence_root = campaign_root / "prerequisites"
    evidence_root.mkdir(mode=0o700, exist_ok=True)

    safety_evidence: list[ContiguousRateRadioSafetyEvidenceV1] = []
    for item in safety:
        context = item.context
        pre_path = _safety_evidence_path(evidence_root, context.radio_id, "preflight")
        post_path = _safety_evidence_path(evidence_root, context.radio_id, "restoration")
        if context.pre_evidence_path != pre_path or item.post_evidence_path != post_path:
            raise AssertionError(f"{context.radio_id} safety evidence escaped campaign root")
        pre_sha256 = _file_sha256(pre_path)
        post_sha256 = _file_sha256(post_path)
        if pre_sha256 != context.pre_evidence_sha256:
            raise AssertionError(f"{context.radio_id} preflight safety evidence changed")
        if post_sha256 != item.post_evidence_sha256:
            raise AssertionError(f"{context.radio_id} restoration safety evidence changed")
        safety_evidence.append(
            ContiguousRateRadioSafetyEvidenceV1(
                radio_id=context.radio_id,
                pre_safety_evidence_sha256=pre_sha256,
                post_safety_evidence_sha256=post_sha256,
                pre_tx_safe=context.pre_safety.tx_safe,
                post_tx_safe=item.post_safety.tx_safe,
                rx_settings_restored=item.settings_restored,
                passed=(
                    context.pre_safety.tx_safe
                    and item.post_safety.tx_safe
                    and item.settings_restored
                ),
            )
        )

    native_evidence: list[ContiguousRateNativeIpCanaryEvidenceV1] = []
    for result in native_ip:
        payload = {
            "kind": "native_ip_counter_canary",
            "schema_version": 1,
            "exact_prefix_sample_count": _SAMPLE_RATE_HZ,
            "raw_capture": asdict(result),
        }
        path = evidence_root / f"{result.radio_id}-native-ip-1s.json"
        _atomic_write_json(path, payload)
        metrics = _prefix_metrics(result, requested_sample_count=_SAMPLE_RATE_HZ)
        native_evidence.append(
            ContiguousRateNativeIpCanaryEvidenceV1(
                sample_rate_hz=_SAMPLE_RATE_HZ,
                bandwidth_hz=_BANDWIDTH_HZ,
                evidence_sha256=_file_sha256(path),
                metrics=metrics,
                passed=metrics.closes_losslessly(_SAMPLE_RATE_HZ),
            )
        )

    usb_radios = _usb_control_identities(usb)
    usb_intervals = tuple(
        ContiguousRateUsbRadioCaptureIntervalV2(
            radio_id=result.radio_id,
            started_monotonic_ns=result.capture_started_monotonic_ns,
            ended_monotonic_ns=result.capture_ended_monotonic_ns,
        )
        for result in usb
    )
    usb_restoration: list[ContiguousRateUsbRadioRestorationEvidenceV2] = []
    for result in usb:
        if (
            result.pre_settings_evidence_sha256 is None
            or result.post_settings_evidence_sha256 is None
            or result.rx_settings_restored is None
        ):
            raise AssertionError(f"{result.radio_id} lacks USB RX-restoration evidence")
        usb_restoration.append(
            ContiguousRateUsbRadioRestorationEvidenceV2(
                radio_id=result.radio_id,
                pre_settings_evidence_sha256=result.pre_settings_evidence_sha256,
                post_settings_evidence_sha256=result.post_settings_evidence_sha256,
                rx_settings_restored=result.rx_settings_restored,
                passed=result.rx_settings_restored,
            )
        )
    usb_payload: dict[str, Any] = {
        "kind": "simultaneous_usb_counter_control",
        "schema_version": 2,
        "exact_prefix_sample_count_per_radio": _REQUESTED_SAMPLE_COUNT,
        "raw_captures": [asdict(item) for item in usb],
        "radios": [radio.model_dump(mode="json") for radio in usb_radios],
        "capture_intervals": [item.model_dump(mode="json") for item in usb_intervals],
        "radio_restoration": [item.model_dump(mode="json") for item in usb_restoration],
    }
    usb_path = evidence_root / "simultaneous-usb-60s.json"
    _atomic_write_json(usb_path, usb_payload)
    usb_metrics = tuple(
        _prefix_metrics(result, requested_sample_count=_REQUESTED_SAMPLE_COUNT) for result in usb
    )
    elapsed_ns = max(1, round(writer_receipt.elapsed_seconds * 1_000_000_000))
    sustained_bytes_per_second = writer_receipt.uncompressed_bytes * 1_000_000_000 // elapsed_ns
    usb_overlap_ns = min(item.ended_monotonic_ns for item in usb_intervals) - max(
        item.started_monotonic_ns for item in usb_intervals
    )
    usb_passed = (
        all(metrics.closes_losslessly(_REQUESTED_SAMPLE_COUNT) for metrics in usb_metrics)
        and usb_overlap_ns * 100 >= 60_000_000_000 * 99
        and all(item.passed for item in usb_restoration)
    )
    return ContiguousRatePrerequisitesV2(
        radio_safety=(safety_evidence[0], safety_evidence[1]),
        native_ip_canaries=(native_evidence[0], native_evidence[1]),
        usb_control_arm=ContiguousRateUsbControlArmEvidenceV2(
            duration_ns=60_000_000_000,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            bandwidth_hz=_BANDWIDTH_HZ,
            evidence_sha256=_file_sha256(usb_path),
            minimum_overlap_fraction=0.99,
            radios=usb_radios,
            capture_intervals=(usb_intervals[0], usb_intervals[1]),
            radio_restoration=(usb_restoration[0], usb_restoration[1]),
            radio_metrics=(usb_metrics[0], usb_metrics[1]),
            passed=usb_passed,
        ),
        writer_benchmark=ContiguousRateWriterBenchmarkEvidenceV1(
            evidence_sha256=writer_receipt_sha256,
            uncompressed_bytes_written=writer_receipt.uncompressed_bytes,
            elapsed_ns=elapsed_ns,
            sustained_bytes_per_second=sustained_bytes_per_second,
            passed=sustained_bytes_per_second >= 72_000_000,
        ),
    )


def _target(
    config: _HardwareConfig,
    plan: CapturePlanV2,
    radios: tuple[RadioIdentityV1, RadioIdentityV1],
    host: HostIdentityV1,
    producer: ProducerV1,
    prerequisites: ContiguousRatePrerequisitesV2,
) -> ContiguousRateQualificationTargetV2:
    return ContiguousRateQualificationTargetV2(
        qualification_id=f"native-ip-3m-{config.leo_revision[:12]}",
        profile_revision_digest=plan.profile_revision.revision_digest,
        capture_plan_digest=plan.plan_digest,
        sample_rate_hz=_SAMPLE_RATE_HZ,
        bandwidth_hz=_BANDWIDTH_HZ,
        requested_sample_count=_REQUESTED_SAMPLE_COUNT,
        expected_radios=radios,
        expected_host=host,
        expected_producer=producer,
        pluto_plus_utils_revision=config.ppu_revision,
        libiio_version=config.libiio_version,
        libiio_library_sha256=config.libiio_library_sha256,
        python_iio_sha256=config.python_iio_sha256,
        native_network_interface=config.network_interface,
        native_source_address=config.network_source_address,
        prerequisites=prerequisites,
        policy=ContiguousRateQualificationPolicyV1(
            required_trial_count=config.trial_count,
            maximum_refill_service_interval_ns=_MAXIMUM_SERVICE_INTERVAL_NS,
            required_tags=("QUALIFICATION",),
        ),
    )


def _atomic_write_receipt(
    path: Path,
    receipt: ContiguousRateQualificationReceiptV2,
) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{uuid4().hex}.partial")
    payload = receipt.model_dump_json(indent=2).encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o440)
        os.link(temporary, path)
        temporary.unlink()
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{uuid4().hex}.partial")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o440)
        os.link(temporary, path)
        temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def _capture_with_campaign_deadline(
    coordinator: AcquisitionCoordinator,
    plan: CapturePlanV2,
    sources: tuple[PlutoIioRadioSource, PlutoIioRadioSource],
    *,
    session_id: str,
    campaign_deadline: float,
) -> Any:
    expected_seconds = plan.resolved_sample_count / plan.profile_revision.profile.sample_rate_hz
    _require_campaign_time(
        campaign_deadline,
        phase=session_id,
        minimum_remaining_seconds=expected_seconds + _RF_SHUTDOWN_RESERVE_SECONDS,
    )
    cancel = Event()
    cancel_after = max(
        0.0,
        campaign_deadline - time.monotonic() - _RF_SHUTDOWN_RESERVE_SECONDS,
    )
    deadline_timer = Timer(cancel_after, cancel.set)
    deadline_timer.daemon = True
    deadline_timer.start()
    try:
        return coordinator.capture_once(
            plan,
            dict(zip(_RADIO_IDS, sources, strict=True)),
            session_id=session_id,
            cancel=cancel,
        )
    finally:
        deadline_timer.cancel()
        deadline_timer.join(timeout=1)


def _write_5m_failed_run_evidence(
    campaign_root: Path,
    *,
    config: _HardwareConfig,
    campaign_id: str,
    result: Any,
    safety_snapshots: tuple[_RadioSafetyContext, _RadioSafetyContext],
    errors: tuple[str, ...],
) -> Path:
    if (
        result is None
        or result.bundle is None
        or not isinstance(
            result.manifest,
            RecordingManifestV2,
        )
    ):
        raise AssertionError("cannot seal 5 MS/s failed-run evidence without a V2 manifest")
    streams = [
        {
            "radio_id": stream.radio.radio_id,
            "state": stream.state.value,
            "requested_sample_count": stream.requested_sample_count,
            "captured_sample_count": stream.captured_sample_count,
            "continuity": (
                None if stream.continuity is None else stream.continuity.model_dump(mode="json")
            ),
        }
        for stream in result.manifest.streams
    ]
    safety_evidence = []
    for snapshot in safety_snapshots:
        post_path = _safety_evidence_path(
            campaign_root / "prerequisites",
            snapshot.radio_id,
            "restoration",
        )
        safety_evidence.append(
            {
                "radio_id": snapshot.radio_id,
                "pre_evidence_path": str(snapshot.pre_evidence_path),
                "pre_evidence_sha256": snapshot.pre_evidence_sha256,
                "post_evidence_path": str(post_path),
                "post_evidence_sha256": _file_sha256(post_path) if post_path.is_file() else None,
            }
        )
    payload = {
        "kind": "segmented_rate_5m_failed_run_evidence",
        "schema_version": 2,
        "leo_revision": config.leo_revision,
        "session_id": campaign_id,
        "manifest_uri": result.bundle.uri.rstrip("/") + "/manifest.json",
        "manifest_sha256": result.bundle.manifest_sha256,
        "state": result.manifest.state.value,
        "streams": streams,
        "radio_safety_evidence": safety_evidence,
        "errors": errors,
        "passed": False,
    }
    path = campaign_root / "segmented-rate-5m-failed-run-evidence-v2.json"
    _atomic_write_json(path, payload)
    return path


@pytest.mark.hardware
def test_two_native_ip_plutos_sustain_strict_contiguous_3m_full_recorder(
    request: pytest.FixtureRequest,
    record_property: Any,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = _hardware_config(repository)
    _attest_production_radio_owners_quiescent()
    _attest_source_tree(repository, config)
    _attest_libiio(config)
    _attest_native_routes(config)

    campaign_id = f"rate-3m-{time.time_ns()}-{uuid4().hex[:8]}"
    campaigns_root = config.output_root / "campaigns"
    campaigns_root.mkdir(mode=0o750, parents=True, exist_ok=True)
    campaign_root = campaigns_root / campaign_id
    campaign_root.mkdir(mode=0o700)
    safety_evidence_root = campaign_root / "prerequisites"
    raw_campaign_bytes = _REQUESTED_SAMPLE_COUNT * 2 * 4 * 2 * config.trial_count
    required_free_bytes = raw_campaign_bytes + 1 * 1024 * 1024 * 1024
    available_free_bytes = shutil.disk_usage(campaign_root).free
    if available_free_bytes < required_free_bytes:
        pytest.fail(
            f"insufficient campaign storage: need {required_free_bytes}, "
            f"have {available_free_bytes}; preserved {campaign_root}",
            pytrace=False,
        )

    maintenance_claim = _claim_paused_campaign_authority(config, task_id=campaign_id)
    request.addfinalizer(maintenance_claim.verify_and_release)
    plan = _capture_plan(repository)
    host = _host_identity()
    producer = _producer(config)
    writer_receipt, writer_receipt_sha256 = _run_writer_capacity_gate(campaign_root)
    campaign_deadline = _campaign_deadline()
    safety_snapshots = _snapshot_radio_safety(
        config,
        evidence_root=safety_evidence_root,
    )
    evidence: list[ContiguousRateTrialEvidenceV1] = []
    campaign_errors: list[str] = []
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    safety_results: tuple[_RadioSafetyResult, _RadioSafetyResult] | None = None
    try:
        radios = _preflight_radios(config)
        native_ip_canaries = _run_individual_ip_canaries(config, campaign_deadline)
        usb_control = _run_simultaneous_usb_control(
            config,
            campaign_deadline,
            safety_evidence_root,
        )
        store = RecordingStore(campaign_root / "bulk")
        coordinator = AcquisitionCoordinator(
            store,
            compression=CompressionSettingsV1(
                policy_id="zstd-128m-v1",
                codec="zstd",
                level=3,
                target_uncompressed_bytes=128 * 1024 * 1024,
            ),
            host=host,
            producer=producer,
        )
        for index in range(1, config.trial_count + 1):
            session_id = f"{campaign_id}-trial-{index:02d}"
            sources = _new_sources(config)
            result = None
            close_errors: tuple[str, ...] = ()
            try:
                try:
                    result = _capture_with_campaign_deadline(
                        coordinator,
                        plan,
                        sources,
                        session_id=session_id,
                        campaign_deadline=campaign_deadline,
                    )
                except Exception as error:  # pragma: no cover - real hardware failure evidence
                    campaign_errors.append(
                        f"{session_id} capture raised: {type(error).__name__}: {error}"
                    )
            finally:
                # Coordinator closes every prepared source. This idempotent final
                # close also covers validation paths that return before preparation.
                close_errors = _close_sources(sources)
            if close_errors:
                campaign_errors.append(session_id + " close failed: " + "; ".join(close_errors))
            if result is None:
                campaign_errors.append(session_id + " returned no capture result")
                continue
            if result.errors:
                campaign_errors.append(session_id + ": " + "; ".join(result.errors))
            if result.bundle is None or not isinstance(result.manifest, RecordingManifestV2):
                campaign_errors.append(session_id + " did not publish a V2 bundle")
                continue
            digest_valid = not result.errors and not close_errors
            try:
                store.verify(result.bundle)
            except Exception as error:  # pragma: no cover - real evidence failure
                digest_valid = False
                campaign_errors.append(
                    f"{session_id} bundle verification failed: {type(error).__name__}: {error}"
                )
            evidence.append(
                ContiguousRateTrialEvidenceV1(
                    trial_id=f"trial-{index:02d}",
                    manifest_sha256=result.bundle.manifest_sha256,
                    digest_valid=digest_valid,
                    manifest=result.manifest,
                )
            )
    except BaseException as error:  # pragma: no cover - real hardware failure path
        operation_error = error
    finally:
        try:
            safety_results = _restore_radio_safety(
                config,
                safety_snapshots,
                evidence_root=safety_evidence_root,
            )
        except BaseException as error:  # pragma: no cover - real hardware cleanup path
            restoration_error = error

    maintenance_claim.verify_and_release()
    if restoration_error is not None:
        raise restoration_error
    if operation_error is not None:
        raise operation_error
    assert safety_results is not None
    prerequisites = _build_prerequisites(
        campaign_root,
        safety=safety_results,
        native_ip=native_ip_canaries,
        usb=usb_control,
        writer_receipt=writer_receipt,
        writer_receipt_sha256=writer_receipt_sha256,
    )
    target = _target(
        config,
        plan,
        radios,
        host,
        producer,
        prerequisites,
    )

    receipt = evaluate_contiguous_rate(
        target,
        tuple(evidence),
        created_utc_ns=time.time_ns(),
    )
    receipt_path = campaign_root / "contiguous-rate-qualification-receipt-v2.json"
    _atomic_write_receipt(receipt_path, receipt)
    record_property("contiguous_rate_qualification_receipt", str(receipt_path))
    print(f"contiguous rate qualification receipt: {receipt_path}")

    failed_checks = tuple(
        f"{check.trial_id}: {'; '.join(check.errors)}"
        for check in receipt.checks
        if not check.passed
    )
    assert not campaign_errors, (
        f"hardware campaign errors; receipt preserved at {receipt_path}: "
        + " | ".join(campaign_errors)
    )
    assert receipt.passed, (
        f"strict 3 MS/s qualification failed; receipt preserved at {receipt_path}: "
        + " | ".join(failed_checks)
    )
    accepted_root = config.output_root / "accepted" / config.leo_revision
    accepted_root.mkdir(mode=0o750, parents=True, exist_ok=False)
    accepted_receipt_path = accepted_root / receipt_path.name
    _atomic_write_receipt(accepted_receipt_path, receipt)
    record_property("accepted_contiguous_rate_qualification_receipt", str(accepted_receipt_path))
    print(f"accepted contiguous rate qualification receipt: {accepted_receipt_path}")


@pytest.mark.hardware
def test_two_native_ip_plutos_truthfully_characterize_segmented_5m_full_recorder(
    request: pytest.FixtureRequest,
    record_property: Any,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = _hardware_config(repository)
    _attest_production_radio_owners_quiescent()
    _attest_source_tree(repository, config)
    _attest_libiio(config)
    _attest_native_routes(config)

    campaign_id = f"rate-5m-{time.time_ns()}-{uuid4().hex[:8]}"
    campaign_root = config.output_root / "campaigns" / campaign_id
    campaign_root.mkdir(mode=0o700, parents=True)
    safety_evidence_root = campaign_root / "prerequisites"
    required_free_bytes = _FIVE_M_REQUESTED_SAMPLE_COUNT * 2 * 4 * 2 + 1024**3
    if shutil.disk_usage(campaign_root).free < required_free_bytes:
        pytest.fail(
            f"insufficient storage for 5 MS/s characterization; preserved {campaign_root}",
            pytrace=False,
        )

    maintenance_claim = _claim_paused_campaign_authority(config, task_id=campaign_id)
    request.addfinalizer(maintenance_claim.verify_and_release)
    plan = _five_m_capture_plan(repository)
    host = _host_identity()
    producer = _producer(config)
    campaign_deadline = _campaign_deadline()
    safety_snapshots = _snapshot_radio_safety(
        config,
        evidence_root=safety_evidence_root,
    )
    sources = _new_sources(config)
    result = None
    close_errors: tuple[str, ...] = ()
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    safety_results: tuple[_RadioSafetyResult, _RadioSafetyResult] | None = None
    store = RecordingStore(campaign_root / "bulk")
    try:
        coordinator = AcquisitionCoordinator(
            store,
            compression=CompressionSettingsV1(
                policy_id="zstd-128m-v1",
                codec="zstd",
                level=3,
                target_uncompressed_bytes=128 * 1024 * 1024,
            ),
            host=host,
            producer=producer,
        )
        result = _capture_with_campaign_deadline(
            coordinator,
            plan,
            sources,
            session_id=campaign_id,
            campaign_deadline=campaign_deadline,
        )
    except BaseException as error:  # pragma: no cover - real hardware failure path
        operation_error = error
    finally:
        close_errors = _close_sources(sources)
        try:
            safety_results = _restore_radio_safety(
                config,
                safety_snapshots,
                evidence_root=safety_evidence_root,
            )
        except BaseException as error:  # pragma: no cover - real hardware cleanup path
            restoration_error = error

    maintenance_claim.verify_and_release()
    run_errors: list[str] = []
    if operation_error is not None:
        run_errors.append(f"capture raised {type(operation_error).__name__}: {operation_error}")
    run_errors.extend(f"source close failed: {error}" for error in close_errors)
    if restoration_error is not None:
        run_errors.append(
            f"restoration raised {type(restoration_error).__name__}: {restoration_error}"
        )
    failure_path: Path | None = None
    if (
        run_errors
        and result is not None
        and result.bundle is not None
        and isinstance(
            result.manifest,
            RecordingManifestV2,
        )
    ):
        failure_path = _write_5m_failed_run_evidence(
            campaign_root,
            config=config,
            campaign_id=campaign_id,
            result=result,
            safety_snapshots=safety_snapshots,
            errors=tuple(run_errors),
        )
        record_property("segmented_rate_5m_failed_run_evidence", str(failure_path))
        print(f"segmented 5 MS/s failed-run evidence: {failure_path}")
    preserved = "" if failure_path is None else f"; evidence preserved at {failure_path}"
    if restoration_error is not None:
        raise AssertionError(f"5 MS/s radio restoration failed{preserved}") from restoration_error
    if operation_error is not None:
        raise AssertionError(f"5 MS/s capture failed{preserved}") from operation_error
    if close_errors:
        raise AssertionError("; ".join(close_errors) + preserved)
    assert safety_results is not None
    assert result is not None
    assert result.bundle is not None
    assert isinstance(result.manifest, RecordingManifestV2)
    manifest = result.manifest
    assert result.bundle.manifest == manifest
    assert manifest.capture_plan == plan
    assert tuple(stream.radio.radio_id for stream in manifest.streams) == _RADIO_IDS
    assert len(manifest.streams) == 2
    verification = store.verify(result.bundle)
    assert verification.session_id == campaign_id
    assert verification.timeline_count == verification.gap_map_count == 2

    stream_facts: list[dict[str, Any]] = []
    for stream in manifest.streams:
        continuity = stream.continuity
        assert isinstance(continuity, ContinuitySummaryV2)
        assert stream.state is not StreamState.FAILED
        assert stream.requested_sample_count == _FIVE_M_REQUESTED_SAMPLE_COUNT
        assert stream.captured_sample_count == continuity.observed_sample_count
        assert continuity.device_span_sample_count == _FIVE_M_REQUESTED_SAMPLE_COUNT
        assert (
            continuity.observed_sample_count + continuity.missing_sample_count
            == _FIVE_M_REQUESTED_SAMPLE_COUNT
        )
        assert sum(chunk.sample_count for chunk in stream.chunks) == stream.captured_sample_count
        assert sum(chunk.uncompressed_bytes for chunk in stream.chunks) == (
            stream.captured_sample_count * 2 * 4
        )
        assert continuity.sample_loss_observable is True
        assert continuity.kernel_buffers == _KERNEL_BUFFERS
        assert continuity.queue_capacity_refills == _QUEUE_CAPACITY
        assert 1 <= continuity.queue_high_water_refills <= _QUEUE_CAPACITY
        assert continuity.metadata_abi_version == 1
        assert continuity.validated_stream_generation
        assert continuity.enqueue_failure_count == 0
        assert continuity.terminal_enqueue_failure is None
        assert continuity.terminal_rejected_gap_count == 0
        assert continuity.terminal_rejected_missing_sample_count == 0
        assert continuity.terminal_rejected_overflow_count == 0
        assert continuity.first_device_sample_counter is not None
        assert continuity.last_device_sample_counter is not None
        terminal_missing = (
            continuity.terminal_gap.in_span_missing_sample_count
            if continuity.terminal_gap is not None
            else 0
        )
        assert (
            continuity.last_device_sample_counter
            - continuity.first_device_sample_counter
            + 1
            + terminal_missing
            == _FIVE_M_REQUESTED_SAMPLE_COUNT
        )

        reader = store.reader(result.bundle, stream.stream_id)
        gap_map = reader.gap_map()
        assert gap_map.timeline_sha256 == stream.timeline_sha256
        assert gap_map.observed_sample_count == continuity.observed_sample_count
        assert gap_map.device_span_sample_count == _FIVE_M_REQUESTED_SAMPLE_COUNT
        assert gap_map.missing_sample_count == continuity.missing_sample_count
        assert gap_map.segment_count == continuity.segment_count
        assert (
            sum(boundary.missing_sample_count for boundary in gap_map.boundaries)
            == continuity.missing_sample_count
        )
        assert (
            sum(boundary.missing_sample_count > 0 for boundary in gap_map.boundaries)
            == continuity.gap_count
        )

        integrity_loss = bool(
            continuity.gap_count
            or continuity.overflow_count
            or continuity.enqueue_failure_count
            or continuity.device_span_sample_count != _FIVE_M_REQUESTED_SAMPLE_COUNT
        )
        assert stream.state is (StreamState.PARTIAL if integrity_loss else StreamState.COMPLETE)
        assert (stream.error is not None) is integrity_loss
        stream_facts.append(
            {
                "radio_id": stream.radio.radio_id,
                "state": stream.state.value,
                "captured_sample_count": stream.captured_sample_count,
                "continuity": continuity.model_dump(mode="json"),
                "gap_map_sha256": stream.gap_map_sha256,
            }
        )

    any_loss = any(stream.state is StreamState.PARTIAL for stream in manifest.streams)
    expected_state = CaptureState.DEGRADED if any_loss else CaptureState.COMMITTED
    expected_grade = (
        SynchronizationGrade.DEGRADED if any_loss else SynchronizationGrade.BEST_EFFORT_OBSERVED
    )
    assert result.state is manifest.state is expected_state
    assert manifest.synchronization.grade is expected_grade
    report_payload = {
        "kind": "segmented_rate_5m_characterization",
        "schema_version": 1,
        "leo_revision": config.leo_revision,
        "manifest_sha256": result.bundle.manifest_sha256,
        "session_id": campaign_id,
        "state": manifest.state.value,
        "streams": stream_facts,
        "radio_safety": [
            {
                "radio_id": item.context.radio_id,
                "settings_restored": item.settings_restored,
                "apply_readback": item.apply_readback.model_dump(mode="json"),
                "independent_readback": item.restored_settings.model_dump(mode="json"),
                "pre_safety_evidence_path": str(item.context.pre_evidence_path),
                "pre_safety_evidence_sha256": item.context.pre_evidence_sha256,
                "post_safety_evidence_path": str(item.post_evidence_path),
                "post_safety_evidence_sha256": item.post_evidence_sha256,
                "pre_host_iio_safety": asdict(item.context.pre_safety),
                "post_host_iio_safety": asdict(item.post_safety),
            }
            for item in safety_results
        ],
    }
    report_path = campaign_root / "segmented-rate-5m-characterization-v1.json"
    _atomic_write_json(report_path, report_payload)
    record_property("segmented_rate_5m_characterization", str(report_path))
    print(f"segmented 5 MS/s characterization: {report_path}")
