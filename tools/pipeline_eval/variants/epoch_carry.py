"""Forecast one pilot start from earlier native factors in the same RF lane."""

from collections import deque
from dataclasses import dataclass
from statistics import median

FRAME_HZ = 750
ALIAS_HZ = 1 / 4.4e-6
MAX_HOLD_S = 0.120
MAX_SLOPE_SAMPLES_S = 500.0
MAX_CFO_STEP_HZ = 2000.0
MIN_STAMPS = 3


def wrap(value, period):
    return (value + period / 2) % period - period / 2


@dataclass(frozen=True)
class Pilot:
    sample: int
    phase: float
    cfo: float
    rank: int
    margin: float


class Holdover:
    def __init__(self, rate):
        self.rate = rate
        self.period = rate / FRAME_HZ
        self.lanes = {}

    def global_phase(self, sample, epoch):
        return ((sample * FRAME_HZ % self.rate) / FRAME_HZ + epoch) % self.period

    def forecast(self, lane, sample):
        stamps = self.lanes.get(lane, ())
        if len(stamps) < MIN_STAMPS:
            return None
        last = stamps[-1]
        hold = (sample - last.sample) / self.rate
        if not 0 < hold <= MAX_HOLD_S:
            return None
        dx = [
            wrap(b.phase - a.phase, self.period) * self.rate / (b.sample - a.sample)
            for a, b in zip(stamps, tuple(stamps)[1:], strict=False)
        ]
        rate = median(dx)
        return dict(
            epoch=self.global_phase(-sample, last.phase + rate * hold),
            cfo_hz=last.cfo,
            seconds=hold,
            drift_samples_s=rate,
            prior_samples=[p.sample for p in stamps],
        )

    def null_channel(self, lane, sample):
        alternatives = []
        for other in self.lanes:
            if other[0] == lane[0] and other[1] != lane[1]:
                candidate = self.forecast(other, sample)
                if candidate is not None:
                    alternatives.append((candidate["seconds"], other, candidate))
        return min(alternatives, default=(None, None, None))[2]

    def advance(self, lane, sample, candidates):
        stamps = self.lanes.setdefault(lane, deque(maxlen=4))
        if stamps and sample <= stamps[-1].sample:
            raise ValueError("sample counter did not advance in receiver lane")
        points = [
            Pilot(
                sample,
                self.global_phase(
                    sample, c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
                ),
                c["fractional_tracking_cfo_hz"],
                c["candidate_rank"],
                c["fractional_margin"],
            )
            for c in candidates
            if c["passed_fractional_margin_gate"]
        ]
        if not points:
            return
        if stamps:
            before = stamps[-1]
            elapsed = (sample - before.sample) / self.rate
            predicted = self.forecast(lane, sample)
            expect = before.phase
            if predicted is not None:
                expect = self.global_phase(sample, predicted["epoch"])
            matches = [
                p
                for p in points
                if elapsed <= MAX_HOLD_S
                and abs(wrap(p.phase - before.phase, self.period)) <= MAX_SLOPE_SAMPLES_S * elapsed
                and abs(wrap(p.cfo - before.cfo, ALIAS_HZ)) <= MAX_CFO_STEP_HZ
            ]
            if matches:
                stamps.append(
                    min(
                        matches,
                        key=lambda p: (abs(wrap(p.phase - expect, self.period)), -p.margin, p.rank),
                    )
                )
                return
        stamps.clear()
        stamps.append(min(points, key=lambda p: (-p.margin, p.rank)))
