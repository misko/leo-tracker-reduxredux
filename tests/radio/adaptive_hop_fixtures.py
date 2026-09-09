"""Actual PPU value types around synthetic application evidence; never RF."""

import dataclasses
from threading import get_ident

import numpy as np
from pluto_plus.adaptive_hop import (
    AdaptiveHopChoiceV2,
    AdaptiveHopMode,
    AdaptiveHopRequestV2,
    AdaptiveHopStatusV2,
)
from pluto_plus.adaptive_hop_client import AdaptiveHopCaptureReceiptV2
from pluto_plus.adaptive_hop_stream import (
    AdaptiveHopSampledVisitV2,
    AdaptiveHopStreamReceiptV2,
    AdaptiveHopVisitV2,
)
from pluto_plus.persistent_hop import (
    PersistentHopEventFlag,
    PersistentHopEventKind,
    PersistentHopEventV1,
    PersistentHopHostLifecycleReceiptV1,
    PersistentHopReceiverSettingsV1,
    PersistentHopSessionState,
    PersistentHopStatusFlag,
    PersistentHopStatusV1,
    PersistentHopTargetCoverageV1,
    PersistentHopTerminalReason,
)

from leo.radio.adaptive_hop_mapping import load_adaptive_policy
from leo.radio.pluto_persistent_hop import _load_plan
from tests.scanner.adaptive_hop_fixtures import block_fixture


def upstream_receipt(receipt):
    plan = _load_plan(receipt.plan.geometry)
    # Substitute hardware-prepared CRCs, as the real backend does before OPEN.
    plan = dataclasses.replace(
        plan, profiles=tuple(dataclasses.replace(p, profile_crc32=1) for p in plan.profiles)
    )
    request = AdaptiveHopRequestV2(
        plan.request(session_id=receipt.terminal.session_id), load_adaptive_policy(receipt.plan)
    )
    events, choices = [], []
    reasons = ("warmup", "weighted", "exploration", "none_active", "fault_fallback")
    for event in receipt.events:
        events.append(
            PersistentHopEventV1(
                event_sequence=event.event_sequence,
                dwell_index=event.visit_index,
                transition_before_counter=event.transition_before_counter,
                transition_after_counter=event.transition_after_counter,
                invalid_start_counter=event.invalid_start_counter,
                invalid_end_counter_exclusive=event.valid_start_counter,
                from_profile_index=255
                if event.from_profile_index is None
                else event.from_profile_index,
                to_profile_index=event.target_index,
                kind=PersistentHopEventKind.RETUNE
                if event.visit_index
                else PersistentHopEventKind.STARTUP,
                flags=PersistentHopEventFlag(3),
                fastlock_slot=event.fastlock_slot,
                actual_lo_frequency_hz=event.actual_lo_frequency_hz,
                actual_if_offset_hz=event.actual_if_offset_hz,
                device_event_id=event.device_event_id,
            )
        )
        decision = event.decision
        choices.append(
            AdaptiveHopChoiceV2(
                decision_counter=decision.decision_counter,
                basis_visit=(1 << 64) - 1 if decision.basis_visit is None else decision.basis_visit,
                cooldown_remaining_samples=decision.cooldown_remaining_samples,
                generation=decision.generation,
                proposed_target=decision.proposed_target,
                reason=reasons.index(decision.reason),
                active_mask=decision.active_mask,
                quiet_mask=decision.quiet_mask,
                consecutive_misses=decision.consecutive_misses,
                mode=AdaptiveHopMode[decision.mode.upper()],
            )
        )
    terminal = receipt.terminal
    fields = {f.name: getattr(terminal, f.name) for f in dataclasses.fields(PersistentHopStatusV1)}
    fields.update(
        state=PersistentHopSessionState[terminal.state.upper()],
        reason=PersistentHopTerminalReason[
            "PLAN_COMPLETE" if terminal.reason == "complete" else "CLIENT_CLOSE"
        ],
        flags=PersistentHopStatusFlag(terminal.flags),
        active_profile_index=255
        if terminal.active_profile_index is None
        else terminal.active_profile_index,
        restored_profile_index=255,
    )
    visits = tuple(
        AdaptiveHopVisitV2(
            events[i],
            choices[i],
            plan.profiles[e.event.target_index],
            e.valid_end_counter_exclusive,
        )
        for i, e in enumerate(receipt.visits)
    )
    settings = receipt.restoration.original_settings
    original = PersistentHopReceiverSettingsV1(
        center_frequency_hz=settings.center_frequency_hz,
        sample_rate_hz=settings.sample_rate_hz,
        bandwidth_hz=settings.bandwidth_hz,
        channels=settings.receiver_ids,
        gain_modes=(settings.gain_mode.value,) * 2,
        gain_db=tuple(g.gain_db for g in settings.gains),
    )
    stream = AdaptiveHopStreamReceiptV2(
        request=request,
        status=AdaptiveHopStatusV2(PersistentHopStatusV1(**fields)),
        stream_generation=receipt.stream_generation,
        visits=visits,
        events=tuple(events),
        choices=tuple(choices),
        target_coverage=tuple(
            PersistentHopTargetCoverageV1(
                target_index=c.target_index,
                target=plan.profiles[c.target_index].target,
                visit_count=c.visit_count,
                valid_sample_count=c.valid_sample_count,
            )
            for c in receipt.target_coverage
        ),
        **{
            name: getattr(receipt, name)
            for name in (
                "valid_sample_count",
                "transition_invalid_sample_count",
                "unclassified_sample_count",
                "unreceived_tail_sample_count",
                "duty_denominator_sample_count",
                "valid_duty_ppm",
                "duty_target_met",
                "source_span_attested",
            )
        },
    )
    return AdaptiveHopCaptureReceiptV2(
        stream,
        receipt.radio_serial,
        receipt.radio_uri,
        PersistentHopHostLifecycleReceiptV1(original, original, True, True),
        None,
        receipt.kernel_buffers_requested,
        receipt.kernel_buffers_readback,
        None,
    )


class UpstreamSession:
    """Synthetic producer with separately retained terminal completed visits."""

    def __init__(self, receipt, *, terminal_visits=1):
        self.source = receipt
        self.receipt = upstream_receipt(receipt)
        self.start_clock_bracket = None
        self.terminal_count = min(terminal_visits, receipt.complete_visit_count)
        self.closed = False
        self.next_index = 0
        self.threads = []

    def sampled(self, index):
        block = block_fixture(self.source, index)
        return AdaptiveHopSampledVisitV2(
            self.receipt.stream.visits[index], np.ascontiguousarray(block.samples.T)
        )

    def visits(self):
        self.threads.append(get_ident())
        while self.next_index < self.source.complete_visit_count - self.terminal_count:
            index = self.next_index
            self.next_index += 1
            yield self.sampled(index)

    def close(self):
        self.threads.append(get_ident())
        self.closed = True
        return self.receipt

    def take_terminal_visits(self):
        assert self.closed
        self.threads.append(get_ident())
        result = tuple(
            self.sampled(i) for i in range(self.next_index, self.source.complete_visit_count)
        )
        self.next_index = self.source.complete_visit_count
        return result


class Client:
    def __init__(self, upstream):
        self.upstream = upstream
        self.arguments = None

    def start(self, plan, *, session_id, policy, tandem_request):
        self.arguments = (plan, session_id, policy, tandem_request)
        return self.upstream
