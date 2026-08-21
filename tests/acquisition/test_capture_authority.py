from __future__ import annotations

import multiprocessing
import os
import threading
import time
from pathlib import Path

import pytest

from leo.acquisition import (
    CapturePausedError,
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioBusyError,
    RadioResource,
)
from leo.contracts.capture_control import CaptureDesiredState, CaptureObservedState


def _resources() -> tuple[RadioResource, ...]:
    return (
        RadioResource("radio-a", "serial-a", "ip:192.0.2.20"),
        RadioResource("radio-b", "serial-b", "ip:192.0.2.21"),
    )


def _authority(root: Path) -> LocalCaptureAuthority:
    return LocalCaptureAuthority(root, _resources())


def test_pause_is_durable_and_blocks_every_radio_until_resume(tmp_path: Path) -> None:
    authority = _authority(tmp_path / "control")

    paused = authority.pause(operator_id="operator", reason="maintenance")

    assert paused.desired_state is CaptureDesiredState.PAUSED
    assert paused.observed_state is CaptureObservedState.PAUSED
    with pytest.raises(CapturePausedError, match="maintenance"):
        authority.claim(
            ("radio-a",),
            task_id="scan-one",
            task_kind=CaptureTaskKind.SCANNER_SWEEP,
        )
    reopened = _authority(tmp_path / "control")
    assert reopened.snapshot() == paused

    resumed = reopened.resume(operator_id="operator", reason="maintenance complete")
    assert resumed.generation == paused.generation + 1
    with reopened.claim(
        ("radio-a",),
        task_id="scan-two",
        task_kind=CaptureTaskKind.SCANNER_SWEEP,
    ) as lease:
        assert lease.radio_ids == ("radio-a",)


def test_only_one_radio_owning_operation_runs_even_on_disjoint_radios(tmp_path: Path) -> None:
    first = _authority(tmp_path / "control")
    second = _authority(tmp_path / "control")

    with first.claim(
        ("radio-a",),
        task_id="capture-a",
        task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
    ):
        with pytest.raises(RadioBusyError):
            second.claim(
                ("radio-a",),
                task_id="scan-a",
                task_kind=CaptureTaskKind.SCANNER_SWEEP,
            )
        with pytest.raises(RadioBusyError):
            second.claim(
                ("radio-b",),
                task_id="capture-b",
                task_kind=CaptureTaskKind.OPERATOR_ONCE,
            )


def test_failed_global_claim_does_not_corrupt_following_claim(tmp_path: Path) -> None:
    first = _authority(tmp_path / "control")
    second = _authority(tmp_path / "control")

    with first.claim(
        ("radio-b",),
        task_id="existing-b",
        task_kind=CaptureTaskKind.OPERATOR_ONCE,
    ):
        with pytest.raises(RadioBusyError):
            second.claim(
                ("radio-a", "radio-b"),
                task_id="paired",
                task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
            )
        with pytest.raises(RadioBusyError):
            second.claim(
                ("radio-a",),
                task_id="independent-a",
                task_kind=CaptureTaskKind.OPERATOR_ONCE,
            )
    with second.claim(
        ("radio-a",),
        task_id="after-release",
        task_kind=CaptureTaskKind.OPERATOR_ONCE,
    ):
        pass


def test_pause_waits_for_active_lease_then_fences_new_claims(tmp_path: Path) -> None:
    holder = _authority(tmp_path / "control")
    operator = _authority(tmp_path / "control")
    lease = holder.claim(
        ("radio-a",),
        task_id="active",
        task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
    )
    completed: list[CaptureObservedState] = []

    thread = threading.Thread(
        target=lambda: completed.append(
            operator.pause(operator_id="operator", reason="pause all").observed_state
        )
    )
    thread.start()
    deadline = time.monotonic() + 2
    while operator.snapshot().observed_state is not CaptureObservedState.PAUSING:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert completed == []

    lease.release()
    thread.join(timeout=2)

    assert completed == [CaptureObservedState.PAUSED]
    with pytest.raises(CapturePausedError):
        holder.claim(
            ("radio-b",),
            task_id="blocked",
            task_kind=CaptureTaskKind.SCANNER_SWEEP,
        )


def test_nonblocking_pause_reconciles_after_active_lease_drains(tmp_path: Path) -> None:
    holder = _authority(tmp_path / "control")
    operator = LocalCaptureAuthority(tmp_path / "control", ())
    lease = holder.claim(
        ("radio-a",),
        task_id="active",
        task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
    )

    pending = operator.pause(operator_id="web-ui", reason="operator pause", wait=False)

    assert pending.observed_state is CaptureObservedState.PAUSING
    assert operator.snapshot().observed_state is CaptureObservedState.PAUSING
    lease.release()
    settled = operator.snapshot()
    assert settled.observed_state is CaptureObservedState.PAUSED
    assert operator.snapshot() == settled


def _claim_then_die(root: str, ready) -> None:
    authority = _authority(Path(root))
    authority.claim(
        ("radio-a",),
        task_id="crashing-child",
        task_kind=CaptureTaskKind.OPERATOR_ONCE,
    )
    ready.send("locked")
    ready.close()
    os._exit(0)


def test_process_exit_releases_kernel_radio_lease(tmp_path: Path) -> None:
    root = tmp_path / "control"
    authority = _authority(root)
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_claim_then_die, args=(str(root), sender))
    process.start()
    sender.close()
    assert receiver.poll(2)
    assert receiver.recv() == "locked"
    receiver.close()
    process.join(timeout=2)
    assert process.exitcode == 0

    with authority.claim(
        ("radio-a",),
        task_id="after-crash",
        task_kind=CaptureTaskKind.OPERATOR_ONCE,
    ):
        pass


def test_duplicate_physical_radio_aliases_are_rejected(tmp_path: Path) -> None:
    resources = (
        RadioResource("radio-a", "same", "ip:192.0.2.20"),
        RadioResource("alias-a", "same", "ip:192.0.2.20"),
    )
    with pytest.raises(ValueError, match="same physical radio"):
        LocalCaptureAuthority(tmp_path / "control", resources)


def test_serial_identity_rejects_different_endpoint_aliases(tmp_path: Path) -> None:
    resources = (
        RadioResource("radio-a", "same", "ip:192.0.2.20"),
        RadioResource("alias-a", "same", "ip:radio-a.local"),
    )
    with pytest.raises(ValueError, match="same physical radio"):
        LocalCaptureAuthority(tmp_path / "control", resources)
