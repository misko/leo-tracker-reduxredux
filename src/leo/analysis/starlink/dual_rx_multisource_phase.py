"""Identifiability-safe dual-receiver phase differences for shared sources.

The input transfer phasor convention is RX1 times conjugate(RX0).  At one
common epoch its phase is modeled as::

    theta_rx(time) + phi_source(time) - 2*pi*frequency*delay_rx1_minus_rx0

Pair differences cancel ``theta_rx``.  They do not separate source geometry
from differential receiver/channel phase unless those instrument terms have
independent calibration authority.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class PhaseIdentifiability(StrEnum):
    """What the reported pair phase is allowed to mean."""

    COMBINED_GEOMETRY_AND_INSTRUMENT = "combined_geometry_and_instrument"
    DELAY_CORRECTED_GEOMETRY_AND_INSTRUMENT = "delay_corrected_geometry_and_instrument"


@dataclass(frozen=True, slots=True)
class SharedSourceTransfer:
    """One phase-blind source match observed simultaneously by both receivers."""

    source_id: str
    baseband_frequency_hz: float
    rx1_times_conjugate_rx0: complex
    weight: float

    def __post_init__(self) -> None:
        values = (
            self.baseband_frequency_hz,
            self.rx1_times_conjugate_rx0.real,
            self.rx1_times_conjugate_rx0.imag,
            self.weight,
        )
        if not self.source_id or not all(math.isfinite(value) for value in values):
            raise ValueError("shared source transfer fields must be finite and identified")
        if self.rx1_times_conjugate_rx0 == 0 or self.weight <= 0:
            raise ValueError("shared source transfer must have nonzero support and weight")


@dataclass(frozen=True, slots=True)
class SharedTransferBlock:
    """Transfers whose extraction support has one explicitly common epoch."""

    block_id: str
    common_time_s: float
    sources: tuple[SharedSourceTransfer, ...]

    def __post_init__(self) -> None:
        if not self.block_id or not math.isfinite(self.common_time_s):
            raise ValueError("shared transfer block must have an identity and finite time")
        identities = tuple(source.source_id for source in self.sources)
        if len(self.sources) < 2 or len(set(identities)) != len(identities):
            raise ValueError("shared transfer block requires at least two unique sources")


@dataclass(frozen=True, slots=True)
class DifferentialDelayCalibration:
    """Independent RX1-minus-RX0 group-delay authority."""

    delay_s: float
    standard_error_s: float
    authority: str

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.delay_s)
            or not math.isfinite(self.standard_error_s)
            or self.standard_error_s < 0
            or not self.authority
        ):
            raise ValueError("differential delay calibration must be finite and authoritative")


@dataclass(frozen=True, slots=True)
class PairPhaseDifference:
    """Wrapped source-B minus source-A receiver phase at one common epoch.

    ``delay_correction_standard_error_rad`` covers only the supplied delay
    calibration.  It is not total measurement or geometry uncertainty.
    """

    block_id: str
    common_time_s: float
    source_a: str
    source_b: str
    frequency_difference_hz: float
    combined_phase_rad: float
    delay_corrected_combined_phase_rad: float | None
    delay_correction_standard_error_rad: float | None
    weight: float


@dataclass(frozen=True, slots=True)
class IndependentPairPhase:
    """One independently extracted directed source-pair phase for closure tests."""

    block_id: str
    source_a: str
    source_b: str
    phase_b_minus_a_rad: float

    def __post_init__(self) -> None:
        if (
            not self.block_id
            or not self.source_a
            or not self.source_b
            or self.source_a == self.source_b
            or not math.isfinite(self.phase_b_minus_a_rad)
        ):
            raise ValueError("independent pair phase must be finite and directed")


@dataclass(frozen=True, slots=True)
class MultiSourcePhaseEstimate:
    """Pair observables with an explicit instrument/geometry boundary."""

    identifiability: PhaseIdentifiability
    pair_differences: tuple[PairPhaseDifference, ...]
    affine_frequency_nullspace: str | None
    delay_authority: str | None


def _wrap(phase_rad: float) -> float:
    return float(np.angle(np.exp(1j * phase_rad)))


def estimate_multisource_phase(
    blocks: tuple[SharedTransferBlock, ...],
    *,
    delay_calibration: DifferentialDelayCalibration | None = None,
) -> MultiSourcePhaseEstimate:
    """Cancel common receiver phase and retain every simultaneous source pair.

    Pairing, frequency-branch selection, and overlap qualification must occur
    independently of phase before constructing these blocks.
    """

    if not blocks or len({block.block_id for block in blocks}) != len(blocks):
        raise ValueError("phase estimation requires uniquely identified blocks")
    pairs: list[PairPhaseDifference] = []
    for block in blocks:
        ordered = sorted(block.sources, key=lambda item: item.source_id)
        for source_a, source_b in itertools.combinations(ordered, 2):
            frequency_difference_hz = (
                source_b.baseband_frequency_hz - source_a.baseband_frequency_hz
            )
            combined = _wrap(
                np.angle(source_b.rx1_times_conjugate_rx0)
                - np.angle(source_a.rx1_times_conjugate_rx0)
            )
            corrected = None
            delay_sigma = None
            if delay_calibration is not None:
                # A positive RX1 delay contributes -2*pi*f*delay to each
                # transfer, so source differencing is corrected by addition.
                corrected = _wrap(
                    combined + 2 * math.pi * frequency_difference_hz * delay_calibration.delay_s
                )
                delay_sigma = (
                    2 * math.pi * abs(frequency_difference_hz) * delay_calibration.standard_error_s
                )
            pairs.append(
                PairPhaseDifference(
                    block_id=block.block_id,
                    common_time_s=block.common_time_s,
                    source_a=source_a.source_id,
                    source_b=source_b.source_id,
                    frequency_difference_hz=frequency_difference_hz,
                    combined_phase_rad=combined,
                    delay_corrected_combined_phase_rad=corrected,
                    delay_correction_standard_error_rad=delay_sigma,
                    weight=min(source_a.weight, source_b.weight),
                )
            )
    calibrated = delay_calibration is not None
    return MultiSourcePhaseEstimate(
        identifiability=(
            PhaseIdentifiability.DELAY_CORRECTED_GEOMETRY_AND_INSTRUMENT
            if calibrated
            else PhaseIdentifiability.COMBINED_GEOMETRY_AND_INSTRUMENT
        ),
        pair_differences=tuple(pairs),
        affine_frequency_nullspace=(
            None
            if calibrated
            else (
                "delay += delta and source_phase += 2*pi*frequency*delta "
                "leave every transfer and pair difference unchanged"
            )
        ),
        delay_authority=(delay_calibration.authority if delay_calibration is not None else None),
    )


def independent_three_source_closure(
    pair_ab: IndependentPairPhase,
    pair_bc: IndependentPairPhase,
    pair_ac: IndependentPairPhase,
) -> float:
    """Return wrapped ``AB + BC - AC`` for three independent pair estimates."""

    if (
        pair_ab.block_id != pair_bc.block_id
        or pair_ab.block_id != pair_ac.block_id
        or pair_ab.source_b != pair_bc.source_a
        or pair_ab.source_a != pair_ac.source_a
        or pair_bc.source_b != pair_ac.source_b
    ):
        raise ValueError("closure requires independent A->B, B->C, and A->C estimates")
    return _wrap(
        pair_ab.phase_b_minus_a_rad + pair_bc.phase_b_minus_a_rad - pair_ac.phase_b_minus_a_rad
    )
