"""Single-owner Pluto adaptive session, with bounded dual-RX read-ahead."""

from __future__ import annotations

import importlib
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.radio.adaptive_hop_mapping import (
    load_adaptive_policy,
    map_adaptive_capture,
    map_adaptive_sampled_visit,
)
from leo.radio.pluto_persistent_hop import (
    _load_plan,
    _load_tandem_hold_request,
    _physical_lan_uri,
)
from leo.radio.scanner_glrt_metadata import (
    ScannerAdaptiveGlrtMetadataExtension,
    ScannerGlrtOptions,
)
from leo.radio.scanner_iio_compat import scanner_adi_module
from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopReceiptV1, AdaptiveHopVisitV1
from leo.scanner.adaptive_hop_ports import AdaptiveHopSession, AdaptiveHopVisitBlock
from leo.scanner.persistent_hop import persistent_hop_wire_session_id
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1
from leo.scanner.ports import ScanRadioIdentity

_POLL_SECONDS = 0.025
_JOIN_SECONDS = 15.0


class PlutoAdaptiveHopError(RuntimeError):
    """Adaptive ownership, source evidence or cleanup could not be verified."""


class PlutoAdaptiveHopRadio:
    """Logical open; PPU admits and owns exactly one physical-LAN context.

    Adaptive capture requires the explicit positive-only metadata profile.
    Unsupported clients fail admission; they cannot silently record fixed hops.
    The producer alone calls upstream methods, including cancellation/close.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str,
        scanner_glrt: ScannerGlrtOptions,
        iiod_port: int | None = None,
        read_ahead_visits: int = 8,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._uri = _physical_lan_uri(host, iiod_port=iiod_port)
        if not expected_serial or expected_serial != expected_serial.strip():
            raise ValueError("adaptive serial must be a trimmed nonempty value")
        if not radio_id or radio_id != radio_id.strip():
            raise ValueError("adaptive radio ID must be a trimmed nonempty value")
        if type(read_ahead_visits) is not int or not 1 <= read_ahead_visits <= 64:
            raise ValueError("adaptive read-ahead visits must be within 1..64")
        if not isinstance(scanner_glrt, ScannerGlrtOptions):
            raise ValueError("adaptive hopping requires explicit GLRT options")
        scanner_glrt.__post_init__()
        if scanner_glrt.mode != "positive-only-v1":
            raise ValueError("adaptive hopping requires the positive-only-v1 GLRT profile")
        self._identity = ScanRadioIdentity(radio_id, expected_serial, self._uri)
        self._options = scanner_glrt
        self._read_ahead = read_ahead_visits
        self._client_factory = client_factory or _load_client
        self._opened = False
        self._session: _PlutoAdaptiveHopSession | None = None
        self._evidence: ScannerGlrtSessionEvidenceV1 | None = None
        self._classification_error: str | None = None

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    @property
    def classification_evidence(self) -> ScannerGlrtSessionEvidenceV1 | None:
        return self._session.classification_evidence if self._session else self._evidence

    @property
    def classification_error(self) -> str | None:
        return self._session.classification_error if self._session else self._classification_error

    def open(self) -> ScanRadioIdentity:
        if self._opened:
            raise PlutoAdaptiveHopError("adaptive radio is already open")
        self._opened = True
        self._evidence = None
        self._classification_error = None
        return self.identity

    def begin_session(self, plan: AdaptiveHopPlanV1, *, session_id: str) -> AdaptiveHopSession:
        if not self._opened:
            raise PlutoAdaptiveHopError("adaptive radio must be opened first")
        if self._session is not None:
            raise PlutoAdaptiveHopError("adaptive radio already owns a session")
        plan = AdaptiveHopPlanV1.model_validate(plan)
        wire_id = persistent_hop_wire_session_id(session_id)
        extension = ScannerAdaptiveGlrtMetadataExtension(
            self._options, session=wire_id, generation=plan.policy.generation
        )
        upstream = None
        try:
            client = self._client_factory(
                self._uri, self.identity.serial, metadata_extension=extension
            )
            upstream = client.start(
                _load_plan(plan.geometry),
                policy=load_adaptive_policy(plan),
                session_id=wire_id,
                tandem_request=_load_tandem_hold_request(),
            )
            session = _PlutoAdaptiveHopSession(
                upstream,
                plan=plan,
                identity=self.identity,
                session_id=session_id,
                read_ahead=self._read_ahead,
                extension=extension,
            )
            self._session = session
            session.start()
        except BaseException as error:
            # No producer owns the upstream if construction/thread startup failed.
            if upstream is not None:
                try:
                    upstream.close()
                except BaseException as cleanup:
                    error.add_note(f"adaptive startup cleanup also failed: {cleanup!r}")
            self._session = None
            if not isinstance(error, Exception):
                raise
            raise PlutoAdaptiveHopError(f"adaptive provider start failed: {error}") from error
        return session

    def close(self) -> None:
        session = self._session
        if session is not None:
            try:
                session.request_cancel()
                session.finish()
            finally:
                # Keep ownership if a timed-out producer is still running.
                # Closing its IIO context here would race its refill/cleanup.
                if session.stopped:
                    self._evidence = session.classification_evidence
                    self._classification_error = session.classification_error
                    self._session = None
                    self._opened = False
        else:
            self._opened = False


class _PlutoAdaptiveHopSession:
    def __init__(
        self,
        upstream: Any,
        *,
        plan: AdaptiveHopPlanV1,
        identity: ScanRadioIdentity,
        session_id: str,
        read_ahead: int,
        extension: ScannerAdaptiveGlrtMetadataExtension,
    ) -> None:
        self._upstream, self._plan = upstream, plan
        self._identity, self._session_id = identity, session_id
        self._extension = extension
        self._visits: queue.Queue[AdaptiveHopVisitBlock] = queue.Queue(maxsize=read_ahead)
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._error: BaseException | None = None
        self._receipt: AdaptiveHopReceiptV1 | None = None
        self._produced: list[AdaptiveHopVisitV1] = []
        self._evidence: ScannerGlrtSessionEvidenceV1 | None = None
        self._classification_error: str | None = None
        self._producer = threading.Thread(
            target=self._run, name=f"leo-adaptive-radio-{session_id}", daemon=False
        )

    def start(self) -> None:
        self._producer.start()

    @property
    def plan(self) -> AdaptiveHopPlanV1:
        return self._plan

    @property
    def stopped(self) -> bool:
        return self._done.is_set() and not self._producer.is_alive()

    @property
    def complete(self) -> bool:
        return self._done.is_set() and self._visits.empty()

    @property
    def classification_evidence(self) -> ScannerGlrtSessionEvidenceV1 | None:
        return self._evidence if self._done.is_set() else None

    @property
    def classification_error(self) -> str | None:
        return self._classification_error if self._done.is_set() else None

    @property
    def start_clock_bracket(self) -> PersistentHopStartClockBracketV1 | None:
        bracket = self._upstream.start_clock_bracket
        if bracket is None:
            return None
        return PersistentHopStartClockBracketV1(
            before_realtime_ns=bracket.before_realtime_ns,
            before_monotonic_ns=bracket.before_monotonic_ns,
            after_realtime_ns=bracket.after_realtime_ns,
            after_monotonic_ns=bracket.after_monotonic_ns,
        )

    def request_cancel(self) -> None:
        # Called from the consumer; no IIO operations or waiting here.
        self._cancel.set()

    def read_visit(self) -> AdaptiveHopVisitBlock:
        while True:
            try:
                return self._visits.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                if not self._done.is_set():
                    continue
                self._join()
                self._terminal()
                raise StopIteration from None

    def finish(self) -> AdaptiveHopReceiptV1:
        if not self.complete:
            if not self._cancel.is_set():
                raise PlutoAdaptiveHopError("adaptive finish requires draining the visit stream")
            # Recovery only: normal cancelled capture drains through read_visit
            # into the recording. Failed/abandoned captures discard here so a
            # full read-ahead queue cannot strand the acquisition owner.
            deadline = time.monotonic() + _JOIN_SECONDS
            while not self.complete:
                with suppress(queue.Empty):
                    self._visits.get(timeout=_POLL_SECONDS)
                if time.monotonic() >= deadline:
                    raise PlutoAdaptiveHopError("adaptive producer did not stop after cancellation")
        self._join()
        return self._terminal()

    def _join(self) -> None:
        self._producer.join(timeout=_JOIN_SECONDS)
        if self._producer.is_alive():
            raise PlutoAdaptiveHopError("adaptive producer did not stop after cancellation")

    def _terminal(self) -> AdaptiveHopReceiptV1:
        if self._error is not None:
            raise self._error
        if self._receipt is None:
            raise PlutoAdaptiveHopError("adaptive producer lacks validated terminal evidence")
        return self._receipt

    def _put(self, sampled: Any) -> None:
        block = map_adaptive_sampled_visit(sampled, self.plan)
        if block.evidence.event.visit_index != len(self._produced):
            raise PlutoAdaptiveHopError("adaptive producer received out-of-order IQ visits")
        while True:
            try:
                self._visits.put(block, timeout=_POLL_SECONDS)
                break
            except queue.Full:
                continue
        self._produced.append(block.evidence)

    def _map_receipt(self) -> AdaptiveHopReceiptV1:
        receipt = map_adaptive_capture(
            self._upstream.receipt,
            plan=self.plan,
            identity=self._identity,
            session_id=self._session_id,
        )
        if receipt.visits != tuple(self._produced):
            raise PlutoAdaptiveHopError("adaptive terminal visits disagree with produced IQ")
        return receipt

    def _run(self) -> None:
        try:
            iterator = iter(self._upstream.visits())
            while not self._cancel.is_set():
                try:
                    sampled = next(iterator)
                except StopIteration:
                    break
                self._put(sampled)
            # PPU normal exhaustion already closes; explicit close is idempotent
            # and, on cancellation, exposes every pending complete visit once.
            self._upstream.close()
            for sampled in self._upstream.take_terminal_visits():
                self._put(sampled)
            self._receipt = self._map_receipt()
        except BaseException as error:
            self._error = error
            try:
                self._upstream.close()
            except BaseException as cleanup:
                error.add_note(f"adaptive producer cleanup also failed: {cleanup!r}")
        finally:
            try:
                if self._error is not None:
                    self._extension.fail("adaptive host capture producer failed")
                self._evidence = self._extension.snapshot()
                self._classification_error = self._evidence.error
            except Exception as error:
                self._classification_error = f"adaptive classification snapshot failed: {error}"
            self._done.set()


def _load_client(
    uri: str, expected_serial: str, *, metadata_extension: ScannerAdaptiveGlrtMetadataExtension
) -> Any:
    module = importlib.import_module("pluto_plus.hardware.iio_adaptive_hop")
    return module.iio_adaptive_hop_client(
        uri,
        expected_serial=expected_serial,
        metadata_extension=metadata_extension,
        adi_module=scanner_adi_module(),
    )
