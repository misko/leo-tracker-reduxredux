"""Environment-driven local composition and injectable production hooks."""

from __future__ import annotations

import ipaddress
import json
import logging
import math
import os
import secrets
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Annotated, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from leo import __version__
from leo.acquisition import (
    AcquisitionApplication,
    AcquisitionConfig,
    AcquisitionCoordinator,
    AcquisitionQueuePressure,
    AuthorizedAcquisitionApplication,
    CaptureAuthorityError,
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioResource,
    StorageAdmissionDecision,
)
from leo.acquisition.models import CaptureSessionResult
from leo.acquisition.starlink_tuning import sample_paired_starlink_tuning
from leo.catalog import (
    AcquisitionOperationLease,
    AcquisitionOperationRecord,
    CatalogRepository,
    create_catalog_engine,
    create_session_factory,
)
from leo.cli.backend import (
    CliBackend,
    CliBackendError,
    ProcessingCliBackend,
    ScheduledPersistentHopRun,
    ScheduledScannerConfiguration,
    ScheduledScannerRun,
    ScheduledScannerRunAnalysis,
    ScheduledScannerRunLike,
    ScheduledScannerSweepReference,
)
from leo.cli.calibration import CalibrationCliBackend
from leo.cli.models import (
    AcquisitionStatusDataV1,
    CalibrationPredeclareDataV1,
    CalibrationPromoteDataV1,
    CalibrationQueueDataV1,
    CalibrationShowDataV1,
    CancelRunDataV1,
    CaptureControlDataV1,
    CaptureDataV1,
    CaptureStreamCoverageV1,
    CheckState,
    DoctorCheckV1,
    DoctorDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    JobsDataV1,
    NativeEvidenceReprocessDataV1,
    ProfileListDataV1,
    ProfileShowDataV1,
    ProfileShowDataV2,
    ProfileValidationDataV1,
    RadioItemV1,
    RadioListDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    StopAndFenceDataV1,
    WorkerDataV1,
    WP11ConfigDataV1,
    WP11CreateDataV1,
    WP11FinalizeDataV1,
    WP11LegacyDataV1,
    WP11QueueDataV1,
    WP11ShowDataV1,
)
from leo.cli.profiles import ProfileDirectory
from leo.cli.scanner import (
    SCANNER_BURST_SIZE,
    STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT,
    reconcile_published_standard_scanner_analyses,
    run_published_standard_scanner_analysis,
    run_scanner_command,
    write_scanner_report,
)
from leo.cli.wp11 import WP11CliBackend
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellIntentV1,
    ProductionDwellIntentV2,
    ProductionDwellIntentV3,
)
from leo.contracts.profile import CaptureProfileRevisionV2
from leo.contracts.recording import ProducerV1
from leo.contracts.states import SourceType
from leo.domain.mixed_rate_capture import (
    compile_mixed_rate_capture_plan_v3,
    compile_production_capture_plan_v4,
    compile_production_capture_plan_v5,
)
from leo.domain.profiles import compile_capture_plan
from leo.qualification import (
    AcquisitionAcceptancePolicyV1,
    AcquisitionQualificationHarness,
    AcquisitionQualificationReceiptV1,
    AcquisitionSoakHarness,
    CaptureModeAcceptanceHarness,
    CaptureModeCampaignAcceptanceReceiptV2,
    CaptureModeExpectationV1,
    FinalSoakAcceptanceAuditor,
    PostCommitObservationV1,
    ProcessingBacklogObservationV1,
    RuntimeContinuityEvidenceV1,
    SoakAcceptanceAuditReceiptV1,
    SoakAcceptancePolicyV1,
    SoakConfigV1,
    SoakSummaryV1,
    WriterBenchmarkConfigV1,
    WriterBenchmarkReceiptV1,
    WriterThroughputBenchmark,
    capture_systemd_runtime_continuity,
    resolve_soak_evidence,
)
from leo.radio import (
    PERSISTENT_HOP_EXCLUDED_SERIAL,
    FakeRadioSource,
    PlutoIioRadioSource,
    PlutoPersistentHopRadio,
    PlutoSequentialScanRadio,
    RadioSource,
)
from leo.scanner import (
    PersistentHopPlanV1,
    PersistentHopRadio,
    ScannerCaptureBurstReportLike,
    ScannerCaptureReportLike,
    ScannerCloseFailureEvidenceV1,
    ScannerConfiguration,
    ScannerConfigurationV2,
    ScannerReportV2,
    ScannerReportV3,
    ScannerReportV4,
    ScannerReportV5,
    ScannerRunManifestV1,
    ScannerRunSweepEntryV1,
    ScheduledScannerRunIntentV1,
    SequentialScanRadioLike,
    analyze_scan_sweep,
    canonical_scheduled_scanner_operation_key,
    capture_configured_scan_sweep,
    compile_scheduled_persistent_hop_plan_v1,
    compile_scheduled_scanner_run_intent_v1,
    current_low_band_targets,
)
from leo.station.resolver import FixtureAuthorityFileReference
from leo.storage import (
    PersistentHopIqStore,
    PublishedBundle,
    PublishedScannerIqBundle,
    RecordingStore,
    ScannerAnalysisStore,
    ScannerIqStore,
    ScannerRunStore,
    capture_persistent_hop_to_store,
)
from leo.storage.errors import BundleNotFoundError

RadioSourceFactory = Callable[["RadioConfigurationV1"], RadioSource]
ScannerRadioFactory = Callable[["RadioConfigurationV1"], SequentialScanRadioLike]
PersistentHopRadioFactory = Callable[["RadioConfigurationV1"], PersistentHopRadio]
ScannerRadioSelector = Callable[[tuple["RadioConfigurationV1", ...]], "RadioConfigurationV1"]
RecordingStoreFactory = Callable[[Path], RecordingStore]
ScannerIqStoreFactory = Callable[[Path], ScannerIqStore]
ScannerAnalysisStoreFactory = Callable[[Path], ScannerAnalysisStore]
ScannerRunStoreFactory = Callable[[Path], ScannerRunStore]
PersistentHopIqStoreFactory = Callable[[Path], PersistentHopIqStore]
CaptureObserver = Callable[[CaptureSessionResult], None]

_MAX_SCANNER_REPORT_BYTES = 4 * 1024 * 1024
BackendFactory = Callable[[], CliBackend]
ProcessingBackendFactory = Callable[["CliSettings"], ProcessingCliBackend]
CalibrationBackendFactory = Callable[["CliSettings"], CalibrationCliBackend]
WP11BackendFactory = Callable[["CliSettings"], WP11CliBackend]
_CAPTURE_MODE_RADIO_CONFIG = (
    (
        "radio_pluto_5d4d",
        "1040005e0b100007100010000bf33a5d4d",
        "192.168.1.20",
    ),
    (
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        "192.168.1.21",
    ),
)


def _maximum_scanner_run_sweeps(intent: ScheduledScannerRunIntentV1) -> int:
    """Bound memory and admission to at most one sweep beyond the RF-time target."""

    sweep_signal_seconds = (
        intent.configuration.dwell_ms * len(intent.configuration.targets) / 1_000.0
    )
    return max(1, math.ceil(intent.run_duration_seconds / sweep_signal_seconds))


def _persisted_scanner_capture_elapsed_ms(bundle: PublishedScannerIqBundle) -> float:
    frames = bundle.manifest.frames
    lower = min(frame.host_request_monotonic_ns_lower for frame in frames)
    upper = max(frame.host_request_monotonic_ns_upper for frame in frames)
    return max(0.0, (upper - lower) / 1_000_000)


def _environment_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


class RadioConfigurationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    serial: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    host: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    receiver_count: Literal[1, 2] = 2


