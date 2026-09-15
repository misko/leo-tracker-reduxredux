"""One IIO owner with bounded native IQ read-ahead and host decision work."""

from __future__ import annotations

import importlib
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from pluto_plus.host_adaptive_hop import HostDecisionOutcome, HostFeedbackV1

from leo.radio.host_adaptive_mapping import (
    load_host_decision,
    load_host_policy,
    map_host_capture,
    map_host_sampled_visit,
    map_host_work_result,
)
from leo.radio.host_decision_worker import (
    BoundedHostDecisionWorker,
    HostDecisionEngine,
    HostDecisionWorkResult,
)
from leo.radio.pluto_persistent_hop import (
    _load_plan,
    _load_tandem_hold_request,
    _physical_lan_uri,
)
from leo.radio.scanner_iio_compat import scanner_adi_module
from leo.scanner.adaptive_hop import AdaptiveHopVisitV1
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostAdaptiveHopReceiptV2,
    HostDecisionConfigurationV1,
    HostDecisionConfigurationV2,
    HostDecisionRecordV1,
    HostDecisionRecordV2,
)
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.persistent_hop import persistent_hop_wire_session_id
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1
from leo.scanner.ports import ScanRadioIdentity

_POLL_SECONDS = 0.025
_JOIN_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class _Overflow:
    source: HostFeedbackV1
    submitted_ns: int


