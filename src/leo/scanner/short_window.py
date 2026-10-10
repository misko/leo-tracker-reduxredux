"""Pure 20 ms acquisition geometry, power evidence, and bounded scheduling.

This is an additive capture contract. It has no detector, radio, or storage
dependencies. IF is authoritative; optional RF metadata states its authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

SAMPLE_RATE_HZ = 2_500_000
WINDOW_MS = 20
WINDOW_SAMPLES = 50_000


class ActivityDecision(StrEnum):
    ACTIVE = "active"
    QUIET = "quiet"
    UNKNOWN = "unknown"


class CounterAuthority(StrEnum):
    HARDWARE = "hardware"
    SOFTWARE_DELIVERY_ORDINAL = "software_delivery_ordinal"
    UNKNOWN = "unknown"


class ValidityAuthority(StrEnum):
    PROVIDER_ATTESTED = "provider_attested"
    DIAGNOSTIC_HOST_GUARD = "diagnostic_host_guard"
    UNKNOWN = "unknown"


class RfMappingAuthority(StrEnum):
    KNOWN = "known"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ShortWindowTarget:
    target_id: str
    if_center_hz: int
    rf_center_hz: int | None = None
    lnb_lo_hz: int | None = None
    channel: int | None = None
    edge: str | None = None
    polarization: str | None = None
    band: str | None = None
    rf_mapping_authority: RfMappingAuthority = RfMappingAuthority.UNKNOWN
    profile_id: str | None = None

    def __post_init__(self) -> None:
        if not self.target_id or self.if_center_hz <= 0:
            raise ValueError("target ID and positive requested IF are required")
        object.__setattr__(
            self, "rf_mapping_authority", RfMappingAuthority(self.rf_mapping_authority)
        )
        for value in (self.rf_center_hz, self.lnb_lo_hz, self.channel):
            if value is not None and value <= 0:
                raise ValueError("optional RF, LO, and channel values must be positive")
        if self.rf_mapping_authority is not RfMappingAuthority.UNKNOWN and (
            self.rf_center_hz is None or self.lnb_lo_hz is None
        ):
            raise ValueError("known or hypothetical RF mapping requires RF and LNB LO")
        if (
            self.rf_center_hz is not None
            and self.lnb_lo_hz is not None
            and self.rf_center_hz != self.if_center_hz + self.lnb_lo_hz
        ):
            raise ValueError("RF mapping disagrees with requested IF and LNB LO")


@dataclass(frozen=True, slots=True)
class ShortWindowConfiguration:
    targets: tuple[ShortWindowTarget, ...]
    receiver_ids: tuple[int, ...] = (0, 1)
    scheduling_receiver_id: int = 0
    sample_rate_hz: int = SAMPLE_RATE_HZ
    window_ms: int = WINDOW_MS
    threshold_dbfs: float = -38.0
    threshold_policy_id: str = "mean-component-ci16-minus38-comparison-v1"
    calibration_id: str = "uncalibrated"
    policy_id: str = "fixed-round-robin-20ms-v1"
    gain_db: float = 40.0
    transition_budget_ms: int = 100
    duration_seconds: float = 120.0
    max_visits: int = 90_000
    physical_receiver_labels: tuple[str, ...] = ("RX1", "RX2")

    def __post_init__(self) -> None:
        if self.sample_rate_hz != SAMPLE_RATE_HZ or self.window_ms != WINDOW_MS:
            raise ValueError("short-window capture requires exactly 2.5 MS/s and 20 ms")
        if not 1 <= len(self.targets) <= 8:
            raise ValueError("short-window target table requires one to eight entries")
        if len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError("target IDs must be unique")
        if len(self.receiver_ids) not in (1, 2) or len(set(self.receiver_ids)) != len(
            self.receiver_ids
        ):
            raise ValueError("receiver IDs must contain one or two unique receivers")
        if any(receiver < 0 for receiver in self.receiver_ids):
            raise ValueError("receiver IDs must be nonnegative")
        if self.scheduling_receiver_id not in self.receiver_ids:
            raise ValueError("scheduling receiver must be one of the configured receivers")
        if len(self.physical_receiver_labels) != len(self.receiver_ids):
            raise ValueError("physical receiver labels must map every software receiver")
        if not all(self.physical_receiver_labels) or len(set(self.physical_receiver_labels)) != len(
            self.physical_receiver_labels
        ):
            raise ValueError("physical receiver labels must be nonempty and unique")
        if not math.isfinite(self.threshold_dbfs) or not math.isfinite(self.gain_db):
            raise ValueError("power threshold and manual gain must be finite")
        if (
            self.threshold_dbfs != -38.0
            and self.threshold_policy_id == "mean-component-ci16-minus38-comparison-v1"
        ):
            object.__setattr__(
                self, "threshold_policy_id", "mean-component-ci16-configured-threshold-v1"
            )
        if (
            isinstance(self.transition_budget_ms, bool)
            or not isinstance(self.transition_budget_ms, int)
            or not 1 <= self.transition_budget_ms <= 100
        ):
            raise ValueError("transition budget must be an integer between 1 and 100 ms")
        if not math.isfinite(self.duration_seconds) or not 0 < self.duration_seconds <= 1800:
            raise ValueError("capture duration must be positive and at most 30 minutes")
        if isinstance(self.max_visits, bool) or not isinstance(self.max_visits, int):
            raise ValueError("maximum visits must be an integer")
        if self.max_visits < 1:
            raise ValueError("maximum visits must be positive")

    @property
    def window_samples(self) -> int:
        return WINDOW_SAMPLES

    @property
    def window_bytes(self) -> int:
        return WINDOW_SAMPLES * len(self.receiver_ids) * 4


def _ci16_samples(samples: np.ndarray) -> np.ndarray:
    values = np.asarray(samples)
    if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[2] != 2:
        raise ValueError("IQ must be little-endian CI16 [sample,receiver,I/Q]")
    if not values.flags.c_contiguous:
        raise ValueError("IQ must be C-contiguous")
    return values


def _bracket(name: str, interval: tuple[int, int]) -> None:
    if len(interval) != 2 or interval[0] < 0 or interval[0] > interval[1]:
        raise ValueError(f"{name} timestamp bracket is invalid")


@dataclass(frozen=True, slots=True)
class ShortWindowAcquisition:
    """Owned samples and source evidence, including diagnostic partial windows.

    Sample coordinates are exclusive-end coordinates in the stated authority.
    Host brackets and arrival times never imply UTC sample-time support.
    """

    samples: np.ndarray
    requested_if_center_hz: int
    actual_if_center_hz: int | None
    generation: int = 0
    sample_start: int | None = None
    counter_authority: CounterAuthority = CounterAuthority.UNKNOWN
    validity_authority: ValidityAuthority = ValidityAuthority.UNKNOWN
    host_request_utc_ns: tuple[int, int] = (0, 0)
    host_request_monotonic_ns: tuple[int, int] = (0, 0)
    host_final_sample_monotonic_ns: int = 0
    sample_start_utc_ns: tuple[int, int] | None = None
    quality_flags: tuple[str, ...] = ()
    tune_ms: float = 0.0
    listen_ms: float = 0.0
    guard_ms: float = 0.0
    discarded_samples: int = 0
    retune_receipt: str | None = None
    validity_includes_guard: bool = False
    contiguous_with_previous: bool = False
    recall_skipped: bool = False

    def __post_init__(self) -> None:
        values = _ci16_samples(self.samples)
        if values.shape[1] < 1 or len(values) > WINDOW_SAMPLES:
            raise ValueError("acquisition must contain at most one 50,000-sample window")
        if self.requested_if_center_hz <= 0 or (
            self.actual_if_center_hz is not None and self.actual_if_center_hz <= 0
        ):
            raise ValueError("acquisition IF must be positive when available")
        if self.generation < 0 or (self.sample_start is not None and self.sample_start < 0):
            raise ValueError("sample generation and start must be nonnegative")
        object.__setattr__(self, "counter_authority", CounterAuthority(self.counter_authority))
        object.__setattr__(self, "validity_authority", ValidityAuthority(self.validity_authority))
        if self.counter_authority is CounterAuthority.HARDWARE and self.sample_start is None:
            raise ValueError("hardware counter authority requires a sample start")
        _bracket("host UTC request", self.host_request_utc_ns)
        _bracket("host monotonic request", self.host_request_monotonic_ns)
        if self.host_final_sample_monotonic_ns < self.host_request_monotonic_ns[1]:
            raise ValueError("final sample arrival precedes the host request")
        if self.sample_start_utc_ns is not None:
            _bracket("sample UTC start", self.sample_start_utc_ns)
        if any(
            not math.isfinite(value) or value < 0
            for value in (self.tune_ms, self.listen_ms, self.guard_ms)
        ):
            raise ValueError("acquisition timing metrics must be finite and nonnegative")
        if self.discarded_samples < 0:
            raise ValueError("discarded sample count must be nonnegative")
        if self.validity_includes_guard and self.guard_ms > 0:
            raise ValueError("provider-included guard cannot be applied again")
        # Own the memory: borrowed DMA arrays and callers may mutate after return.
        owned = values.copy()
        owned.setflags(write=False)
        object.__setattr__(self, "samples", owned)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def sample_end(self) -> int | None:
        return None if self.sample_start is None else self.sample_start + self.sample_count

    @property
    def complete(self) -> bool:
        return self.sample_count == WINDOW_SAMPLES


class ShortWindowSource(Protocol):
    def configure_once(self, configuration: ShortWindowConfiguration) -> None: ...

    def capture(self, target: ShortWindowTarget, sample_count: int) -> ShortWindowAcquisition: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ReceiverPower:
    receiver_id: int
    physical_receiver_label: str
    sample_count: int
    energy_sum: int
    mean_i: float | None
    mean_q: float | None
    clipping_count: int
    mean_component_power: float | None
    power_dbfs: float | None
    zero_power: bool
    threshold_dbfs: float
    decision: ActivityDecision
    quality_flags: tuple[str, ...]


def classify_window(
    acquisition: ShortWindowAcquisition, configuration: ShortWindowConfiguration
) -> tuple[ReceiverPower, ...]:
    """Report exact per-RX integer energy; zero dBFS is represented by None.

    Clipping counts individual I/Q components at either int16 rail. Saturation
    blocks that receiver's activity decision without losing its measured power.
    """
    if acquisition.samples.shape[1] != len(configuration.receiver_ids):
        raise ValueError("acquisition receiver geometry disagrees with configuration")
    flags = list(acquisition.quality_flags)
    if not acquisition.complete:
        flags.append("partial_window")
    if acquisition.validity_authority is not ValidityAuthority.PROVIDER_ATTESTED:
        flags.append("unattested_validity")
    if acquisition.actual_if_center_hz is None:
        flags.append("unknown_actual_if")
    results = []
    for index, receiver_id in enumerate(configuration.receiver_ids):
        # Cast before squaring: -32768 squared exceeds int16/int32 sum bounds.
        values = acquisition.samples[:, index, :].astype(np.int64)
        energy = int(np.sum(values * values, dtype=np.int64))
        count = acquisition.sample_count
        clipping = int(np.count_nonzero((values == -32768) | (values == 32767)))
        mean_power = energy / (2 * count) if count else None
        power_dbfs = 10 * math.log10(mean_power / (32768**2)) if mean_power else None
        receiver_flags = tuple(dict.fromkeys((*flags, *(("clipping",) if clipping else ()))))
        decision = ActivityDecision.UNKNOWN
        if not receiver_flags:
            decision = (
                ActivityDecision.ACTIVE
                if power_dbfs is not None and power_dbfs >= configuration.threshold_dbfs
                else ActivityDecision.QUIET
            )
        results.append(
            ReceiverPower(
                receiver_id=receiver_id,
                physical_receiver_label=configuration.physical_receiver_labels[index],
                sample_count=count,
                energy_sum=energy,
                mean_i=float(np.sum(values[:, 0], dtype=np.int64) / count) if count else None,
                mean_q=float(np.sum(values[:, 1], dtype=np.int64) / count) if count else None,
                clipping_count=clipping,
                mean_component_power=mean_power,
                power_dbfs=power_dbfs,
                zero_power=count > 0 and energy == 0,
                threshold_dbfs=configuration.threshold_dbfs,
                decision=decision,
                quality_flags=receiver_flags,
            )
        )
    return tuple(results)


class RoundRobinScheduler:
    """Bound admission by elapsed time and visits; outcomes never alter coverage."""

    def __init__(self, configuration: ShortWindowConfiguration) -> None:
        self.configuration = configuration
        self.visits = 0
        self.stop_reason: str | None = None

    def next_target(self, elapsed_seconds: float) -> ShortWindowTarget | None:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError("elapsed time must be finite and nonnegative")
        if self.stop_reason is not None:
            return None
        if self.visits >= self.configuration.max_visits:
            self.stop_reason = "max_visits"
            return None
        if elapsed_seconds >= self.configuration.duration_seconds:
            self.stop_reason = "duration"
            return None
        target = self.configuration.targets[self.visits % len(self.configuration.targets)]
        self.visits += 1
        return target

    def stop(self, reason: str) -> None:
        if not reason:
            raise ValueError("scheduler stop reason must be explicit")
        if self.stop_reason is None:
            self.stop_reason = reason


class ShortWindowAssembler:
    """Copy clipped blocks without padding or concatenating across discontinuities.

    Start a new instance at the provider's valid boundary for every visit. A
    failure seals the actual partial payload and refuses subsequent append.
    The caller owns block release and carries these flags into acquisition.
    """

    def __init__(self, receiver_count: int, generation: int, sample_start: int) -> None:
        if receiver_count < 1 or generation < 0 or sample_start < 0:
            raise ValueError("assembler geometry and sample coordinates are invalid")
        self.generation = generation
        self.sample_start = sample_start
        self.sample_count = 0
        self.quality_flags: tuple[str, ...] = ()
        self._buffer = np.empty((WINDOW_SAMPLES, receiver_count, 2), dtype="<i2")

    @property
    def complete(self) -> bool:
        return self.sample_count == WINDOW_SAMPLES and not self.quality_flags

    @property
    def samples(self) -> np.ndarray:
        result = self._buffer[: self.sample_count].copy()
        result.setflags(write=False)
        return result

    def append(
        self,
        samples: np.ndarray,
        *,
        generation: int,
        sample_start: int,
        quality_flags: tuple[str, ...] = (),
    ) -> int:
        if self.quality_flags or self.complete:
            raise ValueError("cannot append to a sealed short window")
        values = _ci16_samples(samples)
        if values.shape[1] != self._buffer.shape[1]:
            raise ValueError("source block receiver geometry changed")
        failure = quality_flags
        if generation != self.generation:
            failure = (*failure, "generation_changed")
        if sample_start != self.sample_start + self.sample_count:
            failure = (*failure, "sample_discontinuity")
        if failure:
            self.quality_flags = tuple(dict.fromkeys(failure))
            return 0
        admitted = min(len(values), WINDOW_SAMPLES - self.sample_count)
        self._buffer[self.sample_count : self.sample_count + admitted] = values[:admitted]
        self.sample_count += admitted
        return admitted

    def fail(self, reason: str) -> None:
        if not reason:
            raise ValueError("assembly failure reason must be explicit")
        self.quality_flags = tuple(dict.fromkeys((*self.quality_flags, reason)))