@dataclass(frozen=True, slots=True)
class CliSettings:
    profile_root: Path
    bulk_root: Path
    radio_backend: Literal["fake", "pluto"]
    radios: tuple[RadioConfigurationV1, ...]
    safety_reserve_bytes: int = 1 * 1024 * 1024 * 1024
    database_url: str | None = None
    corpus_root: Path | None = None
    pipeline_release_id: str = "standard-v1"
    acquisition_release_id: str | None = None
    qualification_root: Path = Path("/srv/bulk/leo/qualification")
    capture_evidence_root: Path = Path("/srv/bulk/leo/qualification/capture")
    legacy_evidence_root: Path = Path("/srv/bulk/leo/qualification/legacy")
    station_authority_root: Path | None = None
    station_topology_relative_path: str | None = None
    station_topology_file_digest: str | None = None
    fixture_authorities: tuple[FixtureAuthorityFileReference, ...] = ()
    scanner_enabled: bool = False
    scanner_capture_mode: Literal["sequential", "persistent_hop"] = "sequential"
    scanner_radio_id: str | None = None
    scanner_interval_seconds: float = 1_200.0
    scanner_maximum_lateness_seconds: float = 300.0
    scanner_run_seconds: float = 300.0
    scanner_dwell_ms: int = 120
    scanner_gain_db: float = 40.0
    scanner_margin_gate: float = 0.025
    scanner_persistent_transition_guard_us: int = 11_000
    scanner_persistent_samples_per_block: int = 131_072
    scanner_persistent_kernel_buffers: int = 8
    scanner_persistent_queue_capacity_visits: int = 16
    scanner_report_root: Path = Path("/srv/bulk/leo/scanner-reports")
    ddr_ring_max_rate_hz: Literal[0, 10_000_000, 15_000_000, 20_000_000] = 0
    direct_async_enabled: bool = False

    def __post_init__(self) -> None:
        ids = tuple(radio.radio_id for radio in self.radios)
        if len(ids) != len(set(ids)):
            raise ValueError("configured radio IDs must be unique")
        if len(ids) > 2:
            raise ValueError("at most two radios can be configured")
        if self.safety_reserve_bytes < 0:
            raise ValueError("acquisition safety reserve cannot be negative")
        if self.ddr_ring_max_rate_hz not in (0, 10_000_000, 15_000_000, 20_000_000):
            raise ValueError("DDR ring rollout maximum must be 0, 10, 15, or 20 MS/s")
        if self.radio_backend == "pluto":
            missing_hosts = tuple(radio.radio_id for radio in self.radios if radio.host is None)
            if missing_hosts:
                raise ValueError(f"Pluto radio hosts are missing: {missing_hosts}")
        if self.scanner_enabled:
            if self.radio_backend != "pluto":
                raise ValueError("scheduled scanner requires the Pluto radio backend")
            if self.scanner_radio_id not in ids:
                raise ValueError("scheduled scanner radio must be configured")
            if self.scanner_capture_mode == "persistent_hop":
                configured = next(
                    radio for radio in self.radios if radio.radio_id == self.scanner_radio_id
                )
                if configured.serial is None or configured.host is None:
                    raise ValueError("persistent hopping requires an exact serial and LAN host")
                try:
                    address = ipaddress.IPv4Address(configured.host)
                except ipaddress.AddressValueError as error:
                    raise ValueError(
                        "persistent hopping requires a literal 192.168.1.* host"
                    ) from error
                network = ipaddress.IPv4Network("192.168.1.0/24")
                if (
                    str(address) != configured.host
                    or address not in network
                    or address in {network[0], network[-1]}
                ):
                    raise ValueError(
                        "persistent hopping requires a usable literal 192.168.1.* host"
                    )
                if configured.serial == PERSISTENT_HOP_EXCLUDED_SERIAL:
                    raise ValueError("persistent hopping cannot use the excluded Pluto serial")
                if (
                    self.scanner_interval_seconds != 1_200
                    or self.scanner_run_seconds != 300
                    or self.scanner_dwell_ms != 120
                ):
                    raise ValueError(
                        "persistent hopping requires 1200-second cadence, 300-second runs, "
                        "and 120 ms valid visits"
                    )
        if self.scanner_interval_seconds <= 0:
            raise ValueError("scanner interval must be positive")
        if self.scanner_maximum_lateness_seconds < 0:
            raise ValueError("scanner maximum lateness cannot be negative")
        if not 0 < self.scanner_run_seconds <= 1_800:
            raise ValueError("scanner run duration is outside its operational bound")
        if self.scanner_dwell_ms < 20 or self.scanner_dwell_ms > 5_000:
            raise ValueError("scanner dwell is outside its operational bound")
        if self.scanner_dwell_ms % 20:
            raise ValueError("scanner dwell must be a multiple of 20 ms")
        if self.scanner_persistent_transition_guard_us <= 0:
            raise ValueError("persistent-hop transition guard must be positive")
        if not 4_096 <= self.scanner_persistent_samples_per_block <= 1_048_576:
            raise ValueError("persistent-hop block samples are outside the supported bound")
        if not 2 <= self.scanner_persistent_kernel_buffers <= 64:
            raise ValueError("persistent-hop kernel buffers are outside the supported bound")
        if self.scanner_persistent_queue_capacity_visits <= 0:
            raise ValueError("persistent-hop storage queue capacity must be positive")
        if not self.scanner_report_root.is_absolute():
            raise ValueError("scanner report root must be absolute")
        if self.scanner_report_root == Path("/mnt/qnap01") or str(
            self.scanner_report_root
        ).startswith("/mnt/qnap01/"):
            raise ValueError("scanner reports cannot be written beneath QNAP")

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> CliSettings:
        values = os.environ if environ is None else environ
        raw_radios = values.get("LEO_RADIOS_JSON", "[]")
        try:
            decoded = json.loads(raw_radios)
            if not isinstance(decoded, list):
                raise ValueError("LEO_RADIOS_JSON must contain a JSON list")
            radios = tuple(RadioConfigurationV1.model_validate(item) for item in decoded)
            backend = values.get("LEO_RADIO_BACKEND", "fake")
            if backend not in {"fake", "pluto"}:
                raise ValueError("LEO_RADIO_BACKEND must be fake or pluto")
            scanner_capture_mode = values.get("LEO_SCANNER_CAPTURE_MODE", "sequential")
            if scanner_capture_mode not in {"sequential", "persistent_hop"}:
                raise ValueError(
                    "LEO_SCANNER_CAPTURE_MODE must be sequential or persistent_hop"
                )
            reserve = int(values.get("LEO_ACQUISITION_RESERVE_BYTES", str(1024**3)))
            raw_fixture_authorities = json.loads(
                values.get("LEO_FIXTURE_PATH_AUTHORITIES_JSON", "[]")
            )
            if not isinstance(raw_fixture_authorities, list):
                raise ValueError("LEO_FIXTURE_PATH_AUTHORITIES_JSON must contain a JSON list")
            fixture_authorities = tuple(
                FixtureAuthorityFileReference(
                    manifest_digest=item["manifest_digest"],
                    relative_path=item["relative_path"],
                    file_digest=item["file_digest"],
                )
                for item in raw_fixture_authorities
            )
            bulk_root = Path(values.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
            qualification_root = Path(
                values.get("LEO_QUALIFICATION_ROOT", str(bulk_root / "qualification"))
            )
            return cls(
                profile_root=Path(values.get("LEO_PROFILE_ROOT", "profiles")),
                bulk_root=bulk_root,
                radio_backend=cast(Literal["fake", "pluto"], backend),
                radios=radios,
                safety_reserve_bytes=reserve,
                ddr_ring_max_rate_hz=cast(
                    Literal[0, 10_000_000, 15_000_000, 20_000_000],
                    int(values.get("LEO_DDR_RING_MAX_RATE_HZ", "0")),
                ),
                direct_async_enabled=_environment_bool(values, "LEO_DIRECT_ASYNC_ENABLED", False),
                database_url=values.get("LEO_DATABASE_URL"),
                corpus_root=Path(
                    values.get(
                        "LEO_CORPUS_ROOT",
                        str(bulk_root / "test-corpus"),
                    )
                ),
                pipeline_release_id=values.get("LEO_PIPELINE_RELEASE_ID", "standard-v1"),
                acquisition_release_id=values.get("LEO_ACQUISITION_RELEASE_ID"),
                qualification_root=qualification_root,
                capture_evidence_root=Path(
                    values.get(
                        "LEO_CAPTURE_EVIDENCE_ROOT",
                        str(qualification_root / "capture"),
                    )
                ),
                legacy_evidence_root=Path(
                    values.get(
                        "LEO_LEGACY_EVIDENCE_ROOT",
                        str(qualification_root / "legacy"),
                    )
                ),
                station_authority_root=(
                    None
                    if values.get("LEO_STATION_AUTHORITY_ROOT") is None
                    else Path(values["LEO_STATION_AUTHORITY_ROOT"])
                ),
                station_topology_relative_path=values.get("LEO_STATION_TOPOLOGY_RELATIVE_PATH"),
                station_topology_file_digest=values.get("LEO_STATION_TOPOLOGY_FILE_DIGEST"),
                fixture_authorities=fixture_authorities,
                scanner_enabled=_environment_bool(values, "LEO_SCANNER_ENABLED", False),
                scanner_capture_mode=cast(
                    Literal["sequential", "persistent_hop"], scanner_capture_mode
                ),
                scanner_radio_id=values.get("LEO_SCANNER_RADIO_ID"),
                scanner_interval_seconds=float(values.get("LEO_SCANNER_INTERVAL_SECONDS", "1200")),
                scanner_maximum_lateness_seconds=float(
                    values.get("LEO_SCANNER_MAXIMUM_LATENESS_SECONDS", "300")
                ),
                scanner_run_seconds=float(values.get("LEO_SCANNER_RUN_SECONDS", "300")),
                scanner_dwell_ms=int(values.get("LEO_SCANNER_DWELL_MS", "120")),
                scanner_gain_db=float(values.get("LEO_SCANNER_GAIN_DB", "40")),
                scanner_margin_gate=float(values.get("LEO_SCANNER_MARGIN_GATE", "0.025")),
                scanner_persistent_transition_guard_us=int(
                    values.get("LEO_SCANNER_PERSISTENT_TRANSITION_GUARD_US", "11000")
                ),
                scanner_persistent_samples_per_block=int(
                    values.get("LEO_SCANNER_PERSISTENT_SAMPLES_PER_BLOCK", "131072")
                ),
                scanner_persistent_kernel_buffers=int(
                    values.get("LEO_SCANNER_PERSISTENT_KERNEL_BUFFERS", "8")
                ),
                scanner_persistent_queue_capacity_visits=int(
                    values.get("LEO_SCANNER_PERSISTENT_QUEUE_CAPACITY_VISITS", "16")
                ),
                scanner_report_root=Path(
                    values.get(
                        "LEO_SCANNER_REPORT_ROOT",
                        str(bulk_root / "scanner-reports"),
                    )
                ),
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise CliBackendError(
                f"invalid CLI environment configuration: {error}",
                ExitCode.INVALID_CONFIGURATION,
            ) from error


@dataclass(frozen=True, slots=True)
class CompositionHooks:
    """Replaceable hardware, storage, and catalog-registration boundaries."""

    radio_source_factory: RadioSourceFactory | None = None
    scanner_radio_factory: ScannerRadioFactory | None = None
    persistent_hop_radio_factory: PersistentHopRadioFactory | None = None
    scanner_radio_selector: ScannerRadioSelector = secrets.choice
    recording_store_factory: RecordingStoreFactory = RecordingStore
    scanner_iq_store_factory: ScannerIqStoreFactory = ScannerIqStore
    scanner_analysis_store_factory: ScannerAnalysisStoreFactory = ScannerAnalysisStore
    scanner_run_store_factory: ScannerRunStoreFactory = ScannerRunStore
    persistent_hop_store_factory: PersistentHopIqStoreFactory = PersistentHopIqStore
    scanner_monotonic: Callable[[], float] = time.monotonic
    scanner_utc_ns: Callable[[], int] = time.time_ns
    capture_observer: CaptureObserver = lambda _result: None
    processing_backend_factory: ProcessingBackendFactory | None = None
    calibration_backend_factory: CalibrationBackendFactory | None = None
    wp11_backend_factory: WP11BackendFactory | None = None


class LocalAcquisitionBackend:
    def __init__(self, settings: CliSettings, hooks: CompositionHooks | None = None) -> None:
        self.settings = settings
        self.hooks = hooks or CompositionHooks()
        self.profiles = ProfileDirectory(settings.profile_root)
        self._store: RecordingStore | None = None
        self._scanner_iq: ScannerIqStore | None = None
        self._scanner_analysis: ScannerAnalysisStore | None = None
        self._scanner_runs: ScannerRunStore | None = None
        self._persistent_hop_store: PersistentHopIqStore | None = None
        self._capture_authority: LocalCaptureAuthority | None = None
        self._processing_backend: ProcessingCliBackend | None = None
        self._calibration_backend: CalibrationCliBackend | None = None
        self._wp11_backend: WP11CliBackend | None = None
        self._acquisition_operations: CatalogRepository | None = None

    def radios(self, *, probe: bool) -> RadioListDataV1:
        items: list[RadioItemV1] = []
        for configuration in self.settings.radios:
            state: Literal["configured", "ready", "error"] = "configured"
            detail = None
            if probe:
                source = self._radio_source(configuration)
                try:
                    with self._authority().claim(
                        (configuration.radio_id,),
                        task_id=f"radio-probe-{uuid4().hex[:16]}",
                        task_kind=CaptureTaskKind.RADIO_PROBE,
                    ):
                        try:
                            identity = source.open()
                        finally:
                            source.close()
                    expected_serial = configuration.serial or configuration.radio_id
                    if identity.serial != expected_serial:
                        raise RuntimeError(
                            f"serial readback {identity.serial!r} != {expected_serial!r}"
                        )
                    state = "ready"
                    detail = identity.uri
                except Exception as error:
                    state = "error"
                    detail = f"{type(error).__name__}: {error}"
            items.append(
                RadioItemV1(
                    radio_id=configuration.radio_id,
                    serial=configuration.serial or configuration.radio_id,
                    backend=self.settings.radio_backend,
                    host=configuration.host,
                    receiver_count=configuration.receiver_count,
                    state=state,
                    detail=detail,
                )
            )
        return RadioListDataV1(radios=tuple(items))

    def doctor(self, *, probe_radios: bool) -> DoctorDataV1:
        checks: list[DoctorCheckV1] = []
        try:
            validation = self.profiles.validate(None)
            checks.append(
                DoctorCheckV1(
                    name="profiles",
                    state=(CheckState.PASS if validation.valid else CheckState.FAIL),
                    detail=f"{len(validation.items)} profile document(s)",
                )
            )
        except Exception as error:
            checks.append(_failed_check("profiles", error))

        try:
            root = self.settings.bulk_root
            root.mkdir(parents=True, exist_ok=True)
            control = root / "control"
            control.mkdir(exist_ok=True)
            probe_path = control / f".doctor-{os.getpid()}-{uuid4().hex}.tmp"
            with probe_path.open("xb") as stream:
                stream.write(b"leo-doctor")
                stream.flush()
                os.fsync(stream.fileno())
            probe_path.unlink()
            free = shutil.disk_usage(root).free
            checks.append(
                DoctorCheckV1(
                    name="bulk_storage",
                    state=CheckState.PASS,
                    detail=f"{root.resolve()} has {free} free bytes",
                )
            )
        except Exception as error:
            checks.append(_failed_check("bulk_storage", error))

        if not self.settings.radios:
            checks.append(
                DoctorCheckV1(
                    name="radios",
                    state=CheckState.FAIL,
                    detail="no acquisition radios are configured",
                )
            )
        else:
            radio_items = self.radios(probe=probe_radios).radios
            failed = tuple(item for item in radio_items if item.state == "error")
            checks.append(
                DoctorCheckV1(
                    name="radios",
                    state=CheckState.FAIL if failed else CheckState.PASS,
                    detail=(
                        f"{len(failed)} of {len(radio_items)} radio probes failed"
                        if failed
                        else f"{len(radio_items)} radio(s) configured"
                    ),
                )
            )
        healthy = all(check.state is not CheckState.FAIL for check in checks)
        return DoctorDataV1(healthy=healthy, checks=tuple(checks))

    def profiles_list(self) -> ProfileListDataV1:
        return self.profiles.list_profiles()

    def profile_show(self, name: str) -> ProfileShowDataV1 | ProfileShowDataV2:
        return self.profiles.show(name)

    def profiles_validate(self, target: str | None) -> ProfileValidationDataV1:
        return self.profiles.validate(target)

    def capture_once(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        session_id: str | None,
        extra_tags: tuple[str, ...],
        cancel: Event,
        task_kind: str = CaptureTaskKind.OPERATOR_ONCE.value,
    ) -> CaptureDataV1:
        shown = self.profiles.show(profile_name)
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        selected_ids = tuple(radio_ids) if radio_ids else tuple(configured)
        if not selected_ids:
            raise CliBackendError(
                "no acquisition radios are configured or selected",
                ExitCode.INVALID_CONFIGURATION,
            )
        if len(selected_ids) > 2 or len(set(selected_ids)) != len(selected_ids):
            raise CliBackendError(
                "select one or two unique configured radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        unknown = tuple(radio_id for radio_id in selected_ids if radio_id not in configured)
        if unknown:
            raise CliBackendError(
                f"selected radios are not configured: {unknown}",
                ExitCode.INVALID_CONFIGURATION,
            )
        try:
            source_type = (
                SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
            )
            plan = compile_capture_plan(
                shown.revision,
                selected_ids,
                source_type=source_type,
            )
            store = self._recording_store()
            coordinator = AcquisitionCoordinator(
                store,
                producer=self._acquisition_producer(),
                config=AcquisitionConfig(
                    safety_reserve_bytes=self.settings.safety_reserve_bytes,
                ),
                storage_admission=self._capture_storage_admission,
            )
            try:
                resolved_task_kind = CaptureTaskKind(task_kind)
            except ValueError as error:
                raise CliBackendError(
                    f"unsupported capture task kind: {task_kind}",
                    ExitCode.INVALID_CONFIGURATION,
                ) from error
            application = AuthorizedAcquisitionApplication(
                AcquisitionApplication(coordinator),
                self._authority(),
                resolved_task_kind,
            )
            sources = {
                radio_id: self._radio_source(configured[radio_id]) for radio_id in selected_ids
            }
            tags = set(extra_tags)
            if source_type is SourceType.TEST:
                tags.add("TEST")
            requested_settings_by_radio = None
            if (
                source_type is SourceType.LIVE
                and len(selected_ids) == 2
                and "RANDOM_TUNING" in shown.revision.profile.tags
            ):
                selection = sample_paired_starlink_tuning((selected_ids[0], selected_ids[1]))
                requested_settings_by_radio = selection.requested_settings(shown.revision.profile)
                tags.update(selection.manifest_tags)
            result = application.once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=tuple(sorted(tags)),
                requested_settings_by_radio=requested_settings_by_radio,
            )
            self.hooks.capture_observer(result)
            data = _capture_data(profile_name, plan.radio_ids, result)
            if result.bundle is not None:
                warning = self._post_commit_registration(result.bundle.session_id)
                if warning is not None:
                    data = data.model_copy(update={"errors": (*data.errors, warning)})
            self._write_last_capture(data)
            return data
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except CliBackendError:
            raise
        except Exception as error:
            raise CliBackendError(
                f"capture setup failed: {type(error).__name__}: {error}",
                ExitCode.CAPTURE_FAILED,
            ) from error

    def mixed_rate_profile_authority(self) -> dict[int, tuple[str, str]]:
        profile_names: dict[int, str] = {
            2_500_000: "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
            5_000_000: "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
            10_000_000: "starlink-ch4-lower-10m-60s-mixed-device-axis-v4",
            15_000_000: "starlink-ch4-lower-15m-60s-mixed-device-axis-v4",
        }
        authority: dict[int, tuple[str, str]] = {}
        for rate, profile_name in profile_names.items():
            shown = self.profiles.show(profile_name)
            if not isinstance(shown.revision, CaptureProfileRevisionV2):
                raise CliBackendError(
                    f"mixed-rate profile {profile_name} is not CaptureProfileV2",
                    ExitCode.INVALID_CONFIGURATION,
                )
            if shown.revision.profile.sample_rate_hz != rate:
                raise CliBackendError(
                    f"mixed-rate profile {profile_name} rate disagrees with authority",
                    ExitCode.INVALID_CONFIGURATION,
                )
            authority[rate] = (profile_name, shown.revision.revision_digest)
        return authority

    def production_profile_authority(
        self,
    ) -> dict[tuple[int, tuple[int, ...], bool], tuple[str, str, int]]:
        profile_names: dict[tuple[int, tuple[int, ...], bool], str] = {
            (2_500_000, (0, 1), False): "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
            (5_000_000, (0, 1), False): "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
            (2_500_000, (0, 1), True): "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
            (5_000_000, (0, 1), True): "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
            **{
                (rate, (receiver,), True): (
                    f"starlink-ch4-lower-{rate // 1_000_000}m-60s-rx{receiver}-"
                    + (
                        "direct-async-exact-dma-drop-v12"
                        if self.settings.direct_async_enabled
                        else (
                            "ddr-ring-v6"
                            if rate <= self.settings.ddr_ring_max_rate_hz
                            else "production-v5"
                        )
                    )
                )
                for rate in (10_000_000, 15_000_000, 20_000_000)
                for receiver in (0, 1)
            },
            **{
                (25_000_000, (receiver,), True): (
                    f"starlink-ch4-lower-25m-60s-rx{receiver}-"
                    + (
                        "direct-async-exact-dma-drop-v12"
                        if self.settings.direct_async_enabled
                        else "direct-async-v8"
                    )
                )
                for receiver in (0, 1)
            },
        }
        authority: dict[tuple[int, tuple[int, ...], bool], tuple[str, str, int]] = {}
        for key, profile_name in profile_names.items():
            shown = self.profiles.show(profile_name)
            if not isinstance(shown.revision, CaptureProfileRevisionV2):
                raise CliBackendError(
                    f"production profile {profile_name} is not CaptureProfileV2",
                    ExitCode.INVALID_CONFIGURATION,
                )
            rate, receivers, _mixed = key
            profile = shown.revision.profile
            if profile.sample_rate_hz != rate or profile.receivers != receivers:
                raise CliBackendError(
                    f"production profile {profile_name} geometry disagrees with authority",
                    ExitCode.INVALID_CONFIGURATION,
                )
            authority[key] = (
                profile_name,
                shown.revision.revision_digest,
                profile.refill_samples,
            )
        return authority

    def capture_mixed_once(
        self,
        intent: ProductionDwellIntentV1,
        *,
        session_id: str | None,
        cancel: Event,
        task_kind: str = CaptureTaskKind.OPERATOR_ONCE.value,
    ) -> CaptureDataV1:
        if intent.ordinary_profile_name is not None:
            raise CliBackendError(
                "ordinary scheduled intent cannot use mixed-rate capture",
                ExitCode.INVALID_CONFIGURATION,
            )
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        selected_ids = tuple(item.radio_id for item in intent.radio_rates)
        if set(selected_ids) != set(configured) or len(selected_ids) != 2:
            raise CliBackendError(
                "mixed-rate capture requires the exact configured two-radio station",
                ExitCode.INVALID_CONFIGURATION,
            )
        authority = self.mixed_rate_profile_authority()
        revisions: dict[str, CaptureProfileRevisionV2] = {}
        for assignment in intent.radio_rates:
            expected = authority[assignment.sample_rate_hz]
            if (assignment.profile_name, assignment.profile_revision_digest) != expected:
                raise CliBackendError(
                    "persisted mixed-rate profile authority differs from this release",
                    ExitCode.INVALID_CONFIGURATION,
                )
            shown = self.profiles.show(assignment.profile_name)
            if not isinstance(shown.revision, CaptureProfileRevisionV2):
                raise CliBackendError(
                    "mixed-rate capture requires CaptureProfileV2 revisions",
                    ExitCode.INVALID_CONFIGURATION,
                )
            revisions[assignment.radio_id] = shown.revision
        try:
            source_type = (
                SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
            )
            if intent.starlink_channel is None or intent.starlink_edge is None:
                raise ValueError("mixed-rate capture intent lacks common tuning")
            plan = compile_mixed_rate_capture_plan_v3(
                dwell_class=intent.dwell_class,
                radio_ids=selected_ids,
                profile_revisions_by_radio=revisions,
                starlink_channel=intent.starlink_channel,
                starlink_edge=intent.starlink_edge,
                source_type=source_type,
            )
            coordinator = AcquisitionCoordinator(
                self._recording_store(),
                producer=self._acquisition_producer(),
                config=AcquisitionConfig(
                    safety_reserve_bytes=self.settings.safety_reserve_bytes,
                ),
                storage_admission=self._capture_storage_admission,
            )
            resolved_task_kind = CaptureTaskKind(task_kind)
            application = AuthorizedAcquisitionApplication(
                AcquisitionApplication(coordinator),
                self._authority(),
                resolved_task_kind,
            )
            sources = {
                radio_id: self._radio_source(configured[radio_id]) for radio_id in selected_ids
            }
            tags = set(intent.extra_tags)
            if source_type is SourceType.TEST:
                tags.add("TEST")
            result = application.once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=tuple(sorted(tags)),
            )
            self.hooks.capture_observer(result)
            label = intent.dwell_class.value
            data = _capture_data(label, plan.radio_ids, result)
            if result.bundle is not None:
                warning = self._post_commit_registration(result.bundle.session_id)
                if warning is not None:
                    data = data.model_copy(update={"errors": (*data.errors, warning)})
            self._write_last_capture(data)
            return data
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except CliBackendError:
            raise
        except Exception as error:
            raise CliBackendError(
                f"mixed-rate capture setup failed: {type(error).__name__}: {error}",
                ExitCode.CAPTURE_FAILED,
            ) from error

    def capture_production_once(
        self,
        intent: ProductionDwellIntentV2 | ProductionDwellIntentV3,
        *,
        session_id: str | None,
        cancel: Event,
        task_kind: str = CaptureTaskKind.OPERATOR_ONCE.value,
    ) -> CaptureDataV1:
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        if set(intent.radio_ids) != set(configured) or len(intent.radio_ids) != 2:
            raise CliBackendError(
                "production capture requires the exact configured two-radio station",
                ExitCode.INVALID_CONFIGURATION,
            )
        authority = self.production_profile_authority()
        revisions: dict[str, CaptureProfileRevisionV2] = {}
        is_mixed = intent.dwell_class.value.startswith("mixed_")
        for assignment in intent.radio_legs:
            key = (assignment.sample_rate_hz, assignment.receiver_ids, is_mixed)
            expected = authority[key]
            if (assignment.profile_name, assignment.profile_revision_digest) != expected[:2]:
                raise CliBackendError(
                    "persisted production profile authority differs from this release",
                    ExitCode.INVALID_CONFIGURATION,
                )
            shown = self.profiles.show(assignment.profile_name)
            assert isinstance(shown.revision, CaptureProfileRevisionV2)
            revisions[assignment.radio_id] = shown.revision
        try:
            source_type = (
                SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
            )
            plan = (
                compile_production_capture_plan_v5(
                    intent=intent,
                    profile_revisions_by_radio=revisions,
                    source_type=source_type,
                )
                if isinstance(intent, ProductionDwellIntentV3)
                else compile_production_capture_plan_v4(
                    intent=intent,
                    profile_revisions_by_radio=revisions,
                    source_type=source_type,
                )
            )
            coordinator = AcquisitionCoordinator(
                self._recording_store(),
                producer=self._acquisition_producer(),
                config=AcquisitionConfig(safety_reserve_bytes=self.settings.safety_reserve_bytes),
                storage_admission=self._capture_storage_admission,
            )
            application = AuthorizedAcquisitionApplication(
                AcquisitionApplication(coordinator),
                self._authority(),
                CaptureTaskKind(task_kind),
            )
            sources = {
                radio_id: self._radio_source(configured[radio_id]) for radio_id in intent.radio_ids
            }
            tags = set(intent.extra_tags)
            if source_type is SourceType.TEST:
                tags.add("TEST")
            result = application.once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=tuple(sorted(tags)),
            )
            self.hooks.capture_observer(result)
            data = _capture_data(intent.dwell_class.value, plan.radio_ids, result)
            if result.bundle is not None:
                warning = self._post_commit_registration(result.bundle.session_id)
                if warning is not None:
                    data = data.model_copy(update={"errors": (*data.errors, warning)})
            self._write_last_capture(data)
            return data
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        except CliBackendError:
            raise
        except Exception as error:
            raise CliBackendError(
                f"production capture setup failed: {type(error).__name__}: {error}",
                ExitCode.CAPTURE_FAILED,
            ) from error

    def acquisition_queue_pressure(self) -> AcquisitionQueuePressure:
        """Adapt the catalog's consistent backlog snapshot to acquisition's port."""

        backlog = self._processing().jobs()
        return AcquisitionQueuePressure(queued=backlog.queued, running=backlog.running)

    def enqueue_acquisition_operation(
        self,
        *,
        operation_key: str,
        kind: str,
        payload: dict[str, object],
        scheduled_for: datetime,
        priority: int = 0,
        coalesce_pending_kind: bool = False,
    ) -> AcquisitionOperationRecord:
        return self._acquisition_operation_catalog().enqueue_acquisition_operation(
            operation_key=operation_key,
            kind=kind,
            payload=payload,
            scheduled_for=scheduled_for,
            priority=priority,
            coalesce_pending_kind=coalesce_pending_kind,
        )

    def active_acquisition_operations(
        self,
        *,
        limit: int = 200,
        kinds: Sequence[str] | None = None,
    ) -> tuple[AcquisitionOperationRecord, ...]:
        return self._acquisition_operation_catalog().active_acquisition_operations(
            limit=limit,
            kinds=kinds,
        )

    def claim_acquisition_operation(
        self,
        *,
        worker_id: str,
        lease_for: timedelta,
        kinds: Sequence[str] | None = None,
    ) -> AcquisitionOperationLease | None:
        return self._acquisition_operation_catalog().claim_acquisition_operation(
            worker_id=worker_id,
            lease_for=lease_for,
            kinds=kinds,
        )

    def complete_acquisition_operation(
        self, *, operation_id: int, worker_id: str, outcome: str
    ) -> None:
        self._acquisition_operation_catalog().complete_acquisition_operation(
            operation_id=operation_id, worker_id=worker_id, outcome=outcome
        )

    def fail_acquisition_operation(
        self,
        *,
        operation_id: int,
        worker_id: str,
        error: str,
        retryable: bool = True,
        retry_after: timedelta = timedelta(0),
    ) -> str:
        return self._acquisition_operation_catalog().fail_acquisition_operation(
            operation_id=operation_id,
            worker_id=worker_id,
            error=error,
            retryable=retryable,
            retry_after=retry_after,
        )

    def reclaim_expired_acquisition_operations(self) -> tuple[int, ...]:
        return self._acquisition_operation_catalog().reclaim_expired_acquisition_operations()

    def status(self) -> AcquisitionStatusDataV1:
        store = self._recording_store()
        reconciliation = store.reconcile()
        return AcquisitionStatusDataV1(
            backend=self.settings.radio_backend,
            bulk_root=str(store.root),
            configured_radio_count=len(self.settings.radios),
            valid_profile_count=self.profiles.count_valid(),
            committed_recording_count=len(reconciliation.committed),
            incomplete_spool_count=sum(1 for _ in store.spool_root.glob("*.partial")),
            reconcile_issue_count=len(reconciliation.issues),
            catalog_registration_warning=self._read_registration_warning(),
            last_capture=self._read_last_capture(),
            capture_control=self._authority().snapshot(),
        )

    def capture_pause(
        self,
        *,
        operator_id: str,
        reason: str,
        wait: bool,
        timeout_seconds: float,
    ) -> CaptureControlDataV1:
        state = self._authority().pause(
            operator_id=operator_id,
            reason=reason,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        return CaptureControlDataV1(state=state, radio_ids=self._authority().radio_ids)

    def capture_resume(self, *, operator_id: str, reason: str) -> CaptureControlDataV1:
        state = self._authority().resume(operator_id=operator_id, reason=reason)
        return CaptureControlDataV1(state=state, radio_ids=self._authority().radio_ids)

    def capture_control_snapshot(self):
        return self._authority().snapshot()

    def scan_starlink(
        self,
        *,
        host: str,
        serial: str,
        radio_id: str,
        gain_db: float,
        margin_gate: float,
        dwell_ms: int,
        output_path: Path | None,
    ) -> ScannerCaptureBurstReportLike:
        configured = {item.radio_id: item for item in self.settings.radios}
        radio = configured.get(radio_id)
        if radio is None:
            raise CliBackendError(
                f"scanner radio is not configured: {radio_id}",
                ExitCode.INVALID_CONFIGURATION,
            )
        if self.settings.radio_backend != "pluto" or radio.host != host:
            raise CliBackendError(
                "scanner host must match its configured Pluto radio",
                ExitCode.INVALID_CONFIGURATION,
            )
        if (radio.serial or radio.radio_id) != serial:
            raise CliBackendError(
                "scanner serial must match its configured Pluto radio",
                ExitCode.INVALID_CONFIGURATION,
            )
        self._admit_scanner_iq(
            ScannerConfigurationV2(
                gain_db=gain_db,
                glrt64_margin_gate=margin_gate,
                dwell_ms=dwell_ms,
                maximum_acquisition_candidates=(STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT),
                targets=current_low_band_targets(),
            ),
            scan_count=SCANNER_BURST_SIZE,
        )
        try:
            lease = self._authority().claim(
                (radio_id,),
                task_id=f"scan-{uuid4().hex[:16]}",
                task_kind=CaptureTaskKind.SCANNER_SWEEP,
            )
            return run_scanner_command(
                host=host,
                serial=serial,
                radio_id=radio_id,
                gain_db=gain_db,
                margin_gate=margin_gate,
                dwell_ms=dwell_ms,
                output_path=output_path,
                radio=self._scanner_radio(radio),
                capture_lease=lease,
                iq_store=self._scanner_iq_store(),
                analysis_store=self._scanner_analysis_store(),
            )
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error

    def scanner_schedule(self) -> ScheduledScannerConfiguration | None:
        if not self.settings.scanner_enabled:
            return None
        return ScheduledScannerConfiguration(
            interval_seconds=self.settings.scanner_interval_seconds,
            maximum_lateness_seconds=self.settings.scanner_maximum_lateness_seconds,
            run_duration_seconds=self.settings.scanner_run_seconds,
            requires_durable_queue=self.settings.scanner_capture_mode == "persistent_hop",
        )

    def scheduled_scanner_intent(
        self,
        *,
        operation_key: str,
        scheduled_for: datetime,
    ) -> ScheduledScannerRunIntentV1:
        if not self.settings.scanner_enabled:
            raise CliBackendError("scheduled scanner is disabled", ExitCode.INVALID_CONFIGURATION)
        expected_operation_key = canonical_scheduled_scanner_operation_key(scheduled_for)
        if operation_key != expected_operation_key:
            raise CliBackendError(
                "scheduled scanner operation key disagrees with its UTC cadence slot",
                ExitCode.INVALID_CONFIGURATION,
            )
        assert self.settings.scanner_radio_id is not None
        configured = next(
            radio
            for radio in self.settings.radios
            if radio.radio_id == self.settings.scanner_radio_id
        )
        return compile_scheduled_scanner_run_intent_v1(
            operation_key=operation_key,
            radio_id=configured.radio_id,
            radio_serial=configured.serial or configured.radio_id,
            scheduled_for=scheduled_for,
            interval_seconds=self.settings.scanner_interval_seconds,
            maximum_lateness_seconds=self.settings.scanner_maximum_lateness_seconds,
            run_duration_seconds=self.settings.scanner_run_seconds,
            dwell_ms=self.settings.scanner_dwell_ms,
            gain_db=self.settings.scanner_gain_db,
            margin_gate=self.settings.scanner_margin_gate,
            maximum_acquisition_candidates=STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT,
        )

    def reconcile_scanner_recordings(self) -> None:
        result = reconcile_published_standard_scanner_analyses(
            self._scanner_iq_store(),
            self._scanner_analysis_store(),
        )
        if result.analyzed or result.failed:
            logging.getLogger(__name__).info(
                "scanner_analysis_reconciled discovered=%d existing=%d analyzed=%d failed=%d",
                result.discovered,
                result.already_analyzed,
                len(result.analyzed),
                len(result.failed),
            )

    def capture_scheduled_scanner(
        self,
        intent: ScheduledScannerRunIntentV1,
        *,
        cancel: Event,
    ) -> ScheduledScannerRunLike:
        if not self.settings.scanner_enabled:
            raise CliBackendError("scheduled scanner is disabled", ExitCode.INVALID_CONFIGURATION)
        expected = self.scheduled_scanner_intent(
            operation_key=intent.operation_key,
            scheduled_for=intent.scheduled_for,
        )
        if intent != expected:
            raise CliBackendError(
                "scheduled scanner intent disagrees with runtime policy",
                ExitCode.INVALID_CONFIGURATION,
            )
        if self.settings.scanner_capture_mode == "persistent_hop":
            return self._capture_scheduled_persistent_hop(intent, cancel=cancel)
        configured = next(
            radio for radio in self.settings.radios if radio.radio_id == intent.radio_id
        )
        radio_id = configured.radio_id
        assert configured.host is not None
        configuration = intent.configuration
        maximum_sweeps = _maximum_scanner_run_sweeps(intent)
        run_id = f"scan-run-{intent.intent_digest.removeprefix('sha256:')[:16]}"
        stamp = intent.scheduled_for.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        try:
            existing = self._scanner_run_store().inspect(run_id)
        except BundleNotFoundError:
            pass
        else:
            if existing.manifest.intent != intent:
                raise CliBackendError(
                    "persisted scanner run disagrees with the scheduled intent",
                    ExitCode.CONFLICT,
                )
            return ScheduledScannerRun(
                intent=intent,
                published=existing,
                sweeps=self._restore_scheduled_scanner_sweeps(existing.manifest),
            )
        self._admit_scanner_iq(configuration, scan_count=maximum_sweeps)
        references = list(
            self._recover_scheduled_scanner_sweeps(
                intent,
                run_id=run_id,
                stamp=stamp,
                maximum_sweeps=maximum_sweeps,
            )
        )
        run_started_utc_ns = self.hooks.scanner_utc_ns()
        run_started = self.hooks.scanner_monotonic()
        scanner_radio = self._scanner_radio(configured)
        identity = scanner_radio.identity
        close_failure: ScannerCloseFailureEvidenceV1 | None = None
        status: Literal["complete", "cancelled", "failed"] = "failed"
        stop_reason = "scanner run did not start"
        opened = False
        try:
            with self._authority().claim(
                (radio_id,),
                task_id=run_id,
                task_kind=CaptureTaskKind.SCANNER_SWEEP,
            ):
                try:
                    if not cancel.is_set() and len(references) < maximum_sweeps:
                        identity = scanner_radio.open()
                        opened = True
                        scanner_radio.configure_once(configuration)
                        deadline = run_started + intent.run_duration_seconds
                        pending: Future[ScheduledScannerSweepReference] | None = None
                        with ThreadPoolExecutor(
                            max_workers=1,
                            thread_name_prefix="leo-scanner-publish",
                        ) as publisher:
                            while (
                                not cancel.is_set()
                                and len(references) + (pending is not None) < maximum_sweeps
                                and (pending is None or self.hooks.scanner_monotonic() < deadline)
                            ):
                                sweep_number = (
                                    len(references) + (1 if pending is not None else 0) + 1
                                )
                                captured = capture_configured_scan_sweep(
                                    scanner_radio,
                                    configuration,
                                    identity=identity,
                                )
                                if pending is not None:
                                    references.append(pending.result())
                                scan_id = (
                                    f"scan-{run_id.removeprefix('scan-run-')}-{sweep_number:04d}"
                                )
                                output_path = self._scheduled_scanner_report_path(
                                    stamp=stamp,
                                    scan_id=scan_id,
                                )
                                pending = publisher.submit(
                                    self._publish_scheduled_scanner_sweep,
                                    captured,
                                    scan_id=scan_id,
                                    output_path=output_path,
                                )
                            if pending is not None:
                                references.append(pending.result())
                    if cancel.is_set():
                        status = "cancelled"
                        stop_reason = "capture cancellation requested between complete sweeps"
                    else:
                        status = "complete"
                        stop_reason = (
                            f"{intent.run_duration_seconds:g}-second capture window "
                            "reached at a sweep boundary"
                        )
                except Exception as error:
                    status = "failed"
                    stop_reason = f"{type(error).__name__}: {error}"[:2048]
                finally:
                    if opened:
                        try:
                            scanner_radio.close()
                        except Exception as error:
                            close_failure = ScannerCloseFailureEvidenceV1(
                                exception_type=type(error).__name__,
                                message=(
                                    str(error) or "radio close failed without an exception message"
                                )[:2048],
                            )
                            status = "failed"
                            stop_reason = "scanner radio close failed"
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        finalized_utc_ns = max(run_started_utc_ns, self.hooks.scanner_utc_ns())
        manifest = ScannerRunManifestV1(
            run_id=run_id,
            intent=intent,
            radio_id=identity.radio_id,
            radio_serial=identity.serial,
            radio_uri=identity.uri,
            started_utc_ns=run_started_utc_ns,
            finalized_utc_ns=finalized_utc_ns,
            capture_elapsed_ms=max(
                0.0,
                (self.hooks.scanner_monotonic() - run_started) * 1_000,
            ),
            status=status,
            stop_reason=stop_reason,
            sweeps=tuple(
                ScannerRunSweepEntryV1(
                    scan_id=reference.scan_id,
                    capture_elapsed_ms=reference.capture_elapsed_ms,
                    iq_bundle_uri=(
                        None if reference.iq_bundle is None else reference.iq_bundle.uri
                    ),
                    iq_manifest_sha256=(
                        None if reference.iq_bundle is None else reference.iq_bundle.manifest_sha256
                    ),
                    report_filename=reference.output_path.name,
                )
                for reference in references
            ),
            close_failure=close_failure,
        )
        published = self._scanner_run_store().publish(manifest)
        return ScheduledScannerRun(intent=intent, published=published, sweeps=tuple(references))

    def _capture_scheduled_persistent_hop(
        self,
        intent: ScheduledScannerRunIntentV1,
        *,
        cancel: Event,
    ) -> ScheduledPersistentHopRun:
        configured = next(
            radio for radio in self.settings.radios if radio.radio_id == intent.radio_id
        )
        plan = compile_scheduled_persistent_hop_plan_v1(
            intent,
            transition_guard_us=self.settings.scanner_persistent_transition_guard_us,
            kernel_buffers=self.settings.scanner_persistent_kernel_buffers,
            samples_per_block=self.settings.scanner_persistent_samples_per_block,
        )
        session_id = f"scan-hop-{intent.intent_digest.removeprefix('sha256:')[:16]}"
        store = self._persistent_hop_iq_store()
        try:
            existing = store.verify(session_id)
        except BundleNotFoundError:
            pass
        else:
            receipt = existing.manifest.receipt
            if (
                existing.manifest.plan != plan
                or receipt.radio_id != configured.radio_id
                or receipt.radio_serial != intent.radio_serial
                or receipt.capture_outcome not in {"complete", "cancelled"}
            ):
                raise CliBackendError(
                    "persisted persistent-hop session disagrees with scheduled intent",
                    ExitCode.CONFLICT,
                )
            return ScheduledPersistentHopRun(intent=intent, published=existing)

        self._admit_persistent_hop_iq(plan)
        radio = self._persistent_hop_radio(configured)
        try:
            with self._authority().claim(
                (configured.radio_id,),
                task_id=session_id,
                task_kind=CaptureTaskKind.SCANNER_SWEEP,
            ):
                published = capture_persistent_hop_to_store(
                    radio,
                    plan,
                    session_id=session_id,
                    store=store,
                    cancel=cancel,
                    queue_capacity_visits=(
                        self.settings.scanner_persistent_queue_capacity_visits
                    ),
                )
        except CaptureAuthorityError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        return ScheduledPersistentHopRun(intent=intent, published=published)

    def analyze_scheduled_scanner(
        self,
        run: ScheduledScannerRun,
    ) -> ScheduledScannerRunAnalysis:
        reports: list[ScannerReportV2 | ScannerReportV3 | ScannerReportV4 | ScannerReportV5] = []
        for capture in run.sweeps:
            report = (
                run_published_standard_scanner_analysis(
                    self._scanner_iq_store(),
                    self._scanner_analysis_store(),
                    capture.iq_bundle,
                    capture_elapsed_ms=capture.capture_elapsed_ms,
                )
                if capture.iq_bundle is not None
                else capture.fallback_report
            )
            assert report is not None
            self._write_scheduled_scanner_report(capture.output_path, report)
            if not isinstance(
                report,
                (ScannerReportV2, ScannerReportV3, ScannerReportV4, ScannerReportV5),
            ):
                raise TypeError("scheduled scanner capture produced a legacy report")
            reports.append(report)
        return ScheduledScannerRunAnalysis(
            run_id=run.published.run_id,
            sweep_count=len(reports),
            active_edge_count=sum(len(report.active_edges) for report in reports),
            failed_sweep_count=sum(
                not report.continuity_observable
                for report in reports
                if isinstance(report, (ScannerReportV3, ScannerReportV4, ScannerReportV5))
            ),
        )

    def _publish_scheduled_scanner_sweep(
        self,
        captured,
        *,
        scan_id: str,
        output_path: Path,
    ) -> ScheduledScannerSweepReference:
        bundle = self._scanner_iq_store().publish(scan_id, captured)
        fallback = None if bundle is not None else analyze_scan_sweep(captured, scan_id=scan_id)
        if fallback is not None:
            self._write_scheduled_scanner_report(output_path, fallback)
        return ScheduledScannerSweepReference(
            scan_id=scan_id,
            output_path=output_path,
            capture_elapsed_ms=captured.capture_elapsed_ms,
            iq_bundle=bundle,
            fallback_report=fallback,
        )

    def _restore_scheduled_scanner_sweeps(
        self,
        manifest: ScannerRunManifestV1,
    ) -> tuple[ScheduledScannerSweepReference, ...]:
        references: list[ScheduledScannerSweepReference] = []
        for entry in manifest.sweeps:
            if (
                entry.report_filename is None
                or Path(entry.report_filename).name != entry.report_filename
            ):
                raise CliBackendError(
                    "persisted scanner run has an invalid report filename",
                    ExitCode.CONFLICT,
                )
            output_path = self.settings.scanner_report_root / entry.report_filename
            if entry.iq_bundle_uri is not None:
                bundle = self._scanner_iq_store().inspect(entry.scan_id)
                if (
                    bundle.uri != entry.iq_bundle_uri
                    or bundle.manifest_sha256 != entry.iq_manifest_sha256
                    or bundle.manifest.configuration != manifest.intent.configuration
                    or bundle.manifest.radio_id != manifest.intent.radio_id
                    or bundle.manifest.radio_serial != manifest.intent.radio_serial
                ):
                    raise CliBackendError(
                        "persisted scanner sweep disagrees with its run manifest",
                        ExitCode.CONFLICT,
                    )
                fallback: ScannerCaptureReportLike | None = None
            else:
                bundle = None
                fallback = self._read_scheduled_scanner_fallback(
                    output_path,
                    scan_id=entry.scan_id,
                    intent=manifest.intent,
                )
            references.append(
                ScheduledScannerSweepReference(
                    scan_id=entry.scan_id,
                    output_path=output_path,
                    capture_elapsed_ms=entry.capture_elapsed_ms,
                    iq_bundle=bundle,
                    fallback_report=fallback,
                )
            )
        return tuple(references)

    def _recover_scheduled_scanner_sweeps(
        self,
        intent: ScheduledScannerRunIntentV1,
        *,
        run_id: str,
        stamp: str,
        maximum_sweeps: int,
    ) -> tuple[ScheduledScannerSweepReference, ...]:
        recovered: list[ScheduledScannerSweepReference] = []
        for sweep_number in range(1, maximum_sweeps + 1):
            scan_id = f"scan-{run_id.removeprefix('scan-run-')}-{sweep_number:04d}"
            output_path = self._scheduled_scanner_report_path(stamp=stamp, scan_id=scan_id)
            try:
                bundle = self._scanner_iq_store().inspect(scan_id)
            except BundleNotFoundError:
                if not output_path.exists():
                    break
                fallback = self._read_scheduled_scanner_fallback(
                    output_path,
                    scan_id=scan_id,
                    intent=intent,
                )
                recovered.append(
                    ScheduledScannerSweepReference(
                        scan_id=scan_id,
                        output_path=output_path,
                        capture_elapsed_ms=fallback.capture_elapsed_ms,
                        iq_bundle=None,
                        fallback_report=fallback,
                    )
                )
                continue
            if bundle.manifest.configuration != intent.configuration:
                raise CliBackendError(
                    "orphaned scanner sweep disagrees with the scheduled intent",
                    ExitCode.CONFLICT,
                )
            if (
                bundle.manifest.radio_id != intent.radio_id
                or bundle.manifest.radio_serial != intent.radio_serial
            ):
                raise CliBackendError(
                    "orphaned scanner sweep has the wrong radio identity",
                    ExitCode.CONFLICT,
                )
            recovered.append(
                ScheduledScannerSweepReference(
                    scan_id=scan_id,
                    output_path=output_path,
                    capture_elapsed_ms=_persisted_scanner_capture_elapsed_ms(bundle),
                    iq_bundle=bundle,
                )
            )
        return tuple(recovered)

    def _read_scheduled_scanner_fallback(
        self,
        path: Path,
        *,
        scan_id: str,
        intent: ScheduledScannerRunIntentV1,
    ) -> ScannerReportV5:
        payload = path.read_bytes()
        if not 0 < len(payload) <= _MAX_SCANNER_REPORT_BYTES:
            raise CliBackendError(
                "persisted scanner fallback report is not bounded",
                ExitCode.CONFLICT,
            )
        try:
            report = ScannerReportV5.model_validate_json(payload)
        except Exception as error:
            raise CliBackendError(
                f"persisted scanner fallback report is invalid: {error}",
                ExitCode.CONFLICT,
            ) from error
        if (
            report.scan_id != scan_id
            or report.configuration != intent.configuration
            or report.radio_id != intent.radio_id
            or report.radio_serial != intent.radio_serial
        ):
            raise CliBackendError(
                "persisted scanner fallback report disagrees with the scheduled intent",
                ExitCode.CONFLICT,
            )
        return report

    @staticmethod
    def _write_scheduled_scanner_report(
        path: Path,
        report: ScannerCaptureReportLike,
    ) -> None:
        try:
            write_scanner_report(path, report)
        except FileExistsError:
            try:
                existing = json.loads(path.read_bytes())
            except Exception as error:
                raise ValueError("existing scanner report is invalid") from error
            if existing != report.model_dump(mode="json"):
                raise ValueError(
                    "existing scanner report disagrees with regenerated analysis"
                ) from None

    def _scheduled_scanner_report_path(self, *, stamp: str, scan_id: str) -> Path:
        return self.settings.scanner_report_root / f"starlink-scan-{stamp}-{scan_id}.json"

    def qualify(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        qualification_id: str | None,
        trial_count: int,
        receipt_path: Path | None,
        policy: AcquisitionAcceptancePolicyV1,
        resume: bool,
        cancel: Event,
    ) -> AcquisitionQualificationReceiptV1:
        shown = self.profiles.show(profile_name)
        selected, configured = self._selected_radios(radio_ids)
        source_type = SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
        plan = compile_capture_plan(shown.revision, selected, source_type=source_type)
        store = self._recording_store()
        coordinator = AcquisitionCoordinator(
            store,
            producer=self._acquisition_producer(),
            config=AcquisitionConfig(
                safety_reserve_bytes=self.settings.safety_reserve_bytes,
            ),
            storage_admission=self._capture_storage_admission,
        )
        identifier = qualification_id or f"qual-{uuid4().hex[:16]}"
        destination = receipt_path or (
            store.root / "qualification" / "acquisition" / f"{identifier}.json"
        )
        harness = AcquisitionQualificationHarness(
            store,
            AuthorizedAcquisitionApplication(
                AcquisitionApplication(coordinator),
                self._authority(),
                CaptureTaskKind.QUALIFICATION,
            ),
        )
        receipt = harness.run(
            plan,
            lambda radio_id: self._radio_source(configured[radio_id]),
            qualification_id=identifier,
            trial_count=trial_count,
            receipt_path=destination,
            cancel=cancel,
            policy=policy,
            resume=resume,
        )
        if any(trial.bundle_uri is not None for trial in receipt.trials):
            self._post_commit_registration()
        return receipt

    def accept_capture_modes(
        self,
        profile_name: str,
        *,
        radio_ids: tuple[str, str],
        acceptance_id: str,
        independent_radio_a_session_ids: tuple[str, ...],
        independent_radio_b_session_ids: tuple[str, ...],
        synchronized_pair_session_ids: tuple[str, ...],
        receipt_path: Path | None,
    ) -> CaptureModeCampaignAcceptanceReceiptV2:
        expected_ids = tuple(item[0] for item in _CAPTURE_MODE_RADIO_CONFIG)
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        if self.settings.radio_backend != "pluto" or radio_ids != expected_ids:
            raise CliBackendError(
                "capture-mode campaign requires the two fixed production Pluto radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        for radio_id, serial, host in _CAPTURE_MODE_RADIO_CONFIG:
            radio = configured.get(radio_id)
            if (
                radio is None
                or radio.serial != serial
                or radio.host != host
                or radio.receiver_count != 2
            ):
                raise CliBackendError(
                    f"capture-mode campaign configuration does not attest {radio_id}",
                    ExitCode.INVALID_CONFIGURATION,
                )
        shown = self.profiles.show(profile_name)
        if isinstance(shown, ProfileShowDataV2):
            raise CliBackendError(
                "capture-mode campaign V1 does not accept a continuity V2 profile",
                ExitCode.INVALID_CONFIGURATION,
            )
        expectation = CaptureModeExpectationV1.from_hardware_profile_revision(
            shown.revision,
            radio_ids,
        )
        harness = CaptureModeAcceptanceHarness.open_read_only(self.settings.bulk_root)
        return harness.run_campaign(
            expectation,
            acceptance_id=acceptance_id,
            independent_radio_a_session_ids=independent_radio_a_session_ids,
            independent_radio_b_session_ids=independent_radio_b_session_ids,
            synchronized_pair_session_ids=synchronized_pair_session_ids,
            receipt_path=receipt_path,
        )

    def benchmark_writer(
        self,
        *,
        benchmark_id: str | None,
        receipt_path: Path | None,
        configuration: WriterBenchmarkConfigV1,
        resume: bool,
        cancel: Event,
    ) -> WriterBenchmarkReceiptV1:
        store = self._recording_store()
        identifier = benchmark_id or f"writer-{uuid4().hex[:16]}"
        destination = receipt_path or (
            store.root / "qualification" / "writer" / f"{identifier}.json"
        )
        return WriterThroughputBenchmark(store).run(
            benchmark_id=identifier,
            receipt_path=destination,
            configuration=configuration,
            cancel=cancel,
            resume=resume,
        )

    def soak(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        soak_id: str | None,
        output_root: Path | None,
        configuration: SoakConfigV1,
        resume: bool,
        cancel: Event,
    ) -> SoakSummaryV1:
        shown = self.profiles.show(profile_name)
        selected, configured = self._selected_radios(radio_ids)
        source_type = SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
        plan = compile_capture_plan(shown.revision, selected, source_type=source_type)
        store = self._recording_store()
        coordinator = AcquisitionCoordinator(
            store,
            producer=self._acquisition_producer(),
            config=AcquisitionConfig(
                safety_reserve_bytes=self.settings.safety_reserve_bytes,
            ),
            storage_admission=self._capture_storage_admission,
        )
        identifier = soak_id or f"soak-{uuid4().hex[:16]}"
        harness = AcquisitionSoakHarness(
            store,
            AuthorizedAcquisitionApplication(
                AcquisitionApplication(coordinator),
                self._authority(),
                CaptureTaskKind.SOAK,
            ),
            output_root=output_root or store.root / "qualification" / "soak",
            backlog_observer=self._soak_backlog_observation,
            post_commit_observer=self._soak_post_commit_observation,
        )
        summary = harness.run(
            plan,
            lambda radio_id: self._radio_source(configured[radio_id]),
            soak_id=identifier,
            configuration=configuration,
            policy=SoakAcceptancePolicyV1(
                maximum_post_commit_failure_count=(
                    0
                    if self.settings.database_url
                    or self.hooks.processing_backend_factory is not None
                    else None
                )
            ),
            cancel=cancel,
            resume=resume,
        )
        if summary.completed_trial_count:
            self._post_commit_registration()
        return summary

    def audit_soak(
        self,
        evidence: str,
        *,
        database_url: str | None,
        receipt_path: Path | None,
        runtime_evidence_path: Path | None,
    ) -> SoakAcceptanceAuditReceiptV1:
        configured_url = database_url or self.settings.database_url
        if configured_url is None:
            raise CliBackendError(
                "soak acceptance audit requires --database-url or LEO_DATABASE_URL",
                ExitCode.INVALID_CONFIGURATION,
            )
        evidence_directory = resolve_soak_evidence(evidence, bulk_root=self.settings.bulk_root)
        auditor = FinalSoakAcceptanceAuditor.from_paths(
            bulk_root=self.settings.bulk_root,
            database_url=configured_url,
            runtime_evidence_path=runtime_evidence_path,
        )
        return auditor.audit(evidence_directory, receipt_path=receipt_path)

    def capture_soak_runtime(
        self, soak_id: str, *, output_path: Path
    ) -> RuntimeContinuityEvidenceV1:
        return capture_systemd_runtime_continuity(soak_id, output_path)

    def search_sessions(
        self,
        *,
        query: str | None = None,
        source_type: str | None,
        state: str | None,
        tag: str | None,
        held: bool | None,
        created_after: datetime | None,
        created_before: datetime | None,
        cursor: int = 0,
        limit: int,
    ) -> SessionSearchDataV1:
        return self._processing().search_sessions(
            query=query,
            source_type=source_type,
            state=state,
            tag=tag,
            held=held,
            created_after=created_after,
            created_before=created_before,
            cursor=cursor,
            limit=limit,
        )

    def show_session(self, session_id: str) -> SessionDetailDataV1:
        return self._processing().show_session(session_id)

    def session_paths(self, session_id: str) -> SessionPathsDataV1:
        return self._processing().session_paths(session_id)

    def reprocess(self, session_id: str, *, dry_run: bool = False) -> ReprocessDataV1:
        return self._processing().reprocess(session_id, dry_run=dry_run)

    def native_evidence(
        self,
        session_id: str,
        *,
        pipeline_release_id: str,
        dry_run: bool = False,
    ) -> NativeEvidenceReprocessDataV1:
        return self._processing().native_evidence(
            session_id,
            pipeline_release_id=pipeline_release_id,
            dry_run=dry_run,
        )

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1:
        return self._processing().cancel_run(run_id, reason=reason)

    def stop_and_fence(
        self,
        *,
        operation_id: str,
        pipeline_release_id: str,
        operator_id: str,
        reason: str,
        expected_run_ids: tuple[str, ...] | None,
        allow_current_release: bool,
    ) -> StopAndFenceDataV1:
        return self._processing().stop_and_fence(
            operation_id=operation_id,
            pipeline_release_id=pipeline_release_id,
            operator_id=operator_id,
            reason=reason,
            expected_run_ids=expected_run_ids,
            allow_current_release=allow_current_release,
        )

    def jobs(self) -> JobsDataV1:
        return self._processing().jobs()

    def pin(self, session_id: str, *, reason: str) -> HoldDataV1:
        return self._processing().pin(session_id, reason=reason)

    def unpin(self, session_id: str) -> HoldDataV1:
        return self._processing().unpin(session_id)

    def import_qnap(
        self,
        manifest_path: Path,
        *,
        copy: bool,
        tags: tuple[str, ...],
    ) -> ImportDataV1:
        return self._processing().import_qnap(manifest_path, copy=copy, tags=tags)

    def retention_status(self) -> RetentionDataV1:
        return self._processing().retention_status()

    def storage_admission(self) -> StorageAdmissionDecision:
        return self._processing().storage_admission()

    def retention_run(self, *, dry_run: bool) -> RetentionDataV1:
        return self._processing().retention_run(dry_run=dry_run)

    def reconcile(self) -> ReconcileDataV1:
        return self._processing().reconcile()

    def reconcile_session(self, session_id: str) -> ReconcileDataV1:
        return self._processing().reconcile_session(session_id)

    def worker(
        self,
        *,
        worker_id: str,
        poll_seconds: float,
        maximum_jobs: int | None,
        once: bool,
        cancel: Event,
    ) -> WorkerDataV1:
        return self._processing().worker(
            worker_id=worker_id,
            poll_seconds=poll_seconds,
            maximum_jobs=maximum_jobs,
            once=once,
            cancel=cancel,
        )

    def calibration_predeclare(
        self,
        *,
        plan_id: str,
        radio_id: str,
        scheduled_session_ids: tuple[str, ...],
        starlink_channel: Literal["ch4"],
        starlink_edge: Literal["lower"],
    ) -> CalibrationPredeclareDataV1:
        return self._calibration().calibration_predeclare(
            plan_id=plan_id,
            radio_id=radio_id,
            scheduled_session_ids=scheduled_session_ids,
            starlink_channel=starlink_channel,
            starlink_edge=starlink_edge,
        )

    def calibration_queue(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
    ) -> CalibrationQueueDataV1:
        return self._calibration().calibration_queue(
            plan_uri=plan_uri,
            plan_digest=plan_digest,
        )

    def calibration_promote(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
        promotion_id: str,
        calibration_id: str,
        calibration_set_id: str,
        valid_until_utc_ns: int | None,
    ) -> CalibrationPromoteDataV1:
        return self._calibration().calibration_promote(
            plan_uri=plan_uri,
            plan_digest=plan_digest,
            promotion_id=promotion_id,
            calibration_id=calibration_id,
            calibration_set_id=calibration_set_id,
            valid_until_utc_ns=valid_until_utc_ns,
        )

    def calibration_show(self, promotion_id: str) -> CalibrationShowDataV1:
        return self._calibration().calibration_show(promotion_id)

    def wp11_create(
        self,
        *,
        campaign_id: str,
        capture_uri: str,
        capture_digest: str,
        config_path: Path,
    ) -> WP11CreateDataV1:
        return self._wp11().wp11_create(
            campaign_id=campaign_id,
            capture_uri=capture_uri,
            capture_digest=capture_digest,
            config_path=config_path,
        )

    def wp11_config(self, *, output_path: Path) -> WP11ConfigDataV1:
        return self._wp11().wp11_config(output_path=output_path)

    def wp11_queue(self, campaign_id: str) -> WP11QueueDataV1:
        return self._wp11().wp11_queue(campaign_id)

    def wp11_legacy(
        self,
        campaign_id: str,
        *,
        ordinals: tuple[int, ...],
    ) -> WP11LegacyDataV1:
        return self._wp11().wp11_legacy(campaign_id, ordinals=ordinals)

    def wp11_finalize(self, campaign_id: str) -> WP11FinalizeDataV1:
        return self._wp11().wp11_finalize(campaign_id)

    def wp11_show(self, campaign_id: str) -> WP11ShowDataV1:
        return self._wp11().wp11_show(campaign_id)

    def _wp11(self) -> WP11CliBackend:
        if self._wp11_backend is not None:
            return self._wp11_backend
        if self.hooks.wp11_backend_factory is not None:
            self._wp11_backend = self.hooks.wp11_backend_factory(self.settings)
            return self._wp11_backend
        if not self.settings.database_url:
            raise CliBackendError(
                "LEO_DATABASE_URL is required for WP11 commands",
                ExitCode.INVALID_CONFIGURATION,
            )
        from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
        from leo.application.frequency_calibration import (
            NativeReleaseCalibrationEvidenceAdapter,
        )
        from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
        from leo.application.trusted_campaign_production import (
            TrustedCampaignProductionSettings,
            open_trusted_campaign_service,
        )
        from leo.application.trusted_matched_recovery import (
            PostgresAuthoritativeCalibrationScope,
        )
        from leo.application.wp11_legacy import WP11LegacyOracleCampaignRunner
        from leo.application.wp11_operations import WP11Operations
        from leo.application.wp11_production import WP11ProductionWorkflow
        from leo.cli.processing import LocalProcessingBackend
        from leo.qualification.frequency_calibration_store import (
            AuthoritativeCalibrationResolver,
            ImmutableCalibrationPromotionStore,
        )
        from leo.qualification.native_release import _normalized_absolute
        from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
        from leo.storage import PinnedLocalRoot

        processing = self._processing()
        if not isinstance(processing, LocalProcessingBackend):
            raise CliBackendError(
                "WP11 requires concrete PostgreSQL processing services",
                ExitCode.INVALID_CONFIGURATION,
            )
        for label, root in (
            ("bulk", self.settings.bulk_root),
            ("qualification", self.settings.qualification_root),
            ("capture evidence", self.settings.capture_evidence_root),
            ("legacy evidence", self.settings.legacy_evidence_root),
        ):
            _normalized_absolute(root, f"WP11 {label} root")
        qualification = PinnedLocalRoot(self.settings.qualification_root)
        capture_root = PinnedLocalRoot(self.settings.capture_evidence_root)
        legacy_root = PinnedLocalRoot(self.settings.legacy_evidence_root)
        bulk = PinnedLocalRoot(self.settings.bulk_root)
        try:
            plans = ImmutableWP11PlanStore(qualification)
            capture = ImmutableCaptureCampaignAuthority(capture_root)
            spool = bulk.child("spool")
            calibration_root = qualification.child("frequency-calibration-promotions")
        finally:
            qualification.close()
            capture_root.close()
            bulk.close()
        release_settings = TrustedCampaignProductionSettings(
            database_url=self.settings.database_url,
            bulk_root=self.settings.bulk_root,
            qualification_root=self.settings.qualification_root,
            capture_evidence_root=self.settings.capture_evidence_root,
            legacy_evidence_root=self.settings.legacy_evidence_root,
            pipeline_release_id=self.settings.pipeline_release_id,
        )
        releases = NativeReleaseCalibrationEvidenceAdapter(
            self.settings.pipeline_release_id,
            current_link=release_settings.current_release_link,
            deployment_root=release_settings.deployment_root,
        )
        calibration_store = ImmutableCalibrationPromotionStore.open_pinned(calibration_root)
        calibration_root.close()
        calibration_resolver = AuthoritativeCalibrationResolver(
            calibration_store,
            releases,
            allowed_release_ids=(self.settings.pipeline_release_id,),
        )
        scopes = PostgresAuthoritativeCalibrationScope(
            processing.services.catalog,
            processing.services.recordings,
            PostgresCalibrationCatalogAdapter(
                processing.services.catalog,
                calibration_resolver,
            ),
        )
        trusted = open_trusted_campaign_service(release_settings)
        self._wp11_backend = WP11CliBackend(
            WP11Operations(
                WP11ProductionWorkflow(
                    plans=plans,
                    capture=capture,
                    catalog=processing.services.catalog,
                    processing=processing.services.processing,
                    trusted=trusted,
                    pipeline_release_id=self.settings.pipeline_release_id,
                )
            ),
            legacy=WP11LegacyOracleCampaignRunner(
                plans=plans,
                capture=capture,
                scopes=scopes,
                recordings=processing.services.recordings,
                spool=spool,
                evidence_root=legacy_root,
                pipeline_release_id=self.settings.pipeline_release_id,
            ),
            releases=releases,
        )
        spool.close()
        legacy_root.close()
        return self._wp11_backend

    def _calibration(self) -> CalibrationCliBackend:
        if self._calibration_backend is None:
            if self.hooks.calibration_backend_factory is not None:
                self._calibration_backend = self.hooks.calibration_backend_factory(self.settings)
            else:
                if not self.settings.database_url:
                    raise CliBackendError(
                        "LEO_DATABASE_URL is required for calibration commands",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                from leo.cli.calibration import (
                    CalibrationBackendSettings,
                    build_postgres_calibration_backend,
                )
                from leo.cli.processing import LocalProcessingBackend

                processing = self._processing()
                if not isinstance(processing, LocalProcessingBackend):
                    raise CliBackendError(
                        "calibration requires concrete PostgreSQL processing services",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                self._calibration_backend = build_postgres_calibration_backend(
                    CalibrationBackendSettings(
                        qualification_root=self.settings.qualification_root,
                        bulk_root=self.settings.bulk_root,
                        pipeline_release_id=self.settings.pipeline_release_id,
                    ),
                    services=processing.services,
                )
        return self._calibration_backend

    def _processing(self) -> ProcessingCliBackend:
        if self._processing_backend is None:
            if self.hooks.processing_backend_factory is not None:
                self._processing_backend = self.hooks.processing_backend_factory(self.settings)
            else:
                if not self.settings.database_url:
                    raise CliBackendError(
                        "LEO_DATABASE_URL is required for process commands",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                from leo.cli.processing import (
                    ProcessingBackendSettings,
                    build_processing_backend,
                )

                self._processing_backend = build_processing_backend(
                    ProcessingBackendSettings(
                        database_url=self.settings.database_url,
                        bulk_root=self.settings.bulk_root,
                        corpus_root=(
                            self.settings.corpus_root
                            if self.settings.corpus_root is not None
                            else self.settings.bulk_root / "test-corpus"
                        ),
                        pipeline_release_id=self.settings.pipeline_release_id,
                        qualification_root=self.settings.qualification_root,
                        legacy_evidence_root=self.settings.legacy_evidence_root,
                        capture_evidence_root=self.settings.capture_evidence_root,
                        station_authority_root=self.settings.station_authority_root,
                        station_topology_relative_path=(
                            self.settings.station_topology_relative_path
                        ),
                        station_topology_file_digest=(self.settings.station_topology_file_digest),
                        fixture_authorities=self.settings.fixture_authorities,
                    )
                )
        return self._processing_backend

    def _acquisition_operation_catalog(self) -> CatalogRepository:
        if self._acquisition_operations is None:
            if not self.settings.database_url:
                raise CliBackendError(
                    "LEO_DATABASE_URL is required for durable acquisition scheduling",
                    ExitCode.INVALID_CONFIGURATION,
                )
            engine = create_catalog_engine(self.settings.database_url)
            self._acquisition_operations = CatalogRepository(create_session_factory(engine))
        return self._acquisition_operations

    def _capture_storage_admission(self, _root: Path) -> StorageAdmissionDecision:
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return StorageAdmissionDecision(allowed=True)
        try:
            return self._processing().storage_admission()
        except Exception as error:
            return StorageAdmissionDecision(
                allowed=True,
                warning=True,
                reason=(
                    "catalog-backed retention admission is unavailable; "
                    f"free-byte admission only ({type(error).__name__}: {error})"
                ),
            )

    def _soak_backlog_observation(self) -> ProcessingBacklogObservationV1:
        observed_utc_ns = time.time_ns()
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return ProcessingBacklogObservationV1(
                observed_utc_ns=observed_utc_ns,
                available=False,
                error="processing backlog observer is not configured",
            )
        jobs = self._processing().jobs()
        return ProcessingBacklogObservationV1(
            observed_utc_ns=observed_utc_ns,
            queued=jobs.queued,
            running=jobs.running,
            failed=jobs.failed,
            oldest_queued_seconds=jobs.oldest_queued_seconds,
        )

    def _soak_post_commit_observation(
        self,
        bundle: PublishedBundle,
    ) -> PostCommitObservationV1:
        observed_utc_ns = time.time_ns()
        if "QUALIFICATION" in bundle.manifest.tags:
            raise ValueError(
                "soak recording unexpectedly has QUALIFICATION tag and would be skipped"
            )
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return PostCommitObservationV1(
                observed_utc_ns=observed_utc_ns,
                target_session_id=bundle.session_id,
                attempted=False,
                succeeded=False,
                error="catalog registration is not configured",
            )
        try:
            result = self._processing().reconcile_session(bundle.session_id)
            if result.issues:
                raise RuntimeError("; ".join(result.issues))
            known = (
                bundle.session_id in result.registered_sessions
                or bundle.session_id in result.existing_sessions
            )
            if not known:
                raise RuntimeError("reconciliation did not report the target soak recording")
            if bundle.session_id in result.registered_sessions and not result.queued_run_ids:
                raise RuntimeError("new soak recording did not queue an analysis run")
        except Exception as error:
            warning = (
                "recording committed locally but per-trial catalog registration failed: "
                f"{type(error).__name__}: {error}"
            )
            self._write_registration_warning(warning)
            raise
        self._write_registration_warning(None)
        return PostCommitObservationV1(
            observed_utc_ns=observed_utc_ns,
            target_session_id=bundle.session_id,
            attempted=True,
            succeeded=True,
            registered_session_ids=result.registered_sessions,
            existing_session_ids=result.existing_sessions,
            queued_run_ids=result.queued_run_ids,
        )

    def _post_commit_registration(self, session_id: str | None = None) -> str | None:
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return None
        try:
            processing = self._processing()
            result = (
                processing.reconcile()
                if session_id is None
                else processing.reconcile_session(session_id)
            )
            if result.issues:
                raise RuntimeError("; ".join(result.issues))
        except Exception as error:
            warning = (
                "recording committed locally but catalog registration is pending: "
                f"{type(error).__name__}: {error}"
            )
            self._write_registration_warning(warning)
            return warning
        self._write_registration_warning(None)
        return None

    def _registration_warning_path(self) -> Path:
        control = self._recording_store().root / "control"
        control.mkdir(exist_ok=True)
        return control / "catalog-registration-warning.txt"

    def _write_registration_warning(self, warning: str | None) -> None:
        destination = self._registration_warning_path()
        if warning is None:
            destination.unlink(missing_ok=True)
            return
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}-{uuid4().hex}.partial"
        )
        with temporary.open("xb") as stream:
            stream.write(warning.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)

    def _read_registration_warning(self) -> str | None:
        path = self._registration_warning_path()
        try:
            return path.read_text(encoding="utf-8") if path.exists() else None
        except OSError:
            return "catalog registration warning status is unreadable"

    def _recording_store(self) -> RecordingStore:
        if self._store is None:
            self._store = self.hooks.recording_store_factory(self.settings.bulk_root)
        return self._store

    def _acquisition_producer(self) -> ProducerV1:
        """Bind every native recording to the configured deployment revision."""

        return ProducerV1(
            name="leo-acquisition",
            version=__version__,
            source_revision=(
                self.settings.acquisition_release_id or self.settings.pipeline_release_id
            ),
        )

    def _scanner_iq_store(self) -> ScannerIqStore:
        if self._scanner_iq is None:
            self._scanner_iq = self.hooks.scanner_iq_store_factory(self.settings.bulk_root)
        return self._scanner_iq

    def _scanner_analysis_store(self) -> ScannerAnalysisStore:
        if self._scanner_analysis is None:
            self._scanner_analysis = self.hooks.scanner_analysis_store_factory(
                self.settings.bulk_root
            )
        return self._scanner_analysis

    def _scanner_run_store(self) -> ScannerRunStore:
        if self._scanner_runs is None:
            self._scanner_runs = self.hooks.scanner_run_store_factory(self.settings.bulk_root)
        return self._scanner_runs

    def _persistent_hop_iq_store(self) -> PersistentHopIqStore:
        if self._persistent_hop_store is None:
            self._persistent_hop_store = self.hooks.persistent_hop_store_factory(
                self.settings.bulk_root
            )
        return self._persistent_hop_store

    def _admit_persistent_hop_iq(self, plan: PersistentHopPlanV1) -> None:
        # Admit against the uncompressed upper bound. RF is never opened on a
        # speculative compression ratio.
        raw_iq_bytes = (
            plan.nominal_device_sample_count * len(plan.receiver_ids) * 4
        )
        required_free_bytes = raw_iq_bytes + self.settings.safety_reserve_bytes
        available_free_bytes = max(0, int(shutil.disk_usage(self.settings.bulk_root).free))
        policy = self._capture_storage_admission(self.settings.bulk_root)
        if available_free_bytes >= required_free_bytes and policy.allowed:
            return
        policy_detail = f"; {policy.reason}" if policy.reason is not None else ""
        raise CliBackendError(
            "persistent-hop IQ storage admission rejected: "
            f"need {required_free_bytes} free bytes, have {available_free_bytes}"
            f"{policy_detail}",
            ExitCode.ADMISSION_REJECTED,
        )

    def _admit_scanner_iq(
        self, configuration: ScannerConfiguration, *, scan_count: int = 1
    ) -> None:
        raw_iq_bytes = (
            configuration.dwell_samples
            * len(configuration.receiver_ids)
            * 4
            * len(configuration.targets)
        )
        required_free_bytes = raw_iq_bytes * scan_count + self.settings.safety_reserve_bytes
        available_free_bytes = max(0, int(shutil.disk_usage(self.settings.bulk_root).free))
        policy = self._capture_storage_admission(self.settings.bulk_root)
        if available_free_bytes >= required_free_bytes and policy.allowed:
            return
        policy_detail = f"; {policy.reason}" if policy.reason is not None else ""
        raise CliBackendError(
            "scanner IQ storage admission rejected: "
            f"need {required_free_bytes} free bytes, have {available_free_bytes}"
            f"{policy_detail}",
            ExitCode.ADMISSION_REJECTED,
        )

    def _authority(self) -> LocalCaptureAuthority:
        if self._capture_authority is None:
            resources = tuple(
                RadioResource(
                    radio_id=radio.radio_id,
                    serial=radio.serial,
                    endpoint=(
                        f"ip:{radio.host}"
                        if self.settings.radio_backend == "pluto"
                        else f"fake:{radio.radio_id}"
                    ),
                )
                for radio in self.settings.radios
            )
            self._capture_authority = LocalCaptureAuthority(
                self.settings.bulk_root / "control",
                resources,
            )
        return self._capture_authority

    def _radio_source(self, configuration: RadioConfigurationV1) -> RadioSource:
        if self.hooks.radio_source_factory is not None:
            return self.hooks.radio_source_factory(configuration)
        if self.settings.radio_backend == "fake":
            return FakeRadioSource(
                configuration.radio_id,
                receiver_count=configuration.receiver_count,
            )
        assert configuration.host is not None
        return PlutoIioRadioSource(
            configuration.host,
            expected_serial=configuration.serial or configuration.radio_id,
            radio_id=configuration.radio_id,
        )

    def _scanner_radio(self, configuration: RadioConfigurationV1) -> SequentialScanRadioLike:
        if self.hooks.scanner_radio_factory is not None:
            return self.hooks.scanner_radio_factory(configuration)
        if self.settings.radio_backend != "pluto" or configuration.host is None:
            raise CliBackendError(
                "scanner requires a configured Pluto radio",
                ExitCode.INVALID_CONFIGURATION,
            )
        return PlutoSequentialScanRadio(
            configuration.host,
            expected_serial=configuration.serial or configuration.radio_id,
            radio_id=configuration.radio_id,
        )

    def _persistent_hop_radio(
        self,
        configuration: RadioConfigurationV1,
    ) -> PersistentHopRadio:
        if self.hooks.persistent_hop_radio_factory is not None:
            return self.hooks.persistent_hop_radio_factory(configuration)
        if (
            self.settings.radio_backend != "pluto"
            or configuration.host is None
            or configuration.serial is None
        ):
            raise CliBackendError(
                "persistent hopping requires an exact Ethernet Pluto configuration",
                ExitCode.INVALID_CONFIGURATION,
            )
        return PlutoPersistentHopRadio(
            configuration.host,
            expected_serial=configuration.serial,
            radio_id=configuration.radio_id,
        )

    def _selected_radios(
        self,
        radio_ids: Sequence[str],
    ) -> tuple[tuple[str, ...], dict[str, RadioConfigurationV1]]:
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        selected = tuple(radio_ids) if radio_ids else tuple(configured)
        if not selected:
            raise CliBackendError(
                "no acquisition radios are configured or selected",
                ExitCode.INVALID_CONFIGURATION,
            )
        if len(selected) > 2 or len(set(selected)) != len(selected):
            raise CliBackendError(
                "select one or two unique configured radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        unknown = tuple(radio_id for radio_id in selected if radio_id not in configured)
        if unknown:
            raise CliBackendError(
                f"selected radios are not configured: {unknown}",
                ExitCode.INVALID_CONFIGURATION,
            )
        return selected, configured

    def _status_path(self) -> Path:
        control = self._recording_store().root / "control"
        control.mkdir(exist_ok=True)
        return control / "last-capture.json"

    def _write_last_capture(self, capture: CaptureDataV1) -> None:
        destination = self._status_path()
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}-{uuid4().hex}.partial"
        )
        payload = capture.model_dump_json().encode("utf-8")
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)

    def _read_last_capture(self) -> CaptureDataV1 | None:
        path = self._status_path()
        if not path.exists():
            return None
        try:
            return CaptureDataV1.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None


def default_backend_factory() -> CliBackend:
    return LocalAcquisitionBackend(CliSettings.from_environ())


def configured_backend_factory(
    settings: CliSettings,
    hooks: CompositionHooks | None = None,
) -> BackendFactory:
    """Return a lazy factory suitable for tests and production composition roots."""

    return lambda: LocalAcquisitionBackend(settings, hooks)


def _capture_data(
    profile_name: str,
    radio_ids: tuple[str, ...],
    result: CaptureSessionResult,
) -> CaptureDataV1:
    bundle = result.bundle
    return CaptureDataV1(
        session_id=result.session_id,
        state=result.state,
        bundle_uri=None if bundle is None else bundle.uri,
        manifest_sha256=None if bundle is None else bundle.manifest_sha256,
        radio_ids=radio_ids,
        profile_name=profile_name,
        raw_iq_bytes=result.admission.raw_iq_bytes,
        required_free_bytes=result.admission.required_free_bytes,
        available_free_bytes=result.admission.available_free_bytes,
        storage_used_fraction=result.admission.storage_used_fraction,
        storage_warning=result.admission.storage_warning,
        admission_reason=result.admission.policy_reason,
        errors=result.errors,
        stream_coverage=tuple(
            CaptureStreamCoverageV1(
                radio_id=coverage.radio_id,
                stream_id=coverage.stream_id,
                delivery_unit=coverage.delivery_unit,
                delivered_units=coverage.delivered_units,
                requested_units=coverage.requested_units,
                delivery_coverage_pct=coverage.delivery_coverage_pct,
                observed_samples=coverage.observed_samples,
                logical_samples=coverage.logical_samples,
                observed_density_pct=coverage.observed_density_pct,
                in_segment_density_pct=coverage.in_segment_density_pct,
                transport_density_pct=coverage.transport_density_pct,
            )
            for coverage in result.stream_coverage
        ),
    )


def _failed_check(name: str, error: Exception) -> DoctorCheckV1:
    return DoctorCheckV1(
        name=name,
        state=CheckState.FAIL,
        detail=f"{type(error).__name__}: {error}",
    )
