"""PPU's counter-attested fixed 20 ms firmware visits through a bounded port.

The firmware owns target ordering. No returned visit is filtered to imitate a
host round-robin schedule. Hardware imports remain lazy for radio-free use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import queue
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from leo.acquisition.ppu_quality import signed12_ci16_quality
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowAcquisition,
    ShortWindowConfiguration,
    ShortWindowTarget,
    ValidityAuthority,
)


def _run_ppu_campaign(source: PpuShortWindowSource, config: ShortWindowConfiguration) -> Any:
    from pluto_plus.adaptive_scan import ScanOutcome, ScanTarget
    from pluto_plus.adaptive_scan_campaign import (
        build_adaptive_scan_setup,
        run_adaptive_scan_campaign,
    )
    from pluto_plus.adaptive_scan_client import AdaptiveScanClient
    from pluto_plus.adaptive_scan_shadow import AdaptiveScanMode

    frequencies = tuple(target.if_center_hz for target in config.targets)
    setup = build_adaptive_scan_setup(
        session=secrets.randbits(63) or 1,
        generation=secrets.randbits(63) or 1,
        seed=secrets.randbits(32) or 1,
        source_rate_hz=config.sample_rate_hz,
        analog_bandwidth_hz=2_000_000,
        duration_ms=round(config.duration_seconds * 1000),
        dwell_ms=20,
        frequencies_hz=frequencies[:7],
        baseline_weights=(1,) * min(7, len(frequencies)),
        analysis_digest=hashlib.sha256(b"leo-short-window-shadow-power-v1").digest(),
        transition_budget_ms=config.transition_budget_ms,
        maximum_revisit_ms=3000,
        rx_mask=3 if len(config.receiver_ids) == 2 else 1,
    )
    if len(frequencies) == 8:
        # The public protocol supports all eight slots; qualification must also
        # demonstrate that the installed driver handles slot zero correctly.
        setup = dataclasses.replace(
            setup,
            targets=tuple(
                ScanTarget(
                    channel=index,
                    profile=index,
                    frequency_hz=frequency,
                    baseline_weight=1,
                    profile_crc32=0,
                )
                for index, frequency in enumerate(frequencies)
            ),
        )
        setup.validate()

    class PreparedClient(AdaptiveScanClient):
        def start(self, *args: Any, **kwargs: Any) -> Any:
            if source.before_start_hook is not None:
                source.before_start_hook()
            return super().start(*args, **kwargs)

    receipt = run_adaptive_scan_campaign(
        source.uri,
        source.expected_serial,
        setup,
        lambda _visit: ScanOutcome.UNKNOWN,
        mode=AdaptiveScanMode.SHADOW,
        manual_gain_db=config.gain_db,
        samples_per_block=100_000,
        visit_sink=source._on_visit,
        session_hook=source._on_session,
        client_factory=PreparedClient,
    )
    source.receipt = receipt
    _validate_terminal(receipt.terminal)
    return receipt


def _validate_terminal(terminal: Any) -> None:
    if (
        terminal.state.name != "COMPLETED"
        or terminal.error
        or terminal.skipped
        or terminal.invalid
        or terminal.cancelled
    ):
        raise RuntimeError(f"PPU campaign ended with incomplete hardware accounting: {terminal!r}")


class PpuShortWindowSource:
    """One bounded LAN campaign with verified serial and PPU-owned restoration.

    USB may identify the same device, but PPU's current READSCAN campaign port
    requires its physical LAN address. Close waits for radio restoration.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        session_hook: Callable[[Any], None] | None = None,
        before_start_hook: Callable[[], None] | None = None,
        queue_windows: int = 32,
    ) -> None:
        if not expected_serial:
            raise ValueError("PPU capture requires an explicit radio serial")
        if not 1 <= queue_windows <= 64:
            raise ValueError("provider queue must contain one to 64 windows")
        self.uri = host if host.startswith("ip:") else f"ip:{host}"
        self.expected_serial = expected_serial
        self.session_hook = session_hook
        self.before_start_hook = before_start_hook
        self._queue: queue.Queue[tuple[ShortWindowTarget, ShortWindowAcquisition]] = queue.Queue(
            queue_windows
        )
        self._ready = threading.Event()
        self._done = threading.Event()
        self._cancelled = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: Any = None
        self._error: BaseException | None = None
        self._config: ShortWindowConfiguration | None = None
        self._previous_end: int | None = None
        self._previous_profile: int | None = None
        self.receipt: Any = None

    def configure_once(self, configuration: ShortWindowConfiguration) -> None:
        if self._thread is not None:
            raise RuntimeError("PPU source can only be configured once")
        if configuration.receiver_ids not in ((0,), (0, 1)):
            raise ValueError("PPU supports physical RX1 or ordered RX1/RX2")
        if not 0.12 <= configuration.duration_seconds <= 300:
            raise ValueError("PPU campaign duration must be between 0.12 and 300 seconds")
        if configuration.policy_id != "firmware-weighted-20ms-v1":
            raise ValueError("PPU requires the truthful firmware-weighted-20ms-v1 policy")
        if any(not 70_000_000 <= t.if_center_hz <= 6_000_000_000 for t in configuration.targets):
            raise ValueError("PPU IF targets must lie between 70 MHz and 6 GHz")
        self._config = configuration
        self._thread = threading.Thread(target=self._run, name="short-window-ppu", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 120
        while not self._ready.wait(0.05):
            if self._done.is_set():
                if self._error is not None:
                    raise RuntimeError("PPU preparation failed") from self._error
                raise RuntimeError("PPU campaign ended without opening a session")
            if time.monotonic() >= deadline:
                self.cancel()
                raise TimeoutError("PPU preparation exceeded 120 seconds")

    def _run(self) -> None:
        try:
            assert self._config is not None
            self.receipt = _run_ppu_campaign(self, self._config)
        except BaseException as error:
            self._error = error
        finally:
            self._done.set()

    def _on_session(self, session: Any) -> None:
        self._session = session
        if self._cancelled.is_set():
            session.close()
            raise RuntimeError("PPU campaign cancelled during preparation")
        if self.session_hook is not None:
            self.session_hook(session)
        self._ready.set()

    def _on_visit(self, visit: Any) -> None:
        config = self._config
        assert config is not None
        record = visit.record
        target = config.targets[record.target]
        receiver_count = len(config.receiver_ids)
        if len(visit.iq) % (receiver_count * 4):
            raise ValueError("PPU returned a partial CI16 sample")
        samples = np.frombuffer(visit.iq, dtype="<i2").reshape(-1, receiver_count, 2)
        if len(samples) > config.window_samples:
            raise ValueError("PPU returned more than a 20 ms window")
        complete = record.result.name == "COMPLETE"
        flags = () if complete else (f"provider_{record.result.name.lower()}",)
        if record.missing_samples_before:
            flags += ("provider_missing_samples",)
        if record.frequency_hz != target.if_center_hz:
            raise ValueError("PPU visit frequency disagrees with target")
        if complete and record.valid_end - record.valid_start != len(samples):
            raise ValueError("PPU hardware interval disagrees with IQ geometry")
        receipt = dataclasses.asdict(record)
        # This provider negotiates AD9361 signed 12-bit codes in CI16 words.
        # CI16 container rails alone would miss actual ADC saturation.
        quality_flags, quality_receipt = signed12_ci16_quality(samples)
        receipt.update(quality_receipt)
        flags += quality_flags
        acquisition = ShortWindowAcquisition(
            samples=samples,
            requested_if_center_hz=target.if_center_hz,
            actual_if_center_hz=record.frequency_hz,
            generation=record.generation,
            sample_start=record.valid_start,
            counter_authority=CounterAuthority.HARDWARE,
            validity_authority=(
                ValidityAuthority.PROVIDER_ATTESTED if complete else ValidityAuthority.UNKNOWN
            ),
            host_final_sample_monotonic_ns=time.monotonic_ns(),
            quality_flags=flags,
            tune_ms=(record.transition_after - record.transition_before)
            * 1000
            / config.sample_rate_hz,
            listen_ms=len(samples) * 1000 / config.sample_rate_hz,
            discarded_samples=record.valid_start - record.transition_before,
            retune_receipt=json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            validity_includes_guard=True,
            contiguous_with_previous=self._previous_end == record.valid_start,
            recall_skipped=(
                self._previous_profile == record.profile
                and record.transition_before == record.transition_after
            ),
        )
        self._previous_end = record.valid_end
        self._previous_profile = record.profile
        try:
            self._queue.put_nowait((target, acquisition))
        except queue.Full as error:
            raise RuntimeError("bounded PPU window queue overflowed; campaign stopped") from error

    def next_capture(self) -> tuple[ShortWindowTarget, ShortWindowAcquisition]:
        if self._thread is None:
            raise RuntimeError("PPU source has not been configured")
        while True:
            try:
                return self._queue.get(timeout=0.05)
            except queue.Empty:
                if self._done.is_set():
                    if self._error is not None:
                        raise RuntimeError("PPU capture or restoration failed") from self._error
                    raise StopIteration from None

    def capture(self, target: ShortWindowTarget, sample_count: int) -> ShortWindowAcquisition:
        raise RuntimeError("PPU owns visit order; consume next_capture() and its actual target")

    def cancel(self) -> None:
        self._cancelled.set()
        if self._session is not None:
            self._session.close()

    def close(self) -> None:
        if self._thread is None:
            return
        if not self._done.is_set():
            self.cancel()
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            raise TimeoutError("PPU worker did not finish restoration within 30 seconds")
        if self._error is not None:
            raise RuntimeError("PPU capture or restoration failed") from self._error
