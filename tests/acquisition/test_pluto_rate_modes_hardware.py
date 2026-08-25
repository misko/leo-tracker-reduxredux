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
    "LEO_PLUTO_RATE_SSH_PASSWORD",
    "LEO_PLUTO_RATE_RADIO_A_SSH_KNOWN_HOSTS",
    "LEO_PLUTO_RATE_RADIO_B_SSH_KNOWN_HOSTS",
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
    ssh_password: str
    ssh_known_hosts: tuple[Path, Path]


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
    pre_health: Any


@dataclass(frozen=True, slots=True)
class _RadioSafetyResult:
    context: _RadioSafetyContext
    restored_settings: Any
    settings_restored: bool
    post_health: Any


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
    known_hosts_names = (
        "LEO_PLUTO_RATE_RADIO_A_SSH_KNOWN_HOSTS",
        "LEO_PLUTO_RATE_RADIO_B_SSH_KNOWN_HOSTS",
    )
    known_hosts = (
        Path(values[known_hosts_names[0]]),
        Path(values[known_hosts_names[1]]),
    )
    for name, path in zip(
        known_hosts_names,
        known_hosts,
        strict=True,
    ):
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_mode & 0o077
        ):
            pytest.fail(
                f"{name} must be an absolute, private, regular file",
                pytrace=False,
            )
    resolved_known_hosts = (
        known_hosts[0].resolve(strict=True),
        known_hosts[1].resolve(strict=True),
    )
    if resolved_known_hosts[0].samefile(resolved_known_hosts[1]):
        pytest.fail(
            "each radio requires a distinct private SSH known-hosts file",
            pytrace=False,
        )

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
        ssh_password=values["LEO_PLUTO_RATE_SSH_PASSWORD"],
        ssh_known_hosts=resolved_known_hosts,
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
        ssh_password="test",
        ssh_known_hosts=(tmp_path / "known-a", tmp_path / "known-b"),
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
        ssh_password="test",
        ssh_known_hosts=(tmp_path / "known-a", tmp_path / "known-b"),
    )
    snapshots = tuple(
        _RadioSafetyContext(
            radio_id=radio_id,
            serial=serial,
            host=host,
            original_settings=SimpleNamespace(marker=radio_id),
            pre_health=SimpleNamespace(),
        )
        for radio_id, serial, host in zip(
            _RADIO_IDS,
            config.serials,
            config.hosts,
            strict=True,
        )
    )
    assert len(snapshots) == 2
    events: list[str] = []

    class FakeDevice:
        def __init__(self, radio_id: str) -> None:
            self.radio_id = radio_id

        def open(self) -> None:
            events.append(f"open:{self.radio_id}")

        def apply_settings(self, settings: Any) -> Any:
            events.append(f"apply:{self.radio_id}")
            return settings

        def close(self) -> None:
            events.append(f"close:{self.radio_id}")
            raise RuntimeError("B close failed")

    def device_factory(_uri: str, *, radio_id: str, **_kwargs: Any) -> FakeDevice:
        events.append(f"construct:{radio_id}")
        if radio_id == _RADIO_IDS[0]:
            raise RuntimeError("A constructor failed")
        return FakeDevice(radio_id)

    safe_health = SimpleNamespace(
        tx_safe=True,
        active_rx_buffers=0,
        active_tx_buffers=0,
        tandem_state=0,
        fault_flags=0,
        overflow_count=0,
    )

    def health_probe(_config: _HardwareConfig, index: int) -> Any:
        events.append(f"health:{_RADIO_IDS[index]}")
        return SimpleNamespace(ensure_tx_safe=lambda: safe_health)

    with pytest.raises(AssertionError) as error:
        _restore_radio_safety(
            config,
            (snapshots[0], snapshots[1]),
            device_factory=device_factory,
            health_probe=health_probe,
        )
    assert "radio_pluto_5d4d RX restore raised RuntimeError: A constructor failed" in str(
        error.value
    )
    assert "radio_pluto_19f2 restore close raised RuntimeError: B close failed" in str(error.value)
    assert events == [
        "construct:radio_pluto_5d4d",
        "health:radio_pluto_5d4d",
        "construct:radio_pluto_19f2",
        "open:radio_pluto_19f2",
        "apply:radio_pluto_19f2",
        "close:radio_pluto_19f2",
        "health:radio_pluto_19f2",
    ]


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


