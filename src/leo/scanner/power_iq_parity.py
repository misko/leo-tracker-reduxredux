"""Exact same-sample CI16/PWR1 numerical qualification; no device or storage IO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest


class PowerIqCounterMappingV1(ContractModel):
    kind: Literal["source_derived_power_iq_counter_mapping"] = (
        "source_derived_power_iq_counter_mapping"
    )
    qualification_scope: Literal["supplied_source_and_simulation_references"] = (
        "supplied_source_and_simulation_references"
    )
    fpga_artifact_sha256: Sha256Digest
    packer_source_sha256: Sha256Digest
    evidence_sha256: Sha256Digest
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    capture_scan_mask: Literal[15] = 15
    fpga_decimation_factor: Literal[1] = 1
    fifo_tag_offset: Literal[1] = 1
    power_counter_identity: Literal["prepack_preincrement_v1"] = "prepack_preincrement_v1"
    declared_by: Annotated[str, Field(min_length=1)]


@dataclass(frozen=True, slots=True)
class ParityFrame:
    samples: np.ndarray
    fifo_start: int
    generation: int
    buffer_sequence: int
    missing_samples_before: int = 0
    overflow: bool = False

    def __post_init__(self) -> None:
        if (
            self.samples.dtype != np.dtype("<i2")
            or self.samples.ndim != 3
            or self.samples.shape[1:] != (2, 2)
            or not 0 < len(self.samples) <= 50_000
            or not 0 <= self.fifo_start < 1 << 64
            or self.generation <= 0
            or self.buffer_sequence < 0
            or self.missing_samples_before < 0
        ):
            raise ValueError("parity frame requires exact dualRX CI16 and hardware identity")


def ci16_from_complex(samples: np.ndarray) -> np.ndarray:
    values = np.asarray(samples)
    if (
        values.ndim != 2
        or values.shape[0] != 2
        or not 0 < values.shape[1] <= 50000
        or not np.iscomplexobj(values)
    ):
        raise ValueError("paired native IQ must have [receiver,sample] complex geometry")
    output = np.empty((values.shape[1], 2, 2), dtype="<i2")
    for lane, component in enumerate((values.real.T, values.imag.T)):
        if (
            not np.all(np.isfinite(component))
            or np.any(component != np.trunc(component))
            or np.any(component < -32768)
            or np.any(component > 32767)
        ):
            raise ValueError("IQ conversion would lose exact CI16 values")
        output[:, :, lane] = component
    return output


def _pair(words: tuple[int, ...], index: int, *, signed: bool = False) -> int:
    value = words[index] | words[index + 1] << 32
    return value - (1 << 64) if signed and value & (1 << 63) else value


def same_sample_window(
    frames: list[ParityFrame], start: int, end: int, mapping: PowerIqCounterMappingV1
) -> np.ndarray:
    if len(frames) > 100 or start < 0 or end - start != 50_000 or end >= 1 << 64:
        raise ValueError("parity support must be bounded exact 50000 samples")
    output = np.empty((50_000, 2, 2), dtype="<i2")
    expected = start
    identity = None
    previous_sequence = None
    for frame in frames:
        origin = frame.fifo_start - mapping.fifo_tag_offset
        frame_end = origin + len(frame.samples)
        if frame_end <= start or origin >= end:
            continue
        if frame.missing_samples_before or frame.overflow:
            raise ValueError("parity IQ has a gap or overflow in selected support")
        if identity is None:
            identity = frame.generation
        if frame.generation != identity or (
            previous_sequence is not None and frame.buffer_sequence != previous_sequence + 1
        ):
            raise ValueError("parity IQ generation or buffer order changed")
        left, right = max(start, origin), min(end, frame_end)
        if left != expected or right <= left:
            raise ValueError("parity IQ counter support is missing, repeated or reordered")
        output[left - start : right - start] = frame.samples[left - origin : right - origin]
        expected = right
        previous_sequence = frame.buffer_sequence
    if expected != end:
        raise ValueError("captured IQ does not cover the exact PWR1 interval; never pad")
    return output


def ci16_power_oracle(samples: np.ndarray) -> tuple[dict[str, int], dict[str, int]]:
    if samples.dtype != np.dtype("<i2") or samples.shape != (50_000, 2, 2):
        raise ValueError("power oracle needs exact 50000 dualRX CI16 tuples")
    metrics = []
    for rx in range(2):
        components = samples[:, rx, :].astype(np.int64)
        metrics.append(
            {
                "energy_sum": int(np.sum(components * components, dtype=np.int64)),
                "sum_i": int(np.sum(components[:, 0], dtype=np.int64)),
                "sum_q": int(np.sum(components[:, 1], dtype=np.int64)),
                "clipping_i": int(
                    np.count_nonzero((components[:, 0] == -32768) | (components[:, 0] == 32767))
                ),
                "clipping_q": int(
                    np.count_nonzero((components[:, 1] == -32768) | (components[:, 1] == 32767))
                ),
                "adc12_contact_samples": int(
                    np.count_nonzero(np.any((components == -2048) | (components == 2047), axis=1))
                ),
                "peak_abs_component": int(np.max(np.abs(components))),
            }
        )
    return tuple(metrics)


def qualify_power_iq(
    frames: list[ParityFrame],
    raw_words: list[int] | tuple[int, ...],
    *,
    mapping: PowerIqCounterMappingV1,
    session: int,
    generation: int,
    adc12_qualified: bool,
) -> dict:
    words = tuple(raw_words)
    if (
        len(words) != 36
        or any(type(word) is not int or not 0 <= word < 1 << 32 for word in words)
        or words[:2] != (0x50575231, 0x00010000)
        or words[3] != 50_000
        or (words[4], words[5]) != (session, generation)
        or words[2] & ~64
        or any(words[index] for index in (6, 7, 8, 9, 34, 35))
    ):
        raise ValueError("PWR1 parity identity/ABI/count or integrity flags are invalid")
    start, end = _pair(words, 10), _pair(words, 12)
    samples = same_sample_window(frames, start, end, mapping)
    expected = ci16_power_oracle(samples)
    observed = tuple(
        {
            "energy_sum": _pair(words, 14 + 2 * rx),
            "sum_i": _pair(words, 18 + 4 * rx, signed=True),
            "sum_q": _pair(words, 20 + 4 * rx, signed=True),
            "clipping_i": words[26 + 2 * rx],
            "clipping_q": words[27 + 2 * rx],
            "adc12_contact_samples": words[30 + rx],
            "peak_abs_component": words[32 + rx],
        }
        for rx in range(2)
    )
    clipped = any(
        value["clipping_i"]
        or value["clipping_q"]
        or (adc12_qualified and value["adc12_contact_samples"])
        for value in expected
    )
    mismatch = [
        {
            "receiver_id": rx,
            "field": key,
            "expected": expected[rx][key],
            "observed": observed[rx][key],
        }
        for rx in range(2)
        for key in expected[rx]
        if expected[rx][key] != observed[rx][key]
    ]
    if words[2] != (64 if clipped else 0):
        mismatch.append(
            {
                "field": "qualified_clipping_flag",
                "expected": 64 if clipped else 0,
                "observed": words[2],
            }
        )
    return {
        "kind": "integer_power_iq_parity_under_supplied_mapping",
        "passed": not mismatch,
        "numerical_parity_passed": not mismatch,
        "mapping_independently_validated": False,
        "physical_mapping_qualified": False,
        "sample_start": start,
        "sample_end_exclusive": end,
        "sample_count": 50000,
        "counter_mapping": mapping.model_dump(mode="json"),
        "expected": list(expected),
        "observed": list(observed),
        "mismatches": mismatch,
        "adc12_qualified": adc12_qualified,
        "observed_signed12_range": bool(np.all((samples >= -2048) & (samples <= 2047))),
        "qualified_tracking": False,
    }
