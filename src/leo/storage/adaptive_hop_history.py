"""Read-only presentation using public adaptive manifests, never IQ decoding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.scanner.adaptive_hop_history import (
    AdaptiveHopCoverageV1,
    AdaptiveHopHistoryItemV1,
    AdaptiveHopHistoryPageV1,
    AdaptiveHopSessionDetailV1,
    AdaptiveHopVisitViewV1,
)
from leo.scanner.glrt_publication import validate_glrt_adaptive_binding
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
    return AdaptiveHopHistoryItemV1(
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
        and receipt.duty_target_met,
        terminal_state=receipt.terminal.state,
        fallback_choices=sum(e.decision.reason == "fault_fallback" for e in receipt.events),
        target_coverage=tuple(coverage),
    )


class AdaptiveHopPresentationStore:
    """Per-request pinned read-only handles; no new directories or IQ reads."""

    def __init__(self, root: Path):
        self._root = root

    def page(self, *, cursor: int, limit: int) -> AdaptiveHopHistoryPageV1:
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("adaptive history pagination is out of bounds")
        store = AdaptiveHopIqStore(self._root, read_only=True)
        try:
            # Keep only ordering keys, not every scan's up-to-2,500-event manifest.
            sessions = [(s.manifest.finalized_utc_ns, s.session_id) for s in store.iter_sessions()]
            sessions.sort(reverse=True)
            items = tuple(
                _summary(store.inspect(key)) for _, key in sessions[cursor : cursor + limit]
            )
        finally:
            store.close()
        return AdaptiveHopHistoryPageV1(
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
        session = self._inspect(session_id)
        if session is None:
            return None
        receipt = session.manifest.receipt
        origin = receipt.terminal.first_counter
        rate = receipt.plan.geometry.sample_rate_hz
        rows = []
        for event in receipt.events:
            end = (
                event.valid_start_counter + receipt.plan.geometry.valid_visit_samples
                if event.visit_index < receipt.complete_visit_count
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
        return AdaptiveHopSessionDetailV1(
            capture=_summary(session),
            source_origin_counter=origin if receipt.source_span_attested else None,
            visits=tuple(rows),
        )

    def glrt(self, session_id: str) -> ScannerGlrtPublicationV1 | None:
        session = self._inspect(session_id)
        if session is None:
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