def test_prefix_metrics_rejects_forged_raw_sequence_span_or_sample_counter() -> None:
    observed_samples = 2 * _REFILL_SAMPLES
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
        requested_refills=2,
        observed_refills=2,
        observed_samples=observed_samples,
        gap_count=0,
        missing_samples=0,
        overflow_count=0,
        first_sample_sequence=first_sample_sequence,
        last_sample_sequence_exclusive=first_sample_sequence + observed_samples,
        capture_started_monotonic_ns=1,
        capture_ended_monotonic_ns=2,
        elapsed_seconds=1e-9,
        pre_settings_evidence_sha256=None,
        post_settings_evidence_sha256=None,
        rx_settings_restored=None,
    )
    metrics = _prefix_metrics(result, requested_sample_count=_REFILL_SAMPLES)
    assert metrics.observed_sample_count == _REFILL_SAMPLES
    assert metrics.device_span_sample_count == _REFILL_SAMPLES

    with pytest.raises(AssertionError, match="raw metadata sequence span"):
        _prefix_metrics(
            replace(
                result,
                last_sample_sequence_exclusive=(result.last_sample_sequence_exclusive + 1),
            ),
            requested_sample_count=_REFILL_SAMPLES,
        )
    with pytest.raises(AssertionError, match="raw metadata sequence span"):
        _prefix_metrics(
            replace(result, observed_samples=result.observed_samples - 1),
            requested_sample_count=_REFILL_SAMPLES,
        )


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


def _health_probe(config: _HardwareConfig, index: int) -> Any:
    from pluto_plus.metadata_soak import SshMetadataHealthProbe
    from pluto_plus.setup_helper import BoundSshTransport

    transport = BoundSshTransport(
        host=config.hosts[index],
        interface=None,
        password=config.ssh_password,
        known_hosts_file=config.ssh_known_hosts[index],
    )
    return SshMetadataHealthProbe(transport, serial=config.serials[index])


def _require_idle_tx_safe(health: Any, *, label: str) -> None:
    if not health.tx_safe:
        raise AssertionError(f"{label} did not read back TX-safe")
    if health.active_rx_buffers != 0 or health.active_tx_buffers != 0:
        raise AssertionError(f"{label} has active RX/TX buffers")
    if health.tandem_state != 0 or health.fault_flags != 0:
        raise AssertionError(f"{label} has a live or faulted tandem owner")
    if health.overflow_count != 0:
        raise AssertionError(f"{label} has a nonzero tandem overflow counter")


def _snapshot_radio_safety(
    config: _HardwareConfig,
) -> tuple[_RadioSafetyContext, _RadioSafetyContext]:
    from pluto_plus.hardware.iio import IioRadioDevice

    snapshots: list[_RadioSafetyContext] = []
    for index, (radio_id, host, serial) in enumerate(
        zip(_RADIO_IDS, config.hosts, config.serials, strict=True)
    ):
        pre_health = _health_probe(config, index).ensure_tx_safe()
        _require_idle_tx_safe(pre_health, label=f"{radio_id} preflight")
        device = IioRadioDevice(
            f"ip:{host}",
            serial=serial,
            radio_id=radio_id,
            expected_metadata_abi=1,
        )
        try:
            device.open()
            identity = device.identity
            if identity.serial != serial or identity.uri != f"ip:{host}":
                raise AssertionError(f"{radio_id} safety snapshot opened the wrong radio")
            original_settings = device.read_settings()
        finally:
            device.close()
        snapshots.append(
            _RadioSafetyContext(
                radio_id=radio_id,
                serial=serial,
                host=host,
                original_settings=original_settings,
                pre_health=pre_health,
            )
        )
    return snapshots[0], snapshots[1]


