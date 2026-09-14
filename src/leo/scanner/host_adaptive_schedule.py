"""Durable ten-minute host-adaptive intent, resolved before radio admission."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, field_validator, model_validator

from leo.contracts.digests import canonical_digest
from leo.scanner.adaptive_hop import AdaptiveHopPolicyV1, AdaptiveMode
from leo.scanner.host_adaptive import (
    HOST_ADAPTIVE_PROFILE_ID,
    HOST_ADAPTIVE_RX0_PROFILE_ID,
    HostAdaptiveHopPlanV2,
    HostDecisionConfigurationV1,
)
from leo.scanner.models import scheduled_low_band_targets
from leo.scanner.schedule import canonical_scheduled_scanner_operation_key
from leo.scanner.single_rx import (
    SingleRxScannerConfigurationV4,
    SingleRxScheduledScannerIntentV3,
    compile_single_rx_hop_plan,
)


def canonical_host_adaptive_operation_key(
    scheduled_for: datetime,
    *,
    mode: AdaptiveMode,
    decision: HostDecisionConfigurationV1,
    profile_id: str = HOST_ADAPTIVE_PROFILE_ID,
) -> str:
    if mode not in ("shadow", "adaptive"):
        raise ValueError("host adaptive mode must be shadow or adaptive")
    decision = HostDecisionConfigurationV1.model_validate(decision)
    slot = canonical_scheduled_scanner_operation_key(scheduled_for)
    if profile_id not in (HOST_ADAPTIVE_PROFILE_ID, HOST_ADAPTIVE_RX0_PROFILE_ID):
        raise ValueError("unknown host adaptive profile")
    return f"{slot}:{profile_id}:{mode}:{decision.configuration_sha256[7:]}"


def host_adaptive_receiver(operation_key: str, radio_serial: str) -> Literal[0, 1]:
    identity = f"{HOST_ADAPTIVE_PROFILE_ID}\0{radio_serial}\0{operation_key}".encode()
    return 1 if hashlib.sha256(identity).digest()[0] & 1 else 0


class HostAdaptiveScheduledScannerIntentV4(SingleRxScheduledScannerIntentV3):
    model_config = ConfigDict(revalidate_instances="always")
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    policy_id: Literal["adaptive-single-rx-random-10m-300s-v1"] = HOST_ADAPTIVE_PROFILE_ID  # type: ignore[assignment]
    adaptive_policy: AdaptiveHopPolicyV1
    decision: HostDecisionConfigurationV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _major_is_exact(cls, value):
        if type(value) is not int:
            raise ValueError("host adaptive intent schema version must be an exact integer")
        return value

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        SingleRxScannerConfigurationV4.model_validate(self.configuration.model_dump())
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("host adaptive scheduled clock must be timezone-aware")
        if self.interval_seconds != 600 or self.operation_key != (
            canonical_host_adaptive_operation_key(
                self.scheduled_for,
                mode=self.adaptive_policy.mode,
                decision=self.decision,
                profile_id=self.policy_id,
            )
        ):
            raise ValueError("host adaptive intent requires its mode-bound ten-minute operation")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if self.cadence_ordinal != int(seconds // 600) or not math.isclose(
            seconds, self.cadence_ordinal * 600, rel_tol=0, abs_tol=1e-6
        ):
            raise ValueError("host adaptive intent is not aligned to its cadence slot")
        if self.adaptive_policy.generation != self.cadence_ordinal + 1:
            raise ValueError("host adaptive policy generation differs from its durable slot")
        expected_receiver = (
            0
            if self.policy_id == HOST_ADAPTIVE_RX0_PROFILE_ID
            else host_adaptive_receiver(self.operation_key, self.radio_serial)
        )
        if self.configuration.receiver_ids != (expected_receiver,):
            raise ValueError("host adaptive receiver differs from durable operation identity")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("host adaptive intent digest does not match content")
        return self


class HostAdaptiveRx0ScheduledScannerIntentV5(SingleRxScheduledScannerIntentV3):
    """New persisted profile whose acquisition input is always physical RX0."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    policy_id: Literal["adaptive-single-rx0-10m-300s-v1"] = "adaptive-single-rx0-10m-300s-v1"  # type: ignore[assignment]
    adaptive_policy: AdaptiveHopPolicyV1
    decision: HostDecisionConfigurationV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _major_is_exact(cls, value):
        if type(value) is not int:
            raise ValueError("host adaptive intent schema version must be an exact integer")
        return value

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        SingleRxScannerConfigurationV4.model_validate(self.configuration.model_dump())
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("host adaptive scheduled clock must be timezone-aware")
        if self.interval_seconds != 600 or self.operation_key != (
            canonical_host_adaptive_operation_key(
                self.scheduled_for,
                mode=self.adaptive_policy.mode,
                decision=self.decision,
                profile_id=HOST_ADAPTIVE_RX0_PROFILE_ID,
            )
        ):
            raise ValueError("host adaptive intent requires its mode-bound ten-minute operation")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if self.cadence_ordinal != int(seconds // 600) or not math.isclose(
            seconds, self.cadence_ordinal * 600, rel_tol=0, abs_tol=1e-6
        ):
            raise ValueError("host adaptive intent is not aligned to its cadence slot")
        if self.adaptive_policy.generation != self.cadence_ordinal + 1:
            raise ValueError("host adaptive policy generation differs from its durable slot")
        if self.configuration.receiver_ids != (0,):
            raise ValueError("fixed-RX0 adaptive intent changed physical receiver")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("host adaptive intent digest does not match content")
        return self


