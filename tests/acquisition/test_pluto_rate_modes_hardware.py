"""Opt-in, bounded full-recorder qualification for two native-IP Pluto+ radios.

This test is inert unless the operator supplies the exact authorization phrase and
every identity/evidence variable listed in ``_REQUIRED_ENV``. A typical invocation is::

    uv run --extra hardware pytest -ra -s \
      tests/acquisition/test_pluto_rate_modes_hardware.py

The output root must be an existing local directory outside this repository and
outside ``/mnt/qnap01``. The test creates one unique campaign directory and never
deletes recordings.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, distribution, version
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from threading import Barrier, Event, Timer
from typing import Any
from uuid import uuid4

import pytest

from leo.acquisition import AcquisitionCoordinator
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
    ContiguousRatePrerequisitesV1,
    ContiguousRateQualificationPolicyV1,
    ContiguousRateQualificationReceiptV1,
    ContiguousRateQualificationTargetV1,
    ContiguousRateRadioMetricsV1,
    ContiguousRateRadioSafetyEvidenceV1,
    ContiguousRateTrialEvidenceV1,
    ContiguousRateUsbControlArmEvidenceV1,
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
_RADIO_IDS = ("radio_pluto_5d4d", "radio_pluto_19f2")
_AUTHORIZED_RF_BUDGET_SECONDS = 30 * 60
_IIO_READ_TIMEOUT_SECONDS = 5.0
_RF_SHUTDOWN_RESERVE_SECONDS = 15.0
_campaign_started_monotonic: float | None = None


@dataclass(frozen=True, slots=True)
class _HardwareConfig:
    hosts: tuple[str, str]
    serials: tuple[str, str]
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
    elapsed_seconds: float

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
        values["LEO_PLUTO_RATE_RADIO_A_SERIAL"],
        values["LEO_PLUTO_RATE_RADIO_B_SERIAL"],
    )
    if len(set(hosts)) != 2 or len(set(serials)) != 2:
        pytest.fail("hardware qualification requires two unique hosts and serials", pytrace=False)
    if any(value != value.strip() or not value for value in serials):
        pytest.fail("hardware qualification serials must be exact non-empty values", pytrace=False)

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


def _attest_libiio(config: _HardwareConfig) -> None:
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

    iio = importlib.import_module("iio")
    python_iio_path = Path(str(getattr(iio, "__file__", ""))).resolve(strict=True)
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
) -> tuple[_RadioSafetyResult, _RadioSafetyResult]:
    from pluto_plus.hardware.iio import IioRadioDevice

    restored: list[_RadioSafetyResult] = []
    errors: list[str] = []
    for index, snapshot in enumerate(snapshots):
        restored_settings = None
        settings_restored = False
        device = IioRadioDevice(
            f"ip:{snapshot.host}",
            serial=snapshot.serial,
            radio_id=snapshot.radio_id,
            expected_metadata_abi=1,
        )
        try:
            device.open()
            restored_settings = device.apply_settings(snapshot.original_settings)
            settings_restored = restored_settings == snapshot.original_settings
            if not settings_restored:
                errors.append(f"{snapshot.radio_id} RX settings did not restore exactly")
        except Exception as error:  # pragma: no cover - real cleanup failure
            errors.append(f"{snapshot.radio_id} RX restore raised {type(error).__name__}: {error}")
        finally:
            try:
                device.close()
            except Exception as error:  # pragma: no cover - real cleanup failure
                errors.append(
                    f"{snapshot.radio_id} restore close raised {type(error).__name__}: {error}"
                )
        post_health = None
        try:
            post_health = _health_probe(config, index).ensure_tx_safe()
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


def _run_metadata_capture(
    *,
    uri: str,
    serial: str,
    radio_id: str,
    refills: int,
    campaign_deadline: float,
    barrier: Barrier | None = None,
    iio_contexts: dict[str, str] | None = None,
) -> _MetadataCaptureResult:
    from pluto_plus.hardware.iio import IioRadioDevice

    device = IioRadioDevice(
        uri,
        serial=serial,
        radio_id=radio_id,
        expected_metadata_abi=1,
        iio_contexts=iio_contexts,
    )
    capture = None
    try:
        device.open()
        applied = device.apply_settings(_metadata_settings())
        if applied != _metadata_settings():
            raise AssertionError(f"{radio_id} metadata control settings did not read back")
        if barrier is not None:
            barrier.wait(timeout=15)
        capture = device.begin_metadata_capture(_REFILL_SAMPLES, kernel_buffers=_KERNEL_BUFFERS)
        started = time.monotonic()
        blocks = []
        for _ in range(refills):
            _require_campaign_time(
                campaign_deadline,
                phase=f"{radio_id} metadata refill",
                minimum_remaining_seconds=(
                    _IIO_READ_TIMEOUT_SECONDS + _RF_SHUTDOWN_RESERVE_SECONDS
                ),
            )
            blocks.append(capture.read_block())
        elapsed = time.monotonic() - started
    finally:
        if capture is not None:
            capture.close()
        device.close()
    first = blocks[0]
    last = blocks[-1]
    missing = tuple(int(block.missing_samples_before) for block in blocks)
    overflows = tuple(bool(block.overflow_observed) for block in blocks)
    result = _MetadataCaptureResult(
        radio_id=radio_id,
        serial=serial,
        uri=device.identity.uri,
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
        elapsed_seconds=elapsed,
    )
    if not result.passed:
        raise AssertionError(f"{radio_id} metadata control observed loss: {result!r}")
    minimum_samples = math.floor(_SAMPLE_RATE_HZ * elapsed * 0.98)
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
) -> tuple[_MetadataCaptureResult, _MetadataCaptureResult]:
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
            )
            for radio_id, serial in zip(_RADIO_IDS, config.serials, strict=True)
        )
        results = tuple(future.result() for future in futures)
    if any(not result.uri.startswith("usb:") for result in results):
        raise AssertionError("USB control arm resolved a non-USB transport")
    return results[0], results[1]


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


def _prefix_metrics(
    result: _MetadataCaptureResult,
    *,
    requested_sample_count: int,
) -> ContiguousRateRadioMetricsV1:
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
) -> ContiguousRatePrerequisitesV1:
    evidence_root = campaign_root / "prerequisites"
    evidence_root.mkdir(mode=0o700)

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

    usb_payload = {
        "kind": "simultaneous_usb_counter_control",
        "schema_version": 1,
        "exact_prefix_sample_count_per_radio": _REQUESTED_SAMPLE_COUNT,
        "raw_captures": [asdict(item) for item in usb],
    }
    usb_path = evidence_root / "simultaneous-usb-60s.json"
    _atomic_write_json(usb_path, usb_payload)
    usb_metrics = tuple(
        _prefix_metrics(result, requested_sample_count=_REQUESTED_SAMPLE_COUNT) for result in usb
    )
    elapsed_ns = max(1, round(writer_receipt.elapsed_seconds * 1_000_000_000))
    sustained_bytes_per_second = writer_receipt.uncompressed_bytes * 1_000_000_000 // elapsed_ns
    return ContiguousRatePrerequisitesV1(
        radio_safety=(safety_evidence[0], safety_evidence[1]),
        native_ip_canaries=(native_evidence[0], native_evidence[1]),
        usb_control_arm=ContiguousRateUsbControlArmEvidenceV1(
            duration_ns=60_000_000_000,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            bandwidth_hz=_BANDWIDTH_HZ,
            evidence_sha256=_file_sha256(usb_path),
            radio_metrics=(usb_metrics[0], usb_metrics[1]),
            passed=all(
                metrics.closes_losslessly(_REQUESTED_SAMPLE_COUNT) for metrics in usb_metrics
            ),
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
    prerequisites: ContiguousRatePrerequisitesV1,
) -> ContiguousRateQualificationTargetV1:
    return ContiguousRateQualificationTargetV1(
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
    receipt: ContiguousRateQualificationReceiptV1,
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
    record_property: Any,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = _hardware_config(repository)
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
        usb_control = _run_simultaneous_usb_control(config, campaign_deadline)
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
    receipt_path = campaign_root / "contiguous-rate-qualification-receipt-v1.json"
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
    record_property: Any,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = _hardware_config(repository)
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