class PlutoHostAdaptiveHopRadio:
    """The release loader supplies the verified engine factory and its identity.

    Logical open does not open IIO. Client construction, admission, reads,
    feedback and restoration all execute on the session's acquisition thread.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str,
        decision: HostDecisionConfigurationV1 | HostDecisionConfigurationV2,
        decision_engine_factory: Callable[[], HostDecisionEngine],
        iiod_port: int | None = None,
        read_ahead_visits: int = 8,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        uri = _physical_lan_uri(host, iiod_port=iiod_port)
        if not expected_serial or expected_serial != expected_serial.strip():
            raise ValueError("host adaptive serial must be a trimmed nonempty value")
        if not radio_id or radio_id != radio_id.strip():
            raise ValueError("host adaptive radio ID must be a trimmed nonempty value")
        if type(read_ahead_visits) is not int or not 1 <= read_ahead_visits <= 64:
            raise ValueError("host adaptive read-ahead must be within 1..64")
        self._identity = ScanRadioIdentity(radio_id, expected_serial, uri)
        decision_model = (
            HostDecisionConfigurationV2
            if getattr(decision, "schema_version", None) == 2
            else HostDecisionConfigurationV1
        )
        self._decision = decision_model.model_validate(decision)
        self._engine_factory = decision_engine_factory
        self._client_factory = client_factory or _load_client
        self._read_ahead = read_ahead_visits
        self._opened = False
        self._session: _HostAdaptiveSession | None = None

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        if self._opened:
            raise RuntimeError("host adaptive radio is already open")
        self._opened = True
        return self.identity

    def begin_session(
        self, plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3, *, session_id: str
    ) -> _HostAdaptiveSession:
        if not self._opened or self._session is not None:
            raise RuntimeError("host adaptive radio must be open without another session")
        plan_model = HostAdaptiveHopPlanV3 if plan.schema_version == 3 else HostAdaptiveHopPlanV2
        plan = plan_model.model_validate(plan)
        if plan.decision != self._decision:
            raise ValueError("host adaptive plan differs from the loaded detector release")
        persistent_hop_wire_session_id(session_id)
        session = _HostAdaptiveSession(
            plan,
            identity=self.identity,
            session_id=session_id,
            read_ahead=self._read_ahead,
            client_factory=self._client_factory,
            engine_factory=self._engine_factory,
        )
        self._session = session
        session.start()
        return session

    def close(self) -> None:
        session = self._session
        if session is None:
            self._opened = False
            return
        try:
            session.request_cancel()
            session.finish()
        finally:
            # A timed-out owner retains the context. Never close its IIO from
            # this thread, including when admission itself is still running.
            if session.stopped:
                self._session = None
                self._opened = False


class _HostAdaptiveSession:
    def __init__(
        self,
        plan: HostAdaptiveHopPlanV2,
        *,
        identity: ScanRadioIdentity,
        session_id: str,
        read_ahead: int,
        client_factory: Callable[..., Any],
        engine_factory: Callable[[], HostDecisionEngine],
    ) -> None:
        self._plan, self._identity, self._session_id = plan, identity, session_id
        self._client_factory, self._engine_factory = client_factory, engine_factory
        self._upstream: Any = None
        self._visits: queue.Queue[HostAdaptiveHopVisitBlock] = queue.Queue(read_ahead)
        self._cancel, self._done, self._ready = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        self._error: BaseException | None = None
        self._receipt: HostAdaptiveHopReceiptV2 | None = None
        self._bracket: PersistentHopStartClockBracketV1 | None = None
        self._produced: list[AdaptiveHopVisitV1] = []
        self._records: list[HostDecisionRecordV1 | HostDecisionRecordV2] = []
        self._completed: dict[int, HostDecisionWorkResult | _Overflow] = {}
        self._decision_order: list[int] = []
        self._records_emitted = 0
        self._feedback_fault: str | None = None
        self._producer = threading.Thread(
            target=self._run, name=f"leo-host-adaptive-{session_id}", daemon=False
        )

    def start(self) -> None:
        try:
            self._producer.start()
        except BaseException as error:
            self._error = error
            self._done.set()
            self._ready.set()
            raise
        if not self._ready.wait(timeout=30):
            self._cancel.set()
            raise RuntimeError("host adaptive admission did not finish within 30 seconds")
        if self._error is not None:
            self._join()
            raise self._error

    @property
    def plan(self) -> HostAdaptiveHopPlanV2:
        return self._plan

    @property
    def start_clock_bracket(self) -> PersistentHopStartClockBracketV1 | None:
        return self._bracket  # Cached by the IIO owner during admission.

    @property
    def complete(self) -> bool:
        return self._done.is_set() and self._visits.empty()

    @property
    def stopped(self) -> bool:
        return self._done.is_set() and not self._producer.is_alive()

    def request_cancel(self) -> None:
        self._cancel.set()

    def read_visit(self) -> HostAdaptiveHopVisitBlock:
        while True:
            try:
                return self._visits.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                if self._done.is_set():
                    self._join()
                    self._terminal()
                    raise StopIteration from None

    def finish(self) -> HostAdaptiveHopReceiptV2:
        if not self.complete and not self._cancel.is_set():
            raise RuntimeError("host adaptive finish requires draining native IQ")
        deadline = time.monotonic() + _JOIN_SECONDS
        while not self.complete:
            with suppress(queue.Empty):
                self._visits.get(timeout=_POLL_SECONDS)
            if time.monotonic() >= deadline:
                raise RuntimeError("host adaptive producer did not finish cancellation")
        self._join()
        return self._terminal()

    def _join(self) -> None:
        if self._producer.ident is None:
            return
        self._producer.join(timeout=_JOIN_SECONDS)
        if self._producer.is_alive():
            raise RuntimeError("host adaptive IIO owner has not stopped")

    def _terminal(self) -> HostAdaptiveHopReceiptV2:
        if self._error is not None:
            raise self._error
        if self._receipt is None:
            raise RuntimeError("host adaptive terminal source evidence is missing")
        return self._receipt

    def _accept(self, sampled: Any, worker: BoundedHostDecisionWorker) -> None:
        block = map_host_sampled_visit(sampled, self.plan)
        event = block.evidence.event
        if self._produced and event.visit_index <= self._produced[-1].event.visit_index:
            raise ValueError("host adaptive native visits arrived out of order")
        feedback_model = (
            importlib.import_module("pluto_plus.host_adaptive_hop").HostFeedbackV2
            if self.plan.decision.source_rate_hz in (15_000_000, 20_000_000)
            else HostFeedbackV1
        )
        source = feedback_model(
            session_id=persistent_hop_wire_session_id(self._session_id),
            generation=self.plan.policy.generation,
            stream_id=self._upstream.stream_generation,
            visit=event.visit_index,
            event_sequence=event.event_sequence,
            receiver_id=self.plan.classification_receiver,
            target_index=event.target_index,
            valid_start=event.valid_start_counter,
            valid_end=block.evidence.valid_end_counter_exclusive,
            configuration_sha256=bytes.fromhex(self.plan.decision.configuration_sha256[7:]),
            outcome=HostDecisionOutcome.UNKNOWN,
            healthy=0,
            screen_mask=0,
            confirmation_mask=0,
            **(
                {"source_rate_hz": self.plan.decision.source_rate_hz}
                if self.plan.decision.source_rate_hz != 10_000_000
                else {}
            ),
        )
        if worker.pending_count == worker.capacity:
            # Retain only small source metadata, never an extra IQ work item.
            self._completed[event.visit_index] = _Overflow(source, time.monotonic_ns())
        else:
            worker.submit(source, sampled.samples, edge=event.target.edge.value)
        self._decision_order.append(event.visit_index)
        try:
            self._visits.put_nowait(block)
        except queue.Full as error:
            raise RuntimeError(
                "host adaptive native IQ read-ahead exhausted; capture must cancel"
            ) from error
        self._produced.append(block.evidence)

    def _flush(self, results: tuple[HostDecisionWorkResult, ...]) -> None:
        for completed in results:
            self._completed[completed.source.visit] = completed
        while (
            self._records_emitted < len(self._decision_order)
            and self._decision_order[self._records_emitted] in self._completed
        ):
            result = self._completed.pop(self._decision_order[self._records_emitted])
            now = time.monotonic_ns()
            feedback = result.source if isinstance(result, _Overflow) else result.feedback(now)
            accepted = False
            attempted = self._feedback_fault is None
            if attempted:
                try:
                    accepted = self._upstream.submit_feedback(feedback)
                except Exception as error:
                    # Provider policy sees missing feedback and latches uniform
                    # fallback. Preserve the native capture and explicit fault;
                    # a failed command must not masquerade as accepted feedback.
                    self._feedback_fault = f"{type(error).__name__}: {error}"[:2048]
            feedback_completed_ns = time.monotonic_ns()
            if isinstance(result, _Overflow):
                values = dict(
                    session_id=feedback.session_id,
                    generation=feedback.generation,
                    stream_generation=feedback.stream_id,
                    visit_index=feedback.visit,
                    event_sequence=feedback.event_sequence,
                    receiver_id=feedback.receiver_id,
                    target_index=feedback.target_index,
                    valid_start_counter=feedback.valid_start,
                    valid_end_counter_exclusive=feedback.valid_end,
                    configuration_sha256="sha256:" + feedback.configuration_sha256.hex(),
                    submitted_monotonic_ns=result.submitted_ns,
                    started_monotonic_ns=None,
                    completed_monotonic_ns=None,
                    feedback_monotonic_ns=now,
                    feedback_completed_monotonic_ns=feedback_completed_ns,
                    numerics=None,
                    health="queue_overflow",
                    failure="host decision capacity of two reached",
                    feedback_outcome="unknown",
                    feedback_disposition=(
                        "rejected"
                        if self._feedback_fault and attempted
                        else "not_submitted"
                        if not attempted
                        else "accepted"
                        if accepted
                        else "source_ended"
                    ),
                    feedback_error=self._feedback_fault,
                )
                if self.plan.decision.source_rate_hz == 10_000_000:
                    record = HostDecisionRecordV1.model_validate(values)
                else:
                    record = HostDecisionRecordV2.model_validate(
                        {
                            **values,
                            "schema_version": 2,
                            "source_rate_hz": self.plan.decision.source_rate_hz,
                        }
                    )
            else:
                record = map_host_work_result(
                    result,
                    feedback_ns=now,
                    accepted=accepted,
                    feedback_error=self._feedback_fault,
                    feedback_completed_ns=feedback_completed_ns,
                    submitted=attempted,
                    source_rate_hz=self.plan.decision.source_rate_hz,
                )
            self._records.append(record)
            self._records_emitted += 1

    def _refresh_start_clock_bracket(self) -> None:
        bracket = self._upstream.start_clock_bracket
        if bracket is not None:
            self._bracket = PersistentHopStartClockBracketV1(
                before_realtime_ns=bracket.before_realtime_ns,
                before_monotonic_ns=bracket.before_monotonic_ns,
                after_realtime_ns=bracket.after_realtime_ns,
                after_monotonic_ns=bracket.after_monotonic_ns,
            )

    def _run(self) -> None:
        worker: BoundedHostDecisionWorker | None = None
        try:
            client = self._client_factory(self._identity.uri, self._identity.serial)
            direct_options: dict[str, int] = (
                {"direct_async_frames": 8192} if self.plan.schema_version == 3 else {}
            )
            self._upstream = client.start(
                _load_plan(self.plan.geometry),
                policy=load_host_policy(self.plan),
                decision=load_host_decision(self.plan),
                session_id=persistent_hop_wire_session_id(self._session_id),
                tandem_request=_load_tandem_hold_request(),
                **direct_options,
            )
            self._refresh_start_clock_bracket()
            worker = BoundedHostDecisionWorker(
                self._engine_factory,
                source_sample_count=self.plan.geometry.valid_visit_samples,
            )
            self._ready.set()

            def before_release() -> None:
                assert worker is not None
                self._flush(worker.drain())

            iterator = iter(self._upstream.visits(before_release=before_release))
            while not self._cancel.is_set():
                self._flush(worker.poll())
                try:
                    sampled = next(iterator)
                except StopIteration:
                    break
                if not self._produced:
                    # The IIO backend replaces its broad OPEN bracket when it
                    # receives block zero and can bind the FPGA sample counter.
                    self._refresh_start_clock_bracket()
                self._flush(worker.poll())
                self._accept(sampled, worker)
            self._upstream.close(before_release=before_release)
            self._refresh_start_clock_bracket()
            for sampled in self._upstream.take_terminal_visits():
                self._flush(worker.poll())
                self._accept(sampled, worker)
            self._flush(worker.finish())
            worker = None
            self._receipt = map_host_capture(
                self._upstream.receipt,
                plan=self.plan,
                identity=self._identity,
                session_id=self._session_id,
                host_decisions=tuple(self._records),
            )
            if self._receipt.visits != tuple(self._produced):
                raise ValueError("host adaptive terminal receipt differs from produced native IQ")
        except BaseException as error:
            self._error = error
        finally:
            for cleanup in (
                self._upstream.close if self._upstream is not None else None,
                worker.finish if worker is not None else None,
            ):
                if cleanup is not None:
                    try:
                        cleanup()
                    except BaseException as error:
                        if self._error is None:
                            self._error = error
                        else:
                            self._error.add_note(f"host adaptive cleanup also failed: {error!r}")
            self._done.set()
            self._ready.set()


def _load_client(uri: str, expected_serial: str) -> Any:
    module = importlib.import_module("pluto_plus.hardware.iio_host_adaptive_hop")
    return module.iio_host_adaptive_hop_client(
        uri, expected_serial=expected_serial, adi_module=scanner_adi_module()
    )