def _restore_radio_safety(
    config: _HardwareConfig,
    snapshots: tuple[_RadioSafetyContext, _RadioSafetyContext],
    *,
    device_factory: Callable[..., Any] | None = None,
    health_probe: Callable[[_HardwareConfig, int], Any] | None = None,
) -> tuple[_RadioSafetyResult, _RadioSafetyResult]:
    if device_factory is None:
        from pluto_plus.hardware.iio import IioRadioDevice

        device_factory = IioRadioDevice
    probe = health_probe or _health_probe

    restored: list[_RadioSafetyResult] = []
    errors: list[str] = []
    for index, snapshot in enumerate(snapshots):
        restored_settings = None
        settings_restored = False
        device = None
        try:
            device = device_factory(
                f"ip:{snapshot.host}",
                serial=snapshot.serial,
                radio_id=snapshot.radio_id,
                expected_metadata_abi=1,
            )
            device.open()
            restored_settings = device.apply_settings(snapshot.original_settings)
            settings_restored = restored_settings == snapshot.original_settings
            if not settings_restored:
                errors.append(f"{snapshot.radio_id} RX settings did not restore exactly")
        except Exception as error:  # pragma: no cover - real cleanup failure
            errors.append(f"{snapshot.radio_id} RX restore raised {type(error).__name__}: {error}")
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception as error:  # pragma: no cover - real cleanup failure
                    errors.append(
                        f"{snapshot.radio_id} restore close raised {type(error).__name__}: {error}"
                    )
        post_health = None
        try:
            post_health = probe(config, index).ensure_tx_safe()
            _require_idle_tx_safe(post_health, label=f"{snapshot.radio_id} cleanup")
        except Exception as error:  # pragma: no cover - real cleanup failure
            errors.append(
                f"{snapshot.radio_id} TX-safe cleanup raised {type(error).__name__}: {error}"
            )
        if post_health is None:
            continue
        restored.append(
            _RadioSafetyResult(
                context=snapshot,
                restored_settings=restored_settings,
                settings_restored=settings_restored,
                post_health=post_health,
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
        pre_payload = {
            "kind": "radio_safety_preflight",
            "schema_version": 1,
            "radio_id": context.radio_id,
            "settings": context.original_settings.model_dump(mode="json"),
            "health": context.pre_health.model_dump(mode="json"),
        }
        post_payload = {
            "kind": "radio_safety_restoration",
            "schema_version": 1,
            "radio_id": context.radio_id,
            "settings": item.restored_settings.model_dump(mode="json"),
            "health": item.post_health.model_dump(mode="json"),
        }
        pre_path = evidence_root / f"{context.radio_id}-safety-pre.json"
        post_path = evidence_root / f"{context.radio_id}-safety-post.json"
        _atomic_write_json(pre_path, pre_payload)
        _atomic_write_json(post_path, post_payload)
        safety_evidence.append(
            ContiguousRateRadioSafetyEvidenceV1(
                radio_id=context.radio_id,
                pre_safety_evidence_sha256=_file_sha256(pre_path),
                post_safety_evidence_sha256=_file_sha256(post_path),
                pre_tx_safe=context.pre_health.tx_safe,
                post_tx_safe=item.post_health.tx_safe,
                rx_settings_restored=item.settings_restored,
                passed=(
                    context.pre_health.tx_safe
                    and item.post_health.tx_safe
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
    safety_snapshots = _snapshot_radio_safety(config)
    evidence: list[ContiguousRateTrialEvidenceV1] = []
    campaign_errors: list[str] = []
    try:
        radios = _preflight_radios(config)
        native_ip_canaries = _run_individual_ip_canaries(config, campaign_deadline)
        usb_control = _run_simultaneous_usb_control(
            config,
            campaign_deadline,
            campaign_root / "prerequisites",
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
    finally:
        safety_results = _restore_radio_safety(config, safety_snapshots)

    maintenance_claim.verify_and_release()
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
    safety_snapshots = _snapshot_radio_safety(config)
    sources = _new_sources(config)
    result = None
    close_errors: tuple[str, ...] = ()
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
    finally:
        close_errors = _close_sources(sources)
        safety_results = _restore_radio_safety(config, safety_snapshots)

    maintenance_claim.verify_and_release()
    assert not close_errors, "; ".join(close_errors)
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
                "pre_health": item.context.pre_health.model_dump(mode="json"),
                "post_health": item.post_health.model_dump(mode="json"),
            }
            for item in safety_results
        ],
    }
    report_path = campaign_root / "segmented-rate-5m-characterization-v1.json"
    _atomic_write_json(report_path, report_payload)
    record_property("segmented_rate_5m_characterization", str(report_path))
    print(f"segmented 5 MS/s characterization: {report_path}")
