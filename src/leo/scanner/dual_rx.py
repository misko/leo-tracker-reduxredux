"""Fixed 2.5 MS/s dual-receiver adaptive scanner profile."""

from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime
from typing import ClassVar, Literal, Self, cast

from pydantic import model_validator

from leo.contracts.digests import canonical_digest
from leo.scanner.models import ScannerConfigurationV3, scheduled_low_band_targets
from leo.scanner.persistent_hop import (
    DualRxPersistentHopPlanV2,
    PersistentHopPlanV1,
    PersistentHopProfileV1,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.schedule import (
    ScheduledScannerRunIntentV1,
    canonical_scheduled_scanner_operation_key,
)

LEGACY_DUAL_RX_ADAPTIVE_2P5_PROFILE_ID = "adaptive-dual-rx-2p5m-300s-v1"
DUAL_RX_ADAPTIVE_2P5_PROFILE_ID = "adaptive-dual-rx-2p5m-300s-360s-v1"
DUAL_RX_EDGE_ADAPTIVE_2P5_PROFILE_ID = "adaptive-dual-rx-2p5m-edge-random-300s-360s-v1"
DUAL_RX_EDGE_ADAPTIVE_10M_PROFILE_ID = "adaptive-dual-rx-10m-edge-random-300s-360s-v1"
DUAL_RX_RATE_HZ: Literal[2_500_000] = 2_500_000
DUAL_RX_10M_RATE_HZ: Literal[10_000_000] = 10_000_000


class DualRxAdaptive2p5ScannerConfigurationV7(ScannerConfigurationV3):
    schema_version: Literal[7] = 7  # type: ignore[assignment]
    band_plan_id: Literal["starlink-low-ch1-ch4-dual-rx-2p5m-v1"] = (  # type: ignore[assignment]
        "starlink-low-ch1-ch4-dual-rx-2p5m-v1"  # type: ignore[assignment]
    )
    sample_rate_hz: Literal[2_500_000] = DUAL_RX_RATE_HZ
    bandwidth_hz: Literal[2_500_000] = DUAL_RX_RATE_HZ
    receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    dwell_ms: Literal[120] = 120

    @model_validator(mode="after")
    def _fixed_geometry(self) -> Self:
        if not math.isfinite(self.gain_db):
            raise ValueError("dual-RX scanner gain must be finite")
        if self.targets != scheduled_low_band_targets(
            bandwidth_hz=DUAL_RX_RATE_HZ, lnb_lo_hz=self.lnb_lo_hz
        ):
            raise ValueError("dual-RX 2.5 MS/s scanner targets must remain canonical")
        return self


class DualRxAdaptive2p5ScheduledScannerIntentV7(ScheduledScannerRunIntentV1):
    schema_version: Literal[7] = 7  # type: ignore[assignment]
    policy_id: Literal["adaptive-dual-rx-2p5m-300s-v1"] = (  # type: ignore[assignment]
        cast(Literal["adaptive-dual-rx-2p5m-300s-v1"], DUAL_RX_ADAPTIVE_2P5_PROFILE_ID)  # type: ignore[assignment]
    )
    required_interval_seconds: ClassVar[int] = 600
    run_duration_seconds: Literal[300] = 300
    configuration: DualRxAdaptive2p5ScannerConfigurationV7

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        if self.interval_seconds != self.required_interval_seconds or self.operation_key != (
            canonical_scheduled_scanner_operation_key(self.scheduled_for)
        ):
            raise ValueError("dual-RX profile requires a canonical ten-minute operation")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if self.cadence_ordinal != int(seconds // self.interval_seconds) or not math.isclose(
            seconds, self.cadence_ordinal * self.interval_seconds, rel_tol=0, abs_tol=1e-6
        ):
            raise ValueError("dual-RX scanner intent is not aligned to its cadence slot")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("dual-RX scanner intent digest does not match content")
        return self


class DualRxAdaptive2p5ScheduledScannerIntentV8(ScheduledScannerRunIntentV1):
    """Six-minute cadence without changing the published V7 contract."""

    schema_version: Literal[8] = 8  # type: ignore[assignment]
    policy_id: Literal["adaptive-dual-rx-2p5m-300s-360s-v1"] = (  # type: ignore[assignment]
        cast(Literal["adaptive-dual-rx-2p5m-300s-360s-v1"], DUAL_RX_ADAPTIVE_2P5_PROFILE_ID)  # type: ignore[assignment]
    )
    required_interval_seconds: ClassVar[int] = 360
    run_duration_seconds: Literal[300] = 300
    configuration: DualRxAdaptive2p5ScannerConfigurationV7

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        if self.interval_seconds != self.required_interval_seconds or self.operation_key != (
            canonical_scheduled_scanner_operation_key(self.scheduled_for)
        ):
            raise ValueError("dual-RX profile requires a canonical six-minute operation")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if self.cadence_ordinal != int(seconds // self.interval_seconds) or not math.isclose(
            seconds, self.cadence_ordinal * self.interval_seconds, rel_tol=0, abs_tol=1e-6
        ):
            raise ValueError("dual-RX scanner intent is not aligned to its cadence slot")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("dual-RX scanner intent digest does not match content")
        return self


def _edge_from_random_bit(bit: int) -> Literal["lower", "upper"]:
    if type(bit) is not int or bit not in (0, 1):
        raise ValueError("dual-RX edge choice requires one exact random bit")
    return "upper" if bit else "lower"


def choose_dual_rx_edge() -> Literal["lower", "upper"]:
    """One cryptographic Bernoulli(0.5) draw, persisted in the scan intent."""

    return _edge_from_random_bit(secrets.randbits(1))


class DualRxAdaptive2p5EdgeScannerConfigurationV8(DualRxAdaptive2p5ScannerConfigurationV7):
    schema_version: Literal[8] = 8  # type: ignore[assignment]
    band_plan_id: Literal["starlink-low-ch1-ch4-one-edge-dual-rx-2p5m-v1"] = (  # type: ignore[assignment]
        "starlink-low-ch1-ch4-one-edge-dual-rx-2p5m-v1"  # type: ignore[assignment]
    )
    selected_edge: Literal["lower", "upper"]


class DualRxAdaptive2p5ScheduledScannerIntentV9(ScheduledScannerRunIntentV1):
    """One durable lower-or-upper edge choice for an entire six-minute slot."""

    schema_version: Literal[9] = 9  # type: ignore[assignment]
    policy_id: Literal["adaptive-dual-rx-2p5m-edge-random-300s-360s-v1"] = (  # type: ignore[assignment]
        cast(  # type: ignore[assignment]
            Literal["adaptive-dual-rx-2p5m-edge-random-300s-360s-v1"],
            DUAL_RX_EDGE_ADAPTIVE_2P5_PROFILE_ID,
        )  # type: ignore[assignment]
    )
    required_interval_seconds: ClassVar[int] = 360
    run_duration_seconds: Literal[300] = 300
    configuration: DualRxAdaptive2p5EdgeScannerConfigurationV8

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if (
            self.interval_seconds != self.required_interval_seconds
            or self.operation_key != canonical_scheduled_scanner_operation_key(self.scheduled_for)
            or self.cadence_ordinal != int(seconds // self.interval_seconds)
            or not math.isclose(
                seconds,
                self.cadence_ordinal * self.interval_seconds,
                rel_tol=0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("dual-RX one-edge intent differs from its durable slot")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("dual-RX one-edge intent digest does not match content")
        return self


class DualRxAdaptive10mEdgeScannerConfigurationV10(ScannerConfigurationV3):
    """New contract for native 10 MS/s dual-receiver one-edge capture."""

    schema_version: Literal[10] = 10  # type: ignore[assignment]
    band_plan_id: Literal["starlink-low-ch1-ch4-one-edge-dual-rx-10m-v1"] = (  # type: ignore[assignment]
        cast(  # type: ignore[assignment]
            Literal["starlink-low-ch1-ch4-one-edge-dual-rx-10m-v1"],
            "starlink-low-ch1-ch4-one-edge-dual-rx-10m-v1",
        )
    )
    sample_rate_hz: Literal[10_000_000] = DUAL_RX_10M_RATE_HZ
    bandwidth_hz: Literal[10_000_000] = DUAL_RX_10M_RATE_HZ
    receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    dwell_ms: Literal[120] = 120
    selected_edge: Literal["lower", "upper"]

    @model_validator(mode="after")
    def _fixed_geometry(self) -> Self:
        if not math.isfinite(self.gain_db):
            raise ValueError("dual-RX 10 MS/s scanner gain must be finite")
        if self.targets != scheduled_low_band_targets(
            bandwidth_hz=DUAL_RX_10M_RATE_HZ, lnb_lo_hz=self.lnb_lo_hz
        ):
            raise ValueError("dual-RX 10 MS/s scanner targets must remain canonical")
        return self


class DualRxAdaptive10mScheduledScannerIntentV10(ScheduledScannerRunIntentV1):
    schema_version: Literal[10] = 10  # type: ignore[assignment]
    policy_id: Literal["adaptive-dual-rx-10m-edge-random-300s-360s-v1"] = (  # type: ignore[assignment]
        cast(  # type: ignore[assignment]
            Literal["adaptive-dual-rx-10m-edge-random-300s-360s-v1"],
            DUAL_RX_EDGE_ADAPTIVE_10M_PROFILE_ID,
        )
    )
    run_duration_seconds: Literal[300] = 300
    configuration: DualRxAdaptive10mEdgeScannerConfigurationV10

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled scanner clock must be timezone-aware")
        seconds = self.scheduled_for.astimezone(UTC).timestamp()
        if (
            self.interval_seconds != 360
            or self.operation_key != canonical_scheduled_scanner_operation_key(self.scheduled_for)
            or self.cadence_ordinal != int(seconds // 360)
            or not math.isclose(seconds, self.cadence_ordinal * 360, rel_tol=0, abs_tol=1e-6)
        ):
            raise ValueError("dual-RX 10 MS/s intent differs from its durable slot")
        if self.intent_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"intent_digest"})
        ):
            raise ValueError("dual-RX 10 MS/s intent digest does not match content")
        return self


def compile_dual_rx_adaptive_2p5_scanner_intent(
    *,
    operation_key: str,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    interval_seconds: float,
    maximum_lateness_seconds: float,
    run_duration_seconds: float,
    dwell_ms: int,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> DualRxAdaptive2p5ScheduledScannerIntentV9:
    if interval_seconds != 360 or run_duration_seconds != 300 or dwell_ms != 120:
        raise ValueError("dual-RX profile requires 360s cadence and 300s/120ms hopping")
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("scheduled scanner clock must be timezone-aware")
    canonical = scheduled_for.astimezone(UTC)
    configuration = DualRxAdaptive2p5EdgeScannerConfigurationV8(
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=DUAL_RX_RATE_HZ),
        selected_edge=choose_dual_rx_edge(),
    )
    candidate = DualRxAdaptive2p5ScheduledScannerIntentV9.model_construct(
        intent_digest="sha256:" + "0" * 64,
        operation_key=operation_key,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=canonical,
        cadence_ordinal=int(canonical.timestamp() // interval_seconds),
        interval_seconds=360.0,
        maximum_lateness_seconds=maximum_lateness_seconds,
        run_duration_seconds=300,
        configuration=configuration,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return DualRxAdaptive2p5ScheduledScannerIntentV9.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def compile_dual_rx_adaptive_10m_scanner_intent(
    *,
    operation_key: str,
    radio_id: str,
    radio_serial: str,
    scheduled_for: datetime,
    interval_seconds: float,
    maximum_lateness_seconds: float,
    run_duration_seconds: float,
    dwell_ms: int,
    gain_db: float,
    margin_gate: float,
    maximum_acquisition_candidates: int,
) -> DualRxAdaptive10mScheduledScannerIntentV10:
    if interval_seconds != 360 or run_duration_seconds != 300 or dwell_ms != 120:
        raise ValueError("dual-RX 10 MS/s profile requires 360s cadence and 300s/120ms hopping")
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise ValueError("scheduled scanner clock must be timezone-aware")
    canonical = scheduled_for.astimezone(UTC)
    configuration = DualRxAdaptive10mEdgeScannerConfigurationV10(
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        maximum_acquisition_candidates=maximum_acquisition_candidates,
        targets=scheduled_low_band_targets(bandwidth_hz=DUAL_RX_10M_RATE_HZ),
        selected_edge=choose_dual_rx_edge(),
    )
    candidate = DualRxAdaptive10mScheduledScannerIntentV10.model_construct(
        intent_digest="sha256:" + "0" * 64,
        operation_key=operation_key,
        radio_id=radio_id,
        radio_serial=radio_serial,
        scheduled_for=canonical,
        cadence_ordinal=int(canonical.timestamp() // 360),
        interval_seconds=360.0,
        maximum_lateness_seconds=maximum_lateness_seconds,
        run_duration_seconds=300,
        configuration=configuration,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return DualRxAdaptive10mScheduledScannerIntentV10.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def compile_dual_rx_adaptive_2p5_hop_plan(
    intent: DualRxAdaptive2p5ScheduledScannerIntentV7
    | DualRxAdaptive2p5ScheduledScannerIntentV8
    | DualRxAdaptive2p5ScheduledScannerIntentV9,
    *,
    transition_guard_us: int = 1_000,
    kernel_buffers: int = 8,
    samples_per_block: int = 131_072,
) -> PersistentHopPlanV1:
    """Project either published cadence onto the existing dual-RX hop geometry."""

    intent_type = (
        DualRxAdaptive2p5ScheduledScannerIntentV9
        if isinstance(intent, DualRxAdaptive2p5ScheduledScannerIntentV9)
        else DualRxAdaptive2p5ScheduledScannerIntentV8
        if isinstance(intent, DualRxAdaptive2p5ScheduledScannerIntentV8)
        else DualRxAdaptive2p5ScheduledScannerIntentV7
    )
    intent = intent_type.model_validate(intent)
    plan = compile_persistent_hop_plan_v1(
        sample_rate_hz=DUAL_RX_RATE_HZ,
        kernel_buffers=kernel_buffers,
        transition_guard_us=transition_guard_us,
        gain_db=intent.configuration.gain_db,
        samples_per_block=samples_per_block,
    )
    if tuple(profile.target for profile in plan.profiles) != intent.configuration.targets:
        raise ValueError("dual-RX hopping targets disagree with the scheduled intent")
    return plan


def compile_dual_rx_adaptive_10m_hop_plan(
    intent: DualRxAdaptive10mScheduledScannerIntentV10,
    *,
    transition_guard_us: int = 1_000,
    kernel_buffers: int = 8,
    samples_per_block: int = 131_072,
) -> DualRxPersistentHopPlanV2:
    intent = DualRxAdaptive10mScheduledScannerIntentV10.model_validate(intent)
    guard_numerator = DUAL_RX_10M_RATE_HZ * transition_guard_us
    if transition_guard_us <= 0 or guard_numerator % 1_000_000:
        raise ValueError("dual-RX 10 MS/s transition guard must be positive and sample-exact")
    plan = DualRxPersistentHopPlanV2(
        gain_db=intent.configuration.gain_db,
        samples_per_block=samples_per_block,
        kernel_buffers=kernel_buffers,
        transition_guard_samples=guard_numerator // 1_000_000,
        profiles=tuple(
            PersistentHopProfileV1(
                target_index=index,
                fastlock_profile_index=index,
                target=target,
            )
            for index, target in enumerate(intent.configuration.targets)
        ),
    )
    if tuple(profile.target for profile in plan.profiles) != intent.configuration.targets:
        raise ValueError("dual-RX 10 MS/s hopping targets disagree with the scheduled intent")
    return plan
