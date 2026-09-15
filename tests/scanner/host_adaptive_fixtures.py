"""Synthetic native-10M counters and host evidence; not RF qualification."""

from leo.scanner.adaptive_hop import AdaptiveHopPolicyV1
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostAdaptiveHopTerminalV2,
    HostDecisionConfigurationV1,
    HostDecisionConfigurationV2,
    HostDecisionNumericsV1,
    HostDecisionNumericsV2,
    HostDecisionRecordV1,
    HostDecisionRecordV2,
)
from leo.scanner.models import scheduled_low_band_targets
from leo.scanner.persistent_hop import PersistentHopProfileV1
from leo.scanner.single_rx import SingleRxMultiratePersistentHopPlanV3, SingleRxPersistentHopPlanV2
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


def decision_configuration():
    return HostDecisionConfigurationV1(detector_manifest_sha256="sha256:" + "a" * 64)


def host_plan(*, receiver=0, mode="adaptive"):
    return HostAdaptiveHopPlanV2(
        geometry=SingleRxPersistentHopPlanV2(
            receiver_ids=(receiver,),
            transition_guard_samples=10_000,
            samples_per_block=262_144,
            kernel_buffers=32,
            profiles=tuple(
                PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=t)
                for i, t in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
            ),
        ),
        classification_receiver=receiver,
        policy=AdaptiveHopPolicyV1(mode=mode, generation=71),
        decision=decision_configuration(),
    )


def numerics():
    return HostDecisionNumericsV1(
        outcome="not_detected",
        confirmation_mask=2,
        candidate_supported=True,
        epoch=121,
        fractional_complete=True,
        fractional_offset=0.125,
        cfo_hz=1200,
        exact_score=0.1,
        margin=0.01,
        filter_cpu_ms=3,
        cpu_ms=15,
        wall_ms=16,
        screen_scores=(0.1,) * 6,
    )


def multirate_numerics(rate):
    return HostDecisionNumericsV2(
        **numerics().model_dump(exclude={"schema_version", "supported_start"}),
        source_rate_hz=rate,
        supported_start={15_000_000: 34, 20_000_000: 32}[rate],
    )


def host_receipt(*, receiver=0, mode="adaptive", plan=None, **kwargs):
    plan = host_plan(receiver=receiver, mode=mode) if plan is None else plan
    receiver = plan.classification_receiver

    def factory(**fields):
        records = tuple(
            HostDecisionRecordV1(
                session_id=fields["terminal"].session_id,
                generation=plan.policy.generation,
                stream_generation=fields["stream_generation"],
                visit_index=e.visit_index,
                event_sequence=e.event_sequence,
                receiver_id=receiver,
                target_index=e.target_index,
                valid_start_counter=e.valid_start_counter,
                valid_end_counter_exclusive=e.valid_start_counter + 1_200_000,
                configuration_sha256=plan.decision.configuration_sha256,
                submitted_monotonic_ns=100 + e.visit_index * 126_000_000,
                started_monotonic_ns=200 + e.visit_index * 126_000_000,
                completed_monotonic_ns=16_000_000 + e.visit_index * 126_000_000,
                feedback_monotonic_ns=20_000_000 + e.visit_index * 126_000_000,
                feedback_completed_monotonic_ns=20_002_000 + e.visit_index * 126_000_000,
                numerics=numerics(),
                health="healthy",
                feedback_outcome="not_detected",
                feedback_disposition="accepted",
            )
            for e in fields["events"][: fields["complete_visit_count"]]
        )
        return HostAdaptiveHopReceiptV2(**fields, host_decisions=records)

    return receipt_fixture(
        plan=plan, receipt_factory=factory, terminal_factory=HostAdaptiveHopTerminalV2, **kwargs
    )


def multirate_host_plan(*, rate=20_000_000, mode="adaptive"):
    factor, taps, delay = {
        15_000_000: (6, 201, 100),
        20_000_000: (8, 257, 128),
    }[rate]
    decision = HostDecisionConfigurationV2(
        detector_manifest_sha256="sha256:" + "a" * 64,
        source_rate_hz=rate,
        decimation_factor=factor,
        filter_taps=taps,
        group_delay_source_samples=delay,
    )
    geometry = SingleRxMultiratePersistentHopPlanV3(
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        transition_guard_samples=rate // 1000,
        samples_per_block=262_144,
        kernel_buffers=32,
        profiles=tuple(
            PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=t)
            for i, t in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
        ),
    )
    return HostAdaptiveHopPlanV3(
        geometry=geometry,
        classification_receiver=0,
        policy=AdaptiveHopPolicyV1(mode=mode, generation=71),
        decision=decision,
    )


def multirate_host_receipt(*, rate=20_000_000, mode="adaptive", plan=None, **kwargs):
    plan = multirate_host_plan(rate=rate, mode=mode) if plan is None else plan

    def factory(**fields):
        records = tuple(
            HostDecisionRecordV2(
                session_id=fields["terminal"].session_id,
                generation=plan.policy.generation,
                stream_generation=fields["stream_generation"],
                visit_index=e.visit_index,
                event_sequence=e.event_sequence,
                receiver_id=0,
                source_rate_hz=plan.geometry.sample_rate_hz,
                target_index=e.target_index,
                valid_start_counter=e.valid_start_counter,
                valid_end_counter_exclusive=(
                    e.valid_start_counter + plan.geometry.valid_visit_samples
                ),
                configuration_sha256=plan.decision.configuration_sha256,
                submitted_monotonic_ns=100 + e.visit_index * 126_000_000,
                started_monotonic_ns=200 + e.visit_index * 126_000_000,
                completed_monotonic_ns=16_000_000 + e.visit_index * 126_000_000,
                feedback_monotonic_ns=20_000_000 + e.visit_index * 126_000_000,
                feedback_completed_monotonic_ns=20_002_000 + e.visit_index * 126_000_000,
                numerics=multirate_numerics(plan.geometry.sample_rate_hz),
                health="healthy",
                feedback_outcome="not_detected",
                feedback_disposition="accepted",
            )
            for e in fields["events"][: fields["complete_visit_count"]]
        )
        return HostAdaptiveHopReceiptV3(**fields, host_decisions=records)

    return receipt_fixture(
        plan=plan, receipt_factory=factory, terminal_factory=HostAdaptiveHopTerminalV2, **kwargs
    )
