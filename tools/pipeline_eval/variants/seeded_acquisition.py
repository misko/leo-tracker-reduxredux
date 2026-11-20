"""Predict a bounded pilot search from earlier measurements on a physical RF lane."""

from dataclasses import dataclass

import numpy as np

RATE = 10_000_000
FRAME_RATE = 750
PERIOD = RATE / FRAME_RATE
EPOCHS = round(PERIOD)
SYMBOL_TIMES = 44
SYMBOLS = (2, 13, 27, 39, 51, 63)
FRAMES = (1, 3, 5, 7, 9, 11, 13)
MAX_AGE = 1.4
MAX_CFO_SLOPE = 12_000
MAX_CFO_INNOVATION = 14_000
BASE_RADIUS = 8
ALIAS = 1 / 4.4e-6


def wrapped(value, period=PERIOD):
    return (value + period / 2) % period - period / 2


def counter_phase(delta):
    """Use the rational frame period even for large hardware counters."""
    return (delta * FRAME_RATE % RATE) / FRAME_RATE


@dataclass(frozen=True, slots=True)
class Point:
    sample: int
    epoch: float
    cfo: float
    rate: float = 0
    cfo_rate: float = 0


@dataclass(frozen=True, slots=True)
class Search:
    epoch: float
    cfo: float
    radius: int
    age: float


def winner(candidates):
    return max(
        (c for c in candidates if c["passed_fractional_margin_gate"]),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def point(sample, candidate, shift=0):
    epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
    return Point(sample, (epoch + shift) % PERIOD, candidate["fractional_tracking_cfo_hz"])


class Tracker:
    def __init__(self, uncertainty_sps, *, shifted=False):
        if not 0 < uncertainty_sps <= 1000:
            raise ValueError("expected a fixed positive sample-rate uncertainty")
        self.uncertainty_sps = uncertainty_sps
        self.shifted = shifted
        self.lanes = {}

    def anchor(self, key, sample, candidates):
        candidate = winner(candidates)
        if candidate is None:
            self.lanes.pop(key, None)
        else:
            self.lanes[key] = point(sample, candidate, PERIOD / 2 if self.shifted else 0)

    def forecast(self, key, sample):
        seed = self.lanes.get(key)
        if seed is None:
            return None
        elapsed = (sample - seed.sample) / RATE
        if not 0 < elapsed <= MAX_AGE:
            return None
        phase = seed.epoch - counter_phase(sample - seed.sample) + seed.rate * elapsed
        return Search(
            phase % PERIOD,
            seed.cfo + seed.cfo_rate * elapsed,
            BASE_RADIUS + int(np.ceil(self.uncertainty_sps * elapsed)),
            elapsed,
        )

    def observe(self, key, sample, prediction, candidates):
        """Update from a fresh local decision with a bounded signed CFO innovation."""
        accepted = winner(
            [
                c
                for c in candidates
                if abs(c["fractional_tracking_cfo_hz"] - prediction.cfo) <= MAX_CFO_INNOVATION
            ]
        )
        if accepted is None:
            return False
        previous = self.lanes[key]
        current = point(sample, accepted)
        phase = wrapped(current.epoch - previous.epoch + counter_phase(sample - previous.sample))
        rate = float(np.clip(phase / prediction.age, -self.uncertainty_sps, self.uncertainty_sps))
        frequency = float(
            np.clip((current.cfo - previous.cfo) / prediction.age, -MAX_CFO_SLOPE, MAX_CFO_SLOPE)
        )
        self.lanes[key] = Point(sample, current.epoch, current.cfo, rate, frequency)
        return True


class LocalSearch:
    """Rank a small epoch window on raw known-symbol correlations before GLRT confirmation."""

    def __init__(self, exact):
        self.relative = np.asarray(SYMBOLS)[:, None] * SYMBOL_TIMES + np.arange(SYMBOL_TIMES)
        reference = np.asarray(exact, dtype=np.complex64)[self.relative]
        self.reference = np.conj(reference) / np.linalg.norm(reference, axis=1, keepdims=True)
        self.starts = np.rint(np.asarray(FRAMES) * PERIOD).astype(int)

    def rank(self, values, prediction, count=2):
        radius = prediction.radius
        epochs = (round(prediction.epoch) + np.arange(-radius, radius + 1)) % EPOCHS
        offsets = epochs[:, None, None, None] + self.starts[None, :, None, None]
        samples = values[offsets + self.relative[None, None, :, :]]
        rotation = np.exp(-2j * np.pi * prediction.cfo * self.relative / RATE).astype(np.complex64)
        score = np.einsum("efst,st->efs", samples, self.reference * rotation)
        power = np.einsum("efst,efst->efs", samples, samples.conj()).real
        normalized = np.divide(
            (score * score.conj()).real, power, out=np.zeros_like(power), where=power > 0
        )
        weights = np.mean(normalized, axis=(1, 2))
        result = []
        for _ in range(count):
            top = int(np.argmax(weights))
            result.append(int(epochs[top]))
            weights[max(0, top - 4) : top + 5] = -np.inf
        return tuple(result)
