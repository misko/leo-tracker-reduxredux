"""Durable ten-minute host-adaptive intent, resolved before radio admission."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from leo.contracts.digests import canonical_digest
from leo.scanner.adaptive_hop import AdaptiveHopPolicyV1, AdaptiveMode
from leo.scanner.host_adaptive import (
    HOST_ADAPTIVE_PROFILE_ID,
    HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID,
    HOST_ADAPTIVE_RX0_PROFILE_ID,
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostDecisionConfigurationV1,
    HostDecisionConfigurationV2,
)
from leo.scanner.models import ScannerConfigurationV3, scheduled_low_band_targets
from leo.scanner.persistent_hop import PersistentHopProfileV1
from leo.scanner.schedule import canonical_scheduled_scanner_operation_key
from leo.scanner.single_rx import (
    SingleRxMultiratePersistentHopPlanV3,
    SingleRxScannerConfigurationV4,
    SingleRxScheduledScannerIntentV3,
    compile_single_rx_hop_plan,
)


def canonical_host_adaptive_operation_key(
    scheduled_for: datetime,
    *,
    mode: AdaptiveMode,
    decision: HostDecisionConfigurationV1 | HostDecisionConfigurationV2,
    profile_id: str = HOST_ADAPTIVE_PROFILE_ID,
) -> str:
    if mode not in ("shadow", "adaptive"):
        raise ValueError("host adaptive mode must be shadow or adaptive")
    decision_model = (
        HostDecisionConfigurationV2
        if profile_id == HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID
        else HostDecisionConfigurationV1
    )
    decision = decision_model.model_validate(decision)
    slot = canonical_scheduled_scanner_operation_key(scheduled_for)
    if profile_id not in (
        HOST_ADAPTIVE_PROFILE_ID,
        HOST_ADAPTIVE_RX0_PROFILE_ID,
        HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID,
    ):
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


def host_adaptive_sample_rate(
    operation_key: str, radio_serial: str
) -> Literal[15_000_000, 20_000_000]:
    """Stable uniform choice that survives retries and process restarts."""

    identity = (
        f"{HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID}\0{radio_serial}\0{operation_key}"
    ).encode()
    return 20_000_000 if hashlib.sha256(identity).digest()[0] & 1 else 15_000_000


class HostAdaptiveMultirateScannerConfigurationV5(ScannerConfigurationV3):
    schema_version: Literal[5] = 5  # type: ignore[assignment]
    band_plan_id: Literal["starlink-low-ch1-ch4-pilot-centered-single-rx-v1"] = (  # type: ignore[assignment]
        "starlink-low-ch1-ch4-pilot-centered-single-rx-v1"  # type: ignore[assignment]
    )
    sample_rate_hz: Literal[15_000_000, 20_000_000]
    bandwidth_hz: Literal[15_000_000, 20_000_000]
    receiver_ids: tuple[Literal[0]] = Field(default=(0,))
    dwell_ms: Literal[120] = 120

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if (
            self.sample_rate_hz != self.bandwidth_hz
            or self.receiver_ids != (0,)
            or self.targets
            != scheduled_low_band_targets(bandwidth_hz=5_000_000, lnb_lo_hz=self.lnb_lo_hz)
        ):
            raise ValueError("15/20 MS/s adaptive configuration changed RX0 or target geometry")
        return self


class HostAdaptiveRx0MultirateScheduledScannerIntentV6(SingleRxScheduledScannerIntentV3):
    schema_version: Literal[6] = 6  # type: ignore[assignment]
    policy_id: Literal["adaptive-single-rx0-random-15m-20m-300s-v1"] = (  # type: ignore[assignment]
        HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID  # type: ignore[assignment]
    )
    configuration: HostAdaptiveMultirateScannerConfigurationV5  # type: ignore[assignment]
    adaptive_policy: AdaptiveHopPolicyV1
    decision: HostDecisionConfigurationV2

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("host adaptive scheduled clock must be timezone-aware")
        if self.interval_seconds != 600:
            raise ValueError("multirate host adaptive intent requires a ten-minute interval")
        slot_key = canonical_scheduled_scanner_operation_key(self.scheduled_for)
        expected_key = canonical_host_adaptive_operation_key(
            self.scheduled_for,
            mode=self.adaptive_policy.mode,
            decision=self.decision,
            profile_id=self.policy_id,
        )
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if (
            self.operation_key != expected_key
            or self.cadence_ordinal != int(seconds // 600)
            or not math.isclose(seconds, self.cadence_ordinal * 600, rel_tol=0, abs_tol=1e-6)
            or self.adaptive_policy.generation != self.cadence_ordinal + 1
            or self.configuration.receiver_ids != (0,)
            or self.configuration.sample_rate_hz
            != host_adaptive_sample_rate(slot_key, self.radio_serial)
            or self.decision.source_rate_hz != self.configuration.sample_rate_hz
        ):
            raise ValueError("multirate host adaptive intent differs from its durable slot")
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


def compile_host_adaptive_rx0_multirate_scanner_intent(
    *,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    mode: AdaptiveMode,
    decision_manifest_sha256: str,
    maximum_lateness_seconds: float,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> HostAdaptiveRx0MultirateScheduledScannerIntentV6:
    slot_key = canonical_scheduled_scanner_operation_key(scheduled_for)
    rate = host_adaptive_sample_rate(slot_key, radio_serial)
    decision = HostDecisionConfigurationV2(
        detector_manifest_sha256=decision_manifest_sha256,
        source_rate_hz=rate,
        decimation_factor=6 if rate == 15_000_000 else 8,
        filter_taps=201 if rate == 15_000_000 else 257,
        group_delay_source_samples=100 if rate == 15_000_000 else 128,
    )
    key = canonical_host_adaptive_operation_key(
        scheduled_for,
        mode=mode,
        decision=decision,
        profile_id=HOST_ADAPTIVE_RX0_MULTIRATE_PROFILE_ID,
    )
    scheduled = scheduled_for.astimezone(UTC)
    ordinal = int(scheduled.timestamp() // 600)
    configuration = HostAdaptiveMultirateScannerConfigurationV5(
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        receiver_ids=(0,),
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=5_000_000),
    )
    candidate = HostAdaptiveRx0MultirateScheduledScannerIntentV6.model_construct(
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
    return HostAdaptiveRx0MultirateScheduledScannerIntentV6.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
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
    intent: HostAdaptiveScheduledScannerIntentV4
    | HostAdaptiveRx0ScheduledScannerIntentV5
    | HostAdaptiveRx0MultirateScheduledScannerIntentV6,
    *,
    transition_guard_us: int = 1000,
    kernel_buffers: int = 32,
    samples_per_block: int = 262_144,
) -> HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3:
    intent = type(intent).model_validate(intent.model_dump())
    if isinstance(intent, HostAdaptiveRx0MultirateScheduledScannerIntentV6):
        configuration = intent.configuration
        geometry = SingleRxMultiratePersistentHopPlanV3(
            sample_rate_hz=configuration.sample_rate_hz,
            bandwidth_hz=configuration.bandwidth_hz,
            receiver_ids=(0,),
            gain_db=configuration.gain_db,
            transition_guard_samples=(
                configuration.sample_rate_hz * transition_guard_us // 1_000_000
            ),
            kernel_buffers=kernel_buffers,
            samples_per_block=samples_per_block,
            profiles=tuple(
                PersistentHopProfileV1(
                    target_index=i, fastlock_profile_index=i, target=target
                )
                for i, target in enumerate(configuration.targets)
            ),
        )
        return HostAdaptiveHopPlanV3(
            geometry=geometry,
            policy=intent.adaptive_policy,
            classification_receiver=0,
            decision=intent.decision,
        )
    single_geometry = compile_single_rx_hop_plan(
        intent,
        transition_guard_us=transition_guard_us,
        kernel_buffers=kernel_buffers,
        samples_per_block=samples_per_block,
    )
    return HostAdaptiveHopPlanV2(
        geometry=single_geometry,
        policy=intent.adaptive_policy,
        classification_receiver=intent.configuration.receiver_ids[0],
        decision=intent.decision,
    )
