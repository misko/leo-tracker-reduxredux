"""Durable capture admission and crash-safe host-local radio leases."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event, Thread
from types import TracebackType

from leo.acquisition.errors import AcquisitionSupervisorPoisoned
from leo.acquisition.service import AcquisitionApplication
from leo.contracts.capture_control import (
    CaptureControlStateV1,
    CaptureDesiredState,
    CaptureObservedState,
)
from leo.contracts.mixed_rate_capture import CapturePlanV3
from leo.contracts.profile import CapturePlanV1
from leo.contracts.radio import RadioSettingsV1
from leo.radio.ports import RadioSource


class CaptureTaskKind(StrEnum):
    SCHEDULED_RECORDING = "scheduled_recording"
    SCANNER_SWEEP = "scanner_sweep"
    OPERATOR_ONCE = "operator_once"
    QUALIFICATION = "qualification"
    SOAK = "soak"
    RADIO_PROBE = "radio_probe"


class CaptureAuthorityError(RuntimeError):
    pass


class CapturePausedError(CaptureAuthorityError):
    pass


class RadioBusyError(CaptureAuthorityError):
    pass


class UnknownRadioError(CaptureAuthorityError):
    pass


@dataclass(frozen=True, slots=True)
class RadioResource:
    radio_id: str
    serial: str | None
    endpoint: str

    @property
    def physical_key(self) -> str:
        # One physical radio may be reachable through multiple endpoint aliases.
        # Its hardware serial remains authoritative whenever one is configured.
        return f"serial:{self.serial}" if self.serial is not None else f"endpoint:{self.endpoint}"

    @property
    def lock_name(self) -> str:
        digest = hashlib.sha256(self.physical_key.encode()).hexdigest()
        return f"radio-{digest}.lock"


class RadioLease:
    """Capability proving exclusive ownership of an exact radio set."""

    def __init__(
        self,
        *,
        radio_ids: tuple[str, ...],
        task_id: str,
        task_kind: CaptureTaskKind,
        descriptors: tuple[int, ...],
    ) -> None:
        self.radio_ids = radio_ids
        self.task_id = task_id
        self.task_kind = task_kind
        self._descriptors = descriptors

    @property
    def released(self) -> bool:
        return not self._descriptors

    def release(self) -> None:
        descriptors, self._descriptors = self._descriptors, ()
        for descriptor in reversed(descriptors):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def __enter__(self) -> RadioLease:
        return self

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.release()


class LocalCaptureAuthority:
    """Own capture pause state and kernel-enforced locks beneath local bulk storage."""

    def __init__(
        self,
        control_root: Path,
        resources: tuple[RadioResource, ...],
        *,
        utc_ns=time.time_ns,
        monotonic=time.monotonic,
        wait=time.sleep,
    ) -> None:
        if not control_root.is_absolute():
            raise ValueError("capture control root must be absolute")
        if str(control_root).startswith("/mnt/qnap01/") or control_root == Path("/mnt/qnap01"):
            raise ValueError("capture control cannot use QNAP")
        control_root.mkdir(parents=True, exist_ok=True)
        if control_root.is_symlink() or not control_root.is_dir():
            raise ValueError("capture control root must be a real directory")
        self.root = control_root.resolve(strict=True)
        self.lock_root = self.root / "radio-locks"
        self.lock_root.mkdir(mode=0o700, exist_ok=True)
        if self.lock_root.is_symlink() or not self.lock_root.is_dir():
            raise ValueError("radio lock root must be a real directory")
        by_id = {item.radio_id: item for item in resources}
        if len(by_id) != len(resources):
            raise ValueError("radio resource IDs must be unique")
        physical = tuple(item.physical_key for item in resources)
        if len(set(physical)) != len(physical):
            raise ValueError("multiple radio IDs cannot name the same physical radio")
        self._resources = by_id
        self._ordered_resources = tuple(sorted(resources, key=lambda item: item.physical_key))
        self._global_radio_lock_path = self.lock_root / "acquisition-global-radio-owner.lock"
        self._state_path = self.root / "capture-authority-v1.json"
        self._control_lock_path = self.root / "capture-authority.lock"
        self._utc_ns = utc_ns
        self._monotonic = monotonic
        self._wait = wait
        with self._control_lock():
            if not self._state_path.exists():
                self._write_state(
                    CaptureControlStateV1(
                        generation=0,
                        desired_state=CaptureDesiredState.RUNNING,
                        observed_state=CaptureObservedState.RUNNING,
                        changed_utc_ns=self._utc_ns(),
                        operator_id="system",
                        reason="initial capture authority state",
                    )
                )
            else:
                self._read_state()

    @property
    def radio_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._resources))

    def snapshot(self) -> CaptureControlStateV1:
        with self._control_lock():
            current = self._read_state()
            if (
                current.desired_state is CaptureDesiredState.PAUSED
                and current.observed_state is CaptureObservedState.PAUSING
            ):
                descriptors = self._try_lock(self._ordered_resources)
                if descriptors is not None:
                    try:
                        current = current.model_copy(
                            update={
                                "observed_state": CaptureObservedState.PAUSED,
                                "changed_utc_ns": self._utc_ns(),
                            }
                        )
                        self._write_state(current)
                    finally:
                        _release_descriptors(descriptors)
            return current

    def claim(
        self,
        radio_ids: tuple[str, ...],
        *,
        task_id: str,
        task_kind: CaptureTaskKind,
    ) -> RadioLease:
        resources = self._resolve_resources(radio_ids)
        with self._control_lock():
            state = self._read_state()
            if state.desired_state is CaptureDesiredState.PAUSED:
                raise CapturePausedError(f"capture is {state.observed_state.value}: {state.reason}")
            descriptors = self._try_lock(resources)
            if descriptors is None:
                busy_ids = tuple(item.radio_id for item in resources)
                raise RadioBusyError(f"radio lease is busy: {busy_ids}")
        return RadioLease(
            radio_ids=tuple(item.radio_id for item in resources),
            task_id=task_id,
            task_kind=task_kind,
            descriptors=descriptors,
        )

    def claim_paused_maintenance(
        self,
        radio_ids: tuple[str, ...],
        *,
        task_id: str,
        expected_generation: int,
    ) -> RadioLease:
        """Claim exact radios while capture is durably paused for maintenance.

        The caller must bind its authorization to one observed control-state
        generation.  The returned lease uses the same global and per-radio
        kernel locks as ordinary acquisition, but it is the only claim path
        permitted while the authority is fully paused.
        """

        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected maintenance generation must be a nonnegative integer")
        resources = self._resolve_resources(radio_ids)
        with self._control_lock():
            state = self._read_state()
            if state.generation != expected_generation:
                raise CaptureAuthorityError(
                    "capture authority generation changed before maintenance claim: "
                    f"expected {expected_generation}, observed {state.generation}"
                )
            if (
                state.desired_state is not CaptureDesiredState.PAUSED
                or state.observed_state is not CaptureObservedState.PAUSED
            ):
                raise CaptureAuthorityError(
                    "maintenance radio lease requires capture to be fully paused"
                )
            descriptors = self._try_lock(resources)
            if descriptors is None:
                busy_ids = tuple(item.radio_id for item in resources)
                raise RadioBusyError(f"radio lease is busy: {busy_ids}")
        return RadioLease(
            radio_ids=tuple(item.radio_id for item in resources),
            task_id=task_id,
            task_kind=CaptureTaskKind.QUALIFICATION,
            descriptors=descriptors,
        )

    def pause(
        self,
        *,
        operator_id: str,
        reason: str,
        wait: bool = True,
        timeout_seconds: float = 90.0,
    ) -> CaptureControlStateV1:
        if timeout_seconds <= 0:
            raise ValueError("pause timeout must be positive")
        with self._control_lock():
            current = self._read_state()
            if current.desired_state is CaptureDesiredState.PAUSED:
                pending = current
            else:
                pending = CaptureControlStateV1(
                    generation=current.generation + 1,
                    desired_state=CaptureDesiredState.PAUSED,
                    observed_state=CaptureObservedState.PAUSING,
                    changed_utc_ns=self._utc_ns(),
                    operator_id=operator_id,
                    reason=reason,
                )
                self._write_state(pending)
        if not wait:
            return pending
        deadline = self._monotonic() + timeout_seconds
        while True:
            descriptors = self._try_lock(self._ordered_resources)
            if descriptors is not None:
                # New claims are already fenced by desired_state=paused. Drop
                # the radio lock before taking the control lock again so every
                # path keeps one lock order: control, then radio.
                _release_descriptors(descriptors)
                with self._control_lock():
                    latest = self._read_state()
                    if latest.desired_state is CaptureDesiredState.RUNNING:
                        return latest
                    drained = latest.model_copy(
                        update={
                            "observed_state": CaptureObservedState.PAUSED,
                            "changed_utc_ns": self._utc_ns(),
                        }
                    )
                    self._write_state(drained)
                    return drained
            if self._monotonic() >= deadline:
                raise TimeoutError("timed out waiting for active radio captures to drain")
            self._wait(0.05)

    def resume(self, *, operator_id: str, reason: str) -> CaptureControlStateV1:
        with self._control_lock():
            current = self._read_state()
            if current.desired_state is CaptureDesiredState.RUNNING:
                return current
            resumed = CaptureControlStateV1(
                generation=current.generation + 1,
                desired_state=CaptureDesiredState.RUNNING,
                observed_state=CaptureObservedState.RUNNING,
                changed_utc_ns=self._utc_ns(),
                operator_id=operator_id,
                reason=reason,
            )
            self._write_state(resumed)
            return resumed

    def _resolve_resources(self, radio_ids: tuple[str, ...]) -> tuple[RadioResource, ...]:
        if not radio_ids or len(set(radio_ids)) != len(radio_ids):
            raise ValueError("radio lease requests must be nonempty and unique")
        try:
            resources = tuple(self._resources[item] for item in radio_ids)
        except KeyError as error:
            raise UnknownRadioError(f"unknown radio resource: {error.args[0]}") from error
        return tuple(sorted(resources, key=lambda item: item.physical_key))

    def _try_lock(self, resources: tuple[RadioResource, ...]) -> tuple[int, ...] | None:
        descriptors: list[int] = []
        try:
            # The operation-level mutex intentionally precedes the exact-radio
            # locks. It makes every authority user (scheduled dwell, scanner,
            # operator once, qualification, soak and probes) one global radio
            # owner while retaining per-radio locks as defense in depth.
            global_descriptor = _open_lock(self._global_radio_lock_path)
            try:
                fcntl.flock(global_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(global_descriptor)
                return None
            descriptors.append(global_descriptor)
            for resource in resources:
                descriptor = _open_lock(self.lock_root / resource.lock_name)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(descriptor)
                    _release_descriptors(tuple(descriptors))
                    return None
                descriptors.append(descriptor)
            return tuple(descriptors)
        except Exception:
            _release_descriptors(tuple(descriptors))
            raise

    def _control_lock(self) -> _LockedDescriptor:
        return _LockedDescriptor(_open_lock(self._control_lock_path))

    def _read_state(self) -> CaptureControlStateV1:
        try:
            payload = self._state_path.read_bytes()
        except FileNotFoundError as error:
            raise CaptureAuthorityError("capture authority state disappeared") from error
        try:
            return CaptureControlStateV1.model_validate_json(payload)
        except Exception as error:
            raise CaptureAuthorityError("capture authority state is invalid") from error

    def _write_state(self, state: CaptureControlStateV1) -> None:
        payload = state.model_dump_json(indent=2).encode() + b"\n"
        temporary = self.root / f".capture-authority.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._state_path)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()


class AuthorizedAcquisitionApplication(AcquisitionApplication):
    """Acquire one atomic radio-set lease around an acquisition application's radio use."""

    def __init__(
        self,
        delegate: AcquisitionApplication,
        authority: LocalCaptureAuthority,
        task_kind: CaptureTaskKind,
    ) -> None:
        super().__init__(delegate.coordinator)
        self._delegate = delegate
        self._authority = authority
        self._task_kind = task_kind

    def estimate(self, plan: CapturePlanV1 | CapturePlanV3):
        return self._delegate.estimate(plan)

    def once(
        self,
        plan: CapturePlanV1 | CapturePlanV3,
        sources: Mapping[str, RadioSource],
        *,
        session_id: str | None = None,
        cancel: Event | None = None,
        extra_tags: tuple[str, ...] = (),
        requested_settings_by_radio: Mapping[str, RadioSettingsV1] | None = None,
    ):
        identity = session_id or self._delegate.new_session_id()
        lease = self._authority.claim(
            plan.radio_ids,
            task_id=identity,
            task_kind=self._task_kind,
        )
        try:
            result = self._delegate.once(
                plan,
                sources,
                session_id=identity,
                cancel=cancel,
                extra_tags=extra_tags,
                requested_settings_by_radio=requested_settings_by_radio,
            )
        except AcquisitionSupervisorPoisoned as error:
            _retain_lease_until_consumers_stop(lease, error.consumer_threads)
            raise
        except BaseException:
            lease.release()
            raise
        lease.release()
        return result


def _retain_lease_until_consumers_stop(
    lease: RadioLease,
    consumer_threads: tuple[Thread, ...],
) -> None:
    """Keep physical ownership until every poisoned storage consumer exits."""

    def release_after_consumers_stop() -> None:
        try:
            for consumer in consumer_threads:
                consumer.join()
        finally:
            lease.release()

    keeper = Thread(
        target=release_after_consumers_stop,
        name="leo-poisoned-radio-lease",
        daemon=True,
    )
    try:
        keeper.start()
    except BaseException as start_error:
        try:
            release_after_consumers_stop()
        except BaseException as cleanup_error:
            raise cleanup_error from start_error
        raise


class _LockedDescriptor:
    def __init__(self, descriptor: int) -> None:
        self._descriptor = descriptor

    def __enter__(self) -> int:
        fcntl.flock(self._descriptor, fcntl.LOCK_EX)
        return self._descriptor

    def __exit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)


def _open_lock(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        os.close(descriptor)
        raise CaptureAuthorityError(f"capture lock is not a private regular file: {path}")
    return descriptor


def _release_descriptors(descriptors: tuple[int, ...]) -> None:
    for descriptor in reversed(descriptors):
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
