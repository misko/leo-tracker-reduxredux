"""Read-only presentation using public adaptive manifests, never IQ decoding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.scanner.adaptive_hop import AdaptiveHopReceiptV2, AdaptiveHopReceiptV3
from leo.scanner.adaptive_hop_history import (
    AdaptiveHopCoverageV1,
    AdaptiveHopHistoryItemV1,
    AdaptiveHopHistoryPageV1,
    AdaptiveHopSessionDetailV1,
    AdaptiveHopVisitViewV1,
    DualRx10mAdaptiveHistoryItemV5,
    DualRx10mAdaptiveSessionDetailV5,
    EdgeAdaptiveHistoryItemV4,
    EdgeAdaptiveSessionDetailV4,
)
from leo.scanner.glrt_publication import validate_glrt_adaptive_binding
from leo.scanner.host_adaptive import (
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostDecisionRecordV2,
)
from leo.scanner.host_adaptive_history import (
    AdaptiveHistoryPageV2,
    AdaptiveHistoryPageV3,
    AdaptiveHistoryPageV4,
    HostAdaptiveHistoryItemV2,
    HostAdaptiveHistoryItemV3,
    HostAdaptiveSessionDetailV2,
    HostAdaptiveSessionDetailV3,
    HostDecisionViewV1,
    HostDecisionViewV2,
    HostFeedbackSummaryV1,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore, PublishedAdaptiveHopIqSession
from leo.storage.errors import BundleNotFoundError
from leo.storage.scanner_glrt import ScannerGlrtStore


def _utc(nanoseconds: int) -> datetime:
    seconds, remainder = divmod(nanoseconds, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(microseconds=remainder // 1000)


def _summary(session: PublishedAdaptiveHopIqSession) -> AdaptiveHopHistoryItemV1:
    manifest = session.manifest
    receipt = manifest.receipt
    rate = receipt.plan.geometry.sample_rate_hz
    span = receipt.duty_denominator_sample_count
    origin = receipt.terminal.first_counter
    visits = receipt.visits
    coverage = []
    for index, profile in enumerate(receipt.plan.geometry.profiles):
        retained = [v for v in visits if v.event.target_index == index]
        # Subtract integer epochs BEFORE any floating conversion.
        starts = [v.event.valid_start_counter - origin for v in retained]
        ends = [v.valid_end_counter_exclusive - origin for v in retained]
        revisit = max((b - a for a, b in zip(starts, starts[1:], strict=False)), default=None)
        blind = (
            max((b - a for a, b in zip([0, *ends], [*starts, span], strict=True)), default=span)
            if receipt.source_span_attested
            else None
        )
        count = len(retained)
        coverage.append(
            AdaptiveHopCoverageV1(
                target_index=index,
                target=profile.target,
                retained_visits=count,
                valid_seconds=count * receipt.plan.geometry.valid_visit_samples / rate,
                allocation_ppm=count * 1_000_000 // len(visits) if visits else None,
                maximum_revisit_seconds=revisit / rate if revisit is not None else None,
                maximum_unobserved_seconds=blind / rate if blind is not None else None,
            )
        )
    model: type[AdaptiveHopHistoryItemV1] = AdaptiveHopHistoryItemV1
    fields: dict[str, Any] = {}
    duty_met = receipt.duty_target_met
    if isinstance(receipt, HostAdaptiveHopReceiptV2):
        model = (
            HostAdaptiveHistoryItemV3
            if isinstance(receipt, HostAdaptiveHopReceiptV3)
            else HostAdaptiveHistoryItemV2
        )
        duty_met = receipt.qualification_duty_floor_met
        records = receipt.host_decisions
        calls = [
            d.feedback_call_elapsed_ns / 1e6
            for d in records
            if d.feedback_call_elapsed_ns is not None
        ]
        fields = dict(
            radio_serial=receipt.radio_serial,
            physical_receiver=receipt.plan.classification_receiver,
            decision_configuration=receipt.plan.decision,
            host_feedback=HostFeedbackSummaryV1(
                complete_visits=len(records),
                healthy=sum(d.health == "healthy" for d in records),
                degraded=sum(d.health != "healthy" for d in records),
                unknown_feedback=sum(d.feedback_outcome == "unknown" for d in records),
                accepted=sum(d.feedback_disposition == "accepted" for d in records),
                source_ended=sum(d.feedback_disposition == "source_ended" for d in records),
                rejected=sum(d.feedback_disposition == "rejected" for d in records),
                not_submitted=sum(d.feedback_disposition == "not_submitted" for d in records),
                maximum_host_result_age_ms=max(
                    ((d.feedback_monotonic_ns - d.submitted_monotonic_ns) / 1e6 for d in records),
                    default=None,
                ),
                maximum_feedback_call_ms=max(calls, default=None),
                first_feedback_error=next(
                    (d.feedback_error for d in records if d.feedback_error), None
                ),
            ),
        )
    elif isinstance(receipt, AdaptiveHopReceiptV2):
        model = (
            DualRx10mAdaptiveHistoryItemV5
            if isinstance(receipt, AdaptiveHopReceiptV3)
            else EdgeAdaptiveHistoryItemV4
        )
        mask = receipt.plan.policy.allowed_target_mask
        fields = dict(
            radio_serial=receipt.radio_serial,
            selected_edge="lower" if mask == 0x0F else "upper",
            allowed_target_mask=mask,
        )
    return model(
        **fields,
        session_id=session.session_id,
        input_manifest_sha256=session.manifest_sha256,
        radio_id=receipt.radio_id,
        mode=receipt.plan.policy.mode,
        policy_generation=receipt.plan.policy.generation,
        recorded_at=_utc(manifest.created_utc_ns),
        finalized_at=_utc(manifest.finalized_utc_ns),
        captured_at=_utc(manifest.timing.first_sample_estimate_utc_ns) if manifest.timing else None,
        utc_qualified=manifest.timing.qualified if manifest.timing else False,
        utc_bracket_width_ms=manifest.timing.first_sample_bracket_width_ns / 1e6
        if manifest.timing
        else None,
        sample_rate_hz=rate,
        bandwidth_hz=receipt.plan.geometry.bandwidth_hz,
        started_visits=len(receipt.events),
        retained_visits=receipt.complete_visit_count,
        source_span_attested=receipt.source_span_attested,
        source_span_seconds=span / rate if receipt.source_span_attested else None,
        valid_duty_ppm=receipt.valid_duty_ppm if receipt.source_span_attested else None,
        capture_qualified=receipt.terminal.state == "completed"
        and receipt.source_span_attested
        and duty_met,
        terminal_state=receipt.terminal.state,
        fallback_choices=sum(e.decision.reason == "fault_fallback" for e in receipt.events),
        target_coverage=tuple(coverage),
    )


class AdaptiveHopPresentationStore:
    """Per-request pinned read-only handles; no new directories or IQ reads."""

    def __init__(self, root: Path):
        self._root = root

    def page(self, *, cursor: int, limit: int) -> AdaptiveHopHistoryPageV1:
        return self._page(cursor=cursor, limit=limit, include_host=False)

    def page_v2(
        self, *, cursor: int, limit: int
    ) -> AdaptiveHistoryPageV2 | AdaptiveHistoryPageV3 | AdaptiveHistoryPageV4:
        result = self._page(cursor=cursor, limit=limit, include_host=True)
        assert isinstance(result, (AdaptiveHistoryPageV2, AdaptiveHistoryPageV3))
        return result

    def _page(self, *, cursor: int, limit: int, include_host: bool) -> AdaptiveHopHistoryPageV1:
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("adaptive history pagination is out of bounds")
        store = AdaptiveHopIqStore(self._root, read_only=True)
        try:
            # Keep only ordering keys, not every scan's up-to-2,500-event manifest.
            sessions = (
                list(store.history_index())
                if include_host
                else [
                    (s.manifest.finalized_utc_ns, s.session_id)
                    for s in store.iter_sessions()
                    if not isinstance(
                        s.manifest.receipt, (HostAdaptiveHopReceiptV2, AdaptiveHopReceiptV2)
                    )
                ]
            )
            sessions.sort(reverse=True)
            items = tuple(
                _summary(store.inspect(key)) for _, key in sessions[cursor : cursor + limit]
            )
        finally:
            store.close()
        model: type[AdaptiveHopHistoryPageV1] = (
            AdaptiveHistoryPageV4
            if include_host and any(isinstance(item, EdgeAdaptiveHistoryItemV4) for item in items)
            else AdaptiveHistoryPageV3
            if include_host and any(isinstance(item, HostAdaptiveHistoryItemV3) for item in items)
            else AdaptiveHistoryPageV2
            if include_host
            else AdaptiveHopHistoryPageV1
        )
        return model(
            cursor=cursor,
            limit=limit,
            total=len(sessions),
            next_cursor=cursor + limit if cursor + limit < len(sessions) else None,
            items=items,
        )

    def _inspect(self, session_id: str) -> PublishedAdaptiveHopIqSession | None:
        store = AdaptiveHopIqStore(self._root, read_only=True)
        try:
            try:
                return store.inspect(session_id)
            except BundleNotFoundError:
                return None
        finally:
            store.close()

    def detail(self, session_id: str) -> AdaptiveHopSessionDetailV1 | None:
        return self._detail(session_id, include_host=False)

    def detail_v2(
        self, session_id: str
    ) -> (
        AdaptiveHopSessionDetailV1
        | HostAdaptiveSessionDetailV2
        | HostAdaptiveSessionDetailV3
        | EdgeAdaptiveSessionDetailV4
        | None
    ):
        return self._detail(session_id, include_host=True)

    def _detail(self, session_id: str, *, include_host: bool) -> AdaptiveHopSessionDetailV1 | None:
        session = self._inspect(session_id)
        if session is None:
            return None
        receipt = session.manifest.receipt
        if isinstance(receipt, HostAdaptiveHopReceiptV2) and not include_host:
            return None
        if isinstance(receipt, AdaptiveHopReceiptV2) and not include_host:
            return None
        origin = receipt.terminal.first_counter
        rate = receipt.plan.geometry.sample_rate_hz
        rows = []
        retained_indices = set(
            getattr(receipt, "retained_visit_indices", range(receipt.complete_visit_count))
        )
        for event in receipt.events:
            end = (
                event.valid_start_counter + receipt.plan.geometry.valid_visit_samples
                if event.visit_index in retained_indices
                else None
            )
            decision = event.decision
            rows.append(
                AdaptiveHopVisitViewV1(
                    visit_index=event.visit_index,
                    target_index=event.target_index,
                    retained=end is not None,
                    invalid_start_seconds=(event.invalid_start_counter - origin) / rate,
                    valid_start_seconds=(event.valid_start_counter - origin) / rate,
                    valid_end_seconds=(end - origin) / rate if end is not None else None,
                    valid_start_counter=event.valid_start_counter,
                    valid_end_counter=end,
                    decision_counter=decision.decision_counter,
                    basis_visit=decision.basis_visit,
                    proposed_target_index=decision.proposed_target,
                    reason=decision.reason,
                    active_mask=decision.active_mask,
                    quiet_mask=decision.quiet_mask,
                    consecutive_misses=decision.consecutive_misses,
                    cooldown_remaining_seconds=decision.cooldown_remaining_samples / rate,
                )
            )
        model: type[AdaptiveHopSessionDetailV1] = AdaptiveHopSessionDetailV1
        fields: dict[str, Any] = {}
        if isinstance(receipt, HostAdaptiveHopReceiptV2):
            model = (
                HostAdaptiveSessionDetailV3
                if isinstance(receipt, HostAdaptiveHopReceiptV3)
                else HostAdaptiveSessionDetailV2
            )
            decision_views: list[HostDecisionViewV1 | HostDecisionViewV2] = []
            for d in receipt.host_decisions:
                worker_elapsed_ms = (
                    (d.completed_monotonic_ns - d.started_monotonic_ns) / 1e6
                    if d.completed_monotonic_ns is not None and d.started_monotonic_ns is not None
                    else None
                )
                feedback_call_ms = (
                    d.feedback_call_elapsed_ns / 1e6
                    if d.feedback_call_elapsed_ns is not None
                    else None
                )
                if isinstance(d, HostDecisionRecordV2):
                    decision_views.append(
                        HostDecisionViewV2(
                            schema_version=2,
                            numerics=d.numerics,
                            visit_index=d.visit_index,
                            health=d.health,
                            failure=d.failure,
                            feedback_outcome=d.feedback_outcome,
                            feedback_disposition=d.feedback_disposition,
                            feedback_error=d.feedback_error,
                            host_result_age_ms=(d.feedback_monotonic_ns - d.submitted_monotonic_ns)
                            / 1e6,
                            worker_elapsed_ms=worker_elapsed_ms,
                            feedback_call_ms=feedback_call_ms,
                        )
                    )
                else:
                    decision_views.append(
                        HostDecisionViewV1(
                            schema_version=1,
                            numerics=d.numerics,
                            visit_index=d.visit_index,
                            health=d.health,
                            failure=d.failure,
                            feedback_outcome=d.feedback_outcome,
                            feedback_disposition=d.feedback_disposition,
                            feedback_error=d.feedback_error,
                            host_result_age_ms=(d.feedback_monotonic_ns - d.submitted_monotonic_ns)
                            / 1e6,
                            worker_elapsed_ms=worker_elapsed_ms,
                            feedback_call_ms=feedback_call_ms,
                        )
                    )
            fields = dict(host_decisions=tuple(decision_views))
        elif isinstance(receipt, AdaptiveHopReceiptV2):
            model = (
                DualRx10mAdaptiveSessionDetailV5
                if isinstance(receipt, AdaptiveHopReceiptV3)
                else EdgeAdaptiveSessionDetailV4
            )
        return model(
            **fields,
            capture=_summary(session),
            source_origin_counter=origin if receipt.source_span_attested else None,
            visits=tuple(rows),
        )

    def glrt(self, session_id: str) -> ScannerGlrtPublicationV1 | None:
        session = self._inspect(session_id)
        if session is None or isinstance(session.manifest.receipt, HostAdaptiveHopReceiptV2):
            return None
        publication = ScannerGlrtStore.open_read_only(self._root).read(session_id)
        if publication is not None:
            validate_glrt_adaptive_binding(
                publication,
                session.manifest.receipt,
                input_manifest_sha256=session.manifest_sha256,
            )
        return publication


class AdaptiveHopGlrtPresentationStore:
    """Explicit adaptive binding behind the existing narrow GLRT reader port."""

    def __init__(self, root: Path):
        self._history = AdaptiveHopPresentationStore(root)

    def detail(self, session_id: str) -> ScannerGlrtPublicationV1 | None:
        return self._history.glrt(session_id)