def compile_host_adaptive_scanner_intent(
    *,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    mode: AdaptiveMode,
    decision: HostDecisionConfigurationV1,
    maximum_lateness_seconds: float,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> HostAdaptiveScheduledScannerIntentV4:
    return _compile_host_adaptive_scanner_intent(
        intent_model=HostAdaptiveScheduledScannerIntentV4,
        profile_id=HOST_ADAPTIVE_PROFILE_ID,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=scheduled_for,
        mode=mode,
        decision=decision,
        maximum_lateness_seconds=maximum_lateness_seconds,
        gain_db=gain_db,
        margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
    )


def compile_host_adaptive_rx0_scanner_intent(
    *,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    mode: AdaptiveMode,
    decision: HostDecisionConfigurationV1,
    maximum_lateness_seconds: float,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> HostAdaptiveRx0ScheduledScannerIntentV5:
    return _compile_host_adaptive_scanner_intent(
        intent_model=HostAdaptiveRx0ScheduledScannerIntentV5,
        profile_id=HOST_ADAPTIVE_RX0_PROFILE_ID,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=scheduled_for,
        mode=mode,
        decision=decision,
        maximum_lateness_seconds=maximum_lateness_seconds,
        gain_db=gain_db,
        margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
    )


def _compile_host_adaptive_scanner_intent(
    *,
    intent_model: type[HostAdaptiveScheduledScannerIntentV4]
    | type[HostAdaptiveRx0ScheduledScannerIntentV5],
    profile_id: str,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    mode: AdaptiveMode,
    decision: HostDecisionConfigurationV1,
    maximum_lateness_seconds: float,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
):
    key = canonical_host_adaptive_operation_key(
        scheduled_for, mode=mode, decision=decision, profile_id=profile_id
    )
    scheduled = scheduled_for.astimezone(UTC)
    ordinal = int(scheduled.timestamp() // 600)
    configuration = SingleRxScannerConfigurationV4(
        receiver_ids=(0,)
        if profile_id == HOST_ADAPTIVE_RX0_PROFILE_ID
        else ((1,) if host_adaptive_receiver(key, radio_serial) else (0,)),
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=5_000_000),
    )
    # Only the digest is deferred; the returned contract is fully validated.
    candidate = intent_model.model_construct(
        intent_digest="sha256:" + "0" * 64,
        operation_key=key,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=scheduled,
        cadence_ordinal=ordinal,
        interval_seconds=600,
        maximum_lateness_seconds=maximum_lateness_seconds,
        configuration=configuration,
        adaptive_policy=AdaptiveHopPolicyV1(mode=mode, generation=ordinal + 1),
        decision=decision,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return intent_model.model_validate({**document, "intent_digest": canonical_digest(document)})


def compile_host_adaptive_hop_plan(
    intent: HostAdaptiveScheduledScannerIntentV4 | HostAdaptiveRx0ScheduledScannerIntentV5,
    *,
    transition_guard_us: int = 1000,
    kernel_buffers: int = 32,
    samples_per_block: int = 262_144,
) -> HostAdaptiveHopPlanV2:
    intent = type(intent).model_validate(intent.model_dump())
    geometry = compile_single_rx_hop_plan(
        intent,
        transition_guard_us=transition_guard_us,
        kernel_buffers=kernel_buffers,
        samples_per_block=samples_per_block,
    )
    return HostAdaptiveHopPlanV2(
        geometry=geometry,
        policy=intent.adaptive_policy,
        classification_receiver=intent.configuration.receiver_ids[0],
        decision=intent.decision,
    )
