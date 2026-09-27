"""Fixed same-frequency tone replacements for a previously found pilot.

These are new constructed diagnostic controls, not edits to golden fixtures.
The pilot arrays are reused with explicit virtual counters/phase resets. Every
negative array is newly generated from its recorded noise seed and has no pilot.
"""

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "src"), str(HERE.parent / "tg11")]
import tg11_dataset as dataset


NOISE_SIGMA = 300.0
TONE_AMPLITUDE = 8000.0
NEGATIVE_FREQUENCIES = ((0.0,), (4000.0,), (-50_000.0, 0.0, 50_000.0))
NEGATIVE_WEIGHTS = ((1.0,), (1.0,), (1.0, 0.5, 0.25))
SEED_BASE = 108_300_000


@dataclass(frozen=True)
class ChallengeStep:
    case: object
    kind: str
    raw: np.ndarray
    array_sha256: str
    expected_active: bool
    noise_seeds: tuple[int, ...]
    tone_frequencies_hz: tuple[float, ...]
    virtual_counter_delta_samples: int
    carrier_phase_reset: bool = True


def negative_array(rate: int, negative_index: int) -> tuple[np.ndarray, tuple[int, int]]:
    if rate not in (2_500_000, 5_000_000) or negative_index not in range(3):
        raise ValueError("unsupported frozen challenge geometry")
    count = rate * 120 // 1000
    indexes = np.arange(count, dtype=np.float64)
    frequencies = NEGATIVE_FREQUENCIES[negative_index]
    weights = np.asarray(NEGATIVE_WEIGHTS[negative_index], dtype=float)
    weights = weights / np.linalg.norm(weights)
    raw = np.empty((count, 2, 2), dtype="<i2")
    seeds = tuple(SEED_BASE + (rate // 2_500_000) * 100 + negative_index * 10 + rx
                  for rx in (0, 1))
    for receiver, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        values = NOISE_SIGMA * (rng.normal(size=count) + 1j * rng.normal(size=count))
        for index, (frequency, weight) in enumerate(zip(frequencies, weights, strict=True)):
            phase_cycles = receiver / 8 + index / 7
            values += TONE_AMPLITUDE * weight * np.exp(
                2j * np.pi * (phase_cycles + frequency * indexes / rate)
            )
        quantized = np.rint(np.column_stack((values.real, values.imag)))
        if np.any(quantized < -32768) or np.any(quantized > 32767):
            raise ValueError("challenge clipping is forbidden")
        raw[:, receiver, :] = quantized.astype("<i2")
    raw.flags.writeable = False
    return raw, seeds


def sequences() -> tuple[tuple[ChallengeStep, ...], ...]:
    cases = {case.id: case for case in dataset.controls()}
    output = []
    for rate in (2_500_000, 5_000_000):
        original = cases[f"lag3-r{rate}-pilot-cfo0-int"]
        pilot = dataset.load_iq(original)
        # Whole-second translation preserves frame phase without ever rounding
        # a large absolute counter through a floating-point value.
        origin = original.source_counter + ((2**55 // rate) + 1) * rate
        rows = []
        for step in range(7):
            counter = origin + step * rate * 120 // 1000
            translated = replace(
                original, id=f"same-cfo-r{rate}-step{step}",
                session=f"same-cfo-challenge-r{rate}", source_counter=counter,
                visit_index=step,
            )
            if step % 2 == 0:
                raw, seeds, frequencies, kind = pilot, (), (), "pilot"
            else:
                index = (step - 1) // 2
                raw, seeds = negative_array(rate, index)
                frequencies = NEGATIVE_FREQUENCIES[index]
                kind = ("same-cfo-tone", "nearby-cfo-tone", "multitone-with-same-cfo")[index]
                # Case supplies stream metadata only for in-memory negatives;
                # its inherited pilot file path is not their provenance.
                translated = replace(translated, injected=((), ()),
                                     origin="generated-in-memory-tone-challenge")
            rows.append(ChallengeStep(
                translated, kind, raw, hashlib.sha256(raw).hexdigest(),
                step % 2 == 0, seeds, frequencies,
                counter - original.source_counter,
            ))
        output.append(tuple(rows))
    return tuple(output)
